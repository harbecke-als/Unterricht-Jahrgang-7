#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_aufgaben.py  ·  Prüft aufgaben.txt gegen die Regeln der Mathe-Warm-up-Engine.
Spiegelt 1:1 den Parser aus mathe-warmup.html (Trenner '::', +/- Optionen, ID = Thema+Frage).

Aufruf:
    python3 validate_aufgaben.py aufgaben.txt
    python3 validate_aufgaben.py aufgaben.txt --since "# --- generiert"   # nur neue Bloecke listen

Exit-Code 0 = sauber, 1 = Fehler gefunden (CI-/Workflow-tauglich).
"""
import sys, re, argparse

def slug(s):
    s = s.lower()
    for a, b in (("ä","ae"),("ö","oe"),("ü","ue"),("ß","ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s[:10]

def hash_id(s):
    # djb2, identisch zur Engine: 32-bit unsigned, Basis 36
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    # int -> base36
    if h == 0:
        return "0"
    digs = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while h:
        out = digs[h % 36] + out
        h //= 36
    return out

def parse_diff(v):
    v = str(v).strip().lower()
    if v in ("1", "leicht"): return 1
    if v in ("3", "schwer"): return 3
    return 2

OPT_SPLIT = re.compile(r"\s::\s")
KV = re.compile(r"^([A-Za-zÄÖÜäöü]+):\s*(.*)$")

def parse_aufgaben(text):
    errors, pool = [], []
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks, cur, start = [], [], 1
    for i, ln in enumerate(raw):
        if ln.strip() == "":
            if cur:
                blocks.append((cur, start)); cur = []
        else:
            if not cur: start = i + 1
            cur.append(ln)
    if cur: blocks.append((cur, start))

    for lines, start in blocks:
        lines = [l for l in lines if not l.strip().startswith("#")]
        if not lines: continue
        thema = frage = loesung = akz = hinweis = id_override = None
        bild = None
        diff, jg, opts = 2, None, []
        for raw_line in lines:
            s = raw_line.strip()
            if s.startswith("+ ") or s.startswith("- "):
                ok = s.startswith("+ ")
                rest = s[2:]
                parts = OPT_SPLIT.split(rest)
                diag = " :: ".join(parts[1:]).strip() if len(parts) > 1 else None
                opts.append({"t": parts[0].strip(), "ok": ok, "diag": diag})
                continue
            m = KV.match(s)
            if m:
                k, v = m.group(1).upper(), m.group(2).strip()
                if   k == "THEMA": thema = v
                elif k in ("F", "FRAGE"): frage = v
                elif k in ("L", "LOESUNG", "LÖSUNG"): loesung = v
                elif k in ("OK", "AKZEPTIERT"): akz = v
                elif k in ("HINWEIS", "TIPP"): hinweis = v
                elif k == "ID": id_override = v
                elif k == "JG":
                    try: jg = int(v)
                    except: jg = None
                elif k == "DIFF": diff = parse_diff(v)
                elif k in ("BILD", "ABB"): bild = v
            elif frage is not None and not opts:
                frage += " " + s

        loc = f"ab Zeile {start}" + (f" („{thema}“)" if thema else "")
        if not thema: errors.append(loc + ": THEMA fehlt."); continue
        if not frage: errors.append(loc + ": F: (Frage) fehlt."); continue
        q = {"thema": thema, "frage": frage, "diff": diff, "jg": jg, "start": start}
        if hinweis: q["hinweis"] = hinweis
        if bild: q["bild"] = bild
        if opts:
            nok = sum(1 for o in opts if o["ok"])
            if nok != 1:
                errors.append(loc + f": genau EINE richtige Option mit „+“ noetig (gefunden: {nok})."); continue
            if len(opts) < 2:
                errors.append(loc + ": Multiple Choice braucht mindestens 2 Optionen."); continue
            for o in opts:
                if not o["ok"] and not o["diag"]:
                    errors.append(loc + f": falsche Option „{o['t']}“ ohne Fehlerdiagnose (nach  ::  ).")
            q["typ"] = "mc"; q["optionen"] = opts
        else:
            if not akz and not loesung:
                errors.append(loc + ": OK: (Auto-Check), L: (Selbstkontrolle) oder +/- Optionen fehlen."); continue
            if akz:
                q["typ"] = "input"
                q["loesung"] = loesung or akz
                q["akzeptiert"] = [x.strip() for x in OPT_SPLIT.split(akz) if x.strip()]
            else:
                q["typ"] = "selbst"
                q["loesung"] = loesung
        q["id"] = id_override or (slug(thema) + "-" + hash_id(thema + "|" + frage))
        pool.append(q)

    seen = {}
    for q in pool:
        if q["id"] in seen:
            errors.append(f"Doppelte Aufgabe (ID „{q['id']}“) – Frage evtl. doppelt: ab Zeile {q['start']}.")
        seen[q["id"]] = True
    return pool, errors

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--since", default=None, help="Nur Bloecke ab erstem Vorkommen dieses Markers listen")
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as f:
        text = f.read()
    pool, errors = parse_aufgaben(text)

    by_theme = {}
    by_diff = {1: 0, 2: 0, 3: 0}
    n_mc = n_input = n_selbst = 0
    for q in pool:
        by_theme[q["thema"]] = by_theme.get(q["thema"], 0) + 1
        by_diff[q["diff"]] += 1
        if q["typ"] == "mc": n_mc += 1
        elif q["typ"] == "selbst": n_selbst += 1
        else: n_input += 1

    print(f"Datei: {args.file}")
    print(f"Gueltige Aufgaben: {len(pool)}  (MC: {n_mc} · Freitext: {n_input} · Selbstkontrolle: {n_selbst})")
    print(f"Themen: {len(by_theme)}")
    for t in sorted(by_theme):
        print(f"   · {t}: {by_theme[t]}")
    print(f"Schwierigkeit  leicht/mittel/schwer: {by_diff[1]}/{by_diff[2]}/{by_diff[3]}")

    if errors:
        print(f"\n❌ {len(errors)} FEHLER – Datei NICHT committen:")
        for e in errors:
            print("   ! " + e)
        sys.exit(1)
    print("\n✅ Keine Fehler. Datei ist gueltig.")
    sys.exit(0)

if __name__ == "__main__":
    main()
