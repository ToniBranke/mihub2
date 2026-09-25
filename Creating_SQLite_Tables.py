import sqlite3
import polars as pl     #because SQL doesn't have a native xlsx-Data import
from yaml import reader
import os

DB_PATH = "mihub2.db"

def createDatabase():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS artikel (
            pmid                    TEXT PRIMARY KEY,
            title                   TEXT,
            first_author            TEXT,
            authors                 TEXT,
            affiliations            TEXT,
            link                    TEXT
        );

        CREATE TABLE IF NOT EXISTS geo_zuordnung (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            pmid                    TEXT,
            affiliation_kandidat    TEXT,
            affiliation_raw         TEXT,
            land                    TEXT,
            quelle                  TEXT,
            trust_ranking           REAL,
            count                   INTEGER DEFAULT 1
        );
            
        CREATE TABLE IF NOT EXISTS autor_klassifikation(
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            pmid                    TEXT NOT NULL REFERENCES artikel(pmid),
            autor_position          INTEGER NOT NULL,
            autor_gesamtzahl        INTEGER NOT NULL,
            autor_name              TEXT,
            affiliation_raw          TEXT,
            affiliation_normalized  TEXT,
            kategorie               TEXT,
            trust_ranking           INTEGER NOT NULL DEFAULT 0,
            pruefung_notwendig      BOOLEAN,
            match_methode           TEXT,
            match_treffer           TEXT,
            klassifiziert_am        TIMESTAMP
        );
            
            CREATE TABLE IF NOT EXISTS kategorie_quarantäne(
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            autor_klassifikation_id INTEGER NOT NULL REFERENCES autor_klassifikation(id),
            pmid                    TEXT NOT NULL REFERENCES artikel(pmid),
            autor_position          INTEGER NOT NULL,
            autor_name              TEXT,
            affiliation_raw         TEXT,
            kategorie_vermutung     TEXT,
            trust_ranking           INTEGER NOT NULL,
            match_methode           TEXT,
            match_treffer           TEXT,
            aufgenommen_am          TIMESTAMP,
            geprüft_von             TEXT,
            geprüft_am              TIMESTAMP,
            kategorie_final         TEXT,
            nicht_klassifizierbar   BOOLEAN DEFAULT 0,
            pruefungsvermerk        TEXT
        );
            
            CREATE TABLE IF NOT EXISTS publikation_klassifikation(
            pmid                    TEXT PRIMARY KEY REFERENCES artikel(pmid),
            niedergelassen_beteiligt BOOLEAN,
            niedergelassen_pos      TEXT,
            lateinschrift           TEXT
        );
            
            CREATE TABLE IF NOT EXISTS laender_quarantaene(
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            pmid                    TEXT,
            affiliation_candidate    TEXT,  
            affiliation_raw         TEXT,
            country                 TEXT,
            source                  TEXT,
            trust_ranking           REAL,
            count                   INTEGER DEFAULT 1,
            reason                   TEXT,       -- warum manuell: "not_found", "low_trust", "no_geo"
            status                  TEXT DEFAULT 'offen'    --offen / geprueft / verworfen´              
            );
    """)

    con.commit()
    con.close()
    print("Database created successfully")


# ── creating DB-table for German Hospitals Excell list ────────────────────────────────────────────────────────
def load_reference_tables():
    # importing Excell spreadsheet into SQLite table for better Matching
    excel_path = "krankenhausverzeichnis-3500100247005.xlsx"

    #filtering the actually needed columns
    selected_columns = ["Einrichtungsname", "Standortname", "Straße", "Hausnummer", "PLZ", "Ort", "Trägername", "typ"]

    #importing Hospitals (header is in Row 3 -> header_row = 2 in Polar/calamine (used for .xslx)
    df_kh = (
        pl.read_excel(
            excel_path,
            sheet_name=" KHV_2024",
            read_options={"header_row": 2},
        )
        .rename({"KH_Name": "Einrichtungsname"})
        .select(
            [
                "Einrichtungsname",
                "Standortname",
                "Straße",
                "Hausnummer",
                "PLZ",
                "Ort",
                "Trägername",
            ]
        )
        .with_columns(pl.lit("Krankenhaus").alias("typ"))
    )

    #importing Reha-clinics
    df_rh = (
        pl.read_excel(
            excel_path,
            sheet_name="RHV_2024",
            read_options={"header_row": 2}
        )
        .rename({"RH_Name": "Einrichtungsname"})
        .with_columns(pl.lit(None).cast(pl.String).alias("Standortname"))
        .select(
            [
                "Einrichtungsname",
                "Standortname",
                "Straße",
                "Hausnummer",
                "PLZ",
                "Ort",
                "Trägername",
            ]
        )
        .with_columns(pl.lit("Reha").alias("typ"))
    )

    #filter significant columns and merge both tables
    df_hospitals = pl.concat(
        [df_kh.select(selected_columns), df_rh.select(selected_columns)]
    )

    #cleaning Data from: empty data, and obsolete spaces
    df_hospitals = df_hospitals.filter(
        pl.col("Einrichtungsname").is_not_null()
    ).with_columns(
        [
            pl.col("Einrichtungsname").str.strip_chars(),
            pl.col("Ort").str.strip_chars(),
            pl.col("PLZ").cast(pl.String).str.zfill(5),
        ]
    )

    #writing in SQL Table
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS ref_hospitals;")

    cursor.execute("""
        CREATE TABLE ref_hospitals(
            Einrichtungsname    TEXT,
            Standortname        TEXT,
            Straße              TEXT,
            Hausnummer          TEXT,
            PLZ                 TEXT,
            Ort                 TEXT,
            Trägername          TEXT,
            typ                 TEXT
        );  
    """)

    cursor.executemany("INSERT INTO ref_hospitals VALUES(?, ?, ?, ?, ?, ?, ?, ?);",
                       df_hospitals.rows(),
                    )
    conn.commit()
    conn.close()

    # ── fill organisations_&_industry table ────────────────────────────────────────────────────────────────────────────

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS organisations_and_industry;")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organisations_and_industry(
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                name                    TEXT NOT NULL,
                abkuerzung              TEXT,
                rechtsform              TEXT,
                kategorie               TEXT,
                typ                     TEXT NOT NULL
            );
       """)

    cursor.execute(f"""
        INSERT INTO organisations_and_industry(name, abkuerzung, rechtsform, kategorie, typ)
        VALUES
        ('Pfizer', NULL, 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('Novartis', NULL, 'AG', 'Pharma & Biotech', 'Industrie'),
        ('F. Hoffmann-La Roche', 'Roche', 'AG', 'Pharma & Biotech', 'Industrie'),
        ('AstraZeneca', NULL, 'plc', 'Pharma & Biotech', 'Industrie'),
        ('Sanofi', NULL, 'S.A.', 'Pharma & Biotech', 'Industrie'),
        ('Johnson & Johnson', 'J&J', 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('Janssen Pharmaceuticals', 'Janssen', 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('Merck & Co.', 'MSD', 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('Eli Lilly', NULL, 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('Bristol Myers Squibb', 'BMS', 'Corp.', 'Pharma & Biotech', 'Industrie'),
        ('AbbVie', NULL, 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('GlaxoSmithKline', 'GSK', 'plc', 'Pharma & Biotech', 'Industrie'),
        ('Gilead Sciences', NULL, 'Inc.', 'Pharma & Biotech', 'Industrie'),
        ('Novo Nordisk', NULL, 'A/S', 'Pharma & Biotech', 'Industrie'),
        ('Bayer', NULL, 'AG', 'Pharma & Biotech', 'Industrie'),
        ('Boehringer Ingelheim', NULL, 'GmbH', 'Pharma & Biotech', 'Industrie'),
        ('BioNTech', NULL, 'SE', 'Pharma & Biotech', 'Industrie'),
        ('CureVac', NULL, 'SE', 'Pharma & Biotech', 'Industrie'),
        ('Evotec', NULL, 'SE', 'Pharma & Biotech', 'Industrie'),
        ('Qiagen', NULL, 'N.V.', 'Pharma & Biotech', 'Industrie'),
        ('MorphoSys', NULL, 'AG', 'Pharma & Biotech', 'Industrie'),
        ('Fresenius Kabi', NULL, 'AG', 'Pharma & Biotech', 'Industrie'),
        ('Siemens Healthineers', NULL, 'AG', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Philips Healthcare', 'Philips', 'N.V.', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('GE HealthCare', 'GE', 'Inc.', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Medtronic', NULL, 'plc', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Boston Scientific', NULL, 'Corp.', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Abbott Laboratories', 'Abbott', 'Inc.', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Roche Diagnostics', NULL, 'GmbH', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Carl Zeiss Meditec', 'Zeiss', 'AG', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Drägerwerk', 'Dräger', 'KGaA', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Stryker Corporation', 'Stryker', 'Corp.', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('B. Braun Melsungen', 'B. Braun', 'SE', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('Olympus Medical Systems', 'Olympus', 'Corp.', 'Medizintechnik & Diagnostik', 'Industrie'),
        ('IQVIA', NULL, 'Inc.', 'Auftragsforschung (CRO)', 'Industrie'),
        ('ICON', NULL, 'plc', 'Auftragsforschung (CRO)', 'Industrie'),
        ('Syneos Health', NULL, 'Inc.', 'Auftragsforschung (CRO)', 'Industrie'),
        ('Parexel', NULL, 'Inc.', 'Auftragsforschung (CRO)', 'Industrie'),
        ('Labcorp', 'Covance', 'Inc.', 'Auftragsforschung (CRO)', 'Industrie'),
        ('Charles River Laboratories', NULL, 'Inc.', 'Auftragsforschung (CRO)', 'Industrie'),
        ('Medpace', NULL, 'Inc.', 'Auftragsforschung (CRO)', 'Industrie'),
        ('Eurofins Scientific', 'Eurofins', 'SE', 'Großlabore & Genetik', 'Industrie'),
        ('Synlab', NULL, 'AG', 'Großlabore & Genetik', 'Industrie'),
        ('Sonic Healthcare', NULL, 'Ltd.', 'Großlabore & Genetik', 'Industrie'),
        ('Limbach Gruppe', 'Limbach', 'SE', 'Großlabore & Genetik', 'Industrie'),
        ('Illumina', NULL, 'Inc.', 'Großlabore & Genetik', 'Industrie'),
        ('Thermo Fisher Scientific', 'Thermo Fisher', 'Inc.', 'Großlabore & Genetik', 'Industrie'),
        ('Myriad Genetics', NULL, 'Inc.', 'Großlabore & Genetik', 'Industrie'),
        ('Google Health', 'Google DeepMind', 'LLC', 'Digital Health & KI', 'Industrie'),
        ('IBM Research', 'Watson Health', 'Corp.', 'Digital Health & KI', 'Industrie'),
        ('Tempus Labs', 'Tempus', 'Inc.', 'Digital Health & KI', 'Industrie'),
        ('Owkin', NULL, 'Inc.', 'Digital Health & KI', 'Industrie'),
        ('Ada Health', NULL, 'GmbH', 'Digital Health & KI', 'Industrie'),
        ('Kaia Health', NULL, 'GmbH', 'Digital Health & KI', 'Industrie'),
        ('Robert Koch-Institut', 'RKI', NULL, 'Bundesbehörde - Gesundheit', 'Behörde'),
        ('Bundesinstitut für Arzneimittel und Medizinprodukte', 'BfArM', NULL, 'Bundesbehörde - Gesundheit', 'Behörde'),
        ('Paul-Ehrlich-Institut', 'PEI', NULL, 'Bundesbehörde - Gesundheit', 'Behörde'),
        ('Bundesinstitut für Prävention und Aufklärung in der Medizin', 'BIPAM', NULL, 'Bundesbehörde - Gesundheit', 'Behörde'),
        ('Bundeszentrale für gesundheitliche Aufklärung', 'BZgA', NULL, 'Bundesbehörde - Gesundheit', 'Behörde'),
        ('Institut für Qualität und Wirtschaftlichkeit im Gesundheitswesen', 'IQWiG', NULL, 'Bundesbehörde - Gesundheit', 'Behörde'),
        ('Bundesinstitut für Risikobewertung', 'BfR', NULL, 'Bundesbehörde - Umwelt & Arbeit', 'Behörde'),
        ('Bundesanstalt für Arbeitsschutz und Arbeitsmedizin', 'BAuA', NULL, 'Bundesbehörde - Umwelt & Arbeit', 'Behörde'),
        ('Umweltbundesamt', 'UBA', NULL, 'Bundesbehörde - Umwelt & Arbeit', 'Behörde'),
        ('Bundesamt für Strahlenschutz', 'BfS', NULL, 'Bundesbehörde - Umwelt & Arbeit', 'Behörde'),
        ('Bundesamt für Verbraucherschutz und Lebensmittelsicherheit', 'BVL', NULL, 'Bundesbehörde - Umwelt & Arbeit', 'Behörde'),
        ('Institut für Mikrobiologie der Bundeswehr', 'InstMikroBioBw', NULL, 'Bundeswehr - Sanitätsdienst', 'Behörde'),
        ('Institut für Radiobiologie der Bundeswehr', 'InstRadiobioBw', NULL, 'Bundeswehr - Sanitätsdienst', 'Behörde'),
        ('Institut für Pharmakologie und Toxikologie der Bundeswehr', 'InstPharmToxBw', NULL, 'Bundeswehr - Sanitätsdienst', 'Behörde'),
        ('Zentrales Institut des Sanitätsdienstes der Bundeswehr', 'ZInstSanBw', NULL, 'Bundeswehr - Sanitätsdienst', 'Behörde'),
        ('Bayerisches Landesamt für Gesundheit und Lebensmittelsicherheit', 'LGL', NULL, 'Landesbehörde', 'Behörde'),
        ('Landesgesundheitsamt Baden-Württemberg', 'LGA', NULL, 'Landesbehörde', 'Behörde'),
        ('Landesamt für Gesundheit und Soziales Berlin', 'LAGeSo', NULL, 'Landesbehörde', 'Behörde'),
        ('Niedersächsisches Landesgesundheitsamt', 'NLGA', NULL, 'Landesbehörde', 'Behörde'),
        ('Landeszentrum Gesundheit Nordrhein-Westfalen', 'LZG.NRW', NULL, 'Landesbehörde', 'Behörde'),
        ('Bundesministerium für Gesundheit', 'BMG', NULL, 'Bundesministerium', 'Behörde'),
        ('Bundesministerium für Ernährung und Landwirtschaft', 'BMEL', NULL, 'Bundesministerium', 'Behörde'),
        ('Bundesministerium für Umwelt, Naturschutz, nukleare Sicherheit und Verbraucherschutz', 'BMUV', NULL, 'Bundesministerium', 'Behörde'),
        ('Bundesministerium für Bildung und Forschung', 'BMBF', NULL, 'Bundesministerium', 'Behörde');
    """)
    conn.commit()
    conn.close()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT affiliation_kandidat, affiliation_raw, count
        FROM geo_zuordnung 
        WHERE quelle = 'geonames_word'
        ORDER BY count DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"Kandidat: {repr(row[0])}")
        print(f"Roh:      {row[1][:80]}")
        print(f"Count:    {row[2]:,}")
        print()
    con.close()

    print(os.getcwd())
    print(f"Saved {len(df_hospitals)} Clinics into 'ref_hospitals' successfully!")

if __name__ == "__main__":
    createDatabase()
    load_reference_tables()

