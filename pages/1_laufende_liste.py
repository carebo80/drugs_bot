import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode
from filter_utils import filter_dataframe
from ui_components import sicherheitsdialog

DB_PATH = "data/laufende_liste.db"

@st.cache_data
def lade_daten():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM bewegungen", conn)
    conn.close()
    return df

st.set_page_config(page_title="💊 Laufende Liste", layout="wide")
st.title("💊 Laufende Liste – Übersicht & Bearbeitung")

if st.sidebar.button("🔄 Laufende Liste neu laden"):
    lade_daten.clear()
    st.session_state["dataframe"] = filter_dataframe(lade_daten())
    st.rerun()

if st.sidebar.button("🔁 Alle Filter zurücksetzen"):
    for key in list(st.session_state.keys()):
        if key.startswith("form_") or key.endswith("_filter") or key.startswith("datum_"):
            del st.session_state[key]
    st.rerun()

# Sidebar Filter-Eingaben
st.sidebar.header("🔍 Filter")

med_filter = st.sidebar.text_input("🔤 Medikament enthält...", value=st.session_state.get("med_filter", ""), key="med_filter")
beleg_filter = st.sidebar.text_input("📄 Belegnummer enthält...", value=st.session_state.get("beleg_filter", ""), key="beleg_filter")

# Für selectboxen nur bei geladenem DataFrame
temp_df = lade_daten()
name_filter = st.sidebar.selectbox("👤 Name", ["Alle"] + sorted(temp_df["name"].dropna().unique()), key="name_filter")
vorname_filter = st.sidebar.selectbox("🧑 Vorname", ["Alle"] + sorted(temp_df["vorname"].dropna().unique()), key="vorname_filter")
lieferant_filter = st.sidebar.selectbox("🏢 Lieferant", ["Alle"] + sorted(temp_df["lieferant"].dropna().unique()), key="lieferant_filter")
liste_filter = st.sidebar.selectbox("📋 Liste", ["Alle"] + sorted(temp_df["liste"].dropna().unique()), key="liste_filter")
quelle_filter = st.sidebar.selectbox("📦 Quelle", ["Alle", "excel", "pdf", "manuell"], key="quelle_filter")
dirty_filter = st.sidebar.selectbox("🧪 Dirty", ["Alle", "Ja", "Nein"], key="dirty_filter")
datum_von = st.sidebar.date_input("📆 Von", value=st.session_state.get("datum_von", None), key="datum_von")
datum_bis = st.sidebar.date_input("📆 Bis", value=st.session_state.get("datum_bis", None), key="datum_bis")

df = filter_dataframe(temp_df)

# Tabelle vorbereiten
columns = [
    "id", "belegnummer", "artikel_bezeichnung", "liste", "datum",
    "name", "vorname", "prirez", "lieferant", "ls_nummer",
    "ein_mge", "ein_pack", "eingang", "aus_mge", "aus_pack", "ausgang",
    "total", "quelle", "ks", "dirty"
]

# Aktionen
st.subheader("🔹 Aktionen")
col1, col2, col3 = st.columns(3)
with col1:
    if "selected_row" in st.session_state and st.session_state["selected_row"] is not None:
        if st.button("✅ Zeile duplizieren"):
            def dupliziere():
                row = st.session_state["selected_row"].copy()
                row["id"] = None
                row["dirty"] = True
                row["quelle"] = "manuell"
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cols = ", ".join([k for k in row if k != "id"])
                placeholders = ", ".join(["?"] * len([k for k in row if k != "id"]))
                sql = f"INSERT INTO bewegungen ({cols}) VALUES ({placeholders})"
                cursor.execute(sql, tuple(row[k] for k in row if k != "id"))
                conn.commit()
                conn.close()
                st.success("✅ Zeile dupliziert.")
                lade_daten.clear()
                st.session_state["dataframe"] = filter_dataframe(lade_daten())
            sicherheitsdialog("Duplizieren", "✅ Ja, duplizieren", dupliziere)
    else:
        st.warning("⚠️ Bitte zuerst eine Zeile auswählen.")

with col2:
    if "selected_row" in st.session_state and st.session_state["selected_row"] is not None:
        if st.button("❌ Zeile löschen"):
            def loeschen():
                row = st.session_state["selected_row"]
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM bewegungen WHERE id = ?", (row["id"],))
                conn.commit()
                conn.close()
                st.success("🗑️ Zeile gelöscht.")
                lade_daten.clear()
                st.session_state["dataframe"] = filter_dataframe(lade_daten())
            sicherheitsdialog("Löschen", "❌ Ja, löschen", loeschen)
    else:
        st.warning("⚠️ Bitte zuerst eine Zeile auswählen.")

with col3:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📂 Export als CSV", data=csv, file_name="laufende_liste_export.csv", mime="text/csv")

# Eingabemaske
st.subheader("📝 Eingabemaske")
neue_zeile = {}
col1, col2, col3 = st.columns(3)
with col1:
    neue_zeile["artikel_bezeichnung"] = st.text_input("Artikel", key="form_neu_artikel_bezeichnung")
    neue_zeile["belegnummer"] = st.text_input("Belegnummer", key="form_neu_belegnummer")
    neue_zeile["liste"] = st.text_input("Liste", key="form_neu_liste")
with col2:
    neue_zeile["datum"] = st.text_input("Datum", key="form_neu_datum")
    neue_zeile["name"] = st.text_input("Name", key="form_neu_name")
    neue_zeile["vorname"] = st.text_input("Vorname", key="form_neu_vorname")
with col3:
    neue_zeile["lieferant"] = st.text_input("Lieferant", key="form_neu_lieferant")
    neue_zeile["quelle"] = st.text_input("Quelle", value="manuell", key="form_neu_quelle")
    neue_zeile["dirty"] = st.checkbox("Dirty", value=True, key="form_neu_dirty")

if st.button("➕ Zeile speichern"):
    def speichern():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        jetzt = pd.Timestamp.now().isoformat()
        sql = f"""
            INSERT INTO bewegungen (artikel_bezeichnung, belegnummer, liste, datum, name, vorname, lieferant, quelle, dirty, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        daten = (
            neue_zeile["artikel_bezeichnung"], neue_zeile["belegnummer"], neue_zeile["liste"], neue_zeile["datum"],
            neue_zeile["name"], neue_zeile["vorname"], neue_zeile["lieferant"], neue_zeile["quelle"], neue_zeile["dirty"],
            jetzt, jetzt
        )
        cursor.execute(sql, daten)
        conn.commit()
        conn.close()
        st.success("✅ Neue Zeile gespeichert.")
        lade_daten.clear()
        st.session_state["dataframe"] = filter_dataframe(lade_daten())
    sicherheitsdialog("Speichern", "💾 Ja, speichern", speichern)

# Tabelle
st.subheader("📋 Daten-Tabelle")
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_column("id", editable=False)
gb.configure_default_column(editable=True, resizable=True)
gb.configure_selection(selection_mode="single", use_checkbox=True)
grid_options = gb.build()

response = AgGrid(
    df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    height=800,
    use_container_width=True,
    enable_enterprise_modules=False,
    enableRowSelection=True
)

if isinstance(response["selected_rows"], list) and len(response["selected_rows"]) > 0:
    st.session_state["selected_row"] = response["selected_rows"][0]
