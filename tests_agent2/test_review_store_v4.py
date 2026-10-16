import sqlite3

import pytest

from agent2.review_store_v4 import ReviewStore, clean


def populate(tmp_path):
    store = ReviewStore(tmp_path / "review.sqlite")
    for company in ("a", "b"):
        ingest = store.add_ingest(company, tmp_path / company, {})
        store.add_score(company, ingest, "2025-W01", [{"company_id": company, "case_id": "same-local-id", "reason": "test"}], {})
    return store


def test_all_reads_and_decisions_are_company_scoped(tmp_path):
    store = populate(tmp_path)
    a, b = store.list_cases("a")[0], store.list_cases("b")[0]
    assert a["case_id"] != b["case_id"]
    with pytest.raises(KeyError):
        store.decide("a", b["case_id"], "reviewer", "legitimate", "checked")
    store.decide("a", a["case_id"], "reviewer", "worth_review", "checked", 2)
    store.decide("a", a["case_id"], "reviewer", "legitimate", "more evidence", 3)
    assert len(store.decisions("a")) == 2
    assert store.decisions("b") == []
    assert store.list_cases("a", "new") == []
    assert store.list_cases("b", "new")[0]["company_id"] == "b"
    assert store.report("a")["review_minutes"] == 5
    assert store.report("a")["worth_review_rate"] is None
    store.decide("a", a["case_id"], "reviewer", "legitimate", "worth checking despite legitimate", worth_review=True)
    assert store.report("a")["worth_review_rate"] == 1
    assert store.report("a")["worth_review_cases_measured"] == 1


def test_decision_records_cannot_be_updated_or_deleted(tmp_path):
    store = populate(tmp_path)
    store.decide("a", store.list_cases("a")[0]["case_id"], "r", "suspected", "needs review")
    for query in ("UPDATE decisions SET reason='changed'", "DELETE FROM decisions"):
        with store.connect() as db, pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(query)


def test_cross_company_score_payload_rejected_without_partial_write(tmp_path):
    store = populate(tmp_path)
    ingest = store.add_ingest("a", tmp_path, {})
    with pytest.raises(ValueError, match="requested company"):
        store.add_score("a", ingest, "2025-W01", [{"company_id": "b"}], {})
    assert store.report("a")["scores"] == 1
    with pytest.raises(ValueError, match="company_id"):
        store.report("")


def test_non_finite_metrics_are_explicitly_missing_in_json():
    assert clean({"ap": float("nan"), "n": 2}) == {"ap": None, "n": 2}
