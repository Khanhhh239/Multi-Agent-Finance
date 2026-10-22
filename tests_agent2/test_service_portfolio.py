"""Accounting-firm portfolio view: read-only, scoped to the firm's own clients (synthetic test doubles)."""
import pytest

from agent2.service import create_app
from tests_agent2.test_service import upload


def score_with_priority(data, out, company, week):
    cases = [{"company_id": company, "case_id": f"{company}-1", "priority": "cao_nhat", "reason": "test"},
             {"company_id": company, "case_id": f"{company}-2", "priority": "trung_binh", "reason": "test"}]
    return {"company_id": company, "model_version": "synthetic_test_double"}, cases


def make(tmp_path):
    companies = {"a": "key-a", "b": "key-b", "c": "key-c"}
    firms = {"dvkt1": {"token": "firm-key", "companies": ["a", "b"]}}
    return create_app(tmp_path / "db.sqlite", tmp_path / "data", companies, score_with_priority, firm_tokens=firms).test_client()


def test_portfolio_lists_only_firm_clients_and_ranks_by_priority(tmp_path):
    client = make(tmp_path)
    for company in ("a", "b", "c"):
        h = {"Authorization": f"Bearer key-{company}"}
        ingest = client.post("/ingest", data=upload(company), headers=h).json["ingest_id"]
        assert client.post("/score?week=2025-W01", json={"ingest_id": ingest}, headers=h).status_code == 201
    a = {"Authorization": "Bearer key-a"}
    case = next(c for c in client.get("/cases", headers=a).json["cases"] if c["priority"] == "cao_nhat")
    client.post(f"/cases/{case['case_id']}/decision", headers=a,
                json={"reviewer_id": "r", "conclusion": "legitimate", "reason": "ok", "review_minutes": 4, "worth_review": False})
    body = client.get("/portfolio", headers={"Authorization": "Bearer firm-key"}).json
    assert [r["company_id"] for r in body["companies"]] == ["b", "a"]          # b still has a highest-priority case
    assert body["companies"][1]["review_minutes"] == 4 and body["companies"][1]["open_cases"] == 1
    assert "c" not in {r["company_id"] for r in body["companies"]}


def test_firm_key_cannot_touch_company_endpoints_and_company_key_cannot_read_portfolio(tmp_path):
    client = make(tmp_path)
    firm = {"Authorization": "Bearer firm-key"}
    assert client.get("/cases", headers=firm).status_code == 401
    assert client.get("/report", headers=firm).status_code == 401
    assert client.get("/portfolio", headers={"Authorization": "Bearer key-a"}).status_code == 401


def test_invalid_firm_configuration_is_refused(tmp_path):
    with pytest.raises(ValueError):
        create_app(tmp_path / "d", tmp_path / "s", {"a": "k"}, firm_tokens={"f": {"token": "k", "companies": ["a"]}})
    with pytest.raises(ValueError):
        create_app(tmp_path / "d", tmp_path / "s", {"a": "k"}, firm_tokens={"f": {"token": "x", "companies": ["zz"]}})
