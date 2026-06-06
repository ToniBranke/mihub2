import polars as pl
def extractUniqueAff(df):
     affiliations = (
        df ["affiliations"]
        .drop_nulls()
        .str.split(" | ")
        .explode()
        .unique()
     )
     return affiliations.filter(affiliations != "")