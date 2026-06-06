import polars as pl
import sys
import AffParser
sys.path.insert(0, ".")          # parser.py im gleichen Ordner
from AffParser import parseAffiliation
from collections import Counter
import importlib

importlib.reload(AffParser)


"""
Resolver Stufe 1: Ländercode aus einem Geo-Kandidaten extrahieren.

Reihenfolge:
  1. Abkürzungs-Dictionary  (Sonderfälle & nicht-englische Namen)
  2. pycountry              (englische ISO-Standardnamen)
"""

import pycountry


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


# ── Öffentliche API ───────────────────────────────────────────────────────────

def resolve(text: str) -> str | None:
    """
    Gibt den ISO-3166-1 alpha-2 Ländercode zurück oder None.
    Dictionary hat Vorrang vor pycountry.
    """
    return matchAbbreviation(text) or matchPycountry(text)


# ── Tests (nur bei direktem Aufruf) ──────────────────────────────────────────

# if __name__ == "__main__":
#    tests = [
#        "Germany", "GERMANY", "Deutschland", "Schweiz",
#        "Österreich", "UK", "USA", "Korea", "North Korea", "Berlin",
#    ]
#    for t in tests:
#        print(f"{t:15} → {resolve(t)}")




df = pl.read_csv("pubmed_rohdaten_komplett.csv")

# Alle Geo-Kandidaten aus dem Parser sammeln
kandidaten = []
for aff in df["affiliations"].drop_nulls():
    kandidaten.extend(parseAffiliation(aff))

# Resolver drüberlaufen lassen
treffer   = [resolve(k) for k in kandidaten]
gefunden  = sum(1 for t in treffer if t is not None)
nicht     = sum(1 for t in treffer if t is None)

print(f"\nGesamt Kandidaten : {len(kandidaten):>6,}")
print(f"Gefunden          : {gefunden:>6,}  ({gefunden/len(kandidaten)*100:.1f}%)")
print(f"Nicht gefunden    : {nicht:>6,}  ({nicht/len(kandidaten)*100:.1f}%)")

# Was wird nicht gefunden?
print("\nTop 15 nicht aufgelöste Kandidaten:")

nicht_gefunden = [k for k, t in zip(kandidaten, treffer) if t is None]
for kanditat, anzahl in Counter(nicht_gefunden).most_common(15):
    print(f"  {anzahl:>4}x  '{kanditat}'")