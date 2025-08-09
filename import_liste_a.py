# import_liste_a.py
import sys
import pandas as pd
import sqlite3
from datetime import datetime
from pathlib import Path
from utils.helpers import ensure_views

DB_PATH = "data/laufende_liste.db"
UEBERTRAG_TEXT = "Uebertrag per 01.01.2020"
DEBUG = True  # bei Bedarf auf False

ensure_views())

# flexibles Spalten-Mapping (Excel -> interne Namen)
SPALTEN_MAP = {
    "Belegnr": "pharmacode",
    "Artikel-Bezeichnung": "artikel_bezeichnung",
    "Artikelbezeichnung": "artikel_bezeichnung",
    "Liste": "liste",
    "Verzeichnis": "liste",
    "Datum": "datum",
    "Lieferdatum": "datum",
    "LS-Nummer": "faktura_nummer",
    "Fakturanr.": "faktura_nummer",
    "Ein.Mge": "ein_mge",
    "Menge": "ein_mge",
    "Ein.Pack": "ein_pack",
    "Aus.Mge": "aus_mge",
    "Aus.Pack": "aus_pack",
    "Name": "name",
    "Vorname": "vorname",
    "Bemerkung": "bemerkung",
    "PriRez": "prirez",
}

def parse_datum_any(x):
    import pandas as pd
    if pd.isna(x):
        return None
    ts = pd.to_datetime(x, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return ts.date().isoformat()

def lade_excel_liste_a(pfad_excel: str) -> pd.DataFrame:
    # 1) Einlesen
    df = pd.read_excel(pfad_excel, sheet_name="Laufende Liste", header=0)
    df.columns = df.columns.astype(str).str.strip()

    if DEBUG:
        print("📋 Spalten (roh):", list(df.columns))

    # 2) Spalten umbenennen (nur vorhandene)
    vorhandene = {k: v for k, v in SPALTEN_MAP.items() if k in df.columns}
    df = df.rename(columns=vorhandene)

    if DEBUG:
        print("📋 Spalten (gemappt):", list(df.columns))

    # 3) Pflichtspalten checken
    required = ["artikel_bezeichnung", "datum", "pharmacode"]
    missing = [c for c in required if c not in df.columns]
    if "liste" not in df.columns:
        # Notfall: falls nach Mapping keine 'liste' existiert, versuche original "Liste"/"Verzeichnis"
        if "Liste" in df.columns:
            df = df.rename(columns={"Liste": "liste"})
        elif "Verzeichnis" in df.columns:
            df = df.rename(columns={"Verzeichnis": "liste"})
        else:
            missing.append("liste")

    if missing:
        raise ValueError(f"Fehlende Spalten nach Mapping: {missing}. Gefunden: {list(df.columns)}")

    # 4) Nur Liste a
    df["liste"] = df["liste"].astype(str).str.strip().str.lower()
    if DEBUG:
        print("🔎 Liste-Werte (unique vor Filter):", df["liste"].dropna().unique())
    df = df[df["liste"] == "a"]

    if DEBUG:
        print("🔎 Zeilen nach Liste-a-Filter:", len(df))

    # 5) Übertrag-Zeilen NICHT importieren (bleiben separat in DB)
    if "bemerkung" in df.columns:
        df = df[df["bemerkung"].fillna("").str.strip() != UEBERTRAG_TEXT]

    # 6) Datentypen
    df["pharmacode"] = pd.to_numeric(df["pharmacode"], errors="coerce").astype("Int64")
    # Mengen/Pack
    for col in ("ein_mge", "ein_pack", "aus_mge", "aus_pack"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Datum normalisieren
    df["datum"] = df["datum"].apply(parse_datum_any)
    df = df[df["datum"].notna()]

    # 7) Eingang/Ausgang berechnen (NULL, wenn unvollständig)
    df["eingang"] = (df["ein_mge"] * df["ein_pack"]).where(
        df.get("ein_mge").notna() & df.get("ein_pack").notna()
    ) if "ein_mge" in df and "ein_pack" in df else None

    df["ausgang"] = (df["aus_mge"] * df["aus_pack"]).where(
        df.get("aus_mge").notna() & df.get("aus_pack").notna()
    ) if "aus_mge" in df and "aus_pack" in df else None

    # 8) fixe Felder
    df["quelle"] = "excel"
    df["dirty"] = False

    # 9) Nur relevante Spalten fürs Insert sicherstellen
    keep_cols = [
        "pharmacode", "artikel_bezeichnung", "liste", "datum",
        "ein_mge", "ein_pack", "eingang",
        "aus_mge", "aus_pack", "ausgang",
        "name", "vorname", "bemerkung",
        "prirez", "faktura_nummer",
        "quelle", "dirty",
    ]
    for c in keep_cols:
        if c not in df.columns:
            df[c] = None

    df = df[keep_cols]

    if DEBUG:
        print("🧾 vorbereitete Zeilen (Liste a):", len(df))

    return df

def replace_liste_a_in_db(df: pd.DataFrame, db_path: str):
    # 🧼 ALLE pd.NA/NaN zu None konvertieren – SQLite-safe
    # 1) saubere Dtypes
    df = df.convert_dtypes()          # pandas NA-typen konsolidieren
    # 2) objekt-cast, damit None möglich ist
    df = df.astype(object)
    # 3) spaltenweise NAs -> None
    for col in df.columns:
        df[col] = df[col].where(pd.notna(df[col]), None)
    # 4) Booleans als int (SQLite hat kein echtes Bool)
    if "dirty" in df.columns:
        df["dirty"] = df["dirty"].map(lambda x: 1 if x is True else 0 if x is False else x)

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        # Vorab löschen: nur Excel/Liste A, Übertrag behalten
        cur.execute(
            """
            DELETE FROM bewegungen
            WHERE quelle='excel'
              AND liste='a'
              AND COALESCE(TRIM(bemerkung),'') <> ?
            """,
            (UEBERTRAG_TEXT,)
        )

        placeholders = ",".join(["?"] * len(df.columns))
        cols = ",".join(df.columns)
        sql = f"INSERT INTO bewegungen ({cols}) VALUES ({placeholders})"

        # Tuples bauen (hier sind jetzt garantiert Python-None statt pd.NA)
        rows = [tuple(row) for row in df.itertuples(index=False, name=None)]
        cur.executemany(sql, rows)
        conn.commit()

    # Logging …

        cur.executemany(sql, [tuple(row) for row in df.itertuples(index=False, name=None)])
        conn.commit()

    # Log
    log_path = Path("logs/import.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"{datetime.now().isoformat()} | import_liste_a | rows={len(df)}\n")

def main():
    if len(sys.argv) < 2:
        print("❗ Bitte Pfad zur Excel-Datei angeben.\nBeispiel: python import_liste_a.py 'upload/btm-mappe_fortlaufend (1).xlsx'")
        raise SystemExit(1)
    excel_path = sys.argv[1]
    print(f"📄 Lade Excel-Datei: {excel_path}")
    df = lade_excel_liste_a(excel_path)
    print(f"🧾 {len(df)} Zeilen (Liste a) vorbereitet.")
    replace_liste_a_in_db(df, DB_PATH)
    print("✅ Liste a erfolgreich ersetzt.")

if __name__ == "__main__":
    main()
