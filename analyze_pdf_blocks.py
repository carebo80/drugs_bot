import fitz  # PyMuPDF
import re

def ist_block_start(zeile1, zeile2):
    return re.fullmatch(r"\d{5}", zeile1.strip()) and re.match(r"\d{2}\.\d{2}\.\d{4}", zeile2.strip())

def analyze_pdf_blocks(pdf_path):
    doc = fitz.open(pdf_path)
    block_num = 0

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        matches = re.findall(r"Medikament:\s*(.*?)\s*Gesamt:", text, re.DOTALL)

        for match in matches:
            lines = match.strip().splitlines()[1:]  # Erste Zeile ist Artikelbezeichnung
            i = 0
            while i + 1 < len(lines):
                if ist_block_start(lines[i], lines[i+1]):
                    block = lines[i:i+11]
                    if len(block) < 11:
                        block += [""] * (11 - len(block))
                    rest = block[7:]
                    print(f"\n🧩 Block {block_num + 1}: {len(rest)} Restelemente → {rest}")
                    block_num += 1
                    i += 11
                else:
                    i += 1

if __name__ == "__main__":
    # Pfad zum PDF hier anpassen
    analyze_pdf_blocks("upload/CPrintQPrinterObject-30824-0.pdf")
