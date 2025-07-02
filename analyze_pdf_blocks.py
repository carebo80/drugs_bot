import pandas as pd
import sqlite3
import re
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime

LIEFERANTEN_PATH = "data/lieferanten.csv"
WHITELIST_PATH = "data/whitelist.csv"
DB_PATH = "data/laufende_liste.db"
LOG_PATH = "tmp/import.log"

def safe_int(value):
    try:
        return int(str(value).strip())
    except:
        return 0

def normalize(text):
    return re.sub(r"[^a-z]", "", text.lower())

def log_import(message):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {message}\n")

def extract_article_info(text):
    match = re.search(r"Medikament:\s*(.*?)\s+(\d+)\s*STK", text)
    if match:
        artikel_text = match.group(1).strip()
        packung = int(match.group(2))
        beleg_match = re.search(r"\b(\d{5,})\b", artikel_text)
        belegnummer = beleg_match.group(1) if beleg_match else None
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

        start_idx = 0
        for idx in range(len(lines) - 1):
            if re.fullmatch(r"\d{5,}", lines[idx].strip()) and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", lines[idx + 1].strip()):
                start_idx = idx
                break

        lines = lines[start_idx:]

        i = 0
        while i < len(lines) - 1:
            if re.fullmatch(r"\d{5,}", lines[i].strip()) and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", lines[i + 1].strip()):
                j = i + 2
                row_lines = [lines[i], lines[i + 1]]
                while j < len(lines) and not re.fullmatch(r"\d{5,}", lines[j].strip()):
                    row_lines.append(lines[j])
                    j += 1
                tokens = " ".join(row_lines).split()
                if "Gesamt:" in tokens:
                    i = j
                    continue
                dirty = False
                layout = 'a' if any(re.fullmatch(r"\d{8,}", t) for t in tokens[-3:]) else 'b'
                if len(tokens) < 11:
                    tokens += ["" for _ in range(11 - len(tokens))]
                    dirty = True
                row_dict = {
                    "lfdnr": tokens[0] if len(tokens) > 0 else "",
                    "datum": tokens[1] if len(tokens) > 1 else "",
                    "bewegung_1": tokens[-4] if layout == 'a' else tokens[-3],
                    "bewegung_2": tokens[-3] if layout == 'a' else tokens[-2],
                    "bg_rez_nr": tokens[-2] if layout == 'a' else None,
                    "name_tokens": tokens[3:-4] if layout == 'a' else tokens[3:-3],
                    "raw_tokens": tokens
                }
                all_rows.append((row_dict, meta, layout, dirty))
                i = j
            else:
                i += 1

    return all_rows

def parse_pdf_to_dataframe_dynamic_layout(rows_with_meta):
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")
    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
    lieferanten_set = set(normalize(l) for l in lieferanten_df.iloc[:, 0])

    whitelist_set = set()
    if Path(WHITELIST_PATH).exists():
        whitelist_df = pd.read_csv(WHITELIST_PATH)
        whitelist_set = set(normalize(w) for w in whitelist_df.iloc[:, 0])

    parsed_rows = []
    for row_dict, meta, layout, dirty in rows_with_meta:
        name_tokens = row_dict["name_tokens"]
        name_str = " ".join(name_tokens).strip()
        name_norm = normalize(name_str)

        lieferant = ""
        name = name_str

        # 💡 Neue robuste Lieferantenerkennung
        candidate = normalize(" ".join(name_tokens))
        if candidate in lieferanten_set:
            lieferant = " ".join(name_tokens)
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

        b1 = safe_int(row_dict["bewegung_1"])
        b2 = safe_int(row_dict["bewegung_2"])
        ein_mge = aus_mge = ein_pack = aus_pack = 0

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

        parsed_rows.append({
            "datum": row_dict["datum"],
            "name": name,
            "lieferant": lieferant,
            "ein_mge": ein_mge,
            "aus_mge": aus_mge,
            "ein_pack": ein_pack,
            "aus_pack": aus_pack,
            "bg_rez_nr": row_dict["bg_rez_nr"],
            "liste": layout,
            "belegnummer": meta["belegnummer"],
            "artikel_bezeichnung": meta["artikel_bezeichnung"],
            "dirty": bool(dirty),
            "quelle": "pdf"
        })

    return pd.DataFrame(parsed_rows)

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
