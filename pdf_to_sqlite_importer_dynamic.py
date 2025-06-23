import pandas as pd
import sqlite3
import os
from pathlib import Path

LIEFERANTEN_PATH = "data/lieferanten.csv"
DB_PATH = "data/laufende_liste.db"

def is_layout_a(row):
    return len(row) == 12

def is_layout_b(row):
    return len(row) == 11
def safe_int(value):
    try:
        return int(str(value).strip())
    except:
        return 0

def parse_row(row, lieferanten_set):
    layout = 'a' if len(row) == 12 else 'b' if len(row) == 11 else None
    if layout is None:
        print(f"⛔ Ungültiges Layout (Spalten: {len(row)}): {row}")
        return None

    try:
        lfdnr = row[0] if row[0].isdigit() and len(row[0]) >= 5 else None
        datum = row[1]
    except IndexError:
        print(f"⛔ Fehlerhafte Grunddaten: {row}")
        return None

    try:
        if layout == 'a':
            bewegung_1 = row[-4]
            bewegung_2 = row[-3]
            bg_rez_nr = row[-2].strip() if row[-2].strip() else None
            name_raw = row[3:-4]
        else:
            bewegung_1 = row[-3]
            bewegung_2 = row[-2]
            bg_rez_nr = None
            name_raw = row[3:-3]

        name_str = " ".join(name_raw).strip()

        # Lieferantenerkennung (robust, case-insensitive, Teilstring)
        lieferant = ""
        name = name_str
        for l in lieferanten_set:
            if l.lower() in name_str.lower():
                lieferant = l
                name = ""
                break

        ein_mge = aus_mge = 0
        b1 = safe_int(bewegung_1)
        b2 = safe_int(bewegung_2)

        if lieferant:
            ein_mge = b1
        else:
            if b1 > 0 and b2 == 0:
                ein_mge = b1
            elif b2 > 0 and b1 == 0:
                aus_mge = b2
            else:
                print(f"⚠️ Ungültige Bewegungsdaten: {row}")
                return None

        return {
            "lfdnr": lfdnr,
            "datum": datum,
            "name": name,
            "lieferant": lieferant,
            "ein_mge": ein_mge,
            "aus_mge": aus_mge,
            "bg_rez_nr": bg_rez_nr,
            "layout": layout
        }

    except Exception as e:
        print(f"⛔ Ausnahme beim Parsen: {e} → {row}")
        return None

def parse_pdf_to_dataframe_dynamic_layout(pdf_rows):
    # Lieferantenliste laden
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")

    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
    lieferanten_set = set(lieferanten_df.iloc[:, 0].astype(str).str.strip())

    result_rows = []
    for row in pdf_rows:
        clean_row = [cell.strip() for cell in row if cell.strip() != "" or cell == ""]
        parsed = parse_row(clean_row, lieferanten_set)
        if parsed:
            result_rows.append(parsed)

    df = pd.DataFrame(result_rows)
    return df

def run_import(parsed_df):
    if not isinstance(parsed_df, pd.DataFrame):
        print("❌ Fehler: Übergabe ist kein DataFrame (sondern Typ:", type(parsed_df), ")")
        return

    if parsed_df.empty:
        print("⚠️ Keine gültigen Zeilen zum Import.")
        return

    with sqlite3.connect(DB_PATH) as conn:
        parsed_df.to_sql("bewegungen", conn, if_exists="append", index=False)
    print(f"✅ {len(parsed_df)} Zeilen erfolgreich importiert.")


