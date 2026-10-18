import ahocorasick
import re
import sqlite3
import polars as pl
import unicodedata
from pathlib import Path

from datetime import datetime

DB_PATH = str(Path(__file__).with_name("mihub2.db"))
MVZ_KONTEXT = re.compile(r"(?<!\w)MVZ(?!\w)", re.IGNORECASE)

KONTAKT_ADRESSEN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)|"
    r"(?<!\w)(?:https?://|www\.)\S+",
    re.IGNORECASE
)

PRAXIS_KANDIDAT = re.compile(
    r"(?<!\w)(?:Private Practice|Privatpraxis|Gemeinschaftspraxis|"
    r"Facharztpraxis|Schwerpunktpraxis|GP Surgery)(?!\w)|"
    r"(?<!\w)Praxis\s+für\s+\w+",
    re.IGNORECASE,
)
GMBH_RECHTSFORM = re.compile(r"(?<!\w)g?gmbh(?!\w)", re.IGNORECASE)

# ── filling autor_klassifikation table ─────────────────────────────────────────────────────────────────────────────────
def normalize_affiliation(text: str) -> str:
    return normalize_name(text)

def fill_autor_klassifikation(db_path=DB_PATH, batchsize=10000):
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ak_pmid_pos "
            "ON autor_klassifikation (pmid, autor_position)"
        )
        con.commit()

        read_cur = con.execute("SELECT pmid, authors, affiliations FROM artikel")
        write_cur = con.cursor()
        insert_sql = """
            INSERT OR IGNORE INTO autor_klassifikation
                (pmid, autor_position, autor_gesamtzahl, autor_name,
                 affiliation_raw, affiliation_normalized)
            VALUES (?, ?, ?, ?, ?, ?)
        """

        batch = []
        mismatch_pmids = []
        processed = 0

        while True:
            rows = read_cur.fetchmany(1000)
            if not rows:
                break

            for pmid, authors_raw, affiliations_raw in rows:
                processed += 1
                author_names = [
                    a.strip() for a in (authors_raw or "").split(";") if a.strip()
                ]
                affiliation_texts = (affiliations_raw or "").split(" | ")
                total = len(author_names)

                if total != len(affiliation_texts):
                    mismatch_pmids.append(pmid)

                for pos in range(total):
                    aff = affiliation_texts[pos] if pos < len(affiliation_texts) else ""
                    batch.append(
                        (pmid, pos + 1, total, author_names[pos],
                         aff, normalize_affiliation(aff))
                    )

                if len(batch) >= batchsize:
                    write_cur.executemany(insert_sql, batch)
                    con.commit()
                    batch.clear()

        if batch:
            write_cur.executemany(insert_sql, batch)
            con.commit()

        print(f"{processed:,} Publikationen gelesen")
        print(
            f"{len(mismatch_pmids):,} Publikationen haben ungleiche Anzahl "
            "von Autoren und Affiliationsangaben"
        )
        return mismatch_pmids
    finally:
        con.close()

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

HOSPITAL_KLARE_BEGRIFFE = (
    "klinik", "krankenhaus", "krankenhäuser", "hospital",
    "hospiz", "rehabilitation", "rehazentrum", "sanatorium",
    "medical center", "medical centre",
)

def build_automation(con):
    automaton = ahocorasick.Automaton()

    # source 1: Hospitals
    df_kh = pl.read_database("SELECT Einrichtungsname, typ FROM ref_hospitals", con)
    for row in df_kh.iter_rows(named = True):
        name = normalize_name(row["Einrichtungsname"])
        if len(name) >= 3:
            automaton.add_word(name, (name, "Klinik", row["typ"], "ref_hospitals"))

    # source 2: organisations and industrial authors
    df_org_indu = pl.read_database("SELECT name, abkuerzung, rechtsform, kategorie, typ FROM organisations_and_industry", con)
    for row in df_org_indu.iter_rows(named = True):
        #full name
        raw_name = row["name"].strip()
        if raw_name.isupper() and len(raw_name) <= 5:
            continue
        name = normalize_name(raw_name)
        if len(name) >= 4:
            automaton.add_word(name, (name, row["typ"], row["kategorie"] or "", "organisations_and_industry"))



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

