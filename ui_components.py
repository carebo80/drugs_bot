import streamlit as st

def sicherheitsdialog(titel: str, bestaetigungs_button: str, callback):
    dialog_key = f"sicherheitsdialog_{titel}"

    if st.session_state.get(f"{dialog_key}_armed"):
        # Benutzer hat auf „Ja, bestätigen“ geklickt → ausführen
        callback()
        st.session_state[f"{dialog_key}_armed"] = False
        st.session_state["__trigger_refresh__"] = True
    else:
        # Erste Stufe: Sicherheitsfrage anzeigen
        if st.button(f"⚠️ {titel} bestätigen", key=f"{dialog_key}_start"):
            st.session_state[f"{dialog_key}_armed"] = True

        if st.session_state.get(f"{dialog_key}_armed"):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.warning(f"Willst du wirklich **{titel}**?")
            with col2:
                if st.button(bestaetigungs_button, key=f"{dialog_key}_confirm"):
                    pass  # Button dient nur als Trigger, nächste Iteration führt Callback aus