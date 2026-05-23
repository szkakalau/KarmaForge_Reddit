"""Quick DB status check."""
import sqlite3

db = sqlite3.connect("data/processed/karmaforge.db")
rows = db.execute(
    "SELECT subreddit, COUNT(*), MIN(upvotes), MAX(upvotes), AVG(upvotes), "
    "MIN(created_utc), MAX(created_utc) FROM posts "
    "GROUP BY subreddit ORDER BY COUNT(*) DESC"
).fetchall()

print(f"{'Subreddit':25s} | {'posts':>5s} | {'score_min':>8s} | {'score_max':>8s} | {'avg':>6s} | {'dates'}")
print("-" * 110)
for r in rows:
    d1 = str(r[5])[:10] if r[5] else "?"
    d2 = str(r[6])[:10] if r[6] else "?"
    print(f"{r[0]:25s} | {r[1]:5d} | {r[2]:8d} | {r[3]:8d} | {r[4]:6.0f} | {d1} -> {d2}")

print(f"\nTotal: {sum(r[1] for r in rows)} posts across {len(rows)} subreddits")

# Check year distribution
print("\n--- Year distribution ---")
years = db.execute(
    "SELECT SUBSTR(created_utc, 1, 4) as yr, COUNT(*) FROM posts "
    "GROUP BY yr ORDER BY yr"
).fetchall()
for yr, cnt in years:
    print(f"  {yr}: {cnt} posts")
db.close()
