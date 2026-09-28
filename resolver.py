import sys
import AffParser
import sqlite3
import importlib
import pycountry
import re
import unicodedata
from Creating_SQLite_Tables import DB_PATH
#from MIHUB2 import affiliations

sys.path.insert(0, ".")          # parser.py im gleichen Ordner
from AffParser import parseAffiliation, splitAffiliations, removeNoise, extractGeoField
from collections import Counter
from GeoResolver import loadGeoNames, resolveCity
from RorResolver import queryRor
from pathlib import Path



_CITY_MAP, _CITY_REVIEW = loadGeoNames()

importlib.reload(AffParser)


"""
Resolver Stufe 1: Ländercode aus einem Geo-Kandidaten extrahieren.

Reihenfolge:
  1. Abkürzungs-Dictionary  (Sonderfälle & nicht-englische Namen)
  2. pycountry              (englische ISO-Standardnamen)
"""

# ── Dictionary ────────────────────────────────────────────────────────────────

ABBREVIATIONS = {

    # ── Europa – deutschsprachig ─────────────────────────────────────────────
    "Deutschland": "DE",
    "Österreich": "AT",
    "Schweiz": "CH",
    "Bundesrepublik Deutschland": "DE",
    "Allemagne": "DE",
    "Alemania": "DE",
    "Oesterreich": "AT",
    "Autriche": "AT",
    "Suisse": "CH",
    "Svizzera": "CH",
    "Confoederatio Helvetica": "CH",

    # ── Europa – westlich ────────────────────────────────────────────────────
    "Grossbritannien": "GB",
    "Großbritannien": "GB",
    "UK": "GB",
    "U.K.": "GB",
    "U.K": "GB",
    "Great Britain": "GB",
    "Britain": "GB",
    "England": "GB",
    "Scotland": "GB",
    "Wales": "GB",
    "Northern Ireland": "GB",
    "Frankreich": "FR",
    "Francia": "FR",
    "Niederlande": "NL",
    "The Netherlands": "NL",
    "the Netherlands": "NL",
    "Holland": "NL",
    "Nederland": "NL",
    "Pays-Bas": "NL",
    "Países Bajos": "NL",
    "Belgien": "BE",
    "Belgique": "BE",
    "België": "BE",
    "Spanien": "ES",
    "España": "ES",
    "Espana": "ES",
    "Espagne": "ES",
    "Italien": "IT",
    "Italia": "IT",
    "Italie": "IT",
    "Portugal": "PT",
    "Irland": "IE",
    "Republic of Ireland": "IE",
    "Éire": "IE",
    "Eire": "IE",
    "Luxemburg": "LU",
    "Lëtzebuerg": "LU",
    "Liechtenstein": "LI",
    "Monaco": "MC",
    "Andorra": "AD",
    "Malta": "MT",
    "Vatican City": "VA",
    "Holy See": "VA",
    "Città del Vaticano": "VA",

    # ── Europa – nordisch ────────────────────────────────────────────────────
    "Dänemark": "DK",
    "Danmark": "DK",
    "Norwegen": "NO",
    "Norge": "NO",
    "Schweden": "SE",
    "Sverige": "SE",
    "Finnland": "FI",
    "Suomi": "FI",
    "Island": "IS",
    "Ísland": "IS",
    "Färöer": "FO",
    "Åland": "AX",

    # ── Europa – östlich ─────────────────────────────────────────────────────
    "Polen": "PL",
    "Polska": "PL",
    "Tschechien": "CZ",
    "Czech Republic": "CZ",
    "Česko": "CZ",
    "Česká republika": "CZ",
    "Slowakei": "SK",
    "Slovensko": "SK",
    "Ungarn": "HU",
    "Magyarország": "HU",
    "Rumänien": "RO",
    "România": "RO",
    "Bulgarien": "BG",
    "Kroatien": "HR",
    "Hrvatska": "HR",
    "Slowenien": "SI",
    "Slovenija": "SI",
    "Serbien": "RS",
    "Srbija": "RS",
    "Bosnien": "BA",
    "Bosnia": "BA",
    "Bosna i Hercegovina": "BA",
    "Nordmazedonien": "MK",
    "North Macedonia": "MK",
    "Macedonia": "MK",
    "Montenegro": "ME",
    "Crna Gora": "ME",
    "Kosovo": "XK",
    "Kosova": "XK",
    "Albanien": "AL",
    "Shqipëria": "AL",
    "Moldau": "MD",
    "Weißrussland": "BY",
    "Belarus": "BY",
    "Ukraine": "UA",
    "Estland": "EE",
    "Eesti": "EE",
    "Lettland": "LV",
    "Latvija": "LV",
    "Litauen": "LT",
    "Lietuva": "LT",
    "Griechenland": "GR",

    # ── Europa – Russland ────────────────────────────────────────────────────
    "Russland": "RU",
    "Russia": "RU",
    "Russian Federation": "RU",
    "Россия": "RU",
    "Российская Федерация": "RU",
    "Russie": "RU",

    # ── Nordamerika ──────────────────────────────────────────────────────────
    "USA": "US",
    "U.S.A.": "US",
    "U.S.A": "US",
    "U.S.": "US",
    "U.S": "US",
    "U. S. A.": "US",
    "United States": "US",
    "United States of America": "US",
    "Estados Unidos": "US",
    "États-Unis": "US",
    "Kanada": "CA",
    "Canadá": "CA",
    "Mexiko": "MX",
    "México": "MX",
    "Estados Unidos Mexicanos": "MX",
    "Grönland": "GL",
    "Kalaallit Nunaat": "GL",
    "Saint-Pierre-et-Miquelon": "PM",

    # ── Mittelamerika & Karibik ──────────────────────────────────────────────
    "Kuba": "CU",
    "Puerto Rico": "PR",
    "Guatemala": "GT",
    "Honduras": "HN",
    "El Salvador": "SV",
    "Nicaragua": "NI",
    "Costa Rica": "CR",
    "Panama": "PA",
    "The Bahamas": "BS",
    "Haïti": "HT",
    "República Dominicana": "DO",
    "Aruba": "AW",
    "Curaçao": "CW",
    "Curacao": "CW",
    "Caribbean Netherlands": "BQ",
    "U.S. Virgin Islands": "VI",
    "US Virgin Islands": "VI",
    "Guadeloupe": "GP",
    "Martinique": "MQ",
    "Sint Maarten": "SX",

    # ── Südamerika ───────────────────────────────────────────────────────────
    "Brasilien": "BR",
    "Brasil": "BR",
    "Brésil": "BR",
    "Argentinien": "AR",
    "Chile": "CL",
    "Kolumbien": "CO",
    "Peru": "PE",
    "Perú": "PE",
    "Venezuela": "VE",
    "Ecuador": "EC",
    "Bolivien": "BO",
    "Bolivia": "BO",
    "Paraguay": "PY",
    "Uruguay": "UY",
    "Surinam": "SR",
    "Guyane française": "GF",
    "Falkland Islands": "FK",
    "Islas Malvinas": "FK",

    # ── Asien – Ostasien ─────────────────────────────────────────────────────
    "Peoples R China": "CN",
    "People's R China": "CN",
    "P.R. China": "CN",
    "PR China": "CN",
    "PRC": "CN",
    "P. R. China": "CN",
    "P. R. China.": "CN",
    "P.R.China": "CN",
    "P R China": "CN",
    "PR. China": "CN",
    "P.R China": "CN",
    "People's Republic of China": "CN",
    "The People's Republic of China": "CN",
    "Peoples Republic of China": "CN",
    "China, People's Republic of": "CN",
    "Mainland China": "CN",
    "China (Mainland)": "CN",
    "中国": "CN",
    "Hong Kong": "HK",
    "Hong Kong SAR": "HK",
    "Hong Kong SAR China": "HK",
    "HKSAR": "HK",
    "Macau": "MO",
    "Macao": "MO",
    "Macau SAR": "MO",
    "Macao SAR": "MO",
    "Taiwan": "TW",
    "Republic of China": "TW",
    "Taiwan, China": "TW",
    "Taiwan R.O.C.": "TW",
    "Korea": "KR",
    "South Korea": "KR",
    "Republic of Korea": "KR",
    "North Korea": "KP",
    "D.P.R. Korea": "KP",
    "DPR Korea": "KP",
    "DPRK": "KP",
    "Japan": "JP",
    "Mongolei": "MN",

    # ── Asien – Südostasien ──────────────────────────────────────────────────
    "Vietnam": "VN",
    "Viet Nam": "VN",
    "Việt Nam": "VN",
    "Thailand": "TH",
    "Singapur": "SG",
    "Indonesien": "ID",
    "Malaysia": "MY",
    "Philippinen": "PH",
    "Philippines": "PH",
    "Myanmar": "MM",
    "Burma": "MM",
    "Kambodscha": "KH",
    "Cambodia": "KH",
    "Laos": "LA",
    "Lao PDR": "LA",
    "Brunei": "BN",
    "East Timor": "TL",

    # ── Asien – Südasien ─────────────────────────────────────────────────────
    "Indien": "IN",
    "Pakistan": "PK",
    "Bangladesch": "BD",
    "Bangladesh": "BD",
    "Sri Lanka": "LK",
    "Nepal": "NP",
    "Bhutan": "BT",
    "Malediven": "MV",

    # ── Asien – Zentralasien ─────────────────────────────────────────────────
    "Kasachstan": "KZ",
    "Kazakhstan": "KZ",
    "Usbekistan": "UZ",
    "Uzbekistan": "UZ",
    "Tadschikistan": "TJ",
    "Turkmenistan": "TM",
    "Kirgisistan": "KG",
    "Kyrgyzstan": "KG",
    "Armenien": "AM",
    "Armenia": "AM",
    "Georgien": "GE",
    "Sakartvelo": "GE",
    "Republic of Georgia": "GE",
    "Aserbaidschan": "AZ",
    "Azerbaijan": "AZ",
    "Azərbaycan": "AZ",

    # ── Asien – Naher Osten ──────────────────────────────────────────────────
    "Iran": "IR",
    "Islamic Republic of Iran": "IR",
    "Irak": "IQ",
    "Iraq": "IQ",
    "Syrien": "SY",
    "Syria": "SY",
    "Libanon": "LB",
    "Lebanon": "LB",
    "Israel": "IL",
    "Jordanien": "JO",
    "Jordan": "JO",
    "Saudi-Arabien": "SA",
    "Saudi Arabia": "SA",
    "Jemen": "YE",
    "Yemen": "YE",
    "Oman": "OM",
    "Vereinigte Arabische Emirate": "AE",
    "UAE": "AE",
    "U.A.E.": "AE",
    "Katar": "QA",
    "Qatar": "QA",
    "Kuwait": "KW",
    "Bahrain": "BH",
    "Türkei": "TR",
    "Turkey": "TR",
    "Türkiye": "TR",
    "Turkiye": "TR",
    "Zypern": "CY",
    "Cyprus": "CY",
    "Palestine": "PS",
    "State of Palestine": "PS",
    "Palestinian Territory": "PS",
    "Palestinian Territories": "PS",
    "Occupied Palestinian Territory": "PS",
    "Occupied Palestinian Territories": "PS",

    # ── Afrika – Nordafrika ──────────────────────────────────────────────────
    "Ägypten": "EG",
    "Egypt": "EG",
    "Égypte": "EG",
    "Marokko": "MA",
    "Morocco": "MA",
    "Maroc": "MA",
    "Algerien": "DZ",
    "Algeria": "DZ",
    "Algérie": "DZ",
    "Algerie": "DZ",
    "Tunesien": "TN",
    "Tunisia": "TN",
    "Tunisie": "TN",
    "Libyen": "LY",
    "Libya": "LY",
    "Libye": "LY",
    "Sudan": "SD",
    "Soudan": "SD",
    "Sahara Occidental": "EH",

    # ── Afrika – westlich ────────────────────────────────────────────────────
    "Nigeria": "NG",
    "Ghana": "GH",
    "Senegal": "SN",
    "Elfenbeinküste": "CI",
    "Ivory Coast": "CI",
    "Cote d'Ivoire": "CI",
    "Côte d'Ivoire": "CI",
    "Kamerun": "CM",
    "Cameroon": "CM",
    "Bénin": "BJ",
    "Cape Verde": "CV",
    "The Gambia": "GM",
    "Guinée": "GN",
    "Mauritanie": "MR",
    "Republic of Niger": "NE",

    # ── Afrika – zentral ─────────────────────────────────────────────────────
    "République centrafricaine": "CF",
    "Tchad": "TD",
    "Congo, Republic of the": "CG",
    "Democratic Republic of the Congo": "CD",
    "Democratic Republic of Congo": "CD",
    "Guinée équatoriale": "GQ",
    "São Tomé and Príncipe": "ST",

    # ── Afrika – östlich ─────────────────────────────────────────────────────
    "Äthiopien": "ET",
    "Ethiopia": "ET",
    "Kenia": "KE",
    "Kenya": "KE",
    "Tansania": "TZ",
    "Tanzania": "TZ",
    "Uganda": "UG",
    "Ruanda": "RW",
    "Rwanda": "RW",
    "Komoren": "KM",
    "Mayotte": "YT",

    # ── Afrika – südlich ─────────────────────────────────────────────────────
    "Südafrika": "ZA",
    "South Africa": "ZA",
    "Simbabwe": "ZW",
    "Zimbabwe": "ZW",
    "Sambia": "ZM",
    "Zambia": "ZM",
    "Mosambik": "MZ",
    "Mozambique": "MZ",
    "Demokratische Republik Kongo": "CD",
    "DR Congo": "CD",
    "DRC": "CD",
    "Swaziland": "SZ",

    # ── Ozeanien ─────────────────────────────────────────────────────────────
    "Australien": "AU",
    "Neuseeland": "NZ",
    "New Zealand": "NZ",
    "Papua-Neuguinea": "PG",
    "Papua New Guinea": "PG",
    "American Samoa": "AS",
    "Guam": "GU",
    "Northern Mariana Islands": "MP",
    "Pitcairn Islands": "PN",
    "United States Minor Outlying Islands": "UM",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def _alias_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return " ".join(normalized.casefold().split())

_NORMALIZED_ABBREVIATIONS = {
    _alias_key(name): country
    for name, country in ABBREVIATIONS.items()
    if name != "Island"
}

def matchAbbreviation(text: str) -> str | None:
    """Schlägt den Text im Abkürzungs-Dictionary nach."""
    normalized = unicodedata.normalize("NFKC", text).strip()

    exact = ABBREVIATIONS.get(normalized)
    if exact is not None:
        return exact
    return _NORMALIZED_ABBREVIATIONS.get(_alias_key(normalized))

_COUNTRY_NAMES = {}
for country in pycountry.countries:
    for attribute in ("name", "official_name", "common_name"):
        name = getattr(country, attribute, None)
        if name:
            _COUNTRY_NAMES.setdefault(name.strip().casefold(), set()).add(country.alpha_2)

_SUBDIVISION_NAMES = {}
for subdivision in pycountry.subdivisions:
    _SUBDIVISION_NAMES.setdefault(subdivision.name.strip().casefold(), set()).add(subdivision.country_code)

def matchIso3(text: str) -> str | None:
    code = text.strip()
    if re.fullmatch(r"[A-Z]{3}", code) is None:
        return None

    country = pycountry.countries.get(alpha_3=code)
    return country.alpha_2 if country else None

def matchPycountry(text: str) -> tuple[str | None, str | None]:
    """Sucht den ISO-Ländercode via pycountry (englische Namen)."""
    key = text.strip().casefold()
    countries = _COUNTRY_NAMES.get(key, set())
    subdivisions = _SUBDIVISION_NAMES.get(key, set())

    if len(countries) > 1 or (countries and subdivisions -countries):
        return None, "pycountry_ambiguous"

    if countries:
        return next(iter(countries)), "pycountry_exact"

    if len(subdivisions) > 1:
        return None, "pycountry_ambiguous"

    if subdivisions:
        return next(iter(subdivisions)), "pycountry_subdivision_exact"

    return None, None


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
    "dictionary_exact" :                1.0,
    "pycountry_exact":                  0.95,     #standard-ISO-Names
    "pycountry_iso3_exact":             0.95,
    "geonames_unique_primary":          0.90,
    "ror_exact":                        0.85,     #Exact ROR-Name/ID Match
    "geonames_exact":                   0.85,     #whole String is known City(i.E.Leipzig)

    #partial matches
    "dictionary_word":                  0.85,   #found word in dict but String contains more text
    "geonames_word":                    0.80,   #City found in Text(i.E. "Univesitätsklinik Leipzig")
    "pycountry_subdivision_exact":      0.75,
    "ror_fuzzy":                        0.70,   #ROR found in fuzzy search

    #fallback
    "geonames_review":                  0.0,
    "pycountry_ambiguous":              0.0,
    "not_found":                        0.0,
}

