import streamlit as st
import sqlite3
import pandas as pd
import logging
import os
import re

DB_PATH = "data/laufende_liste.db"
LOG_PATH = "logs/delta.log"
EXPORT_PATH = "logs/x_candidates_export.csv"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# Logging initialisieren
logging.basicConfig(
    filename=LOG_PATH,
    filemode="a",
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)

st.set_page_config(page_title="📄 Delta-Abgleich", layout="wide")
st.title("📄 Excel–PDF Abgleich (Delta-Analyse)")

@st.cache_data
def lade_daten():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM bewegungen", conn)
    conn.close()
    return df

df = lade_daten()

# UI: Parameter
st.markdown("### ⚙️ Parameter")

liste_wahl = st.selectbox("📁 Welche Liste aus Excel prüfen?", options=["alle"] + sorted(df[df["quelle"] == "excel"]["liste"].dropna().unique().tolist()), index=0)
simulate = st.checkbox("🔧 Nur simulieren (keine Änderungen an DB)", value=True)

# Vorverarbeitung
df_excel = df[df["quelle"] == "excel"].copy()
df_pdf = df[df["quelle"] == "pdf"].copy()

if liste_wahl != "alle":
    df_excel = df_excel[df_excel["liste"] == liste_wahl]

def name_token(n):
    return str(n).strip().split(" ")[0].lower()

def normalize_artikel(s):
    return re.sub(r"\s+", " ", str(s).lower()).strip()

df_excel["name_token"] = df_excel["name"].apply(name_token)
df_pdf["name_token"] = df_pdf["name"].apply(name_token)
df_excel["artikel_norm"] = df_excel["artikel_bezeichnung"].apply(normalize_artikel)
df_pdf["artikel_norm"] = df_pdf["artikel_bezeichnung"].apply(normalize_artikel)

# Lieferanten berücksichtigen
df_excel["lieferant"] = df_excel["lieferant"].fillna("").str.lower().str.strip()
df_pdf["lieferant"] = df_pdf["lieferant"].fillna("").str.lower().str.strip()

keys = ["belegnummer", "datum", "name_token", "artikel_norm", "lieferant"]

df_delta = df_excel.merge(df_pdf, on=keys, how="left", suffixes=("_excel", "_pdf"), indicator=True)

# delta_detail (optionale Spalte mit Feldunterschieden)
def berechne_delta_detail(row):
    diffs = []
    for f in ["ein_mge", "aus_mge", "ein_pack", "aus_pack", "lager", "bg", "rez_nr"]:
        if row.get(f + "_excel") != row.get(f + "_pdf"):
            diffs.append(f)
    return ", ".join(diffs)

df_delta["delta_detail"] = df_delta.apply(berechne_delta_detail, axis=1)

# Kontrollstatus berechnen
def berechne_ks(row):
    if row["_merge"] != "both":
        return ""
    menge_excel = (row["ein_mge_excel"], row["aus_mge_excel"])
    menge_pdf   = (row["ein_mge_pdf"],   row["aus_mge_pdf"])
    if menge_excel == menge_pdf:
        return "x"
    elif pd.notna(row["ein_mge_pdf"]) or pd.notna(row["aus_mge_pdf"]):
        return "xx"
    else:
        return ""

df_delta["ks"] = df_delta.apply(berechne_ks, axis=1)

# Übersicht anzeigen
anz_x = (df_delta["ks"] == "x").sum()
anz_xx = (df_delta["ks"] == "xx").sum()
anz_none = (df_delta["ks"] == "").sum()

st.markdown(f"🔢 **Statusübersicht:** `xx`: {anz_xx} | `x`: {anz_x} | leer: {anz_none}")

anzeige_spalten = ["belegnummer", "datum", "name_token", "artikel_norm", "lieferant", "ein_mge_excel", "ein_mge_pdf", "aus_mge_excel", "aus_mge_pdf", "ks", "delta_detail"]

def highlight_differences(row):
    styles = []
    for col in anzeige_spalten:
        if col == "ein_mge_excel" and row["ein_mge_excel"] != row["ein_mge_pdf"]:
            styles.append("background-color: #ffcccb")
        elif col == "aus_mge_excel" and row["aus_mge_excel"] != row["aus_mge_pdf"]:
            styles.append("background-color: #ffcccb")
        else:
            styles.append("")
    return styles

