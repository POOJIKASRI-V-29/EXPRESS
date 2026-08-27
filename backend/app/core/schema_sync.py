"""Additive dev-bootstrap schema sync.

`create_all` creates missing *tables* but never alters existing ones, so a
model that gains a column would silently diverge from a database that already
has data in it. This walks the model metadata and issues `ALTER TABLE ... ADD
COLUMN` for anything missing.

It is deliberately one-directional: it only ever ADDs. It never drops, renames
or retypes a column, so it cannot destroy data. Alembic remains the production
path (see README) — this only keeps the frictionless dev bootstrap honest.
"""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn


def sync(engine, metadata) -> list[str]:
    """Add model columns that are missing from existing tables. Returns the
    list of `table.column` names that were added."""
    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names())
    added: list[str] = []

    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if table.name not in live_tables:
                continue  # create_all owns brand-new tables
            live_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in live_cols:
                    continue
                ddl = CreateColumn(col).compile(dialect=engine.dialect)
                # A column added to a populated table cannot be NOT NULL without a
                # default; add it nullable and let the model enforce it going forward.
                sql = str(ddl).replace(" NOT NULL", "")
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {sql}'))
                added.append(f"{table.name}.{col.name}")

    return added
