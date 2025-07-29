# utils/extractor.py (komplett mit Slotstruktur – stabiler Import)
import csv
import fitz
import re
from utils.helpers import normalize, detect_bewegung_from_structured_tokens, extract_article_info, slot_preserving_tokenizer_fixed
from utils.logger import log_import

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
        anzahl = 5 if layout == "a" else 4

        # Artikelzeile extrahieren
        artikel_bezeichnung, belegnummer, packungsgroesse = "", "", 1
        for line in text.splitlines():
            if re.search(r"(?i)^medikament:", line):
                log_import(f"🧪 Zeile MEDI: {line}")
                meta = extract_article_info(line)
                artikel_bezeichnung = meta["artikel_bezeichnung"]
                packungsgroesse = meta["packungsgroesse"]
                belegnummer = meta["belegnummer"]
                log_import(f"🧪 Artikel extrahiert: {artikel_bezeichnung}, PG: {packungsgroesse}, Beleg: {belegnummer}")
                break

        for block in page.get_text("blocks"):
            block_text = block[4].strip()
            rows = re.split(r"(?=\d{5,}\s+\d{2}\.\d{2}\.\d{4})", block_text)
            for zeile in rows:
                zeile = zeile.strip()
                if not re.match(r"^\d{5,}\s+\d{2}\.\d{2}\.\d{4}", zeile):
                    continue

                tokens = slot_preserving_tokenizer_fixed(zeile, layout)
                if not tokens or len(tokens) < (3 + anzahl):
                    continue

                bewegung_tokens = tokens[-anzahl:]
                kopf_tokens = tokens[:-anzahl]
                if len(kopf_tokens) < 3:
                    continue

                lfdnr, datum = kopf_tokens[0], kopf_tokens[1]
                kundennr = kopf_tokens[2] if kopf_tokens[2].isdigit() else ""

                name_tokens = kopf_tokens[3:]
                name_cleaned = []
                arzt_trigger = ["DR.", "PROF.", "ARZT", "ÄRZTIN", "ZENTRUM", "PRAXIS", "SPITAL", "KLINIK", "TUCARE", "CLINICUM", "UNBEKANNT"]
                for token in name_tokens:
                    if re.match(r"^[A-Z]\d{6,}$", token):  # Arztnummer
                        break
                    if token.upper() in arzt_trigger:
                        break
                    name_cleaned.append(token)

                name_cleaned_str = " ".join(name_cleaned)
                name_parts = name_cleaned_str.split()
                vorname = name_parts[0] if len(name_parts) > 1 else ""
                nachname = name_parts[1] if len(name_parts) > 1 else (name_parts[0] if name_parts else "")
                name = nachname if vorname else name_cleaned_str

                # Lieferantenerkennung
                lieferant = ""
                normalized = normalize(name_cleaned_str)
                for l in lieferanten_set:
                    if normalize(l) in normalized:
                        lieferant = l
                        name = ""
                        vorname = ""
                        break

                # Bewegung und BG-Rez-Nr erkennen
                try:
                    ein_mge, aus_mge, bg_rez_nr, dirty = detect_bewegung_from_structured_tokens(bewegung_tokens, layout)
                except Exception as e:
                    log_import(f"❌ Fehler Bewegung: {bewegung_tokens} → {e}")
                    ein_mge, aus_mge, bg_rez_nr = 0, 0, ""
                    dirty = True


                log_import(f"🧪 Bewegungstokens: {bewegung_tokens}")
                log_import(f"🔎 Zeile {lfdnr} | Layout {layout} | Lieferant: {bool(lieferant)} | Ein_raw: '{ein_mge}' | Aus_raw: '{aus_mge}' → Ein: {ein_mge}, Aus: {aus_mge}, Dirty: {dirty}")
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