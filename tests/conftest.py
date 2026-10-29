import os
from collections import defaultdict
from datetime import date

import pytest
from sqlalchemy import select

from app import db, generator, pipeline

AS_OF = date(2026, 10, 28)


@pytest.fixture
def engine(tmp_path):
    """SQLite by default. Set TEST_DATABASE_URL (e.g. a PostgreSQL URL) to run the same suite there."""
    url = os.getenv("TEST_DATABASE_URL")
    eng = db.get_engine(url or f"sqlite:///{tmp_path}/test.db")
    if url:
        db.metadata.drop_all(eng)
    db.init_db(eng)
    yield eng
    eng.dispose()


def load_generated(engine, n=5000, seed=7):
    data = generator.generate(n=n, seed=seed, as_of=AS_OF)
    pipeline.load_reference(engine, data["vendors"], data["customers"], data["tax_rates"])
    pipeline.ingest(engine, data["invoices"], data["payments"])
    return data


def flagged(engine) -> dict:
    """{rule_code: set of invoice_no (or payment_ref for payment rules)} from the exceptions table."""
    e = db.exceptions
    j = (e.outerjoin(db.invoices, e.c.invoice_id == db.invoices.c.id)
          .outerjoin(db.payments, e.c.payment_id == db.payments.c.id))
    with engine.connect() as conn:
        rows = conn.execute(select(e.c.rule_code, db.invoices.c.invoice_no,
                                   db.payments.c.payment_ref).select_from(j)).all()
    out = defaultdict(set)
    for rule, inv_no, ref in rows:
        out[rule].add(inv_no if inv_no is not None else ref)
    return out
