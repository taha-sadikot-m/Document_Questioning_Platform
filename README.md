# DocIntel — Document Intelligence System

A RAG (Retrieval-Augmented Generation) application that lets users upload documents, ask natural language questions, and receive cited answers grounded exclusively in the uploaded content.

---

## Optimization Choice: **Accuracy**

This system is optimized for **accuracy over latency**.

**Why:** The primary use case is knowledge extraction from technical or business documents where a wrong answer is worse than a slow one. Users uploading contracts, research papers, or project specs need to trust every sentence in the response. Latency sacrifices were made deliberately at every layer — larger retrieval pool (`TOP_K=20`), re-ranking with keyword boosting, hybrid chunking with heading context, mandatory inline citations, and a confidence-tier system — all of which add processing time but significantly reduce hallucination and irrelevant answers.

---

## Architecture Overview

```
User (Browser)
     │
     ▼
Flask Web Server  (application/main.py)
     │
     ├── /upload  ──► DocumentConverter (Docling)
     │                    │
     │                    ▼
     │               HybridChunker (512-token chunks with heading breadcrumbs)
     │                    │
     │                    ▼
     │               SentenceTransformer embeddings (all-MiniLM-L6-v2)
     │                    │
     │                    ▼
     │               ChromaDB (persistent cosine-similarity vector store)
     │                    │
     │                    ▼
     │               doc_registry.json  (metadata persistence across restarts)
     │
     └── /query  ──► ChromaDB.query (TOP_K=20 candidates)
                          │
                          ▼
                     Score boosting (semantic + keyword term hits)
                     TOP_N=6 chunks selected
                          │
                          ▼
                     Gemini 2.5 Flash (system_instruction + XML-delimited prompt)
                          │
                          ▼
                     Cited answer 
```

**Stack:** Python · Flask · Docling · ChromaDB · SentenceTransformers · Google Gemini 2.5 Flash

---

## Key Design Decisions

### 1. Docling for document conversion
Docling is used as the single unified converter for all supported file types — PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and more. The alternative would be maintaining a separate dedicated library for each format (`PyMuPDF` for PDF, `python-docx` for Word, `python-pptx` for PowerPoint, `Pillow`+OCR for images, etc.), each with its own API, error surface, and output format that would need to be normalised before chunking. Docling handles all of these through one consistent interface and produces a unified `DoclingDocument` structure regardless of input format, which means the chunking and embedding pipeline never needs to know what file type it received.

Beyond format unification, Docling preserves document structure (headings, tables, page numbers) that plain text extractors discard. The `HybridChunker` uses this structure to keep semantically coherent chunks and prepend heading breadcrumbs via `contextualize()`, which improves embedding quality for section-specific queries.

### 2. Two-stage retrieval (TOP_K → TOP_N)
Retrieve 20 candidates from ChromaDB, then re-rank by adding a small keyword-hit boost before selecting the top 6 for the LLM context. This avoids over-relying on pure cosine similarity which can miss exact-term matches on domain-specific vocabulary.

### 3. Accuracy-first prompting
- `system_instruction` API parameter keeps rules in Gemini's privileged instruction channel rather than mixing them into the user-data turn.
- XML delimiters (`<document_chunks>`, `<question>`, `<answer>`) give the model unambiguous structural boundaries.
- Knowledge firewall instruction explicitly forbids the model from supplementing with training knowledge.
- Chain-of-thought gate asks the model to identify relevant chunks before composing the answer.

### 4. Persistent registry (`doc_registry.json`)
ChromaDB persists vectors to disk automatically. `DOC_REGISTRY` (document metadata) is mirrored to a JSON file on every write using an atomic tmp-then-rename pattern, so the sidebar survives server restarts without re-uploading.

### 5. Citation indexing starts at 1
Context chunks are labelled `[1]…[n]` in the prompt. The LLM cites with the same numbers. A placeholder-swap render strategy (tokens → marked.parse → HTML spans) prevents the markdown parser from interpreting `[1][2]` as a reference-style link and stripping the brackets.

---

