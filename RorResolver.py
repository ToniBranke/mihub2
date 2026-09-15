import time
import requests
import sqlite3
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

def queryRor (name: str) -> str | None:
    """
        looks for a named institution in the ROR API
        returns the ISO-3166-1 alpha 2 country code of the best fit (or None)
    """
    try:
        response = requests.get(
            ROR_API_URL,
            params={"query": name},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if not items:
            return None

        #best match (first result, ROR sorts for relevance)
        best_match = items[0]
        countryCode = (
            best_match
            .get("locations", [{}])[0]#
            .get("geonames_details", {})
            .get("country_code")
        )
        return countryCode
    except (requests.RequestException, IndexError, KeyError):
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
                SET country = ?, source = 'ror_exact', trust_ranking = 0.85, reason = 'ror_solved'
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