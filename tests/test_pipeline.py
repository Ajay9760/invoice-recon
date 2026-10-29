from datetime import date

import pandas as pd
from sqlalchemy import func, select

from app import db, generator, pipeline

from conftest import AS_OF, flagged, load_generated


def count(engine, table):
    with engine.connect() as c:
        return c.execute(select(func.count()).select_from(table)).scalar_one()


def test_schema_has_six_tables(engine):
    assert len(db.metadata.tables) == 6


def test_load_reference_inserts_rows(engine):
    v, c, t = generator.reference_data()
    pipeline.load_reference(engine, v, c, t)
    assert (count(engine, db.vendors), count(engine, db.customers), count(engine, db.tax_rates)) == (200, 500, 4)


def test_ingest_loads_all_clean_rows(engine):
    data = load_generated(engine, n=1000)
    assert count(engine, db.invoices) == 1000
    assert count(engine, db.payments) == len(data["payments"])


def test_unknown_vendor_gets_null_vendor_id(engine):
    load_generated(engine, n=1000)
    with engine.connect() as c:
        n_null = c.execute(select(func.count()).select_from(db.invoices)
                           .where(db.invoices.c.vendor_id.is_(None))).scalar_one()
    assert n_null == 5  # 0.5% of 1000 injected as missing vendor


def test_orphan_payment_gets_null_invoice_id(engine):
    load_generated(engine, n=1000)
    with engine.connect() as c:
        n_null = c.execute(select(func.count()).select_from(db.payments)
                           .where(db.payments.c.invoice_id.is_(None))).scalar_one()
    assert n_null == 5


def test_ingest_replaces_previous_transactions(engine):
    load_generated(engine, n=1000)
    load_generated(engine, n=1000)
    assert count(engine, db.invoices) == 1000


def test_reconcile_is_idempotent(engine):
    load_generated(engine, n=2000)
    first = pipeline.reconcile(engine, AS_OF)["exceptions"]
    second = pipeline.reconcile(engine, AS_OF)["exceptions"]
    assert first == second == count(engine, db.exceptions)


def test_bad_rows_are_counted_as_rejected(engine):
    inv = pd.DataFrame([dict(invoice_no="INV-1", vendor_code="V0001", customer_code="C0001",
                             invoice_date="oops", due_date="2026-01-31", currency="INR",
                             net_amount="1", tax_amount="0", total_amount="1")])
    pay = pd.DataFrame(columns=["payment_ref", "vendor_code", "invoice_no", "payment_date", "amount"])
    result = pipeline.ingest(engine, inv, pay)
    assert result["invoices_rejected"] == 1 and result["invoices_loaded"] == 0


def test_reconcile_with_no_data_returns_zero(engine):
    assert pipeline.reconcile(engine, date(2026, 1, 1))["exceptions"] == 0


def test_reference_reload_clears_transactions(engine):
    load_generated(engine, n=1000)
    v, c, t = generator.reference_data()
    pipeline.load_reference(engine, v, c, t)
    assert count(engine, db.invoices) == 0 and count(engine, db.exceptions) == 0


def test_flagged_helper_groups_by_rule(engine):
    load_generated(engine, n=1000)
    pipeline.reconcile(engine, AS_OF)
    assert len(flagged(engine)) == 12
