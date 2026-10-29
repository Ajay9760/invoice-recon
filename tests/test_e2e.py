"""5 end-to-end tests: generated data -> ingest -> reconcile -> compare with injected ground truth."""
import io
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db, generator, pipeline
from app.main import create_app

from conftest import AS_OF, flagged, load_generated


def assert_exact(engine, truth):
    found = flagged(engine)
    assert set(found) == set(truth)
    for rule, expected in truth.items():
        assert found[rule] == set(expected), f"{rule}: detection differs from injected truth"


def test_e2e_every_rule_detects_exactly_the_injected_anomalies(engine):
    data = load_generated(engine, n=5000)
    pipeline.reconcile(engine, AS_OF)
    assert_exact(engine, data["truth"])


def test_e2e_csv_upload_via_api_matches_direct_pipeline(engine, tmp_path):
    data = generator.generate(n=3000, seed=11, as_of=AS_OF)
    pipeline.load_reference(engine, data["vendors"], data["customers"], data["tax_rates"])
    client = TestClient(create_app(engine))
    generator.write_csvs(data, str(tmp_path))
    with open(tmp_path / "invoices.csv", "rb") as fi, open(tmp_path / "payments.csv", "rb") as fp:
        r = client.post("/data/upload", files={"invoices": ("i.csv", fi, "text/csv"),
                                               "payments": ("p.csv", fp, "text/csv")})
    assert r.json()["invoices_loaded"] == 3000
    client.post("/reconcile", params={"as_of": AS_OF.isoformat()})
    assert_exact(engine, data["truth"])


def test_e2e_rerunning_ingest_and_reconcile_gives_identical_results(engine):
    data = load_generated(engine, n=3000)
    pipeline.reconcile(engine, AS_OF)
    first = {k: set(v) for k, v in flagged(engine).items()}
    pipeline.ingest(engine, data["invoices"], data["payments"])
    pipeline.reconcile(engine, AS_OF)
    assert {k: set(v) for k, v in flagged(engine).items()} == first


def test_e2e_api_flow_generate_reconcile_drill_down(engine):
    client = TestClient(create_app(engine))
    assert client.post("/data/generate", params={"n": 1000}).json()["invoices_loaded"] == 1000
    client.post("/reconcile")
    summary = client.get("/summary").json()
    assert summary["exceptions"] == 60 and all(r["count"] == 5 for r in summary["by_rule"])
    first = client.get("/exceptions", params={"rule": "UNPAID_OVERDUE"}).json()["items"][0]
    detail = client.get(f"/invoices/{first['invoice_id']}").json()
    assert detail["paid_total"] == 0 and detail["payments"] == []


@pytest.mark.slow
def test_e2e_full_scale_100k_invoices_exact_detection_and_runtime(engine):
    data = generator.generate(n=100_000, seed=42, as_of=AS_OF)
    assert len(data["invoices"]) == 100_000
    start = time.perf_counter()
    pipeline.load_reference(engine, data["vendors"], data["customers"], data["tax_rates"])
    pipeline.ingest(engine, data["invoices"], data["payments"])
    result = pipeline.reconcile(engine, AS_OF)
    elapsed = time.perf_counter() - start
    print(f"\n100K pipeline (ingest + reconcile): {elapsed:.1f}s, exceptions={result['exceptions']}")
    assert result["exceptions"] == 6000
    assert_exact(engine, data["truth"])
    assert elapsed < 60
