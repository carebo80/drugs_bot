import streamlit as st
import sqlite3
import pandas as pd
from utils.helpers import ensure_views

DB_PATH = "data/laufende_liste.db"

ensure_views()
st.set_page_config(page_title="📊 Dashboard", layout="wide")
st.title("📊 Bestands-Dashboard")

# Verbindung zur DB und Laden der View v_bestand
@st.cache_data
def lade_bestand():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM v_bestand ORDER BY saldo ASC", conn)
    conn.close()
    return df

df = lade_bestand()

# Kennzahlen
col1, col2, col3 = st.columns(3)
col1.metric("Gesamtanzahl Medikamente", len(df))
col2.metric("Anzahl mit negativem Bestand", (df["saldo"] < 0).sum())
col3.metric("Durchschnittsbestand", f"{df['saldo'].mean():.1f}")

# Tabelle anzeigen
st.subheader("📋 Bestände (negativ zuerst)")
st.dataframe(df)

# Filter
with st.expander("🔍 Filteroptionen"):
    min_saldo = st.number_input("Mindest-Saldo", value=int(df["saldo"].min()))
    max_saldo = st.number_input("Maximal-Saldo", value=int(df["saldo"].max()))
    df = df[(df["saldo"] >= min_saldo) & (df["saldo"] <= max_saldo)]

# Gefilterte Tabelle
st.dataframe(df)
