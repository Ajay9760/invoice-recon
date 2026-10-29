"""The 12 reconciliation / validation rules, all vectorised with pandas.

Rules 1-8 are data-quality checks on invoices, 9-11 reconcile invoices against payments,
12 finds payments that match no invoice. Rules 9-11 look only at the first occurrence of an
invoice (duplicates are reported by rule 2) and only at invoices with a positive total.
"""
import pandas as pd

from app.config import TOLERANCE as TOL
from app.config import VALID_CURRENCIES

EXCEPTION_COLS = ["rule_code", "severity", "invoice_id", "payment_id", "detail"]


def prepare(inv: pd.DataFrame, pay: pd.DataFrame, vendors: pd.DataFrame, tax_rates: pd.DataFrame):
    """Enrich invoices with vendor country, tax rate, duplicate flag and amount paid."""
    inv = inv.sort_values("id").reset_index(drop=True).copy()
    inv["invoice_date"] = pd.to_datetime(inv["invoice_date"])
    inv["due_date"] = pd.to_datetime(inv["due_date"])
    inv["vendor_id"] = pd.to_numeric(inv["vendor_id"])  # NULLs may arrive as object dtype
    inv = inv.merge(vendors[["id", "country"]].rename(columns={"id": "vendor_id"}),
                    on="vendor_id", how="left")
    inv["rate"] = inv["country"].map(tax_rates.set_index("country")["rate"])
    inv["is_dup"] = inv.duplicated(["vendor_code", "invoice_no"], keep="first")
    firsts = inv.loc[~inv["is_dup"], ["vendor_code", "invoice_no", "id"]].rename(columns={"id": "match_id"})
    pay = pay.merge(firsts, on=["vendor_code", "invoice_no"], how="left")
    inv["paid"] = inv["id"].map(pay.groupby("match_id")["amount"].sum()).fillna(0.0)
    return inv, pay


def _hit(code, severity, df, mask, detail, kind="invoice"):
    sel = df[mask]
    out = pd.DataFrame({"rule_code": code, "severity": severity,
                        "invoice_id": sel["id"] if kind == "invoice" else pd.NA,
                        "payment_id": sel["id"] if kind == "payment" else pd.NA,
                        "detail": detail(sel)})
    return out[EXCEPTION_COLS]


def _s(x):
    return x.astype(str)


def r01_missing_vendor(inv, pay, as_of):
    return _hit("MISSING_VENDOR", "HIGH", inv, inv["vendor_id"].isna(),
                lambda d: "Vendor code '" + d["vendor_code"] + "' not in vendor master")


def r02_duplicate_invoice(inv, pay, as_of):
    return _hit("DUPLICATE_INVOICE", "HIGH", inv, inv["is_dup"],
                lambda d: "Duplicate of invoice " + d["invoice_no"] + " from vendor '" + d["vendor_code"] + "'")


def r03_non_positive_amount(inv, pay, as_of):
    return _hit("NON_POSITIVE_AMOUNT", "HIGH", inv, (inv["net_amount"] <= 0) | (inv["total_amount"] <= 0),
                lambda d: "Net " + _s(d["net_amount"]) + ", total " + _s(d["total_amount"]) + " is not positive")


def r04_tax_mismatch(inv, pay, as_of):
    expected = (inv["net_amount"] * inv["rate"]).round(2)
    mask = inv["rate"].notna() & (inv["net_amount"] > 0) & ((inv["tax_amount"] - expected).abs() > TOL)
    return _hit("TAX_MISMATCH", "MEDIUM", inv, mask,
                lambda d: "Tax " + _s(d["tax_amount"]) + " differs from expected " + _s(expected[d.index]))


def r05_total_mismatch(inv, pay, as_of):
    expected = (inv["net_amount"] + inv["tax_amount"]).round(2)
    mask = (inv["total_amount"] - expected).abs() > TOL
    return _hit("TOTAL_MISMATCH", "MEDIUM", inv, mask,
                lambda d: "Total " + _s(d["total_amount"]) + " differs from net+tax " + _s(expected[d.index]))


def r06_future_dated(inv, pay, as_of):
    return _hit("FUTURE_DATED", "MEDIUM", inv, inv["invoice_date"] > pd.Timestamp(as_of),
                lambda d: "Invoice date " + _s(d["invoice_date"].dt.date) + " is after " + str(as_of))


def r07_due_before_issue(inv, pay, as_of):
    return _hit("DUE_BEFORE_ISSUE", "MEDIUM", inv, inv["due_date"] < inv["invoice_date"],
                lambda d: "Due date " + _s(d["due_date"].dt.date) + " is before invoice date " + _s(d["invoice_date"].dt.date))


def r08_invalid_currency(inv, pay, as_of):
    return _hit("INVALID_CURRENCY", "LOW", inv, ~inv["currency"].isin(VALID_CURRENCIES),
                lambda d: "Currency '" + d["currency"] + "' is not supported")


def _open(inv):
    return (~inv["is_dup"]) & (inv["total_amount"] > 0)


def r09_unpaid_overdue(inv, pay, as_of):
    mask = _open(inv) & (inv["due_date"] < pd.Timestamp(as_of)) & (inv["paid"] <= TOL)
    return _hit("UNPAID_OVERDUE", "HIGH", inv, mask,
                lambda d: "No payment; due " + _s(d["due_date"].dt.date) + ", total " + _s(d["total_amount"]))


def r10_overpaid(inv, pay, as_of):
    mask = _open(inv) & (inv["paid"] > inv["total_amount"] + TOL)
    return _hit("OVERPAID", "MEDIUM", inv, mask,
                lambda d: "Paid " + _s(d["paid"].round(2)) + " exceeds total " + _s(d["total_amount"]))


def r11_partially_paid_overdue(inv, pay, as_of):
    mask = (_open(inv) & (inv["due_date"] < pd.Timestamp(as_of)) & (inv["paid"] > TOL)
            & (inv["paid"] < inv["total_amount"] - TOL))
    return _hit("PARTIALLY_PAID_OVERDUE", "HIGH", inv, mask,
                lambda d: "Paid " + _s(d["paid"].round(2)) + " of " + _s(d["total_amount"]) + ", past due")


def r12_orphan_payment(inv, pay, as_of):
    return _hit("ORPHAN_PAYMENT", "MEDIUM", pay, pay["match_id"].isna(),
                lambda d: "Payment " + d["payment_ref"] + " references unknown invoice " + d["invoice_no"],
                kind="payment")


RULES = [r01_missing_vendor, r02_duplicate_invoice, r03_non_positive_amount, r04_tax_mismatch,
         r05_total_mismatch, r06_future_dated, r07_due_before_issue, r08_invalid_currency,
         r09_unpaid_overdue, r10_overpaid, r11_partially_paid_overdue, r12_orphan_payment]


def run_all(inv, pay, vendors, tax_rates, as_of) -> pd.DataFrame:
    inv, pay = prepare(inv, pay, vendors, tax_rates)
    parts = [rule(inv, pay, as_of) for rule in RULES]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=EXCEPTION_COLS)
    return pd.concat(parts, ignore_index=True)
