import streamlit as st
from pdf_to_sqlite_importer_dynamic import run_import, parse_pdf_to_dataframe_dynamic_layout
from analyze_pdf_blocks import extract_table_rows  # oder wie auch immer deine Extraktionsfunktion heißt
import os
from analyze_pdf_blocks import extract_table_rows
from pdf_to_sqlite_importer_dynamic import parse_pdf_to_dataframe_dynamic_layout, run_import
import pandas as pd

st.set_page_config(page_title="📄 PDF-Import", layout="centered")
st.title("📄 PDF Upload & Datenbank-Import")

uploaded_file = st.file_uploader("Wähle eine PDF-Datei", type=["pdf"])

if uploaded_file is not None:
    filename = uploaded_file.name
    save_path = os.path.join("upload", filename)
    os.makedirs("upload", exist_ok=True)

    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"✅ PDF gespeichert unter: `{save_path}`")

    with st.spinner("📦 Import läuft..."):
        try:
            # 1. PDF einlesen und Zeilen extrahieren
            pdf_rows = extract_table_rows(save_path)
            st.info(f"📄 {len(pdf_rows)} Zeilen extrahiert.")

            # 2. Zeilen zu DataFrame parsen
            df = parse_pdf_to_dataframe_dynamic_layout(pdf_rows)

            if isinstance(df, pd.DataFrame):
                st.success(f"✅ {len(df)} gültige Zeilen erkannt.")
                st.dataframe(df.head())  # optional Vorschau
                run_import(df)
                st.success("✅ Import abgeschlossen.")
            else:
                st.error("❌ Fehler beim Parsen: Kein DataFrame zurückgegeben.")
                st.text(df)  # falls df z. B. ein Fehlerstring war

        except Exception as e:
            st.error(f"❌ Fehler beim Import: {e}")

    # Zeige Logfile an (optional)
    if os.path.exists("tmp/import.log"):
        st.subheader("📝 Import-Log:")
        with open("tmp/import.log", encoding="utf-8") as log_file:
            st.text(log_file.read())
