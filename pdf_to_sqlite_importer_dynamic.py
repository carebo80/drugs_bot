# pdf_to_sqlite_importer_dynamic.py
import fitz
import pandas as pd
import re
import sqlite3
from pathlib import Path
from utils.logger import get_log_path, log_import
from utils.env import get_env_var, validate_env

ENV =get_env_var("APP_ENV")
LOG_PATH = get_env_var("LOG_PATH")

# 🔧 Konfigurierbare Pfade
LIEFERANTEN_PATH = "data/lieferanten.csv"
WHITELIST_PATH = "data/whitelist.csv"
DB_PATH = "data/laufende_liste.db"

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

def extract_article_info(page):
    text = page.get_text("text")
    artikel_bezeichnung = ""
    belegnummer = ""
    packungsgroesse = 1

    for line in text.split("\n"):
        if "Medikament:" in line:
            artikel_line = line.replace("Medikament:", "").strip()
            
            # Neu: Suche an beliebiger Stelle nach 4–8-stelliger Belegnummer
            match = re.search(r"\b(\d{4,8})\b", artikel_line)
            if match:
                belegnummer = match.group(1)
                artikel_bezeichnung = artikel_line.replace(belegnummer, "").strip()
            else:
                artikel_bezeichnung = artikel_line

            # Packungsgröße bleibt
            pg_match = re.search(r"(\d+)\s*STK", artikel_line)
            if pg_match:
                packungsgroesse = int(pg_match.group(1))
            break

    return {
        "artikel_bezeichnung": artikel_bezeichnung,
        "belegnummer": belegnummer or "Unbekannt",
        "packungsgroesse": packungsgroesse
    }

def detect_layout_from_page(page):
    return "a" if "BG Rez.Nr." in page.get_text("text") else "b"

def clean_name_and_bg_rez_nr(name: str, bg_rez_nr: str) -> tuple[str, str]:
    # Wenn im Namen eine echte BG-Nummer steckt, extrahiere sie
    matches = re.findall(r"\b\d{7,9}\b", name)
    if matches and (not bg_rez_nr or bg_rez_nr == "0"):
        bg_rez_nr = matches[-1]
        name = re.sub(r"\b" + re.escape(bg_rez_nr) + r"\b", "", name)

    # Entferne Arzt-Kennungen (z.B. T123456) und alles danach
    name = re.split(r"\s(?:K|T)\d{6,}", name)[0]

    # Entferne unnötige 1–3-stellige Zahlen (z. B. Vorangestellte Kundennummern)
    name = re.sub(r"\b\d{1,3}\b", "", name)

    # Mehrfache Leerzeichen bereinigen
    name = re.sub(r"\s+", " ", name).strip()

    return name, bg_rez_nr

def detect_bewegung(tokens: list[str], is_lieferant: bool) -> tuple[str, str, bool]:
    """
    Liefert (ein_mge, aus_mge, dirty)
    - Zahlen als string zurück ("" bei leer)
    - keine automatische 0
    - is_lieferant steuert Verhalten
    """
    # Nur echte Zahlen als string extrahieren (auch '0', keine Dezimalzahlen)
    digits = [t for t in tokens if re.fullmatch(r"-?\d+", t)]

    ein_mge = ""
    aus_mge = ""
    dirty = False

    if not digits:
        return "", "", True

    digits_int = [int(d) for d in digits]
    digits_rev = digits[::-1]  # für spätere Indexzugriffe

    if is_lieferant:
        # Nehme 3. Zahl von rechts (Ein)
        if len(digits_rev) >= 3:
            val = digits_rev[2]
            ein_mge = val if val != "-1" else ""  # Lagerwert vermeiden
        elif len(digits_rev) >= 1:
            ein_mge = digits_rev[0]
        else:
            dirty = True
    else:
        # Letzte ist Lager
        lager_val = digits_rev[0] if len(digits_rev) >= 1 else None
        aus_val = digits_rev[1] if len(digits_rev) >= 2 else None
        ein_val = digits_rev[2] if len(digits_rev) >= 3 else None

        if ein_val and not aus_val:
            ein_mge = ein_val
        elif aus_val and not ein_val:
            aus_mge = aus_val
        elif not ein_val and not aus_val:
            dirty = True
        else:
            dirty = True

    return str(ein_mge).strip(), str(aus_mge).strip(), dirty

