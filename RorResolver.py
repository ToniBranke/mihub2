import time
import requests
from jsonschema.exceptions import best_match

"""
    Step 4: mapping names of institutions through the ROR-API 
    (Research Organization Registry) 
    to a Country-Code
    
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

def resolveRorBatch(names: list[str], delaySeconds: float= 0.2) -> dict[str, str | None]:
    """
    requests a list of Institution names via ROR API
    delaySeconds assures that the allowed amount of requests is not exceeded
    """
    results = {}
    for i, name in enumerate(names):
        results[name] = queryRor(name)
        print(f"{i+1} / {len(names)} : '{name}' -> {results[name]}")
        time.sleep(delaySeconds)
        return results

#test
if __name__ == "__main__":
    tests = [
    "Universitätsklinikum Leipzig",
    "Medizinische Hochschule Hannover",
    "Justus-Liebig-Universität Gießen",
    "Asklepios Klinik Barmbek",
    ]
    results = resolveRorBatch(tests)