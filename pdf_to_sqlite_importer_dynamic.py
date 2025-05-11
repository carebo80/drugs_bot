import fitz  # PyMuPDF
import re
import os
import sqlite3
import pandas as pd
from datetime import datetime

LOG_PATH = "tmp/import.log"
LIEFERANTEN_CSV = "data/lieferanten.csv"

def log(message):
    timestamp = datetime.now().isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")
    print(message)

def lade_lieferanten():
    try:
        df = pd.read_csv(LIEFERANTEN_CSV)
        return set(df["name"].dropna().str.upper())
    except Exception as e:
        log(f"⚠️ Fehler beim Laden der Lieferantenliste: {e}")
        return set()

def extract_pack_size(text):
    match = re.search(r"(\d+)\s*STK", str(text).upper())
    return int(match.group(1)) if match else 1

def parse_pdf_to_dataframe(pdf_path):
    if not os.path.isfile(pdf_path):
        log(f"PDF nicht gefunden: {pdf_path}")
        return pd.DataFrame()

    doc = fitz.open(pdf_path)
    records = []
    fehler_zeilen = []
    lieferanten_set = lade_lieferanten()
    seiten_gesamt = len(doc)

    for page_num in range(seiten_gesamt):
        page = doc.load_page(page_num)
        text = page.get_text()
        matches = re.findall(r"Medikament:\s*(.*?)\s*Gesamt:", text, re.DOTALL)

        for match in matches:
            lines = match.strip().splitlines()
            if len(lines) < 14:
                continue  # zu kurz = keine gültige Medikamentengruppe

            artikelzeile = lines[0].strip()
            artikel_split = artikelzeile.split(" ", 1)
            artikelnummer = artikel_split[0] if len(artikel_split) > 1 else ""
            artikeltext = artikel_split[1] if len(artikel_split) > 1 else ""

            datenzeilen = lines[12:]  # Bewegungen ab Zeile 13
            for zeile in datenzeilen:
                felder = zeile.strip().split()
                dirty = False

                if len(felder) < 11:
                    felder += [""] * (11 - len(felder))
                    dirty = True

                try:
                    lfdnr, datum, kunde_id, kundenname, arzt_id, arzt_name, lieferant, ein, aus, lager, abh = felder[:11]

                    parts = kundenname.split()
                    vorname = parts[0] if parts else ''
                    nachname = ' '.join(parts[1:]) if len(parts) > 1 else ''

                    name_upper = kundenname.upper()
                    if name_upper in lieferanten_set or lieferant.upper() in lieferanten_set:
                        final_lieferant = kundenname or lieferant
                        vorname, nachname = None, None
                    else:
                        final_lieferant = lieferant or None

                    records.append({
                        "dirty": dirty,
                        "lfdnr": lfdnr,
                        "datum": datum,
                        "kunde_id": kunde_id,
                        "vorname": vorname,
                        "nachname": nachname,
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

                except Exception as e:
                    fehler_zeilen.append({
                        "seite": page_num + 1,
                        "artikel": artikelnummer,
                        "zeile": zeile,
                        "fehler": str(e)
                    })

    log(f"Seiten gelesen: {seiten_gesamt}, Bewegungen erkannt: {len(records)}")
    if fehler_zeilen:
        log(f"⚠️ {len(fehler_zeilen)} unvollständige oder fehlerhafte Zeilen erkannt. Beispiel:")
        for fehler in fehler_zeilen[:3]:
            log(f"Seite {fehler['seite']} – {fehler['artikel']}: {fehler['zeile']} ({fehler['fehler']})")

    return pd.DataFrame(records).fillna('').astype({'dirty': 'bool'})


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
            created_at, updated_at, dirty
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """

        ein_raw = str(row["ein"]).strip()
        aus_raw = str(row["aus"]).strip()
        ein_mge = int(ein_raw) if ein_raw.isdigit() else None
        aus_mge = int(aus_raw) if aus_raw.isdigit() else None

        pack_size = extract_pack_size(row.get("artikeltext", ""))
        ein_pack = pack_size if ein_mge is not None else None
        aus_pack = pack_size if aus_mge is not None else None
        eingang = ein_mge * pack_size if ein_mge is not None else None
        ausgang = aus_mge * pack_size if aus_mge is not None else None

        daten = (
            row.get("artikelnummer"), row.get("artikeltext"), "b", row.get("datum"),
            ein_mge, ein_pack, eingang,
            aus_mge, aus_pack, ausgang,
            row.get("nachname"), row.get("vorname"),
            row.get("lieferant"), "pdf",
            datetime.now().isoformat(), datetime.now().isoformat(), row.get("dirty")
        )

        try:
            cursor.execute(insert_sql, daten)
        except sqlite3.IntegrityError:
            log(f"⚠️ Übersprungen (Duplikat?): {row.get('artikelnummer')} am {row.get('datum')}")

    conn.commit()
    conn.close()
    log(f"{len(df)} Bewegungen in die Datenbank importiert.")


def run_import(pdf_path, db_path="data/laufende_liste.db"):
    df = parse_pdf_to_dataframe(pdf_path)
    if not df.empty and "artikeltext" in df.columns:
        df = df[df["artikeltext"].notnull() & (df["artikeltext"].str.strip() != "")]
        import_dataframe_to_sqlite(df, db_path)
    else:
        log("Keine gültigen Bewegungen gefunden – kein Import durchgeführt.")
