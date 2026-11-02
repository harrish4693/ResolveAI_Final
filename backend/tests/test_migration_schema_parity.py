"""
ResolveAIV2 — Migration Schema Parity Test Suite (Item 8.a)

Guarantees database migration safety:
1. Runs `alembic upgrade head` on an EMPTY database from scratch.
2. Compares the resulting database schema against all registered SQLAlchemy models
   in `Base.metadata` using Alembic's `compare_metadata`.
3. Fails immediately if any table, column, index, or constraint is missing from migrations
   or extra in migrations.
4. Verifies negative-control: injecting a phantom unmigrated column fails the check.
"""

import os
import tempfile
import pytest
from sqlalchemy import create_engine, Column, String
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata

# Import all models so Base.metadata is fully populated
import app.main  # noqa: F401
from app.database import Base


class TestMigrationSchemaParity:
    """Tests that migrations recreate the exact SQLAlchemy models on an empty DB."""

    def test_alembic_upgrade_head_on_empty_db_matches_models(self):
        """Run all migrations on a clean empty database and assert 0 schema diffs."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "clean_parity_test.db").replace("\\", "/")
        async_url = f"sqlite+aiosqlite:///{db_path}"
        sync_url = f"sqlite:///{db_path}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", async_url)

        sync_engine = None
        try:
            # Step 1: Run all migrations up to head on the empty DB
            command.upgrade(alembic_cfg, "head")

            # Step 2: Compare upgraded DB schema against SQLAlchemy models
            sync_engine = create_engine(sync_url)
            with sync_engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                diff = compare_metadata(ctx, Base.metadata)

            # Filter out any dialect-specific quirks if needed (SQLite doesn't support certain server defaults)
            # In our setup, diff should be completely empty
            assert diff == [], (
                f"Schema mismatch detected between Alembic migrations and SQLAlchemy models!\n"
                f"Differences (action, schema, table, details): {diff}\n"
                f"Run 'python -m alembic revision --autogenerate -m \"...\"' to generate missing migrations."
            )

        finally:
            if sync_engine is not None:
                sync_engine.dispose()
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass

    def test_compare_metadata_catches_unmigrated_columns(self):
        """Negative control: asserts compare_metadata actively detects missing columns."""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "negative_control_parity.db").replace("\\", "/")
        async_url = f"sqlite+aiosqlite:///{db_path}"
        sync_url = f"sqlite:///{db_path}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", async_url)

        sync_engine = None
        dummy_col_name = "test_unmigrated_phantom_column"
        try:
            command.upgrade(alembic_cfg, "head")

            # Temporarily attach an unmigrated column to the conversations model
            conv_table = Base.metadata.tables["conversations"]
            dummy_col = Column(dummy_col_name, String(50), nullable=True)
            conv_table.append_column(dummy_col)

            sync_engine = create_engine(sync_url)
            with sync_engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                diff = compare_metadata(ctx, Base.metadata)

            # Verify that compare_metadata caught the missing column
            missing_cols = [
                d for d in diff
                if d[0] == "add_column" and getattr(d[3], "name", None) == dummy_col_name
            ]
            assert len(missing_cols) > 0, "Expected compare_metadata to catch the unmigrated column!"

        finally:
            # Clean up phantom column from metadata in memory
            if "conversations" in Base.metadata.tables and dummy_col_name in Base.metadata.tables["conversations"].c:
                conv_table = Base.metadata.tables["conversations"]
                conv_table._columns.remove(dummy_col)

            if sync_engine is not None:
                sync_engine.dispose()
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass
