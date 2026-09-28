import time
import requests
import sqlite3
import unicodedata

from Creating_SQLite_Tables import DB_PATH

"""
    Step 4: mapping names of institutions through the ROR-API 
    (Research Organization Registry) 
    to a Country-Code
    
    - reads "geo_zuordnung" table, where there is no previous result, maps that Affiliations via the ROR API
    - writes results into "geo_zuordnung" table
    
    ROR-Documentation: https://ror.readme.io/docs/rest-api
    no API-Key needed yet (Rate-Limit of 2000 requests/ 5 minutes)
"""

ROR_API_URL = "https://api.ror.org/v2/organizations"

def _normalize_ror_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.casefold().split())

def queryRor (name: str) -> str | None:
    """
        looks for a named institution in the ROR API
        returns the ISO-3166-1 alpha 2 country code of the best fit (or None)
    """
    target = _normalize_ror_name(name)
    if not target:
        return None

    try:
        response = requests.get(
            ROR_API_URL,
            params={"affiliation": name},
            timeout=10,
        )
        response.raise_for_status()

        items = response.json().get("items", [])
        exact = []
        for item in items:
            organization = item.get("organization") or {}
            names = organization.get("names") or []

            if any(
                isinstance(entry.get("value"), str)
                and "acronym" not in (entry.get("types") or [])
                and _normalize_ror_name(entry["value"]) == target
                for entry in names
            ):
                exact.append(item)

        if len(exact) != 1 or exact[0].get("chosen") is not True:
            return None

        organization = exact[0]["organization"]
        if organization.get("status") != "active":
            return None

        country_codes = {
            (location.get("geonames_details") or {}).get("country_code")
            for location in (organization.get("locations") or [])
        }
        country_codes.discard(None)

        return next(iter(country_codes)) if len(country_codes) == 1 else None

    except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError):
        return None

def resolve_not_found():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    #getting unique- non-parted Affiliations
    cur.execute("""SELECT DISTINCT affiliation_candidate 
                FROM laender_quarantaene 
                WHERE reason = 'not_found'""")
    not_found = [row[0] for row in cur.fetchall()]
    print(f"{len(not_found)} unique non-split affiliations found")

    found = 0
    for i, name in enumerate(not_found):
        country = queryRor(name)
        if country:
            cur.execute("""
                UPDATE laender_quarantaene 
                SET country = ?, source = 'ror_exact', trust_ranking = 0.85, reason = 'ror_verified'
                WHERE affiliation_candidate = ? AND reason = 'not_found'
            """, (country, name))
            con.commit()
            found += 1

        if (i+1)%100 == 0:
            print(f"{i+1:,} / {len(not_found):,} processed - {found} Affiliations found", flush = True)
        time.sleep(0.2)
    con.close()
    print(f"\ndone - {found} / {len(not_found)} Affiliations resolved via ROR")
if __name__ == "__main__":
    resolve_not_found()

#def resolveRorBatch(names: list[str], delaySeconds: float= 0.2) -> dict[str, str | None]:
#    """
#    requests a list of Institution names via ROR API
#    delaySeconds assures that the allowed amount of requests is not exceeded
#    """
#    results = {}
#    for i, name in enumerate(names):
#        results[name] = queryRor(name)
#        print(f"{i+1} / {len(names)} : '{name}' -> {results[name]}")
#        time.sleep(delaySeconds)
#    return results

#test
#if __name__ == "__main__":
#    tests = [
#    "Universitätsklinikum Leipzig",
#    "Medizinische Hochschule Hannover",
#    "Justus-Liebig-Universität Gießen",
#    "Asklepios Klinik Barmbek",
#    ]
#    results = resolveRorBatch(tests)