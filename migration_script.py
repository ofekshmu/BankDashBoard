#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migration script: SQLite to PostgreSQL
Copies CardTransactions and BankTransactions data from local SQLite to Neon PostgreSQL
"""

import sqlite3
import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_batch

# Handle unicode encoding on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

DB_SQLITE = 'C:/Users/ofeks/OneDrive/Ofek/BankProject/ShmuelFamiliy 2026-05-22.db'  # Latest database backup
DB_POSTGRES_URL = os.getenv('DATABASE_URL')

if not DB_POSTGRES_URL:
    print("ERROR: DATABASE_URL not set in environment")
    sys.exit(1)

if not os.path.exists(DB_SQLITE):
    print(f"ERROR: SQLite database not found at {DB_SQLITE}")
    sys.exit(1)

def migrate_table(sqlite_conn, pg_conn, table_name):
    """Migrate a single table from SQLite to PostgreSQL"""
    print(f"\nMigrating {table_name}...")

    # Get data from SQLite
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    column_names = [desc[0] for desc in sqlite_cursor.description]

    if not rows:
        print(f"  No data in {table_name}")
        return

    # Create table in PostgreSQL if it doesn't exist
    pg_cursor = pg_conn.cursor()

    # This is a simplified approach - you may need to adjust column types
    # For production, consider using schema detection

    try:
        # Insert data into PostgreSQL
        placeholders = ','.join(['%s'] * len(column_names))
        insert_sql = f"INSERT INTO {table_name} ({','.join(column_names)}) VALUES ({placeholders})"

        execute_batch(pg_cursor, insert_sql, rows, page_size=100)
        pg_conn.commit()

        print(f"  [OK] Migrated {len(rows)} rows from {table_name}")
    except Exception as e:
        pg_conn.rollback()
        print(f"  [ERROR] Error migrating {table_name}: {e}")
        return False
    finally:
        pg_cursor.close()

    return True

def main():
    print("Starting migration from SQLite to PostgreSQL...")

    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(DB_SQLITE)
        sqlite_cursor = sqlite_conn.cursor()

        # Get list of tables
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in sqlite_cursor.fetchall()]

        print(f"Found tables: {', '.join(tables)}")

        # Connect to PostgreSQL
        pg_conn = psycopg2.connect(DB_POSTGRES_URL)

        # Migrate each table
        for table in tables:
            if table.startswith('sqlite_'):  # Skip SQLite internal tables
                continue
            migrate_table(sqlite_conn, pg_conn, table)

        pg_conn.close()
        sqlite_conn.close()

        print("\n[OK] Migration completed successfully")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
