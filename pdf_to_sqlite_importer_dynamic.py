import pandas as pd
import sqlite3
import re
import fitz  # PyMuPDF
from pathlib import Path

LIEFERANTEN_PATH = "data/lieferanten.csv"
WHITELIST_PATH = "data/whitelist.csv"
DB_PATH = "data/laufende_liste.db"

def safe_int(value):
    try:
        return int(str(value).strip())
    except:
        return 0

def normalize(text):
    return re.sub(r"[^a-z]", "", text.lower())

def extract_article_info(text):
    match = re.search(r"Medikament:\s*(.*?)\s+(\d+)\s*STK", text)
    if match:
        artikel_text = match.group(1).strip()
        packung = int(match.group(2))
        beleg_match = re.search(r"\b(\d{5,})\b", artikel_text)
        belegnummer = beleg_match.group(1) if beleg_match else None
        # Entferne belegnummer aus artikelbezeichnung
        artikel_text = re.sub(rf"\b{belegnummer}\b", "", artikel_text).strip() if belegnummer else artikel_text
        return {
            "artikel_bezeichnung": artikel_text,
            "belegnummer": belegnummer,
            "packungsgroesse": packung
        }
    return {
        "artikel_bezeichnung": "Unbekannt",
        "belegnummer": None,
        "packungsgroesse": 1
    }

def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    for page in doc:
        text = page.get_text()
        meta = extract_article_info(text)
        lines = text.splitlines()

        i = 0
        while i + 1 < len(lines):
            zeile1, zeile2 = lines[i].strip(), lines[i+1].strip()
            if re.fullmatch(r"\d{5}", zeile1) and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", zeile2):
                block = lines[i:i+12]
                tokens = []
                for line in block:
                    tokens.extend(line.strip().split())
                if 9 <= len(tokens) <= 13:
                    all_rows.append((tokens, meta))
                i += 12
            else:
                i += 1

    return all_rows

def parse_row(row, meta, lieferanten_set, whitelist_set):
    layout = 'a' if len(row) == 12 else 'b' if len(row) == 11 else None
    if layout is None:
        return None
    try:
        datum = row[1]
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
        name_norm = normalize(name_str)

        lieferant = ""
        name = name_str

        # Prüfe, ob es sich um eine reine Lieferantenzeile handelt (nur 1 Wort wie "VOIGT")
        if normalize(row[3]) in lieferanten_set:
            lieferant = row[3]
            name = ""
        else:
            for l in lieferanten_set:
                if l in name_norm:
                    lieferant = l
                    name = ""
                    break

        if not lieferant:
            for wl in whitelist_set:
                if wl in name_norm:
                    break
            else:
                name = re.split(r"\sK\d{6,}|\s[A-Z]\d{6,}", name_str)[0].strip()

        b1 = safe_int(bewegung_1)
        b2 = safe_int(bewegung_2)
        ein_mge = aus_mge = ein_pack = aus_pack = 0
        dirty = False

        if lieferant:
            ein_mge = b1
            ein_pack = meta["packungsgroesse"] or 1
        elif b1 > 0 and b2 <= 0:
            ein_mge = b1
            ein_pack = meta["packungsgroesse"] or 1
        elif b2 > 0 and b1 <= 0:
            aus_mge = b2
            aus_pack = meta["packungsgroesse"] or 1
        else:
            dirty = True

        artikel_bezeichnung = meta["artikel_bezeichnung"] or "Unbekannt"

        return {
            "datum": datum,
            "name": name,
            "lieferant": lieferant,
            "ein_mge": ein_mge,
            "aus_mge": aus_mge,
            "ein_pack": ein_pack,
            "aus_pack": aus_pack,
            "bg_rez_nr": bg_rez_nr,
            "liste": layout,
            "belegnummer": meta["belegnummer"],
            "artikel_bezeichnung": artikel_bezeichnung,
            "dirty": bool(dirty),
            "quelle": "pdf"
        }
    except Exception:
        return None

def parse_pdf_to_dataframe_dynamic_layout(rows_with_meta):
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")
    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
    lieferanten_set = set(normalize(l) for l in lieferanten_df.iloc[:, 0])

    if not Path(WHITELIST_PATH).exists():
        whitelist_set = set()
    else:
        whitelist_df = pd.read_csv(WHITELIST_PATH)
        whitelist_set = set(normalize(w) for w in whitelist_df.iloc[:, 0])

    result_rows = []
    for tokens, meta in rows_with_meta:
        parsed = parse_row(tokens, meta, lieferanten_set, whitelist_set)
        if parsed:
            result_rows.append(parsed)

    return pd.DataFrame(result_rows)

def run_import(parsed_df):
    if not isinstance(parsed_df, pd.DataFrame):
        print("❌ Fehler: Übergabe ist kein DataFrame")
        return
    if parsed_df.empty:
        print("⚠️ Keine gültigen Zeilen zum Import.")
        return

    with sqlite3.connect(DB_PATH) as conn:
        parsed_df.to_sql("bewegungen", conn, if_exists="append", index=False)
    print(f"✅ {len(parsed_df)} Zeilen erfolgreich importiert.")
