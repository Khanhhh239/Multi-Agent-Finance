"""Pilot KPI script on a review store filled with synthetic test doubles."""
import importlib.util
from pathlib import Path

from agent2.service import create_app
from tests_agent2.test_service import upload
from tests_agent2.test_service_portfolio import score_with_priority

spec = importlib.util.spec_from_file_location("pilot_kpis", Path(__file__).resolve().parents[1] / "scripts" / "pilot_kpis.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_kpis_from_store(tmp_path):
    client = create_app(tmp_path / "db.sqlite", tmp_path / "data", {"a": "key-a"}, score_with_priority).test_client()
    h = {"Authorization": "Bearer key-a"}
    ingest = client.post("/ingest", data=upload("a"), headers=h).json["ingest_id"]
    client.post("/score?week=2025-W01", json={"ingest_id": ingest}, headers=h)
    cases = client.get("/cases", headers=h).json["cases"]
    first, second = cases[0]["case_id"], cases[1]["case_id"]
    client.post(f"/cases/{first}/decision", headers=h, json={"reviewer_id": "r", "conclusion": "legitimate", "reason": "ok",
                                                              "review_minutes": 5, "worth_review": False})
    client.post(f"/cases/{first}/decision", headers=h, json={"reviewer_id": "r", "conclusion": "suspected", "reason": "re",
                                                              "review_minutes": 3, "worth_review": True})
    client.post(f"/cases/{second}/decision", headers=h, json={"reviewer_id": "r", "conclusion": "legitimate", "reason": "ok",
                                                               "review_minutes": 2, "worth_review": False})
    k = pilot.kpis(tmp_path / "db.sqlite")
    assert k["cases"] == 2 and k["company_weeks"] == 1 and k["K1_cases_per_company_week"] == 2
    assert k["K2_worth_review_rate"] == .5                     # latest decision per case counts
    assert k["K3_suspected_or_confirmed"] == 1
    assert k["K5_review_minutes_per_company_week"] == 10
    assert set(k["by_priority"]) == {"cao_nhat", "trung_binh"}