def classify_stufe_1(db_path=DB_PATH, batchsize=10000):
    if batchsize < 1:
        raise ValueError("batchsize muss mindestens 1 sein")

    con = sqlite3.connect(db_path)
    try:
        automaton = build_automation(con)
        read_cur = con.cursor()
        write_cur = con.cursor()
        update_sql = """
            UPDATE autor_klassifikation
            SET kategorie = ?, trust_ranking = ?, pruefung_notwendig = ?,
                match_methode = ?, match_treffer = ?, klassifiziert_am = ?
            WHERE id = ?
        """

        last_id = 0
        checked = 0
        classified = 0
        now = datetime.now().isoformat()

        while True:
            read_cur.execute("""
                SELECT id, affiliation_raw, affiliation_normalized
                FROM autor_klassifikation
                WHERE id > ?
                  AND trust_ranking = 0
                  AND affiliation_normalized != ''
                ORDER BY id
                LIMIT ?
            """, (last_id, batchsize))
            rows = read_cur.fetchall()
            if not rows:
                break

            last_id = rows[-1][0]
            checked += len(rows)
            updates = []

            for id_, aff_raw, aff in rows:
                if aff_raw and(
                    "@" in aff_raw or "://" in aff_raw or "www." in aff_raw.lower()
                ):
                    aff = normalize_affiliation(KONTAKT_ADRESSEN.sub(" ", aff_raw))

                if MVZ_KONTEXT.search(aff) or PRAXIS_KANDIDAT.search(aff):
                    continue

                best_match, best_len = None, 0
                gefundene_typen = set()
                for end, (name, typ, sub, quelle) in automaton.iter(aff):
                    start = end - len(name) + 1
                    davor = aff[start - 1] if start > 0 else ""
                    danach = aff[end + 1] if end + 1 < len(aff) else ""

                    if (davor and (davor.isalnum() or davor == "_")) or (
                        danach and (danach.isalnum() or danach == "_")
                    ):
                        continue
                    if typ == "Industrie" and name == "novo nordisk" and re.match(r"\s+foundation\b", aff[end + 1:]):
                        continue
                    gefundene_typen.add(typ)
                    if len(name) > best_len:
                        best_match, best_len = (name, typ, sub, quelle), len(name)

                if best_match:
                    if first_match(UNI_KLINIK_PHRASE.sub(" ", aff), FORSCHUNG_MUSTER):
                        gefundene_typen.add("Forschung")
                    if KLINIK_KONTEXT.search(aff):
                        gefundene_typen.add("Klinik")
                    name, typ, sub, quelle = best_match
                    rechtsform_treffer = None
                    if typ == "Forschung":
                        aff_ohne_kontakt = KONTAKT_ADRESSEN.sub(" ", aff_raw or "")
                        gmbh_treffer = GMBH_RECHTSFORM.search(aff_ohne_kontakt)
                        rechtsform_treffer = (
                            gmbh_treffer.group(0) if gmbh_treffer
                            else first_match(aff_ohne_kontakt, INDUSTRIE_RECHTSFORMEN)
                        )
                    treffer_text = f"{name} (typ={typ}, sub={sub})"

                    kontext_hinweise = []
                    if typ == "Industrie":
                        for muster, hinweis in (
                            (r"(?<!\w)IRCCS(?!\w)", "IRCCS: Klinik/Forschung"),
                            (r"(?<!\w)National Institutes of Health(?!\w)", "NIH: Forschung/Behörde"),
                            (r"(?<!\w)Genetic Alliance(?!\w)", "Genetic Alliance: weitere Organisation"),
                        ):
                            if re.search(muster, aff, re.IGNORECASE):
                                kontext_hinweise.append(hinweis)
                    if len(gefundene_typen) > 1 or rechtsform_treffer or kontext_hinweise:
                        kategorie = None
                        ranking = 1
                        pruefung = True
                        methode = f"ref_konflikt_{typ}"
                        treffer_text += f"; Referenztypen: {', '.join(sorted(gefundene_typen))}"
                        if rechtsform_treffer:
                            treffer_text += f"; zusätzliche Rechtsform: {rechtsform_treffer}"
                        if kontext_hinweise:
                            treffer_text += "; weiterer Kontext: " + ", ".join(kontext_hinweise)
                    elif quelle == "ref_hospitals" and not any(begriff in name for begriff in HOSPITAL_KLARE_BEGRIFFE):
                        kategorie = None
                        ranking = 2
                        pruefung = True
                        methode = "ref_hospitals_name_unklar"
                    else:
                        kategorie = typ
                        ranking = 3
                        pruefung = False
                        methode = f"{quelle}_name_match"

                    updates.append((kategorie, ranking, pruefung, methode, treffer_text, now, id_))

            if updates:
                write_cur.executemany(update_sql, updates)
                con.commit()
                classified += len(updates)

        print(f"{checked:,} unklassifizierte Autorzeilen geprüft")
        print(f"{classified:,} Autorzeilen in Stufe 1 klassifiziert")
    finally:
        con.close()

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

    cur.execute("""
                SELECT pmid, autor_position
                FROM autor_klassifikation
                WHERE kategorie = 'niedergelassen'
                  AND trust_ranking = 3

                UNION

                SELECT pmid, autor_position
                FROM "kategorie_quarantäne"
                WHERE kategorie_final = 'niedergelassen'
                  AND "geprüft_am" IS NOT NULL
                  AND COALESCE(nicht_klassifizierbar, 0) = 0

                ORDER BY pmid, autor_position
                """)

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
        "RKI", "BfArM", "PEI", "BfR", "BAuA", "BfS",
        "LGL", "LAGeSo", "NLGA", "BZgA", "BIPAM", "BVL", "LZG",
        "BMG", "BMEL", "BMUV", "BMBF",
    ]
]

