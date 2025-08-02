# utils/helpers.py
import re
import csv
import unicodedata
from utils.logger import log_import
import os
from typing import List, Tuple

def get_env_var(key: str) -> str:
    return os.getenv(key, "")

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
    log_import(f"🔎 erkannte Bewegung: Ein: {ein}, Aus: {aus}")

    return 0, 0, True

def is_valid_bewegungsteil(tokens: list[str]) -> bool:
    """Prüft, ob die letzten Tokens von Layout A valide für Bewegungserkennung sind."""
    if len(tokens) != 5:
        return False
    try:
        # Ein/Aus/Lager: numerisch oder leer
        int(tokens[0]) if tokens[0] else None
        int(tokens[1]) if tokens[1] else None
        int(tokens[2]) if tokens[2] else None
        # BG Rez.Nr.: entweder leer oder 8-stellige Zahl
        if tokens[3] and not re.fullmatch(r"\d{8}", tokens[3]):
            return False
        # Abh: darf leer oder ein einzelnes Zeichen sein
        if tokens[4] and len(tokens[4].strip()) > 1:
            return False
        return True
    except Exception:
        return False

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
def slot_preserving_tokenizer_fixed(line: str, layout: str) -> list[str]:
    log_import(f"\n🔍 Input-Zeile: {repr(line)}")

    if line.strip().lower().startswith("gesamt"):
        return []

    tokens = [t.strip() for t in line.split("\n")]

    expected_len = 12 if layout == "a" else 11
    if len(tokens) < expected_len:
        tokens += [""] * (expected_len - len(tokens))
    elif len(tokens) > expected_len:
        tokens = tokens[:expected_len]

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

def detect_bewegung_from_structured_tokens(tokens: list[str], layout: str, is_lieferant: bool = False):
    """
    Erwartet Tokens:
    - Layout A: ['ein', 'aus', 'lager', 'bg_rez_nr']
    - Layout B: ['ein', 'aus', 'bg_rez_nr']
    """

    def is_valid_number(val):
        return val.strip().isdigit()

    # Entferne leere Tokens von hinten, bis bg_rez_nr sichtbar ist
    tokens_cleaned = tokens.copy()
    while tokens_cleaned and not is_valid_number(tokens_cleaned[-1]):
        tokens_cleaned.pop()

    if layout == "a":
        if len(tokens_cleaned) < 4:
            return 0, 0, "", True
        bewegung = tokens_cleaned[-4:]  # ['ein', 'aus', 'lager', 'bg_rez_nr']
        ein_raw, aus_raw, _, bg_rez_nr_raw = bewegung
        
    else:  # layout == "b"
        if len(tokens_cleaned) < 3:
            return 0, 0, "", True
        bewegung = tokens_cleaned[-3:]  # ['ein', 'aus', 'bg_rez_nr']
        ein_raw, aus_raw, _ = bewegung
        bg_rez_nr_raw = ""
        
    # Bewegung für Lieferanten (immer 'ein')
    if is_lieferant:
        ein_mge = int(ein_raw) if is_valid_number(ein_raw) else 0
        return ein_mge, 0, bg_rez_nr_raw if is_valid_number(bg_rez_nr_raw) else "", False

    # Normale Bewegung
    ein_mge = int(ein_raw) if is_valid_number(ein_raw) else 0
    aus_mge = int(aus_raw) if is_valid_number(aus_raw) else 0
    dirty = False

    # Plausibilitätscheck
    if ein_mge > 0 and aus_mge > 0:
        dirty = True  # Beides gleichzeitig ist ungültig

    bg_rez_nr = bg_rez_nr_raw if is_valid_number(bg_rez_nr_raw) else ""

    return ein_mge, aus_mge, bg_rez_nr, dirty

def clean_tokens_layout_a(tokens: list[str]) -> list[str]:
    """
    Entfernt überflüssige leere Tokens am Ende eines Layout-A-Eintrags,
    wobei das letzte relevante Token bg_rez_nr ist (eine Zahl oder '0').
    Alles danach (wie 'abh' oder '') wird abgeschnitten.
    """
    # Rückwärts durchgehen und ab dem letzten numerischen Token abschneiden
    for i in range(len(tokens)-1, -1, -1):
        if tokens[i].isdigit():
            return tokens[:i+1]  # inkl. bg_rez_nr, ohne leer/abh danach
    return tokens  # Fallback: nichts ändern
def clean_trailing_empty_tokens(tokens: list[str], expected_len: int) -> list[str]:
    """
    Entfernt leere Tokens am Ende der Liste, solange sie über der erwarteten Länge liegt.
    """
    while len(tokens) > expected_len and tokens[-1] == '':
        tokens = tokens[:-1]
    return tokens
