#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_figuren.py · Holt die figurenabhängigen Pflichtaufgaben (Gruppe A, 2020–2024)
des Hessischen Mathe-Wettbewerbs, schneidet je Aufgabe die Abbildung als PNG zu und
baut fertige Blöcke (inkl. BILD:-Feld) für aufgaben-wettbewerb.txt.

WARUM lokal? Die reine Text-Extraktion lief in der Cowork-Session; das Rendern/Zuschneiden
der Figuren aus dem PDF braucht aber eine echte PDF-Engine (PyMuPDF) und Schreibzugriff
auf den Bilder-Ordner – das läuft zuverlässig nur hier bei dir.

Quelle (einzige): https://mathematik-wettbewerb.de/aufgabenauswahl
Es werden ausschließlich Aufgaben von dieser Seite verwendet.

------------------------------------------------------------------
VORAUSSETZUNG (einmalig):
    pip install pymupdf

AUFRUF (im Ordner dieser Datei):
    python3 extract_figuren.py

ERGEBNIS:
    bilder/*.png                      – ein Zuschnitt je Figur-Aufgabe
    figur-aufgaben.generated.txt      – fertige Blöcke zum Prüfen
  danach (nach Sichtkontrolle):
    - Inhalt von figur-aufgaben.generated.txt ans Ende von aufgaben-wettbewerb.txt kopieren
    - python3 validate_aufgaben.py aufgaben-wettbewerb.txt   -> muss ✅ ergeben
  ODER automatisch anhängen:
    python3 extract_figuren.py --append
------------------------------------------------------------------
Der Renderer (mathe-warmup.html) zeigt das Bild über das Feld  BILD: bilder/<datei>.png
direkt unter der Frage an (Patch ist bereits eingespielt).
"""

import sys, os, re, urllib.parse, urllib.request

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("FEHLER: PyMuPDF fehlt.  ->  pip install pymupdf")

BASE   = "https://mathematik-wettbewerb.de/aufgabenauswahl"
YEARS  = ["2024", "2023", "2022", "2021", "2020"]
GRUPPE = "A"
IMGDIR = "bilder"
DPI    = 300                      # Render-Auflösung der Zuschnitte
PAD    = 18                       # Rand (Punkte) um die erkannte Figur; per --pad N änderbar

# --- Die 17 figurenabhängigen Aufgaben (dedupliziert) -----------------------
#   field = Spalten-ID der Lerntheke (Thema), nur zum gezielten PDF-Abruf.
#   thema = exaktes Lerntheke-Label fürs Blockformat (THEMA:).
#   DIFF wird automatisch aus den Sternen im PDF abgeleitet.
TASKS = [
    # Thema „Flächen und Körper" (Spalte 6_P)
    dict(field="6_P",  thema="Flächen und Körper",        year="2020", code="P8", slug="flaechen-koerper"),
    dict(field="6_P",  thema="Flächen und Körper",        year="2021", code="P8", slug="flaechen-koerper"),
    dict(field="6_P",  thema="Flächen und Körper",        year="2022", code="P8", slug="koordinaten-viereck"),
    dict(field="6_P",  thema="Flächen und Körper",        year="2023", code="P8", slug="kongruente-dreiecke"),
    dict(field="6_P",  thema="Flächen und Körper",        year="2024", code="P7", slug="quadernetz"),
    dict(field="6_P",  thema="Flächen und Körper",        year="2024", code="P8", slug="figur-abcdef"),
    # Thema „Symmetrie" (Spalte 21_P) – Bildsymbole, nur als Original-Crop möglich
    dict(field="21_P", thema="Symmetrie",                 year="2020", code="P6", slug="symmetrie-figuren"),
    dict(field="21_P", thema="Symmetrie",                 year="2021", code="P5", slug="babyspielzeug"),
    dict(field="21_P", thema="Symmetrie",                 year="2022", code="P7", slug="emojis"),
    dict(field="21_P", thema="Symmetrie",                 year="2023", code="P5", slug="waeschesymbole"),
    dict(field="21_P", thema="Symmetrie",                 year="2024", code="P5", slug="spielkartensymbole"),
    # Thema „Winkel in Figuren" (Spalte 27_P)
    dict(field="27_P", thema="Winkel in Figuren",         year="2020", code="P4", slug="parallelen-winkel"),
    dict(field="27_P", thema="Winkel in Figuren",         year="2021", code="P3", slug="dreieck-winkel"),
    dict(field="27_P", thema="Winkel in Figuren",         year="2022", code="P5", slug="gleichschenklig"),
    dict(field="27_P", thema="Winkel in Figuren",         year="2023", code="P3", slug="winkelhalbierende"),
    dict(field="27_P", thema="Winkel in Figuren",         year="2024", code="P3", slug="parallelen-winkel"),
    # Thema „Wahrscheinlichkeitsrechnung" (Spalte 28_P) – nur das Würfelnetz
    dict(field="28_P", thema="Wahrscheinlichkeitsrechnung", year="2022", code="P6", slug="wuerfelnetz"),
]

# ---------------------------------------------------------------------------
def pdf_url(field):
    qs = [("1_G", GRUPPE)] + [(y + "_J", y) for y in YEARS] + [(field, "True"), ("submit", "True")]
    return BASE + "?" + urllib.parse.urlencode(qs)

def download(field):
    req = urllib.request.Request(pdf_url(field), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if data[:5] != b"%PDF-":
        raise RuntimeError(f"Antwort für {field} ist kein PDF (Anfang: {data[:16]!r})")
    return fitz.open(stream=data, filetype="pdf")

def clean(text):
    """PDF-Rohtext zu einzeiliger, sauberer Frage/Lösung normalisieren."""
    t = text.replace("­", "")                 # weiches Trennzeichen
    t = re.sub(r"-\n(?=[a-zäöü])", "", t)           # Trennstriche am Zeilenende zusammenführen
    t = t.replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    # typografische Anführungszeichen vereinheitlichen
    t = t.replace("“", "„").replace("”", "\"")
    return t

STAR = re.compile(r"[∗*⋆✶✱]")
def diff_from_stars(s):
    n = len(STAR.findall(s))
    return {1: "leicht", 2: "mittel", 3: "schwer"}.get(n, "mittel")

HEAD = re.compile(r"(Aufgabe|L[öo]sung)\s+(\d{4})\s+A\s+(P\d+)")

def heading_spans(doc):
    """Alle Überschriften mit Seite, y-Position und Typ (Aufgabe/Lösung)."""
    out = []
    for pno in range(doc.page_count):
        page = doc[pno]
        d = page.get_text("dict")
        for b in d["blocks"]:
            for ln in b.get("lines", []):
                txt = "".join(s["text"] for s in ln["spans"])
                m = HEAD.search(txt)
                if m:
                    out.append(dict(page=pno, y=ln["bbox"][1], y1=ln["bbox"][3],
                                    typ=m.group(1).lower().replace("ö", "o"),
                                    year=m.group(2), code=m.group(3), line=txt))
    return out

def region_text(page, y0, y1):
    words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,word_no
    # obere Kante ab Aufgabentext (y0), untere Kante VOR der nächsten Überschrift (y1)
    sel = [w for w in words if y0 - 1 <= w[1] < y1 - 2]
    sel.sort(key=lambda w: (round(w[1] / 3), w[0]))
    return clean(" ".join(w[4] for w in sel))

def figure_bbox(page, y0, y1):
    """Bounding-Box der grafischen Elemente (Vektorzeichnungen + Rasterbilder) im Bereich."""
    rects = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.y0 >= y0 - 2 and r.y1 <= y1 + 2 and r.width > 4 and r.height > 4:
            rects.append(r)
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.y0 >= y0 - 2 and r.y1 <= y1 + 2:
            rects.append(r)
    if not rects:
        return None
    bb = rects[0]
    for r in rects[1:]:
        bb |= r
    bb = fitz.Rect(bb.x0 - PAD, bb.y0 - PAD, bb.x1 + PAD, bb.y1 + PAD)
    return bb & page.rect

# ---------------------------------------------------------------------------
def main():
    global PAD
    append = "--append" in sys.argv
    if "--pad" in sys.argv:
        try: PAD = float(sys.argv[sys.argv.index("--pad") + 1])
        except (IndexError, ValueError): sys.exit("FEHLER: --pad braucht eine Zahl, z. B. --pad 24")
    print(f"Rand um Figur: {PAD} pt")
    os.makedirs(IMGDIR, exist_ok=True)
    pdf_cache, head_cache = {}, {}
    blocks, report = [], []

    for t in TASKS:
        field = t["field"]
        if field not in pdf_cache:
            print(f"… lade PDF Thema {t['thema']} ({field})")
            pdf_cache[field] = download(field)
            head_cache[field] = heading_spans(pdf_cache[field])
        doc, heads = pdf_cache[field], head_cache[field]

        # passende Aufgaben-/Lösungs-Überschrift finden
        aufg = [h for h in heads if h["typ"] == "aufgabe" and h["year"] == t["year"] and h["code"] == t["code"]]
        loes = [h for h in heads if h["typ"] == "losung"  and h["year"] == t["year"] and h["code"] == t["code"]]
        if not aufg:
            report.append(f"!! {t['year']} {t['code']} {t['thema']}: Aufgabe nicht gefunden – übersprungen")
            continue
        a = aufg[0]
        page = doc[a["page"]]

        # Bereich bis zur nächsten Überschrift auf derselben Seite (sonst Seitenende)
        later = [h["y"] for h in heads if h["page"] == a["page"] and h["y"] > a["y"] + 2]
        y_end = min(later) if later else page.rect.y1

        frage = region_text(page, a["y1"], y_end)
        diff  = diff_from_stars(a["line"])

        # Figur zuschneiden
        bb = figure_bbox(page, a["y1"], y_end)
        fname = f"{t['year']}-A-{t['code']}-{t['slug']}.png"
        fpath = os.path.join(IMGDIR, fname)
        if bb and bb.height > 8:
            pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72), clip=bb)
        else:
            # Fallback: gesamten Aufgabenbereich rendern
            clip = fitz.Rect(page.rect.x0, a["y1"], page.rect.x1, y_end)
            pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72), clip=clip)
            report.append(f"   (Fallback-Crop für {t['year']} {t['code']} – bitte Bild prüfen)")
        pix.save(fpath)

        # Lösung
        if loes:
            lh = loes[0]
            lpage = doc[lh["page"]]
            later_l = [h["y"] for h in heads if h["page"] == lh["page"] and h["y"] > lh["y"] + 2]
            ly_end = min(later_l) if later_l else lpage.rect.y1
            loesung = region_text(lpage, lh["y1"], ly_end)
        else:
            loesung = "(Lösung im PDF nicht gefunden – bitte ergänzen)"

        stars = "*" * len(STAR.findall(a["line"]))
        block = (
            f"# Quelle: Math.-Wettbewerb Hessen · 1. Runde {t['year']} · Gruppe {GRUPPE} · Pflicht · {stars}\n"
            f"THEMA: {t['thema']}\n"
            f"DIFF: {diff}\n"
            f"F: {frage}\n"
            f"BILD: {IMGDIR}/{fname}\n"
            f"L: {loesung}\n"
        )
        blocks.append(block)
        report.append(f"OK {t['year']} {t['code']:>3} · {t['thema']:<26} · {diff:<7} · {fname}")

    header = (
        "\n# ============================================================\n"
        "# Import (Figuren): Math.-Wettbewerb Hessen · 1. Runde · Gruppe A · Pflicht\n"
        "# Figurenabhängige Aufgaben mit BILD:-Verweis · Jahrgänge 2020–2024\n"
        "# Quelle: https://mathematik-wettbewerb.de/aufgabenauswahl\n"
        "# ============================================================\n\n"
    )
    out = header + "\n".join(blocks)

    with open("figur-aufgaben.generated.txt", "w", encoding="utf-8") as f:
        f.write(out)

    print("\n".join(report))
    print(f"\n{len(blocks)} Blöcke geschrieben -> figur-aufgaben.generated.txt")
    print(f"Bilder -> {IMGDIR}/  ({len(blocks)} PNG)")

    if append:
        with open("aufgaben-wettbewerb.txt", "a", encoding="utf-8") as f:
            f.write(out)
        print("Angehängt an aufgaben-wettbewerb.txt. Jetzt prüfen:")
        print("    python3 validate_aufgaben.py aufgaben-wettbewerb.txt")
    else:
        print("\nSichtkontrolle der Bilder + Texte, dann entweder manuell einfügen")
        print("oder erneut mit  --append  ausführen.")

if __name__ == "__main__":
    main()
