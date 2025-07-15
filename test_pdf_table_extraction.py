import fitz  # PyMuPDF
import sys

def test_pdf_table_extraction(pdf_path):
    doc = fitz.open(pdf_path)

    for page_num, page in enumerate(doc):
        print(f"📄 Seite {page_num + 1}:")
        blocks = page.get_text("blocks")  # liefert (x0, y0, x1, y1, "text", block_no, block_type, block_flags)

        for b in sorted(blocks, key=lambda b: (b[1], b[0])):  # sortiere nach y (oben nach unten), dann x (links nach rechts)
            text = b[4].strip()
            if text:
                print(f"🧩 {text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❗ Bitte gib einen PDF-Pfad an, z. B.:")
        print("   python3 test_pdf_table_extraction.py <pfad/zur/datei.pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    test_pdf_table_extraction(pdf_path)
