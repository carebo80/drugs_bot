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

# 📦 total: Live-Saldo pro Medikamentenname
gruppen_saldo = df.groupby("artikel_bezeichnung").agg({
    "eingang": "sum",
    "ausgang": "sum"
}).fillna(0)
gruppen_saldo["total"] = gruppen_saldo["eingang"] - gruppen_saldo["ausgang"]
df["total"] = df["eingang"] - df["ausgang"]
df["dirty"] = df["dirty"].astype(bool)

# 🔄 Daten neu laden
if st.sidebar.button("🔄 Laufende Liste neu laden"):
    lade_daten.clear()  # Cache löschen
    st.rerun()

if st.sidebar.button("🔁 Alle Filter zurücksetzen"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# 🎛️ Sidebar-Filter
st.sidebar.header("🔍 Filter")

med_filter = st.sidebar.text_input("🔤 Medikament enthält...", value="", key="med_filter")
beleg_filter = st.sidebar.text_input("📄 Belegnummer enthält...", value="", key="beleg_filter")

name_filter = st.sidebar.selectbox("👤 Name", ["Alle"] + sorted(df["name"].dropna().unique()), key="name_filter")
vorname_filter = st.sidebar.selectbox("🧑 Vorname", ["Alle"] + sorted(df["vorname"].dropna().unique()), key="vorname_filter")
lieferant_filter = st.sidebar.selectbox("🏢 Lieferant", ["Alle"] + sorted(df["lieferant"].dropna().unique()), key="lieferant_filter")
liste_filter = st.sidebar.selectbox("📋 Liste", ["Alle"] + sorted(df["liste"].dropna().unique()), key="liste_filter")
quelle_filter = st.sidebar.selectbox("📦 Quelle", ["Alle", "excel", "pdf"], key="quelle_filter")
dirty_filter = st.sidebar.selectbox("🧪 Dirty", ["Alle", "Ja", "Nein"], key="dirty_filter")

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
if dirty_filter == "Ja":
    df = df[df["dirty"] == True]
elif dirty_filter == "Nein":
    df = df[df["dirty"] == False]


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
    "id", "belegnummer", "artikel_bezeichnung", "liste", "datum",
    "name", "vorname", "prirez", "lieferant", "ls_nummer",
    "ein_mge", "ein_pack", "eingang", "aus_mge", "aus_pack", "ausgang",
    "total", "quelle", "ks", "dirty"
]

    
anzeige_df = df_page[columns].copy()

# Originaldaten für Vergleich sichern (rohe Daten, kein Format)
st.session_state["original_df_page"] = df_page[columns].copy()

from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode

gb = GridOptionsBuilder.from_dataframe(anzeige_df)
# gb.configure_default_column(editable=True, resizable=True)
gb.configure_column("id", editable=False, hide=False)
gb.configure_column("ks", editable=False, hide=False)
gb.configure_column("belegnummer", editable=True, resizable=True)
gb.configure_column("artikel_bezeichnung", editable=True, width=600, resizable=True)
gb.configure_column("liste", editable=True, resizable=True)
gb.configure_column("datum", editable=True, resizable=True, type=["textColumn"])
gb.configure_column("name", editable=True, resizable=True)
gb.configure_column("vorname", editable=True, resizable=True)
gb.configure_column("prirez", editable=True, resizable=True)
gb.configure_column("lieferant", editable=True, resizable=True)
gb.configure_column("ls_nummer", editable=True, resizable=True)
gb.configure_column("ein_mge", editable=True, resizable=True)
gb.configure_column("ein_pack", editable=True, resizable=True)
gb.configure_column("eingang", editable=True, resizable=True)
gb.configure_column("aus_mge", editable=True, resizable=True)
gb.configure_column("aus_pack", editable=True, resizable=True)
gb.configure_column("ausgang", editable=True, resizable=True)
gb.configure_column("total", editable=True, resizable=True)
gb.configure_column("quelle", editable=True, resizable=True)
gb.configure_column("dirty", editable=True, resizable=True)

gb.configure_grid_options(domLayout='normal')  # vermeidet zu enge Darstellung
grid_options = gb.build()

st.subheader("📋 Daten-Tabelle")
response = AgGrid(
    anzeige_df,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.MANUAL,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
    height=800,
    use_container_width=True,
    reload_data=True
)

# Originaldaten merken
if "original_df_page" not in st.session_state:
    st.session_state["original_df_page"] = df_page[columns].copy()


if st.button("💾 Änderungen speichern"):
    updated_df = pd.DataFrame(response["data"])
    original_df = st.session_state.get("original_df_page")

    if original_df is None or updated_df is None:
        st.warning("⚠️ Vergleich nicht möglich – Originaldaten fehlen.")
    else:
        def normalize(val):
            if pd.isna(val):
                return ""
            if isinstance(val, (pd.Timestamp, date)):
                return val.strftime("%Y-%m-%d")
            try:
                parsed = pd.to_datetime(val, dayfirst=True, errors="coerce")
                if pd.notna(parsed):
                    return parsed.strftime("%Y-%m-%d")
            except:
                pass
            return str(val).strip()

        changed_rows = []

        for i, updated_row in updated_df.iterrows():
            row_id = updated_row["id"]
            original_row = original_df[original_df["id"] == row_id]
            if original_row.empty:
                continue
            original_row = original_row.iloc[0]

            row_changed = False
            for col in updated_df.columns:
                if col == "id":
                    continue

                val_old = normalize(original_row[col])
                val_new = normalize(updated_row[col])

                if val_old != val_new:
                    st.write(f"🆔 Änderung erkannt bei ID {row_id} – Spalte: {col}")
                    st.write(f"  ALT: '{val_old}' | NEU: '{val_new}'")
                    row_changed = True
                    break

            if row_changed:
                changed_rows.append(updated_row.to_dict())

        # Änderungen anzeigen
        st.write(f"🧾 Änderungen erkannt: {len(changed_rows)}")
        if changed_rows:
            st.dataframe(pd.DataFrame(changed_rows))

        # Speichern in DB
        if changed_rows:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            for row in changed_rows:
                sql = """
                UPDATE bewegungen SET
                    belegnummer = ?, artikel_bezeichnung = ?, liste = ?, datum = ?, name = ?, vorname = ?, prirez = ?,
                    lieferant = ?, ls_nummer = ?, ein_mge = ?, ein_pack = ?, eingang = ?,
                    aus_mge = ?, aus_pack = ?, ausgang = ?, total = ?, quelle = ?, ks = ?, dirty = ?
                WHERE id = ?
                """
                cursor.execute(sql, (
                    row["belegnummer"], row["artikel_bezeichnung"], row["liste"], row["datum"], row["name"],
                    row["vorname"], row["prirez"], row["lieferant"], row["ls_nummer"], row["ein_mge"], row["ein_pack"],
                    row["eingang"], row["aus_mge"], row["aus_pack"], row["ausgang"], row["total"],
                    row["quelle"], row["ks"], row["dirty"], row["id"]
                ))
            conn.commit()
            conn.close()
            st.success(f"✅ {len(changed_rows)} Zeile(n) erfolgreich aktualisiert.")
        else:
            st.info("ℹ️ Keine Änderungen erkannt.")

# 📂 CSV Export nur sichtbare Daten
csv = anzeige_df.to_csv(index=False).encode("utf-8")
st.download_button("📂 Exportiere aktuelle Seite als CSV", data=csv, file_name="laufende_liste_export.csv", mime="text/csv")
