"""
Run with: python -m app.db.init_db

Creates all tables directly from the SQLAlchemy models. No Alembic needed
for this stage — swap to proper migrations once the schema stabilizes.
"""
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401  (registers all model classes on Base.metadata)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    table_names = sorted(Base.metadata.tables.keys())
    print(f"Created/verified {len(table_names)} tables: {', '.join(table_names)}")


if __name__ == "__main__":
    init_db()