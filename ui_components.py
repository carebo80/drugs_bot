import streamlit as st

def sicherheitsdialog(label: str, ausfuehren_button: str, aktion):
    key_base = f"dialog_{label.lower()}"
    if f"{key_base}_offen" not in st.session_state:
        st.session_state[f"{key_base}_offen"] = False

    if not st.session_state[f"{key_base}_offen"]:
        if st.button(f"⚠️ {label}", key=f"btn_open_{key_base}"):
            st.session_state[f"{key_base}_offen"] = True
        return

    with st.expander(f"Sicherheitsabfrage: {label}", expanded=True):
        if st.button(ausfuehren_button, key=f"btn_confirm_{key_base}"):
            aktion()
            st.session_state[f"{key_base}_offen"] = False
            st.rerun()  # sofort nach Ausführung aktualisieren
        if st.button("❎ Abbrechen", key=f"btn_cancel_{key_base}"):
            st.session_state[f"{key_base}_offen"] = False
