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
def extract_table_rows(pdf_path):
    import fitz
    import re

    doc = fitz.open(pdf_path)
    rows = []

    for page in doc:
        lines = page.get_text().splitlines()
        cleaned = [line.strip() for line in lines if line.strip() != ""]

        buffer = []
        for item in cleaned:
            # Blockstart: 5-stellige Nummer + gültiges Datum folgt
            if len(buffer) == 0 and re.fullmatch(r"\d{5}", item):
                buffer.append(item)
            elif len(buffer) == 1 and re.match(r"\d{2}\.\d{2}\.\d{4}", item):
                buffer.append(item)
            elif len(buffer) >= 2:
                buffer.append(item)

            # Sobald wir 11 oder 12 Elemente haben (Layout B oder A), block beenden
            if len(buffer) == 12:
                rows.append(buffer.copy())
                buffer.clear()
            elif len(buffer) == 11:
                rows.append(buffer.copy())
                buffer.clear()
            elif len(buffer) > 12:
                buffer.clear()  # Ungültiger Block

    return rows
