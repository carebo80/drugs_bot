import fitz
import pandas as pd
import re
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

def detect_bewegung(tokens):
    """
    Analysiert eine Liste von Tokens und erkennt Bewegungswerte.
    Gibt ein Tupel zurück: (ein_mge, aus_mge, dirty)
    """
    ein_mge = aus_mge = 0
    dirty = False

    for i in range(len(tokens) - 1, 1, -1):
        t1, t2, t3 = tokens[i - 2], tokens[i - 1], tokens[i]

        if re.fullmatch(r"\d+", t1) and t2.strip() == "" and re.fullmatch(r"\d+", t3):
            return int(t1), 0, False
        elif t1.strip() == "" and re.fullmatch(r"\d+", t2) and re.fullmatch(r"\d+", t3):
            return 0, int(t2), False
        elif re.fullmatch(r"\d+", t1) and re.fullmatch(r"\d+", t2):
            return 0, 0, True
        elif re.fullmatch(r"\d+", t1) and re.fullmatch(r"\d+", t3) and t2 == "0":
            return int(t1), 0, False
        elif t1 == "0" and re.fullmatch(r"\d+", t2) and re.fullmatch(r"\d+", t3):
            return 0, int(t2), False

    return 0, 0, True

def extract_table_rows_with_article(pdf_path):
    doc = fitz.open(pdf_path)
    all_rows = []

    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        lines = text.splitlines()
        meta = extract_article_info(page)
        layout = detect_layout_from_page(page)

        current_line_tokens = []
        rows = []

        for line in lines:
            tokens = line.strip().split()
            if not tokens:
                continue
            current_line_tokens.extend(tokens)

        i = 0
        while i < len(current_line_tokens) - 1:
            token = current_line_tokens[i]
            next_token = current_line_tokens[i + 1]

            if re.fullmatch(r"\d{5,}", token) and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", next_token):
                j = i + 2
                while j < len(current_line_tokens):
                    if (re.fullmatch(r"\d{5,}", current_line_tokens[j]) and
                        j + 1 < len(current_line_tokens) and
                        re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", current_line_tokens[j + 1])):
                        break
                    j += 1
                row_tokens = current_line_tokens[i:j]
                rows.append(row_tokens)
                i = j
            else:
                i += 1

        print(f"📄 Seite {page_num+1}: {len(rows)} Real-Rows erkannt.")

        for r in rows:
            if len(r) < 5:
                continue

            # Grundstruktur: Lfdnr + Datum + Name + Mengen + evtl. BG-Nr
            lfdnr = r[0]
            datum = r[1]
            remaining = r[2:]

            # Footer-Zeilen ausschließen (z. B. "Gesamt:" oder "Total")
            if any(tok.lower().startswith("gesamt") or tok.lower().startswith("total") for tok in remaining):
                print(f"⛔ Footer-Zeile erkannt: {remaining}")
                continue

            ein_mge = aus_mge = bg_rez_nr = ""
            tokens_used = 0

            # Rückwärtsanalyse: Mengen und ggf. BG-Nr extrahieren
            for i in range(1, min(4, len(remaining)) + 1):
                token = remaining[-i]
                if not bg_rez_nr and re.fullmatch(r"\d{6,}", token):
                    bg_rez_nr = token
                    tokens_used += 1
                elif not aus_mge and re.fullmatch(r"\d+", token):
                    aus_mge = token
                    tokens_used += 1
                elif not ein_mge and re.fullmatch(r"\d+", token):
                    ein_mge = token
                    tokens_used += 1

            name_tokens = remaining[:len(remaining) - tokens_used]
            name = " ".join(name_tokens)

            row_dict = {
                "lfdnr": lfdnr,
                "datum": datum,
                "name": name,
                "ein_mge": ein_mge,
                "aus_mge": aus_mge,
                "bg_rez_nr": bg_rez_nr if layout == "a" else ""
            }

            print(f"🔍 Tokens: {[name, ein_mge, aus_mge, bg_rez_nr]}")
            all_rows.append((row_dict, meta, layout, False))

    print(f"✅ Gesamt extrahierte Zeilen: {len(all_rows)}")
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
                "-3",  # simuliertes Lagerfeld, da du es im realen Token nicht brauchst, kannst du später ggf. dynamisch einsetzen
                str(row_dict.get("bg_rez_nr", "")).strip()
            ]

            if any(t.startswith("Gesamt") for t in tokens):
                print(f"⛔ Footer-Zeile erkannt: {tokens}")
            else:
                print(f"🔍 Tokens: {tokens}")

                ein_raw, aus_raw, lager_raw, bg_token = tokens[-4:]

                try:
                    ein_val = int(ein_raw) if ein_raw.isdigit() else None
                    aus_val = int(aus_raw) if aus_raw.isdigit() else None
                except ValueError:
                    ein_val = aus_val = None

                # Bewegung interpretieren
                if ein_val and not aus_val:
                    print(f"🟢 Eingang erkannt: {ein_val}")
                elif aus_val and not ein_val:
                    print(f"🔴 Ausgang erkannt: {aus_val}")
                elif not ein_val and not aus_val:
                    print(f"⚪ Keine Bewegung erkannt. Möglicherweise Lager oder nur BG-Nr.: {bg_token}")
                else:
                    print(f"⚠️ Ungültige Kombination: Ein={ein_raw}, Aus={aus_raw}, BG={bg_token}")


            ein_mge, aus_mge, dirty_m = detect_bewegung(tokens)
            dirty = dirty or dirty_m  # kombiniere mit externem dirty-Flag

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
        print("❌ Fehler: Übergabe ist kein DataFrame")
        return
    if parsed_df.empty:
        print("⚠️ Keine gültigen Zeilen zum Import.")
        return

    # Falls fälschlich lfdnr mitkommt: raus damit
    if "lfdnr" in parsed_df.columns:
        parsed_df = parsed_df.drop(columns=["lfdnr"])

    with sqlite3.connect(DB_PATH) as conn:
        parsed_df.to_sql("bewegungen", conn, if_exists="append", index=False)
        print(f"✅ {len(parsed_df)} Zeilen erfolgreich importiert.")
        log_import(f"✅ {len(parsed_df)} Zeilen erfolgreich in DB importiert.")



