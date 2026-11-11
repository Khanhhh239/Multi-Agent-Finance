import base64
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import pickle
import re
import os
import time
import hmac
from pathlib import Path
import threading
import uuid
import zipfile
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Header, Request, Query
from fastapi.responses import Response, FileResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ConfigDict, field_validator
from agent1.adaptive.data import (
    SCHEMAS,
    IDS,
    suggested_mapping,
    parse_rows,
    validate_dataset,
    fingerprint,
    merge_import,
    account_scope,
    vnd,
    ACCOUNTING,
    MONEY_FIELDS,
)
from ..ingest.einvoice_xml import read_invoice_xml
from ..ingest.strict_files import read_csv, read_excel, source_hash
from agent1.adaptive.methods import train, forecast, CATALOG
from typing import Annotated, Any
from .company_profile import company_profile, import_formats
from .portal_connect import install_portal_connect
from .sessions import WorkspaceSessions
from .catalog import outstanding, import_counts, preview_history, record_rows, search_rows, record_detail
from .reconciliation import WorkspaceSource
from agent1.reconciliation import operations as t9_operations
from agent1.reconciliation.pipeline import today as t9_today
from agent1.reconciliation.pipeline import NON_AR


class Training(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asof: str
    payments_complete: bool = False
    try_deep_cash: bool = False


class Allocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_id: str = Field(min_length=1, max_length=160)
    bank_id: str = Field(min_length=1, max_length=160)
    invoice_id: str = Field(min_length=1, max_length=160)
    amount: int = Field(strict=True, gt=0, le=999999999999999999)
    reviewed_by: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("amount", mode="before")
    @classmethod
    def exact_vnd(cls, value):
        return vnd(value)

    @field_validator("reviewed_by", "note")
    @classmethod
    def nonblank_review(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Cần tên người xử lý và nguồn bằng chứng")
        return value


class ReconciliationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReconciliationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200)
    proposal_id: str = Field(min_length=1, max_length=160)
    bank_id: str = Field(min_length=1, max_length=160)
    reviewed_by: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=2000)


class ReconciliationReverse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200)
    decision_id: str = Field(min_length=1, max_length=160)
    reviewed_by: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)


class CorrectionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(min_length=1, max_length=30)
    identifier: str = Field(min_length=1, max_length=160)
    values: dict[str, Any]


class CorrectionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_hash: str = Field(min_length=1, max_length=100)
    changes: list[CorrectionChange] = Field(min_length=1, max_length=20)
    reviewed_by: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)


class CorrectionCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200)


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cutoff: str
    opening_balance: float = Field(allow_inf_nan=False)
    horizon_weeks: int = Field(default=13, ge=1, le=52)
    delay_days: int = Field(default=0, ge=0, le=90)
    expense_multiplier: float = Field(default=1, ge=0, le=3, allow_inf_nan=False)
    payments_complete: bool = False
    confirmed_weeks: list[Annotated[int, Field(ge=1, le=52)]] = Field(
        default_factory=list, max_length=52
    )
    cash_floor: float = Field(default=0.0, allow_inf_nan=False)
    shared_customer_risk: bool = False
    delay_customer: str | None = None
    include_operating: bool = False


def demo_training_allowed(firm):
    return os.environ.get("AGENT1_DEMO_TRAINING") == "1" and firm.startswith("DEMO_")


def display_money(row):
    """JSON numbers beyond JavaScript's exact range are displayed as decimal text."""
    if isinstance(row, list):
        return [display_money(r) for r in row]
    if not isinstance(row, dict):
        return row
    fields = MONEY_FIELDS | {"unallocated", "total_received", "unallocated_minor", "amount_minor", "amount_open_minor", "available_minor",
                             "remaining_amount", "allocated_amount", "outstanding_before", "outstanding_after"}
    return {k: str(v) if k in fields and isinstance(v, int) and abs(v) > 2**53 - 1 else display_money(v) for k, v in row.items()}


