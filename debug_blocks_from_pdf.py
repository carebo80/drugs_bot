import fitz
from pathlib import Path
from pprint import pprint
from pdf_to_sqlite_importer_dynamic import group_blocks_by_line, extract_article_info  # ggf. Pfad anpassen

PDF_PATH = "upload/CPrintQPrinterObject-31785-0.pdf"  # oder den Pfad deiner Wahl

def is_valid_zeile(zeile):
    return (
        len(zeile) >= 5
        and zeile[0].isdigit()
        and "." in zeile[1]
    )

def debug_extraction(pdf_path):
    doc = fitz.open(pdf_path)
    for page in doc:
        print(f"\n=== Seite {page.number + 1} ===")
        blocks = page.get_text("blocks")
        lines = group_blocks_by_line(blocks)
        meta = extract_article_info(page)
        print(f"🧾 Artikelinfo: {meta}")

        for zeile in lines:
            if not is_valid_zeile(zeile):
                continue

            print(f"\n🔹 Zeile:")
            pprint(zeile)

            tokens = zeile[2:]  # nach Lfdnr + Datum
            numerics = [t for t in tokens if t.strip().lstrip('-').isdigit()]
            print(f"🔍 Zahlen (numerics): {numerics}")

            # Logik zur Testbewegung
            if len(numerics) == 2:
                print(f"➡️ Bewegung 1: {numerics[0]}, Bewegung 2: {numerics[1]}")
            elif len(numerics) == 1:
                print(f"➡️ Eine Bewegung: {numerics[0]}")
            elif len(numerics) == 3:
                print(f"➡️ Bewegung + Lager (3x numerisch): {numerics}")
            else:
                print("⚠️ Keine/unklare Bewegung")

debug_extraction(PDF_PATH)
