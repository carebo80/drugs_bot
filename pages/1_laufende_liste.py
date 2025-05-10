import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode

DB_PATH = "data/laufende_liste.db"

# Dummy-Flag setzen für Trigger-Refresh
if "__reset_flag__" not in st.session_state:
    st.session_state["__reset_flag__"] = False

@st.cache_data
def lade_daten():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM bewegungen", conn)
    conn.close()
    return df

st.set_page_config(page_title="💊 Laufende Liste", layout="wide")
st.title("💊 Laufende Liste – Übersicht & Bearbeitung")

# 📄 Daten laden
df = lade_daten()
gesamt_anzahl = len(df)

# 💡 Datentypen bereinigen
df["eingang"] = pd.to_numeric(df["eingang"], errors="coerce")
df["ausgang"] = pd.to_numeric(df["ausgang"], errors="coerce")

# 📦 saldo_total: Live-Saldo pro Medikamentenname
gruppen_saldo = df.groupby("artikel_bezeichnung").agg({
    "eingang": "sum",
    "ausgang": "sum"
}).fillna(0)
gruppen_saldo["saldo_total"] = gruppen_saldo["eingang"] - gruppen_saldo["ausgang"]
df["total"] = df["eingang"] - df["ausgang"]

# 🔄 Daten neu laden
if st.sidebar.button("🔄 Laufende Liste neu laden"):
    lade_daten.clear()  # Cache löschen
    st.rerun()

# 🔁 Reset-Button
if st.sidebar.button("🔁 Alle Filter zurücksetzen"):
    st.session_state.clear()

# 🎛️ Sidebar-Filter
st.sidebar.header("🔍 Filter")

med_filter = st.sidebar.text_input("🔤 Medikament enthält...", value="", key="med_filter")
beleg_filter = st.sidebar.text_input("📄 Belegnummer enthält...", value="", key="beleg_filter")

name_filter = st.sidebar.selectbox("👤 Name", ["Alle"] + sorted(df["name"].dropna().unique()), key="name_filter")
vorname_filter = st.sidebar.selectbox("🧑 Vorname", ["Alle"] + sorted(df["vorname"].dropna().unique()), key="vorname_filter")
lieferant_filter = st.sidebar.selectbox("🏢 Lieferant", ["Alle"] + sorted(df["lieferant"].dropna().unique()), key="lieferant_filter")
liste_filter = st.sidebar.selectbox("📋 Liste", ["Alle"] + sorted(df["liste"].dropna().unique()), key="liste_filter")
quelle_filter = st.sidebar.selectbox("📦 Quelle", ["Alle", "excel", "pdf"], key="quelle_filter")

# Datum-Filter
datum_von = st.sidebar.date_input("📆 Von", value=st.session_state.get("datum_von", None), key="datum_von")
datum_bis = st.sidebar.date_input("📆 Bis", value=st.session_state.get("datum_bis", None), key="datum_bis")

# 🧼 Filter anwenden
if med_filter:
    df = df[df["artikel_bezeichnung"].str.contains(med_filter, case=False, na=False)]
if beleg_filter:
    df = df[df["belegnummer"].astype(str).str.contains(beleg_filter, na=False)]
if name_filter != "Alle":
    df = df[df["name"] == name_filter]
if vorname_filter != "Alle":
    df = df[df["vorname"] == vorname_filter]
if lieferant_filter != "Alle":
    df = df[df["lieferant"] == lieferant_filter]
if liste_filter != "Alle":
    df = df[df["liste"] == liste_filter]
if quelle_filter != "Alle":
    df = df[df["quelle"] == quelle_filter]
if datum_von:
    df = df[pd.to_datetime(df["datum"], errors='coerce') >= pd.to_datetime(datum_von)]
if datum_bis:
    df = df[pd.to_datetime(df["datum"], errors='coerce') <= pd.to_datetime(datum_bis)]

# 🔢 Pagination: Seitengröße und aktuelle Seite
page_size = 100
num_pages = max((len(df) - 1) // page_size + 1, 1)

# Init aktuelle Seite in Session-State
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# Sidebar: Seitennavigation
st.sidebar.markdown("### 📄 Seiten-Navigation")
col1, col2 = st.sidebar.columns([1, 1])
with col1:
    if st.button("⬅️ Zurück", use_container_width=True, disabled=st.session_state.current_page <= 1):
        st.session_state.current_page -= 1
with col2:
    if st.button("Weiter ➡️", use_container_width=True, disabled=st.session_state.current_page >= num_pages):
        st.session_state.current_page += 1

# Hinweis auf aktuelle Seite
st.sidebar.caption(f"Aktuelle Seite: {st.session_state.current_page} / {num_pages}")

# Slice DataFrame für aktuelle Seite
start_idx = (st.session_state.current_page - 1) * page_size
end_idx = start_idx + page_size
df_page = df.iloc[start_idx:end_idx]


# 🔢 Info zur Trefferanzahl
st.info(f"🔍 Zeige {len(df)} von {gesamt_anzahl} Gesamteinträgen")

# 📊 Tabelle anzeigen mit AgGrid
columns = [
    "belegnummer", "artikel_bezeichnung", "liste", "datum",
    "name", "vorname", "prirez", "lieferant", "ls_nummer",
    "ein_mge", "ein_pack", "eingang", "aus_mge", "aus_pack", "ausgang",
    "total", "quelle", "ks", "dirty"
]

anzeige_df = df_page[columns].copy()

from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode

gb = GridOptionsBuilder.from_dataframe(anzeige_df)
gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=100)
gb.configure_default_column(editable=True, resizable=True)
grid_options = gb.build()

st.subheader("📋 Daten-Tabelle")
response = AgGrid(
    anzeige_df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.MANUAL,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    height=800,
    use_container_width=True
)

# 📂 CSV Export nur sichtbare Daten
csv = anzeige_df.to_csv(index=False).encode("utf-8")
st.download_button("📂 Exportiere aktuelle Seite als CSV", data=csv, file_name="laufende_liste_export.csv", mime="text/csv")
