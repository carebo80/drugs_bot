# 2_import_delta.py

import streamlit as st
import os
import traceback
from pdf_to_sqlite_importer_dynamic import main  # <-- nur main importieren
from utils.logger import get_log_path
from utils.env import get_env_var, validate_env

validate_env(["APP_ENV", "LOG_PATH"])

ENV = get_env_var("APP_ENV")
LOG_PATH = get_env_var("LOG_PATH")

st.set_page_config(page_title="📄 PDF-Import", layout="centered")
st.title("📄 PDF Upload & Datenbank-Import")

uploaded_file = st.file_uploader("Wähle eine PDF-Datei", type=["pdf"])

if uploaded_file is not None:
    filename = uploaded_file.name
    save_path = os.path.join("upload", filename)

    # Ordner sicherstellen
    os.makedirs("upload", exist_ok=True)

    # Datei speichern
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"✅ PDF gespeichert unter: `{save_path}`")

    with st.spinner("📦 Import läuft..."):
        try:
            # Nur noch 1 Aufruf nötig:
            main(save_path)

            st.success("✅ Import abgeschlossen.")

        except Exception as e:
            st.error(f"❌ Fehler beim Import: {e}")
            st.text(traceback.format_exc())

        # Letzte Log-Zeilen anzeigen
        with open(LOG_PATH, encoding="utf-8") as log_file:
            lines = log_file.readlines()
            last_lines = lines[-100:]
            st.text("".join(last_lines))
