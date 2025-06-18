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
lieferanten_set = lade_liste(LIEFERANTEN_CSV)

def ist_zahl(text):
    return bool(re.fullmatch(r"-?\d+([.,]\d+)?", text.strip()))

def ist_block_start(zeile1, zeile2):
    return re.fullmatch(r"\d{5}", zeile1.strip()) and re.match(r"\d{2}\.\d{2}\.\d{4}", zeile2.strip())
def erkenne_bewegung(rest):
    if len(rest) != 4:
        return None, None, None, None

    val1, val2, val3, val4 = [s.strip() for s in rest]

    bg_rez_nr = val4 if val4 else None
    lager = int(val3) if val3.lstrip("-").isdigit() else None

    ein = aus = None

    if val1 == "" and val2.lstrip("-").isdigit():
        aus = int(val2)
    elif val2 == "" and val1.lstrip("-").isdigit():
        ein = int(val1)
    elif val1.lstrip("-").isdigit() and val2 == "":
        ein = int(val1)
    elif val2.lstrip("-").isdigit() and val1 == "":
        aus = int(val2)
    elif val1.lstrip("-").isdigit() and val2.lstrip("-").isdigit():
        # Beide befüllt → nicht eindeutig → ignorieren
        return None, None, lager, bg_rez_nr

    return ein, aus, lager, bg_rez_nr

def is_valid_lfdnr(s):
    return s.isdigit() and len(s) >= 5

def is_valid_datum(s):
    return re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", s.strip()) is not None

def is_valid_lfdnr(s):
    return s.isdigit() and len(s) >= 5

def is_valid_datum(s):
    return re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", s.strip()) is not None

def parse_pdf_to_dataframe(pdf_path: str) -> pd.DataFrame:
    doc = fitz.open(pdf_path)
    all_data = []
    artikelnummer = None
    artikeltext = None

    lieferanten_set = lade_liste(LIEFERANTEN_CSV)
    whitelist_set = lade_liste(WHITELIST_CSV)

    for page in doc:
        blocks = page.get_text("blocks")
        blocks.sort(key=lambda b: (b[1], b[0]))  # sort by y, then x

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

        for line in lines:
            flat = " ".join(line).replace("\n", " ").strip().split()
            if not flat:
                continue

            # Medikamentenzeile erkennen
            if flat[0].upper() == "MEDIKAMENT:" and len(flat) >= 3:
                artikelnummer = flat[1]
                artikeltext = " ".join(flat[2:])
                continue

            # Überschrift ignorieren
            if flat[0].lower() == "lfdnr":
                continue

            # Bewegungszeile
            if len(flat) >= 8 and is_valid_lfdnr(flat[0]) and is_valid_datum(flat[1]):
                core = flat[:-4]
                rest = flat[-4:]

                # Aufteilen
                lfdnr = core[0]
                datum = core[1]
                kunde_name = core[2] if len(core) > 2 else ""
                arzt_name = core[3] if len(core) > 3 else ""
                lieferant = core[4] if len(core) > 4 else ""

                # Verschobene Felder erkennen (Lieferant steht im Kundenfeld)
                if kunde_name.upper() in lieferanten_set:
                    lieferant = kunde_name
                    kunde_name = ""
                    arzt_name = ""
                    print(f"[⚠️ SHIFT] Verschoben erkannt: {lieferant}")

                ein, aus, lager, bg_rez_nr = erkenne_bewegung(rest)

                # Nur ein oder aus erlaubt
                if ein is not None and aus is not None:
                    print(f"[⛔ FEHLER] doppelt belegt: ein={ein}, aus={aus} → verworfen")
                    continue

                # Wenn Lieferant aus CSV → immer ein
                if lieferant.upper() in lieferanten_set:
                    if ein is None and aus is not None:
                        ein = aus
                        aus = None
                    elif ein is None and aus is None:
                        ein = 0
                    aus = None
                    print(f"[✔ EIN] Lieferant erkannt: {lieferant} → ein={ein}")

                data = {
                    "lfdnr": lfdnr,
                    "datum": datum,
                    "kunde_name": kunde_name,
                    "arzt_name": arzt_name,
                    "lieferant": lieferant,
                    "ein": ein,
                    "aus": aus,
                    "lager": lager,
                    "bg_rez_nr": bg_rez_nr,
                    "liste": "a",  # fix auf Layout A
                    "artikelnummer": artikelnummer,
                    "artikeltext": artikeltext
                }

                print(f"[✔ PARSED] {data}")
                all_data.append(data)

    return pd.DataFrame(all_data)


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

