import csv
import fitz
import re
from utils.logger import log_import
from utils.parser import detect_bewegung_from_structured_tokens
from utils.helpers import (
    normalize,
    slot_preserving_tokenizer_fixed,
    clean_tokens_layout_a,
    clean_trailing_empty_tokens,
    extract_article_info
)

def extract_table_rows_with_article(pdf_path: str):
    doc = fitz.open(pdf_path)
    all_rows = []

    # Lieferantenliste laden
    lieferanten_set = set()
    try:
        with open("data/lieferanten.csv", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    lieferanten_set.add(row[0].strip().upper())
    except Exception:
        pass

    for page in doc:
        text = page.get_text("text")
        layout = "a" if "BG Rez.Nr." in text else "b"

        # Artikel-Metadaten extrahieren
        artikel_bezeichnung, belegnummer, packungsgroesse = "", "", 1
        for line in text.splitlines():
            if re.search(r"(?i)^medikament:", line):
                log_import(f"🥚 Zeile MEDI: {line}")
                meta = extract_article_info(line)
                artikel_bezeichnung = meta["artikel_bezeichnung"]
                belegnummer = meta["belegnummer"]
                packungsgroesse = meta["packungsgroesse"]
                log_import(f"🥚 Artikel extrahiert: {artikel_bezeichnung}, PG: {packungsgroesse}, Beleg: {belegnummer}")
                break

        for block in page.get_text("blocks"):
            block_text = block[4].strip()
            rows = re.split(r"(?=\d{5,}\s+\d{2}\.\d{2}\.\d{4})", block_text)
            for zeile in rows:
                zeile = zeile.strip()
                if not re.match(r"^\d{5,}\s+\d{2}\.\d{2}\.\d{4}", zeile):
                    continue

                tokens_raw = slot_preserving_tokenizer_fixed(zeile, layout)
                tokens = clean_tokens_layout_a(tokens_raw) if layout == "a" else clean_trailing_empty_tokens(tokens_raw, 11)

                if tokens_raw != tokens:
                    log_import(f"🧼 Token cleanup: {tokens_raw} → {tokens}")

                if len(tokens) < 2:
                    continue

                if layout == "a":
                    if len(tokens) < 10:
                        log_import(f"⚠️ Zu wenige Tokens für Layout A: {len(tokens)}")
                        continue

                    bewegung_tokens = tokens[-5:]  # IMMER 5 letzte Tokens
                    kopf_tokens = tokens[:-5]
                else:  # Layout B
                    if len(tokens) < 9:
                        log_import(f"⚠️ Zu wenige Tokens für Layout B: {len(tokens)}")
                        continue

                    bewegung_tokens = tokens[-4:]  # IMMER 4 letzte Tokens
                    kopf_tokens = tokens[:-4]

                # Basisdaten extrahieren
                lfdnr = kopf_tokens[0] if len(kopf_tokens) > 0 else ""
                datum = kopf_tokens[1] if len(kopf_tokens) > 1 else ""

                # Lieferanten-Logik
                kundennr = kopf_tokens[2] if len(kopf_tokens) > 2 and kopf_tokens[2].isdigit() else ""
                lieferant_kandidat = kopf_tokens[2] if not kundennr else ""
                name_tokens = kopf_tokens[3:] if kundennr else kopf_tokens[3:] if len(kopf_tokens) > 3 else []

                name_cleaned = []
                for token in name_tokens:
                    if re.match(r"^[A-Z]\d{6,}$", token): break
                    if re.search(r"(DR\.?|PROF\.?|SPITAL|KLINIK|PRAXIS|ZENTRUM|TUCARE|UNBEKANNT)", token.upper()): break
                    name_cleaned.append(token)

                name_cleaned_str = " ".join(name_cleaned).strip()
                normalized = normalize(name_cleaned_str)
                lieferant = ""
                name = ""
                vorname = ""

                if normalize(lieferant_kandidat) in {normalize(l) for l in lieferanten_set}:
                    lieferant = lieferant_kandidat.strip()
                else:
                    for l in lieferanten_set:
                        if normalize(l) in normalized:
                            lieferant = l
                            break

                if not lieferant:
                    name_parts = name_cleaned_str.split()
                    vorname = name_parts[0] if len(name_parts) > 1 else ""
                    nachname = name_parts[1] if len(name_parts) > 1 else (name_parts[0] if name_parts else "")
                    name = nachname if vorname else name_cleaned_str

                # Bewegung erkennen
                try:
                    ein_mge, aus_mge, bg_rez_nr, dirty = detect_bewegung_from_structured_tokens(
                        bewegung_tokens, layout, is_lieferant=bool(lieferant)
                    )
                except Exception as e:
                    log_import(f"❌ Fehler Bewegung: {bewegung_tokens} → {e}")
                    ein_mge, aus_mge, bg_rez_nr, dirty = 0, 0, "", True

                log_import(f"🥚 Bewegungstokens: {bewegung_tokens}")
                log_import(f"🕎 Zeile {lfdnr} | Layout {layout} | Lieferant: {bool(lieferant)} | Ein_raw: '{ein_mge}' | Aus_raw: '{aus_mge}' → Ein: {ein_mge}, Aus: {aus_mge}, Dirty: {dirty}")
                log_import(f"📦 Tokens: {tokens}")

                row_dict = {
                    "lfdnr": lfdnr,
                    "datum": datum,
                    "name": name,
                    "vorname": vorname,
                    "lieferant": lieferant,
                    "ein_mge": ein_mge,
                    "aus_mge": aus_mge,
                    "bg_rez_nr": bg_rez_nr,
                    "artikel_bezeichnung": artikel_bezeichnung,
                    "belegnummer": belegnummer,
                    "tokens": tokens,
                    "liste": layout,
                    "dirty": 1 if dirty else 0,
                    "quelle": "pdf"
                }

                all_rows.append((row_dict, {
                    "artikel_bezeichnung": artikel_bezeichnung,
                    "belegnummer": belegnummer,
                    "packungsgroesse": packungsgroesse
                }, layout, dirty))

    return all_rows
