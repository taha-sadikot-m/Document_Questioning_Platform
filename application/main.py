from flask import Flask,render_template, request, jsonify
from flask_cors import CORS
import logging
from dotenv import load_dotenv
from pathlib import Path
import os
import chromadb
from chromadb.utils import embedding_functions
from google import genai

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from transformers import AutoTokenizer
from sentence_transformers import CrossEncoder

from datetime import datetime
import re


import uuid

import json

load_dotenv()  # Load GEMINI_API_KEY from .env if present

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

#Directory Setup
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
log.info(f"Upload folder is set to: {UPLOAD_FOLDER.resolve()}")

CHROMA_PATH   = Path("chroma_db")
CHROMA_PATH.mkdir(exist_ok=True)
log.info(f"Chroma DB path is set to: {CHROMA_PATH.resolve()}")

#Global Varibales for chunking, embedding and retrieval
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html",".pptx",".xlsx",".csv",".json",".jpg",".png",".jpeg"}
MAX_TOKENS  = 512   
TOP_K       = 20    
TOP_N       = 6     


#Gemini API Key Setup
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    gemini_client = None
    log.warning("GEMINI_API_KEY not found in environment variables. Please set it in the .env file.")
else:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    log.info("GEMINI_API_KEY successfully loaded from environment variables.")


#vectory store setup
chromadb_client = chromadb.PersistentClient(path=CHROMA_PATH)
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/all-MiniLM-L6-v2")
#embedding_function = embedding_functions.GoogleGeminiEmbeddingFunction(api_key=GEMINI_API_KEY)
collection = chromadb_client.get_or_create_collection(name="documents", embedding_function=embedding_function,metadata={"hnsw:space": "cosine"})
log.info("ChromaDB collection 'documents' is ready for use.")

#document Processing Setup
document_converter = DocumentConverter()
tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
chunker = HybridChunker(tokenizer=tokenizer, max_tokens=MAX_TOKENS, merge_peers=True)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
log.info("Application setup complete. Ready to process documents and handle queries.")

#Global Data Storing
REGISTRY_PATH = Path("doc_registry.json")

def _save_registry() -> None:
    """Write DOC_REGISTRY to disk atomically."""
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(DOC_REGISTRY, indent=2), encoding="utf-8")
    tmp.replace(REGISTRY_PATH)

if REGISTRY_PATH.exists():
    try:
        DOC_REGISTRY: dict[str, dict] = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        log.info(f"Loaded {len(DOC_REGISTRY)} documents from registry cache.")
    except Exception:
        log.warning("Registry file corrupted — starting with empty registry.")
        DOC_REGISTRY: dict[str, dict] = {}
else:
    DOC_REGISTRY: dict[str, dict] = {}



def _infer_content_type(text: str) -> str:
    """Infer content type based on simple heuristics."""
    if text.strip().startswith("#"):
        return "heading"
    elif len(text.split()) < 5:
        return "short_text"
    else:
        return "paragraph"