def resolve(text: str) -> tuple[str | None, str | None, float]:
    """
    returns ISO-3166-1 alpha-2 Country-code, Source for the decision and TrustRanking (or None)
    Order: Dictionary -> pycountry -> GeoNames (cities)
    """
    dictionary_country = matchAbbreviation(text)

    if dictionary_country:
        return dictionary_country, "dictionary_exact", Trust_RANKING["dictionary_exact"]

    iso3_country = matchIso3(text)
    if iso3_country:
        return iso3_country, "pycountry_iso3_exact", Trust_RANKING["pycountry_iso3_exact"]

    country, source = matchPycountry(text)
    if source == "pycountry_ambiguous":
        return None, source, Trust_RANKING[source]
    if source:
        return country, source, Trust_RANKING[source]
    city = resolveCity(text, _CITY_MAP)
    if city:
        return city, "geonames_unique_primary", Trust_RANKING["geonames_unique_primary"]
    if text.strip().casefold() in _CITY_REVIEW:
        return None, "geonames_review", Trust_RANKING["geonames_review"]
    word = resolveFromWords(text, _CITY_MAP)
    if word:
        return word, "geonames_word", Trust_RANKING["geonames_word"]
    return None, "not_found", Trust_RANKING["not_found"]

# ── Tests (only with direct call) ──────────────────────────────────────────

