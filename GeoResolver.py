import polars as pl
from pathlib import Path

"""
Stufe 3: Städtenamen auf Ländercode mappen via GeoNames cities15000.txt
"""

GEONAMES_PATH = Path(__file__).resolve().with_name("cities15000.txt")
CONTEXT_REQUIRED_NAMES = {"alta", "roth", "johnston", "bello", "lanka", "republic"}


def loadGeoNames() -> tuple[dict[str, str], set[str]]:
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

    countries_by_name: dict[str, str | None] = {}
    primary_names: set[str] = set()

    def add_name(value: str | None, country_code: str, primary: bool) -> None:
        if not value:
            return

        key = value.strip().casefold()
        if not key:
            return

        if primary:
            primary_names.add(key)

        if key not in countries_by_name:
            countries_by_name[key] = country_code
        elif countries_by_name[key] != country_code:
            countries_by_name[key] = None

    for name, asciiname, alternatenames, country_code in df.select(
            ["name", "asciiname", "alternatenames", "country_code"]
    ).iter_rows():
        if not country_code:
            continue

        add_name(name, country_code, True)
        add_name(asciiname, country_code, True)

        if alternatenames:
            for alternative in alternatenames.split(","):
                add_name(alternative, country_code, False)

    unique_primary = {
        name: country
        for name, country in countries_by_name.items()
        if (
            country is not None
            and name in primary_names
            and len(name) > 3
            and name not in CONTEXT_REQUIRED_NAMES
        )
    }
    review_names = set(countries_by_name) - set(unique_primary)

    return unique_primary, review_names


def resolveCity(text: str, city_map: dict[str, str]) -> str | None:
    """
    Sucht den Text im GeoNames Dictionary.
    Gibt ISO-Ländercode zurück oder None.
    """
    return city_map.get(text.strip().casefold(), None)


# Test
if __name__ == "__main__":
    city_map, review_names = loadGeoNames()
    print(f"Geladene Städte: {len(city_map):,}")

    tests = ["München", "Tübingen", "Frankfurt", "Hannover",
             "Mainz", "Leipzig", "St. Gallen", "Zürich"]
    for t in tests:
        result = resolveCity(t, city_map)
        print(f"{t:20} → {result}")