#federal institutional phrases (trust ranking = 1)
BEHOERDE_PHRASEN = [re.compile(p, re.IGNORECASE) for p in [
    r"\bFederal Institute\b(?!\s+of\s+(?:Technology|Education)\b)",
    r"\bFederal Agency\b", r"\bFederal Ministry\b",
    r"\bBundesinstitut\b", r"\bBundesamt\b", r"\bBundesanstalt\b",
    r"\bBundesministerium\b", r"\bLandesamt\b",
    r"\bLandesuntersuchungsamt\b", r"\bLandesgesundheitsamt\b",
    r"\bSanitätsdienst\b", r"(?<!\w)Umweltbundesamt(?!\w)",
    r"(?<!\w)Public Health Agency of Canada(?!\w)",
    r"(?<!\w)Centers for Disease Control and Prevention(?!\w)",
    ]
                    ]

#industrial legal forms (trust ranking = 1)
#case sensitive as "AG" ≠ "ag", "Ltd" ≠ "ltd"
INDUSTRIE_RECHTSFORMEN = [
    re.compile(rf"(?<!\w){re.escape(a)}(?!\w|-\s*\d)" if a == "SE"
    else rf"(?<!\d{{4}}\s)(?<!\w){re.escape(a)}(?!\w)" if a == "AG"
    else rf"(?<!\w){re.escape(a)}(?!\w)"
    )
    for a in [
        "GmbH", "AG", "Inc.", "Inc", "Ltd.", "Limited", "Ltd", "SE", "S.A.", "KGaA", "SpA",
    ]
]

RECHTSFORM_UNKLAR = [
    re.compile(rf"(?<!\w){re.escape(a)}(?!\w)")
    for a in ["Corp.", "Corp", "Corporation", "Ltda.", "Ltda", "NV"]
]

