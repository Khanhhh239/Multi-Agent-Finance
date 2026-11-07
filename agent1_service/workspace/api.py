import base64
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
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Header
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field, ConfigDict
from agent1.adaptive.data import (
    SCHEMAS,
    IDS,
    suggested_mapping,
    parse_rows,
    validate_dataset,
    fingerprint,
)
from agent1.adaptive.methods import train, forecast, CATALOG
from typing import Annotated


class Training(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asof: str
    payments_complete: bool = False
    try_deep_cash: bool = False


class Allocation(BaseModel):
    payment_id: str = Field(min_length=1, max_length=160)
    bank_id: str = Field(min_length=1, max_length=160)
    invoice_id: str = Field(min_length=1, max_length=160)
    amount: float = Field(gt=0, allow_inf_nan=False)


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


def install(app, store, authorize, firm_id):
    router = APIRouter(prefix="/v1")
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
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            )
        return response

    def records(firm, kind):
        return store.get(firm, "company_" + kind)

    def put(firm, kind, rows):
        store.put(firm, "company_" + kind, rows)

    def one(firm, kind, identifier):
        return store.one(firm, "company_" + kind, identifier)

    def read_access(authorization: str | None = Header(None)):
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
    def access(authorization: str | None = Header(None), firm=Depends(read_access)):
        try:
            authorize(authorization)
        except HTTPException:
            return dict(company=firm, role="reader")
        return dict(company=firm, role="accountant")

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
    def template(kind: str, firm=Depends(authorize)):
        if kind not in SCHEMAS:
            raise HTTPException(404, "Không có mẫu")
        examples = {
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
        }
        csv = (
            pd.DataFrame([examples[kind]], columns=list(SCHEMAS[kind]))
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
        date_format: str = Form("%d/%m/%Y"),
        number_format: str = Form("vi-VN"),
        sheet: str = Form(""),
        firm=Depends(authorize),
    ):
        if kind not in SCHEMAS:
            raise HTTPException(422, "Loại bảng không hợp lệ")
        content = await file.read(5_000_001)
        if len(content) > 5_000_000:
            raise HTTPException(413, "Tối đa 5 MB mỗi file")
        try:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix == ".xlsx":
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    if sum(f.file_size for f in z.infolist()) > 30_000_000:
                        raise ValueError("Workbook vượt giới hạn giải nén 30 MB")
                with pd.ExcelFile(io.BytesIO(content)) as workbook:
                    sheets = workbook.sheet_names
                    raw = workbook.parse(
                        sheet_name=sheet or sheets[0],
                        dtype=object,
                        keep_default_na=False,
                    )
            elif suffix == ".csv":
                raw = pd.read_csv(
                    io.BytesIO(content),
                    dtype=str,
                    sep=None,
                    engine="python",
                    encoding="utf-8-sig",
                    keep_default_na=False,
                )
            else:
                raise ValueError("Chọn CSV UTF-8 hoặc XLSX")
            if len(raw) > 50000:
                raise ValueError("Tối đa 50.000 dòng mỗi lần nạp")
            selected = json.loads(mapping)
            if not isinstance(selected, dict):
                raise ValueError("Ánh xạ phải là đối tượng")
            schema_id = fingerprint([kind, list(raw.columns)])
            saved = one(firm, "mappings", schema_id)
            selected = selected or (
                saved["mapping"] if saved else suggested_mapping(raw.columns, kind)
            )
            accepted, errors, warnings = parse_rows(
                raw, kind, selected, date_format, number_format
            )
            staged = current(firm)
            base_hash = fingerprint(staged)
            merged = {r[IDS[kind]]: r for r in staged.get(kind, [])}
            changes = [
                dict(before=merged[r[IDS[kind]]], after=r)
                for r in accepted
                if r[IDS[kind]] in merged and merged[r[IDS[kind]]] != r
            ][:10]
            updates = sum(r[IDS[kind]] in merged for r in accepted)
            merged.update({r[IDS[kind]]: r for r in accepted})
            staged[kind] = list(merged.values())
            if not errors:
                try:
                    validate_dataset(staged)
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
                        base_hash=base_hash,
                        valid=not errors,
                        errors=errors,
                        schema_id=schema_id,
                        mapping=selected,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                ],
            )
            return dict(
                id=identifier,
                columns=list(raw.columns),
                sheets=sheets if suffix == ".xlsx" else [],
                changes=changes,
                fields=list(SCHEMAS[kind]),
                mapping=selected,
                rows=len(raw),
                valid_rows=len(accepted),
                updates=updates,
                errors=errors[:100],
                error_count=len(errors),
                warnings=warnings,
                sample=accepted[:5],
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
            data = current(firm)
            if p["base_hash"] != fingerprint(data):
                raise HTTPException(
                    409, "Dữ liệu đã đổi. Xem trước lại để tránh ghi đè."
                )
            key = IDS[p["kind"]]
            merged = {r[key]: r for r in data.get(p["kind"], [])}
            merged.update({r[key]: r for r in p["records"]})
            data[p["kind"]] = list(merged.values())
            validate_dataset(data)
            version = fingerprint(data)
            put(
                firm,
                "datasets",
                [
                    dict(
                        id=version,
                        data=data,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                ],
            )
            put(
                firm,
                "dataset_active",
                [
                    dict(
                        id="active",
                        version=version,
                        counts={k: len(data.get(k, [])) for k in SCHEMAS},
                    )
                ],
            )
            if "schema_id" in p:
                put(firm, "mappings", [dict(id=p["schema_id"], mapping=p["mapping"])])
            return dict(version=version, accepted=len(p["records"]), updated=True)

    @router.delete("/records/{kind}/{identifier:path}")
    def remove(kind: str, identifier: str, firm=Depends(authorize)):
        if kind not in SCHEMAS:
            raise HTTPException(404, "Không có bảng này")
        with mutex:
            data = current(firm)
            before = len(data.setdefault(kind, []))
            data[kind] = [r for r in data[kind] if r[IDS[kind]] != identifier]
            if before == len(data[kind]):
                raise HTTPException(404, "Không tìm thấy mã")
            try:
                validate_dataset(data)
            except ValueError as exc:
                raise HTTPException(409, "Xóa thanh toán liên quan trước. " + str(exc))
            version = fingerprint(data)
            put(
                firm,
                "datasets",
                [
                    dict(
                        id=version,
                        data=data,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                ],
            )
            put(
                firm,
                "dataset_active",
                [
                    dict(
                        id="active",
                        version=version,
                        counts={k: len(data.get(k, [])) for k in SCHEMAS},
                    )
                ],
            )
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

            accounts = sorted(
                {
                    r["account"]
                    for r in data.get("statements", [])
                    if r["known_at"] <= asof
                }
            )
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
        data = current(firm)
        used = {}
        for r in data.get("payments", []):
            if r.get("bank_id"):
                used[r["bank_id"]] = used.get(r["bank_id"], 0) + r["amount"]
        rows = [
            dict(**r, unallocated=r["amount"] - used.get(r["bank_id"], 0))
            for r in data.get("bank", [])
            if r["direction"] == "in"
        ]
        pending = [
            r
            for r in rows
            if r["unallocated"] > 0.01 and r.get("component") != "cash_sale"
        ]
        return dict(
            total_received=sum(r["amount"] for r in rows),
            unallocated=sum(r["unallocated"] for r in pending),
            pending_count=len(pending),
            pending=pending[:100],
        )

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
            if existing and any(
                existing.get(k) not in (None, v) for k, v in body.model_dump().items()
            ):
                raise HTTPException(
                    409,
                    "Mã thanh toán đã có nội dung khác. Xem trước bản cập nhật hoặc hoàn phân bổ trước.",
                )
            if existing and existing.get("bank_id") == body.bank_id:
                return dict(version=fingerprint(data), replayed=True)
            payments[body.payment_id] = dict(
                **body.model_dump(),
                payment_date=transaction["date"],
                known_at=max(transaction["known_at"], str(datetime.now().date())),
            )
            data["payments"] = list(payments.values())
            try:
                validate_dataset(data)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            identifier = fingerprint(data)
            put(
                firm,
                "datasets",
                [
                    dict(
                        id=identifier,
                        data=data,
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                ],
            )
            put(
                firm,
                "dataset_active",
                [
                    dict(
                        id="active",
                        version=identifier,
                        counts={k: len(data.get(k, [])) for k in SCHEMAS},
                    )
                ],
            )
            return dict(version=identifier, replayed=False)

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
                        reviewed_vnd=sum(r["outstanding"] for r in reviewed),
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
                accounts=sorted(
                    {
                        r["account"]
                        for k in ("bank", "statements")
                        for r in data.get(k, [])
                        if r["known_at"] <= cutoff
                    }
                ),
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
            result.update(
                id=uuid.uuid4().hex,
                created_at=datetime.now(timezone.utc).isoformat(),
                band_protocol="cash-v2",
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

    app.include_router(router)
    root = Path(__file__).resolve().parents[1] / "ui/workspace"

    @app.get("/workspace", include_in_schema=False)
    def page():
        return FileResponse(root / "index.html")

    from fastapi.staticfiles import StaticFiles

    app.mount("/workspace-assets", StaticFiles(directory=root), name="workspace-assets")
