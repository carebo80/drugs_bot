# 💊 Drugs Bot
Ein Streamlit-basiertes Tool zur Verwaltung und Analyse von Medikamentenbewegungen aus PDF-Importen.

## Features
- PDF-Upload, Layoutanylse & automatischer Import in SQLite
- Manuelle Bearbeitung in interaktiver Tabelle
- CSV-Export, Duplizieren, Löschen
- Automatische Listenklassifizierung (A/B)

## Installation
```bash
git clone git@github.com:carebo80/drugs_bot.git
cd drugs_bot
pip install -r requirements.txt
streamlit run gui.py
