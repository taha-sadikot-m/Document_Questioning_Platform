from docling.document_converter import DocumentConverter

converter = DocumentConverter()

# --- Product Feedback ---
source = "../Product Feedback - SYM.pdf"
doc = converter.convert(source).document
md = doc.export_to_markdown()
print(md)
with open("product_feedback.md", "w") as f:
    f.write(md)

# --- N-ERGY Internship ---
source = "../N-ERGY Internship_ Take Home Interview.pdf"
doc = converter.convert(source).document
md = doc.export_to_markdown()
print(md)
with open("n-ergy_internship.md", "w") as f:
    f.write(md)

# .docx file
source = "../Product Feedback - SYM.docx"
doc = converter.convert(source).document
md = doc.export_to_markdown()
print(md)
with open("product_feedback_docx.md", "w") as f:
    f.write(md)


# .txt file
source = "../demo.txt"
doc = converter.convert(source).document
md = doc.export_to_markdown()
print(md)
with open("demo_txt.md", "w") as f:
    f.write(md)