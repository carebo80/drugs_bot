import pandas as pd
import re
from utils.helpers import detect_bewegung_from_structured_tokens

def is_valid_token(t):
    t_clean = t.strip()
    return t_clean == "" or re.fullmatch(r"\d+", t_clean)

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
def parse_pdf_to_dataframe_dynamic_layout(rows_with_meta):
    parsed_rows = []

    for row_dict, meta, layout, dirty_reason in rows_with_meta:
        tokens_raw = row_dict["tokens"]
        artikel_bezeichnung = meta.get("artikel_bezeichnung", "Unbekannt")
        belegnummer = meta.get("belegnummer", "Unbekannt")
        packungsgroesse = meta.get("packungsgroesse", 0)

        # Bewegungstokens = letzte 5/4 Slots
        movement_slots = 5 if layout == "a" else 4
        bewegung_tokens = tokens_raw[-movement_slots:]

        # Ein/Aus-Mengen & BG Rez.Nr. extrahieren
        ein_mge, aus_mge, bg_rez_nr, dirty_bewegung = detect_bewegung_from_structured_tokens(bewegung_tokens, layout)

        # Name & Bewegung nochmals prüfen
        name, bewegungstokens, dirty_name = split_name_and_bewegung(tokens_raw, layout)

        dirty = dirty_reason or dirty_bewegung or dirty_name

        row_dict.update({
            "ein_mge": ein_mge,
            "aus_mge": aus_mge,
            "bg_rez_nr": bg_rez_nr,
            "dirty": 1 if dirty else 0,
            "dirty_reason": dirty,
            "artikel_bezeichnung": artikel_bezeichnung,
            "belegnummer": belegnummer,
            "liste": layout
        })

        parsed_rows.append(row_dict)

    df = pd.DataFrame(parsed_rows)
    return df

def split_name_and_bewegung(tokens: list[str], layout: str) -> tuple[str, list[str], bool]:
    """
    Trennt Namens-Tokens von Bewegungstokens anhand Layout.
    Entfernt Arztnummern (z. B. Z031031) aus dem Namensteil.
    Nur gültig, wenn die letzten 5 (a) bzw. 4 (b) Tokens numerisch oder leer (\n etc.) sind.
    """
    bewegung_len = 5 if layout == "a" else 4

    if len(tokens) < bewegung_len:
        return ("", [], True)

    bewegung_tokens = tokens[-bewegung_len:]

    name_tokens = tokens[:-bewegung_len]

    # Arztnummern entfernen (Z031031, T464901 usw.)
    name_tokens_cleaned = [t for t in name_tokens if not re.match(r"^[A-Z]\d{6,}$", t.strip())]

    if not name_tokens_cleaned:
        return ("", bewegung_tokens, True)

    name_str = " ".join(name_tokens_cleaned).strip()
    return (name_str, bewegung_tokens, False)

def detect_layout_from_page(page):
    return "a" if "BG Rez.Nr." in page.get_text("text") else "b"