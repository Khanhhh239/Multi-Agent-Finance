import io
import zipfile

import yaml

from agent2.service import create_app


def upload(company="a", unsafe=False):
    mapping = {"tables": {"transactions": {"file": "book.csv", "columns": {n: n for n in
               ("company_id", "transaction_id", "posted_at", "created_at", "approved_at", "txn_type", "amount_vnd")}}}}
    csv = "company_id,transaction_id,posted_at,created_at,approved_at,txn_type,amount_vnd\n" + f"{company},t,2025-01-01T12:00:00+07:00,2025-01-01T10:00:00+07:00,2025-01-01T11:00:00+07:00,cash_expense,100\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escaped.csv" if unsafe else "book.csv", csv)
    stream.seek(0)
    return {"file": (stream, "book.zip"), "mapping": (io.BytesIO(yaml.safe_dump(mapping).encode()), "mapping.yaml")}


def fake_score(data, out, company, week):
    return {"company_id": company, "model_version": "synthetic_test_double"}, [{"company_id": company, "case_id": "local", "reason": "test"}]


def test_ingest_score_review_and_reports_are_isolated(tmp_path):
    app = create_app(tmp_path / "db.sqlite", tmp_path / "data", {"a": "key-a", "b": "key-b"}, fake_score)
    client = app.test_client()
    a, b = {"Authorization": "Bearer key-a"}, {"Authorization": "Bearer key-b"}
    assert client.get("/cases").status_code == 401
    assert client.get("/cases?company_id=b", headers=a).status_code == 403
    response = client.post("/ingest", data=upload(), headers=a)
    assert response.status_code == 201
    identifier = response.json["ingest_id"]
    assert client.post("/score?week=2025-W01", json={"ingest_id": identifier}, headers=b).status_code == 404
    scored = client.post("/score?week=2025-W01", json={"ingest_id": identifier}, headers=a)
    assert scored.status_code == 201
    repeat = client.post("/score?week=2025-W01", json={"ingest_id": identifier}, headers=a)
    assert repeat.status_code == 200 and repeat.json["cached"]
    assert repeat.json["score_id"] == scored.json["score_id"]
    case = client.get("/cases?status=new", headers=a).json["cases"][0]
    body = {"reviewer_id": "reviewer", "conclusion": "worth_review", "reason": "checked", "review_minutes": 2}
    assert client.post(f"/cases/{case['case_id']}/decision", json=body, headers=b).status_code == 404
    assert client.post(f"/cases/{case['case_id']}/decision", json=body, headers=a).status_code == 201
    assert client.get("/cases?status=new", headers=a).json["cases"] == []
    assert client.get("/cases", headers=b).json["cases"] == []
    assert client.get("/report", headers=a).json["decisions"] == 1
    assert client.get("/decisions", headers=b).json["decisions"] == []


def test_upload_scope_and_archive_paths_are_checked(tmp_path):
    client = create_app(tmp_path / "db", tmp_path / "data", {"a": "key"}).test_client()
    auth = {"Authorization": "Bearer key"}
    assert client.post("/ingest", data=upload("b"), headers=auth).status_code == 400
    assert client.post("/ingest", data=upload(unsafe=True), headers=auth).status_code == 400
    assert not list(tmp_path.rglob("escaped.csv"))
    assert client.post("/score", json={}, headers=auth).status_code == 503
    assert client.get("/health").status_code == 200
