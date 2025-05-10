import streamlit as st
from pdf_to_sqlite_importer_dynamic import run_import  # Neue Version mit Liste-Erkennung
import os

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
            run_import(save_path)
            st.success("✅ Import abgeschlossen.")
        except Exception as e:
            st.error(f"❌ Fehler beim Import: {e}")

    # Zeige Logfile an
    if os.path.exists("tmp/import.log"):
        st.subheader("📝 Import-Log:")
        with open("tmp/import.log", encoding="utf-8") as log_file:
            st.text(log_file.read())