# industrial branches (trust ranking = 1)
INDUSTRIE_BRANCHE = [
    re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
    for t in ["Pharmaceuticals", "Pharma"]
]
INDUSTRIE_STICHWORTE = [
    re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
    for t in [
        "Biotech", "Therapeutics", "Biosciences", "Diagnostics",
        "Laboratories", "Labs", "Life Sciences", "HealthCare",
    ]
]

def first_match(text, patterns):
    #retruns first match or None
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0)
    return None

FORSCHUNG_MUSTER = [
    re.compile(p, re.IGNORECASE) for p in [
        r"(?<!\w)(?:University|Universität|Université|Universidad|"
        r"Universidade|Universit[aà]|Universitat|Universiteit|Universitet|"
        r"Hochschule|Fachhochschule)(?!\w)",
        r"(?<!\w)(?:Research Institute|Forschungsinstitut|"
        r"Federal Institute of Education|Federal Institute of Technology)(?!\w)",
        r"(?<!\w)(?:Academy of Sciences|Academia Sinica|Universitas|"
        r"National Institute for Medical Research)(?!\w)",
        r"(?<!\w)IQWiG(?!\w)",
        r"(?<!\w)(?:UBA[-\s]CONICET|CONICET[-\s]UBA|FCEN[-\s]UBA)(?!\w)",
        r"(?<!\w)(?:Medical School|School of Medicine|National Laboratory)(?!\w)",
    ]
]

UNI_KLINIK_PHRASE = re.compile(
    r"(?<!\w)University Hospitals?(?!\w)|"
    r"(?<!\w)University Medical Cent(?:er|re)(?!\w)|"
    r"Universitäts(?:klinikum|medizin)",
    re.IGNORECASE,
)

KLINIK_KONTEXT = re.compile(
    r"(?<!\w)(?:Hospitals?|Clinics?|Klinik|Klinikum|Krankenhaus|"
    r"Medical Cent(?:er|re)|(?:Complejo|Complexo)"
    r"(?:\s+Asistencial)?\s+Hospitalari[oa])(?!\w)|"
    r"Universitäts(?:klinikum|medizin)|"
    r"(?<!\w)(?:Ospedale|Policlinico)(?!\w)",
    re.IGNORECASE,
)

PRAXIS_KONTEXT = re.compile(
    r"(?<!\w)(?:Praxis|Privatpraxis|Facharztpraxis|"
    r"Gemeinschaftspraxis|Private Practice)(?!\w)",
    re.IGNORECASE,
)

def klinik_konflikt_bei_praxis(aff):
    ohne_adresse = re.sub(
        r"(?<!\w)(?:Am|An der|Im)\s+Krankenhaus\s+\d+\b",
        " ", aff, flags=re.IGNORECASE,
    )
    for teil in re.split(r"\s*(?:;|&)\s*", ohne_adresse):
        treffer = list(KLINIK_KONTEXT.finditer(teil))
        if not treffer:
            continue
        nur_clinic = all(
            t.group(0).casefold() in {"clinic", "clinics"} for t in treffer
        )
        if nur_clinic and PRAXIS_KANDIDAT.search(teil):
            continue
        return True
    return False

def forschung_kandidat(aff):
    # „University Hospital“ ist als Ganzes ein Klinikhinweis.
    ohne_uniklinik = UNI_KLINIK_PHRASE.sub(" ", aff)
    treffer = first_match(ohne_uniklinik, FORSCHUNG_MUSTER)
    if not treffer:
        return None

    konflikte = []
    if KLINIK_KONTEXT.search(aff):
        konflikte.append("Klinik")
    if MVZ_KONTEXT.search(aff):
        konflikte.append("MVZ")
    if PRAXIS_KONTEXT.search(aff):
        konflikte.append("Praxis")
    if first_match(aff, BEHOERDE_ABKUERZUNGEN + BEHOERDE_PHRASEN):
        konflikte.append("Behörde")
    if first_match(aff, INDUSTRIE_RECHTSFORMEN):
        konflikte.append("Industrie")

    if konflikte:
        return (
            None, 1, True, "forschung_konflikt",
            f"Vermutung Forschung: {treffer}; weitere Hinweise: {', '.join(konflikte)}",
        )
    return ("Forschung", 1, True, "forschung_muster", treffer)