# if __name__ == "__main__":
#    tests = [
#        "Germany", "GERMANY", "Deutschland", "Schweiz",
#        "Österreich", "UK", "USA", "Korea", "North Korea", "Berlin",
#    ]
#    for t in tests:
#        print(f"{t:15} → {resolve(t)}")
def run_geo_pipeline(batch_size: int = 10000) -> None:

    if batch_size < 1:
        raise ValueError("batch_size muss mindestens 1 sein")

    db_path = Path(DB_PATH)
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parent / db_path
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    con = sqlite3.connect(db_path)

    try:
        #loading current ROR before replacing current table
        old_ror_table = {
            candidate: (country, trust)
            for candidate, country, trust in con.execute("""
                SELECT affiliation_candidate, country, trust_ranking
                FROM laender_quarantaene
                WHERE reason = 'ror_verified'
                    AND country IS NOT NULL
                    AND country != 'not found'
            """)
        }

        candidate_counter = Counter()
        candidate_pmids = {}
        article_count = 0

        for pmid, affiliations in con.execute("""
            SELECT pmid, affiliations
            FROM artikel
            WHERE affiliations IS NOT NULL
        """):
            article_count += 1

            for single in splitAffiliations(affiliations):
                clean = removeNoise(single)
                if not clean:
                    continue

                field = extractGeoField(clean)
                field = re.sub(r"^\d{4,6}\s+", "", field).strip()

                if field and len(field) >= 3:
                    candidate_counter[field] += 1
                    if field not in candidate_pmids:
                        candidate_pmids[field] = (pmid, single)

        candidate_count = len(candidate_counter)
        occurence_count = sum(candidate_counter.values())

        if candidate_count == 0:
            raise RuntimeError("Keine Kandidaten gefunden, bestehende Tabellen bleiben")
        print(f"{article_count:,} artikel gelesen")
        print(f"{candidate_count:,}verschiedene Kandidaten "
              f"{occurence_count:,} mal in gefunden")
        print(f"{len(old_ror_table):,} bisherige ROR-Ergebnisse gelesen")

        geo_insert_sql = """
            INSERT INTO geo_zuordnung
                (pmid, affiliation_kandidat, affiliation_raw, land, quelle, trust_ranking, count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """

        quarantaene_insert_sql = """
            INSERT INTO laender_quarantaene
                (pmid, affiliation_candidate, affiliation_raw, country, source, trust_ranking, count, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        batch_geo = []
        batch_manual = []

        #one commit to delete and fully replace
        #on exception contextmanager will execute a rollback

        with con:
            con.execute("DELETE FROM geo_zuordnung")
            con.execute("DELETE FROM laender_quarantaene")

            for i, (candidate, count) in enumerate(candidate_counter.items(), start=1):
                country, source, trust_ranking = resolve(candidate)
                previous_ror = old_ror_table.get(candidate)
                if previous_ror is not None and previous_ror[1] > trust_ranking:
                    country, trust_ranking = previous_ror
                    source = "ror_exact"

                if source == "ror_exact":
                    reason = "ror_verified"
                elif source == "pycountry_ambiguous":
                    reason = "ambiguous"
                elif source == "pycountry_subdivision_exact":
                    reason = "subdivision_review"
                elif source == "geonames_review":
                    reason = "geonames_review"
                elif country is None:
                    reason = "not_found"
                elif trust_ranking < 0.90:
                    reason = "low_trust"
                else:
                    reason = None

                pmid, affiliations_raw = candidate_pmids[candidate]

                entry = (pmid, candidate, affiliations_raw, country if country else "not found", source, trust_ranking, count,)

                if reason is None:
                    batch_geo.append(entry)
                    if len(batch_geo) >= batch_size:
                        con.executemany(geo_insert_sql, batch_geo)
                        batch_geo.clear()
                else:
                    batch_manual.append(entry + (reason,))
                    if len(batch_manual) >= batch_size:
                        con.executemany(quarantaene_insert_sql, batch_manual)
                        batch_manual.clear()

                if i % 10000 == 0:
                    print(f"{i:,}/{candidate_count:,} kandidaten zugeordnet", flush = True)

            if batch_geo: con.executemany(geo_insert_sql, batch_geo)

            if batch_manual: con.executemany(quarantaene_insert_sql, batch_manual)

            geo_rows, geo_count = con.execute('SELECT COUNT(*), COALESCE(SUM("count"), 0) FROM geo_zuordnung').fetchone()
            manual_rows, manual_count = con.execute('SELECT COUNT(*), COALESCE(SUM("count"), 0) FROM laender_quarantaene').fetchone()

            if geo_rows + manual_rows != candidate_count:
                raise RuntimeError("Kandidatenzahl nach dem Schreiben stimmt nicht")

            if geo_count + manual_count != occurence_count:
                raise RuntimeError("Summe der Vorkommen nach dem schreiben stimmt nicht")
        print(f"{geo_rows:,} länder zugeordnet, {manual_rows:,} quarantäne-Zeilen gespeichert")
    finally:
        con.close()

if __name__ == "__main__":
    run_geo_pipeline()
