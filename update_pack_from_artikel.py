import sqlite3
import re

DB_PATH = "data/laufende_liste.db"

def extrahiere_packung(text):
    """Extrahiere Packungseinheit aus Artikelbezeichnung gemäß definierter Regeln."""
    text = str(text)

    # 1. Multiplikator-Fälle wie "5x2.5ml", "10Am 1ml", "5 Amp 1ml"
    match_multi = re.search(r"(\d+)\s*(?:x|A|Am|Amp)\s*\d*\.?\d*\s*ml", text, re.IGNORECASE)
    if match_multi:
        return int(match_multi.group(1))

    # 2. Direkte ml-Zahl wie "50ml"
    match_ml = re.search(r"(\d+)\s*ml", text, re.IGNORECASE)
    if match_ml:
        return int(match_ml.group(1))

    # 3. Letzte Zahl im Text – z. B. "12.5mg 28" → 28
    matches = re.findall(r"(\d+)", text)
    if matches:
        return int(matches[-1])

    return None

def aktualisiere_packungen():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Nur Zeilen mit quelle='excel' holen
    cursor.execute("SELECT id, artikel_bezeichnung, ein_mge, aus_mge FROM bewegungen WHERE quelle = 'excel'")
    zeilen = cursor.fetchall()

    updated = 0
    for zeile in zeilen:
        id_, artikel, ein_mge, aus_mge = zeile
        packung = extrahiere_packung(artikel)
        if not packung:
            continue

        if ein_mge is not None:
            cursor.execute("UPDATE bewegungen SET ein_pack = ? WHERE id = ?", (packung, id_))
            updated += 1

        if aus_mge is not None:
            cursor.execute("UPDATE bewegungen SET aus_pack = ? WHERE id = ?", (packung, id_))
            updated += 1

    conn.commit()
    conn.close()

    print(f"✅ {updated} Packungsgrößen aktualisiert (nur quelle='excel').")

if __name__ == "__main__":
    aktualisiere_packungen()