def _classify_stufe_2_batch(db_path = DB_PATH, batchsize=10000, last_id=0):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    #only non classified lines
    cur.execute("""
        SELECT id, affiliation_raw
        FROM autor_klassifikation
        WHERE id > ? AND trust_ranking = 0 AND affiliation_raw IS NOT NULL AND affiliation_raw != ''
        ORDER BY id
        LIMIT ?
    """, (last_id, batchsize))
    rows = cur.fetchall()
    if not rows:
        con.close()
        return None

    now = datetime.now().isoformat()
    updates = []

    for id_, aff in rows:
        aff = KONTAKT_ADRESSEN.sub(" ", aff)
        mvz_treffer = MVZ_KONTEXT.search(aff)
        if mvz_treffer:
            konflikte = []
            if KLINIK_KONTEXT.search(aff):
                konflikte.append("Klinik")
            if forschung_kandidat(aff) is not None:
                konflikte.append("Forschung")
            if PRAXIS_KANDIDAT.search(aff):
                konflikte.append("Praxis")
            if first_match(aff, BEHOERDE_ABKUERZUNGEN + BEHOERDE_PHRASEN):
                konflikte.append("Behörde")

            if konflikte:
                updates.append((
                    None, 1, True, "mvz_konflikt",
                    f"Vermutung MVZ; weitere Hinweise: {', '.join(konflikte)}",
                    now, id_
                ))
            else:
                updates.append((
                    "MVZ", 2, True, "mvz_abkuerzung",
                    mvz_treffer.group(0), now, id_
                ))
            continue
        praxis_treffer = PRAXIS_KANDIDAT.search(aff)
        if praxis_treffer:
            konflikte = []
            if klinik_konflikt_bei_praxis(aff):
                konflikte.append("Klinik")
            if forschung_kandidat(aff) is not None:
                konflikte.append("Forschung")
            if first_match(aff, BEHOERDE_ABKUERZUNGEN + BEHOERDE_PHRASEN):
                konflikte.append("Behörde")
            if first_match(aff, INDUSTRIE_RECHTSFORMEN):
                konflikte.append("Industrie")

            methode = "praxis_konflikt" if konflikte else "praxis_kandidat"
            hinweis = praxis_treffer.group(0)
            if konflikte:
                hinweis += f"; weitere Hinweise: {', '.join(konflikte)}"

            updates.append((None, 1, True, methode, hinweis, now, id_))
            continue

        descicion = forschung_kandidat(aff)
        if descicion is not None:
            updates.append((*descicion, now, id_))
            continue

        hit = first_match(aff, BEHOERDE_ABKUERZUNGEN)
        if hit:
            updates.append(("Behoerde", 2, True, "behoerde_abkuerzung", hit, now, id_))
            continue

        hit = first_match(aff, BEHOERDE_PHRASEN)
        if hit:
            updates.append((None, 1, True, "behoerde_phrase", hit, now, id_))
            continue

        klinik_treffer = KLINIK_KONTEXT.search(aff)
        if klinik_treffer:
            updates.append((None, 1, True, "klinik_wort", klinik_treffer.group(0), now, id_))
            continue

        hit = first_match(aff, INDUSTRIE_RECHTSFORMEN)
        if hit:
            updates.append((None, 1, True, "Industrie_rechtsform", hit, now, id_))
            continue

        hit = first_match(aff, INDUSTRIE_BRANCHE)
        if hit:
            updates.append((None, 1, True, "Industrie_branche", hit, now, id_))
            continue

        hit = first_match(aff, RECHTSFORM_UNKLAR)
        if hit:
            updates.append((None, 1, True, "rechtsform_unklar", hit, now, id_))
            continue

        hit = first_match(aff, INDUSTRIE_STICHWORTE)
        if hit:
            updates.append((None, 1, True, "stichwort_unklar", hit, now, id_))
            continue

    cur.executemany("""
        UPDATE autor_klassifikation
        SET kategorie = ?, trust_ranking = ?, pruefung_notwendig = ?, match_methode = ?, match_treffer = ?, klassifiziert_am = ?
        WHERE id = ?
    """, updates)
    con.commit()
    con.close()
    return rows[-1][0], len(rows), len(updates)

    ''' overview after step 2
    df_check = pl.read_database("""
    SELECT kategorie,  trust_ranking, COUNT(*) AS anzahl
    FROM autor_klassifikation
    GROUP BY kategorie, trust_ranking
        ORDER BY anzahl DESC
    """, con)
    con.close()
    print(f"{len(updates):,} Zeilen per Muster klassifiziert(trust_ranking 1-2, pruefung_notwendig = True)")
    print(df_check)'''

