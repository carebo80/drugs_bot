import fitz
import pandas as pd
import re
import difflib
import sqlite3
from pathlib import Path

# 🔧 Konfigurierbare Pfade
LIEFERANTEN_PATH = "data/lieferanten.csv"
WHITELIST_PATH = "data/whitelist.csv"
DB_PATH = "data/laufende_liste.db"
LOG_PATH = "tmp/import.log"

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

def log_import(msg):
    print(msg)

def extract_article_info(page):
    # Dummy-Extraktion (ersetzen mit echter Logik bei Bedarf)
    text = page.get_text("text")
    artikel_bezeichnung = ""
    belegnummer = ""
    packungsgroesse = 1

    for line in text.split("\n"):
        if "Medikament:" in line:
            artikel_bezeichnung = line.replace("Medikament:", "").strip()
            match = re.search(r"(\d{7,})", artikel_bezeichnung)
            if match:
                belegnummer = match.group(1)
            pg_match = re.search(r"(\d+)\s*STK", artikel_bezeichnung)
            if pg_match:
                packungsgroesse = int(pg_match.group(1))
            break

    return {
        "artikel_bezeichnung": artikel_bezeichnung.strip(),
        "belegnummer": belegnummer,
        "packungsgroesse": packungsgroesse
    }

def detect_layout_from_page(page):
    text = page.get_text("text")
    return "a" if "BG Rez.Nr." in text else "b"

def group_blocks_by_line(blocks):
    lines = []
    for b in blocks:
        lines.append(b[4].strip().split())
    return lines

def split_name_and_bewegung(tokens, layout):
    return tokens[:-3], tokens[-3:]

def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    # 📦 Lade Lieferanten
    lieferanten_map = {}
    if Path(LIEFERANTEN_PATH).exists():
        lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
        lieferanten_map = {
            normalize(name): name.strip()
            for name in lieferanten_df.iloc[:, 0] if isinstance(name, str)
        }
        lieferanten_keys = list(lieferanten_map.keys())
    else:
        lieferanten_keys = []

    for page in doc:
        meta = extract_article_info(page)
        layout = detect_layout_from_page(page)
        log_import(f"📄 Seite {page.number+1}: erkannter Layout-Typ = {layout}")
        log_import(f"📦 Artikel-Metadaten: {meta}")

        blocks = page.get_text("blocks")
        logical_lines = group_blocks_by_line(blocks)

        for tokens in logical_lines:
            token_list = tokens[0].split("\n") if len(tokens) == 1 and "\n" in tokens[0] else tokens

            real_rows = []
            current_row = []

            for token in token_list:
                if re.match(r"^\d{5,}$", token):  # mögliche Lfdnr
                    if current_row and len(current_row) >= 2 and re.match(r"^\d{2}\.\d{2}\.\d{4}$", current_row[1]):
                        real_rows.append(current_row)
                        current_row = [token]
                    else:
                        current_row.append(token)
                elif re.match(r"^\d{2}\.\d{2}\.\d{4}$", token) and current_row and len(current_row) == 1:
                    current_row.append(token)
                else:
                    current_row.append(token)

            if current_row and len(current_row) >= 2:
                real_rows.append(current_row)

            log_import(f"🧮 Seite {page.number+1}: erkannte Real-Rows = {len(real_rows)}")
            for row in real_rows:
                log_import(f"📊 Real-Row: {row}")

            for row_tokens in real_rows:
                if len(row_tokens) < 5:
                    log_import(f"⛔️ Verworfen (zu kurz): {row_tokens}")
                    continue
                if not re.match(r"^\d{5,}$", row_tokens[0]):
                    log_import(f"⛔️ Verworfen (keine gültige Lfdnr): {row_tokens}")
                    continue
                if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", row_tokens[1]):
                    log_import(f"⛔️ Verworfen (ungültiges Datum): {row_tokens}")
                    continue

                lfdnr = row_tokens[0]
                datum = row_tokens[1]
                data_tokens = row_tokens[2:]

                required_len = 12 if layout == "a" else 11
                while len(data_tokens) < required_len:
                    data_tokens.append("")

                name_tokens, bewegung_tokens = split_name_and_bewegung(data_tokens, layout)

                ein_mge = aus_mge = ""
                ein_pack = aus_pack = 0
                bg_rez_nr = ""
                lieferant = ""
                dirty = False

                numerics = [t.strip() for t in bewegung_tokens if re.match(r"^-?\d+(\.0)?$", t.strip())]
                numerics_ohne_lager = [t for t in numerics if t != "-1"]

                if len(numerics_ohne_lager) == 1:
                    val = numerics_ohne_lager[0]
                    if "-" in val:
                        aus_mge = val.lstrip("-")
                        aus_pack = meta.get("packungsgroesse", 1)
                    else:
                        ein_mge = val
                        ein_pack = meta.get("packungsgroesse", 1)
                elif len(numerics_ohne_lager) > 1:
                    dirty = True

                if layout == "a" and len(data_tokens) >= 2:
                    bg_candidate = data_tokens[-2].strip()
                    if bg_candidate.isdigit():
                        bg_rez_nr = bg_candidate

                for j, token in enumerate(name_tokens):
                    if re.match(r"^[A-Z]\d{6}$", token):
                        name_tokens = name_tokens[:j]
                        break
                name_joined = " ".join(name_tokens).strip()
                name_joined = re.sub(r"^\d{3,6}\s+", "", name_joined)

                lieferant_text = re.sub(r"\s+\d+$", "", name_joined).strip()
                lieferant_norm = normalize(lieferant_text)
                match_list = difflib.get_close_matches(lieferant_norm, lieferanten_keys, n=1, cutoff=0.9)

                if match_list:
                    matched_key = match_list[0]
                    lieferant = lieferanten_map[matched_key]
                    name_joined = ""
                    dirty = False
                    if not ein_mge:
                        for num in numerics:
                            if num != "0":
                                ein_mge = num
                                break
                        else:
                            ein_mge = "1"
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

                log_import(f"✅ Zeile übernommen: {row_dict}")
                all_rows.append((row_dict, meta, layout, dirty))
                if dirty:
                    log_import(f"⚠️ Dirty-Zeile erkannt: {row_dict['raw_line']}")

    log_import(f"📄 {len(all_rows)} Zeilen aus PDF extrahiert.")
    return all_rows

def parse_pdf_to_dataframe_dynamic_layout(rows_with_meta):
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")
    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)

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

        if lieferanten_set & token_set:
            lieferant = next(iter(lieferanten_set & token_set))
            name = ""

        if not lieferant:
            if any(w in name_norm for w in whitelist_set):
                pass
            else:
                name = re.split(r"\sK\d{6,}|\s[A-Z]\d{6,}", name_str)[0].strip()

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
