"""
Draw the database as an entity-relationship diagram, straight from the models.

Run from backend/:
    python -m app.db.erd > docs/erd.mmd      # the diagram only (Mermaid)
    python -m app.db.erd --markdown > docs/ERD.md   # the diagram plus a short note per table

Because it reads the SQLAlchemy models, the picture cannot drift from the code:
change a model, run it again. Mermaid is drawn natively by GitHub, and the
.mmd file can be turned into an image with the Mermaid CLI (see docs/ERD.md).
"""
from __future__ import annotations

import sys

from sqlalchemy import Column, Table
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base

# Tables that exist in the models (and in the database) but that no feature uses yet.
# They stay out of the main picture so it shows what the app actually does.
UNUSED = {
    "compatibility_rule": "planned for the build checker",
    "use_budget_profile": "an earlier budget-bot design, replaced by rule-based guides",
    "recommendation_rule": "an earlier budget-bot design, replaced by rule-based guides",
    "comparison": "comparisons are computed on the fly, nothing is saved",
    "comparison_item": "comparisons are computed on the fly, nothing is saved",
    "app_user": "there are no user accounts",
}

# What each table is for, in plain words (the diagram shows structure, this shows meaning).
PURPOSE = {
    "symptom": "A troubleshooting guide: its title, area, keywords, bot type and URL slug.",
    "diagnosis_rule": "The decision tree (JSON) of a guide. One per guide.",
    "guide_feedback": "Anonymous 'did this fix it?' votes on a final answer. No user, no IP, no free text.",
    "unmatched_query": "Chat messages that matched no guide (text only), once per wording with a counter.",
    "category": "A hardware category (CPU, RAM, Storage ...).",
    "product": "A catalog part with its specs (JSON), tags, image and video links.",
    "product_link": "One to three store links per product; position 0 is the 'Check price' link.",
    "blog_post": "The plain-English write-up and 'Do you know?' note shown on a product page. Its buy_links text is a legacy field: store links live in product_link.",
}

_MERMAID_TYPE = {
    "UUID": "uuid", "VARCHAR": "string", "TEXT": "text", "INTEGER": "int", "BOOLEAN": "bool",
    "TIMESTAMP": "datetime", "TIMESTAMP WITH TIME ZONE": "datetime", "SMALLINT": "int", "JSONB": "jsonb", "JSON": "json", "FLOAT": "float", "NUMERIC": "numeric",
}


def _type(column: Column) -> str:
    name = column.type.compile(dialect=postgresql.dialect()).split("(")[0].strip().upper()
    return _MERMAID_TYPE.get(name, name.lower().replace(" ", "_"))


def _entity(table: Table) -> list[str]:
    lines = [f"    {table.name} {{"]
    # Columns covered by a unique index, including an expression index such as lower(btrim(title)).
    unique_cols = {c.name for idx in table.indexes if idx.unique for c in idx.columns}
    for idx in table.indexes:
        if idx.unique:
            unique_cols |= {c.name for c in table.columns if any(c.name in str(e) for e in idx.expressions if not hasattr(e, "table"))}
    for column in table.columns:
        keys = []
        if column.primary_key:
            keys.append("PK")
        if column.foreign_keys:
            keys.append("FK")
        if column.unique or column.name in unique_cols:
            keys.append("UK")
        lines.append(f"        {_type(column)} {column.name}" + (f" {','.join(keys)}" if keys else ""))
    lines.append("    }")
    return lines


def build_mermaid(include_unused: bool = False) -> str:
    tables = [t for t in Base.metadata.sorted_tables if include_unused or t.name not in UNUSED]
    names = {t.name for t in tables}
    out = ["erDiagram"]
    for table in sorted(tables, key=lambda t: t.name):
        out += _entity(table)
    for table in sorted(tables, key=lambda t: t.name):
        for column in table.columns:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                if parent not in names:
                    continue
                # parent side: exactly one when the link is required, zero-or-one when it may be empty
                left = "||" if not column.nullable else "|o"
                out.append(f'    {parent} {left}--o{{ {table.name} : "{column.name}"')
    return "\n".join(out)


def build_markdown() -> str:
    used = sorted(t.name for t in Base.metadata.sorted_tables if t.name not in UNUSED)
    missing = [t for t in used if t not in PURPOSE]
    assert not missing, f"describe these tables in PURPOSE (app/db/erd.py): {missing}"
    rows = "\n".join(f"| `{t}` | {PURPOSE[t]} |" for t in used)
    unused = "\n".join(f"| `{t}` | {why} |" for t, why in sorted(UNUSED.items()) if t in Base.metadata.tables)
    return f"""# Hardware Hub: database diagram

Generated from the SQLAlchemy models by `python -m app.db.erd --markdown`. Do not edit by hand:
change a model and run it again.

PK = primary key, FK = foreign key, UK = covered by a unique index.
A line from `a` to `b` means one `a` can have many `b`. A link that may be empty
(`symptom.product_id`, `unmatched_query.resolved_symptom_id`) is drawn with a zero-or-one end.

```mermaid
{build_mermaid()}
```

## What each table is for

| Table | Purpose |
|-------|---------|
{rows}

## Tables that exist but no feature uses yet

They are left in the models so nothing breaks, and are not drawn above.

| Table | Why it is unused |
|-------|------------------|
{unused}

An older chat database may also still hold `chat_session`, `chat_log` and `feedback`
tables from before the chat became stateless. No model uses them and they are harmless.

## Making an image

```
npm install -g @mermaid-js/mermaid-cli
python -m app.db.erd > docs/erd.mmd
mmdc -i docs/erd.mmd -o docs/erd.svg
```
"""


if __name__ == "__main__":
    if "--markdown" in sys.argv:
        print(build_markdown())
    else:
        print(build_mermaid("--all" in sys.argv))