import polars as pl

"""
Stufe 3: Städtenamen auf Ländercode mappen via GeoNames cities15000.txt
"""

GEONAMES_PATH = "cities15000.txt"


def loadGeoNames() -> dict[str, str]:
    """
    Lädt die GeoNames Datenbank und gibt ein Dictionary zurück:
    stadtname (lowercase) → ISO-Ländercode

    Berücksichtigt name, asciiname UND alternatenames,
    da viele Städte unterschiedliche Schreibweisen haben
    (z.B. "München" vs. "Munich", "Frankfurt" vs. "Frankfurt am Main")
    """
    df = pl.read_csv(
        GEONAMES_PATH,
        separator="\t",
        has_header=False,
        infer_schema_length=0,
        quote_char=None,  # GeoNames nutzt keine Anführungszeichen, verhindert Parsing-Fehler
        new_columns=[
            "geonameid", "name", "asciiname", "alternatenames",
            "latitude", "longitude", "feature_class", "feature_code",
            "country_code", "cc2", "admin1", "admin2", "admin3", "admin4",
            "population", "elevation", "dem", "timezone", "modification"
        ]
    )

    city_map = {}

    for row in df.select(["name", "asciiname", "alternatenames", "country_code"]).iter_rows():
        name, asciiname, alternatenames, country_code = row

        if name:
            city_map.setdefault(name.lower(), country_code)
        if asciiname:
            city_map.setdefault(asciiname.lower(), country_code)
        if alternatenames:
            for alt in alternatenames.split(","):
                alt_clean = alt.strip().lower()
                if alt_clean:
                    city_map.setdefault(alt_clean, country_code)

    return city_map


def resolveCity(text: str, city_map: dict[str, str]) -> str | None:
    """
    Sucht den Text im GeoNames Dictionary.
    Gibt ISO-Ländercode zurück oder None.
    """
    return city_map.get(text.strip().lower(), None)


# Test
if __name__ == "__main__":
    city_map = loadGeoNames()
    print(f"Geladene Städte: {len(city_map):,}")

    tests = ["München", "Tübingen", "Frankfurt", "Hannover",
             "Mainz", "Leipzig", "St. Gallen", "Zürich"]
    for t in tests:
        result = resolveCity(t, city_map)
        print(f"{t:20} → {result}")
