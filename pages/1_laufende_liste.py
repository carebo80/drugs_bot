import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode
from filter_utils import filter_dataframe
from ui_components import sicherheitsdialog
import os

DB_PATH = "data/laufende_liste.db"

# Trigger-Mechanismus für Refresh
if st.session_state.pop("__trigger_refresh__", False):
    st.rerun()

# 🔹 Robust: Nur gültige Datumswerte im ISO-Format parsen
def format_datum_safe(d):
    try:
        return pd.to_datetime(d, format="%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return ""

@st.cache_data
def lade_daten():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM bewegungen", conn)
        conn.close()
    except Exception as e:
        st.error(f"❌ Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

    if "datum" in df.columns:
        df["datum"] = df["datum"].apply(format_datum_safe)

    return df

st.set_page_config(page_title="💊 Laufende Liste", layout="wide")
st.title("💊 Laufende Liste – Übersicht & Bearbeitung")

# Sidebar
if st.sidebar.button("🔁 Laufende Liste neu laden"):
    lade_daten.clear()
    st.rerun()

if st.sidebar.button("🔁 Alle Filter zurücksetzen"):
    for key in list(st.session_state.keys()):
        if key.startswith("form_") or key.endswith("_filter") or key.startswith("datum_"):
            del st.session_state[key]
    st.rerun()

st.sidebar.header("🔍 Filter")
temp_df = lade_daten()
st.sidebar.text_input("🎤 Medikament enthält...", value=st.session_state.get("med_filter", ""), key="med_filter")
st.sidebar.text_input("📄 Belegnummer enthält...", value=st.session_state.get("beleg_filter", ""), key="beleg_filter")
st.sidebar.selectbox("👤 Name", ["Alle"] + sorted(temp_df["name"].dropna().unique()), key="name_filter")
st.sidebar.selectbox("🧑 Vorname", ["Alle"] + sorted(temp_df["vorname"].dropna().unique()), key="vorname_filter")
st.sidebar.selectbox("🏢 Lieferant", ["Alle"] + sorted(temp_df["lieferant"].dropna().unique()), key="lieferant_filter")
st.sidebar.selectbox("📋 Liste", ["Alle"] + sorted(temp_df["liste"].dropna().unique()), key="liste_filter")
st.sidebar.selectbox("📦 Quelle", ["Alle", "excel", "pdf", "manuell"], key="quelle_filter")
st.sidebar.selectbox("🧪 Dirty", ["Alle", "Ja", "Nein"], key="dirty_filter")
st.sidebar.date_input("📆 Von", value=st.session_state.get("datum_von", None), key="datum_von")
st.sidebar.date_input("📆 Bis", value=st.session_state.get("datum_bis", None), key="datum_bis")

# Tabelle
df = filter_dataframe(temp_df)

if "selected_row" not in st.session_state:
    st.session_state["selected_row"] = {}

st.subheader("📋 Daten-Tabelle")
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_column("id", editable=False)
gb.configure_default_column(editable=False, resizable=True)
gb.configure_selection(selection_mode="single", use_checkbox=True)
grid_options = gb.build()

response = AgGrid(
    df,
    key="laufende_liste_grid",
    gridOptions=grid_options,
    update_mode=GridUpdateMode.SELECTION_CHANGED,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    height=800,
    use_container_width=True,
    enable_enterprise_modules=False
)

selected_rows = response.get("selected_rows", [])
if isinstance(selected_rows, pd.DataFrame):
    selected_rows = selected_rows.to_dict("records")

if selected_rows and "id" in selected_rows[0]:
    st.session_state["selected_row"] = selected_rows[0]

selected = st.session_state.get("selected_row", {})
valid_selection = bool(selected) and "id" in selected

# Aktionen
st.subheader("🔹 Aktionen")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("➕ Neue Zeile anlegen"):
        st.session_state["selected_row"] = {
            "artikel_bezeichnung": "",
            "belegnummer": "",
            "liste": "b",
            "datum": "",
            "name": "",
            "vorname": "",
            "lieferant": "",
            "ein_mge": None,
            "ein_pack": None,
            "aus_mge": None,
            "aus_pack": None,
            "quelle": "manuell",
            "dirty": True,
            "new": True
        }
        st.session_state["__trigger_refresh__"] = True

with col2:
    def dupliziere():
        row = selected.copy()
        if not row.get("datum") or not row["datum"].strip():
            st.error("⚠️ Duplizieren nicht möglich: Kein Datum gesetzt.")
            return

        try:
            row["datum"] = datetime.strptime(row["datum"], "%d.%m.%Y").date().isoformat()
        except Exception:
            st.error("⚠️ Ungültiges Datum.")
            return

        jetzt = pd.Timestamp.now().isoformat()
        row.update({
            "id": None,
            "dirty": True,
            "quelle": "manuell",
            "created_at": jetzt,
            "updated_at": jetzt
        })

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cols = ", ".join(k for k in row if k != "id")
        placeholders = ", ".join(["?"] * len([k for k in row if k != "id"]))
        sql = f"INSERT INTO bewegungen ({cols}) VALUES ({placeholders})"
        cursor.execute(sql, tuple(row[k] for k in row if k != "id"))
        conn.commit()
        conn.close()

        st.session_state["selected_row"] = {**row, "new": True}
        st.session_state["__trigger_refresh__"] = True

    if valid_selection:
        sicherheitsdialog("Duplizieren", "✅ Ja, duplizieren", dupliziere)

with col3:
    def loeschen():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bewegungen WHERE id = ?", (selected["id"],))
        conn.commit()
        conn.close()
        lade_daten.clear()
        st.session_state["selected_row"] = {}
        st.session_state["__trigger_refresh__"] = True

    if valid_selection:
        sicherheitsdialog("Löschen", "❌ Ja, löschen", loeschen)

with col4:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📂 Export als CSV", data=csv, file_name="laufende_liste_export.csv", mime="text/csv")

if selected.get("new", False) or valid_selection:
    st.subheader("✏️ Bearbeitungsformular")
    with st.form("edit_form"):
        updated = {}

        c1a, c1b, c1c, c1d = st.columns([1, 3, 1, 1])
        updated["belegnummer"] = c1a.text_input("Belegnummer", value=selected.get("belegnummer", ""), key="form_beleg")
        updated["artikel_bezeichnung"] = c1b.text_input("Artikel-Bezeichnung", value=selected.get("artikel_bezeichnung", ""), key="form_artikel")
        updated["datum"] = c1c.text_input("Datum (TT.MM.JJJJ)", value=selected.get("datum", ""), key="form_datum")
        updated["liste"] = c1d.selectbox("Liste", ["a", "b"], index=0 if selected.get("liste") == "a" else 1, key="form_liste")

        c2a, c2b, c2c, c2d = st.columns(4)
        updated["ein_mge"] = c2a.number_input("Ein_Mge", value=int(selected.get("ein_mge") or 0), step=1, format="%d", key="form_ein_mge")
        updated["ein_pack"] = c2b.number_input("Ein_Pack", value=int(selected.get("ein_pack") or 0), step=1, format="%d", key="form_ein_pack")
        updated["aus_mge"] = c2c.number_input("Aus_Mge", value=int(selected.get("aus_mge") or 0), step=1, format="%d", key="form_aus_mge")
        updated["aus_pack"] = c2d.number_input("Aus_Pack", value=int(selected.get("aus_pack") or 0), step=1, format="%d", key="form_aus_pack")

        c3a, c3b, c3c = st.columns([1, 1, 2])
        updated["name"] = c3a.text_input("Name", value=selected.get("name", ""), key="form_name")
        updated["vorname"] = c3b.text_input("Vorname", value=selected.get("vorname", ""), key="form_vorname")

        # Lieferantenauswahl wie bisher
        lieferanten_df = pd.read_csv("data/lieferanten.csv") if os.path.exists("data/lieferanten.csv") else pd.DataFrame(columns=["lieferant"])
        if "lieferant" not in lieferanten_df.columns:
            lieferanten_df["lieferant"] = ""
        lieferanten_liste = [""] + sorted(lieferanten_df["lieferant"].dropna().unique()) if not lieferanten_df.empty else [""]
        aktuell = selected.get("lieferant", "")
        index = lieferanten_liste.index(aktuell) if aktuell in lieferanten_liste else 0
        updated["lieferant"] = c3c.selectbox("Lieferant", lieferanten_liste, index=index, key="form_lieferant")

        c4a, c4b = st.columns([2, 1])
        updated["quelle"] = c4a.selectbox("Quelle", ["excel", "pdf", "manuell"], index=["excel", "pdf", "manuell"].index(selected.get("quelle", "manuell")), key="form_quelle")
        updated["dirty"] = c4b.checkbox("Dirty", value=bool(selected.get("dirty", True)), key="form_dirty")

        # Submit-Button
        if st.form_submit_button("📏 Änderungen speichern"):
            if not updated["datum"] or not updated["datum"].strip():
                st.error("⚠️ Bitte ein gültiges Datum eingeben.")
                st.stop()

            try:
                datum_obj = datetime.strptime(updated["datum"], "%d.%m.%Y").date()
            except ValueError:
                st.error("⚠️ Bitte gültiges Datum im Format TT.MM.JJJJ eingeben.")
                st.stop()

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            if "id" in selected:
                sql = """UPDATE bewegungen SET artikel_bezeichnung = ?, belegnummer = ?, liste = ?, datum = ?, 
                         ein_mge = ?, ein_pack = ?, aus_mge = ?, aus_pack = ?,
                         name = ?, vorname = ?, lieferant = ?, quelle = ?, dirty = ? WHERE id = ?"""
                values = [
                    updated["artikel_bezeichnung"], updated["belegnummer"], updated["liste"], datum_obj.isoformat(),
                    updated["ein_mge"], updated["ein_pack"], updated["aus_mge"], updated["aus_pack"],
                    updated["name"], updated["vorname"], updated["lieferant"], updated["quelle"], updated["dirty"],
                    selected["id"]
                ]
            else:
                sql = """INSERT INTO bewegungen (
                            artikel_bezeichnung, belegnummer, liste, datum,
                            ein_mge, ein_pack, aus_mge, aus_pack,
                            name, vorname, lieferant, quelle, dirty, created_at, updated_at
                         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                jetzt = pd.Timestamp.now().isoformat()
                values = [
                    updated["artikel_bezeichnung"], updated["belegnummer"], updated["liste"], datum_obj.isoformat(),
                    updated["ein_mge"], updated["ein_pack"], updated["aus_mge"], updated["aus_pack"],
                    updated["name"], updated["vorname"], updated["lieferant"], updated["quelle"], updated["dirty"],
                    jetzt, jetzt
                ]

            cursor.execute(sql, values)
            conn.commit()
            conn.close()

            st.success("✅ Eintrag gespeichert.")
            lade_daten.clear()
            st.session_state["selected_row"] = {}
            st.session_state["__trigger_refresh__"] = True
