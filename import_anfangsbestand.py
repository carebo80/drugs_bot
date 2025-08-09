# import_anfangsbestand.py
import pandas as pd
import sqlite3
from datetime import datetime
from pathlib import Path

EXCEL_PATH = "upload/btm-mappe_fortlaufend (1).xlsx"
DB_PATH = "data/laufende_liste.db"

# Mapping: Excel → DB
SPALTEN_MAPPING = {
    "Belegnr": "pharmacode",
    "Artikel-Bezeichnung": "artikel_bezeichnung",
    "Liste": "liste",
    "Datum": "datum",
    "Ein.Mge": "ein_mge",
    "Ein.Pack": "ein_pack",
    "Name": "bemerkung"
}

IGNORIERTE_ARTIKEL = [
    "Haens Opii tinctura normata PhEur 20 g"
]

def lade_excel(pfad):
    df = pd.read_excel(pfad, skiprows=0)
    df = df.rename(columns=SPALTEN_MAPPING)
    df = df[df["artikel_bezeichnung"].notna()]
    df = df[~df["artikel_bezeichnung"].isin(IGNORIERTE_ARTIKEL)]

    # Nur Liste A importieren
    df = df[df["liste"].astype(str).str.strip().str.lower() == "a"]

    # Pharmacode als Integer
    df["pharmacode"] = pd.to_numeric(df["pharmacode"], errors="coerce").astype("Int64")

    # Datum formatieren
    df["datum"] = pd.to_datetime(df["datum"], errors="coerce").dt.date

    # Mengen und Packungen bereinigen
    df["ein_mge"] = pd.to_numeric(df["ein_mge"], errors="coerce").fillna(0).astype(int)
    df["ein_pack"] = pd.to_numeric(df["ein_pack"], errors="coerce").fillna(0).astype(int)

    # Eingang berechnen
    df["eingang"] = df["ein_mge"] * df["ein_pack"]

    # Zusätzliche Felder
    df["aus_mge"] = None
    df["aus_pack"] = None
    df["ausgang"] = None
    df["name"] = None
    df["vorname"] = None
    df["dirty"] = False
    df["quelle"] = "excel"

    return df[[
        "pharmacode", "artikel_bezeichnung", "liste", "datum",
        "ein_mge", "ein_pack", "eingang",
        "aus_mge", "aus_pack", "ausgang",
        "bemerkung", "name", "vorname",
        "dirty", "quelle"
    ]]

def speichere_in_db(df, db_path):
    # Konvertiere alle pd.NA/nan zu None (für SQLite-kompatibel)
    df = df.where(pd.notna(df), None)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for _, row in df.iterrows():
        werte = tuple(None if pd.isna(val) else val for val in row.values)
        placeholder = ",".join(["?"] * len(df.columns))
        spalten = ",".join(df.columns)
        sql = f"INSERT INTO bewegungen ({spalten}) VALUES ({placeholder})"
        cursor.execute(sql, werte)

    conn.commit()
    conn.close()

    # Logging
    log_path = Path("logs/import.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"{datetime.now().isoformat()} | anfangsbestand | {EXCEL_PATH} | {len(df)} Zeilen\n")

def main():
    df = lade_excel(EXCEL_PATH)
    print(f"🗕 {len(df)} Zeilen geladen für Import.")
    speichere_in_db(df, DB_PATH)
    print("✅ Anfangsbestände erfolgreich importiert.")

if __name__ == "__main__":
    main()