## Tradeoffs Made

| Decision | Benefit | Cost |
|---|---|---|
| `all-MiniLM-L6-v2` embeddings (local) | No API cost, no latency for embedding calls | Lower embedding quality vs. text-embedding-004 or OpenAI ada-002 |
| TOP_K=20, TOP_N=6 | Higher recall before re-ranking | More ChromaDB I/O; larger LLM context window usage |
| Gemini 2.5 Flash | Fast + cheap for the generation step | Slightly less instruction-following than larger models |
| Docling conversion | Rich structure extraction | Slow for large PDFs; adds 2–10s per upload |
| All uploads stored on local disk | Simple, no external dependencies | Not suitable for multi-instance or cloud deployment |
| In-process Flask server | Zero-config development setup | No concurrency — one upload blocks all other requests |

---

## What Would Break at Scale (10k+ Documents)

1. **ChromaDB single-file SQLite backend** — ChromaDB's default persistent store uses SQLite which does not scale past ~100k vectors without significant latency degradation. A distributed vector DB (Pinecone, Weaviate, Qdrant cluster) would be required.

2. **In-memory + JSON registry** — `DOC_REGISTRY` is a plain Python dict loaded entirely into RAM. At 10k documents this is still fine, but concurrent writes from multiple workers would corrupt `doc_registry.json` without a proper database (PostgreSQL, Redis).

3. **Synchronous upload processing** — Docling conversion and embedding generation block the Flask request thread. A single large PDF can take 10–30 seconds. At scale this needs an async task queue (Celery + Redis) with a progress polling endpoint.

4. **Single embedding model instance** — `SentenceTransformer` is loaded once at startup and runs on CPU. Under concurrent load, all embedding requests are serialised through one model. Multiple workers with a dedicated embedding service (or GPU) would be needed.

5. **No pagination on `/documents`** — The endpoint returns all documents in one response. At 10k documents this becomes a large payload. Cursor-based pagination is needed.

6. **TOP_K=20 fixed retrieval** — With 10k+ documents and millions of chunks, a fixed TOP_K of 20 may miss relevant content. A two-tower retrieval approach (coarse ANN search → fine cross-encoder re-rank) would be needed.

---

## What I Would Improve With More Time

- **Streaming responses** — Stream Gemini output token-by-token to the frontend via SSE so users see the answer building rather than waiting for the full response.
- **Cross-encoder re-ranking** — Replace the simple keyword-boost scorer with a proper cross-encoder (e.g., `ms-marco-MiniLM`) for significantly better chunk selection.
- **OCR support** — Integrate Tesseract or Docling's OCR pipeline for scanned image PDFs that currently produce zero chunks.
- **Async ingestion queue** — Move document processing to a Celery worker so uploads return immediately with a job ID that the frontend polls.
- **User sessions / multi-tenancy** — Scope documents and queries per user with a simple auth layer so multiple users can use the system independently.
- **Evaluation harness** — Add a test suite that runs a fixed set of queries against known documents and measures citation accuracy and answer faithfulness (using RAGAs or a similar framework).
- **Chunk deduplication** — Detect and skip re-uploading documents whose content hash already exists in the registry.
- **GraphRAG for complex knowledge representation** — The current flat vector retrieval treats every chunk independently, losing cross-document relationships and multi-hop reasoning (e.g., "Person A reported to Person B who approved Project C"). GraphRAG builds a knowledge graph on top of the documents — entities, relationships, and communities — enabling the retrieval step to traverse connections rather than just finding similar text. This would significantly improve accuracy on queries that require synthesising facts spread across multiple documents or reasoning about entities and their relationships, at the cost of a much more complex ingestion pipeline and higher storage requirements.

---

## Setup

```bash
cd application
pip install -r ../requirements.txt

# Add your Gemini API key
echo "GEMINI_API_KEY=your_key_here" > .env

python main.py
# → http://localhost:8080
```

Supported file types: `PDF · DOCX · TXT · MD · HTML · PPTX · XLSX · CSV · JSON · JPG · PNG · JPEG`
