import re

def normalize(text):
    return re.sub(r"[^a-z]", "", text.lower())

# 🔧 Beispielhafte Lieferantendaten (aus lieferanten.csv)
lieferanten_set = {normalize("VOIGT AG"), normalize("Sandoz"), normalize("Mepha")}

# 🔎 Beispiel-Zeilen (Layout B, wie aus einem PDF extrahiert)
beispiele = [
    ["27091", "11.04.2025", "VOIGT", "AG", "1", "0", "0"],            # ✅ VOIGT AG
    ["27110", "12.04.2025", "Sandoz", "Pharma", "2", "0", "0"],       # ✅ Sandoz
    ["27120", "13.04.2025", "Mepha", "AG", "0", "2", "0"],            # ✅ Mepha
    ["27130", "14.04.2025", "Kunde", "Testname", "1", "0", "0"],      # ❌ kein Lieferant
    ["27140", "15.04.2025", "ABC", "12345", "0", "1", "0"],           # ❌ kein Lieferant
]

print("🔍 Lieferantenerkennung:\n")

for row in beispiele:
    candidate_tokens = row[2:-3]  # Position des Lieferantennamens
    candidate = normalize(" ".join(candidate_tokens))

    gefunden = None
    for l in lieferanten_set:
        if l in candidate:
            gefunden = " ".join(candidate_tokens)
            break

    print(f"➡️ Zeile: {' '.join(row)}")
    if gefunden:
        print(f"✅ Erkannt als Lieferant: {gefunden}\n")
    else:
        print("❌ Kein Lieferant erkannt\n")
