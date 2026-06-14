#!/usr/bin/env python3
"""
One-time migration: copies all data from local ShmuelFamiliy.db (SQLite)
into the hosted PostgreSQL database configured via DATABASE_URL.

Usage:
    python migrate_to_postgres.py                          # looks for ShmuelFamiliy.db in cwd
    python migrate_to_postgres.py path/to/ShmuelFamiliy.db

DATABASE_URL must be set in your .env file or shell environment before running.
"""

import os
import sys
import sqlite3

import psycopg2
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = sys.argv[1] if len(sys.argv) > 1 else "ShmuelFamiliy.db"
DATABASE_URL = os.environ.get("DATABASE_URL")

# Insertion order respects foreign-key dependencies:
#   Card / File first → then transactions that reference them → then join tables last.
TABLES = [
    "Card",
    "File",
    "BankTransactions",
    "CardTransactions",
    "CashTransactions",
    "TableMeta",
    "DevisionTransactions",
    "OtherAccountStatus",
]

# These tables have SERIAL (auto-increment) PKs whose sequences must be
# reset after we insert explicit IDs from SQLite, otherwise the next
# app insert would collide with an already-existing ID.
SERIAL_ID_TABLES = [
    "BankTransactions",
    "CardTransactions",
    "CashTransactions",
    "DevisionTransactions",
    "TableMeta",
    "OtherAccountStatus",
]

# Full schema — created here so the script is self-contained and works even
# on a blank PostgreSQL database.  Matches the schema in source/database.py.
SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS Card (
        CardID      CHAR(4) PRIMARY KEY,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS File (
        File_Name         CHAR NOT NULL,
        Format            CHAR NOT NULL,
        Card_Number       CHAR NOT NULL,
        Date              DATE NOT NULL,
        New_Transactions  INT,
        Transaction_count INT  NOT NULL,
        Last_update       DATE NOT NULL,
        PRIMARY KEY (File_Name, Format, Card_Number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS BankTransactions (
        ID          SERIAL PRIMARY KEY,
        Date        DATE   NOT NULL,
        Value_Date  DATE,
        Name        CHAR   NOT NULL,
        Ref         CHAR,
        Out         INT    NOT NULL,
        Income      INT    NOT NULL,
        Balance     TEXT,
        Extra_Info  CHAR,
        Source_file CHAR   NOT NULL,
        Category    CHAR,
        Description CHAR,
        Reserved    INT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS CardTransactions (
        ID                SERIAL PRIMARY KEY,
        CardID            CHAR   NOT NULL,
        Name              CHAR   NOT NULL,
        Executed_Date     DATE   NOT NULL,
        Charge_Date       DATE,
        Charge_Value      INT,
        Charge_Currency   CHAR,
        Transaction_Value INT,
        Value_Currency    CHAR,
        Extra_Info        CHAR,
        Source_file       CHAR   NOT NULL,
        Category          CHAR,
        Description       CHAR,
        Reserved          INT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS CashTransactions (
        ID             SERIAL PRIMARY KEY,
        Name           CHAR   NOT NULL,
        Execution_Date DATE   NOT NULL,
        Amount         INT    NOT NULL,
        Currency       CHAR   NOT NULL,
        Category       CHAR   NOT NULL,
        Insertion_Date DATE   NOT NULL,
        Description    CHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS TableMeta (
        ID            SERIAL PRIMARY KEY,
        File_Name     CHAR   NOT NULL,
        Format        CHAR   NOT NULL,
        Card_Number   CHAR   NOT NULL,
        Initial_index INT    NOT NULL,
        Initial_col   INT    NOT NULL,
        Row_count     INT    NOT NULL,
        Bad_rows      CHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS DevisionTransactions (
        ID             SERIAL PRIMARY KEY,
        DevisionOfBank INT    NOT NULL,
        DevisionOfCard INT    NOT NULL,
        Name           CHAR   NOT NULL,
        Execution_Date DATE   NOT NULL,
        Amount         INT    NOT NULL,
        Currency       CHAR   NOT NULL,
        Description    CHAR,
        Category       CHAR   NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS OtherAccountStatus (
        ID            SERIAL  PRIMARY KEY,
        AccountName   TEXT    NOT NULL,
        StatusDate    DATE    NOT NULL,
        Value         REAL    NOT NULL,
        TransactionID INTEGER
    )
    """,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_url(url: str) -> str:
    """Hide password in connection string for log output."""
    try:
        at = url.rindex("@")
        scheme_end = url.index("://") + 3
        return url[:scheme_end] + "***:***@" + url[at + 1:]
    except ValueError:
        return "***"


def migrate_table(sqlite_cur: sqlite3.Cursor,
                  pg_cur: psycopg2.extensions.cursor,
                  table: str) -> int:
    print(f"  {table} ...", end=" ", flush=True)

    sqlite_cur.execute(f'SELECT * FROM "{table}"')
    rows = sqlite_cur.fetchall()

    if not rows:
        print("(empty)")
        return 0

    cols = [d[0] for d in sqlite_cur.description]
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))

    # OVERRIDING SYSTEM VALUE lets us insert explicit values into SERIAL columns.
    sql = (
        f'INSERT INTO "{table}" ({col_list}) '
        f"OVERRIDING SYSTEM VALUE "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )

    pg_cur.executemany(sql, [list(row) for row in rows])
    print(f"{len(rows)} rows")
    return len(rows)


def reset_sequences(pg_cur: psycopg2.extensions.cursor) -> None:
    """Advance each SERIAL sequence to max(id) so new inserts don't collide."""
    for table in SERIAL_ID_TABLES:
        pg_cur.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table}', 'id'),
                COALESCE((SELECT MAX(id) FROM "{table}"), 1)
            )
        """)
        print(f"  Reset sequence for {table}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Pre-flight checks
    if not DATABASE_URL:
        sys.exit(
            "ERROR: DATABASE_URL is not set.\n"
            "Add DATABASE_URL=postgresql://... to your .env file and try again."
        )

    if not os.path.exists(SQLITE_PATH):
        sys.exit(
            f"ERROR: SQLite database not found at '{SQLITE_PATH}'.\n"
            f"Usage: python migrate_to_postgres.py [path/to/ShmuelFamiliy.db]"
        )

    print(f"Source (SQLite) : {SQLITE_PATH}")
    print(f"Target (Postgres): {_redact_url(DATABASE_URL)}")
    print()

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_conn.autocommit = False
    pg_cur = pg_conn.cursor()

    try:
        # 1. Create schema
        print("Creating schema (IF NOT EXISTS) ...")
        for stmt in SCHEMA_SQL:
            pg_cur.execute(stmt)
        print("  Done.\n")

        # 2. Migrate each table
        print("Migrating data ...")
        total = 0
        for table in TABLES:
            sqlite_cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not sqlite_cur.fetchone():
                print(f"  {table} ... (not in SQLite DB, skipping)")
                continue
            total += migrate_table(sqlite_cur, pg_cur, table)

        # 3. Fix sequences so the app can insert new rows without ID conflicts
        print(f"\nResetting auto-increment sequences ...")
        reset_sequences(pg_cur)

        pg_conn.commit()
        print(f"\nDone — {total} rows migrated successfully.")

    except Exception as exc:
        pg_conn.rollback()
        print(f"\nERROR during migration: {exc}")
        raise

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