def install(app, store, authorize, firm_id, *, bank_registry=None, bank_accounts_file=None, bank_accounts_required=False):
    router = APIRouter(prefix="/v1")
    bearer_authorize = authorize
    sessions = WorkspaceSessions(firm_id)
    app.state.workspace_sessions = sessions

    def credential(authorization, request):
        return authorization if authorization else sessions.credential(request)

    def authorize(authorization: str | None = Header(None), request: Request = None):
        return bearer_authorize(credential(authorization, request))

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="company-training")
    app.state.company_executor = executor
    mutex = threading.RLock()
    running = set()
    app.state.company_mutex = mutex
    app.state.company_running = running

    @app.middleware("http")
    async def workspace_headers(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith(
            ("/workspace", "/v1/")
        ):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors " + os.environ.get("AGENT1_FRAME_ANCESTORS", "'none'") + "; base-uri 'self'; form-action 'self'"
            )
        return response

    def records(firm, kind):
        return store.get(firm, "company_" + kind)

    def put(firm, kind, rows):
        store.put(firm, "company_" + kind, rows)

    def one(firm, kind, identifier):
        return store.one(firm, "company_" + kind, identifier)

    def read_access(authorization: str | None = Header(None), request: Request = None):
        authorization = credential(authorization, request)
        for env in ("AGENT1_AGENT4_TOKEN", "AGENT1_VIEWER_TOKEN"):
            secret = os.environ.get(env)
            if secret and hmac.compare_digest(
                (authorization or "").encode(), ("Bearer " + secret).encode()
            ):
                return firm_id
        return authorize(authorization)

    def current(firm):
        with mutex:
            pointers = records(firm, "dataset_active")
            if not pointers:
                return dict(invoices=[], payments=[], outflows=[])
            return one(firm, "datasets", pointers[0]["version"])["data"]

    def check_bank_scope(data, *, allow_update=False):
        if not (data.get("bank") or data.get("statements")):
            return
        configured = bank_accounts_required or os.environ.get("AGENT1_BANK_ACCOUNTS_FILE") or (bank_accounts_file and Path(bank_accounts_file).is_file()) or data.get("bank_scope")
        if not configured:
            return
        scope = bank_registry()
        for kind in ("bank", "statements"):
            for row in data.get(kind, []):
                account = scope["accounts"].get(row["account"])
                if not account or account["currency"] != "VND":
                    raise ValueError("Tài khoản ngoài danh mục VND được duyệt: " + row["account"])
        changed = bool(data.get("bank_scope") and data["bank_scope"] != scope)
        if changed and not allow_update:
            raise ValueError("Danh mục tài khoản đã đổi; đối chiếu phạm vi trước khi nhập tiếp")
        data["bank_scope"] = scope
        return changed

    def save_dataset(firm, data):
        try:
            WorkspaceSource(store, firm, data).validate_managed()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        version = fingerprint(data)
        store.put_many(firm, {
            "company_datasets": [dict(id=version, data=data, created_at=datetime.now(timezone.utc).isoformat())],
            "company_dataset_active": [dict(id="active", version=version, counts={k: len(data.get(k, [])) for k in SCHEMAS})],
        })
        return version

    def public_run(row):
        return {
            k: v
            for k, v in row.items()
            if k not in ["artifact", "selection", "selected_method", "selected_weight"]
        }

    def date(value):
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError()
            parsed = pd.Timestamp(value)
            if pd.isna(parsed) or parsed.tzinfo is not None:
                raise ValueError()
            return str(parsed.date())
        except (ValueError, TypeError):
            raise HTTPException(422, "Ngày phải có dạng yyyy-mm-dd")

    for old_job in records(firm_id, "jobs"):
        if old_job["status"] in ["queued", "running"]:
            old_job.update(
                status="failed",
                message="Máy chủ đã khởi động lại; hãy tạo tác vụ mới. Phiên bản đang dùng được giữ nguyên.",
            )
            put(firm_id, "jobs", [old_job])
    # Split weights out of old rows once. Metadata polling never opens the weight store.
    for identifier in store.ids(firm_id, "company_models"):
        row = one(firm_id, "models", identifier)
        if "artifact" in row:
            put(firm_id, "weights", [dict(id=identifier, artifact=row.pop("artifact"))])
            row["artifact_id"] = identifier
            put(firm_id, "models", [row])
    indexed = set(store.ids(firm_id, "company_forecast_index"))
    for identifier in store.ids(firm_id, "company_predictions"):
        if identifier in indexed:
            continue
        row = one(firm_id, "predictions", identifier)
        if "cutoff" not in row:
            continue
        meta = {
            k: row.get(k)
            for k in (
                "id",
                "cutoff",
                "opening_balance",
                "dataset_hash",
                "model_version",
                "scenario",
                "minimum_balance",
            )
        }
        meta.update(created_at=row.get("created_at") or "", legacy=True)
        put(firm_id, "forecast_index", [meta])

    @router.get("/access")
    def access(request: Request, authorization: str | None = Header(None), firm=Depends(read_access)):
        try:
            authorize(authorization, request)
        except HTTPException:
            return dict(company=firm, role="reader")
        return dict(company=firm, role="accountant")

    @router.post("/session")
    def browser_session(request: Request, response: Response,
                        authorization: str | None = Header(None), firm=Depends(read_access)):
        sessions.issue(request, response, credential(authorization, request))
        return dict(company=firm, expires_in=sessions.ttl)

    @router.delete("/session")
    def end_browser_session(request: Request, response: Response):
        sessions.revoke(request, response)
        return dict(disconnected=True)

    @router.get("/workspace")
    def workspace(firm=Depends(authorize)):
        pointer = one(firm, "dataset_active", "active")
        dataset_hash = (
            pointer["version"]
            if pointer
            else fingerprint(dict(invoices=[], payments=[], outflows=[]))
        )
        counts = (pointer or {}).get("counts")
        if counts is None:
            data = current(firm)
            counts = {k: len(data.get(k, [])) for k in SCHEMAS}
        active = records(firm, "model_active")
        versions = sorted(
            records(firm, "models"), key=lambda r: r["created_at"], reverse=True
        )
        jobs = sorted(
            records(firm, "jobs"), key=lambda r: r["created_at"], reverse=True
        )
        return dict(
            company=firm,
            company_profile=company_profile(firm),
            synthetic_sandbox=demo_training_allowed(firm),
            counts=counts,
            dataset_hash=dataset_hash,
            active_version=active[0]["version"] if active else None,
            versions=[public_run(v) for v in versions],
            jobs=jobs[:10],
            method_count=len(CATALOG),
            needs_retraining=bool(
                active
                and next(
                    (v for v in versions if v["id"] == active[0]["version"]), {}
                ).get("dataset_hash")
                != dataset_hash
            ),
        )

    @router.get("/templates/{kind}")
    def template(kind: str, date_format: str | None = None, number_format: str | None = None, firm=Depends(authorize)):
        if kind not in SCHEMAS:
            raise HTTPException(404, "Không có mẫu")
        date_format, number_format = import_formats(company_profile(firm), date_format, number_format)
        examples = {
            "invoice_events": dict(event_id="CANCEL01", invoice_id="DEMO_HD001", event_type="cancel", event_date="01/02/2026", known_at="01/02/2026"),
            "actions": dict(
                event_id="EVENT01",
                invoice_id="DEMO_HD001",
                date="01/02/2026",
                kind="promise",
                promise_date="15/02/2026",
                known_at="01/02/2026",
            ),
            "bank": dict(
                bank_id="TEST_TX01",
                account="TK01",
                date="01/01/2026",
                direction="thu",
                amount="100000",
                known_at="01/01/2026",
            ),
            "statements": dict(
                statement_id="TEST_KY01",
                account="TK01",
                start_date="01/01/2026",
                end_date="31/01/2026",
                opening_balance="0",
                closing_balance="100000",
                known_at="31/01/2026",
            ),
            "invoices": dict(
                invoice_id="DEMO_HD001",
                customer_id="DEMO_KH001",
                issue_date="01/01/2026",
                due_date="31/01/2026",
                amount="15000000",
                known_at="01/01/2026",
                currency="VND",
            ),
            "payments": dict(
                payment_id="DEMO_TT001",
                invoice_id="DEMO_HD001",
                payment_date="30/01/2026",
                amount="15000000",
                known_at="30/01/2026",
            ),
            "outflows": dict(
                expense_id="DEMO_CHI001",
                date="30/11/2026",
                amount="20000000",
                category="Lương",
                known_at="01/11/2026",
            ),
            "expense_payments": dict(
                settlement_id="DEMO_TRA001", expense_id="DEMO_CHI001",
                bank_id="DEMO_BANK_CHI001", payment_date="30/11/2026",
                amount="20000000", known_at="30/11/2026",
            ),
        }
        example = examples[kind]
        for field, value in example.items():
            if field.endswith("date") or field in ("date", "known_at", "refund_approved_at"):
                example[field] = datetime.strptime(value, "%d/%m/%Y").strftime(date_format)
            elif field in ("amount", "opening_balance", "closing_balance") and number_format == "vi-VN":
                example[field] = f"{int(value):,}".replace(",", ".") + ",00"
        csv = (
            pd.DataFrame([example], columns=list(SCHEMAS[kind]))
            .to_csv(index=False)
            .encode("utf-8-sig")
        )
        return Response(
            csv,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="agent1-{kind}.csv"'
            },
        )

    @router.post("/imports/preview")
    async def preview(
        file: UploadFile = File(...),
        kind: str = Form(...),
        mapping: str = Form("{}"),
        date_format: str | None = Form(None),
        number_format: str | None = Form(None),
        sheet: str = Form(""),
        known_at: str | None = Form(None),
        imported_by: str = Form("", max_length=200),
        firm=Depends(authorize),
    ):
        if kind not in SCHEMAS:
            raise HTTPException(422, "Loại bảng không hợp lệ")
        profile = company_profile(firm)
        date_format, number_format = import_formats(profile, date_format, number_format)
        content = await file.read(5_000_001)
        if len(content) > 5_000_000:
            raise HTTPException(413, "Tối đa 5 MB mỗi file")
        try:
            suffix = Path(file.filename or "").suffix.lower()
            sheets = []
            if suffix == ".xlsx":
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    if sum(f.file_size for f in z.infolist()) > 30_000_000:
                        raise ValueError("Workbook vượt giới hạn giải nén 30 MB")
                with pd.ExcelFile(io.BytesIO(content)) as workbook:
                    sheets = workbook.sheet_names
                raw = read_excel(content, file.filename, sheet_name=sheet or sheets[0])
            elif suffix == ".csv":
                header = content.decode("utf-8-sig").splitlines()[0] if content else ""
                try:
                    delimiter = csv.Sniffer().sniff(header, delimiters=",;\t").delimiter
                except csv.Error:
                    delimiter = ","
                raw = read_csv(content, file.filename, delimiter=delimiter)
            elif suffix == ".xml" and kind == "invoices":
                row = read_invoice_xml(content, firm, validate=False)
                received = date(known_at) if known_at else str(pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date())
                row.update(amount=row.pop("amount_gross"), known_at=received)
                raw = pd.DataFrame([row])
            else:
                raise ValueError("Chọn CSV UTF-8, XLSX hoặc XML hóa đơn")
            if len(raw) > 50000:
                raise ValueError("Tối đa 50.000 dòng mỗi lần nạp")
            selected = json.loads(mapping)
            if not isinstance(selected, dict):
                raise ValueError("Ánh xạ phải là đối tượng")
            schema_id = fingerprint([kind, list(raw.columns)])
            saved = one(firm, "mappings", schema_id)
            selected = suggested_mapping(raw.columns, kind) if suffix == ".xml" else selected or (
                saved["mapping"] if saved else suggested_mapping(raw.columns, kind)
            )
            accepted, errors, warnings = parse_rows(
                raw, kind, selected,
                "%Y-%m-%d" if suffix == ".xml" else date_format,
                "plain" if suffix == ".xml" else number_format,
                source="xml" if suffix == ".xml" else "erp",
            )
            for i, row in enumerate(accepted, 2):
                if kind == "invoices" and ACCOUNTING <= row.keys():
                    row.update(source_file=file.filename, source_row=i, source_sha256=source_hash(content))
                    row["source_lineage"][row["source"]] = dict(file=file.filename, row=i, sha256=source_hash(content))
            # current() waits for the dataset lock: never block the event loop on it (health checks and every other request stall).
            staged = await run_in_threadpool(current, firm)
            base_hash = fingerprint(staged)
            merged = {r[IDS[kind]]: r for r in staged.get(kind, [])}
            changes = [
                dict(before=merged[r[IDS[kind]]], after=r)
                for r in accepted
                if r[IDS[kind]] in merged and merged[r[IDS[kind]]] != r
            ][:10]
            updates = sum(r[IDS[kind]] in merged for r in accepted)
            if not errors:
                try:
                    staged = merge_import(staged, kind, accepted)
                    WorkspaceSource(store, firm, staged).validate_managed()
                    if check_bank_scope(staged, allow_update=kind in ("bank", "statements")):
                        warnings.append("Danh mục tài khoản đã đổi. Phạm vi sau khi lưu: " + ", ".join(sorted(staged["bank_scope"]["accounts"])))
                    if kind in ("bank", "statements") and not staged.get("bank_scope"):
                        warnings.append("Chưa có danh mục tài khoản ngân hàng được duyệt; chưa xác nhận phạm vi tài khoản đầy đủ.")
                    changes = [dict(before=merged[r[IDS[kind]]], after=r) for r in staged[kind]
                               if r[IDS[kind]] in merged and merged[r[IDS[kind]]] != r][:10]
                    updates = sum(r[IDS[kind]] in merged and merged[r[IDS[kind]]] != r for r in staged[kind])
                except ValueError as exc:
                    errors.append(dict(row=0, column="reference", message=str(exc)))
            for e in errors:
                col = selected.get(e["column"])
                i = e["row"] - 2
                e["original"] = (
                    str(raw.iloc[i][col])
                    if col in raw.columns and 0 <= i < len(raw)
                    else ""
                )
                e["suggestion"] = (
                    "Ghép cột trong bước xem trước."
                    if e["row"] == 1
                    else "Đối chiếu mã và số tiền với bảng đã nạp."
                    if e["row"] == 0
                    else "Đối chiếu với file mẫu, sửa ô trong file nguồn và xem trước lại."
                )
            identifier = uuid.uuid4().hex
            put(
                firm,
                "previews",
                [
                    dict(
                        id=identifier,
                        kind=kind,
                        records=accepted,
                        source_file=Path(file.filename or "Không rõ tên tệp").name,
                        source_sha256=source_hash(content),
                        imported_by=imported_by.strip(),
                        row_count=len(raw),
                        valid_rows=len(accepted),
                        error_count=len(errors),
                        bank_scope=staged.get("bank_scope"),
                        base_hash=base_hash,
                        valid=not errors,
                        errors=errors,
                        schema_id=schema_id,
                        mapping=selected,
                        company_profile=profile if profile["managed"] else None,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                ],
            )
            return dict(
                id=identifier,
                columns=list(raw.columns),
                sheets=sheets if suffix == ".xlsx" else [],
                changes=[dict(before=display_money(r["before"]), after=display_money(r["after"])) for r in changes],
                fields=list(SCHEMAS[kind]),
                mapping=selected,
                mapping_locked=suffix == ".xml",
                rows=len(raw),
                valid_rows=len(accepted),
                updates=updates,
                errors=errors[:100],
                error_count=len(errors),
                warnings=warnings,
                sample=[display_money(r) for r in accepted[:5]],
                can_commit=not errors and bool(accepted),
            )
        except (ValueError, TypeError, UnicodeError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, str(exc))

    @router.post("/imports/{identifier}/commit")
    def commit(identifier: str, firm=Depends(authorize)):
        with mutex:
            p = one(firm, "previews", identifier)
            if not p or not p["valid"] or not p["records"]:
                raise HTTPException(422, "Bản xem trước còn lỗi hoặc không tồn tại")
            if p.get("committed_result"):
                return dict(p["committed_result"], replayed=True)
            profile = company_profile(firm)
            if (profile["managed"] or p.get("company_profile")) and p.get("company_profile") != profile:
                raise HTTPException(409, "Cấu hình doanh nghiệp đã đổi. Kiểm tra file lại trước khi ghi.")
            data = current(firm)
            before = data
            if p["base_hash"] != fingerprint(data):
                raise HTTPException(
                    409, "Dữ liệu đã đổi. Xem trước lại để tránh ghi đè."
                )
            try:
                data = merge_import(data, p["kind"], p["records"])
                WorkspaceSource(store, firm, data).validate_managed()
                check_bank_scope(data, allow_update=p["kind"] in ("bank", "statements"))
                if data.get("bank_scope") != p.get("bank_scope"):
                    raise ValueError("Danh mục tài khoản đã đổi từ lần xem trước; kiểm tra file lại")
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            version = fingerprint(data)
            counts = import_counts(before, data, p["kind"], len(p["records"]))
            old_rows = {r[IDS[p["kind"]]]: r for r in before.get(p["kind"], [])}
            incoming_ids = {x[IDS[p["kind"]]] for x in p["records"]}
            batch = dict(id=identifier, kind=p["kind"], source_file=p.get("source_file", "Không rõ tên tệp"),
                         source_sha256=p.get("source_sha256"), imported_by=p.get("imported_by", ""),
                         created_at=datetime.now(timezone.utc).isoformat(), status="committed",
                         rows=p.get("row_count", len(p["records"])), valid_rows=len(p["records"]), error_count=0,
                         **counts, before_version=p["base_hash"], version=version,
                         outstanding_before=outstanding(WorkspaceSource(store, firm, before)),
                         outstanding_after=outstanding(WorkspaceSource(store, firm, data)),
                         record_ids=[r[IDS[p["kind"]]] for r in data.get(p["kind"], [])
                                     if old_rows.get(r[IDS[p["kind"]]]) != r or r[IDS[p["kind"]]] in incoming_ids])
            result = dict(version=version, accepted=len(p["records"]), updated=True, **counts)
            batches = {
                "company_datasets": [dict(id=version, data=data, created_at=batch["created_at"])],
                "company_dataset_active": [dict(id="active", version=version, counts={k: len(data.get(k, [])) for k in SCHEMAS})],
                "company_imports": [batch],
                "company_previews": [dict(p, committed_result=result)],
            }
            if "schema_id" in p:
                batches["company_mappings"] = [dict(id=p["schema_id"], mapping=p["mapping"])]
            store.put_many(firm, batches)
            return result

    @router.get("/records")
    def browse_records(kind: str, q: str = Query("", max_length=200), status: str = "",
                       date_from: str = "", date_to: str = "", offset: int = Query(0, ge=0),
                       limit: int = Query(25, ge=1, le=100), firm=Depends(authorize)):
        if kind not in SCHEMAS:
            raise HTTPException(422, "Loại bảng không hợp lệ")
        if date_from:
            date_from = date(date_from)
        if date_to:
            date_to = date(date_to)
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "Ngày bắt đầu phải trước ngày kết thúc")
        with mutex:
            rows = record_rows(WorkspaceSource(store, firm, current(firm)), kind)
            selected = search_rows(rows, q, status, date_from, date_to, kind)
            return display_money(dict(kind=kind, total=len(selected), offset=offset, limit=limit,
                                      statuses=sorted({r["status"] for r in rows}), rows=selected[offset:offset + limit]))

    @router.get("/records/{kind}/{identifier:path}")
    def browse_record(kind: str, identifier: str, firm=Depends(authorize)):
        if kind not in SCHEMAS:
            raise HTTPException(404, "Không có bảng này")
        with mutex:
            try:
                return display_money(record_detail(WorkspaceSource(store, firm, current(firm)), kind, identifier,
                                                   records(firm, "imports")))
            except KeyError:
                raise HTTPException(404, "Không tìm thấy bản ghi của doanh nghiệp")

    @router.get("/imports")
    def import_history(kind: str = "", offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                       firm=Depends(authorize)):
        if kind and kind not in SCHEMAS:
            raise HTTPException(422, "Loại bảng không hợp lệ")
        with mutex:
            batches = {r["id"]: r for r in records(firm, "imports")}
            history = list(batches.values())
            for p in records(firm, "previews"):
                if p["id"] not in batches:
                    history.append(preview_history(p))
            history = sorted((r for r in history if not kind or r["kind"] == kind),
                             key=lambda r: (r["created_at"], r["id"]), reverse=True)
            return display_money(dict(total=len(history), offset=offset, limit=limit,
                                      legacy_count=sum(bool(r.get("legacy")) for r in history),
                                      rows=[{k: v for k, v in r.items() if k != "record_ids"}
                                            for r in history[offset:offset + limit]]))

    @router.get("/imports/{identifier}")
    def import_detail(identifier: str, firm=Depends(authorize)):
        batch = one(firm, "imports", identifier)
        preview = one(firm, "previews", identifier)
        if not batch and not preview:
            raise HTTPException(404, "Không tìm thấy lần nạp")
        return display_money(dict(batch={k: v for k, v in (batch or preview_history(preview)).items() if k != "record_ids"},
                                  errors=(preview or {}).get("errors", [])[:100],
                                  records=[dict(kind=(batch or preview)["kind"], identifier=r)
                                           for r in (batch or {}).get("record_ids", [])[:100]],
                                  record_count=len((batch or {}).get("record_ids", []))))

    @router.delete("/records/{kind}/{identifier:path}")
    def remove(kind: str, identifier: str, firm=Depends(authorize)):
        if kind not in SCHEMAS:
            raise HTTPException(404, "Không có bảng này")
        with mutex:
            data = current(firm)
            if kind == "invoice_events" or (kind == "invoices" and any(r["invoice_id"] == identifier and ACCOUNTING <= r.keys() for r in data.get(kind, []))):
                raise HTTPException(409, "Giữ lịch sử chứng từ kế toán: nhập sự kiện hủy hoặc phiên bản sửa thay vì xóa")
            before = len(data.setdefault(kind, []))
            history = data.setdefault("record_history", {}).setdefault(kind, list(data[kind]))
            data[kind] = [r for r in data[kind] if r[IDS[kind]] != identifier]
            if before == len(data[kind]):
                raise HTTPException(404, "Không tìm thấy mã")
            try:
                validate_dataset(data)
            except ValueError as exc:
                raise HTTPException(409, "Xóa thanh toán liên quan trước. " + str(exc))
            removed = next(r for r in reversed(history) if r[IDS[kind]] == identifier)
            history.append({IDS[kind]: identifier, "known_at": max(removed["known_at"], str(pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date())), "_deleted": True})
            version = save_dataset(firm, data)
            return dict(deleted=True, version=version)

    @router.post("/training", status_code=202)
    def training(body: Training, firm=Depends(authorize)):
        asof = date(body.asof)
        if not body.payments_complete:
            raise HTTPException(
                422,
                "Xác nhận đã nạp đầy đủ thanh toán đến ngày chốt; không suy missing = unpaid",
            )
        identifier = uuid.uuid4().hex
        created = datetime.now(timezone.utc).isoformat()
        with mutex:
            if running:
                raise HTTPException(
                    409, "Đang có một tác vụ huấn luyện. Chờ tác vụ hoàn tất."
                )
            data = current(firm)
            try:
                check_bank_scope(data)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            if any(
                str(r["invoice_id"]).startswith("DEMO_") for r in data["invoices"]
            ) and not demo_training_allowed(firm):
                raise HTTPException(
                    422,
                    "Xóa/thay dòng mẫu DEMO trước khi huấn luyện; dữ liệu mẫu chỉ thử luồng",
                )
            if len(data["invoices"]) > 50000:
                raise HTTPException(
                    422,
                    "Giới hạn 50.000 hóa đơn cho mỗi worker local",
                )
            # Automatically include eligible cash learners; the UI need not name algorithms.
            from agent1.adaptive.operating import available_history

            accounts = account_scope(data, asof)
            cash_history, _ = (
                available_history(data, asof, accounts) if accounts else ([], 0)
            )
            deep_cash = body.try_deep_cash or len(cash_history) >= 156
            if len(data["invoices"]) >= 10000 or deep_cash:
                import psutil

                if psutil.virtual_memory().available < 3 * 1024**3:
                    raise HTTPException(
                        409,
                        "Cần ít nhất 3 GiB RAM trống cho tác vụ lớn hoặc DL dòng tiền.",
                    )
            running.add(firm)
        job = dict(
            id=identifier,
            status="queued",
            message="Đang xếp hàng",
            created_at=created,
            dataset_hash=fingerprint(data),
        )
        put(firm, "jobs", [job])

        def worker():
            try:

                def progress(message):
                    job.update(status="running", message=message, last_stage=message)
                    put(firm, "jobs", [job])

                if (
                    len(data["invoices"]) >= 10000
                    or deep_cash
                    or os.environ.get("AGENT1_ISOLATE_TRAINING") == "1"
                ):
                    from .train_worker import isolated_train

                    progress(
                        "Đang học trong worker riêng; không giới hạn tổng thời gian"
                    )
                    bundle = isolated_train(data, asof, deep_cash, progress)
                else:
                    bundle = train(data, asof, progress)
                    from agent1.adaptive.operating import select_operating

                    bundle["operating"] = select_operating(data, asof, False)
                # Only internally generated artifacts are deserialized, never uploads.
                bundle["synthetic_sandbox"] = demo_training_allowed(firm)
                from agent1.adaptive.training_report import save_training_report

                report_path = save_training_report(bundle, data, identifier)
                artifact = base64.b64encode(pickle.dumps(bundle)).decode()
                metadata = {
                    k: bundle[k]
                    for k in [
                        "asof",
                        "dataset_hash",
                        "audit",
                        "validation_n",
                        "train_n",
                        "algorithm_version",
                        "limitation",
                        "windows",
                        "code_hash",
                        "dependencies",
                    ]
                }
                metadata["synthetic_sandbox"] = demo_training_allowed(firm)
                metadata["risk_status"] = bundle.get("risk", {}).get(
                    "status", "unavailable"
                )
                metadata["risk_quality"] = {
                    k: v
                    for k, v in bundle.get("risk", {}).items()
                    if k
                    in (
                        "status",
                        "audit_brier",
                        "baseline_brier",
                        "accepted",
                        "n",
                        "audit_n",
                        "horizon_days",
                    )
                }
                metadata["collection_quality"] = {
                    k: v
                    for k, v in bundle.get("collection_evaluation", {}).items()
                    if k in ("status", "audit", "baseline", "accepted", "metric")
                }
                put(firm, "weights", [dict(id=identifier, artifact=artifact)])
                put(
                    firm,
                    "models",
                    [
                        dict(
                            id=identifier,
                            created_at=created,
                            artifact_id=identifier,
                            operating_ready=bool(bundle["operating"]),
                            **metadata,
                        )
                    ],
                )
                job.update(
                    status="completed",
                    message="Kiểm định xong. Xem kết quả và chọn phiên bản trước khi sử dụng.",
                    version=identifier,
                    encrypted_report=bool(report_path),
                )
            except Exception as exc:
                job.update(
                    status="failed",
                    message=str(exc)
                    if isinstance(exc, ValueError)
                    else "Tác vụ thất bại; dữ liệu và phiên bản đang dùng được giữ nguyên.",
                )
            finally:
                put(firm, "jobs", [job])
                with mutex:
                    running.discard(firm)

        executor.submit(worker)
        return dict(id=identifier, status="queued")

    @router.post("/models/{identifier}/activate")
    def activate(identifier: str, firm=Depends(authorize)):
        with mutex:
            row = next(
                (r for r in records(firm, "models") if r["id"] == identifier), None
            )
            if not row:
                raise HTTPException(404, "Không tìm thấy phiên bản của doanh nghiệp")
            put(firm, "model_active", [dict(id="active", version=identifier)])
            return dict(
                active_version=identifier,
                mode="shadow",
                stale=row["dataset_hash"] != fingerprint(current(firm)),
            )

    @router.delete("/models/{identifier}")
    def retire_model(identifier: str, confirm: str, firm=Depends(authorize)):
        with mutex:
            if confirm != identifier:
                raise HTTPException(422, "Xác nhận lại đúng mã phiên bản cần xóa.")
            model = one(firm, "models", identifier)
            if not model:
                raise HTTPException(404, "Không có phiên bản")
            active = one(firm, "model_active", "active") or {}
            if active.get("version") == identifier or any(
                r.get("model_version") == identifier
                for r in records(firm, "forecast_index")
            ):
                raise HTTPException(
                    409, "Phiên bản đang dùng hoặc đã được lưu trong kế hoạch."
                )
            entries = [("company_models", identifier)]
            if not any(
                r["id"] != identifier and r.get("artifact_id") == model["artifact_id"]
                for r in records(firm, "models")
            ):
                entries.append(("company_weights", model["artifact_id"]))
            store.remove(firm, entries)
            return dict(deleted=True)

    @router.get("/imports/{identifier}/errors")
    def import_errors(identifier: str, firm=Depends(authorize)):
        row = one(firm, "previews", identifier)
        if not row:
            raise HTTPException(404, "Không có bản kiểm tra")
        return dict(errors=row["errors"])

    @router.get("/reconciliation")
    def reconciliation(firm=Depends(authorize)):
        with mutex:
            data = current(firm)
            source = WorkspaceSource(store, firm, data)
            try:
                visible = source.view(t9_today())
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from exc
            used = {}
            for r in visible["links"].to_dict("records"):
                used[r["txn_id"]] = used.get(r["txn_id"], 0) + r["amount_minor"]
            rows = [dict(**r, unallocated=vnd(r["amount"]) - used.get(r["bank_id"], 0))
                    for r in visible["bank"] if r["direction"] == "in"]
            pending = [r for r in rows if r["unallocated"] > 0 and r.get("component") != "cash_sale"
                       and r.get("cash_flow_class") not in NON_AR]
            proposals = records(firm, "t9_proposals")
            latest = max(proposals, key=lambda r: r["created_at"], default=None)
            if latest:
                latest = dict(latest, stale=latest["snapshot_hash"] != visible["snapshot_hash"]
                              or latest["cutoff"] != t9_today()
                              or latest["ledger_sequence"] != len(source.ledger.events()))
                rejected = source.rejected_banks()
                latest["cases"] = [dict(r, status="rejected", note=rejected[r["bank_id"]]["note"],
                                        reviewed_by=rejected[r["bank_id"]]["reviewed_by"])
                                   if r["bank_id"] in rejected else r for r in latest["cases"]]
            history = source.history()
            open_invoices = visible["invoices"].to_dict("records")
            return display_money(dict(
                total_received=sum(vnd(r["amount"]) for r in rows),
                unallocated=sum(r["unallocated"] for r in pending), pending_count=len(pending),
                pending=pending[:100], proposal=latest, history=history[:100], history_count=len(history),
                invoices=[dict(invoice_id=r["invoice_id"], customer_id=r["customer_id"], amount_open_minor=r["amount_open_minor"])
                          for r in open_invoices if r["closure_type"] == "open"][:1000],
            ))

    @router.get("/corrections/record")
    def correction_record(kind: str, identifier: str, firm=Depends(authorize)):
        with mutex:
            try:
                return display_money(WorkspaceSource(store, firm, current(firm)).correction_record(kind, identifier))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc

    @router.post("/corrections/preview")
    def correction_preview(body: CorrectionPreview, firm=Depends(authorize)):
        with mutex, store.lock:
            data = current(firm)
            if body.base_hash != fingerprint(data):
                raise HTTPException(409, "Dữ liệu đã đổi. Tải lại bản ghi trước khi sửa.")
            try:
                preview, staged = WorkspaceSource(store, firm, data).preview_correction(
                    [r.model_dump() for r in body.changes], body.reviewed_by, body.note)
                check_bank_scope(staged)
                put(firm, "correction_previews", [preview])
                return display_money({k:v for k,v in preview.items() if k != 'changes_input'})
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(422, str(exc)) from exc

    @router.post("/corrections/{identifier}/commit")
    def correction_commit(identifier: str, body: CorrectionCommit, firm=Depends(authorize)):
        with mutex, store.lock:
            preview = one(firm, "correction_previews", identifier)
            if not preview:
                raise HTTPException(404, "Không tìm thấy bản xem trước của doanh nghiệp")
            try:
                return WorkspaceSource(store, firm, current(firm)).commit_correction(
                    preview, body.idempotency_key, validate_scope=check_bank_scope)
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @router.post("/reconciliation/run")
    def reconciliation_run(body: ReconciliationRun, firm=Depends(authorize)):
        with mutex:
            data = current(firm)
            try:
                check_bank_scope(data)
                result = t9_operations.propose(WorkspaceSource(store, firm, data), t9_today())
                return display_money(result)
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from exc

    @router.post("/reconciliation/accept")
    def reconciliation_accept(body: ReconciliationReview, firm=Depends(authorize)):
        with mutex:
            try:
                data = current(firm)
                check_bank_scope(data)
                result = t9_operations.accept(WorkspaceSource(store, firm, data), body.idempotency_key,
                    body.reviewed_by, proposal_id=body.proposal_id, txn_ids=[body.bank_id], note=body.note)
                return result
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @router.post("/reconciliation/reject")
    def reconciliation_reject(body: ReconciliationReview, firm=Depends(authorize)):
        with mutex:
            try:
                return WorkspaceSource(store, firm, current(firm)).reject(body.idempotency_key,
                    body.proposal_id, body.bank_id, body.reviewed_by, body.note)
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @router.post("/reconciliation/reverse")
    def reconciliation_reverse(body: ReconciliationReverse, firm=Depends(authorize)):
        with mutex:
            try:
                return t9_operations.reverse(WorkspaceSource(store, firm, current(firm)), body.idempotency_key,
                                              body.decision_id, body.reviewed_by, body.note)
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @router.post("/allocations")
    def allocate(body: Allocation, firm=Depends(authorize)):
        with mutex:
            data = current(firm)
            transaction = next(
                (r for r in data.get("bank", []) if r["bank_id"] == body.bank_id), None
            )
            if not transaction:
                raise HTTPException(404, "Không có dòng sao kê")
            payments = {r["payment_id"]: r for r in data["payments"]}
            existing = payments.get(body.payment_id)
            if existing and any(existing.get(k) not in (None, getattr(body, k))
                                for k in ("payment_id", "bank_id", "invoice_id", "amount")):
                raise HTTPException(
                    409,
                    "Mã thanh toán đã có nội dung khác. Xem trước bản cập nhật hoặc hoàn phân bổ trước.",
                )
            if existing and existing.get("bank_id") == body.bank_id and not existing.get("t9_decision_id"):
                return dict(version=fingerprint(data), replayed=True)
            try:
                check_bank_scope(data)
                source = WorkspaceSource(store, firm, data,
                                         payment_ids={(body.bank_id, body.invoice_id): body.payment_id})
                return t9_operations.accept(source, "workspace-payment:" + body.payment_id, body.reviewed_by,
                    allocations=[dict(txn_id=body.bank_id, invoice_id=body.invoice_id, amount_minor=body.amount)],
                    note=body.note)
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from exc

    @router.get("/forecasts")
    def histories(firm=Depends(read_access)):
        return sorted(
            records(firm, "forecast_index"), key=lambda r: r["created_at"], reverse=True
        )[:100]

    @router.get("/forecasts/{identifier}")
    def saved_forecast(identifier: str, firm=Depends(read_access)):
        row = one(firm, "predictions", identifier)
        if not row:
            raise HTTPException(404, "Không có dự báo này")
        return row

    @router.get("/forecasts/{identifier}/xlsx")
    def export_forecast(identifier: str, firm=Depends(read_access)):
        from .forecast_export import workbook_bytes

        plan = saved_forecast(identifier, firm)
        return Response(
            workbook_bytes(plan, firm),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="agent1-{identifier}.xlsx"'
            },
        )

    @router.get("/forecasts/{identifier}/actuals")
    def actuals(
        identifier: str,
        asof: str,
        payments_complete: bool = False,
        firm=Depends(authorize),
    ):
        from agent1.adaptive.cash_history import evaluate_plan

        plan = saved_forecast(identifier, firm)
        end = date(asof)
        if not plan.get("accounts"):
            raise HTTPException(422, "Kế hoạch chưa xác định phạm vi tài khoản sao kê.")
        data = current(firm)
        rows = evaluate_plan(data, plan, end, plan["accounts"])
        ready = [r for r in rows if r["balance_available"]]
        queue = []
        if payments_complete and pd.Timestamp(end) >= pd.Timestamp(
            plan["cutoff"]
        ) + pd.Timedelta(days=28):
            from agent1.adaptive.data import observed

            limit = pd.Timestamp(plan["cutoff"]) + pd.Timedelta(days=28)
            truth = observed(data, end).set_index("invoice_id")
            for budget in (5, 10, 20, 30):
                reviewed = [
                    r
                    for r in plan["collections"][:budget]
                    if r["invoice_id"] in truth.index
                ]
                hit = sum(
                    pd.isna(truth.loc[r["invoice_id"], "settled"])
                    or truth.loc[r["invoice_id"], "settled"] > limit
                    for r in reviewed
                )
                queue.append(
                    dict(
                        budget=budget,
                        reviewed=len(reviewed),
                        precision_still_open_28d=hit / len(reviewed)
                        if reviewed
                        else None,
                        coverage=len(reviewed) / max(1, plan["open_invoices"]),
                        reviewed_vnd=sum(int(r["outstanding"]) for r in reviewed),
                    )
                )
        return dict(
            weeks=rows,
            covered_weeks=len(ready),
            actual_dataset_hash=fingerprint(data),
            collections_curve=queue,
            mean_width80=sum(r["interval_width"] for r in ready) / len(ready)
            if ready
            else None,
            warning_lead_weeks=[
                r["week"] for r in ready if r["alert"] and r["shortfall"]
            ],
            prospective=plan.get("created_at", "9999")[:10] <= plan["cutoff"],
            mae=sum(r["abs_error"] for r in ready) / len(ready) if ready else None,
            coverage80=sum(r["interval_hit"] for r in ready) / len(ready)
            if ready
            else None,
            false_alerts=sum(r["alert"] and not r["shortfall"] for r in ready),
            misses=sum(not r["alert"] and r["shortfall"] for r in ready),
        )

    @router.post("/predict")
    def predict(body: Prediction, firm=Depends(authorize)):
        if not body.payments_complete:
            raise HTTPException(
                422,
                "Xác nhận đã nạp đủ thanh toán đến ngày dự báo để xác định đúng công nợ còn mở.",
            )
        cutoff = date(body.cutoff)
        if any(week > body.horizon_weeks for week in body.confirmed_weeks):
            raise HTTPException(422, "Tuần xác nhận lịch chi phải nằm trong kỳ dự báo.")
        active = records(firm, "model_active")
        bundle = None
        model = None
        if active:
            model = one(firm, "models", active[0]["version"])
            if model:
                weight = one(firm, "weights", model["artifact_id"])
                bundle = pickle.loads(base64.b64decode(weight["artifact"]))
        try:
            data = current(firm)
            check_bank_scope(data)
            started = time.perf_counter()
            result = forecast(
                data,
                cutoff,
                body.opening_balance,
                bundle,
                body.delay_days,
                body.expense_multiplier,
                body.confirmed_weeks,
                body.cash_floor,
                body.shared_customer_risk,
                body.delay_customer,
                body.include_operating,
                horizon_weeks=body.horizon_weeks,
            )
            result.update(
                inference_ms=round((time.perf_counter() - started) * 1000),
                accounts=account_scope(data, cutoff),
                model_version=model["id"] if model else None,
                stale_model=bool(model and model["dataset_hash"] != fingerprint(data)),
                scenario=dict(
                    delay_days=body.delay_days,
                    expense_multiplier=body.expense_multiplier,
                    delay_customer=body.delay_customer,
                    shared_customer_risk=body.shared_customer_risk,
                ),
                confirmed_weeks=body.confirmed_weeks,
                dataset_hash=fingerprint(data),
            )
            for invoice in result["collections"]:
                explanation = invoice.get("payment_explanation")
                if explanation is not None:
                    explanation.update(
                        model_version=result["model_version"],
                        dataset_hash=result["dataset_hash"],
                    )
                ranking = invoice.get("ranking_explanation")
                if ranking is not None:
                    ranking.update(
                        displayed_model_version=result["model_version"],
                        dataset_hash=result["dataset_hash"],
                    )
                    ranking["probability_source"]["dataset_hash"] = result["dataset_hash"]
                    if ranking.get("probability_explanation"):
                        ranking["probability_explanation"]["dataset_hash"] = result["dataset_hash"]
            result["collection_ranking"].update(
                model_version=result["model_version"],
                dataset_hash=result["dataset_hash"],
            )
            result["cash_decomposition"].update(
                model_version=result["model_version"],
                dataset_hash=result["dataset_hash"],
            )
            result.update(
                id=uuid.uuid4().hex,
                created_at=datetime.now(timezone.utc).isoformat(),
                band_protocol="cash-v3-t5-ledger",
            )
            if result["accounts"]:
                from agent1.adaptive.cash_history import calibrate_bands

                # Read only mature, eligible candidates; old unindexed plans cannot calibrate.
                past = [
                    r
                    for r in records(firm, "forecast_index")
                    if r["created_at"]
                    and r["created_at"][:10] <= r["cutoff"]
                    and r["cutoff"] < cutoff
                    and r.get("model_version") == result["model_version"]
                ]
                calibrate_bands(
                    result, (one(firm, "predictions", r["id"]) for r in past), data
                )
            put(firm, "predictions", [result])
            put(
                firm,
                "forecast_index",
                [
                    {
                        k: result[k]
                        for k in (
                            "id",
                            "created_at",
                            "cutoff",
                            "opening_balance",
                            "dataset_hash",
                            "model_version",
                            "scenario",
                            "minimum_balance",
                            "horizon_weeks",
                        )
                    }
                ],
            )
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    install_portal_connect(app, router, bearer_authorize, firm_id)
    app.include_router(router)
    root = Path(__file__).resolve().parents[1] / "ui/workspace"

    @app.get("/workspace", include_in_schema=False)
    def page():
        return FileResponse(root / "index.html")

    from fastapi.staticfiles import StaticFiles

    app.mount("/workspace-assets", StaticFiles(directory=root), name="workspace-assets")
