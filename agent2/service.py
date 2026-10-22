"""Local Flask ingestion, scoring and review API with company-scoped bearer keys."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import secrets
import shutil
import stat
import uuid
import zipfile
import threading
from pathlib import Path

import yaml
from flask import Flask, abort, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .adapters.csv_generic import CSVAdapter
from .inference_v4 import ReducedInput, week_bounds
from .review_store_v4 import ReviewStore, clean


def extract_csv_archive(payload, target):
    target = Path(target).resolve()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        files = archive.infolist()
        if len(files) > 1000 or sum(f.file_size for f in files) > 512 * 1024 * 1024:
            raise ValueError("archive exceeds the extraction limit")
        seen = set()
        for member in files:
            parts = member.filename.rstrip('/').split('/')
            reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(1, 10)}
            if (member.filename.startswith('/') or '\\' in member.filename or ':' in member.filename
                    or any(part in ('', '.', '..') or part.endswith((' ', '.'))
                           or part.split('.')[0].upper() in reserved for part in parts)):
                raise ValueError('archive contains an unsafe filename')
            path = (target / member.filename).resolve()
            if not path.is_relative_to(target) or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("archive contains an unsafe path")
            if member.is_dir():
                continue
            key = str(path).casefold()
            if path.suffix.lower() != ".csv" or key in seen:
                raise ValueError("archive must contain unique CSV files only")
            seen.add(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, path.open("xb") as output:
                shutil.copyfileobj(source, output)


def create_app(database, storage, company_tokens, scorer=None, scoring_version="unspecified", synthetic_demo=False,
               firm_tokens=None):
    if not company_tokens or len(set(company_tokens.values())) != len(company_tokens):
        raise ValueError("distinct company bearer keys must be configured")
    if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in company_tokens.items()):
        raise ValueError("company ids and bearer keys must be non-empty strings")
    firm_tokens = dict(firm_tokens or {})
    for firm, spec in firm_tokens.items():
        token, members = spec.get("token") if isinstance(spec, dict) else None, spec.get("companies") if isinstance(spec, dict) else None
        if not isinstance(firm, str) or not firm or not isinstance(token, str) or not token or not members:
            raise ValueError("each accounting firm needs a non-empty bearer key and company list")
        if token in company_tokens.values() or sum(s["token"] == token for s in firm_tokens.values()) > 1:
            raise ValueError("firm bearer keys must differ from every other key")
        if not set(members) <= set(company_tokens):
            raise ValueError("firm portfolio lists an unknown company")
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
    store = ReviewStore(database)
    root = Path(storage).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ui = Path(__file__).resolve().parents[1] / "review_ui"
    app.extensions["review_store"] = store
    score_lock = threading.Lock()

    @app.before_request
    def authenticate():
        if request.path in ("/", "/v4.js", "/v4.css", "/health", "/portfolio.html"):
            return None
        value = request.headers.get("Authorization", "")
        supplied = value[7:] if value.startswith("Bearer ") else ""
        if request.path == "/portfolio":
            # Read-only portfolio for an accounting firm: firm keys work here and nowhere else.
            firms = [f for f, spec in firm_tokens.items() if secrets.compare_digest(supplied, spec["token"])]
            if not firms:
                abort(401, description="accounting firm bearer key required")
            g.firm = firms[0]
            return None
        match = [company for company, token in company_tokens.items() if secrets.compare_digest(supplied, token)]
        if not match:
            abort(401, description="company bearer key required")
        g.company = match[0]
        claimed = request.args.get("company_id") or request.form.get("company_id")
        if request.is_json:
            body = request.get_json()
            if not isinstance(body, dict):
                abort(400, description="JSON body must be an object")
            claimed = body.get("company_id", claimed)
        if claimed is not None and claimed != g.company:
            abort(403, description="company scope differs from bearer key")

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(ValueError)
    @app.errorhandler(zipfile.BadZipFile)
    def invalid(error):
        if isinstance(error, ReducedInput):
            return jsonify(error=str(error), input_report=clean(error.report)), 422
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(error="record not found in this company"), 404

    @app.get("/")
    def index():
        return send_from_directory(ui, "v4.html")

    @app.get("/v4.js")
    def javascript():
        return send_from_directory(ui, "v4.js")

    @app.get("/v4.css")
    def stylesheet():
        return send_from_directory(ui, "v4.css")

    @app.get("/portfolio.html")
    def portfolio_page():
        return send_from_directory(ui, "portfolio.html")

    @app.get("/health")
    def health():
        import datetime as dt
        from zoneinfo import ZoneInfo
        day = dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        year, week, _ = day.isocalendar()
        return jsonify(status="local", current_week=f"{year}-W{week:02d}", synthetic_demo=synthetic_demo)

    @app.post("/ingest")
    def ingest():
        upload, mapping_file = request.files.get("file"), request.files.get("mapping")
        if not upload or not mapping_file:
            raise ValueError("file and mapping uploads are required")
        payload, mapping_bytes = upload.read(), mapping_file.read(1024 * 1024 + 1)
        if len(mapping_bytes) > 1024 * 1024:
            raise ValueError("mapping exceeds one megabyte")
        try:
            mapping = yaml.safe_load(mapping_bytes.decode("utf-8-sig"))
        except (yaml.YAMLError, UnicodeError) as exc:
            raise ValueError("invalid UTF-8 YAML mapping") from exc
        workspace = root / hashlib.sha256(g.company.encode()).hexdigest()[:24] / uuid.uuid4().hex
        source, normalized = workspace / "source", workspace / "normalized"
        source.mkdir(parents=True)
        try:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix == ".zip":
                try:
                    extract_csv_archive(payload, source)
                except zipfile.BadZipFile as exc:
                    raise ValueError("invalid ZIP upload") from exc
            elif suffix == ".csv":
                filename = Path(upload.filename).name
                if "/" in filename or "\\" in filename or ":" in filename:
                    raise ValueError("invalid CSV filename")
                (source / filename).write_bytes(payload)
            else:
                raise ValueError("upload must be CSV or a ZIP of CSV tables")
            adapter = CSVAdapter(mapping)
            tables = adapter.load(source)
            for name, frame in tables.items():
                if not isinstance(name, str) or not name.isidentifier():
                    raise ValueError("invalid canonical table name")
                if "company_id" in frame and not frame.company_id.astype(str).eq(g.company).all():
                    raise ValueError("uploaded tables contain another company")
            normalized.mkdir()
            for name, frame in tables.items():
                frame.to_csv(normalized / f"{name}.csv", index=False, encoding="utf-8-sig")
            manifest = {"source_sha256": hashlib.sha256(payload).hexdigest(), "mapping_sha256": hashlib.sha256(mapping_bytes).hexdigest(),
                        "input_report": adapter.last_report}
            identifier = store.add_ingest(g.company, normalized, manifest)
        except Exception:
            checked = workspace.resolve()
            if checked.is_relative_to(root) and checked != root:
                shutil.rmtree(checked)
            raise
        return jsonify(ingest_id=identifier, input_report=clean(adapter.last_report)), 201

    @app.post("/score")
    def score():
        if scorer is None:
            abort(503, description="no verified scoring configuration is loaded")
        body = request.get_json() or {}
        week = request.args.get("week") or body.get("week", "")
        week_bounds(week)
        ingest = store.get_ingest(g.company, body.get("ingest_id", ""))
        key = hashlib.sha256(f"{ingest['id']}:{week}:{scoring_version}".encode()).hexdigest()
        with score_lock:
            existing = store.find_score(g.company, key)
            if existing is not None:
                return jsonify(**clean(existing), cached=True)
            target = root / "runs" / uuid.uuid4().hex
            report, cases = scorer(Path(ingest["path"]), target, g.company, week)
            if hasattr(cases, "to_dict"):
                cases = cases.to_dict("records")
            identifier = store.add_score(g.company, ingest["id"], week, cases, report, key)
        return jsonify(score_id=identifier, cases=len(cases), report=clean(report)), 201

    @app.get("/cases")
    def cases():
        return jsonify(cases=store.list_cases(g.company, request.args.get("status")))

    @app.post("/cases/<identifier>/decision")
    def decision(identifier):
        body = request.get_json() or {}
        identifier = store.decide(g.company, identifier, body.get("reviewer_id"), body.get("conclusion"),
                                  body.get("reason"), body.get("review_minutes", 0), body.get("worth_review"))
        return jsonify(decision_id=identifier), 201

    @app.get("/report")
    def report():
        return jsonify(clean(store.report(g.company)))

    @app.get("/portfolio")
    def portfolio():
        """Per-client summary for the firm's reviewer: open work, priority and measured review quality."""
        rows = []
        for company in firm_tokens[g.firm]["companies"]:
            summary = store.report(company)
            open_cases = store.list_cases(company, "new")
            rows.append({"company_id": company, "open_cases": len(open_cases),
                         "open_highest_priority": sum(c.get("priority") == "cao_nhat" for c in open_cases),
                         "decisions": summary["decisions"], "review_minutes": summary["review_minutes"],
                         "worth_review_rate": summary["worth_review_rate"],
                         "cases_by_status": summary["cases_by_status"]})
        rows.sort(key=lambda r: (-r["open_highest_priority"], -r["open_cases"], r["company_id"]))
        return jsonify(firm=g.firm, companies=clean(rows),
                       note="Tổng hợp hàng đợi rà soát; không phải kết luận về gian lận hay về cá nhân.")

    @app.get("/decisions")
    def decisions():
        return jsonify(decisions=store.decisions(g.company))

    return app


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=Path("work/service/review.sqlite"))
    p.add_argument("--storage", type=Path, default=Path("work/service/data"))
    p.add_argument("--tenants", type=Path, required=True, help="local JSON company_id -> bearer key; keep outside Git")
    p.add_argument("--firms", type=Path, help="local JSON firm_id -> {token, companies}; keep outside Git")
    p.add_argument("--config", type=Path)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    a = p.parse_args()
    scorer = None
    if a.config:
        from .pipeline_v4 import OperationalV4Detector
        OperationalV4Detector(a.config)
        def scorer(data, out, company, week):
            from .pipeline_v4 import run
            return run(data, out, a.config, week=week, company_id=company)
    config = json.loads(a.config.read_text(encoding="utf-8")) if a.config else {}
    version = hashlib.sha256(a.config.read_bytes()).hexdigest() if a.config else "unconfigured"
    app = create_app(a.db, a.storage, json.loads(a.tenants.read_text(encoding="utf-8")), scorer,
                     scoring_version=version, synthetic_demo=bool(config.get("qa_fixture_only")),
                     firm_tokens=json.loads(a.firms.read_text(encoding="utf-8")) if a.firms else None)
    app.run(host=a.host, port=a.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
