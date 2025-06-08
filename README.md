# 💊 Drugs Bot
Ein Streamlit-basiertes Tool zur Verwaltung und Analyse von Medikamentenbewegungen aus PDF-Importen.

## Features
- PDF-Upload & automatischer Import in SQLite
- Automatische Listenklassifizierung (A/B)
- Manuelle Bearbeitung in interaktiver Tabelle
- Neue Zeile anlegen, Duplizieren, Löschen, CSV-Export

## Installation
```bash
git clone git@github.com:carebo80/drugs_bot.git
cd drugs_bot
pip install -r requirements.txt
streamlit run gui.py
