# pdf_to_sqlite_importer_dynamic.py
import csv
import fitz
import pandas as pd
import re
import sqlite3
from pathlib import Path
from utils.logger import get_log_path, log_import
from utils.env import get_env_var, validate_env
from utils.helpers import is_lieferant
from typing import List, Optional, Tuple, Dict, Any

ENV = get_env_var("APP_ENV")
LOG_PATH = get_env_var("LOG_PATH")

LIEFERANTEN_PATH = "data/lieferanten.csv"
WHITELIST_PATH = "data/whitelist.csv"
DB_PATH = "data/laufende_liste.db"

def normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())

def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def clean_name_and_bg_rez_nr(name: str, bg_rez_nr: str) -> tuple[str, str]:
    name_clean = re.sub(r"\b[NJT]\d{6}\b", "", name).strip()
    match = re.search(r"\b\d{8}\b", name_clean)
    if match:
        bg_rez_nr = match.group(0)
        name_clean = name_clean.replace(bg_rez_nr, "").strip()
    name_clean = re.sub(r"^\d+\s+", "", name_clean)
    name_clean = re.sub(r"\b\d{1,3}\b", "", name_clean).strip()
    name_clean = re.sub(r"\s+", " ", name_clean)
    return name_clean, bg_rez_nr
def clean_name_tokens(tokens: list[str]) -> list[str]:
    cleaned = []
    for token in tokens:
        if re.fullmatch(r"[A-Z]\d{6}", token):
            break
        cleaned.append(token)
    return cleaned

import re

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

    def is_valid_token(t):
        t_clean = t.strip()
        return t_clean == "" or re.fullmatch(r"\d+", t_clean)

    if not all(is_valid_token(t) for t in bewegung_tokens):
        return ("", bewegung_tokens, True)  # Dirty, weil z. B. Namen in Bewegungstokens

    name_tokens = tokens[:-bewegung_len]

    # Arztnummern entfernen (Z031031, T464901 usw.)
    name_tokens_cleaned = [t for t in name_tokens if not re.match(r"^[A-Z]\d{6,}$", t.strip())]

    if not name_tokens_cleaned:
        return ("", bewegung_tokens, True)

    name_str = " ".join(name_tokens_cleaned).strip()
    return (name_str, bewegung_tokens, False)

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

def detect_layout_from_page(page):
    return "a" if "BG Rez.Nr." in page.get_text("text") else "b"

def pre_fix_date(line: str) -> str:
    line = re.sub(r'(\d{2})\s*[\.\n]+\s*(\d{2})[\.\n]+(\d{4})', r'\1.\2.\3', line)
    return line

def slot_preserving_tokenizer_fixed(line: str) -> list[str]:
    log_import(f"\n🔍 Input-Zeile: {repr(line)}")
    if line.strip().lower().startswith("gesamt"):
        return []
    tokens = re.split(r'(\s+)', line)
    log_import(f"🎉 Tokens RAW: {tokens} (Anzahl: {len(tokens)})")
    return tokens

def detect_bewegung_from_structured_tokens(tokens: list[str], layout: str):
    ein_raw, aus_raw = "", ""
    ein_mge, aus_mge = 0, 0
    dirty = False
    bg_rez_nr = ""

    # Slotpositionen
    try:
        if layout == "a" and len(tokens) >= 12:
            ein_raw = tokens[-5]
            aus_raw = tokens[-4]
            bg_rez_nr = tokens[-2]
        elif layout == "b" and len(tokens) >= 11:
            ein_raw = tokens[-4]
            aus_raw = tokens[-3]
        else:
            dirty = True
    except Exception:
        dirty = True

    # Bewegung interpretieren
    try:
        if ein_raw and ein_raw.isdigit():
            ein_mge = int(ein_raw)
        if aus_raw and aus_raw.isdigit():
            aus_mge = int(aus_raw)
        if (ein_mge > 0 and aus_mge > 0) or (ein_mge == 0 and aus_mge == 0):
            dirty = True
    except Exception:
        dirty = True

    return ein_mge, aus_mge, bg_rez_nr, dirty

def split_multiple_rows(text):
    zeilen = []
    matches = re.finditer(r"\b\d{5,}\b\s+\d{2}\.\d{2}\.\d{4}", text)
    starts = [m.start() for m in matches]
    starts.append(len(text))
    for i in range(len(starts) - 1):
        chunk = text[starts[i]:starts[i+1]].strip()
        if chunk:
            zeilen.append(chunk)
    return zeilen

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
                bewegung_tokens = tokens[-5:] if layout == "a" else tokens[-4:]
                ein_mge, aus_mge, bg_rez_nr, dirty = detect_bewegung_from_structured_tokens(bewegung_tokens, layout)
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

def run_import(parsed_df):
    if not isinstance(parsed_df, pd.DataFrame):
        log_import("❌ Fehler: Übergabe ist kein DataFrame")
        return
    if parsed_df.empty:
        log_import("⚠️ Keine gültigen Zeilen zum Import.")
        return

    # Nur die Spalten übernehmen, die auch in der Datenbanktabelle existieren
    allowed_cols = [
        "datum", "name", "vorname", "lieferant",
        "ein_mge", "aus_mge", "bg_rez_nr",
        "artikel_bezeichnung", "belegnummer",
        "dirty", "liste", "quelle"
    ]

    df_clean = parsed_df[[col for col in allowed_cols if col in parsed_df.columns]]

    with sqlite3.connect(DB_PATH) as conn:
        df_clean.to_sql("bewegungen", conn, if_exists="append", index=False)
        log_import(f"✅ {len(df_clean)} Zeilen erfolgreich in DB importiert.")