def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    for page_num, page in enumerate(doc):
        meta = extract_article_info(page)
        layout = detect_layout_from_page(page)

        blocks = page.get_text("blocks")
        lines = [b[4].strip() for b in sorted(blocks, key=lambda b: (round(b[1], 1), b[0])) if b[4].strip()]

        current_line_tokens = []
        for line in lines:
            current_line_tokens.extend(line.strip().split())

        i = 0
        rows = []
        while i < len(current_line_tokens) - 1:
            token = current_line_tokens[i]
            next_token = current_line_tokens[i + 1]

            if re.fullmatch(r"\d{5,}", token) and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", next_token):
                j = i + 2
                while j < len(current_line_tokens):
                    if re.fullmatch(r"\d{5,}", current_line_tokens[j]) and j + 1 < len(current_line_tokens) and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", current_line_tokens[j + 1]):
                        break
                    j += 1

                row_tokens = current_line_tokens[i:j]

                footer_keywords = ("gesamt", "total")
                footer_index = next((k for k, tok in enumerate(row_tokens) if any(tok.lower().startswith(f) for f in footer_keywords)), None)
                if footer_index is not None:
                    log_import(f"\u26d8 Footer erkannt, Abschneiden ab Index {footer_index}: {row_tokens}")
                    row_tokens = row_tokens[:footer_index]

                if len(row_tokens) >= 5:
                    rows.append(row_tokens)
                else:
                    log_import(f"\u26a0\ufe0f Ignorierte Kurz-Zeile nach Footer-Schnitt: {row_tokens}")

                i = j
            else:
                i += 1

        log_import(f"📄 Seite {page_num+1}: {len(rows)} Real-Rows erkannt.")

        # Lade Lieferantenliste
        if not Path(LIEFERANTEN_PATH).exists():
            raise FileNotFoundError("Lieferantenliste nicht gefunden")
        lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)
        lieferanten_set = set(normalize(tok) for val in lieferanten_df.iloc[:, 0].dropna() for tok in str(val).split())

        for r in rows:
            if len(r) < 5:
                continue

            lfdnr = r[0]
            datum = r[1]
            remaining = r[2:]

            # Lieferantenerkennung
            tokens_norm = set(normalize(t) for t in remaining)
            is_lieferant = bool(lieferanten_set & tokens_norm)

            # Nur numerische Tokens extrahieren (auch '0', aber keine Dezimalzahlen)
            numeric_tokens = [t for t in remaining if re.fullmatch(r"-?\d+", t)]
            log_import(f"💬 Vor detect_bewegung: Tokens={numeric_tokens}")
            ein_mge, aus_mge, dirty = detect_bewegung(numeric_tokens, is_lieferant)

            # BG Rez.Nr. nur für Layout A
            bg_rez_nr = ""
            if layout == "a":
                for tok in reversed(remaining):
                    if re.fullmatch(r"\d{7,9}", tok):
                        bg_rez_nr = tok
                        break

            if not ein_mge and not aus_mge:
                log_import(f"⚪ Keine Bewegung erkannt → dirty: {remaining}")

            used_tokens = {ein_mge, aus_mge, bg_rez_nr}
            name_tokens = [t for t in remaining if t not in used_tokens and not re.fullmatch(r"0+", t)]
            name = " ".join(name_tokens)

            log_import(f"🔍 Tokens: {[name, ein_mge, aus_mge, bg_rez_nr]}")

            row_dict = {
                "lfdnr": lfdnr,
                "datum": datum,
                "name": name,
                "ein_mge": ein_mge,
                "aus_mge": aus_mge,
                "bg_rez_nr": bg_rez_nr if layout == "a" else ""
            }

            all_rows.append((row_dict, meta, layout, dirty))

    log_import(f"✅ Gesamt extrahierte Zeilen: {len(all_rows)}")
    return all_rows

