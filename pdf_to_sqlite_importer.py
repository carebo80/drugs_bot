import fitz  # PyMuPDF
import re
import os
import sqlite3
import pandas as pd
from datetime import datetime

PDF_PATH = "data/CPrintQPrinterObject-4520-0.pdf"
DB_PATH = "data/laufende_liste.db"
LOG_PATH = "tmp/import.log"

def log(message):
    timestamp = datetime.now().isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")
    print(message)

def parse_pdf_to_dataframe(pdf_path):
    if not os.path.isfile(pdf_path):
        log(f"PDF nicht gefunden: {pdf_path}")
        return pd.DataFrame()

    doc = fitz.open(pdf_path)
    records = []
    seiten_gesamt = len(doc)

    for page_num in range(seiten_gesamt):
        page = doc.load_page(page_num)
        text = page.get_text()
        matches = re.findall(r"Medikament:\s*(.*?)\s*Gesamt:", text, re.DOTALL)

        for match in matches:
            lines = match.splitlines()
            if len(lines) < 14:
                continue

            artikelzeile = lines[0].strip()
            artikel_split = artikelzeile.split(" ", 1)
            artikelnummer = artikel_split[0] if len(artikel_split) > 1 else ""
            artikeltext = artikel_split[1] if len(artikel_split) > 1 else ""

            datenzeilen = lines[12:]
            for i in range(0, len(datenzeilen), 11):
                block = datenzeilen[i:i+11]
                if len(block) < 11:
                    continue

                block = [line.strip() for line in block]
                lfdnr, datum, kunde_id, kundenname = block[:4]
                arzt_id, arzt_name, lieferant = block[4:7]
                ein, aus, lager, abh = block[7:]

                parts = kundenname.split()
                vorname = parts[0] if parts else ''
                nachname = ' '.join(parts[1:]) if len(parts) > 1 else ''

                records.append({
                    "lfdnr": lfdnr,
                    "datum": datum,
                    "kunde_id": kunde_id,
                    "vorname": vorname,
                    "nachname": nachname,
                    "arzt_id": arzt_id,
                    "arzt_name": arzt_name,
                    "lieferant": lieferant,
                    "ein": ein,
                    "aus": aus,
                    "lager": lager,
                    "abh": abh,
                    "artikelnummer": artikelnummer,
                    "artikeltext": artikeltext
                })

    log(f"Seiten gelesen: {seiten_gesamt}, Bewegungen erkannt: {len(records)}")
    return pd.DataFrame(records)

def extract_pack_size(text):
    match = re.search(r"(\d+)\s*STK", str(text).upper())
    return int(match.group(1)) if match else 1

def import_dataframe_to_sqlite(df, db_path):
    daten = []
    for _, row in df.iterrows():
        ein_raw = str(row["ein"]).strip()
        aus_raw = str(row["aus"]).strip()

        ein_mge = int(ein_raw) if ein_raw.isdigit() else None
        aus_mge = int(aus_raw) if aus_raw.isdigit() else None

        pack_size = extract_pack_size(row.get("artikeltext", ""))
        ein_pack = pack_size if ein_mge is not None else None
        aus_pack = pack_size if aus_mge is not None else None
        eingang = ein_mge * pack_size if ein_mge is not None else None
        ausgang = aus_mge * pack_size if aus_mge is not None else None

        daten.append({
            "belegnummer": row.get("artikelnummer"),
            "artikel_bezeichnung": row.get("artikeltext"),
            "liste": "b",
            "datum": row.get("datum"),
            "ein_mge": ein_mge,
            "ein_pack": ein_pack,
            "eingang": eingang,
            "aus_mge": aus_mge,
            "aus_pack": aus_pack,
            "ausgang": ausgang,
            "name": row.get("nachname"),
            "vorname": row.get("vorname"),
            "lieferant": row.get("lieferant"),
            "quelle": "pdf",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    insert_sql = """
    INSERT INTO bewegungen (
        belegnummer, artikel_bezeichnung, liste, datum,
        ein_mge, ein_pack, eingang,
        aus_mge, aus_pack, ausgang,
        name, vorname,
        lieferant, quelle,
        created_at, updated_at
    ) VALUES (
        :belegnummer, :artikel_bezeichnung, :liste, :datum,
        :ein_mge, :ein_pack, :eingang,
        :aus_mge, :aus_pack, :ausgang,
        :name, :vorname,
        :lieferant, :quelle,
        :created_at, :updated_at
    );
    """

    try:
        cursor.executemany(insert_sql, daten)
        conn.commit()
        log(f"{len(daten)} Bewegungen in die Datenbank importiert.")
    except sqlite3.IntegrityError as e:
        log(f"Fehler beim Import: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    df = parse_pdf_to_dataframe(PDF_PATH)
    if not df.empty and "artikeltext" in df.columns:
        df = df[df["artikeltext"].notnull() & (df["artikeltext"].str.strip() != "")]
        import_dataframe_to_sqlite(df, DB_PATH)
    else:
        log("Keine gültigen Bewegungen gefunden – kein Import durchgeführt.")
