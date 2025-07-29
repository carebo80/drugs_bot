# utils/extractor.py
import csv
import fitz
import re
from utils.helpers import normalize, detect_bewegung_from_structured_tokens, extract_article_info
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
            rows = re.split(r"(?=\d{5,}\s+\d{2}\.\d{2}\.\d{4})", block_text.replace("\n", " "))
            for zeile in rows:
                zeile = zeile.strip()
                if not re.match(r"^\d{5,}\s+\d{2}\.\d{2}\.\d{4}", zeile):
                    continue

                anzahl = 5 if layout == "a" else 4
                bewegung_tokens = zeile.split()[-anzahl:]
                bewegungsteil = " ".join(bewegung_tokens)
                kopfteil = zeile[:zeile.rfind(bewegungsteil)].strip()
                tokens = kopfteil.split() + bewegung_tokens

                if len(tokens) < 6:
                    continue

                lfdnr, datum = tokens[0], tokens[1]
                kundennr = tokens[2] if tokens[2].isdigit() else ""

                name_tokens = tokens[3:-anzahl]
                name_raw = " ".join(name_tokens)

                # Name bereinigen
                name_cleaned = re.sub(r"\b[NZJT]\d{6}\b", "", name_raw)
                name_cleaned = re.sub(r"\b[KREWUV]\d{6,8}\b", "", name_cleaned)
                name_cleaned = re.sub(r"\bDr\.?\b|\bProf\.?\b|\bArzt\b.*", "", name_cleaned, flags=re.IGNORECASE)
                name_cleaned = re.sub(r"(Zentrum|Praxis|Unbekannt.*|TUCARE|CLINICUM|KLINIK.*|SPITAL.*)", "", name_cleaned, flags=re.IGNORECASE)
                name_cleaned = re.sub(r"\s+", " ", name_cleaned).strip()

                name_parts = name_cleaned.split()
                vorname = name_parts[0] if len(name_parts) > 1 else ""
                nachname = name_parts[1] if len(name_parts) > 1 else (name_parts[0] if name_parts else "")
                name = nachname if vorname else name_cleaned

                normalized_name = normalize(name_cleaned)
                lieferant = ""
                for l in lieferanten_set:
                    if normalize(l) in normalized_name:
                        lieferant = l
                        break

                bg_rez_nr = ""
                dirty = False
                ein_mge, aus_mge, *_ = detect_bewegung_from_structured_tokens(tokens[-anzahl:], layout)

                if layout == "a" and len(tokens) >= 5:
                    candidate = tokens[-2]
                    if candidate.isdigit() and len(candidate) == 8:
                        bg_rez_nr = candidate

                if ein_mge == 0 and aus_mge == 0:
                    dirty = True

                log_import(f"🧪 Bewegungstokens: {tokens[-anzahl:]}")
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
