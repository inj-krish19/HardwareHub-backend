"""The checked-in diagram must match the models. If this fails, a model changed:
run  python -m app.db.erd > docs/erd.mmd  and  python -m app.db.erd --markdown > docs/ERD.md
(and re-make docs/erd.png, see docs/ERD.md)."""
from pathlib import Path

from app.db import erd

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_the_mermaid_file_matches_the_models():
    assert (DOCS / "erd.mmd").read_text(encoding="utf-8").strip() == erd.build_mermaid().strip()


def test_the_markdown_file_matches_the_models():
    assert (DOCS / "ERD.md").read_text(encoding="utf-8").strip() == erd.build_markdown().strip()


def test_every_table_the_app_uses_is_described():
    from app.db.base import Base

    used = {t.name for t in Base.metadata.sorted_tables} - set(erd.UNUSED)
    assert used <= set(erd.PURPOSE)