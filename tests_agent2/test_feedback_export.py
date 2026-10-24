"""Anonymised legitimate-case export from a review store with synthetic test doubles."""
import json

import pytest

from agent2.feedback_export import export_confirmed_legitimate
from agent2.service import create_app
from tests_agent2.test_service import upload
from tests_agent2.test_service_portfolio import score_with_priority

SALT = "x" * 20


def filled_store(tmp_path):
    client = create_app(tmp_path / "db.sqlite", tmp_path / "data", {"acme-secret-co": "key-a"}, score_with_priority).test_client()
    h = {"Authorization": "Bearer key-a"}
    ingest = client.post("/ingest", data=upload("acme-secret-co"), headers=h).json["ingest_id"]
    client.post("/score?week=2025-W01", json={"ingest_id": ingest}, headers=h)
    cases = client.get("/cases", headers=h).json["cases"]
    post = lambda c, conclusion, reason: client.post(f"/cases/{c['case_id']}/decision", headers=h, json={
        "reviewer_id": "reviewer-nguyen-van-a", "conclusion": conclusion, "reason": reason, "review_minutes": 7, "worth_review": False})
    post(cases[0], "legitimate", "Hóa đơn của nhà cung cấp Công ty Hoa Sen, đã đối chiếu")
    post(cases[1], "suspected", "Nghi vấn")
    return tmp_path / "db.sqlite", [c["case_id"] for c in cases]


def test_refuses_without_approval_or_salt(tmp_path):
    db, _ = filled_store(tmp_path)
    with pytest.raises(ValueError, match="legal approval"):
        export_confirmed_legitimate(db, SALT, "")
    with pytest.raises(ValueError, match="salt"):
        export_confirmed_legitimate(db, "short", "LS-2026-001")


def test_export_keeps_only_legitimate_cases_and_leaks_no_identifiers(tmp_path):
    db, case_ids = filled_store(tmp_path)
    result = export_confirmed_legitimate(db, SALT, "LS-2026-001")
    assert result["count"] == 1 and result["records"][0]["conclusion"] == "legitimate"
    assert result["records"][0]["review_time"] == "up_to_15" and len(result["records"][0]["pseudo_company"]) == 12
    text = json.dumps(result, ensure_ascii=False)
    for secret in ("acme-secret-co", "reviewer-nguyen-van-a", "Hoa Sen", "Hóa đơn của nhà cung cấp", *case_ids):
        assert secret not in text
    again = export_confirmed_legitimate(db, SALT, "LS-2026-001")
    other = export_confirmed_legitimate(db, "y" * 20, "LS-2026-001")
    assert again["records"][0]["pseudo_company"] == result["records"][0]["pseudo_company"] != other["records"][0]["pseudo_company"]
