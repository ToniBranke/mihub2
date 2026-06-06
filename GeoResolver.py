import polars as pl

"""
    step 3: mapping city name and country code with GeoNames cities 15000.txt
"""

#   GeoNames columns: geonameid, name, asciiname, alternatennames, latitude, longitude,
#   feature_class, country_code, …

GEONAMES_PATH = "cities15000.txt"

def loadGeoNames() -> dict [str, str]:
    """
    loads GeoNames database and returns diractionary:
    city name(lowercase) -> ISO-Country-code
    """

    df = pl.read_csv(
        GEONAMES_PATH,
        separator="\t",
        has_header=False,
        infer_schema_length=0,
        new_columns=["geonameid", "name", "asciiname", "alternatenames",
            "latitude", "longitude", "feature_class", "feature_code",
            "country_code", "cc2", "admin1", "admin2", "admin3", "admin4",
            "population", "elevation", "dem", "timezone", "modification"
        ]
    )

    city_map = {}
    # main names
    for row in df.select(["name", "country_code"]).iter_rows():
        city_map[row[0].lower()] = row[1]

    # ASCII names for "Muenchen" for "München"
    for row in df.select(["asciiname", "country_code"]).iter_rows():
        city_map[row[0].lower()] = row[1]

    return city_map

def resolveCity(text: str, city_map: dict[str, str]) -> str | None:
    """
    searches the text in the GeoNames dict.
    returns either ISO-country-code or None
    """
    return city_map.get(text.strip().lower(), None)


# Test
if __name__ == "__main__":
    city_map = loadGeoNames()
    tests = ["München", "Tübingen", "Frankfurt", "Hannover",
             "Mainz", "Leipzig", "St. Gallen", "Zürich"]
    for t in tests:
        result = resolveCity(t, city_map)
        print(f"{t:20} -> {result:}")
