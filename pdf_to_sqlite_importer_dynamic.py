import fitz  # PyMuPDF
import re
import os
import shutil
import sqlite3
import pandas as pd
from datetime import datetime

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

def parse_pdf_to_dataframe(pdf_path):
    if not os.path.isfile(pdf_path):
        log(f"PDF nicht gefunden: {pdf_path}")
        return pd.DataFrame()

    lieferanten_set = lade_liste(LIEFERANTEN_CSV)
    whitelist_set = lade_liste(WHITELIST_CSV)

    doc = fitz.open(pdf_path)
    records = []
    seiten_gesamt = len(doc)

    for page_num in range(seiten_gesamt):
        page = doc.load_page(page_num)
        text = page.get_text()
        matches = re.findall(r"Medikament:\s*(.*?)\s*Gesamt:", text, re.DOTALL)

        for match in matches:
            match_lines = match.strip().splitlines()
            if len(match_lines) < 1:
                continue

            artikelzeile = match_lines[0].strip()
            artikelnummer = ""
            artikeltext = ""
            artikel_match = re.match(r"(\d+)\s+(.*)", artikelzeile)
            if artikel_match:
                artikelnummer = artikel_match.group(1)
                artikeltext = artikel_match.group(2)

            lines = match_lines[1:]
            i = 0
            while i + 1 < len(lines):
                if ist_block_start(lines[i], lines[i+1]):
                    block = lines[i:i+11]
                    is_dirty = False

                    if len(block) < 11:
                        block += [""] * (11 - len(block))
                        is_dirty = True

                    block = [line.strip() for line in block]
                    lfdnr, datum, kunde_id, kundenname = block[:4]
                    arzt_id, arzt_name, lieferant = block[4:7]
                    rest = block[7:]

                    name_upper = kundenname.upper()
                    lieferant_upper = lieferant.upper()

                    if any(w in name_upper for w in whitelist_set):
                        name = kundenname.strip()
                        final_lieferant = lieferant
                    elif name_upper in lieferanten_set or lieferant_upper in lieferanten_set:
                        name = ""
                        final_lieferant = kundenname or lieferant
                    else:
                        name = kundenname.strip()
                        final_lieferant = lieferant or None

                    zahlen_idx = [j for j in range(len(rest)) if ist_zahl(rest[j])]
                    lager = rest[zahlen_idx[-1]] if len(zahlen_idx) >= 1 else ""
                    bewegung = rest[zahlen_idx[-2]] if len(zahlen_idx) >= 2 else ""

                    ein = aus = ""
                    if len(zahlen_idx) >= 2:
                        abstand = zahlen_idx[-1] - zahlen_idx[-2] - 1
                        if abstand == 0:
                            aus = bewegung
                        elif abstand == 1:
                            ein = bewegung
                        else:
                            is_dirty = True
                    else:
                        is_dirty = True

                    if not lfdnr.strip() or not datum.strip() or not re.match(r"\d{2}\.\d{2}\.\d{4}", datum):
                        is_dirty = True

                    records.append({
                        "dirty": is_dirty,
                        "lfdnr": lfdnr,
                        "datum": datum,
                        "kunde_id": kunde_id,
                        "vorname": "",
                        "nachname": name,
                        "arzt_id": arzt_id,
                        "arzt_name": arzt_name,
                        "lieferant": final_lieferant,
                        "ein": ein,
                        "aus": aus,
                        "lager": lager,
                        "abh": "",
                        "artikelnummer": artikelnummer,
                        "artikeltext": artikeltext
                    })
                    i += 11
                else:
                    i += 1

    df = pd.DataFrame(records).fillna('').astype({'dirty': 'bool'})
    log(f"Seiten gelesen: {seiten_gesamt}, Bewegungen erkannt: {len(records)}")
    log(f"Davon dirty: {df['dirty'].sum()}, clean: {len(df) - df['dirty'].sum()}")
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
            created_at, updated_at, dirty, ks
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """

        ein_raw = str(row["ein"]).strip()
        aus_raw = str(row["aus"]).strip()
        ein_mge = int(ein_raw) if ist_zahl(ein_raw) else None
        aus_mge = int(aus_raw) if ist_zahl(aus_raw) else None

        daten = (
            row.get("artikelnummer"), row.get("artikeltext"), "b", row.get("datum"),
            ein_mge, None, None,
            aus_mge, None, None,
            row.get("nachname"), row.get("vorname"),
            row.get("lieferant"), "pdf",
            datetime.now().isoformat(), datetime.now().isoformat(), row.get("dirty"), None
        )

        cursor.execute(insert_sql, daten)

    conn.commit()
    conn.close()
    log(f"{len(df)} Bewegungen in die Datenbank importiert.")

def run_import(pdf_path, db_path="data/laufende_liste.db"):
    df = parse_pdf_to_dataframe(pdf_path)
    if not df.empty and "artikeltext" in df.columns:
        df = df[df["artikeltext"].notnull() & (df["artikeltext"].str.strip() != "")]
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
