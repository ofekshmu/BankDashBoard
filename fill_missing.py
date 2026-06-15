#!/usr/bin/env python3
"""Insert SQLite rows that are absent from PostgreSQL (by ID)."""
import os, sqlite3, psycopg2
from dotenv import load_dotenv

load_dotenv('.env')
load_dotenv('source/.env')

sq = sqlite3.connect('ShmuelFamiliy.db')
sq.row_factory = sqlite3.Row
pg = psycopg2.connect(os.environ['DATABASE_URL'])
pg.autocommit = False
pgc = pg.cursor()

# Column types that need coercion: table -> {col_index: type}
# INT columns that SQLite may store as '' or float
INT_COLS = {
    'BankTransactions':  {'Out', 'Income', 'Balance', 'Reserved'},
    'CardTransactions':  {'Charge_Value', 'Transaction_Value', 'Reserved'},
    'CashTransactions':  {'Amount'},
    'DevisionTransactions': {'DevisionOfBank', 'DevisionOfCard', 'Amount'},
    'OtherAccountStatus': {'TransactionID'},
    'TableMeta': {'Initial_index', 'Initial_col', 'Row_count'},
}

def coerce_row(table, cols, row):
    int_set = INT_COLS.get(table, set())
    result = []
    for col, val in zip(cols, row):
        if col in int_set:
            if val is None or (isinstance(val, str) and val.strip() == ''):
                result.append(None)
            else:
                try:
                    result.append(int(float(val)))
                except (ValueError, TypeError):
                    result.append(None)
        else:
            result.append(val)
    return result

SERIAL_TABLES = [
    'BankTransactions',
    'CardTransactions',
    'CashTransactions',
    'TableMeta',
    'DevisionTransactions',
    'OtherAccountStatus',
]

total_inserted = 0

# File must come before TableMeta (FK dependency) — process it first
sq_cur = sq.execute('SELECT * FROM [File]')
cols = [d[0] for d in sq_cur.description]
rows = sq_cur.fetchall()
pgc.execute('SELECT file_name, format, card_number FROM file')
existing_file_keys = {(r[0].strip(), r[1].strip(), r[2].strip()) for r in pgc.fetchall()}
missing_files = [r for r in rows
                 if (str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip()) not in existing_file_keys]
if missing_files:
    print(f'File: inserting {len(missing_files)} missing rows ...')
    col_list = ', '.join(f'"{c.lower()}"' for c in cols)
    placeholders = ', '.join(['%s'] * len(cols))
    sql = f'INSERT INTO file ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
    pgc.executemany(sql, [list(r) for r in missing_files])
    total_inserted += len(missing_files)
else:
    print('File: up to date')

for table in SERIAL_TABLES:
    pg_table = table.lower()
    sq_cur = sq.execute(f'SELECT * FROM [{table}]')
    cols = [d[0] for d in sq_cur.description]
    rows = sq_cur.fetchall()

    pgc.execute(f'SELECT id FROM {pg_table}')
    existing_ids = {r[0] for r in pgc.fetchall()}

    missing = [row for row in rows if row[0] not in existing_ids]
    if not missing:
        print(f'{table}: up to date')
        continue

    print(f'{table}: inserting {len(missing)} missing rows ...', end=' ')

    date_col = next((c for c in cols if 'Date' in c), None)
    if date_col:
        idx = cols.index(date_col)
        dates = sorted(str(r[idx]) for r in missing)
        print(f'  (dates: {dates[0][:10]} – {dates[-1][:10]})', end='')
    print()

    # Only use columns that exist in PostgreSQL
    pgc.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (pg_table,))
    pg_cols_set = {r[0] for r in pgc.fetchall()}
    insert_idx = [i for i, c in enumerate(cols) if c.lower() in pg_cols_set]
    insert_cols = [cols[i] for i in insert_idx]

    col_list = ', '.join(f'"{c.lower()}"' for c in insert_cols)
    placeholders = ', '.join(['%s'] * len(insert_cols))
    sql = (
        f'INSERT INTO {pg_table} ({col_list}) '
        f'OVERRIDING SYSTEM VALUE '
        f'VALUES ({placeholders}) '
        f'ON CONFLICT DO NOTHING'
    )
    coerced = [[coerce_row(table, cols, r)[i] for i in insert_idx] for r in missing]
    skipped = 0
    for row_vals in coerced:
        pgc.execute("SAVEPOINT sp")
        try:
            pgc.execute(sql, row_vals)
            pgc.execute("RELEASE SAVEPOINT sp")
            total_inserted += 1
        except psycopg2.errors.ForeignKeyViolation:
            pgc.execute("ROLLBACK TO SAVEPOINT sp")
            pgc.execute("RELEASE SAVEPOINT sp")
            skipped += 1
        except Exception:
            pgc.execute("ROLLBACK TO SAVEPOINT sp")
            pgc.execute("RELEASE SAVEPOINT sp")
            raise
    if skipped:
        print(f'  (skipped {skipped} rows with FK violations)')

# Reset sequences
for table in SERIAL_TABLES:
    pg_table = table.lower()
    pgc.execute(f"""
        SELECT setval(
            pg_get_serial_sequence('{pg_table}', 'id'),
            COALESCE((SELECT MAX(id) FROM {pg_table}), 1)
        )
    """)

pg.commit()
print(f'\nDone — {total_inserted} rows inserted.')
sq.close()
pg.close()