def classify_stufe_2(db_path=DB_PATH, batchsize=10000):
    if batchsize < 1:
        raise ValueError("batchsize must be at least 1")
    last_id = 0
    checked = 0
    classified = 0
    while True:
        result = _classify_stufe_2_batch(db_path, batchsize, last_id)
        if result is None:
            break
        last_id, n_checked, n_classified = result
        checked += n_checked
        classified += n_classified
    print(f"{checked:,} offene Zeilen geprüft; {classified:,} Musterzuordnungen geschrieben")

def fill_kategorie_quarantaene(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    try:
        with con:
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_kq_autor
                ON "kategorie_quarantäne"(autor_klassifikation_id)
            """)

            con.execute("""
                INSERT INTO "kategorie_quarantäne" (
                    autor_klassifikation_id, pmid, autor_position,
                    autor_name, affiliation_raw, kategorie_vermutung,
                    trust_ranking, match_methode, match_treffer, aufgenommen_am
                )
                SELECT
                    ak.id, ak.pmid, ak.autor_position,
                    ak.autor_name, ak.affiliation_raw,
                 CASE
                    WHEN ak.match_methode = 'forschung_konflikt' THEN 'Forschung'
                    WHEN ak.match_methode = 'mvz_konflikt' THEN 'MVZ'
                    WHEN ak.match_methode IN ('praxis_kandidat', 'praxis_konflikt') THEN 'niedergelassen'
                    WHEN ak.match_methode = 'ref_hospitals_name_unklar' THEN 'Klinik' 
                    WHEN ak.match_methode LIKE 'ref_konflikt_%' THEN substr(ak.match_methode, 14)
                    WHEN ak.match_methode = 'klinik_wort' THEN 'Klinik'
                    WHEN ak.match_methode = 'behoerde_phrase' THEN 'Behoerde'
                    WHEN ak.match_methode = 'Industrie_branche' THEN 'Industrie'
                    WHEN ak.match_methode = 'Industrie_rechtsform' THEN 'Industrie'
                    ELSE ak.kategorie
                END,
                    ak.trust_ranking, ak.match_methode, ak.match_treffer, ?
                FROM autor_klassifikation AS ak
                WHERE ak.trust_ranking < 3
                ON CONFLICT(autor_klassifikation_id) DO UPDATE SET
                    kategorie_vermutung = excluded.kategorie_vermutung,
                    trust_ranking = excluded.trust_ranking,
                    match_methode = excluded.match_methode,
                    match_treffer = excluded.match_treffer
                WHERE "kategorie_quarantäne"."geprüft_am" IS NULL
            """, (datetime.now().isoformat(),))

            # Bereits sicher klassifizierte Fälle aus der offenen Prüfliste entfernen.
            # Abgeschlossene manuelle Prüfungen bleiben erhalten.
            con.execute("""
                DELETE FROM "kategorie_quarantäne"
                WHERE "geprüft_am" IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM autor_klassifikation AS ak
                      WHERE ak.id = "kategorie_quarantäne".autor_klassifikation_id
                        AND ak.trust_ranking < 3
                  )
            """)
    finally:
        con.close()
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

if __name__ == "__main__":
    classify_stufe_2()
    fill_kategorie_quarantaene()