"""Unit tests for each of the 12 rules on tiny hand-built frames (one bad case, one good case)."""
from datetime import date

import pandas as pd

from app import rules

AS_OF = date(2026, 6, 30)
VENDORS = pd.DataFrame({"id": [1], "code": ["V0001"], "country": ["IN"]})
TAX = pd.DataFrame({"country": ["IN"], "rate": [0.18]})
PAY_COLS = ["id", "payment_ref", "vendor_code", "invoice_no", "payment_date", "amount"]


def inv(**kw):
    base = dict(id=1, invoice_no="INV-1", vendor_code="V0001", vendor_id=1,
                invoice_date=date(2026, 1, 1), due_date=date(2026, 1, 31), currency="INR",
                net_amount=100.0, tax_amount=18.0, total_amount=118.0)
    base.update(kw)
    return base


def pay(**kw):
    base = dict(id=1, payment_ref="PAY-1", vendor_code="V0001", invoice_no="INV-1",
                payment_date=date(2026, 2, 1), amount=118.0)
    base.update(kw)
    return base


def run(inv_rows, pay_rows=(), as_of=AS_OF):
    i = pd.DataFrame(inv_rows)
    p = pd.DataFrame(list(pay_rows), columns=PAY_COLS).astype({"amount": float})
    return rules.run_all(i, p, VENDORS, TAX, as_of)


def codes(df):
    return sorted(df["rule_code"].tolist())


PAID = [pay()]


def test_clean_invoice_has_no_exceptions():
    assert codes(run([inv()], PAID)) == []


# 1 MISSING_VENDOR
def test_r01_flags_unknown_vendor():
    out = run([inv(vendor_code="V9999", vendor_id=None)], [pay(vendor_code="V9999")])
    assert codes(out) == ["MISSING_VENDOR"]


def test_r01_passes_known_vendor():
    assert "MISSING_VENDOR" not in codes(run([inv()], PAID))


# 2 DUPLICATE_INVOICE
def test_r02_flags_second_occurrence_only():
    out = run([inv(id=1), inv(id=2)], PAID)
    dup = out[out["rule_code"] == "DUPLICATE_INVOICE"]
    assert dup["invoice_id"].tolist() == [2]


def test_r02_passes_distinct_invoice_numbers():
    assert "DUPLICATE_INVOICE" not in codes(run([inv(id=1), inv(id=2, invoice_no="INV-2")],
                                                [pay(), pay(id=2, payment_ref="PAY-2", invoice_no="INV-2")]))


def test_duplicate_is_not_also_reported_unpaid():
    assert codes(run([inv(id=1), inv(id=2)], PAID)) == ["DUPLICATE_INVOICE"]


# 3 NON_POSITIVE_AMOUNT
def test_r03_flags_zero_and_negative():
    out = run([inv(net_amount=0.0, tax_amount=0.0, total_amount=0.0),
               inv(id=2, invoice_no="INV-2", net_amount=-100.0, tax_amount=-18.0, total_amount=-118.0)])
    assert codes(out) == ["NON_POSITIVE_AMOUNT", "NON_POSITIVE_AMOUNT"]


def test_r03_passes_positive():
    assert "NON_POSITIVE_AMOUNT" not in codes(run([inv()], PAID))


# 4 TAX_MISMATCH
def test_r04_flags_wrong_tax():
    out = run([inv(tax_amount=40.0, total_amount=140.0)], [pay(amount=140.0)])
    assert codes(out) == ["TAX_MISMATCH"]


def test_r04_passes_correct_tax():
    assert "TAX_MISMATCH" not in codes(run([inv()], PAID))


def test_r04_tolerates_one_cent_difference():
    assert codes(run([inv(tax_amount=18.01, total_amount=118.01)], [pay(amount=118.01)])) == []


def test_r04_skipped_when_vendor_unknown():
    out = run([inv(vendor_id=None, tax_amount=99.0, total_amount=199.0)], [pay(amount=199.0)])
    assert "TAX_MISMATCH" not in codes(out)


# 5 TOTAL_MISMATCH
def test_r05_flags_wrong_total():
    out = run([inv(total_amount=158.0)], [pay(amount=158.0)])
    assert codes(out) == ["TOTAL_MISMATCH"]


def test_r05_passes_correct_total():
    assert "TOTAL_MISMATCH" not in codes(run([inv()], PAID))


# 6 FUTURE_DATED
def test_r06_flags_future_invoice_date():
    out = run([inv(invoice_date=date(2026, 8, 1), due_date=date(2026, 9, 1))])
    assert codes(out) == ["FUTURE_DATED"]


def test_r06_passes_past_date():
    assert "FUTURE_DATED" not in codes(run([inv()], PAID))


# 7 DUE_BEFORE_ISSUE
def test_r07_flags_due_before_invoice_date():
    out = run([inv(due_date=date(2025, 12, 25))], PAID)
    assert codes(out) == ["DUE_BEFORE_ISSUE"]


def test_r07_passes_normal_terms():
    assert "DUE_BEFORE_ISSUE" not in codes(run([inv()], PAID))


# 8 INVALID_CURRENCY
def test_r08_flags_unknown_currency():
    assert codes(run([inv(currency="XXX")], PAID)) == ["INVALID_CURRENCY"]


def test_r08_passes_supported_currency():
    assert "INVALID_CURRENCY" not in codes(run([inv(currency="USD")], PAID))


# 9 UNPAID_OVERDUE
def test_r09_flags_overdue_without_payment():
    assert codes(run([inv()])) == ["UNPAID_OVERDUE"]


def test_r09_passes_when_not_yet_due():
    assert codes(run([inv(due_date=date(2026, 7, 31))])) == []


def test_r09_boundary_due_today_is_not_overdue():
    assert codes(run([inv(due_date=AS_OF)])) == []


# 10 OVERPAID
def test_r10_flags_payment_above_total():
    assert codes(run([inv()], [pay(amount=130.0)])) == ["OVERPAID"]


def test_r10_passes_exact_payment():
    assert "OVERPAID" not in codes(run([inv()], PAID))


# 11 PARTIALLY_PAID_OVERDUE
def test_r11_flags_partial_payment_past_due():
    assert codes(run([inv()], [pay(amount=50.0)])) == ["PARTIALLY_PAID_OVERDUE"]


def test_r11_passes_two_instalments_that_sum_to_total():
    out = run([inv()], [pay(amount=70.8), pay(id=2, payment_ref="PAY-2", amount=47.2)])
    assert codes(out) == []


def test_r11_partial_not_flagged_before_due_date():
    assert codes(run([inv(due_date=date(2026, 7, 31))], [pay(amount=50.0)])) == []


# 12 ORPHAN_PAYMENT
def test_r12_flags_payment_for_unknown_invoice():
    out = run([inv()], [pay(), pay(id=2, payment_ref="PAY-2", invoice_no="INV-404")])
    assert codes(out) == ["ORPHAN_PAYMENT"]
    assert out["payment_id"].tolist() == [2]


def test_r12_passes_matched_payment():
    assert "ORPHAN_PAYMENT" not in codes(run([inv()], PAID))


def test_exactly_twelve_rules_registered():
    assert len(rules.RULES) == 12
