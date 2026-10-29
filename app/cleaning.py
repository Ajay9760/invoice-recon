"""pandas cleaning step: normalise text, parse dates/amounts, reject unusable rows."""
import pandas as pd

INVOICE_COLS = ["invoice_no", "vendor_code", "customer_code", "invoice_date", "due_date",
                "currency", "net_amount", "tax_amount", "total_amount"]
PAYMENT_COLS = ["payment_ref", "vendor_code", "invoice_no", "payment_date", "amount"]


def _text(s: pd.Series, upper: bool = True) -> pd.Series:
    s = s.astype("string").fillna("").str.strip()
    return (s.str.upper() if upper else s).astype(object)


def _check_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")


def clean_invoices(df: pd.DataFrame):
    """Return (clean, rejected). A row is rejected if invoice_no is blank or any
    date/amount cannot be parsed."""
    _check_columns(df, INVOICE_COLS)
    d = df[INVOICE_COLS].copy()
    for c in ("invoice_no", "vendor_code", "customer_code", "currency"):
        d[c] = _text(d[c])
    for c in ("invoice_date", "due_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("net_amount", "tax_amount", "total_amount"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    bad = (d["invoice_no"] == "") | d[["invoice_date", "due_date", "net_amount",
                                       "tax_amount", "total_amount"]].isna().any(axis=1)
    clean = d[~bad].copy()
    for c in ("invoice_date", "due_date"):
        clean[c] = clean[c].dt.date
    for c in ("net_amount", "tax_amount", "total_amount"):
        clean[c] = clean[c].round(2)
    return clean.reset_index(drop=True), df[bad.to_numpy()]


def clean_payments(df: pd.DataFrame):
    _check_columns(df, PAYMENT_COLS)
    d = df[PAYMENT_COLS].copy()
    for c in ("payment_ref", "vendor_code", "invoice_no"):
        d[c] = _text(d[c])
    d["payment_date"] = pd.to_datetime(d["payment_date"], errors="coerce")
    d["amount"] = pd.to_numeric(d["amount"], errors="coerce")
    bad = (d["payment_ref"] == "") | (d["invoice_no"] == "") | d[["payment_date", "amount"]].isna().any(axis=1)
    clean = d[~bad].copy()
    clean["payment_date"] = clean["payment_date"].dt.date
    clean["amount"] = clean["amount"].round(2)
    return clean.reset_index(drop=True), df[bad.to_numpy()]
