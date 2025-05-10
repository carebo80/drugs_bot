import sys
import pandas as pd
import sqlite3
import re
from pathlib import Path

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

def importiere_excel(pfad_excel, pfad_sqlite="data/laufende_liste.db", sheet="Laufende Liste", liste_filter=None):
    spalten_map = {
        "Beleg vorhanden?": "belegnummer",
        "Artikel-Bezeichnung": "artikel_bezeichnung",
        "Liste": "liste",
        "Datum": "datum",
        "Ein.Mge": "ein_mge",
        "Ein.Pack": "ein_pack",
        "Eingang": "eingang",
        "Aus.Mge": "aus_mge",
        "Aus.Pack": "aus_pack",
        "Ausgang": "ausgang",
        "KS": "ks",
        "Total": "total",
        "Name": "name",
        "Vorname": "vorname",
        "Bemerkung": "bemerkung",
        "PriRez": "prirez",
        "LS-Nummer": "ls_nummer"
    }

    print(f"\U0001F4C4 Lade Excel-Datei: {pfad_excel}")
    df = pd.read_excel(pfad_excel, sheet_name=sheet)

    # Spalten umbenennen
    df_clean = df[list(spalten_map.keys())].rename(columns=spalten_map)

    # Optional Liste A oder B filtern
    if liste_filter:
        df_clean = df_clean[df_clean["liste"].str.lower() == liste_filter.lower()]

    # Leere oder ungültige Zeilen filtern
    df_clean = df_clean[df_clean["artikel_bezeichnung"].notna() & df_clean["datum"].notna()]

    # Robust: ungültige Datumseinträge rausfiltern
    df_clean["datum"] = pd.to_datetime(df_clean["datum"], errors="coerce")
    df_clean = df_clean[df_clean["datum"].notna()]
    df_clean["datum"] = df_clean["datum"].dt.strftime("%d.%m.%Y")

    # Packung extrahieren wenn nötig
    df_clean["ein_pack"] = df_clean.apply(
        lambda row: extrahiere_packung(row["artikel_bezeichnung"]) if pd.notna(row["ein_mge"]) and pd.isna(row["ein_pack"]) else row["ein_pack"], axis=1)
    df_clean["aus_pack"] = df_clean.apply(
        lambda row: extrahiere_packung(row["artikel_bezeichnung"]) if pd.notna(row["aus_mge"]) and pd.isna(row["aus_pack"]) else row["aus_pack"], axis=1)

    df_clean["eingang"] = df_clean.apply(
        lambda row: row["ein_mge"] * row["ein_pack"] if pd.notna(row["ein_mge"]) and pd.notna(row["ein_pack"]) else row["eingang"], axis=1)
    df_clean["ausgang"] = df_clean.apply(
        lambda row: row["aus_mge"] * row["aus_pack"] if pd.notna(row["aus_mge"]) and pd.notna(row["aus_pack"]) else row["ausgang"], axis=1)

    df_clean["total"] = df_clean.apply(
        lambda row: row["eingang"] - row["ausgang"] if pd.notna(row["eingang"]) and pd.notna(row["ausgang"]) else row["total"], axis=1)

    # Lieferanten aus CSV (fuzzy: StartsWith) oder wenn LS-Nummer gesetzt
    lieferanten_set = lade_lieferanten_csv()
    lieferanten_mask = (
        df_clean["ein_mge"].notna() & (
            df_clean["name"].apply(lambda x: ist_lieferant(x, lieferanten_set)) |
            df_clean["ls_nummer"].notna()
        )
    )
    df_clean.loc[lieferanten_mask, "lieferant"] = df_clean.loc[lieferanten_mask, "name"]
    df_clean.loc[lieferanten_mask, "name"] = None
    df_clean.loc[lieferanten_mask, "vorname"] = None

    df_clean["quelle"] = "excel"

    # In SQLite einfügen
    conn = sqlite3.connect(pfad_sqlite)
    df_clean.to_sql("bewegungen", conn, if_exists="append", index=False)
    conn.close()

    print(f"\u2705 {len(df_clean)} Zeilen importiert (Liste = {liste_filter or 'alle'}).")

# CLI-Aufruf
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\u2757 Bitte Pfad zur Excel-Datei angeben.\nBeispiel: python import_liste.py 'btm.xlsx' [a|b|leer]")
        sys.exit(1)

    pfad_excel = Path(sys.argv[1])
    liste_filter = sys.argv[2] if len(sys.argv) > 2 else None

    if not pfad_excel.exists():
        print(f"\u2757 Datei nicht gefunden: {pfad_excel}")
        sys.exit(1)

    importiere_excel(pfad_excel, liste_filter=liste_filter)
