import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "data/laufende_liste.db"

st.set_page_config(page_title="📄 Delta-Abgleich", layout="wide")
st.title("📄 Excel–PDF Abgleich (Delta-Analyse)")

@st.cache_data
def lade_daten():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM bewegungen", conn)
    conn.close()
    return df

# 1. Daten laden und vorbereiten
df = lade_daten()
df_excel = df[df["quelle"] == "excel"].copy()
df_pdf = df[df["quelle"] == "pdf"].copy()

# 2. Vergleichsschlüssel definieren
keys = ["belegnummer", "datum", "name", "vorname", "artikel_bezeichnung"]

# 3. Merge mit Kennzeichnung
delta = df_excel.merge(df_pdf, on=keys, how="left", suffixes=("_excel", "_pdf"), indicator=True)

# 4. KS-Kennzeichnung setzen (nur für Excel-Zeilen relevant)
def berechne_ks(row):
    if row["_merge"] == "both":
        return "x"  # gefunden, identisch
    elif pd.notna(row.get("eingang_pdf")) or pd.notna(row.get("ausgang_pdf")):
        return "xx"  # gefunden + ergänzbar
    else:
        return ""  # kein PDF vorhanden

delta["ks"] = delta.apply(berechne_ks, axis=1)

# 5. Filter
df_filtered = delta.copy()

st.sidebar.markdown("### 🔍 Filter")
ks_filter = st.sidebar.selectbox("KS-Status (nur für Excel)", ["Alle", "", "x", "xx"], index=0)
if ks_filter != "Alle":
    df_filtered = df_filtered[df_filtered["ks"] == ks_filter]

# 6. Anzeige
st.caption("🔎 Hinweis: KS (Kontrollstatus) wird nur für Excel-Zeilen geführt. PDF-Zeilen bleiben davon unberührt.")
st.info(f"Zeige {len(df_filtered)} von {len(delta)} Einträgen")
st.dataframe(df_filtered[[*keys, "eingang_excel", "ausgang_excel", "eingang_pdf", "ausgang_pdf", "ks"]], use_container_width=True)

# 7. Werte übernehmen bei "xx"
if st.button("🟢 PDF-Werte übernehmen bei KS = 'xx'"):
    df_to_update = delta[delta["ks"] == "xx"]
    if not df_to_update.empty:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        updated_count = 0
        for _, row in df_to_update.iterrows():
            sql = """
                UPDATE bewegungen
                SET eingang = ?, ausgang = ?, ks = 'xx'
                WHERE quelle = 'excel' AND belegnummer = ? AND datum = ? AND name = ? AND vorname = ? AND artikel_bezeichnung = ?
            """
            cursor.execute(sql, (
                row.get("eingang_pdf"),
                row.get("ausgang_pdf"),
                row["belegnummer"],
                row["datum"],
                row["name"],
                row["vorname"],
                row["artikel_bezeichnung"]
            ))
            updated_count += 1
        conn.commit()
        conn.close()
        st.success(f"✅ {updated_count} Excel-Einträge aktualisiert (KS = 'xx').")
    else:
        st.info("ℹ️ Keine 'xx'-Einträge zum Aktualisieren gefunden.")

# 8. Option: PDF-Einträge mit KS = x löschen
if st.button("🗑️ PDF-Einträge mit KS = 'x' löschen"):
    df_to_delete = delta[delta["ks"] == "x"]
    if not df_to_delete.empty:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        deleted_count = 0
        for _, row in df_to_delete.iterrows():
            sql = """
                DELETE FROM bewegungen
                WHERE quelle = 'pdf' AND belegnummer = ? AND datum = ? AND name = ? AND vorname = ? AND artikel_bezeichnung = ?
            """
            cursor.execute(sql, (
                row["belegnummer"],
                row["datum"],
                row["name"],
                row["vorname"],
                row["artikel_bezeichnung"]
            ))
            deleted_count += 1
        conn.commit()
        conn.close()
        st.success(f"🗑️ {deleted_count} PDF-Einträge gelöscht (KS = 'x').")
    else:
        st.info("ℹ️ Keine 'x'-PDF-Einträge gefunden.")
