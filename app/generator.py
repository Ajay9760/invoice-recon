"""cd Synthetic data generator with injected anomalies and exact ground truth.

All data is synthetic. Each injected anomaly goes into its own disjoint block of invoices,
so tests can check that every rule flags EXACTLY the injected records (no misses, no extras).
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

COUNTRY_RATES = {"IN": 0.18, "US": 0.07, "GB": 0.20, "DE": 0.19}
CURRENCIES = ["INR", "USD", "EUR", "GBP"]
INVOICE_RULES = ["MISSING_VENDOR", "DUPLICATE_INVOICE", "NON_POSITIVE_AMOUNT", "TAX_MISMATCH",
                 "TOTAL_MISMATCH", "FUTURE_DATED", "DUE_BEFORE_ISSUE", "INVALID_CURRENCY",
                 "UNPAID_OVERDUE", "OVERPAID", "PARTIALLY_PAID_OVERDUE"]


def reference_data(n_vendors: int = 200, n_customers: int = 500):
    countries = list(COUNTRY_RATES)
    vendors = pd.DataFrame({
        "code": [f"V{i:04d}" for i in range(1, n_vendors + 1)],
        "name": [f"Synthetic Vendor {i:04d}" for i in range(1, n_vendors + 1)],
        "country": [countries[i % len(countries)] for i in range(n_vendors)],
    })
    customers = pd.DataFrame({
        "code": [f"C{i:04d}" for i in range(1, n_customers + 1)],
        "name": [f"Synthetic Customer {i:04d}" for i in range(1, n_customers + 1)],
    })
    tax = pd.DataFrame({"country": list(COUNTRY_RATES), "rate": list(COUNTRY_RATES.values())})
    return vendors, customers, tax


def generate(n: int = 100_000, seed: int = 42, as_of: date | None = None):
    """Return dict with vendors, customers, tax_rates, invoices (exactly n rows),
    payments, truth ({rule_code: sorted list of invoice_no / payment_ref})."""
    as_of = as_of or date.today()
    rng = np.random.default_rng(seed)
    k = max(1, int(n * 0.005))                      # anomalies per rule
    n_base = n - k                                  # k duplicate rows are appended
    if len(INVOICE_RULES) * k > n_base:
        raise ValueError("n too small for the anomaly blocks")
    vendors, customers, tax = reference_data()
    country = dict(zip(vendors["code"], vendors["country"]))

    vcodes = rng.choice(vendors["code"].to_numpy(), n_base)
    ccodes = rng.choice(customers["code"].to_numpy(), n_base)
    days_ago = rng.integers(1, 541, n_base)
    terms = rng.choice([15, 30, 45, 60], n_base)
    inv_date = np.array([as_of - timedelta(days=int(d)) for d in days_ago], dtype="datetime64[D]")
    due_date = inv_date + terms.astype("timedelta64[D]")
    net = np.round(rng.uniform(100, 50_000, n_base), 2)
    rate = np.array([COUNTRY_RATES[country[v]] for v in vcodes])
    tax_amt = np.round(net * rate, 2)
    total = np.round(net + tax_amt, 2)
    currency = rng.choice(CURRENCIES, n_base).astype(object)
    inv_no = np.array([f"INV-{i + 1:07d}" for i in range(n_base)], dtype=object)
    vcodes = vcodes.astype(object)

    # disjoint anomaly blocks
    perm = rng.permutation(n_base)
    block = {rule: perm[i * k:(i + 1) * k] for i, rule in enumerate(INVOICE_RULES)}
    truth = {}

    ix = block["MISSING_VENDOR"]
    vcodes[ix] = np.where(np.arange(k) % 2 == 0, "", "V9999")
    ix = block["NON_POSITIVE_AMOUNT"]
    net[ix] = np.where(np.arange(k) % 2 == 0, -net[ix], 0.0)
    tax_amt[ix] = np.round(net[ix] * rate[ix], 2)
    total[ix] = np.round(net[ix] + tax_amt[ix], 2)
    ix = block["TAX_MISMATCH"]
    tax_amt[ix] = np.round(tax_amt[ix] + 25.0, 2)
    total[ix] = np.round(net[ix] + tax_amt[ix], 2)
    ix = block["TOTAL_MISMATCH"]
    total[ix] = np.round(total[ix] + 40.0, 2)
    ix = block["FUTURE_DATED"]
    inv_date[ix] = np.datetime64(as_of) + rng.integers(5, 61, k).astype("timedelta64[D]")
    due_date[ix] = inv_date[ix] + terms[ix].astype("timedelta64[D]")
    ix = block["DUE_BEFORE_ISSUE"]
    due_date[ix] = inv_date[ix] - rng.integers(1, 11, k).astype("timedelta64[D]")
    ix = block["INVALID_CURRENCY"]
    currency[ix] = "XXX"
    for rule in ("UNPAID_OVERDUE", "OVERPAID", "PARTIALLY_PAID_OVERDUE"):
        ix = block[rule]                            # make them clearly overdue (>= 60 days)
        inv_date[ix] = np.datetime64(as_of) - rng.integers(120, 501, k).astype("timedelta64[D]")
        due_date[ix] = inv_date[ix] + terms[ix].astype("timedelta64[D]")

    # ---- payments -------------------------------------------------------------------
    no_payment = np.zeros(n_base, dtype=bool)
    no_payment[block["NON_POSITIVE_AMOUNT"]] = True
    no_payment[block["FUTURE_DATED"]] = True
    no_payment[block["UNPAID_OVERDUE"]] = True
    as_of64 = np.datetime64(as_of)
    overdue = due_date < as_of64
    paid_full = (~no_payment) & (overdue | (rng.random(n_base) < 0.6))
    paid_full[block["OVERPAID"]] = False
    paid_full[block["PARTIALLY_PAID_OVERDUE"]] = False
    pay_rows = []

    def add(idx, amounts, lag):
        for i, amt, lg in zip(idx, amounts, lag):
            pdte = min(inv_date[i] + np.timedelta64(int(lg), "D"), as_of64)
            pay_rows.append((vcodes[i], inv_no[i], pdte, float(amt)))

    full_idx = np.flatnonzero(paid_full)
    split = rng.random(len(full_idx)) < 0.10        # 10% paid in two instalments
    single, two = full_idx[~split], full_idx[split]
    add(single, total[single], rng.integers(1, 40, len(single)))
    first = np.round(total[two] * 0.6, 2)
    add(two, first, rng.integers(1, 20, len(two)))
    add(two, np.round(total[two] - first, 2), rng.integers(20, 40, len(two)))
    ix = block["OVERPAID"]
    add(ix, np.round(total[ix] * 1.1, 2), rng.integers(1, 40, k))
    ix = block["PARTIALLY_PAID_OVERDUE"]
    add(ix, np.round(total[ix] * 0.5, 2), rng.integers(1, 40, k))

    payments = pd.DataFrame(pay_rows, columns=["vendor_code", "invoice_no", "payment_date", "amount"])
    # orphan payments (invoice_no that does not exist)
    orphan = pd.DataFrame({
        "vendor_code": rng.choice(vendors["code"].to_numpy(), k),
        "invoice_no": [f"INV-9{j:06d}" for j in range(k)],
        "payment_date": [as_of - timedelta(days=int(d)) for d in rng.integers(1, 300, k)],
        "amount": np.round(rng.uniform(100, 20_000, k), 2),
    })
    payments = pd.concat([payments, orphan], ignore_index=True)
    payments.insert(0, "payment_ref", [f"PAY-{i + 1:07d}" for i in range(len(payments))])
    payments["payment_date"] = pd.to_datetime(payments["payment_date"]).dt.date

    # ---- invoices (+ appended duplicates) ---------------------------------------------
    invoices = pd.DataFrame({
        "invoice_no": inv_no, "vendor_code": vcodes, "customer_code": ccodes,
        "invoice_date": pd.to_datetime(inv_date).date, "due_date": pd.to_datetime(due_date).date,
        "currency": currency, "net_amount": net, "tax_amount": tax_amt, "total_amount": total,
    })
    dup_src = block["DUPLICATE_INVOICE"]
    invoices = pd.concat([invoices, invoices.iloc[dup_src]], ignore_index=True)

    for rule in INVOICE_RULES:
        truth[rule] = sorted(inv_no[block[rule]].tolist())
    truth["ORPHAN_PAYMENT"] = sorted(orphan_refs(payments, k))
    return {"vendors": vendors, "customers": customers, "tax_rates": tax,
            "invoices": invoices, "payments": payments, "truth": truth, "as_of": as_of}


def orphan_refs(payments: pd.DataFrame, k: int):
    return payments.loc[payments["invoice_no"].str.startswith("INV-9"), "payment_ref"].tolist()


def write_csvs(data: dict, out_dir: str) -> None:
    import json
    import os
    os.makedirs(out_dir, exist_ok=True)
    for name in ("vendors", "customers", "tax_rates", "invoices", "payments"):
        data[name].to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)
    with open(os.path.join(out_dir, "truth.json"), "w") as fh:
        json.dump(data["truth"], fh)
