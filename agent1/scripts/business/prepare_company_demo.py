"""Build an isolated, fictional one-company Agent 1 presentation workspace.

Never resets existing stores. Each preparation creates a new local run directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent1"))
PACK = ROOT / "agent1/pilot/demo_doanh_nghiep"
SOURCE = ROOT / "agent1/pilot/demo_dai_phat"
FIRM = "DEMO_DAIPHAT"
ORDER = ("invoices", "bank", "payments", "statements", "outflows", "expense_payments", "actions")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def csv_bytes(rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def build(cutoff):
    from agent1.adaptive.data import SCHEMAS, parse_rows, suggested_mapping, validate_dataset
    import pandas as pd

    rows = {}
    for n, kind in enumerate(("invoices", "bank", "payments", "statements", "outflows", "actions"), 1):
        with (SOURCE / f"{n:02}_{kind}.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows[kind] = list(csv.DictReader(handle))
    # Keep the entire source ledger, including its original supplier settlements.
    rows["expense_payments"] = []
    base_date = date(2026, 10, 31)
    if cutoff <= base_date:
        raise ValueError("Demo date must be after 2026-10-31")
    shift = cutoff - base_date
    # Move the known future schedule together, leaving the historical ledger unchanged.
    for row in rows["outflows"]:
        row["date"] = str(date.fromisoformat(row["date"]) + shift)
        row["known_at"] = str(cutoff)
        row.update(obligation_ref="DP-PLAN-" + row["expense_id"],
                   payment_period=row["date"][:7], installment_no="1")
    paid_ids = {r["bank_id"] for r in rows["payments"]}
    for row in rows["bank"]:
        if row["direction"] == "in" and row["bank_id"] not in paid_ids and row["component"] != "cash_sale":
            row.update(cash_flow_class="other_external", memo="Khoản thu phi công nợ mô phỏng")

    history_counts = {k: len(rows[k]) for k in ("invoices", "bank", "payments", "statements", "actions")}

    def invoice(identifier, customer, amount, due_days=0):
        rows["invoices"].append(dict(invoice_id=identifier, customer_id=customer,
            customer_name=customer.replace("DP-", ""), issue_date=str(cutoff - timedelta(days=1)),
            due_date=str(cutoff + timedelta(days=due_days)), amount=amount,
            currency="VND", known_at=str(cutoff - timedelta(days=1))))

    def bank(identifier, customer, amount, memo, direction="in"):
        rows["bank"].append(dict(bank_id=identifier, account="DP-VND01", date=str(cutoff),
            direction=direction, amount=amount, known_at=str(cutoff), component="other",
            customer_id=customer, counterparty=customer, memo=memo))

    invoice("DP-HD-DUNG", "DP-KH-DEMO-DUNG", 10_000_000)
    invoice("DP-HD-MOTPHAN", "DP-KH-DEMO-PART", 20_000_000)
    invoice("DP-HD-GOP1", "DP-KH-DEMO-GOP", 3_000_000)
    invoice("DP-HD-GOP2", "DP-KH-DEMO-GOP", 7_000_000)
    invoice("DP-HD-KIEMTRA1", "DP-KH-DEMO-KIEMTRA", 6_000_000)
    invoice("DP-HD-KIEMTRA2", "DP-KH-DEMO-KIEMTRA", 6_000_000)
    bank("DP-B-DUNG", "DP-KH-DEMO-DUNG", 10_000_000, "Thanh toan DP-HD-DUNG")
    bank("DP-B-MOTPHAN", "DP-KH-DEMO-PART", 8_000_000, "Thanh toan mot phan DP-HD-MOTPHAN")
    bank("DP-B-GOP", "DP-KH-DEMO-GOP", 10_000_000, "Thanh toan DP-HD-GOP1 DP-HD-GOP2")
    bank("DP-B-KIEMTRA", "DP-KH-DEMO-KIEMTRA", 6_000_000, "Thanh toan cong no")
    bank("DP-B-CHUARO", "", 5_000_000, "Chua xac minh nguoi chuyen")
    bank("DP-B-THUE", "DP-NCC-THUE", 40_000_000, "Tra truoc tien thue", "out")
    closing = 425_000_000 + 39_000_000 - 40_000_000
    rows["statements"].append(dict(statement_id="DP-S-DEMO", account="DP-VND01",
        start_date=str(base_date + timedelta(days=1)), end_date=str(cutoff),
        opening_balance=425_000_000, closing_balance=closing, known_at=str(cutoff)))
    rows["outflows"].append(dict(expense_id="DP-THUE-DEMO", date=str(cutoff + timedelta(days=7)),
        known_at=str(cutoff), amount=100_000_000, category="Tiền thuê kho mô phỏng",
        obligation_ref="DP-HOPDONG-THUE", payment_period=str(cutoff)[:7], installment_no="1"))
    rows["expense_payments"].append(dict(settlement_id="DP-TRA-THUE", expense_id="DP-THUE-DEMO",
        bank_id="DP-B-THUE", payment_date=str(cutoff), amount=40_000_000, known_at=str(cutoff)))
    rows["actions"].append(dict(event_id="DP-HUA-DEMO", invoice_id="DP-HD-MOTPHAN",
        date=str(cutoff), known_at=str(cutoff), kind="promise", promise_date=str(cutoff + timedelta(days=7))))
    received = {}
    for row in rows['payments']:
        received[row['invoice_id']] = received.get(row['invoice_id'], 0) + int(row['amount'])
    written_off = {r['invoice_id'] for r in rows['actions'] if r['kind']=='write_off'}
    promised = max((r for r in rows['invoices'] if r['invoice_id'] not in written_off),
        key=lambda r:int(r['amount'])-received.get(r['invoice_id'],0))
    rows['actions'].append(dict(event_id='DP-HUA-KHOANLON', invoice_id=promised['invoice_id'],
        date=str(cutoff), known_at=str(cutoff), kind='promise', promise_date=str(cutoff+timedelta(days=7))))
    data = {k: [] for k in SCHEMAS}
    files = []
    PACK.mkdir(parents=True, exist_ok=True)
    for n, kind in enumerate(ORDER, 1):
        payload = csv_bytes(rows[kind])
        filename = f"{n:02}_{kind}.csv"
        (PACK / filename).write_bytes(payload)
        raw = pd.read_csv(io.BytesIO(payload), dtype=str, keep_default_na=False)
        parsed, errors, _ = parse_rows(raw, kind, suggested_mapping(raw.columns, kind), "%Y-%m-%d", "plain")
        if errors:
            raise ValueError((kind, errors[:3]))
        data[kind] = parsed
        files.append(dict(kind=kind, file=filename, rows=len(parsed), sha256=hashlib.sha256(payload).hexdigest()))
    validate_dataset(data)
    phases = []
    for phase, kinds in (("01_lich_su", ("invoices", "bank", "payments", "statements", "actions")),
                         ("02_phat_sinh_moi", ("invoices", "bank", "statements", "actions")),
                         ("03_lich_chi", ("outflows", "expense_payments"))):
        entries = []
        for n, kind in enumerate(kinds, 1):
            phase_rows = (rows[kind][:history_counts[kind]] if phase == "01_lich_su" else
                          rows[kind][history_counts[kind]:] if phase == "02_phat_sinh_moi" else rows[kind])
            relative = f"{phase}/{n:02}_{kind}.csv"
            payload = csv_bytes(phase_rows)
            (PACK / phase).mkdir(parents=True, exist_ok=True)
            (PACK / relative).write_bytes(payload)
            entries.append(dict(kind=kind, file=relative, rows=len(phase_rows),
                                sha256=hashlib.sha256(payload).hexdigest()))
        phases.append(dict(id=phase, files=entries))
    invalid = dict(rows["invoices"][-1], invoice_id="DP-LOI-DEMO", amount="-1")
    (PACK / "99_chi_xem_truoc_loi.csv").write_bytes(csv_bytes([invalid]))
    # Small, idempotent import for showing the Portal intake without a second business.
    (PACK / "00_nap_thu_khong_trung.csv").write_bytes(csv_bytes([rows["invoices"][-1]]))
    manifest = dict(company=FIRM, legal_name="Đại Phát — doanh nghiệp mô phỏng",
        synthetic=True, cutoff=str(cutoff), opening_balance=closing, cash_floor=200_000_000,
        confirmed_weeks=list(range(1, 14)), files=files, phases=phases,
        source_files=[dict(file=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                      for p in sorted(SOURCE.glob("*.csv"))],
        history_cutoff=str(base_date), history_counts=history_counts,
        pending_bank_ids=["DP-B-DUNG", "DP-B-MOTPHAN", "DP-B-GOP", "DP-B-KIEMTRA", "DP-B-CHUARO"],
        assumptions=["Full fictional Dai Phat ledger retained: all 12,780 invoices, all historical bank/payment rows and original supplier settlements. Future source schedule is not scaled down.",
            "No additional business movements between 2026-11-01 and cutoff except six explicitly generated bank rows.",
            "The 13-week declared schedule is complete for this synthetic AR/T5 demonstration; new sales are excluded.",
            "The 40m rent prepayment is already included in the 424m opening balance; only 60m remains.",
            "No real-world forecast accuracy or causal benefit is claimed."])
    write_json(PACK / "manifest.json", manifest)
    return data, manifest


def import_pack(client, manifest, entries=None):
    for entry in manifest["files"] if entries is None else entries:
        file = PACK / entry["file"]
        response = client.post("/v1/imports/preview", files={"file": (file.name, file.read_bytes())},
            data=dict(kind=entry["kind"], date_format="%Y-%m-%d", number_format="plain", imported_by="Chuẩn bị demo Đại Phát"))
        response.raise_for_status()
        preview = response.json()
        if not preview["can_commit"]:
            raise ValueError((file.name, preview.get("errors")))
        client.post("/v1/imports/" + preview["id"] + "/commit").raise_for_status()
        print("Imported", entry["file"], entry["rows"], flush=True)


def prepare(args):
    cutoff = date.fromisoformat(args.cutoff) if args.cutoff else datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    data, manifest = build(cutoff)
    if args.pack_only:
        print(json.dumps(dict(cutoff=manifest["cutoff"], files=manifest["files"], phases=manifest["phases"]), ensure_ascii=False, indent=2))
        return
    run_id = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    run = ROOT / ".runtime/agent1-demo" / run_id
    work = run / "portal"
    work.mkdir(parents=True)
    company = dict(code=FIRM, legal_name=manifest["legal_name"], tax_code="0999999905",
        registered_address="Địa chỉ mô phỏng", industry="Thương mại và phân phối (mô phỏng)",
        vat_method="DEDUCTION", filing_period="MONTH", fiscal_year_end_month=12,
        date_format="iso", number_format="plain", agent2_company="")
    write_json(work / "company.json", company)
    profile = work / "agent1_profiles" / (FIRM + ".json")
    write_json(profile, {k: company[k] for k in ("code", "date_format", "number_format")})
    storage = run / "agent1"
    state = storage / (".state-business-firm-" + FIRM + "-data")
    keys = Path(str(state) + "-keys")
    config = dict(port=args.port, workspace=str(work), demo_company=None,
        agents={"agent1": dict(port=args.agent_port, python=sys.executable, storage_root=str(storage),
            env={"AGENT1_T1_GLOBAL_CATALOG": str(ROOT / "agent1/outputs/t1/settlement_partial_catalog_v3_20261114/catalog.json"),
                 "AGENT1_REPORT_DIR": str(run / "training-reports")}),
            "agent2": dict(port=args.agent_port+1),
            "agent3": dict(port=args.agent_port+2, env={
                "AGENT3_WORKSPACES": str(run / "agent3/workspaces"),
                "AGENT3_ADMIN_STORE": str(run / "agent3/admin.json")}),
            "agent4": dict(port=args.agent_port+3)})
    write_json(run / "portal-config.json", config)
    os.environ["AGENT1_COMPANY_PROFILE_FILE"] = str(profile)
    os.environ["AGENT1_DEMO_TRAINING"] = "1"
    os.environ["AGENT1_FRAME_ANCESTORS"] = f"http://127.0.0.1:{args.port} http://localhost:{args.port}"
    from fastapi.testclient import TestClient
    from agent1_service.api import create_app
    app = create_app(state, key_dir=keys, firm_id=FIRM)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + (keys / "api-token.txt").read_text(encoding="utf-8").strip()
        if args.preload:
            import_pack(client, manifest)
        if args.preload:
            # Synthetic fixture coverage, never inferred for a real company.
            app.state.store.put(FIRM, "company_payment_coverage", [dict(id="synthetic-coverage-"+r["statement_id"],
                start_date=r["start_date"], end_date=r["end_date"], known_at=r["known_at"], complete=True,
                source="deterministic synthetic demo generator") for r in data['statements']])
        status = client.get("/v1/reconciliation").json()
        if status["pending_count"] != (5 if args.preload else 0):
            raise ValueError(("pending count", status["pending_count"]))
    latest = dict(run=str(run), config=str(run / "portal-config.json"), state=str(state), keys=str(keys),
        company=FIRM, cutoff=str(cutoff), portal_url=f"http://127.0.0.1:{args.port}",
        agent_url=f"http://127.0.0.1:{args.agent_port}", password_file=str(run / "portal-password.txt"),
        manifest=str(run / "pack/manifest.json"), preloaded=args.preload)
    # Freeze each run's inputs: regenerating the next pack must not alter this run.
    import shutil
    shutil.copytree(PACK, run / "pack", ignore=shutil.ignore_patterns("*.ps1", "*.md"))
    (run / "portal-password.txt").write_text(secrets.token_urlsafe(12), encoding="utf-8")
    write_json(ROOT / ".runtime/agent1-demo/latest.json", latest)
    print(json.dumps({k:latest[k] for k in ("company", "cutoff", "portal_url", "run")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff")
    parser.add_argument("--port", type=int, default=8881)
    parser.add_argument("--agent-port", type=int, default=8111)
    parser.add_argument("--preload", action="store_true", help="Load sources in advance for a backup run; default is empty")
    parser.add_argument("--pack-only", action="store_true", help="Regenerate phase inputs without touching any runtime or latest pointer")
    prepare(parser.parse_args())
