"""Company-scoped local review records and append-only decisions."""
from __future__ import annotations

import datetime as dt
import json
import math
import numbers
import sqlite3
import uuid
from pathlib import Path


def clean(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def encode(value):
    return json.dumps(clean(value), ensure_ascii=False, allow_nan=False)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def company_key(company):
    if not isinstance(company, str) or not company.strip():
        raise ValueError("company_id is required")
    return company


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS ingests (
                id TEXT PRIMARY KEY, company_id TEXT NOT NULL, path TEXT NOT NULL, manifest TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(company_id,id));
              CREATE TABLE IF NOT EXISTS scores (
                id TEXT PRIMARY KEY, company_id TEXT NOT NULL, ingest_id TEXT NOT NULL, week TEXT NOT NULL,
                report TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(company_id,id),
                FOREIGN KEY(company_id,ingest_id) REFERENCES ingests(company_id,id));
              CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, company_id TEXT NOT NULL, score_id TEXT NOT NULL, payload TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(company_id,id),
                FOREIGN KEY(company_id,score_id) REFERENCES scores(company_id,id));
              CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, company_id TEXT NOT NULL, case_id TEXT NOT NULL,
                reviewer_id TEXT NOT NULL, conclusion TEXT NOT NULL, reason TEXT NOT NULL,
                review_minutes REAL NOT NULL, created_at TEXT NOT NULL,
                worth_review INTEGER CHECK(worth_review IN (0,1) OR worth_review IS NULL),
                FOREIGN KEY(company_id,case_id) REFERENCES cases(company_id,id));
              CREATE TABLE IF NOT EXISTS model_versions (
                company_id TEXT NOT NULL, version TEXT NOT NULL, metadata TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(company_id,version));
              CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
                BEGIN SELECT RAISE(ABORT,'decisions are append-only'); END;
              CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
                BEGIN SELECT RAISE(ABORT,'decisions are append-only'); END;
              CREATE INDEX IF NOT EXISTS decisions_case_time ON decisions(company_id,case_id,id);
              CREATE INDEX IF NOT EXISTS cases_company ON cases(company_id);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(decisions)")}
            if "worth_review" not in columns:
                db.execute("ALTER TABLE decisions ADD COLUMN worth_review INTEGER CHECK(worth_review IN (0,1) OR worth_review IS NULL)")
            score_columns = {row[1] for row in db.execute("PRAGMA table_info(scores)")}
            if "request_key" not in score_columns:
                db.execute("ALTER TABLE scores ADD COLUMN request_key TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS scores_request_key ON scores(company_id,request_key)")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def add_ingest(self, company, path, manifest):
        company = company_key(company)
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO ingests VALUES(?,?,?,?,?)", (identifier, company, str(Path(path).resolve()), encode(manifest), now()))
        return identifier

    def get_ingest(self, company, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM ingests WHERE company_id=? AND id=?", (company_key(company), identifier)).fetchone()
        if row is None:
            raise KeyError("ingest not found")
        return dict(row)

    def add_score(self, company, ingest, week, cases, report, request_key=None):
        company = company_key(company)
        self.get_ingest(company, ingest)
        if any(c.get("company_id") != company for c in cases):
            raise ValueError("scored cases must all belong to the requested company")
        if report.get("company_id", company) != company:
            raise ValueError("score report company differs")
        identifier, at = uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute("INSERT INTO scores(id,company_id,ingest_id,week,report,created_at,request_key) VALUES(?,?,?,?,?,?,?)", (identifier, company, ingest, week, encode(report), at, request_key))
            for case in cases:
                payload = {**case, "source_case_id": case.get("case_id"), "case_id": uuid.uuid4().hex}
                db.execute("INSERT INTO cases VALUES(?,?,?,?,?)", (payload["case_id"], company, identifier, encode(payload), at))
            version = str(report.get("model_version") or report.get("model_sha256") or "untrained")
            db.execute("INSERT OR IGNORE INTO model_versions VALUES(?,?,?,?)", (company, version, encode(report.get("model_manifest", {"version": version})), at))
        return identifier

    def find_score(self, company, request_key):
        with self.connect() as db:
            row = db.execute("SELECT id,report FROM scores WHERE company_id=? AND request_key=?", (company_key(company), request_key)).fetchone()
            if row is None:
                return None
            count = db.execute("SELECT COUNT(*) FROM cases WHERE company_id=? AND score_id=?", (company, row["id"])).fetchone()[0]
        return {"score_id": row["id"], "report": json.loads(row["report"]), "cases": count}

    def list_cases(self, company, status=None):
        company = company_key(company)
        query = """SELECT * FROM (SELECT c.payload,
          COALESCE((SELECT d.conclusion FROM decisions d WHERE d.company_id=c.company_id AND d.case_id=c.id ORDER BY d.id DESC LIMIT 1),'new') AS status
          FROM cases c WHERE c.company_id=?)"""
        params = [company]
        if status is not None:
            query += " WHERE status=?"
            params.append(status)
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
        return [{**json.loads(r["payload"]), "status": r["status"]} for r in rows]

    def decide(self, company, case, reviewer, conclusion, reason, review_minutes=0, worth_review=None):
        company = company_key(company)
        if conclusion not in {"worth_review", "legitimate", "suspected", "confirmed"}:
            raise ValueError("unsupported conclusion")
        if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError("reviewer and reason are required")
        try:
            minutes = float(review_minutes)
        except (TypeError, ValueError) as exc:
            raise ValueError("review_minutes must be a number") from exc
        if not math.isfinite(minutes) or minutes < 0:
            raise ValueError("review_minutes must be finite and non-negative")
        if worth_review is not None and not isinstance(worth_review, bool):
            raise ValueError("worth_review must be true, false or null")
        with self.connect() as db:
            if db.execute("SELECT 1 FROM cases WHERE company_id=? AND id=?", (company, case)).fetchone() is None:
                raise KeyError("case not found")
            cursor = db.execute("INSERT INTO decisions(company_id,case_id,reviewer_id,conclusion,reason,review_minutes,created_at,worth_review) VALUES(?,?,?,?,?,?,?,?)",
                                (company, case, reviewer, conclusion, reason, minutes, now(), worth_review))
            return cursor.lastrowid

    def decisions(self, company):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM decisions WHERE company_id=? ORDER BY id", (company_key(company),))]

    def report(self, company):
        company = company_key(company)
        with self.connect() as db:
            counts = {table: db.execute(f"SELECT COUNT(*) FROM {table} WHERE company_id=?", (company,)).fetchone()[0]
                      for table in ("ingests", "scores", "cases", "decisions", "model_versions")}
        cases = self.list_cases(company)
        counts["cases_by_status"] = {status: sum(c["status"] == status for c in cases)
                                     for status in ("new", "worth_review", "legitimate", "suspected", "confirmed")}
        decisions = self.decisions(company)
        counts["review_minutes"] = sum(d["review_minutes"] for d in decisions)
        latest = {d["case_id"]: d for d in decisions}
        known = [d["worth_review"] for d in latest.values() if d["worth_review"] is not None]
        counts["worth_review_cases_measured"] = len(known)
        counts["worth_review_rate"] = sum(known) / len(known) if known else None
        return {"company_id": company, **counts}
