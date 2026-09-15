import sqlite3
from Creating_SQLite_Tables import DB_PATH

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

cur.execute("SELECT COUNT(*) FROM geo_zuordnung")
print(f"geo_zuordnung: {cur.fetchone()[0]:,} Einträge")

cur.execute("SELECT COUNT(*) FROM laender_quarantaene")
print(f"manuell_pruefen: {cur.fetchone()[0]:,} Einträge")

cur.execute("SELECT reason, COUNT(*) FROM laender_quarantaene GROUP BY reason")
for row in cur.fetchall():
    print(f"  {row[0]:15} {row[1]:>6,}")

cur.execute("""
    SELECT source, COUNT(*) 
    FROM laender_quarantaene 
    WHERE reason = 'low_trust'
    GROUP BY source
""")
for row in cur.fetchall():
    print(f"  {row[0]:25} {row[1]:>6,}")

cur.execute("""
    SELECT source, COUNT(*) as count, AVG(trust_ranking) as avg_trust
    FROM laender_quarantaene 
    WHERE reason = 'low_trust'
    GROUP BY source
    ORDER BY count DESC
""")

for row in cur.fetchall():
    print(f"  {row[0]:25} {row[1]:>8,}  Ø Trust: {row[2]:.2f}")

cur.execute("SELECT COUNT(*) FROM geo_zuordnung")
print(f"geo_zuordnung hat:   {cur.fetchone()[0]:,} Einträge")

cur.execute("SELECT COUNT(*) FROM laender_quarantaene")
print(f"die Tabelle laender_quarantaene hat: {cur.fetchone()[0]:,} Einträge")

cur.execute("SELECT reason, COUNT(*) FROM laender_quarantaene GROUP BY reason ORDER BY COUNT(*) DESC")
for row in cur.fetchall():
    print(f"  {row[0]:20} {row[1]:>8,}")


# Tatsächliche not_found Kandidaten mit Roh-Text
cur.execute("""
    SELECT affiliation_candidate, affiliation_raw, count
    FROM laender_quarantaene
    WHERE reason = 'not_found'
    ORDER BY count DESC
    LIMIT 20
""")
for row in cur.fetchall():
    print(f"Kandidat: {repr(row[0])}")
    print(f"Roh:      {repr(row[1][:100])}")
    print(f"Count:    {row[2]:,}")
    print()

con.close()