import ahocorasick
import re
import sqlite3
import polars as pl
import unicodedata

from datetime import datetime
from Creating_SQLite_Tables import DB_PATH

# ── filling autor_klassifikation table ─────────────────────────────────────────────────────────────────────────────────
def normalize_affiliation(text : str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower()).strip()

def fill_autor_klassifikation(db_path = DB_PATH, batchsize = 10000):        #füllt die autor_klassifikation tabelle mit den Daten aus der artikel Tabelle
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT pmid, authors, affiliations FROM artikel")
    rows = cur.fetchall()
    print(f"{len(rows):,} Publikationen gelesen")

    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ak_pmid_pos ON autor_klassifikation (pmid, autor_position);")
    con.commit()

    batch, mismatch_pmids = [], []
    for pmid, authors_raw, affiliations_raw in rows:
        author_names = [a.strip() for a in (authors_raw or "").split(";") if a.strip()]
        affiliation_texts = (affiliations_raw or "").split(" | ")
        total = len(author_names)
        if total != len(affiliation_texts):
            mismatch_pmids.append(pmid)
        for pos in range(total):
            aff = affiliation_texts[pos] if pos < len(affiliation_texts) else ""
            batch.append((pmid, pos + 1, total, author_names[pos], aff, normalize_affiliation(aff)))
        if len(batch) >= batchsize:
            cur.executemany(""" 
                INSERT OR IGNORE INTO autor_klassifikation
                    (pmid, autor_position, autor_gesamtzahl, autor_name, affiliation_raw, affiliation_normalized)
                    VALUES (?, ?, ?, ?, ?, ?);
            """, batch)
            con.commit(); batch = []
    if batch:
        cur.executemany(""" 
            INSERT OR IGNORE INTO autor_klassifikation
                (pmid, autor_position, autor_gesamtzahl, autor_name, affiliation_raw, affiliation_normalized)
                VALUES (?, ?, ?, ?, ?, ?);
        """, batch)
        con.commit()
    con.close()
    print(f"{len(mismatch_pmids):,} Publikationen haben ungleiche Anzahl von Autoren und Affiliationsangaben")
    return mismatch_pmids

#Rechtsform-Suffixe Parsen um Namensvergleiche zu entrauschen
rechtsformen_suffixe = re.compile(
    r"\b(ggmbh|gmbh|gemeinnützige|e\.?\s?v\.?|ag|kg|co\.?\s?kg|stiftung)\b",
    re.IGNORECASE,
    )

