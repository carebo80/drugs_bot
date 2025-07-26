import fitz  # PyMuPDF
import re
from pathlib import Path

def slot_preserving_tokenizer_fixed(line: str) -> list[str]:
    print(f"\n🔍 Input-Zeile: {repr(line)}")

    tokens = []
    date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')
    number_pattern = re.compile(r'(\s*)(\d+)')
    pos = 0

    while pos < len(line):
        # Prüfe auf Datum zuerst
        m_date = date_pattern.match(line, pos)
        if m_date:
            tokens.append(m_date.group(0))
            pos = m_date.end()
            continue

        # Prüfe auf Zahlen mit führendem Whitespace
        m = number_pattern.match(line, pos)
        if m:
            spaces = m.group(1)
            num = m.group(2)
            if spaces:
                tokens.append(spaces)
            tokens.append(num)
            pos = m.end()
        else:
            # nimm auch Whitespaces als Token mit
            if line[pos].isspace():
                space_start = pos
                while pos < len(line) and line[pos].isspace():
                    pos += 1
                tokens.append(line[space_start:pos])
            else:
                next_space = line.find(' ', pos)
                if next_space == -1:
                    tokens.append(line[pos:])
                    break
                else:
                    tokens.append(line[pos:next_space])
                    pos = next_space

    print(f"🧩 Tokens RAW: {tokens} (Anzahl: {len(tokens)})")

    normalized = []
    for t in tokens:
        if t.isspace():
            normalized.append(t)  # wir behalten Leerzeichen
        else:
            normalized.append(t)

    print(f"🧩 Tokens normalisiert: {normalized} (Anzahl: {len(normalized)})")

    while len(normalized) < 16:
        normalized.append('')

    return normalized

def detect_bewegung_from_tokens(tokens):
    try:
        # finde erste "1"
        idx = tokens.index('1')
        if idx >= 1:
            vor_token = tokens[idx - 1]
            if isinstance(vor_token, str) and vor_token.isspace():
                if len(vor_token) == 3:
                    return "ein"
                elif len(vor_token) >= 4:
                    return "aus"
                else:
                    return f"⚠️ unklar (len={len(vor_token)})"
            else:
                return f"⚠️ unklar ({repr(vor_token)})"
        else:
            return "⚠️ kein Whitespace vor Bewegung"
    except ValueError:
        return "⛔ keine Bewegung erkannt"

def extract_blocks_from_pdf(pdf_path: str):
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc, start=1):
        print(f"\n--- 📜 Seite {page_num} ---")
        blocks = page.get_text("blocks")

        for block in sorted(blocks, key=lambda b: (round(b[1]), round(b[0]))):
            text = block[4]
            if text.strip():
                combined_line = " ".join(text.splitlines())
                split_lines = re.split(r'(?=\d{5} \d{2}\.\d{2}\.\d{4})', combined_line)
                for line in split_lines:
                    if line.strip():
                        tokens = slot_preserving_tokenizer_fixed(line)
                        if len(tokens) >= 10:
                            print(f"✅ Zusammengeführt: {tokens}")
                            bewegung = detect_bewegung_from_tokens(tokens)
                            print(f"🔍 Bewegung erkannt als: {bewegung}")

if __name__ == "__main__":
    PDF_PATH = "upload/CPrintQPrinterObject-30824-0.pdf"
    if Path(PDF_PATH).exists():
        extract_blocks_from_pdf(PDF_PATH)
    else:
        print(f"❌ Datei nicht gefunden: {PDF_PATH}")
