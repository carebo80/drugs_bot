# utils/helpers.py
import re
import csv
import unicodedata
from utils.logger import log_import
import os

def get_env_var(key: str) -> str:
    return os.getenv(key, "")

from utils.env import get_env_var
import csv

def is_lieferant(name: str) -> bool:
    lieferanten_path = get_env_var("LIEFERANTEN_PATH")
    print(f"📦 LIEFERANTEN (helpers.py): {lieferanten_path}")  # Debug
    if not lieferanten_path:
        raise FileNotFoundError("❌ LIEFERANTEN_PATH wurde nicht aus .env geladen.")
    with open(lieferanten_path, newline='', encoding="utf-8") as f:
        reader = csv.reader(f)
        return any(name.strip().lower() == row[0].strip().lower() for row in reader if row)

def detect_bewegung(ein_raw: str, aus_raw: str, lieferant: str):
    dirty = False
    try:
        ein = int(ein_raw) if ein_raw.isdigit() else 0
        aus = int(aus_raw) if aus_raw.isdigit() else 0
    except Exception:
        return 0, 0, True

    if lieferant:
        return ein, 0, False
    if ein and not aus:
        return ein, 0, False
    if aus and not ein:
        return 0, aus, False
    return 0, 0, True

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

def slot_preserving_tokenizer_fixed(line: str) -> list[str]:
    log_import(f"\n🔍 Input-Zeile: {repr(line)}")
    if line.strip().lower().startswith("gesamt"):
        return []
    tokens = re.split(r'(\s+)', line)
    log_import(f"🎉 Tokens RAW: {tokens} (Anzahl: {len(tokens)})")
    return tokens

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
def pre_fix_date(line: str) -> str:
    line = re.sub(r'(\d{2})\s*[\.\n]+\s*(\d{2})[\.\n]+(\d{4})', r'\1.\2.\3', line)
    return line

def clean_name_tokens(tokens: list[str]) -> list[str]:
    cleaned = []
    for token in tokens:
        if re.fullmatch(r"[A-Z]\d{6}", token):
            break
        cleaned.append(token)
    return cleaned

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.strip().split())

def extract_article_info(line: str) -> dict:
    # Entferne "Medikament:" (case-insensitive)
    line_clean = re.sub(r"(?i)^medikament:\s*", "", line).strip()
    # Finde erste Belegnummer (6–8 Ziffern)
    belegnummer_match = re.search(r"\b\d{6,8}\b", line_clean)
    belegnummer = belegnummer_match.group(0) if belegnummer_match else ""

    # Entferne belegnummer aus Zeile (nur erste Instanz)
    artikeltext = line_clean
    if belegnummer:
        artikeltext = line_clean.replace(belegnummer, "", 1).strip()

    # Packungsgröße (z. B. "30 STK")
    packung_match = re.search(r"(\d+)\s*STK", artikeltext.upper())
    packungsgroesse = int(packung_match.group(1)) if packung_match else 0

    return {
        "artikel_bezeichnung": artikeltext,
        "packungsgroesse": packungsgroesse,
        "belegnummer": belegnummer
    }

def detect_bewegung_from_structured_tokens(tokens: list[str], layout: str):
    """
    Erwartet:
    - Layout A: [..., ein, aus, lager, bg_rez_nr, abh]
    - Layout B: [..., ein, aus, lager, abh]
    """

    ein_mge = aus_mge = 0
    bg_rez_nr = ""
    dirty = False

    try:
        if layout == "a" and len(tokens) >= 5:
            ein_raw = tokens[-5]
            aus_raw = tokens[-4]
            bg_rez_candidate = tokens[-2]

        elif layout == "b" and len(tokens) >= 4:
            ein_raw = tokens[-4]
            aus_raw = tokens[-3]
            bg_rez_candidate = ""

        else:
            return 0, 0, "", True  # nicht genug Tokens → dirty

        # Prüfe und konvertiere Ein/Aus-Werte
        ein_mge = int(ein_raw) if ein_raw.strip().isdigit() else 0
        aus_mge = int(aus_raw) if aus_raw.strip().isdigit() else 0

        # bg_rez_nr: Nur bei Layout A und nur wenn 8-stellig numerisch
        if layout == "a" and re.fullmatch(r"\d{8}", bg_rez_candidate):
            bg_rez_nr = bg_rez_candidate

        # Validierungslogik:
        # - nur einer von beiden (ein/aus) darf > 0 sein
        # - beide 0 oder beide > 0 → dirty
        if (ein_mge > 0 and aus_mge > 0) or (ein_mge == 0 and aus_mge == 0):
            dirty = True

    except Exception:
        dirty = True
        ein_mge = aus_mge = 0
        bg_rez_nr = ""

    return ein_mge, aus_mge, bg_rez_nr, dirty