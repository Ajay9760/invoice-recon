from datetime import date

import pandas as pd
import pytest

from app.cleaning import clean_invoices, clean_payments


def raw_inv(**kw):
    row = dict(invoice_no="INV-1", vendor_code="V0001", customer_code="C0001", invoice_date="2026-01-01",
               due_date="2026-01-31", currency="inr", net_amount="100", tax_amount="18", total_amount="118")
    row.update(kw)
    return pd.DataFrame([row])


def raw_pay(**kw):
    row = dict(payment_ref="PAY-1", vendor_code="v0001", invoice_no="INV-1", payment_date="2026-02-01", amount="118")
    row.update(kw)
    return pd.DataFrame([row])


def test_invoice_text_is_stripped_and_uppercased():
    clean, _ = clean_invoices(raw_inv(invoice_no="  inv-1 ", vendor_code=" v0001", currency="inr"))
    assert clean.loc[0, "invoice_no"] == "INV-1"
    assert clean.loc[0, "vendor_code"] == "V0001"
    assert clean.loc[0, "currency"] == "INR"


def test_blank_vendor_code_becomes_empty_string():
    clean, _ = clean_invoices(raw_inv(vendor_code=""))
    assert clean.loc[0, "vendor_code"] == ""


def test_dates_become_python_dates():
    clean, _ = clean_invoices(raw_inv())
    assert clean.loc[0, "invoice_date"] == date(2026, 1, 1)


def test_unparseable_date_is_rejected():
    clean, rejected = clean_invoices(raw_inv(invoice_date="not a date"))
    assert len(clean) == 0 and len(rejected) == 1


def test_unparseable_amount_is_rejected():
    clean, rejected = clean_invoices(raw_inv(net_amount="abc"))
    assert len(clean) == 0 and len(rejected) == 1


def test_blank_invoice_number_is_rejected():
    clean, rejected = clean_invoices(raw_inv(invoice_no="   "))
    assert len(clean) == 0 and len(rejected) == 1


def test_amounts_are_rounded_to_cents():
    clean, _ = clean_invoices(raw_inv(net_amount="100.456"))
    assert clean.loc[0, "net_amount"] == 100.46


def test_missing_invoice_column_raises():
    with pytest.raises(ValueError, match="missing columns"):
        clean_invoices(raw_inv().drop(columns=["currency"]))


def test_good_rows_survive_alongside_bad_rows():
    df = pd.concat([raw_inv(), raw_inv(invoice_no="INV-2", due_date="bad")], ignore_index=True)
    clean, rejected = clean_invoices(df)
    assert clean["invoice_no"].tolist() == ["INV-1"] and len(rejected) == 1


def test_payment_codes_uppercased_and_date_parsed():
    clean, _ = clean_payments(raw_pay())
    assert clean.loc[0, "vendor_code"] == "V0001"
    assert clean.loc[0, "payment_date"] == date(2026, 2, 1)


def test_payment_bad_amount_is_rejected():
    clean, rejected = clean_payments(raw_pay(amount="x"))
    assert len(clean) == 0 and len(rejected) == 1


def test_payment_missing_column_raises():
    with pytest.raises(ValueError, match="missing columns"):
        clean_payments(raw_pay().drop(columns=["amount"]))
