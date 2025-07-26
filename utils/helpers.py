# utils/helpers.py
import re
import csv
import unicodedata
from utils.logger import log_import

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
