# utils/extractor.py
import csv
import fitz
import re
from utils.helpers import normalize, detect_bewegung_from_structured_tokens
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

        # Artikelzeile
        artikel_bezeichnung, belegnummer, packungsgroesse = "", "", 1
        for line in text.splitlines():
            if "STK" in line and re.search(r"\d{5,}", line):
                artikel_bezeichnung = re.sub(r"\s*\d+\s*STK.*", "", line).strip()
                match = re.search(r"\b(\d{5,})\b", line)
                if match:
                    belegnummer = match.group(1)
                match_pg = re.search(r"(\d+)\s*STK", line)
                if match_pg:
                    packungsgroesse = int(match_pg.group(1))
                break

        for block in page.get_text("blocks"):
            block_text = block[4].strip()
            rows = re.split(r"(?=\d{5,}\s+\d{2}\.\d{2}\.\d{4})", block_text.replace("\n", " "))
            for zeile in rows:
                zeile = zeile.strip()
                if not re.match(r"^\d{5,}\s+\d{2}\.\d{2}\.\d{4}", zeile):
                    continue

                tokens = zeile.split()
                if len(tokens) < 6:
                    continue

                lfdnr, datum = tokens[0], tokens[1]
                kundennr = tokens[2] if tokens[2].isdigit() else ""

                arzt_index = -1
                for i, t in enumerate(tokens):
                    if re.fullmatch(r"[NZJT]\d{6}", t):
                        arzt_index = i
                        break

                name_tokens = tokens[3:arzt_index] if arzt_index != -1 else tokens[3:-5 if layout == "a" else -4]

                name_raw = " ".join(name_tokens)

                # Saubere Namensbereinigung
                name_cleaned = name_raw
                name_cleaned = re.sub(r"\b[NZJT]\d{6}\b", "", name_cleaned)  # Arztnummern
                name_cleaned = re.sub(r"\b[KREWUV]\d{6,8}\b", "", name_cleaned)  # weitere Codes (z.B. K241001)
                name_cleaned = re.sub(r"\bDr\.?\b|\bProf\.?\b|\bArzt\b.*", "", name_cleaned, flags=re.IGNORECASE)
                name_cleaned = re.sub(r"(Zentrum|Praxis|Unbekannt.*)", "", name_cleaned, flags=re.IGNORECASE)
                name_cleaned = re.sub(r"\s+", " ", name_cleaned).strip()

                name_parts = name_cleaned.split()
                vorname = name_parts[0] if len(name_parts) > 1 else ""
                nachname = " ".join(name_parts[1:]) if len(name_parts) > 1 else name_parts[0] if name_parts else ""
                name = nachname if vorname else name_cleaned

                name_normalized = normalize(name_cleaned)
                lieferant = name_cleaned if normalize(name_cleaned) in {normalize(l) for l in lieferanten_set} else ""

                bg_rez_nr = ""
                # Korrekte Extraktion der letzten Felder (stellenweise noch Rohwerte)
                bewegung_tokens = tokens[-5:] if layout == "a" else tokens[-4:]

                # Prüfen, ob die letzten 3–5 Felder wirklich nur aus Zahl oder leer bestehen
                bewegung_values = [t for t in bewegung_tokens if re.match(r'^-?\d+$', t) or t == '']

                # wenn nicht genau 3 (b) oder 4 (a) numerische Werte → dirty
                if (layout == "a" and len(bewegung_values) < 3) or (layout == "b" and len(bewegung_values) < 2):
                    dirty = True
                    ein_mge = aus_mge = 0
                else:
                    ein_mge, aus_mge, *_ = detect_bewegung_from_structured_tokens(bewegung_tokens, layout)

                ein_mge, aus_mge, bg_rez_nr, dirty = detect_bewegung_from_structured_tokens(bewegung_tokens, layout)
                
                log_import(f"🧪 Bewegungstokens: {bewegung_tokens}")
                log_import(f"🔎 Zeile {lfdnr} | Layout {layout} | Lieferant: {bool(lieferant)} | Ein_raw: '{ein_mge}' | Aus_raw: '{aus_mge}' → Ein: {ein_mge}, Aus: {aus_mge}, Dirty: {dirty}")
                log_import(f"📦 Tokens: {tokens}")

                if layout == "a" and len(bewegung_tokens) >= 4:
                    candidate = bewegung_tokens[-2]
                    if candidate.isdigit() and len(candidate) == 8:
                        bg_rez_nr = candidate

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

def extract_article_info(page):
    text = page.get_text("text")
    artikel_bezeichnung = ""
    belegnummer = ""
    packungsgroesse = 1
    for line in text.split("\n"):
        if "Medikament:" in line:
            # Entferne Prefix
            artikel_line = line.replace("Medikament:", "").strip()
            # Extrahiere Belegnummer
            match = re.search(r"\b(\d{4,8})\b", artikel_line)
            if match:
                belegnummer = match.group(1)
                artikel_line = artikel_line.replace(belegnummer, "").strip()
            artikel_bezeichnung = artikel_line
            # Extrahiere Packungsgröße
            pg_match = re.search(r"(\d+)\s*STK", artikel_line)
            if pg_match:
                packungsgroesse = int(pg_match.group(1))
            break
    return {
        "artikel_bezeichnung": artikel_bezeichnung,
        "belegnummer": belegnummer or "Unbekannt",
        "packungsgroesse": packungsgroesse
    }
