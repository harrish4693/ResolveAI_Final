"""
ResolveAI V2 — Database Migration Utility (SQLite to PostgreSQL / Supabase)
===========================================================================
Exports all relational tables from local SQLite (resolveai.db) and streams them
into the target PostgreSQL / Supabase database specified in DATABASE_URL.

Usage:
    python scripts/migrate_database.py             # Normal migration
    python scripts/migrate_database.py --truncate  # Clear target Postgres tables first
"""

import asyncio
import os
import sys
import argparse

from sqlalchemy import select, insert, text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base
import app.main  # Ensures all models and relationships are registered
from app.config import settings

async def migrate_data(truncate: bool = False):
    sqlite_url = "sqlite+aiosqlite:///./resolveai.db"
    postgres_url = settings.database_url
    
    if "postgres" not in postgres_url:
        print("[ERROR] DATABASE_URL is not pointing to PostgreSQL / Supabase.")
        print(f"Current DATABASE_URL: {postgres_url}")
        print("Please configure backend/.env with your PostgreSQL connection string.")
        return

    print(f"Connecting to Source SQLite: {sqlite_url}")
    sqlite_engine = create_async_engine(sqlite_url)
    
    print(f"Connecting to Target PostgreSQL: {postgres_url.split('@')[-1]}")
    pg_engine = create_async_engine(postgres_url)

    sorted_tables = Base.metadata.sorted_tables

    if truncate:
        print("\nClearing existing PostgreSQL data (TRUNCATE CASCADE)...")
        async with pg_engine.begin() as pg_conn:
            for table in reversed(sorted_tables):
                try:
                    await pg_conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))
                    print(f"  Truncated {table.name}")
                except Exception as e:
                    print(f"  Warning truncating {table.name}: {e}")

    async with sqlite_engine.connect() as sqlite_conn:
        async with pg_engine.connect() as pg_conn:
            print("\nStarting table data migration...")
            
            for table in sorted_tables:
                print(f"--- Migrating {table.name} ---")
                
                # Fetch all rows from sqlite
                result = await sqlite_conn.execute(select(table))
                rows = result.mappings().all()
                
                if not rows:
                    print(f"  No rows in {table.name}, skipping.")
                    continue
                
                print(f"  Found {len(rows)} rows. Inserting into PostgreSQL...")
                insert_data = [dict(row) for row in rows]
                
                try:
                    async with pg_conn.begin_nested():
                        await pg_conn.execute(insert(table), insert_data)
                    print(f"  [SUCCESS] {len(rows)} rows migrated to {table.name}.")
                except Exception as e:
                    print(f"  [WARNING] Error on {table.name}: {e}")
                    
            print("\nCommitting changes to PostgreSQL...")
            await pg_conn.commit()
    
    print("\nDatabase migration finished successfully!")
    await sqlite_engine.dispose()
    await pg_engine.dispose()

def main():
    parser = argparse.ArgumentParser(description="Migrate ResolveAI SQLite data to PostgreSQL.")
    parser.add_argument("--truncate", "--clean", action="store_true", help="Truncate target PostgreSQL tables before migration.")
    args = parser.parse_args()
    asyncio.run(migrate_data(truncate=args.truncate))

if __name__ == "__main__":
    main()

