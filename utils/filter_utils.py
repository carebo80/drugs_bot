# filter_utils.py
import pandas as pd
import streamlit as st
import os

def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    med_filter = st.session_state.get("med_filter", "").strip()
    if med_filter:
        df = df[df["artikel_bezeichnung"].str.contains(med_filter, case=False, na=False)]

    pharma_filter = st.session_state.get("pharma_filter", "").strip()
    if pharma_filter:
        df = df[df["pharmacode"].astype(str).str.contains(pharma_filter, na=False)]

    name_filter = st.session_state.get("name_filter", "Alle")
    if name_filter != "Alle":
        df = df[df["name"] == name_filter]

    vorname_filter = st.session_state.get("vorname_filter", "Alle")
    if vorname_filter != "Alle":
        df = df[df["vorname"] == vorname_filter]

    lieferant_filter = st.session_state.get("lieferant_filter", "Alle")
    if lieferant_filter != "Alle":
        df = df[df["lieferant"] == lieferant_filter]

    liste_filter = st.session_state.get("liste_filter", "Alle")
    if liste_filter != "Alle":
        df = df[df["liste"] == liste_filter]

    quelle_filter = st.session_state.get("quelle_filter", "Alle")
    if quelle_filter != "Alle":
        df = df[df["quelle"] == quelle_filter]

    dirty_filter = st.session_state.get("dirty_filter", "Alle")
    if dirty_filter == "Ja":
        df = df[df["dirty"] == True]
    elif dirty_filter == "Nein":
        df = df[df["dirty"] == False]

    datum_von = st.session_state.get("datum_von", None)
    if datum_von:
        df = df[pd.to_datetime(df["datum"], errors='coerce') >= pd.to_datetime(datum_von)]

    datum_bis = st.session_state.get("datum_bis", None)
    if datum_bis:
        df = df[pd.to_datetime(df["datum"], errors='coerce') <= pd.to_datetime(datum_bis)]

    return df

def lade_lieferantenliste(pfad="data/lieferanten.csv"):
    if not os.path.exists(pfad):
        return [""]
    df = pd.read_csv(pfad)
    if "lieferant" not in df.columns:
        return [""]
    return sorted(df["lieferant"].dropna().unique())