def normalize_name(text:str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = rechtsformen_suffixe.sub("", text)
    text = re.sub(r"[^\w\säöüß-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def build_automation(con):
    automaton = ahocorasick.Automaton()

    # source 1: Hospitals
    df_kh = pl.read_database("SELECT Einrichtungsname, typ FROM ref_hospitals", con)
    for row in df_kh.iter_rows(named = True):
        name = normalize_name(row["Einrichtungsname"])
        if len(name) >= 3:
            automaton.add_word(name, (name, "Klinik", row["typ"]))

    # source 2: organisations and industrial authors
    df_org_indu = pl.read_database("SELECT name, abkuerzung, rechtsform, kategorie, typ FROM organisations_and_industry", con)
    for row in df_org_indu.iter_rows(named = True):
        #full name
        name = normalize_name(row["name"])
        if len(name) >= 4:
            automaton.add_word(name, (name, row["typ"], row["kategorie"] or ""))



        #Abbreviation (if exists as own entry and >= 3)
        #if row["abkuerzung"]:
        #    abbr = row["abkuerzung"].strip()
        #    if len(abbr) >= 3:
        #        automaton.add_word(abbr.lower(), (abbr, row["typ"], row["kategorie"] or ""))



    #df = pl.read_database("SELECT Einrichtungsname, typ FROM ref_hospitals", con)
    #automaton = ahocorasick.Automaton()
    #for row in df.iter_rows(named = True):
    #    name = normalize_name(row["Einrichtungsname"])
    #    if len(name) < 4:   #skips too short (generic) names
    #        continue
    #    automaton.add_word(name, (name, row["typ"]))

    automaton.make_automaton()
    return automaton

def classify_stufe_1(db_path= DB_PATH):
    con = sqlite3.connect(db_path)
    automaton = build_automation(con)

    cur = con.cursor()
    cur.execute("""
                    SELECT id, affiliation_normalized
                    FROM autor_klassifikation
                    WHERE trust_ranking = 0 AND affiliation_normalized != ''
                """)
    rows = cur.fetchall()
    print(f"{len(rows):,} unclassified rows checked against ref_hospitals + organisations_and_industry")

    now = datetime.now().isoformat()
    updates = []
    for id_, aff in rows:
        best_match, best_len = None, 0
        for _, (name, typ, sub) in automaton.iter(aff):
            if len(name) > best_len:        #longest match wins (specified)
                best_match, best_len = (name, typ, sub), len(name)
        if best_match:
            name, typ, sub = best_match
            updates.append((
                typ, 3, False, "ref_hospitals_exact", f"{name} (typ={typ}, sub={sub})", now, id_
            ))
    cur.executemany("""
                        UPDATE autor_klassifikation
                        SET kategorie = ?, trust_ranking = ?, pruefung_notwendig = ?, match_methode = ?, match_treffer = ?, klassifiziert_am = ?
                        WHERE id = ?
                    """, updates)
    con.commit()
    con.close()
    print(f"{len(updates):,} Zeilen als 'klinik' (Konfidenzstufe 3) klassifiziert")

if __name__ == "__main__":
    fill_autor_klassifikation()
    classify_stufe_1()

    con = sqlite3.connect(DB_PATH)
    df_check = pl.read_database("""
        SELECT kategorie, trust_ranking, COUNT(*) AS anzahl
        FROM autor_klassifikation
        GROUP BY kategorie, trust_ranking
        ORDER BY anzahl DESC
    """, con)
    con.close()
    print(df_check)

# ── publikation aggregieren ────────────────────────────────────────────────────────────────────────────────────────────
def is_latin(text: str) -> bool:
    if not text:
        return True
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    return (latin / len(letters)) >= 0.5

def fill_publikation_klassifikation(db_path = DB_PATH, batchsize = 10000):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute("SELECT pmid, title FROM artikel")
    titel_map = dict(cur.fetchall())

    cur.execute("SELECT pmid, autor_position FROM autor_klassifikation WHERE kategorie = 'niedergelassen' ORDER BY pmid, autor_position")
    niedergelassen_map = {}
    for pmid, pos in cur.fetchall():
        niedergelassen_map.setdefault(pmid, []).append(str(pos))

    batch = []
    for pmid, title in titel_map.items():
        positionen = niedergelassen_map.get(pmid)
        batch.append((pmid, positionen is not None, ",".join(positionen) if positionen else None, is_latin(title)))
        if len(batch) >= batchsize:
            cur.executemany("""
                INSERT OR REPLACE INTO publikation_klassifikation 
                (pmid, niedergelassen_beteiligt, niedergelassen_pos, lateinschrift)
                VALUES (?, ?, ?, ?)
            """, batch)
            con.commit(); batch = []
    if batch:
        cur.executemany("""
            INSERT OR REPLACE INTO publikation_klassifikation
            (pmid, niedergelassen_beteiligt, niedergelassen_pos, lateinschrift)
            VALUES (?, ?, ?, ?)
        """, batch)
        con.commit()
    con.close()
    print(f"{len(titel_map):,} Publikationen in publikation_klassifikation geschrieben")

# ── Step 2 of Autor classification ─────────────────────────────────────────────────────────────────────────────────────
    # checks against typical pattens of federal institures and industrial publications

#case sensitive as lowercase may lead to errors (trust ranking = 2)
BEHOERDE_ABKUERZUNGEN = [
    re.compile(rf"\b{re.escape(a)}\b") for a in [
        "RKI", "BfArM", "PEI", "BfR", "BAuA", "UBA", "BfS", "IQWiG",
        "LGL", "LAGeSo", "NLGA", "BZgA", "BIPAM", "BVL", "LZG",
        "BMG", "BMEL", "BMUV", "BMBF",
    ]
]

#federal institutional phrases (trust ranking = 1)
BEHOERDE_PHRASEM = [ re.compile(p, re.IGNORECASE) for p in [
        r"\bFederal Institute\b", r"\bFederal Agency\b", r"\bFederal Ministry\b",
    r"\bBundesinstitut\b", r"\bBundesamt\b", r"\bBundesanstalt\b",
    r"\bBundesministerium\b", r"\bLandesamt\b",
    r"\bLandesuntersuchungsamt\b", r"\bLandesgesundheitsamt\b",
    r"\bSanitätsdienst\b",
    ]
]

#industrial legal forms (trust ranking = 1)
#case sensitive as "AG" ≠ "ag", "Ltd" ≠ "ltd"
INDUSTRIE_RECHTSFORMEN = [
    re.compile(rf"(?!<\w){re.escape(a)}(?!<\w)") for a in [
        "GmbH", "AG", "Inc.", "Inc", "Ltd.", "Ltd", "Corp.", "Corp",
        "Corporation", "SE", "S.A.", "NV", "KGaA", "SpA",
    ]
]

# industrial branches (trust ranking = 1)
INDUSTRIE_BRANCHE = [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in [
    "Pharmaceuticals", "Pharma", "Biotech", "Therapeutics", "Biosciences",
    "Diagnostics", "Laboratories", "Labs", "Life Sciences", "HealthCare",
    ]
]

def first_match(text, patterns):
    #retruns first match or None
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0)
    return None

def classify_stufe_2(db_path = DB_PATH):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    #only non classified lines
    cur.execute("""
        SELECT id, affiliation_raw
        FROM autor_klassifikation
        WHERE trust_ranking = 0 AND affiliation_raw IS NOT NULL AND affiliation_raw != ''
    """)
    rows = cur.fetchall()
    print(f"{len(rows):,} unclassified rows checked against Behörde/Industrie-Muster")

    now = datetime.now().isoformat()
    updates = []

    for id_, aff in rows:
        # order = Priority (speizific before generic)
        hit = first_match(aff, BEHOERDE_ABKUERZUNGEN)
        if hit:
            updates.append(("Behoerde", 2, True, "behoerde_abkuerzung", hit, now, id_))
            continue

        hit = first_match(aff, BEHOERDE_PHRASEM)
        if hit:
            updates.append(("Behoerde", 1, True, "behoerde_phrase", hit, now, id_))
            continue

        hit = first_match(aff, INDUSTRIE_RECHTSFORMEN)
        if hit:
            updates.append(("Industrie", 1, True, "Industrie_rechtsform", hit, now, id_))
            continue

        hit = first_match(aff, INDUSTRIE_BRANCHE)
        if hit:
            updates.append(("Industrie", 1, True, "Industrie_branche", hit, now, id_))
            continue

    cur.executemany("""
        UPDATE autor_klassifikation
        SET kategorie = ?, trust_ranking = ?, pruefung_notwendig = ?, match_methode = ?, match_treffer = ?, klassifiziert_am = ?
        WHERE id = ?
    """, updates)
    con.commit()

    # overview after step 2
    df_check = pl.read_database("""
    SELECT kategorie,  trust_ranking, COUNT(*) AS anzahl
    FROM autor_klassifikation
    GROUP BY kategorie, trust_ranking
        ORDER BY anzahl DESC
    """, con)
    con.close()
    print(f"{len(updates):,} Zeilen per Muster klassifiziert(trust_ranking 1-2, pruefung_notwendig = True)")
    print(df_check)

def unistr(s): return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1),16)), s)
con = sqlite3.connect('stat.db'); con.create_function('unistr', 1, unistr)
for f in ['geo_zuordnung_export_02.sql','laender_quarantaene_export.sql']:
    con.executescript(open(f, encoding='utf-8').read())
con.commit()


SELECT quelle, trust_ranking, COUNT(*) AS kandidaten, SUM(count) AS vorkommen
FROM geo_zuordnung GROUP BY 1,2 ORDER BY 2 DESC;

-- Fehlerverdacht: häufigste Kandidaten der unsicheren Stufen
SELECT affiliation_kandidat, land, count FROM geo_zuordnung
WHERE trust_ranking <= 0.9 ORDER BY count DESC LIMIT 50;

-- Konsistenz
SELECT affiliation_kandidat FROM geo_zuordnung
GROUP BY 1 HAVING COUNT(DISTINCT land) > 1;

if __name__ == "__main__":
    classify_stufe_2()