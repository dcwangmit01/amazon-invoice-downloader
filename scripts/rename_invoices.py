#!/usr/bin/env python3
"""
Amazon Invoice PDF Renamer

Benennt heruntergeladene Amazon-Rechnungs-PDFs basierend auf ihrem Inhalt um.
Extrahiert Produktnamen und Einzelbeträge aus dem PDF-Text und erkennt/löscht
Screenshot-PDFs (Chrome PDF-Viewer Captures).

Voraussetzungen:
    pip install pdfplumber

Aufruf:
    python rename_invoices.py /pfad/zu/downloads/
    python rename_invoices.py /pfad/zu/downloads/ --date-from 20240401
    python rename_invoices.py /pfad/zu/downloads/ --date-from 20240401 --date-to 20240731
    python rename_invoices.py /pfad/zu/downloads/ --dry-run          # Nur anzeigen, nichts ändern
    python rename_invoices.py /pfad/zu/downloads/ --only-suffixed    # Nur _1, _2 etc. Dateien

Dateinamen-Schema:
    YYYYMMDD_BETRAG_amazon_PRODUKTNAME.pdf
"""
import argparse
import os
import re
import sys

try:
    import pdfplumber
except ImportError:
    print("pdfplumber nicht installiert. Bitte: pip install pdfplumber")
    sys.exit(1)


# --- Screenshot/Junk Detection ---

SCREENSHOT_MARKERS = [
    "Amazon.de durchsuchen",
    "Rufus",
    "Nachrichtenassistent",
    "Chat neu starten",
    "Zum Einkaufsw",
]


def classify_pdf(text):
    """Klassifiziert PDF-Inhalt. Returns: 'invoice', 'screenshot', 'bestelluebersicht', 'css_garbage'"""
    if not text or len(text.strip()) < 20:
        return "empty"
    if any(m in text for m in SCREENSHOT_MARKERS):
        return "screenshot"
    if text.strip().startswith("cls-") or ".cls-" in text[:100] or "<style>" in text[:200]:
        return "css_garbage"
    if "Bestellübersicht" in text and "Rechnung" not in text[:200]:
        return "bestelluebersicht"
    return "invoice"


# --- Amount Extraction ---

AMOUNT_PATTERNS = [
    r'Zahlbetrag\s+([\d.,]+)\s*€',
    r'Rechnungsbetrag[:\s€]*([\d.,]+)\s*€',
    r'Gesamt-Brutto\s+([\d.,]+)\s*EUR',
    r'Gesamtbetrag[:\s]+([\d.,]+)\s*€',
    r'Endbetrag\s+([\d.,]+)\s*€',
    r'Total[:\s]+([\d.,]+)\s*€',
]


def extract_amount(text):
    """Extrahiert Rechnungsbetrag aus PDF-Text. Returns: str like '16.10' or None"""
    for pattern in AMOUNT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1).replace(".", "").replace(",", ".")
            try:
                return f"{float(raw):.2f}"
            except ValueError:
                pass
    return None


# --- Product Name Extraction ---

