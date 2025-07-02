import pandas as pd
import sqlite3
import re
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from collections import defaultdict

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
    for line in text.splitlines():
        if "STK" in line:
            tokens = line.strip().split()
            if len(tokens) < 3:
                continue
            belegnummer = tokens[0] if tokens[0].isdigit() else "Unbekannt"
            try:
                stk_index = tokens.index("STK")
                packung = int(tokens[stk_index - 1])
                artikel_tokens = tokens[1:stk_index - 1]  # ohne belegnummer und packung
                artikel_bezeichnung = " ".join(artikel_tokens).strip()
                return {
                    "artikel_bezeichnung": artikel_bezeichnung or "Unbekannt",
                    "belegnummer": belegnummer,
                    "packungsgroesse": packung
                }
            except Exception:
                continue
    return {
        "artikel_bezeichnung": "Unbekannt",
        "belegnummer": "Unbekannt",
        "packungsgroesse": 1
    }

def detect_layout_from_page(page):
    words = page.get_text().split()
    if "Lfdnr" in words and ("Ein." in words or "Ein" in words):
        if "BG" in words and "Rez.Nr." in words:
            return "a"
        return "b"
    return None

def group_words_by_line(words, y_tolerance=1.5):
    lines = defaultdict(list)
    for word in words:
        x0, y0, x1, y1, text, *_ = word
        y_key = round(y0 / y_tolerance)
        lines[y_key].append((x0, text))
    return [
        [text for _, text in sorted(words_by_x)]
        for words_by_x in lines.values()
    ]

def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    lieferanten_set = set()
    if Path(LIEFERANTEN_PATH).exists():
        lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
        lieferanten_set = set(lieferanten_df.iloc[:, 0].str.lower().str.strip())

    for page in doc:
        meta = extract_article_info(page.get_text())
        layout = detect_layout_from_page(page)
        log_import(f"📄 Seite {page.number+1}: erkannter Layout-Typ = {layout}")

        words = page.get_text("words")
        logical_lines = group_words_by_line(words)

        for tokens in logical_lines:
            if len(tokens) < 5:
                continue
            if not re.match(r"^\d{5,}$", tokens[0]):
                continue
            if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", tokens[1]):
                continue

            lfdnr = tokens[0]
            datum = tokens[1]
            values = list(reversed(tokens[2:]))
            ein_mge = aus_mge = 0
            bg_rez_nr = None
            name_tokens = []
            lieferant = ""

            try:
                if layout == "a":
                    bewegung_token = values[3]
                    lager_token = values[2]
                    bg_rez_nr_candidate = values[1]

                    if re.match(r"^\d+$", bg_rez_nr_candidate):
                        bg_rez_nr = bg_rez_nr_candidate

                    bewegung = safe_int(bewegung_token)
                    raw_name_tokens = tokens[2:-5]
                elif layout == "b":
                    bewegung = safe_int(values[2])
                    raw_name_tokens = tokens[2:-4]
                else:
                    continue
            except:
                log_import(f"⚠️ Dirty-Zeile erkannt (rückwärts fail): {' '.join(tokens)}")
                continue

            if layout and bewegung > 0:
                ein_mge = bewegung
            elif layout and bewegung < 0:
                aus_mge = abs(bewegung)

            if raw_name_tokens and raw_name_tokens[0].isdigit():
                raw_name_tokens = raw_name_tokens[1:]

            filtered_name_tokens = []
            i = 0
            while i < len(raw_name_tokens):
                token = raw_name_tokens[i]
                if re.match(r"^[A-Z]\d{6}$", token):
                    i += 2
                    continue
                filtered_name_tokens.append(token)
                i += 1

            name_tokens = filtered_name_tokens

            if name_tokens:
                name_joined = " ".join(name_tokens).strip()
                name_normalized = name_joined.lower()
                if any(l in name_normalized for l in lieferanten_set):
                    lieferant = name_joined
                    name_tokens = []

            row_dict = {
                "lfdnr": lfdnr,
                "datum": datum,
                "ein_mge": ein_mge,
                "aus_mge": aus_mge,
                "bg_rez_nr": bg_rez_nr,
                "name": " ".join(name_tokens).strip(),
                "name_tokens": name_tokens,
                "lieferant": lieferant,
                "artikel_bezeichnung": meta.get("artikel_bezeichnung"),
                "belegnummer": meta.get("belegnummer"),
                "packungsgroesse": meta.get("packungsgroesse"),
                "raw_line": " ".join(tokens)
            }

            dirty = False
            if ein_mge and aus_mge:
                dirty = True
            if ein_mge < 0 or aus_mge < 0:
                dirty = True

            all_rows.append((row_dict, meta, layout, dirty))
            if dirty:
                log_import(f"⚠️ Dirty-Zeile erkannt: {row_dict['raw_line']}")

    log_import(f"📄 {len(all_rows)} Zeilen aus PDF extrahiert.")
    return all_rows

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
        name_tokens = row_dict["name_tokens"]
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
