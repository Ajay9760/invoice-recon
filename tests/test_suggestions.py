import pytest
from fastapi.testclient import TestClient

from app import llm
from app.main import create_app

from conftest import AS_OF, load_generated

KEY = {"X-API-Key": "secret"}


class FakeSuggester:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def suggest(self, rule_code, severity, detail):
        self.calls.append((rule_code, severity, detail))
        if self.error:
            raise self.error
        return self.result or llm.Suggestion("ESCALATE_TO_HUMAN", "fake", "llm", "fake-model")


def make(engine, suggester=None):
    load_generated(engine, n=2000)
    client = TestClient(create_app(engine, suggester or FakeSuggester()))
    client.post("/reconcile", params={"as_of": AS_OF.isoformat()})
    return client


@pytest.fixture(autouse=True)
def reviewer_key(monkeypatch):
    monkeypatch.setenv("REVIEWER_API_KEY", "secret")


def first_exception_id(client):
    return client.get("/exceptions", params={"limit": 1}).json()["items"][0]["id"]


def test_create_suggestion_is_pending_and_nothing_else_changes(engine):
    client = make(engine)
    before = client.get("/summary").json()
    r = client.post(f"/exceptions/{first_exception_id(client)}/suggestion")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PENDING" and body["source"] == "llm" and body["decided_at"] is None
    assert client.get("/summary").json() == before  # the agent never mutates reconciliation data


def test_unknown_exception_is_404(engine):
    assert make(engine).post("/exceptions/999999/suggestion").status_code == 404


def test_llm_failure_falls_back_to_rule_based(engine):
    client = make(engine, FakeSuggester(error=llm.SuggestionError("timeout")))
    r = client.post(f"/exceptions/{first_exception_id(client)}/suggestion")
    assert r.status_code == 201 and r.json()["source"] == "fallback"


def test_suggester_receives_exception_fields(engine):
    fake = FakeSuggester()
    client = make(engine, fake)
    client.post(f"/exceptions/{first_exception_id(client)}/suggestion")
    rule, severity, detail = fake.calls[0]
    assert rule and severity and detail


def test_list_filters_by_status(engine):
    client = make(engine)
    client.post(f"/exceptions/{first_exception_id(client)}/suggestion")
    assert client.get("/suggestions", params={"status": "PENDING"}).json()["total"] == 1
    assert client.get("/suggestions", params={"status": "APPROVED"}).json()["total"] == 0
    assert client.get("/suggestions", params={"status": "BOGUS"}).status_code == 422


def test_approve_records_decision_and_note(engine):
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    r = client.post(f"/suggestions/{sid}/decision", json={"decision": "approve", "note": "ok"}, headers=KEY)
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED" and r.json()["reviewer_note"] == "ok" and r.json()["decided_at"]


def test_reject(engine):
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    r = client.post(f"/suggestions/{sid}/decision", json={"decision": "reject"}, headers=KEY)
    assert r.json()["status"] == "REJECTED"


def test_cannot_decide_twice(engine):
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    client.post(f"/suggestions/{sid}/decision", json={"decision": "approve"}, headers=KEY)
    r = client.post(f"/suggestions/{sid}/decision", json={"decision": "reject"}, headers=KEY)
    assert r.status_code == 409


def test_decision_requires_valid_key(engine):
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    body = {"decision": "approve"}
    assert client.post(f"/suggestions/{sid}/decision", json=body).status_code == 401
    assert client.post(f"/suggestions/{sid}/decision", json=body, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/suggestions").json()["items"][0]["status"] == "PENDING"


def test_decision_fails_closed_when_key_not_configured(engine, monkeypatch):
    monkeypatch.delenv("REVIEWER_API_KEY")
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    r = client.post(f"/suggestions/{sid}/decision", json={"decision": "approve"}, headers=KEY)
    assert r.status_code == 503


def test_decision_input_validation(engine):
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    url = f"/suggestions/{sid}/decision"
    assert client.post(url, json={"decision": "delete"}, headers=KEY).status_code == 422
    assert client.post(url, json={"decision": "approve", "note": "x" * 300}, headers=KEY).status_code == 422
    assert client.post("/suggestions/999999/decision", json={"decision": "approve"}, headers=KEY).status_code == 404


def test_reconcile_clears_stale_suggestions(engine):
    client = make(engine)
    client.post(f"/exceptions/{first_exception_id(client)}/suggestion")
    client.post("/reconcile", params={"as_of": AS_OF.isoformat()})
    assert client.get("/suggestions").json()["total"] == 0


def test_metrics_endpoint_counts_requests_and_decisions(engine):
    client = make(engine)
    sid = client.post(f"/exceptions/{first_exception_id(client)}/suggestion").json()["id"]
    client.post(f"/suggestions/{sid}/decision", json={"decision": "approve"}, headers=KEY)
    text = client.get("/metrics").text
    assert 'suggestion_decisions_total{decision="APPROVED"}' in text
    assert 'route="/suggestions/{suggestion_id}/decision"' in text
    assert "suggestions_total" in text


def test_request_id_header_is_returned(engine):
    r = make(engine).get("/health", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
