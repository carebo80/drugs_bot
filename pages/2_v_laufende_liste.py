from io import BytesIO
import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
from utils.helpers import ensure_views

DB_PATH = "data/laufende_liste.db"

st.set_page_config(page_title="📋 Laufende Liste – Ansicht & Export", layout="wide")
st.title("📋 Laufende Liste – Ansicht & Export")

ensure_views()

@st.cache_data
def lade_laufende_liste():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM bewegungen ORDER BY datum DESC", conn)
    conn.close()
    return df

df_raw = lade_laufende_liste()

# Robustes Datums-Parsing
try:
    dt = pd.to_datetime(df_raw["datum"], errors="coerce", dayfirst=True, format="mixed")
except Exception:
    dt = pd.to_datetime(df_raw["datum"], errors="coerce", dayfirst=True)

min_dt = dt.min() if pd.notna(dt.min()) else pd.Timestamp("2000-01-01")
max_dt = dt.max() if pd.notna(dt.max()) else pd.Timestamp.today()

# Filter UI
with st.expander("🔍 Filteroptionen", expanded=True):
    liste_options = sorted(df_raw.get("liste", pd.Series()).dropna().unique()) if "liste" in df_raw.columns else []
    liste_sel = st.multiselect("Liste filtern", options=liste_options, default=liste_options)

    quelle_options = sorted(df_raw.get("quelle", pd.Series()).dropna().unique()) if "quelle" in df_raw.columns else []
    quelle_sel = st.multiselect("Quelle filtern", options=quelle_options, default=quelle_options)

    colA, colB = st.columns(2)
    start_date = colA.date_input("Startdatum", value=min_dt.date())
    end_date = colB.date_input("Enddatum", value=max_dt.date())

# Filter anwenden
df = df_raw.copy()
mask_date = (dt >= pd.to_datetime(start_date)) & (dt <= pd.to_datetime(end_date))
df = df[mask_date]
if liste_sel:
    df = df[df["liste"].isin(liste_sel)]
if quelle_sel:
    df = df[df["quelle"].isin(quelle_sel)]

# Ansicht / Aggregation
show_totals = st.checkbox("Summen (Total) anzeigen", value=False)
only_negative = st.checkbox("Nur negative Differenz", value=False)

if show_totals:
    agg = (
        df.groupby(["artikel_bezeichnung"], dropna=False)
          .agg(total_eingang=("eingang", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum()),
               total_ausgang=("ausgang", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum()))
          .reset_index()
    )
    agg["total"] = agg["total_eingang"] - agg["total_ausgang"]
    if only_negative:
        agg = agg[agg["total"] < 0]
    st.dataframe(agg, use_container_width=True)
    data_for_export = agg
else:
    st.dataframe(df, use_container_width=True)
    data_for_export = df

def _sql_where_for_movements(start_date, end_date, liste_sel, quelle_sel):
    where = ["1=1"]
    params = []
    if start_date:
        where.append("date(datum) >= date(?)")
        params.append(str(start_date))
    if end_date:
        where.append("date(datum) <= date(?)")
        params.append(str(end_date))
    if liste_sel:
        where.append("liste IN (" + ",".join(["?"]*len(liste_sel)) + ")")
        params += list(liste_sel)
    if quelle_sel:
        where.append("quelle IN (" + ",".join(["?"]*len(quelle_sel)) + ")")
        params += list(quelle_sel)
    return " WHERE " + " AND ".join(where), params

def _load_df(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn, params=params)

st.subheader("📤 Kombi-Export (Bewegungen + Bestand)")

col_src, col_btn = st.columns([2,1])
export_source = col_src.selectbox(
    "Quelle",
    ["Beides (empfohlen)", "Nur Bewegungen (v_bewegung)", "Nur Bestand (v_bestand)"],
    index=0
)

if col_btn.button("⬇️ Excel erzeugen"):
    # Bewegungen (v_bewegung) – mit denselben Filtern wie oben
    where_sql, params = _sql_where_for_movements(start_date, end_date, liste_sel, quelle_sel)

    dfs = []
    if export_source in ("Beides (empfohlen)", "Nur Bewegungen (v_bewegung)"):
        df_mov = _load_df("SELECT * FROM v_bewegung" + where_sql + " ORDER BY datum, artikel_bezeichnung", params)
        dfs.append(("Bewegungen", df_mov))

    if export_source in ("Beides (empfohlen)", "Nur Bestand (v_bestand)"):
        # Bestand ist unabhängig von Datum/List in der Regel – falls du filtern willst, bräuchte es eine eigene view mit Datum.
        df_best = _load_df("SELECT * FROM v_bestand ORDER BY saldo")
        dfs.append(("Bestand", df_best))

    # Schreiben
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        for sheet, dfx in dfs:
            dfx.to_excel(xw, index=False, sheet_name=sheet)
            ws = xw.sheets[sheet]
            # simple Spaltenbreiten
            for i, col in enumerate(dfx.columns):
                try:
                    width = max(12, min(42, int(dfx[col].astype(str).str.len().mean() + 6)))
                except Exception:
                    width = 18
                ws.column_dimensions[chr(65+i)].width = width

    st.download_button(
        "📥 Excel herunterladen",
        data=bio.getvalue(),
        file_name="export_bewegungen_bestand.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )