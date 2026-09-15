import sys
import AffParser
import sqlite3
from Creating_SQLite_Tables import DB_PATH
#from MIHUB2 import affiliations

sys.path.insert(0, ".")          # parser.py im gleichen Ordner
from AffParser import parseAffiliation, splitAffiliations, removeNoise, extractGeoField
from collections import Counter
from GeoResolver import loadGeoNames, resolveCity
from RorResolver import queryRor
import importlib
import pycountry
import re

_CITY_MAP = loadGeoNames()

importlib.reload(AffParser)


"""
Resolver Stufe 1: Ländercode aus einem Geo-Kandidaten extrahieren.

Reihenfolge:
  1. Abkürzungs-Dictionary  (Sonderfälle & nicht-englische Namen)
  2. pycountry              (englische ISO-Standardnamen)
"""

# ── Dictionary ────────────────────────────────────────────────────────────────

ABBREVIATIONS = {

    # ── Europa – deutschsprachig ──────────────────────────────────────────────
    "Deutschland":                  "DE",
    "Österreich":                   "AT",
    "Schweiz":                      "CH",

    # ── Europa – westlich ─────────────────────────────────────────────────────
    "Grossbritannien":              "GB",
    "Großbritannien":               "GB",
    "UK":                           "GB",
    "U.K.":                         "GB",
    "England":                      "GB",
    "Scotland":                     "GB",
    "Wales":                        "GB",
    "Northern Ireland":             "GB",
    "Frankreich":                   "FR",
    "Niederlande":                  "NL",
    "The Netherlands":              "NL",
    "Holland":                      "NL",
    "Belgien":                      "BE",
    "Spanien":                      "ES",
    "Italien":                      "IT",
    "Portugal":                     "PT",
    "Irland":                       "IE",
    "Luxemburg":                    "LU",
    "Liechtenstein":                "LI",
    "Monaco":                       "MC",
    "Andorra":                      "AD",
    "Malta":                        "MT",

    # ── Europa – nordisch ─────────────────────────────────────────────────────
    "Dänemark":                     "DK",
    "Norwegen":                     "NO",
    "Schweden":                     "SE",
    "Finnland":                     "FI",
    "Island":                       "IS",

    # ── Europa – östlich ──────────────────────────────────────────────────────
    "Polen":                        "PL",
    "Tschechien":                   "CZ",
    "Czech Republic":               "CZ",
    "Tschechoslowakei":             "CZ",
    "Slowakei":                     "SK",
    "Ungarn":                       "HU",
    "Rumänien":                     "RO",
    "Bulgarien":                    "BG",
    "Kroatien":                     "HR",
    "Slowenien":                    "SI",
    "Serbien":                      "RS",
    "Bosnien":                      "BA",
    "Bosnia":                       "BA",
    "Nordmazedonien":               "MK",
    "North Macedonia":              "MK",
    "Macedonia":                    "MK",
    "Montenegro":                   "ME",
    "Kosovo":                       "XK",
    "Albanien":                     "AL",
    "Moldau":                       "MD",
    "Weißrussland":                 "BY",
    "Belarus":                      "BY",
    "Ukraine":                      "UA",
    "Estland":                      "EE",
    "Lettland":                     "LV",
    "Litauen":                      "LT",

    # ── Europa – Russland ─────────────────────────────────────────────────────
    "Russland":                     "RU",
    "Russia":                       "RU",
    "Russian Federation":           "RU",

    # ── Nordamerika ───────────────────────────────────────────────────────────
    "USA":                          "US",
    "U.S.A.":                       "US",
    "U.S.A":                        "US",
    "U.S.":                         "US",
    "United States":                "US",
    "United States of America":     "US",
    "Kanada":                       "CA",
    "Mexiko":                       "MX",

    # ── Mittelamerika & Karibik ───────────────────────────────────────────────
    "Kuba":                         "CU",
    "Puerto Rico":                  "PR",
    "Guatemala":                    "GT",
    "Honduras":                     "HN",
    "El Salvador":                  "SV",
    "Nicaragua":                    "NI",
    "Costa Rica":                   "CR",
    "Panama":                       "PA",

    # ── Südamerika ────────────────────────────────────────────────────────────
    "Brasilien":                    "BR",
    "Argentinien":                  "AR",
    "Chile":                        "CL",
    "Kolumbien":                    "CO",
    "Peru":                         "PE",
    "Venezuela":                    "VE",
    "Ecuador":                      "EC",
    "Bolivien":                     "BO",
    "Bolivia":                      "BO",
    "Paraguay":                     "PY",
    "Uruguay":                      "UY",

    # ── Asien – Ostasien ──────────────────────────────────────────────────────
    "Peoples R China":              "CN",
    "People's R China":             "CN",
    "P.R. China":                   "CN",
    "PR China":                     "CN",
    "PRC":                          "CN",
    "P. R. China":                  "CN",
    "P. R. China.":                 "CN",
    "P.R.China":                    "CN",
    "People's Republic of China":   "CN",
    "Mainland China":               "CN",
    "China (Mainland)":             "CN",
    "Hong Kong":                    "HK",
    "Hong Kong SAR":                "HK",
    "Macau":                        "MO",
    "Macao":                        "MO",
    "Taiwan":                       "TW",
    "Republic of China":            "TW",
    "Korea":                        "KR",
    "South Korea":                  "KR",
    "Republic of Korea":            "KR",
    "North Korea":                  "KP",
    "D.P.R. Korea":                 "KP",
    "DPRK":                         "KP",
    "Japan":                        "JP",
    "Mongolei":                     "MN",

    # ── Asien – Südostasien ───────────────────────────────────────────────────
    "Vietnam":                      "VN",
    "Viet Nam":                     "VN",
    "Thailand":                     "TH",
    "Singapur":                     "SG",
    "Indonesien":                   "ID",
    "Malaysia":                     "MY",
    "Philippinen":                  "PH",
    "Philippines":                  "PH",
    "Myanmar":                      "MM",
    "Burma":                        "MM",
    "Kambodscha":                   "KH",
    "Cambodia":                     "KH",
    "Laos":                         "LA",
    "Lao PDR":                      "LA",

    # ── Asien – Südasien ──────────────────────────────────────────────────────
    "Indien":                       "IN",
    "Pakistan":                     "PK",
    "Bangladesch":                  "BD",
    "Bangladesh":                   "BD",
    "Sri Lanka":                    "LK",
    "Nepal":                        "NP",
    "Bhutan":                       "BT",

    # ── Asien – Zentralasien ──────────────────────────────────────────────────
    "Kasachstan":                   "KZ",
    "Kazakhstan":                   "KZ",
    "Usbekistan":                   "UZ",
    "Uzbekistan":                   "UZ",
    "Tadschikistan":                "TJ",
    "Turkmenistan":                 "TM",
    "Kirgisistan":                  "KG",
    "Kyrgyzstan":                   "KG",
    "Armenien":                     "AM",
    "Armenia":                      "AM",
    "Georgien":                     "GE",
    "Aserbaidschan":                "AZ",
    "Azerbaijan":                   "AZ",

    # ── Asien – Naher Osten ───────────────────────────────────────────────────
    "Iran":                         "IR",
    "Islamic Republic of Iran":     "IR",
    "Irak":                         "IQ",
    "Iraq":                         "IQ",
    "Syrien":                       "SY",
    "Syria":                        "SY",
    "Libanon":                      "LB",
    "Lebanon":                      "LB",
    "Israel":                       "IL",
    "Jordanien":                    "JO",
    "Jordan":                       "JO",
    "Saudi-Arabien":                "SA",
    "Saudi Arabia":                 "SA",
    "Jemen":                        "YE",
    "Yemen":                        "YE",
    "Oman":                         "OM",
    "Vereinigte Arabische Emirate": "AE",
    "UAE":                          "AE",
    "Katar":                        "QA",
    "Qatar":                        "QA",
    "Kuwait":                       "KW",
    "Bahrain":                      "BH",
    "Türkei":                       "TR",
    "Turkey":                       "TR",
    "Türkiye":                      "TR",
    "Zypern":                       "CY",
    "Cyprus":                       "CY",

    # ── Afrika – Nordafrika ───────────────────────────────────────────────────
    "Ägypten":                      "EG",
    "Egypt":                        "EG",
    "Marokko":                      "MA",
    "Morocco":                      "MA",
    "Algerien":                     "DZ",
    "Algeria":                      "DZ",
    "Tunesien":                     "TN",
    "Tunisia":                      "TN",
    "Libyen":                       "LY",
    "Libya":                        "LY",
    "Sudan":                        "SD",

    # ── Afrika – westlich ─────────────────────────────────────────────────────
    "Nigeria":                      "NG",
    "Ghana":                        "GH",
    "Senegal":                      "SN",
    "Elfenbeinküste":               "CI",
    "Ivory Coast":                  "CI",
    "Cote d'Ivoire":                "CI",
    "Côte d'Ivoire":                "CI",
    "Kamerun":                      "CM",
    "Cameroon":                     "CM",

    # ── Afrika – östlich ──────────────────────────────────────────────────────
    "Äthiopien":                    "ET",
    "Ethiopia":                     "ET",
    "Kenia":                        "KE",
    "Kenya":                        "KE",
    "Tansania":                     "TZ",
    "Tanzania":                     "TZ",
    "Uganda":                       "UG",
    "Ruanda":                       "RW",
    "Rwanda":                       "RW",

    # ── Afrika – südlich ──────────────────────────────────────────────────────
    "Südafrika":                    "ZA",
    "South Africa":                 "ZA",
    "Simbabwe":                     "ZW",
    "Zimbabwe":                     "ZW",
    "Sambia":                       "ZM",
    "Zambia":                       "ZM",
    "Mosambik":                     "MZ",
    "Mozambique":                   "MZ",
    "Demokratische Republik Kongo": "CD",
    "DR Congo":                     "CD",
    "DRC":                          "CD",

    # ── Ozeanien ─────────────────────────────────────────────────────────────
    "Australien":                   "AU",
    "Neuseeland":                   "NZ",
    "New Zealand":                  "NZ",
    "Papua-Neuguinea":              "PG",
    "Papua New Guinea":             "PG",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def matchAbbreviation(text: str) -> str | None:
    """Schlägt den Text im Abkürzungs-Dictionary nach."""
    return ABBREVIATIONS.get(text.strip(), None)


def matchPycountry(text: str) -> str | None:
    """Sucht den ISO-Ländercode via pycountry (englische Namen)."""
    try:
        results = pycountry.countries.search_fuzzy(text.strip())
        return results[0].alpha_2
    except LookupError:
        return None


def resolveFromWords(text: str, cityMap: dict[str, str]) -> str | None:
    """
    Fallback: scans every single word (back to front) in a text
    and checks it against the dictionary cityMap. Useful for Affiliations like
     "Universitätsklinik Leipzig".
    """
    #splitts on spaces AND dashes like (i.e. Hamburg-Eppendorf)
    words = re.split(r"[\s\-]+", text.strip())
    words = [w.strip(".,;") for w in words if w.strip(".,;")]

    #check back to front (Geo-Names mostly in the last place)
    for word in reversed(words):
        result = matchAbbreviation(word) or resolveCity(word, cityMap)
        if result:
            return result
    return None

# ── Trust Ranking ──────────────────────────────────────────────────────────────
Trust_RANKING = {
    #exact matches
    "dictionary_exact" :    1.0,
    "pycountry_exact":      0.95,     #standard-ISO-Names
    "geonames_exact":       0.90,     #whole String is known City(i.E.Leipzig)
    "ror_exact":            0.85,     # Exact ROR-Name/ID Match

    #partial matches
    "dictionary_word":      0.85,   #found word in dict but String contains more text
    "geonames_word":        0.80,   #City found in Text(i.E. "Univesitätsklinik Leipzig")
    "ror_fuzzy":            0.70,   #ROR found in fuzzy search

    #fallback
    "not_found":            0.0,
}

def resolve(text: str) -> tuple[str | None, str | None, float]:
    """
    returns ISO-3166-1 alpha-2 Country-code, Source for the decision and TrustRanking (or None)
    Order: Dictionary -> pycountry -> GeoNames (cities)
    """
    if matchAbbreviation(text):
        return matchAbbreviation(text), "dictionary_exact", Trust_RANKING["dictionary_exact"]
    if matchPycountry(text):
        return matchPycountry(text), "pycountry_exact", Trust_RANKING["pycountry_exact"]
    city = resolveCity(text, _CITY_MAP)
    if city:
        return city, "geonames_exact", Trust_RANKING["geonames_exact"]
    word = resolveFromWords(text, _CITY_MAP)
    if word:
        return word, "geonames_word", Trust_RANKING["geonames_word"]
    return None, "Not found", Trust_RANKING["not_found"]



# ── Tests (only with direct call) ──────────────────────────────────────────

# if __name__ == "__main__":
#    tests = [
#        "Germany", "GERMANY", "Deutschland", "Schweiz",
#        "Österreich", "UK", "USA", "Korea", "North Korea", "Berlin",
#    ]
#    for t in tests:
#        print(f"{t:15} → {resolve(t)}")
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
cur.execute("DELETE FROM geo_zuordnung")
cur.execute("DELETE FROM laender_quarantaene")
con.commit()
con.close()
print("geo_zuordnung und laender_quarantaene Tabellen geleert")
# ── Main Pipeline ────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_PATH)
cur = con.cursor()

#aus "artikel" lesen
cur.execute("SELECT pmid, affiliations FROM artikel WHERE affiliations IS NOT NULL;")
artikel_rows = cur.fetchall()
print(f"Verarbeite {len(artikel_rows):,} Artikel")



# Step 1 - collects every candidate and counts them (before getting deduplicated)
kandidat_counter = Counter()
kandidat_pmids = {}

for pmid, affiliations in artikel_rows:
    for single in splitAffiliations(affiliations):
        clean = removeNoise(single)
        if not clean:
            continue
        field = extractGeoField(clean)
        field = re.sub(r'^\d{4,6}}\s+', '', field).strip()
        if field and len(field) >= 3:
            kandidat_counter[field] += 1
            if field not in kandidat_pmids:
                kandidat_pmids[field] = (pmid, single)

print(f"{sum(kandidat_counter.values()):,} Kandidaten gesamt, wovon {len(kandidat_counter):,} einzigartig sind.")

# Step 2 - resolve and save only unique candidates
batch_geo = []          #trust >= 0.80
batch_manual = []      #trust < 0.80 / no Geo-candidate

for i, (kandidat, count) in enumerate(kandidat_counter.items()):
    country, source, trust_ranking = resolve(kandidat)
    pmid, affiliation_roh, = kandidat_pmids[kandidat]

    # setting the reason
    if country is None:
        reason = "not_found"
    elif trust_ranking < 0.90:
        reason = "low_trust"
    else:
        reason = None

    entry = (
        pmid,
        kandidat,
        affiliation_roh,
        country if country else "not found",
        source,
        trust_ranking,
        count
    )

    if reason:
        batch_manual.append(entry + (reason,))
    else:
        batch_geo.append(entry)

#alle 10.000 Zeilen in DB schreiben
    if len(batch_geo) >= 10000:
        cur.executemany("""
                        INSERT INTO geo_zuordnung
                        (pmid, affiliation_kandidat, affiliation_raw, land, quelle, trust_ranking, count)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, batch_geo)
        con.commit()
        print(f"{i:,}/{len(kandidat_counter):,} Artikel verarbeitet", flush=True)
        batch_geo = []

        if len(batch_manual) >= 10000:
            cur.executemany("""
                            INSERT INTO laender_quarantaene
                            (pmid, affiliation_candidate, affiliation_raw, country, source, trust_ranking, count, reason)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, batch_manual)
            con.commit()
            batch_manual = []

#den Rest rausschreiben
if batch_geo:
    cur.executemany("""
        INSERT INTO geo_zuordnung 
        (pmid, affiliation_kandidat, affiliation_raw, land, quelle, trust_ranking, count) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, batch_geo)
    con.commit()
if batch_manual:
    cur.executemany("""
       INSERT INTO laender_quarantaene
        (pmid, affiliation_candidate, affiliation_raw, country, source, trust_ranking, count, reason)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, batch_manual)
    con.commit()
con.close()

print("alle ergebnisse in DB erfolgreich geschrieben")
