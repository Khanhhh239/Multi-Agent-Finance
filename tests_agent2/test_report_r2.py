"""R2 report: registration section 7 outcome when the supervised gate fails (synthetic summaries)."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("report_r2", Path(__file__).resolve().parents[1] / "scripts" / "report_r2.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)

CANDIDATE = {"J": .41, "Q_min": .38, "Q_mean": .5, "R_mean": .61, "R_min": .47, "B_mean": .39, "eligible": True}


def setup(tmp_path, monkeypatch, passed):
    r2 = tmp_path / "R2"
    r2.mkdir()
    checks = {"R_mean": {"value": .61, "minimum": .65, "passed": passed}, "hard_negative_limit": {"passed": True}}
    (r2 / "selection_summary.json").write_text(json.dumps({"chosen": "L3-PU", "candidates": {"L3-PU": CANDIDATE},
        "gate": {"passed": passed, "checks": checks, "decision": "continue" if passed else "stop_without_generating_sealed_worlds"}}),
        encoding="utf-8")
    monkeypatch.setattr(report, "R2", r2)
    monkeypatch.setattr(report, "OUT", tmp_path / "10.md")
    monkeypatch.setattr(report, "OUTCOME", tmp_path / "09.md")


def test_failed_gate_writes_outcome_with_pivot_and_lf(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, passed=False)
    report.main()
    text = (tmp_path / "09.md").read_bytes()
    assert b"\r" not in text and b"\r" not in (tmp_path / "10.md").read_bytes()
    body = text.decode("utf-8")
    assert "KHÔNG ĐẠT" in body and "không sinh và không chấm" in body and report.PIVOT in body
    assert "| R_mean | 61,0 | 65,0 | Không |" in body


def test_passed_gate_writes_no_outcome(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, passed=True)
    report.main()
    assert (tmp_path / "10.md").exists() and not (tmp_path / "09.md").exists()


def test_no_eligible_candidate_is_a_failed_gate():
    md = report.outcome({"chosen": None, "gate": {"passed": False, "decision": "stop_without_generating_sealed_worlds"}}, None)
    assert any("Không còn ứng viên hợp lệ" in line for line in md)
