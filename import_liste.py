import sys
import pandas as pd
import sqlite3
import re
from pathlib import Path
from datetime import datetime

def extrahiere_packung(text):
    match = re.search(r"(\d+)\s*Stk", str(text))
    return int(match.group(1)) if match else None

def lade_lieferanten_csv(pfad="data/lieferanten.csv"):
    try:
        return set(pd.read_csv(pfad)["name"].dropna().str.upper())
    except Exception as e:
        print(f"⚠️ Konnte Lieferantenliste nicht laden: {e}")
        return set()

def ist_lieferant(name, lieferanten_set):
    if not isinstance(name, str):
        return False
    name_upper = name.upper()
    return any(name_upper.startswith(lieferant) for lieferant in lieferanten_set)

def parse_datum_jjjjmmtt(raw):
    try:
        return datetime.strptime(str(int(raw)), "%Y%m%d").strftime("%d.%m.%Y")
    except:
        return None

def importiere_excel(pfad_excel, pfad_sqlite="data/laufende_liste.db"):
    spalten_map = {
        "Menge": "ein_mge",
        "Artikelbezeichnung": "artikel_bezeichnung",
        "Verzeichnis": "liste",
        "Pharmacode": "pharmacode",
        "Lieferdatum": "datum",
        "Fakturanr.": "faktura_nummer"
    }

    print(f"📄 Lade Excel-Datei: {pfad_excel}")
    df = pd.read_excel(pfad_excel, sheet_name=0, header=2)

    # Nur relevante Spalten übernehmen
    df = df[[col for col in spalten_map if col in df.columns]].rename(columns=spalten_map)

    # Liste (a / b)
    df["liste"] = df["liste"].astype(str).str.strip().str.lower()

    # Datum konvertieren
    df["datum"] = df["datum"].apply(parse_datum_jjjjmmtt)
    df = df[df["datum"].notna()]

    # Packung aus Artikelname extrahieren
    df["ein_pack"] = df.apply(
        lambda row: extrahiere_packung(row["artikel_bezeichnung"]) if pd.notna(row["ein_mge"]) else None, axis=1)

    # Eingang berechnen
    df["eingang"] = df.apply(
        lambda row: row["ein_mge"] * row["ein_pack"] if pd.notna(row["ein_mge"]) and pd.notna(row["ein_pack"]) else None, axis=1)

    # Standardfelder für DB
    df["aus_mge"] = None
    df["aus_pack"] = None
    df["ausgang"] = None
    df["total"] = df["eingang"]
    df["name"] = None
    df["vorname"] = None
    df["ks"] = None
    df["bemerkung"] = None
    df["prirez"] = None
    df["quelle"] = "excel"

    # Lieferantenerkennung via pharmacode (optional)
    lieferanten_set = lade_lieferanten_csv()
    df["lieferant"] = df["pharmacode"].apply(lambda val: val if ist_lieferant(str(val), lieferanten_set) else None)

    # Zielspalten in richtiger Reihenfolge
    df = df[
        ["pharmacode", "datum", "artikel_bezeichnung", "ein_mge", "ein_pack", "eingang",
         "aus_mge", "aus_pack", "ausgang", "total", "name", "vorname", "lieferant",
         "ks", "bemerkung", "prirez", "faktura_nummer", "liste", "quelle"]
    ]

    # In Datenbank speichern
    conn = sqlite3.connect(pfad_sqlite)
    df.to_sql("bewegungen", conn, if_exists="append", index=False)
    conn.close()

    print(f"✅ {len(df)} Zeilen importiert aus: {pfad_excel.name}")

    # Logging
    log_path = Path("logs/import.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"{datetime.now().isoformat()} | excel | {pfad_excel} | {len(df)} Zeilen\n")

# CLI
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❗ Bitte Pfad zur Excel-Datei angeben.\nBeispiel: python import_liste.py upload/liste.xlsx")
        sys.exit(1)

    pfad_excel = Path(sys.argv[1])
    if not pfad_excel.exists():
        print(f"❗ Datei nicht gefunden: {pfad_excel}")
        sys.exit(1)

    importiere_excel(pfad_excel)
