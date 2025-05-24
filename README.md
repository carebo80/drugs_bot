🧠 Projekt: Medikamenten-Bewegungsdatenverwaltung
Ein System zur Verwaltung, Bearbeitung und Validierung von Bewegungsdaten (z. B. Medikamenten-Ein- und Ausgänge) aus Excel/PDF-Importen mit Streamlit-GUI und SQLite-Backend.

📌 Kernfunktionen (Stand jetzt)
🔄 PDF-Importer (mit PyMuPDF)
Extrahiert Daten pro Medikamentblock und analysiert Zeilen in 11er-Blöcken.

Robuste heuristische Erkennung von ein/aus mit Lagerwert-Filter.

OCR-Fallback mit Tesseract eingebaut (aber verworfen, da ohne erkennbaren Gewinn).

Fehlerhafte Zeilen werden als dirty markiert.

Daten werden in eine SQLite-DB geschrieben.

Quelle (pdf, excel, manuell) wird gespeichert.

.bak-Backup der PDF-Dateien nach Import.

🖥️ Streamlit-GUI: Laufende Liste
Tabellarische Darstellung mit st_aggrid, inkl. Filterung, Bearbeitung, Seitenweise Navigation.

Neue Zeilen hinzufügen: über Eingabemaske (quelle = manuell) oberhalb der Tabelle.

Zeile duplizieren, löschen und CSV-Export.

Eingabemaske ist dynamisch: synchronisiert sich mit ausgewählter Tabellenzeile.

Bearbeitung direkt im Grid oder über separate Felder.

⚠️ Offene Punkte / bekannte Einschränkungen
Einige Zeilen (v. a. in komplexen PDF-Seiten) werden nicht erkannt (z. B. mit ungewöhnlichem Layout, fehlerhafter aus-Erkennung).

OCR bringt derzeit keinen Mehrwert → Fokus wieder auf manuelle Prüfprozesse.

Bei manuell hinzugefügten Zeilen ist derzeit keine automatische Positionierung zur neuen Zeile vorhanden.

Refresh & Filter-Verhalten nach Aktionen noch ausbaufähig.

💡 Ideen für weitere Schritte
Optimierung der ein/aus-Erkennung anhand von Zeichenabständen oder struktureller Muster.

Fallback-Tabelle oder manuelle Prüfmaske für nicht erkannte Bewegungen.

Zentrale Prüfmaske außerhalb der Tabelle zur komfortableren Bearbeitung einzelner Einträge.

Differenzabgleich PDF/Excel zur Validierung.