# pdf_to_sqlite_importer_dynamic.py

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

def clean_name_tokens(tokens: list[str]) -> list[str]:
    cleaned = []
    for token in tokens:
        if re.fullmatch(r"[A-Z]\d{6}", token):
            break
        cleaned.append(token)
    return cleaned

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
