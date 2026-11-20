"""
Bring an existing database in line with the SQLAlchemy models.

Run with: python -m app.db.sync_schema

What it does (additive only, never destructive):
  1. creates any table that is missing
  2. adds any column that exists in a model but not in the table
  3. lists tables in the database that no model uses (it does NOT drop them)

Why this exists: Base.metadata.create_all() (used by init_db) only creates
missing TABLES. It never adds a column to a table that already exists, so
after a model gains a field you would otherwise have to write ALTER TABLE
by hand. Safe to run repeatedly; a second run changes nothing.
"""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base
from app.db.session import engine


def sync_schema() -> None:
    tables_before = set(inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine)  # step 1: missing tables
    inspector = inspect(engine)  # fresh inspector so it sees the new tables
    created = sorted(set(Base.metadata.tables) - tables_before)
    added: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:  # step 2: missing columns
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = CreateColumn(column).compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
                added.append(f"{table.name}.{column.name}")

    model_tables = set(Base.metadata.tables)
    extra = sorted(set(inspector.get_table_names()) - model_tables)  # step 3: report only

    print(f"Created {len(created)} table(s): {', '.join(created) if created else 'none'}")
    print(f"Added {len(added)} column(s): {', '.join(added) if added else 'none, schema already up to date'}")
    if extra:
        print(f"Tables in the database that no model uses (left untouched): {', '.join(extra)}")


if __name__ == "__main__":
    sync_schema()