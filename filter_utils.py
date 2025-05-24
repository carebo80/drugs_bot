# filter_utils.py

import pandas as pd
import streamlit as st

def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Wendet die gespeicherten Filter in st.session_state auf den DataFrame an."""
    
    med_filter = st.session_state.get("med_filter", "").strip()
    if med_filter:
        df = df[df["artikel_bezeichnung"].str.contains(med_filter, case=False, na=False)]

    beleg_filter = st.session_state.get("beleg_filter", "").strip()
    if beleg_filter:
        df = df[df["belegnummer"].astype(str).str.contains(beleg_filter, na=False)]

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
