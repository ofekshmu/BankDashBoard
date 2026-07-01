#!/usr/bin/env python3
"""
Reset Postgres SERIAL sequences for tables that were populated via
OVERRIDING SYSTEM VALUE (explicit IDs) without a subsequent setval().
Safe to run multiple times — setval() is idempotent.
"""
import os, sys, io, psycopg2
from dotenv import load_dotenv

load_dotenv('.env')
load_dotenv('source/.env')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TABLES = [
    'billentries',
    'billtypes',
    'spotifymembers',
    'spotifymonthlycharge',
    'spotifymemberpayments',
]

pg = psycopg2.connect(os.environ['DATABASE_URL'])
pg.autocommit = False
c = pg.cursor()

for table in TABLES:
    c.execute(f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', 'id'),
            COALESCE((SELECT MAX(id) FROM {table}), 1)
        )
    """)
    c.execute(f"SELECT MAX(id) FROM {table}")
    max_id = c.fetchone()[0]
    print(f"  {table}: sequence set to {max_id or 1}")

pg.commit()
pg.close()
print("Done.")
