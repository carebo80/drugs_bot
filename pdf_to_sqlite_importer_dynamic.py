import pandas as pd
import sqlite3
import re
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import difflib

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

def group_blocks_by_line(blocks, y_tolerance=2.0):
    lines = defaultdict(list)
    for x0, y0, x1, y1, text, *_ in blocks:
        y_key = round(y0 / y_tolerance)
        lines[y_key].append((x0, text))
    return [
        [text for _, text in sorted(words_by_x)]
        for words_by_x in lines.values()
    ]

def extract_article_info(page):
    for line in group_blocks_by_line(page.get_text("blocks")):
        if line and line[0].lower().startswith("medikament:"):
            full_line = " ".join(line)
            match = re.search(r"medikament:\s*(\d+)\s+(.*?)(\d+)\s+stk", full_line.lower())
            if match:
                belegnummer = match.group(1)
                artikel_bezeichnung = f"{match.group(2).strip()} {match.group(3)} STK".upper()
                packungsgroesse = safe_int(match.group(3))
                return {
                    "artikel_bezeichnung": artikel_bezeichnung,
                    "belegnummer": belegnummer,
                    "packungsgroesse": packungsgroesse
                }
    return {
        "artikel_bezeichnung": "Unbekannt",
        "belegnummer": "Unbekannt",
        "packungsgroesse": 1
    }

def detect_layout_from_page(page):
    text = page.get_text()
    if "Lfdnr" in text and ("Ein." in text or "Ein" in text):
        if "BG" in text and "Rez.Nr." in text:
            return "a"
        return "b"
    return None

def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    lieferanten_map = {}
    if Path(LIEFERANTEN_PATH).exists():
        lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
        lieferanten_map = {
            name.lower().strip(): name.strip()
            for name in lieferanten_df.iloc[:, 0] if isinstance(name, str)
        }
        lieferanten_keys = list(lieferanten_map.keys())
    else:
        lieferanten_keys = []

    for page in doc:
        meta = extract_article_info(page)
        layout = detect_layout_from_page(page)
        log_import(f"📄 Seite {page.number+1}: erkannter Layout-Typ = {layout}")

        blocks = page.get_text("blocks")
        logical_lines = group_blocks_by_line(blocks)

        for tokens in logical_lines:
            if len(tokens) == 1 and "\n" in tokens[0]:
                token_list = tokens[0].split("\n")
            else:
                token_list = tokens

            real_rows = []
            current_row = []
            for token in token_list:
                if re.match(r"^\d{5,}$", token):
                    if current_row:
                        real_rows.append(current_row)
                    current_row = [token]
                else:
                    current_row.append(token)
            if current_row:
                real_rows.append(current_row)

            for row_tokens in real_rows:
                if len(row_tokens) < 5:
                    continue
                if not re.match(r"^\d{5,}$", row_tokens[0]):
                    continue
                if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", row_tokens[1]):
                    continue

                lfdnr = row_tokens[0]
                datum = row_tokens[1]
                data_tokens = row_tokens[2:]

                required_len = 12 if layout == "a" else 11
                while len(data_tokens) < required_len:
                    data_tokens.append("")

                ein_mge = aus_mge = ""
                ein_pack = aus_pack = 0
                bg_rez_nr = ""
                name_tokens = []
                lieferant = ""
                dirty = False

                name_tokens = data_tokens[:-5] if layout == "a" else data_tokens[:-4]
                bewegung_tokens = data_tokens[-5:] if layout == "a" else data_tokens[-4:]

                numerics = [t for t in bewegung_tokens if re.match(r"^-?\d+$", t)]
                numerics_ohne_lager = [t for t in numerics if t != "-1"]

                if len(numerics_ohne_lager) == 1:
                    val = numerics_ohne_lager[0]
                    if "-" in val:
                        aus_mge = val.lstrip("-")
                        aus_pack = meta.get("packungsgroesse", 1)
                    else:
                        ein_mge = val
                        ein_pack = meta.get("packungsgroesse", 1)
                elif len(numerics_ohne_lager) == 0:
                    pass
                else:
                    dirty = True

                if layout == "a":
                    bg_candidate = data_tokens[-2].strip()
                    if bg_candidate.isdigit():
                        bg_rez_nr = bg_candidate

                for j, token in enumerate(name_tokens):
                    if re.match(r"^[A-Z]\d{6}$", token):
                        name_tokens = name_tokens[:j]
                        break

                name_joined = " ".join(name_tokens).strip()
                lieferant_match = None
                lieferant_text = name_joined.lower()

                match_list = difflib.get_close_matches(lieferant_text, lieferanten_keys, n=1, cutoff=0.9)
                if match_list:
                    normalized = match_list[0].strip()
                    lieferant_match = lieferanten_map.get(normalized, normalized)

                if lieferant_match:
                    lieferant = lieferant_match
                    name_joined = ""
                    bg_rez_nr = "0"
                    dirty = False
                    if not ein_mge:
                        ein_mge = numerics[0] if numerics else "1"
                        ein_pack = meta.get("packungsgroesse", 1)

                if ein_mge and aus_mge:
                    dirty = True

                row_dict = {
                    "lfdnr": lfdnr,
                    "datum": datum,
                    "ein_mge": ein_mge,
                    "ein_pack": ein_pack,
                    "aus_mge": aus_mge,
                    "aus_pack": aus_pack,
                    "bg_rez_nr": bg_rez_nr,
                    "name": name_joined,
                    "lieferant": lieferant,
                    "artikel_bezeichnung": meta.get("artikel_bezeichnung"),
                    "belegnummer": meta.get("belegnummer"),
                    "packungsgroesse": meta.get("packungsgroesse"),
                    "raw_line": " ".join(row_tokens)
                }

                all_rows.append((row_dict, meta, layout, dirty))
                if dirty:
                    log_import(f"⚠️ Dirty-Zeile erkannt: {row_dict['raw_line']}")

    log_import(f"📄 {len(all_rows)} Zeilen aus PDF extrahiert.")
    return all_rows

