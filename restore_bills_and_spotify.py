#!/usr/bin/env python3
"""
Restore BillTypes group assignments and all Spotify data from the local SQLite backup
into Neon Postgres.

Safe to run more than once — UPDATEs are idempotent, INSERTs use ON CONFLICT DO NOTHING.
"""
import os, sys, io, sqlite3, psycopg2
from dotenv import load_dotenv

load_dotenv('.env')
load_dotenv('source/.env')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SQLITE_PATH = 'ShmuelFamiliy.db'

sq = sqlite3.connect(SQLITE_PATH)
sq.row_factory = sqlite3.Row
pg = psycopg2.connect(os.environ['DATABASE_URL'])
pg.autocommit = False
c = pg.cursor()


# ── 1. Bill group assignments ─────────────────────────────────────────────────
print('=== Bill group assignments ===')
sq_rows = sq.execute('SELECT ID, GroupName FROM BillTypes').fetchall()
updated = 0
for r in sq_rows:
    group = r['GroupName']
    if group:
        c.execute('UPDATE billtypes SET billgroup=%s WHERE id=%s', (group, r['ID']))
        if c.rowcount:
            print(f'  ID={r["ID"]} → BillGroup={group!r}')
            updated += c.rowcount
print(f'  {updated} BillTypes updated.\n')


# ── 2. SpotifyMembers ─────────────────────────────────────────────────────────
print('=== SpotifyMembers ===')
sq_rows = sq.execute(
    'SELECT ID, Name, Is_Exempt, Is_Active FROM SpotifyMembers'
).fetchall()
inserted = 0
for r in sq_rows:
    c.execute("""
        INSERT INTO spotifymembers (id, name, is_exempt, is_active, insertion_date)
        OVERRIDING SYSTEM VALUE
        VALUES (%s, %s, %s, %s, '2026-01-01')
        ON CONFLICT (id) DO NOTHING
    """, (r['ID'], r['Name'], r['Is_Exempt'], r['Is_Active']))
    if c.rowcount:
        print(f'  Inserted member ID={r["ID"]} name={r["Name"]!r}')
        inserted += 1
print(f'  {inserted} members inserted.\n')
# Reset sequence
c.execute("""
    SELECT setval(
        pg_get_serial_sequence('spotifymembers', 'id'),
        COALESCE((SELECT MAX(id) FROM spotifymembers), 1)
    )
""")


# ── 3. SpotifyMonthlyCharge ───────────────────────────────────────────────────
# SQLite: ID, Month, Total_Amount, Member_Count, TX_ID, Confirmed
# Postgres: id, month, totalamount, membercount, tx_id, confirmed
print('=== SpotifyMonthlyCharge ===')
sq_rows = sq.execute(
    'SELECT ID, Month, Total_Amount, Member_Count, TX_ID, Confirmed FROM SpotifyMonthlyCharge'
).fetchall()
inserted = 0
for r in sq_rows:
    c.execute("""
        INSERT INTO spotifymonthlycharge (id, month, totalamount, membercount, tx_id, confirmed)
        OVERRIDING SYSTEM VALUE
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (r['ID'], r['Month'], r['Total_Amount'], r['Member_Count'], r['TX_ID'], r['Confirmed']))
    if c.rowcount:
        print(f'  Inserted charge ID={r["ID"]} month={r["Month"]} amount={r["Total_Amount"]}')
        inserted += 1
print(f'  {inserted} monthly charges inserted.\n')
c.execute("""
    SELECT setval(
        pg_get_serial_sequence('spotifymonthlycharge', 'id'),
        COALESCE((SELECT MAX(id) FROM spotifymonthlycharge), 1)
    )
""")


# ── 4. SpotifyMemberPayments ──────────────────────────────────────────────────
# SQLite: ID, Member_ID, Amount, Payment_Date, TX_ID, Note, Created_At, TX_Source
# Postgres: id, member_id, amount, payment_date, tx_id, tx_source, note, dismissed
print('=== SpotifyMemberPayments ===')
sq_rows = sq.execute(
    'SELECT ID, Member_ID, Amount, Payment_Date, TX_ID, Note, TX_Source FROM SpotifyMemberPayments'
).fetchall()
inserted = 0
for r in sq_rows:
    c.execute("""
        INSERT INTO spotifymemberpayments
            (id, member_id, amount, payment_date, tx_id, tx_source, note, dismissed)
        OVERRIDING SYSTEM VALUE
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
        ON CONFLICT (id) DO NOTHING
    """, (r['ID'], r['Member_ID'], r['Amount'], r['Payment_Date'],
          r['TX_ID'], r['TX_Source'], r['Note']))
    if c.rowcount:
        print(f'  Inserted payment ID={r["ID"]} member_id={r["Member_ID"]} amount={r["Amount"]}')
        inserted += 1
print(f'  {inserted} payments inserted.\n')
c.execute("""
    SELECT setval(
        pg_get_serial_sequence('spotifymemberpayments', 'id'),
        COALESCE((SELECT MAX(id) FROM spotifymemberpayments), 1)
    )
""")


# ── 5. TransactionSplits ──────────────────────────────────────────────────────
# SQLite: ID, Original_Table, Original_ID, Amount, Description, Category, Created_At
print('=== TransactionSplits ===')
sq_rows = sq.execute(
    'SELECT ID, Original_Table, Original_ID, Amount, Description, Category, Created_At FROM TransactionSplits'
).fetchall()
inserted = 0
for r in sq_rows:
    c.execute("""
        INSERT INTO transactionsplits
            (id, original_table, original_id, amount, description, category, created_at)
        OVERRIDING SYSTEM VALUE
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (r['ID'], r['Original_Table'], r['Original_ID'], r['Amount'],
          r['Description'], r['Category'], r['Created_At']))
    if c.rowcount:
        print(f'  Inserted split ID={r["ID"]} {r["Original_Table"]}#{r["Original_ID"]} amount={r["Amount"]}')
        inserted += 1
print(f'  {inserted} splits inserted.\n')
c.execute("""
    SELECT setval(
        pg_get_serial_sequence('transactionsplits', 'id'),
        COALESCE((SELECT MAX(id) FROM transactionsplits), 1)
    )
""")


pg.commit()
print('Done — all changes committed.')
sq.close()
pg.close()
