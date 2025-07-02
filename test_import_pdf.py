from pdf_to_sqlite_importer_dynamic import extract_table_rows_with_article, parse_pdf_to_dataframe_dynamic_layout
import pandas as pd

PDF_PATH = "upload/CPrintQPrinterObject-31785-0.pdf"

# Schritt 1: PDF-Zeilen mit Metadaten extrahieren
rows = extract_table_rows_with_article(PDF_PATH)

# Schritt 2: In sauberes DataFrame parsen (inkl. Lieferantenerkennung)
df = parse_pdf_to_dataframe_dynamic_layout(rows)
print(df[["datum", "name", "lieferant", "ein_mge", "aus_mge", "dirty"]].head(10))
# Zeige Ergebnis
print("\n✅ Vorschau auf erkannte Zeilen:")
print(df[["datum", "name", "lieferant", "ein_mge", "aus_mge", "bg_rez_nr", "dirty"]].head(10))

# Optional: Als CSV speichern für Abgleich
df.to_csv("tmp/pdf_test_ergebnis.csv", index=False)