def document_upload(file_path: str, file_name:str)-> dict:
    doc_id = str(uuid.uuid4())

    # Reject empty files before even attempting conversion
    if Path(file_path).stat().st_size < 50:
        raise ValueError(f"'{file_name}' appears to be empty (file size < 50 bytes).")

    try:
        result = document_converter.convert(file_path)
        doc = result.document
        log.info(f"Document '{file_name}' converted successfully with {len(doc.pages)} pages.")
    except Exception as e:
        log.error("Docling conversion failed", exc_info=True)
        raise ValueError(f"Could not read '{file_name}'. The file may be corrupted, password-protected, or in an unsupported format.") from e

    chunk = chunker.chunk(dl_doc=doc)
    chunks = list(chunk)
    if len(chunks) == 0:
        raise ValueError(f"'{file_name}' contains no extractable text. It may be a scanned image PDF with no text layer.")
    else:
        log.info(f"Document '{file_name}' chunked into {len(chunks)} chunks.")

    id = []
    texts = []
    metadata = []
    for idx, chunk in enumerate(chunks):
        # contextualize adds heading breadcrumb — improves semantic precision
        text = chunker.contextualize(chunk=chunk)

        if not text.strip():
            continue

        # Token count for metadata / diagnostics
        token_count = len(tokenizer.encode(text))

        # Section path from chunk metadata (headings breadcrumb)
        section_path = ""
        if hasattr(chunk, "meta") and chunk.meta:
            headings = getattr(chunk.meta, "headings", None)
            if headings:
                section_path = " > ".join(headings)

        # Page number (Docling provides this for PDFs)
        page_num = None
        if hasattr(chunk, "meta") and chunk.meta:
            prov = getattr(chunk.meta, "doc_items", [])
            if prov:
                first_item = prov[0]
                if hasattr(first_item, "prov") and first_item.prov:
                    page_num = getattr(first_item.prov[0], "page_no", None)

        chunk_id = f"{doc_id}__chunk_{idx}"
        id.append(chunk_id)
        texts.append(text)
        metadata.append({
            "doc_id":       doc_id,
            "filename":     file_name,
            "chunk_idx":    idx,
            "page_num":     str(page_num) if page_num else "unknown",
            "section_path": section_path,
            "token_count":  token_count,
            "content_type": _infer_content_type(text),
        })

    if not id:
        raise ValueError("All chunks were empty after contextualization.")


    collection.upsert(
        ids=id,
        documents=texts,
        metadatas=metadata
    )
    log.info(f"Upserted {len(id)} chunks into ChromaDB for document '{file_name}' with doc_id '{doc_id}'.")

    doc_info = {
        "doc_id":     doc_id,
        "filename":   file_name,
        "chunk_count": len(id),
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    DOC_REGISTRY[doc_id] = doc_info
    _save_registry()
    log.info(f"Registry saved ({len(DOC_REGISTRY)} total documents).")

    return doc_info

def get_data_from_vector(query:str, doc_id:list[str] | None = None)-> list[dict]:
    where_filter = None
    if doc_id:
        if len(doc_id) == 1:
            where_filter = {"doc_id": {"$eq": doc_id[0]}}
        else:
            where_filter = {"doc_id": {"$in": doc_id}}

    results = collection.query(
        query_texts=[query],
        n_results=min(TOP_K, collection.count()),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    if results["ids"][0] == []:
        log.warning(f"No chunks found in ChromaDB for query '{query}' with doc_id filter '{doc_id}'.")
        return []
    
    chunks = []
    for i, chunk_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i]
        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity score 0–1
        similarity = 1 - (distance / 2)

        chunks.append({
            "chunk_id":     chunk_id,
            "text":         results["documents"][0][i],
            "metadata":     results["metadatas"][0][i],
            "score":        round(similarity, 4),
        })

    # Cross-encoder reranking: jointly scores (query, chunk) pairs — same
    # mechanism as Cohere Rerank but runs locally with no API cost.
    # Scores are raw logits (unbounded) — only their relative order matters.
    if chunks:
        pairs = [(query, chunk["text"]) for chunk in chunks]
        ce_scores = reranker.predict(pairs)
        for chunk, score in zip(chunks, ce_scores):
            chunk["score"] = round(float(score), 4)

    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks[:TOP_N]

SYSTEM_PROMPT = """You are a precise document intelligence assistant.
Your ONLY knowledge source is the document chunks provided in each query.

CRITICAL — KNOWLEDGE FIREWALL:
Treat the document chunks as the only source of truth that exists.
Do NOT supplement, extrapolate, or draw on your training knowledge.
If a fact is not explicitly stated in the chunks, it does not exist.

BEFORE WRITING YOUR ANSWER — internal reasoning steps (do NOT include in output):
1. Identify which chunk numbers [n] contain information directly relevant to the question.
2. Note any contradictions or gaps between chunks.
3. Only then compose your final answer using those chunks.

CITATION RULES:
1. Cite every claim inline immediately after the claim using [n].
2. If multiple chunks support one claim, cite all: [1][3] — never [1,3] or (see [1]).
3. Never group citations at the end of a paragraph.

EXAMPLE (correct citation style):
  Q: What is the budget for Phase 1?
  A: The Phase 1 budget is $240,000 [2]. This includes hardware
     procurement [2] and a 10% contingency reserve [5].

STYLE: Be concise but complete. Use markdown formatting. No filler phrases."""


def generate_context(chunks:list[dict])-> str:
    part = []
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"]
        source_label = meta.get("filename", "unknown")
        page          = meta.get("page_num", "?")
        section       = meta.get("section_path", "")
        if page =="unknown":
            loc = ""
        else:
            loc = f"p.{page}"
        
        if section:
            sec = f"{section}"
        else:
            sec = ""

        part.append(f"[{i+1}] (Source: {source_label}{', ' + loc if loc else ''}{sec})\n{chunk['text']}")

    return "\n\n---\n\n".join(part)


def llm_calling(query: str, chunks: list[dict]) -> dict:

    if GEMINI_API_KEY is None:
        log.error("GEMINI_API_KEY is not set. Cannot call Gemini API.")
        return {"error": "GEMINI_API_KEY not configured."}

    if len(chunks) == 0:
        log.warning("No chunks provided for LLM context. Returning default message.")
        return {
            "answer": "I could not find an answer in the provided documents.",
            "citations": [],
            "chunks_used": [],
        }

    context = generate_context(chunks)
    prompt  = f"""<document_chunks>
{context}
</document_chunks>

<question>
{query}
</question>

<answer>"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        answer_text = response.text
        log.info(f"LLM response generated successfully for query '{query}'.")
    except Exception as e:
        log.error("LLM generation failed", exc_info=True)
        log.error(f"Error details: {e}")
        return {"error": "LLM generation failed."}

    cited_nums = sorted(set(int(n) for n in re.findall(r"\[(\d+)\]", answer_text)))
    cited_chunks = [chunks[n - 1] for n in cited_nums if 1 <= n <= len(chunks)]

    citations = []
    for n in cited_nums:
        if 1 <= n <= len(chunks):
            meta = chunks[n - 1]["metadata"]
            citations.append({
                "ref":      n,
                "filename": meta.get("filename", "unknown"),
                "page":     meta.get("page_num", "?"),
                "section":  meta.get("section_path", ""),
                "score":    chunks[n - 1]["score"],
            })

    return {
        "answer":      answer_text,
        "citations":   citations,
        "chunks_used": [
            {
                "ref":      i + 1,
                "filename": c["metadata"].get("filename"),
                "page":     c["metadata"].get("page_num"),
                "section":  c["metadata"].get("section_path"),
                "score":    c["score"],
                "preview":  c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
            }
            for i, c in enumerate(chunks)
        ],
    }



@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files   = request.files.getlist("files")
    results = []
    errors  = []

    for f in files:
        if not f.filename:
            continue

        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            errors.append({"filename": f.filename, "error": f"Unsupported type: {ext}"})
            continue

        # Save to disk
        safe_name = f"{uuid.uuid4().hex}{ext}"
        save_path = UPLOAD_FOLDER / safe_name
        f.save(save_path)

        try:
            summary = document_upload(save_path, f.filename)
            results.append(summary)
        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})
            log.error(f"Ingestion failed for {f.filename}: {e}")
            # Clean up the saved file so failed uploads don't accumulate on disk
            if save_path.exists():
                save_path.unlink()
                log.info(f"Cleaned up orphaned file: {save_path}")

    return jsonify({"ingested": results, "errors": errors})


@app.route("/documents", methods=["GET"])
def list_documents():
    return jsonify({"documents": list(DOC_REGISTRY.values())})

@app.route("/documents/<doc_id>", methods=["DELETE"])
def delete_document(doc_id: str):
    if doc_id not in DOC_REGISTRY:
        return jsonify({"error": "Document not found"}), 404

    results = collection.get(where={"doc_id": {"$eq": doc_id}}, include=[])
    if results["ids"]:
        collection.delete(ids=results["ids"])

    del DOC_REGISTRY[doc_id]
    _save_registry()
    log.info(f"Deleted doc_id={doc_id}")
    return jsonify({"deleted": doc_id})


@app.route("/query", methods=["POST"])
def ask():
    body  = request.get_json(force=True)
    query = (body.get("query") or "").strip()

    if not query:
        return jsonify({"error": "Empty query"}), 400

    doc_ids = body.get("doc_ids") or None  # None → search all docs

    if collection.count() == 0:
        return jsonify({
            "answer":"No documents have been ingested yet. Please upload documents first.",
            "citations":[],
            "chunks_used":[],
            "query":query,
        })

    chunks = get_data_from_vector(query, doc_id=doc_ids)
    result = llm_calling(query, chunks)
    result["query"] = query

    return jsonify(result)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":         "ok",
        "total_chunks":   collection.count(),
        "total_docs":     len(DOC_REGISTRY),
        "gemini_ready":   gemini_client is not None,
    })


 
if __name__ == "__main__":
    app.run(debug=True, port=8080, host="0.0.0.0")