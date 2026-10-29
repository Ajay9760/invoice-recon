"""Relational schema (6 tables) and engine helper.

vendor_code / invoice_no are stored as received (text) AND resolved to foreign keys
(vendor_id, invoice_id) where possible. Unresolved references stay NULL so bad data can
be loaded and then reported as exceptions instead of being rejected at the door.
"""
from sqlalchemy import (Column, Date, DateTime, ForeignKey, Index, Integer, MetaData,
                        Numeric, String, Table, create_engine)

from app.config import DATABASE_URL

metadata = MetaData()
MONEY = Numeric(14, 2, asdecimal=False)

vendors = Table(
    "vendors", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(32), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("country", String(2), nullable=False),
)

customers = Table(
    "customers", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(32), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
)

tax_rates = Table(
    "tax_rates", metadata,
    Column("id", Integer, primary_key=True),
    Column("country", String(2), nullable=False, unique=True),
    Column("rate", Numeric(5, 4, asdecimal=False), nullable=False),
)

invoices = Table(
    "invoices", metadata,
    Column("id", Integer, primary_key=True),
    Column("invoice_no", String(32), nullable=False),
    Column("vendor_code", String(32), nullable=False, default=""),
    Column("vendor_id", Integer, ForeignKey("vendors.id"), nullable=True),
    Column("customer_id", Integer, ForeignKey("customers.id"), nullable=True),
    Column("invoice_date", Date, nullable=False),
    Column("due_date", Date, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("net_amount", MONEY, nullable=False),
    Column("tax_amount", MONEY, nullable=False),
    Column("total_amount", MONEY, nullable=False),
    Index("ix_invoices_key", "vendor_code", "invoice_no"),
    Index("ix_invoices_date", "invoice_date"),
)

payments = Table(
    "payments", metadata,
    Column("id", Integer, primary_key=True),
    Column("payment_ref", String(32), nullable=False),
    Column("vendor_code", String(32), nullable=False, default=""),
    Column("invoice_no", String(32), nullable=False),
    Column("invoice_id", Integer, ForeignKey("invoices.id"), nullable=True),
    Column("payment_date", Date, nullable=False),
    Column("amount", MONEY, nullable=False),
    Index("ix_payments_key", "vendor_code", "invoice_no"),
)

exceptions = Table(
    "exceptions", metadata,
    Column("id", Integer, primary_key=True),
    Column("rule_code", String(32), nullable=False, index=True),
    Column("severity", String(8), nullable=False),
    Column("invoice_id", Integer, ForeignKey("invoices.id"), nullable=True),
    Column("payment_id", Integer, ForeignKey("payments.id"), nullable=True),
    Column("detail", String(255), nullable=False),
    Column("run_at", DateTime, nullable=False),
)

# order matters for deletes (children first)
DELETE_ORDER = [exceptions, payments, invoices]


def get_engine(url: str | None = None):
    return create_engine(url or DATABASE_URL, future=True)


def init_db(engine) -> None:
    metadata.create_all(engine)
