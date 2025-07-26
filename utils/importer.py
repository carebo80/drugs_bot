import sqlite3
import pandas as pd
from utils.logger import log_import
from utils.env import get_env_var

DB_PATH = get_env_var("DB_PATH", fallback="data/laufende_liste.db")

def run_import(parsed_df: pd.DataFrame):
    if not isinstance(parsed_df, pd.DataFrame):
        log_import("❌ Fehler: Übergabe ist kein DataFrame")
        return
    if parsed_df.empty:
        log_import("⚠️ Keine gültigen Zeilen zum Import.")
        return

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
