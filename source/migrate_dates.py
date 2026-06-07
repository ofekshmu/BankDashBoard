"""
One-off migration: normalise File.Last_update from DD-MM-YYYY → YYYY-MM-DD.

Rows stored by delete_transactions() before this fix used strftime("%d-%m-%Y"),
which breaks ORDER BY Last_update. This script converts them to ISO format.
"""
import sqlite3
import os

_HERE        = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_HERE)

DB_CANDIDATES = [
    os.path.join(_PROJECT_DIR, 'ShmuelFamiliy.db'),   # primary (used by WebApp)
    os.path.join(_HERE,        'ShmuelFamiliy.db'),   # fallback (source/)
]

db_path = next((p for p in DB_CANDIDATES if os.path.exists(p) and os.path.getsize(p) > 0), None)

if not db_path:
    print("ERROR: no non-empty database found — checked:")
    for p in DB_CANDIDATES:
        exists = os.path.exists(p)
        size   = os.path.getsize(p) if exists else 0
        print(f"  {p}  exists={exists}  size={size}")
    raise SystemExit(1)

print(f"Using DB: {db_path}")

conn = sqlite3.connect(db_path)
cur  = conn.cursor()

# Preview affected rows
cur.execute("SELECT File_Name, Last_update FROM File WHERE Last_update LIKE '__-__-____'")
affected = cur.fetchall()
print(f"Rows with DD-MM-YYYY format (to be fixed): {len(affected)}")
for row in affected:
    try:
        print(f"  {row[0]:50s}  {row[1]}")
    except UnicodeEncodeError:
        print(f"  [name contains non-ASCII chars]  {row[1]}")

if affected:
    cur.execute("""
        UPDATE File
        SET Last_update = substr(Last_update, 7, 4)
                       || '-'
                       || substr(Last_update, 4, 2)
                       || '-'
                       || substr(Last_update, 1, 2)
        WHERE Last_update LIKE '__-__-____'
    """)
    conn.commit()
    print(f"\n✓ Updated {cur.rowcount} rows.")
else:
    print("Nothing to fix — all rows are already in YYYY-MM-DD format.")

# Verify
cur.execute("SELECT DISTINCT Last_update FROM File LIMIT 5")
print("\nSample Last_update values after migration:")
for r in cur.fetchall():
    print(f"  {r[0]}")

conn.close()
print("\nDone.")
