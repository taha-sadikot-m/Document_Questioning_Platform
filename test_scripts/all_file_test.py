import os
from docling.document_converter import DocumentConverter

# Initialize the converter
converter = DocumentConverter()

# List of all files you want to test
files_to_test = [
    "../Product Feedback - SYM.pdf",
    "../N-ERGY Internship_ Take Home Interview.pdf",
    "../Product Feedback - SYM.docx",
    "../demo.txt",
    "../sample_image.jpeg",   # You can add images too!
    "../presentation.pptx"   # And PowerPoint
]

for source in files_to_test:
    if not os.path.exists(source):
        print(f"File not found: {source}")
        continue

    print(f"--- Processing: {source} ---")
    output_filename = f"{os.path.basename(source).replace('.', '_')}.md"

    try:
        # Check if the file is a plain .txt file
        if source.lower().endswith(".txt"):
            with open(source, "r", encoding="utf-8") as f:
                md_content = f.read()
            print("Handled as plain text.")
        else:
            # Use Docling for structured formats (PDF, DOCX, etc.)
            result = converter.convert(source)
            md_content = result.document.export_to_markdown()
            print("Handled by Docling.")

        # Save to markdown file
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Saved to: {output_filename}\n")

    except Exception as e:
        print(f"Error converting {source}: {e}\n")

print("All tests completed.")