def extract_product(text):
    """
    Extrahiert Produktnamen aus Amazon-Rechnungs-PDF.

    Amazon-Rechnungen haben sehr unterschiedliche Formate:
    - Amazon-Standard: Tabelle mit "Beschreibung Menge Stückpreis (ohne USt.) (inkl. USt.)"
    - Verkäufer-Rechnungen: "Pos Art-Nr. Bezeichnung Menge ..." oder "Artikelnr Bezeichnung Einh."
    - Drittanbieter: Komplett eigenes Layout (z.B. Cycamore, Kleiderkabine, KRUSTENZAUBER)

    Returns: str or None
    """
    product = None

    # Methode 1: Nach Tabellen-Header suchen und nächste Produktzeile extrahieren
    header_patterns = [
        r'\(inkl\. USt\.\)\s*(?:\(inkl\. USt\.\))?\s*\n',  # Amazon Standard
        r'Bezeichnung\s+(?:Einh\.|Anz|Menge).*?\n',         # Verkäufer-Rechnungen
        r'G-Preis\s*€?\s*\n',                                # Cycamore-Stil
    ]

    for hp in header_patterns:
        m = re.search(hp, text)
        if m:
            after = text[m.end():]
            lines = after.split('\n')
            product_lines = []
            for line in lines:
                line = line.strip()
                # Stop bei Summen/Zusammenfassung
                if re.match(r'(?:Netto|Summe|Gesamt|Zwischen|Versand|MwSt|Umsatz|'
                           r'Vielen|Zahlungs|Diese|Ihre Zahlung|Rechnungsbetrag)', line):
                    break
                if re.match(r'^ASIN', line) or re.match(r'^B0[A-Z0-9]{8}$', line):
                    break
                if not line or len(line) < 3:
                    continue
                if re.match(r'^[\d.,€%\s/]+$', line):
                    continue
                product_lines.append(line)
                if len(product_lines) >= 2:
                    break

            if product_lines:
                raw = " ".join(product_lines)
                raw = _clean_product_text(raw)
                if len(raw) > 5:
                    product = raw
                    break

    # Methode 2: Pos-basierte Tabelle (z.B. "PosEAN Bezeichnung ...")
    if not product:
        m = re.search(r'Pos.*?Bezeichnung.*?\n', text)
        if m:
            after = text[m.end():]
            for line in after.split('\n'):
                line = line.strip()
                if not line:
                    continue
                line = re.sub(r'^\d+\s+\d{10,}\s+', '', line)  # Pos + EAN entfernen
                line = re.sub(r'\s+\d+\s+\(.*$', '', line)
                line = re.sub(r'\s+[\d.,]+\s*EUR.*$', '', line)
                line = line.strip()
                if len(line) > 10:
                    product = line
                    break

    # Methode 3: Text vor ASIN suchen
    if not product:
        asin_match = re.search(r'(.{10,150}?)\s*ASIN[:\s]', text)
        if asin_match:
            candidate = asin_match.group(1).strip()
            candidate = re.sub(r'\s+', ' ', candidate)
            candidate = re.sub(r'^[\d.,€\s]+', '', candidate)
            skip = ["(ohne USt.)", "(inkl. USt.)", "Menge", "Stückpreis", "Rechnungsadresse"]
            if len(candidate) > 5 and not any(s in candidate for s in skip):
                product = candidate

    if product and len(product) > 80:
        product = product[:77] + "..."

    return product


def _clean_product_text(raw):
    """Bereinigt extrahierten Produkttext von Artikelnummern, Preisen, etc."""
    # Artikelnummer-Präfixe entfernen
    raw = re.sub(r'^[A-Z0-9-]+_[A-Za-z]+\s+', '', raw)        # "KRZ-11_Tajine red"
    raw = re.sub(r'^[A-Z]-\d+\s+\d+\s+\d+\s+', '', raw)       # "C-71 9 01 "
    raw = re.sub(r'^[A-Z]-\d+\s+\d+\s+', '', raw)
    raw = re.sub(r'^\d{10,}\s+', '', raw)                       # EAN-Nummern
    raw = re.sub(r'^\d+\.\s+\d{8,}\s+', '', raw)               # "1. 09929677 "
    raw = re.sub(r'^\d+\s+', '', raw)                           # Pos-Nummer

    # Trailing Mengen-/Preisdaten entfernen
    raw = re.sub(r'\s+\d+\s+[\d.,]+\s*€\s*[\d.,]*\s*%?.*$', '', raw)
    raw = re.sub(r'\s+Stück\s+[\d.,]+\s+[\d.,]+.*$', '', raw)
    raw = re.sub(r'\s+Flasche\s+[\d.,]+\s+[\d.,]+.*$', '', raw)
    raw = re.sub(r'\s+\d+\s+\([\d%]+\s*%?\).*$', '', raw)
    raw = re.sub(r'\s+[\d.,]+\s*EUR\s*$', '', raw)
    raw = re.sub(r'\s+[\d.,]+\s*€\s*$', '', raw)
    raw = re.sub(r'\s+\d+\s+[\d.,]+\s*€?\s+\d+[.,]?\d*%.*$', '', raw)

    # ASIN und (ohne USt.) entfernen
    raw = re.sub(r'\s*\|?\s*ASIN.*$', '', raw)
    raw = re.sub(r'\s*\|?\s*B0[A-Z0-9]{8,}$', '', raw)
    raw = re.sub(r'\(ohne USt\.\).*$', '', raw)
    raw = re.sub(r'\(inkl\. USt\.\).*$', '', raw)

    # Bereinigung
    raw = re.sub(r'^[,.\s-]+', '', raw)
    raw = re.sub(r'[,.\s-]+$', '', raw)
    raw = re.sub(r'--+', '-', raw)

    return raw.strip()


# --- Filename Helpers ---

def sanitize_filename(name):
    """Macht einen String dateinamen-sicher."""
    safe = "".join(c for c in name if c.isalnum() or c in " -_+äöüÄÖÜß.,()").strip()
    safe = re.sub(r'\s+', ' ', safe)
    return safe