def parse_pdf_to_dataframe_dynamic_layout(rows_with_meta):
    if not Path(LIEFERANTEN_PATH).exists():
        raise FileNotFoundError("Lieferantenliste nicht gefunden")
    lieferanten_df = pd.read_csv(LIEFERANTEN_PATH)

    # Lieferantentokens extrahieren
    lieferanten_set = set()
    for val in lieferanten_df.iloc[:, 0].dropna():
        for token in str(val).split():
            lieferanten_set.add(normalize(token))

    # Whitelist laden
    whitelist_set = set()
    if Path(WHITELIST_PATH).exists():
        whitelist_df = pd.read_csv(WHITELIST_PATH)
        whitelist_set = set(normalize(w) for w in whitelist_df.iloc[:, 0])

    parsed_rows = []
    seen_keys = set()

    for row_dict, meta, layout, dirty in rows_with_meta:
        key = (row_dict["lfdnr"], row_dict["datum"])
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Name & BG RezNr bereinigen
        raw_name = row_dict.get("name", "")
        name_tokens = raw_name.split()
        name = raw_name
        bg_rez_nr = row_dict.get("bg_rez_nr", "")
        name, bg_rez_nr = clean_name_and_bg_rez_nr(name, bg_rez_nr)

        name_norm = normalize(name)
        token_set = set(normalize(tok) for tok in name_tokens)

        # Lieferant erkennen
        lieferant = ""
        match_tokens = lieferanten_set & token_set
        for token in name_tokens:
            norm_tok = normalize(token)
            if norm_tok in match_tokens and norm_tok != "dr":
                lieferant = token  # Original-Schreibweise übernehmen
                break

        # Kundenname bereinigen
        if lieferant:
            name = ""
        elif not any(w in name_norm for w in whitelist_set):
            # Entferne z. B. „25927 Giorgio Bellina T123456“ ⇒ „Giorgio Bellina“
            name_clean = re.split(r"\sK\d{6,}|\s[A-Z]\d{6,}", raw_name)[0].strip()
            name_clean = re.sub(r"^\d+\s+", "", name_clean)  # Entfernt führende Kundennummern jeder Länge
            name_clean = re.sub(r"\b\d{1,3}\b", "", name_clean).strip()
            name = re.sub(r"\s+", " ", name_clean)

            # Bewegungstoken interpretieren
            tokens = [
                str(row_dict.get("ein_mge", "")).strip(),
                str(row_dict.get("aus_mge", "")).strip(),
                "0",  # neutraler Platzhalter statt -3
                str(row_dict.get("bg_rez_nr", "")).strip()
            ]

            if any(t.startswith("Gesamt") for t in tokens):
                log_import(f"⛔ Footer-Zeile erkannt: {tokens}", level="debug")  # statt immer log_import()

            else:
                log_import(f"🔍 Tokens: {tokens}", level="debug")

                ein_raw, aus_raw, lager_raw, bg_token = tokens[-4:]

                try:
                    ein_val = int(ein_raw) if ein_raw.isdigit() else None
                    aus_val = int(aus_raw) if aus_raw.isdigit() else None
                except ValueError:
                    ein_val = aus_val = None

                # Bewegung interpretieren
                if ein_val and not aus_val:
                    log_import(f"🟢 Eingang erkannt: {ein_val}", level="debug")
                elif aus_val and not ein_val:
                   log_import(f"🔴 Ausgang erkannt: {aus_val}", level="debug")
                elif not ein_val and not aus_val:
                    log_import(f"⚪ Keine Bewegung erkannt. Möglicherweise Lager oder nur BG-Nr.: {bg_token}", level="debug")
                else:
                    log_import(f"⚠️ Ungültige Kombination: Ein={ein_raw}, Aus={aus_raw}, BG={bg_token}", level="debug")
            log_import(f"💬 Vor detect_bewegung: Tokens={tokens}")

            ein_mge = safe_int(row_dict.get("ein_mge"))
            aus_mge = safe_int(row_dict.get("aus_mge"))

            log_import(f"📦 Bewegung übernommen: Ein={ein_mge}, Aus={aus_mge}, dirty={dirty}", level="debug")

            ein_pack = aus_pack = 0
            if ein_mge:
                ein_pack = meta.get("packungsgroesse") or 1
            if aus_mge:
                aus_pack = meta.get("packungsgroesse") or 1

        # Zeile speichern
        parsed_rows.append({
            "lfdnr": row_dict["lfdnr"],
            "datum": row_dict["datum"],
            "name": name,
            "lieferant": lieferant,
            "ein_mge": ein_mge,
            "aus_mge": aus_mge,
            "ein_pack": ein_pack,
            "aus_pack": aus_pack,
            "bg_rez_nr": bg_rez_nr if re.fullmatch(r"\d+", str(bg_rez_nr).strip()) else "0",
            "liste": layout,
            "belegnummer": meta.get("belegnummer") or "Unbekannt",
            "artikel_bezeichnung": meta.get("artikel_bezeichnung") or "Unbekannt",
            "dirty": bool(dirty),
            "quelle": "pdf"
        })

    return pd.DataFrame(parsed_rows)

def run_import(parsed_df):
    if not isinstance(parsed_df, pd.DataFrame):
        log_import("❌ Fehler: Übergabe ist kein DataFrame")
        return
    if parsed_df.empty:
        log_import("⚠️ Keine gültigen Zeilen zum Import.")
        return

    # Falls fälschlich lfdnr mitkommt: raus damit
    if "lfdnr" in parsed_df.columns:
        parsed_df = parsed_df.drop(columns=["lfdnr"])

    with sqlite3.connect(DB_PATH) as conn:
        parsed_df.to_sql("bewegungen", conn, if_exists="append", index=False)
        log_import(f"✅ {len(parsed_df)} Zeilen erfolgreich in DB importiert.")



