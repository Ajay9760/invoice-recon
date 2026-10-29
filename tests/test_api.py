import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from conftest import AS_OF, load_generated

INV_CSV = ("invoice_no,vendor_code,customer_code,invoice_date,due_date,currency,net_amount,tax_amount,total_amount\n"
           "INV-1,V0001,C0001,2026-01-01,2026-01-31,INR,100,18,118\n")
PAY_CSV = "payment_ref,vendor_code,invoice_no,payment_date,amount\nPAY-1,V0001,INV-1,2026-02-01,118\n"


@pytest.fixture
def client(engine):
    return TestClient(create_app(engine))


@pytest.fixture
def loaded(engine, client):
    load_generated(engine, n=2000)
    client.post("/reconcile", params={"as_of": AS_OF.isoformat()})
    return client


def files(inv=INV_CSV, pay=PAY_CSV):
    return {"invoices": ("i.csv", io.BytesIO(inv.encode()), "text/csv"),
            "payments": ("p.csv", io.BytesIO(pay.encode()), "text/csv")}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_summary_counts(loaded):
    s = loaded.get("/summary").json()
    assert s["invoices"] == 2000 and s["exceptions"] == 120 and len(s["by_rule"]) == 12


def test_summary_severity_totals_match(loaded):
    s = loaded.get("/summary").json()
    assert sum(s["by_severity"].values()) == s["exceptions"]


def test_exceptions_pagination(loaded):
    r = loaded.get("/exceptions", params={"limit": 7, "offset": 3}).json()
    assert r["total"] == 120 and len(r["items"]) == 7 and r["offset"] == 3


def test_exceptions_filter_by_rule(loaded):
    r = loaded.get("/exceptions", params={"rule": "OVERPAID"}).json()
    assert r["total"] == 10 and all(i["rule_code"] == "OVERPAID" for i in r["items"])


def test_exceptions_filter_by_severity(loaded):
    r = loaded.get("/exceptions", params={"severity": "LOW", "limit": 500}).json()
    assert r["total"] == 10 and {i["rule_code"] for i in r["items"]} == {"INVALID_CURRENCY"}


def test_exceptions_limit_above_500_is_rejected(loaded):
    assert loaded.get("/exceptions", params={"limit": 501}).status_code == 422


def test_invoice_detail_includes_exceptions(loaded):
    item = loaded.get("/exceptions", params={"rule": "OVERPAID"}).json()["items"][0]
    d = loaded.get(f"/invoices/{item['invoice_id']}").json()
    assert d["invoice"]["id"] == item["invoice_id"]
    assert any(e["rule_code"] == "OVERPAID" for e in d["exceptions"])
    assert d["paid_total"] > d["invoice"]["total_amount"]


def test_unknown_invoice_returns_404(loaded):
    assert loaded.get("/invoices/99999999").status_code == 404


def test_trends_are_grouped_by_month(loaded):
    rows = loaded.get("/trends").json()
    assert rows and set(rows[0]) == {"month", "rule_code", "count"}
    assert sum(r["count"] for r in rows) == 120


def test_upload_csv_then_reconcile(client):
    assert client.post("/data/upload", files=files()).json()["invoices_loaded"] == 1
    client.post("/reconcile", params={"as_of": "2026-06-30"})
    s = client.get("/summary").json()
    assert s["by_rule"][0]["rule_code"] == "MISSING_VENDOR"  # no vendor master loaded


def test_upload_with_missing_column_returns_422(client):
    bad = INV_CSV.replace("currency,", "")
    assert client.post("/data/upload", files=files(inv=bad)).status_code == 422


def test_reconcile_with_bad_date_returns_422(client):
    assert client.post("/reconcile", params={"as_of": "yesterday"}).status_code == 422


def test_generate_rejects_too_small_n(client):
    assert client.post("/data/generate", params={"n": 10}).status_code == 422
