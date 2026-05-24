df = pl.DataFrame(alleArtikel)

df = df.with_columns([
    pl.col("affiliations").str.replace_all("\xa0", " "),
    pl.col("title").str.replace_all("\xa0", " ")
])

df.write_csv("pubmed_rohdaten_komplett.csv")

print(f"Gespeichert – {df.shape[0]} Zeilen, {df.shape[1]} Spalten")
df.head()