def split_into_real_rows(tokens):
    rows = []
    current_row = []
    for token in tokens:
        if re.match(r"^\d{5,}$", token):  # Lfdnr beginnt neue Zeile
            if current_row:
                rows.append(current_row)
            current_row = [token]
        else:
            current_row.append(token)
    if current_row:
        rows.append(current_row)
    return rows

def parse_pdf_to_dataframe_dynamic_layout(rows_with_meta):
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")
    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
    
    # Erzeuge Set mit normalisierten Einzelwörtern aus Lieferantennamen
    lieferanten_set = set()
    for val in lieferanten_df.iloc[:, 0]:
        for token in str(val).split():
            lieferanten_set.add(normalize(token))

    whitelist_set = set()
    if Path(WHITELIST_PATH).exists():
        whitelist_df = pd.read_csv(WHITELIST_PATH)
        whitelist_set = set(normalize(w) for w in whitelist_df.iloc[:, 0])

    parsed_rows = []
    for row_dict, meta, layout, dirty in rows_with_meta:
        name_tokens = row_dict.get("name", "").split()
        name_str = " ".join(name_tokens).strip()
        name_norm = normalize(name_str)
        token_set = set(normalize(tok) for tok in name_tokens)

        lieferant = ""
        name = name_str

        # 🧪 Debug-Ausgaben
        print(f"📦 Tokens: {name_tokens}")
        print(f"🔍 Normalisiert: {token_set}")
        print(f"🔎 Kandidat für Match: '{name_str}'")

        if lieferanten_set & token_set:
            lieferant = next(iter(lieferanten_set & token_set))
            name = ""
            print(f"✅ Lieferant erkannt: {lieferant}")

        # Whitelist-Check
        if not lieferant:
            if any(w in name_norm for w in whitelist_set):
                pass  # in Ordnung
            else:
                # Versuche Arzt-/Kundennummern abzuschneiden
                name = re.split(r"\sK\d{6,}|\s[A-Z]\d{6,}", name_str)[0].strip()

        # Bewegungswerte auswerten
        b1 = safe_int(row_dict["ein_mge"])
        b2 = safe_int(row_dict["aus_mge"])
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
            "belegnummer": meta["belegnummer"] or "Unbekannt",
            "artikel_bezeichnung": meta["artikel_bezeichnung"] or "Unbekannt",
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
    log_import(f"✅ {len(parsed_df)} Zeilen erfolgreich in DB importiert.")
