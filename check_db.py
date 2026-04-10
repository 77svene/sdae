import sqlite3
db = r"C:\Users\ll-33\.sdae\cold.db"
c = sqlite3.connect(db)
count = c.execute("SELECT COUNT(*) FROM opportunity_scores").fetchone()[0]
print(f"Cached scores: {count}")
rows = c.execute("SELECT title, composite FROM opportunity_scores ORDER BY composite DESC LIMIT 10").fetchall()
for r in rows:
    print(f"  {r[1]:.2f}  {r[0][:65]}")
c.close()
