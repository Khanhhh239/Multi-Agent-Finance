from copy import deepcopy

import pytest

from agent2.schema import validate_input


def tables():
    return {"transactions": [{"company_id": "a", "transaction_id": "t", "posted_at": "2025-01-01T12:00:00+07:00",
                              "created_at": "2025-01-01T10:00:00+07:00", "approved_at": "2025-01-01T11:00:00+07:00",
                              "txn_type": "payroll", "amount_vnd": "1000000", "employee_id": "e"}],
            "employees": [{"company_id": "a", "employee_id": "e"}]}


def test_minimal_valid_input_reports_reduced_mode_without_mutating():
    t = tables()
    before = deepcopy(t)
    report = validate_input(t)
    assert report["status"] == "reduced"
    assert report["errors"] == []
    assert "payroll_after_leave" in report["disabled_capabilities"]
    assert t == before


@pytest.mark.parametrize("change,code", [({"amount_vnd": "NaN"}, "invalid_amount"),
                                       ({"amount_vnd": "1.5"}, "invalid_amount"),
                                       ({"created_at": "2025-01-02"}, "invalid_chronology"),
                                       ({"posted_at": "not a date"}, "invalid_datetime"),
                                       ({"employee_id": "missing"}, "invalid_foreign_key"),
                                       ({"is_fraud": 1}, "truth_in_input")])
def test_corrupt_input_stops(change, code):
    t = tables()
    t["transactions"][0].update(change)
    report = validate_input(t)
    assert report["status"] == "error"
    assert code in [e["code"] for e in report["errors"]]


def test_foreign_key_cannot_point_into_another_company():
    t = tables()
    t["employees"][0]["company_id"] = "b"
    assert validate_input(t)["errors"][0]["code"] == "invalid_foreign_key"


def test_missing_required_column_and_duplicate_key():
    t = tables()
    del t["transactions"][0]["txn_type"]
    t["transactions"].append(dict(t["transactions"][0]))
    codes = {e["code"] for e in validate_input(t)["errors"]}
    assert {"missing_columns", "duplicate_key"} <= codes
