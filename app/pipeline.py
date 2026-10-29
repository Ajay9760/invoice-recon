"""ETL pipeline: load reference data, ingest (clean -> resolve keys -> insert), reconcile."""
from datetime import date, datetime

import pandas as pd
from sqlalchemy import delete, insert, select

from app import db
from app.cleaning import clean_invoices, clean_payments
from app.rules import run_all


def _records(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(df.notna(), None).to_dict("records")


def load_reference(engine, vendors: pd.DataFrame, customers: pd.DataFrame, tax_rates: pd.DataFrame) -> None:
    with engine.begin() as conn:
        for t in db.DELETE_ORDER + [db.tax_rates, db.customers, db.vendors]:
            conn.execute(delete(t))
        conn.execute(insert(db.vendors), _records(vendors))
        conn.execute(insert(db.customers), _records(customers))
        conn.execute(insert(db.tax_rates), _records(tax_rates))


def ingest(engine, invoices_raw: pd.DataFrame, payments_raw: pd.DataFrame) -> dict:
    """Replace all transactional data with the given raw frames."""
    inv, inv_rejected = clean_invoices(invoices_raw)
    pay, pay_rejected = clean_payments(payments_raw)
    with engine.begin() as conn:
        for t in db.DELETE_ORDER:
            conn.execute(delete(t))
        vmap = dict(conn.execute(select(db.vendors.c.code, db.vendors.c.id)).all())
        cmap = dict(conn.execute(select(db.customers.c.code, db.customers.c.id)).all())
        inv["vendor_id"] = inv["vendor_code"].map(vmap).astype("Int64")
        inv["customer_id"] = inv["customer_code"].map(cmap).astype("Int64")
        cols = ["invoice_no", "vendor_code", "vendor_id", "customer_id", "invoice_date",
                "due_date", "currency", "net_amount", "tax_amount", "total_amount"]
        if len(inv):  # an all-invalid upload must not crash the insert
            conn.execute(insert(db.invoices), _records(inv[cols]))
        keys = (pd.read_sql(select(db.invoices.c.id, db.invoices.c.vendor_code, db.invoices.c.invoice_no), conn)
                .sort_values("id").drop_duplicates(["vendor_code", "invoice_no"])
                .rename(columns={"id": "invoice_id"}))
        pay = pay.merge(keys, on=["vendor_code", "invoice_no"], how="left")
        pay["invoice_id"] = pay["invoice_id"].astype("Int64")
        if len(pay):
            conn.execute(insert(db.payments), _records(pay))
    return {"invoices_loaded": len(inv), "payments_loaded": len(pay),
            "invoices_rejected": len(inv_rejected), "payments_rejected": len(pay_rejected)}


def reconcile(engine, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    with engine.begin() as conn:
        inv = pd.read_sql(select(db.invoices), conn)
        pay = pd.read_sql(select(db.payments), conn)
        ven = pd.read_sql(select(db.vendors), conn)
        tax = pd.read_sql(select(db.tax_rates), conn)
        exc = run_all(inv, pay, ven, tax, as_of)
        conn.execute(delete(db.exceptions))
        if len(exc):
            exc = exc.assign(run_at=datetime.now())
            conn.execute(insert(db.exceptions), _records(exc))
    return {"as_of": as_of.isoformat(), "exceptions": len(exc)}
