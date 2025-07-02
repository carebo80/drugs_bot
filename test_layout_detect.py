import fitz
import re

def detect_layout_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    for page in doc:
        words = page.get_text().split()
        if "Lfdnr" in words and "Ein." in words:
            if "BG" in words and "Rez.Nr." in words:
                return "a"
            return "b"
    return None

if __name__ == "__main__":
    # Pfad zum PDF (lokal)
    pdf_path = "upload/CPrintQPrinterObject-30824-0.pdf"  # <-- Pfad anpassen!
    layout = detect_layout_from_pdf(pdf_path)
    print(f"\n➡️ Erkanntes Layout: {layout}")
