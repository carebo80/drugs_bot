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
                meta = extract_article_info(line)
                artikel_bezeichnung = meta["artikel_bezeichnung"]
                belegnummer = meta["belegnummer"]
                packungsgroesse = meta["packungsgroesse"]
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

                if len(tokens) < 2:
                    continue

                if layout == "a":
                    # Ab letzter Stelle rückwärts: so lange leere Tokens entfernen, bis bg_rez_nr erkennbar ist
                    tokens_cleaned = list(tokens)
                    while tokens_cleaned and tokens_cleaned[-1] == "":
                        tokens_cleaned.pop()

                    if len(tokens_cleaned) < 4:
                        log_import(f"❌ Zu wenige Tokens für Layout A nach Bereinigung: {tokens_cleaned}")
                        continue

                    bewegung_tokens = tokens_cleaned[-4:]  # ['ein', 'aus', 'lager', 'bg_rez_nr']
                    kopf_tokens = tokens[:len(tokens_cleaned) - 4]

                else:
                    bewegung_tokens = tokens[-4:]  # ['ein', 'aus', 'lager', '']
                    kopf_tokens = tokens[:-4]

                # Basisdaten
                lfdnr = kopf_tokens[0] if len(kopf_tokens) > 0 else ""
                datum = kopf_tokens[1] if len(kopf_tokens) > 1 else ""
                kundennr = kopf_tokens[2] if len(kopf_tokens) > 2 and kopf_tokens[2].isdigit() else ""

                lieferant = ""
                for idx, token in enumerate(kopf_tokens):
                    log_import(f"🔍 Kopf-Token {idx}: '{token}' | Normalisiert: '{normalize(token)}'")
                    if normalize(token) in {normalize(l) for l in lieferanten_set}:
                        lieferant = token.strip()
                        log_import(f"✅ MATCH mit Lieferant: '{lieferant}'")
                        break

                # 🧠 Namensfelder nur extrahieren wenn kein Lieferant
                name, vorname = "", ""
                if not lieferant:
                    name_tokens = kopf_tokens[3:] if kundennr else kopf_tokens[2:]
                    name_cleaned = []
                    for token in name_tokens:
                        if re.match(r"^[A-Z]\d{6,}$", token):  # Arztnummer z. B. Z031031
                            break
                        name_cleaned.append(token)
                    name_cleaned_str = " ".join(name_cleaned).strip()
                    name_parts = name_cleaned_str.split()
                    vorname = name_parts[0] if len(name_parts) > 1 else ""
                    nachname = name_parts[1] if len(name_parts) > 1 else (name_parts[0] if name_parts else "")
                    name = nachname if vorname else name_cleaned_str

                log_import(f"✅ Erkannt als Lieferant: '{lieferant}'") if lieferant else log_import(f"❌ Kein Lieferant erkannt. Name: '{name}'")

                # Bewegung erkennen
                try:
                    ein_mge, aus_mge, bg_rez_nr, dirty = detect_bewegung_from_structured_tokens(
                        bewegung_tokens, layout, is_lieferant=bool(lieferant)
                    )
                except Exception as e:
                    log_import(f"❌ Fehler Bewegung: {bewegung_tokens} → {e}")
                    ein_mge, aus_mge, bg_rez_nr, dirty = 0, 0, "", True

                ein_pack = packungsgroesse if ein_mge > 0 else 0
                aus_pack = packungsgroesse if aus_mge > 0 else 0

                row_dict = {
                    "lfdnr": lfdnr,
                    "datum": datum,
                    "name": name,
                    "vorname": vorname,
                    "lieferant": lieferant,
                    "ein_mge": ein_mge,
                    "aus_mge": aus_mge,
                    "ein_pack": ein_pack,
                    "aus_pack": aus_pack,
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
