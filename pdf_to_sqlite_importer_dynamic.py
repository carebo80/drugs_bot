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
            lines = match.strip().splitlines()
            if len(lines) < 14:
                continue

            artikelzeile = lines[0].strip()
            artikel_split = artikelzeile.split(" ", 1)
            artikelnummer = artikel_split[0] if len(artikel_split) > 1 else ""
            artikeltext = artikel_split[1] if len(artikel_split) > 1 else ""

            datenzeilen = lines[12:]
            i = 0
            while i < len(datenzeilen):
                if i + 1 < len(datenzeilen) and ist_block_start(datenzeilen[i], datenzeilen[i+1]):
                    block = datenzeilen[i:i+11]
                    is_dirty = False

                    if len(block) < 11:
                        block += [""] * (11 - len(block))
                        is_dirty = True

                    block = [line.strip() for line in block]
                    lfdnr, datum, kunde_id, kundenname = block[:4]
                    arzt_id, arzt_name, lieferant = block[4:7]
                    ein, aus, lager, abh = block[7], block[8], block[9], block[10]

                    if not lfdnr.strip() or not datum.strip():
                        is_dirty = True

                    if not re.match(r"\d{2}\.\d{2}\.\d{4}", datum):
                        is_dirty = True

                    for feld in [ein, aus]:
                        if feld and not ist_zahl(feld):
                            is_dirty = True

                    if not ein.strip() and not aus.strip():
                        is_dirty = True
                        log(f"⚠️ Warnung: Ein UND Aus leer bei Lfdnr {lfdnr} auf Seite {page_num + 1}")

                    if ist_zahl(ein) and ist_zahl(aus):
                        try:
                            if int(ein) > 0 and int(aus) > 0:
                                is_dirty = True
                                log(f"⚠️ Warnung: Ein UND Aus positiv bei Lfdnr {lfdnr} auf Seite {page_num + 1}")
                        except:
                            pass

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

                    # Retoure-Regel mit Korrektur: Nur aus setzen, ein löschen
                    if name and ist_zahl(ein) and not ist_zahl(aus):
                        aus = str(-int(ein))
                        ein = ""

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
                        "abh": abh,
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
