import streamlit as st
import os
import traceback
from pdf_to_sqlite_importer_dynamic import (
    extract_table_rows_with_article,
    parse_pdf_to_dataframe_dynamic_layout,
    run_import
)

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
            # 🔍 PDF analysieren → Zeilen extrahieren mit Artikel-Metadaten
            raw_rows = extract_table_rows_with_article(save_path)
            st.info(f"📄 {len(raw_rows)} Zeilen extrahiert.")

            # 🧠 Zeilen parsen inkl. Artikelinfo (Bezeichnung, Packungsgröße etc.)
            parsed_df = parse_pdf_to_dataframe_dynamic_layout(raw_rows)

            # 💾 In DB schreiben
            run_import(parsed_df)

            st.success("✅ Import abgeschlossen.")

        except Exception as e:
            st.error(f"❌ Fehler beim Import: {e}")
            st.text(traceback.format_exc())

    # 🔍 Logfile anzeigen
    if os.path.exists("tmp/import.log"):
        st.subheader("📝 Import-Log:")
        with open("tmp/import.log", encoding="utf-8") as log_file:
            st.text(log_file.read())
