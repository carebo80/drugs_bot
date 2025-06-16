import fitz  # PyMuPDF
import re
import os
import shutil
import sqlite3
import pandas as pd
from datetime import datetime
import streamlit as st

LOG_PATH = "tmp/import.log"
LIEFERANTEN_CSV = "data/lieferanten.csv"
WHITELIST_CSV = "data/whitelist.csv"

def log(message):
    timestamp = datetime.now().isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")
    print(message)

def lade_liste(pfad):
    try:
        df = pd.read_csv(pfad)
        return set(df["name"].dropna().str.upper())
    except Exception as e:
        log(f"⚠️ Fehler beim Laden von {pfad}: {e}")
        return set()

def ist_zahl(text):
    return bool(re.fullmatch(r"-?\d+([.,]\d+)?", text.strip()))

def ist_block_start(zeile1, zeile2):
    return re.fullmatch(r"\d{5}", zeile1.strip()) and re.match(r"\d{2}\.\d{2}\.\d{4}", zeile2.strip())

def parse_pdf_to_dataframe(pdf_path: str) -> pd.DataFrame:

    doc = fitz.open(pdf_path)
    all_data = []

    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (b[1], b[0]))  # Sortieren: y (vertikal), dann x (horizontal)

        lines = []
        current_line_y = None
        current_line = []

        for block in blocks:
            x0, y0, x1, y1, text, *_ = block
            if current_line_y is None or abs(y0 - current_line_y) > 5:
                if current_line:
                    lines.append(current_line)
                current_line = [text.strip()]
                current_line_y = y0
            else:
                current_line.append(text.strip())

        if current_line:
            lines.append(current_line)

        # Datenblöcke filtern (mindestens 10 Spalten = potenzielles Datenfeld)
        for line in lines:
            if len(line) >= 10:
                rest = line[-4:]
                core = line[:-4]

                # BG-Layout wird anhand der Restelemente (immer 4) bestätigt
                bg_rez_nr = rest[-1].strip() if rest[-1].strip() else None
                lager = rest[-2].strip() if rest[-2].strip() else None
                bewegung = rest[-3].strip() if rest[-3].strip() else None
                steuerfeld = rest[-4].strip()

                # Bewegung je nach Position:
                ein = bewegung if steuerfeld == "" else None
                aus = bewegung if steuerfeld != "" else None

                data = {
                    "lfdnr": core[0] if len(core) > 0 else None,
                    "datum": core[1] if len(core) > 1 else None,
                    "kunde_name": core[2] if len(core) > 2 else None,
                    "arzt_name": core[3] if len(core) > 3 else None,
                    "lieferant": core[4] if len(core) > 4 else None,
                    "ein": ein,
                    "aus": aus,
                    "lager": lager,
                    "bg_rez_nr": bg_rez_nr,
                    "liste": "a",  # Da das ganze PDF A ist
                }

                all_data.append(data)

    df = pd.DataFrame(all_data)
    return df

def import_dataframe_to_sqlite(df, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for _, row in df.iterrows():
        insert_sql = """
        INSERT INTO bewegungen (
            belegnummer, artikel_bezeichnung, liste, datum,
            ein_mge, ein_pack, eingang,
            aus_mge, aus_pack, ausgang,
            name, vorname,
            lieferant, quelle,
            created_at, updated_at, dirty, ks, bg_rez_nr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """

        ein_raw = str(row["ein"]).strip()
        aus_raw = str(row["aus"]).strip()
        ein_mge = int(ein_raw) if ist_zahl(ein_raw) else None
        aus_mge = int(aus_raw) if ist_zahl(aus_raw) else None

        daten = (
            row.get("artikelnummer"), row.get("artikeltext"), "a" if row.get("bg_rez_nr") else "b", row.get("datum"),
            ein_mge, None, None,
            aus_mge, None, None,
            row.get("nachname"), row.get("vorname"),
            row.get("lieferant"), "pdf",
            datetime.now().isoformat(), datetime.now().isoformat(), row.get("dirty"), None, row.get("bg_rez_nr")
        )

        cursor.execute(insert_sql, daten)

    conn.commit()
    conn.close()
    log(f"{len(df)} Bewegungen in die Datenbank importiert.")

def run_import(pdf_path, db_path="data/laufende_liste.db"):
    df = parse_pdf_to_dataframe(pdf_path)
    st.write("✅ Bewegungen gefunden:", len(df))
    st.dataframe(df)

    if not df.empty:
        import_dataframe_to_sqlite(df, db_path)
        try:
            timestamp = datetime.now().strftime("_%Y%m%d-%H%M%S")
            backup_path = pdf_path + timestamp + ".bak"
            shutil.copy2(pdf_path, backup_path)
            os.remove(pdf_path)
            log(f"✅ PDF-Datei gesichert als {backup_path} und gelöscht: {pdf_path}")
        except Exception as e:
            log(f"⚠️ Fehler beim Löschen/Sichern der Datei {pdf_path}: {e}")
    else:
        log("Keine gültigen Bewegungen gefunden – kein Import durchgeführt.")