# Pagination
st.markdown("### 📊 Delta-Vergleich")
page_size = 20
total_rows = len(df_delta)
total_pages = (total_rows - 1) // page_size + 1
page = st.number_input("📄 Seite wählen", min_value=1, max_value=max(1, total_pages), value=1, step=1)
start = (page - 1) * page_size
end = start + page_size
df_page = df_delta.iloc[start:end]

st.markdown("💡 Unterschiede in Mengen sind farbig markiert.")
styled_df = df_page[anzeige_spalten].style.apply(highlight_differences, axis=1)
st.dataframe(styled_df, use_container_width=True)

# Delta-Abgleich durchführen
if st.button("🚀 Delta-Abgleich durchführen"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    updated, deleted = 0, 0
    x_candidates = []

    for _, row in df_delta.iterrows():
        status = row["ks"]
        if status == "xx":
            log_msg = f"XX: Ergänze → {row['belegnummer']} | {row['datum']} | {row['name_excel']} | {row['artikel_bezeichnung_excel']} | delta: {row['delta_detail']}"
            if not simulate:
                cursor.execute("""
                    UPDATE bewegungen
                    SET ein_mge = ?, aus_mge = ?, ein_pack = ?, aus_pack = ?, ks = 'xx'
                    WHERE quelle = 'excel' AND belegnummer = ? AND datum = ? AND name = ? AND vorname = ? AND artikel_bezeichnung = ?
                """, (
                    row["ein_mge_pdf"], row["aus_mge_pdf"],
                    row["ein_pack_pdf"], row["aus_pack_pdf"],
                    row["belegnummer"], row["datum"], row["name_excel"], row["vorname_excel"], row["artikel_bezeichnung_excel"]
                ))
                logging.info(log_msg + " → ✅ committed")
            else:
                logging.info(log_msg + " → 🔍 simulation")
            updated += 1

        elif status == "x":
            x_candidates.append(row)
            log_msg = f"X: Lösche → {row['belegnummer']} | {row['datum']} | {row['name_pdf']} | {row['artikel_bezeichnung_pdf']}"
            if not simulate:
                cursor.execute("""
                    DELETE FROM bewegungen
                    WHERE quelle = 'pdf' AND belegnummer = ? AND datum = ? AND name = ? AND vorname = ? AND artikel_bezeichnung = ?
                """, (
                    row["belegnummer"], row["datum"], row["name_pdf"], row["vorname_pdf"], row["artikel_bezeichnung_pdf"]
                ))
                logging.info(log_msg + " → ✅ committed")
            else:
                logging.info(log_msg + " → 🔍 simulation")
            deleted += 1

        else:
            log_msg = f"--: Kein Match → {row['belegnummer']} | {row['datum']} | {row['name_excel']} | {row['artikel_bezeichnung_excel']}"
            logging.info(log_msg)

    if not simulate:
        conn.commit()
        st.success(f"✅ {updated} ergänzt (xx), {deleted} gelöscht (x)")
        logging.info(f"🔁 Delta-Abgleich durchgeführt (real): {updated} ergänzt, {deleted} gelöscht")
    else:
        st.info(f"🔍 Simulation: {updated} würden ergänzt (xx), {deleted} würden gelöscht (x)")
        logging.info(f"🔁 Delta-Abgleich simuliert: {updated} ergänzt, {deleted} gelöscht")

    if x_candidates:
        df_x = pd.DataFrame(x_candidates)
        df_x.to_csv(EXPORT_PATH, index=False)
        st.download_button("⬇️ CSV aller 'x'-Kandidaten herunterladen", data=df_x.to_csv(index=False), file_name="x_candidates.csv", mime="text/csv")

    conn.close()

# 🔍 Log-Anzeige
st.markdown("---")
st.markdown("### 📝 Delta-Log anzeigen")
if os.path.exists(LOG_PATH):
    with open(LOG_PATH, "r") as log_file:
        log_lines = log_file.readlines()[-100:]  # letzte 100 Zeilen
        st.text_area("📄 Logauszug", value="".join(log_lines), height=300)
    if st.button("🧹 Logdatei löschen"):
        os.remove(LOG_PATH)
        st.success("🗑️ Logdatei gelöscht.")
else:
    st.info("ℹ️ Noch keine Logdatei vorhanden.")