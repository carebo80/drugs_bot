# pdf_to_sqlite_importer_dynamic.py

from utils.extractor import extract_table_rows_with_article
from utils.parser import parse_pdf_to_dataframe_dynamic_layout
from utils.importer import run_import
from utils.logger import log_import

def main(pdf_path: str):
    try:
        log_import(f"🚀 Import gestartet für: {pdf_path}")
        raw_rows = extract_table_rows_with_article(pdf_path)
        parsed_df = parse_pdf_to_dataframe_dynamic_layout(raw_rows)
        run_import(parsed_df)
        log_import("🏁 Import abgeschlossen.")
    except Exception as e:
        log_import(f"❌ Fehler beim Import: {e}")
        raise