def unique_path(directory, filename):
    """Gibt einen eindeutigen Dateipfad zurück (fügt _2, _3 etc. hinzu bei Kollision)."""
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(filename)
    counter = 2
    while os.path.exists(os.path.join(directory, f"{base}_{counter}{ext}")):
        counter += 1
    return os.path.join(directory, f"{base}_{counter}{ext}")


# --- Main Logic ---

def process_file(filepath, dry_run=False):
    """
    Verarbeitet eine einzelne PDF-Datei.
    Returns: (action, old_name, new_name_or_reason)
        action: 'rename', 'delete', 'skip', 'error'
    """
    filename = os.path.basename(filepath)
    directory = os.path.dirname(filepath)

    try:
        with pdfplumber.open(filepath) as pdf:
            text = ""
            for p in pdf.pages[:3]:
                text += (p.extract_text() or "") + "\n"
    except Exception as e:
        return ("error", filename, str(e))

    # Klassifizieren
    classification = classify_pdf(text)
    if classification in ("screenshot", "css_garbage", "bestelluebersicht"):
        if not dry_run:
            try:
                os.remove(filepath)
            except Exception as e:
                return ("error", filename, f"Löschen fehlgeschlagen: {e}")
        return ("delete", filename, classification)

    if classification == "empty":
        return ("skip", filename, "Leeres PDF")

    # Dateiname parsen
    parts = filename.split('_', 3)
    if len(parts) < 3:
        return ("skip", filename, "Unerwartetes Namensformat")

    date_str = parts[0]
    orig_total = parts[1]

    # Betrag und Produkt extrahieren
    amount = extract_amount(text)
    product = extract_product(text)
    new_total = amount if amount else orig_total

    if product:
        safe_product = sanitize_filename(product)
        new_name = f"{date_str}_{new_total}_amazon_{safe_product}.pdf"
    else:
        # Kein Produkt gefunden — _N Suffix entfernen
        rest = parts[3] if len(parts) > 3 else ""
        rest = re.sub(r'_\d+\.pdf$', '.pdf', rest)
        if rest and rest != '.pdf':
            new_name = f"{date_str}_{new_total}_amazon_{rest}"
        else:
            return ("skip", filename, "Kein Produkt extrahiert")

    if new_name == filename:
        return ("skip", filename, "Name bereits korrekt")

    new_path = unique_path(directory, new_name)
    new_name = os.path.basename(new_path)

    if not dry_run:
        try:
            os.rename(filepath, new_path)
        except Exception as e:
            return ("error", filename, f"Umbenennung fehlgeschlagen: {e}")

    return ("rename", filename, new_name)


def main():
    parser = argparse.ArgumentParser(description="Amazon-Rechnungs-PDFs umbenennen")
    parser.add_argument("directory", help="Verzeichnis mit den PDF-Dateien")
    parser.add_argument("--date-from", help="Startdatum (YYYYMMDD), z.B. 20240401")
    parser.add_argument("--date-to", help="Enddatum (YYYYMMDD), z.B. 20240731")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts ändern")
    parser.add_argument("--only-suffixed", action="store_true",
                       help="Nur Dateien mit _1, _2 etc. Suffix verarbeiten")
    args = parser.parse_args()

    directory = args.directory
    if not os.path.isdir(directory):
        print(f"Verzeichnis nicht gefunden: {directory}")
        sys.exit(1)

    files = sorted(os.listdir(directory))
    to_process = []

    for f in files:
        if not f.endswith('.pdf'):
            continue
        # Datumsfilter
        if args.date_from and f[:8] < args.date_from:
            continue
        if args.date_to and f[:8] > args.date_to:
            continue
        # Nur _N Suffix?
        if args.only_suffixed and not re.search(r'_\d+\.pdf$', f):
            continue
        to_process.append(f)

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Verarbeite {len(to_process)} Dateien...\n")

    stats = {"rename": 0, "delete": 0, "skip": 0, "error": 0}

    for f in to_process:
        filepath = os.path.join(directory, f)
        action, old_name, detail = process_file(filepath, dry_run=args.dry_run)
        stats[action] += 1

        if action == "rename":
            print(f"  📝 {old_name[:60]}")
            print(f"     → {detail[:60]}")
        elif action == "delete":
            print(f"  🗑️  {old_name[:60]} [{detail}]")
        elif action == "error":
            print(f"  ❌ {old_name[:60]}: {detail}")
        # skip: still ausgeben

    print(f"\n{'='*50}")
    print(f"Umbenannt: {stats['rename']}")
    print(f"Gelöscht:  {stats['delete']}")
    print(f"Fehler:    {stats['error']}")
    print(f"Übersprungen: {stats['skip']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
