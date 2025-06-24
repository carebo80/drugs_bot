import pandas as pd
import sqlite3
import os
import re
from pathlib import Path
import fitz  # PyMuPDF

LIEFERANTEN_PATH = "data/lieferanten.csv"
DB_PATH = "data/laufende_liste.db"


def safe_int(value):
    try:
        return int(str(value).strip())
    except:
        return 0


def extract_article_info(text):
    match = re.search(r"(\d{4,})\s+(.*?)(\d+)\s*STK", text)
    if match:
        belegnummer = match.group(1)
        artikel_bezeichnung = match.group(2).strip()
        packungsgroesse = safe_int(match.group(3))
        return belegnummer, artikel_bezeichnung, packungsgroesse
    return None, None, 0


def parse_row(row, lieferanten_set, artikel_info):
    layout = 'a' if len(row) == 12 else 'b' if len(row) == 11 else None
    if layout is None:
        return None

    try:
        lfdnr = row[0] if row[0].isdigit() and len(row[0]) >= 5 else None
        datum = row[1]
        if layout == 'a':
            bewegung_1 = row[7]
            bewegung_2 = row[8]
            bg_rez_nr = row[9].strip() if row[9].strip() else None
            lieferant_kandidat = row[6].strip()
            name_raw = row[3:6]
        else:
            bewegung_1 = row[6]
            bewegung_2 = row[7]
            bg_rez_nr = None
            lieferant_kandidat = row[5].strip()
            name_raw = row[3:5]

        name = " ".join(name_raw).strip()
        lieferant = ""
        for l in lieferanten_set:
            if l.lower() in lieferant_kandidat.lower():
                lieferant = l
                name = ""
                break

        b1 = safe_int(bewegung_1)
        b2 = safe_int(bewegung_2)
        ein_mge = aus_mge = 0
        if lieferant:
            ein_mge = b1
        else:
            if b1 > 0 and b2 == 0:
                ein_mge = b1
            elif b2 > 0 and b1 == 0:
                aus_mge = b2
            else:
                return None

        # Artikelinfo zuweisen
        belegnummer, artikel_bezeichnung, packungsgroesse = artikel_info

        return {
            "datum": datum,
            "name": name,
            "lieferant": lieferant,
            "ein_mge": ein_mge,
            "aus_mge": aus_mge,
            "bg_rez_nr": bg_rez_nr,
            "layout": layout,
            "belegnummer": belegnummer,
            "artikel_bezeichnung": artikel_bezeichnung,
            "packungsgroesse": packungsgroesse
        }

    except Exception:
        return None


def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    for page in doc:
        text = page.get_text()
        article_info = extract_article_info(text)
        matches = re.findall(r"Medikament:\s*(.*?)\s*Gesamt:", text, re.DOTALL)
        for match in matches:
            lines = match.strip().splitlines()
            for line in lines[1:]:  # erste Zeile = Kopfzeile mit Artikelinfo
                tokens = line.strip().split()
                if len(tokens) >= 5 and re.fullmatch(r"\d{5}", tokens[0]) and re.match(r"\d{2}\.\d{2}\.\d{4}", tokens[1]):
                    all_rows.append((tokens, article_info))

    return all_rows


def parse_pdf_to_dataframe_dynamic_layout(pdf_path):
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")

    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
    lieferanten_set = set(lieferanten_df.iloc[:, 0].astype(str).str.strip())

    rows = extract_table_rows_with_article(pdf_path)
    parsed_rows = []
    for row, artikel_info in rows:
        parsed = parse_row(row, lieferanten_set, artikel_info)
        if parsed:
            parsed_rows.append(parsed)

    return pd.DataFrame(parsed_rows)


def run_import(df):
    if not isinstance(df, pd.DataFrame):
        print("❌ Kein gültiger DataFrame")
        return

    if df.empty:
        print("⚠️ Keine gültigen Zeilen zum Import.")
        return

    with sqlite3.connect(DB_PATH) as conn:
        df.to_sql("bewegungen", conn, if_exists="append", index=False)
    print(f"✅ {len(df)} Zeilen erfolgreich importiert.")
