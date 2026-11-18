"""Rehearse full history -> append -> reconcile -> schedule -> T1/T6/T10 in a new store."""
from __future__ import annotations

import io
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent1"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", type=Path, help="Continue final forecast checks in an existing completed rehearsal store")
    args = parser.parse_args()
    from fastapi.testclient import TestClient
    from agent1_service.api import create_app
    from openpyxl import load_workbook
    from load_company_demo_phase import load_phase

    pack = ROOT / "agent1/pilot/demo_doanh_nghiep"
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    rehearsal = args.resume.resolve() if args.resume else ROOT / ".runtime/agent1-demo" / ("rehearsal-full-" + str(time.time_ns()))
    if args.resume:
        if not rehearsal.is_relative_to((ROOT / ".runtime/agent1-demo").resolve()) or not (rehearsal / "data/agent1.db").is_file():
            raise ValueError("Resume requires an existing isolated rehearsal under .runtime/agent1-demo")
    else:
        rehearsal.mkdir(parents=True)
    state, keys = rehearsal / "data", rehearsal / "keys"
    profile = rehearsal / "company.json"
    profile.write_text(json.dumps(dict(code=manifest["company"], date_format="iso", number_format="plain")), encoding="utf-8")
    os.environ["AGENT1_COMPANY_PROFILE_FILE"] = str(profile)
    os.environ["AGENT1_T1_GLOBAL_CATALOG"] = str(ROOT / "agent1/outputs/t1/settlement_partial_catalog_v3_20261114/catalog.json")
    os.environ["AGENT1_DEMO_TRAINING"] = "1"
    app = create_app(state, key_dir=keys, firm_id=manifest["company"])
    report = dict(company=manifest["company"], synthetic=True, checks=[], cutoff=manifest["cutoff"],
                  status="running", rehearsal=str(rehearsal))
    checkpoint = rehearsal / "verification.json"
    if args.resume and checkpoint.is_file():
        report.update(json.loads(checkpoint.read_text(encoding="utf-8")))
        report["status"] = "running"

    def passed(name):
        report["checks"].append(name)
        checkpoint.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("PASS", name, flush=True)

    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + (keys / "api-token.txt").read_text(encoding="utf-8").strip()

        def call(method, path, **kwargs):
            response = getattr(client, method)(path, **kwargs)
            if response.status_code >= 400:
                raise AssertionError((path, response.status_code, response.text[:1500]))
            return response.json()

        if not args.resume:
            status = call("get", "/v1/workspace")
            assert not status["jobs"] and not status["versions"]
            assert call("get", "/v1/forecasts") == []
            assert all(n == 0 for n in status["counts"].values())
            passed("Empty store: no invoices, bank, schedules, jobs or forecasts")
            # A schedule cannot be loaded before history/new documents/reconciliation.
            try:
                load_phase(client, manifest, pack, "schedule")
            except ValueError:
                pass
            else:
                raise AssertionError("Out-of-order schedule accepted")
            load_phase(client, manifest, pack, "history")
            history = call("get", "/v1/workspace")["counts"]
            assert all(history[k] == n for k, n in manifest["history_counts"].items())
            assert history["invoices"] == 12780 and history["outflows"] == 0
            assert call("get", "/v1/reconciliation")["pending_count"] == 0
            report["history_counts"] = history
            passed("T0: full 2015-2026 history loaded; 12,780 invoices; historical payments already allocated")
            # Safe retry of the entire history, before subsequent operations.
            load_phase(client, manifest, pack, "history")
            assert call("get", "/v1/workspace")["counts"] == history
            passed("T0: retry entire history without duplicated records")
            load_phase(client, manifest, pack, "new")
            current = call("get", "/v1/workspace")["counts"]
            assert current["invoices"] == history["invoices"] + 6
            assert current["bank"] == history["bank"] + 6
            assert current["payments"] == history["payments"] and current["outflows"] == 0
            pending = call("get", "/v1/reconciliation")
            assert pending["pending_count"] == 5 and int(pending["unallocated"]) == 39_000_000
            passed("Append: six NEW invoices and six bank documents; history retained; 5 pending receipts / 39m")
            file = pack / "99_chi_xem_truoc_loi.csv"
            bad = call("post", "/v1/imports/preview", files={"file": (file.name, file.read_bytes())},
                data=dict(kind="invoices", imported_by="Rehearsal"))
            assert not bad["can_commit"] and bad["error_count"]
            passed("T0: invalid money rejected before commit")
            file = pack / "00_nap_thu_khong_trung.csv"
            preview = call("post", "/v1/imports/preview", files={"file": (file.name, file.read_bytes())},
                data=dict(kind="invoices", imported_by="Rehearsal"))
            assert preview["can_commit"]
            before = call("get", "/v1/workspace")["counts"]
            call("post", "/v1/imports/"+preview["id"]+"/commit")
            assert call("get", "/v1/workspace")["counts"] == before
            passed("T0: identical import does not duplicate invoices")
            proposal = call("post", "/v1/reconciliation/run", json={})
            cases = {r["bank_id"]:r for r in proposal["cases"]}
            assert cases["DP-B-KIEMTRA"]["status"] != "auto", cases["DP-B-KIEMTRA"]
            for n, bank in enumerate(("DP-B-DUNG", "DP-B-MOTPHAN", "DP-B-GOP")):
                proposal = call("post", "/v1/reconciliation/run", json={})
                row = next(r for r in proposal["cases"] if r["bank_id"] == bank)
                assert row.get("allocations"), row
                call("post", "/v1/reconciliation/accept", json=dict(idempotency_key="rehearsal-"+str(n),
                    proposal_id=proposal["id"], bank_id=bank, reviewed_by="Diễn tập", note="Dữ liệu mô phỏng"))
            detail = call("get", "/v1/records", params=dict(kind="invoices", q="DP-HD-MOTPHAN"))
            assert int(next(r for r in detail["rows"] if r["invoice_id"] == "DP-HD-MOTPHAN")["remaining_amount"]) == 12_000_000
            passed("T9: exact, partial and grouped receipts accepted; ambiguous receipt held")
            call("post", "/v1/allocations", json=dict(payment_id="DP-TT-KIEMTRA", bank_id="DP-B-KIEMTRA",
                invoice_id="DP-HD-KIEMTRA2", amount=6_000_000, reviewed_by="Diễn tập",
                note="BANG_KE_XAC_MINH.md: xác nhận mô phỏng trả DP-HD-KIEMTRA2"))
            correction = call("post", "/v1/corrections/preview", json=dict(
                base_hash=call("get", "/v1/workspace")["dataset_hash"],
                changes=[dict(kind="bank", identifier="DP-B-CHUARO", values=dict(cash_flow_class="other_external"))],
                reviewed_by="Diễn tập", note="BANG_KE_XAC_MINH.md: khoản thu khác ngoài công nợ, tình huống mô phỏng"))
            call("post", "/v1/corrections/"+correction["id"]+"/commit", json=dict(idempotency_key="verify-non-ar"))
            assert call("get", "/v1/reconciliation")["pending_count"] == 0
            passed("T9: manual ambiguity resolution and documented non-AR classification clear the queue")
            load_phase(client, manifest, pack, "schedule")
            report["final_counts"] = call("get", "/v1/workspace")["counts"]
            assert report["final_counts"]["outflows"] == 28
            assert report["final_counts"]["expense_payments"] == 1
            passed("T5: schedules loaded after reconciliation, 28 obligations and one actual settlement")
        else:
            status = call("get", "/v1/workspace")
            expected_counts = {e["kind"]: e["rows"] for e in manifest["files"]}
            expected_counts["payments"] += 5
            assert all(status["counts"][kind] == n for kind, n in expected_counts.items())
            assert not status["jobs"] and not status["versions"]
            assert call("get", "/v1/reconciliation")["pending_count"] == 0
            report["history_counts"] = manifest["history_counts"]
            report["final_counts"] = status["counts"]
            report["resumed_after_intake"] = True
            passed("Resume: exact completed intake counts and zero pending receipts confirmed")
        prediction = dict(cutoff=manifest["cutoff"], opening_balance=float(manifest["opening_balance"]),
            cash_floor=float(manifest["cash_floor"]), horizon_weeks=13, payments_complete=True,
            confirmed_weeks=list(range(1,14)), include_operating=False)
        if args.resume:
            saved = call("get", "/v1/forecasts")
            current_hash = call("get", "/v1/workspace")["dataset_hash"]
            matching = next(r for r in saved if r["cutoff"] == manifest["cutoff"] and r["dataset_hash"] == current_hash)
            plan = call("get", "/v1/forecasts/" + matching["id"])
            assert plan["dataset_hash"] == current_hash
            assert plan["cutoff"] == manifest["cutoff"]
        else:
            plan = call("post", "/v1/predict", json=prediction)
        assert len(plan["weeks"]) == 13 and plan["t10"] and plan["open_invoices"] > 100
        assert all(0 <= r["payment_probability_4w"] <= 1 for r in plan["collections"])
        report["open_invoices"] = plan["open_invoices"]
        report["displayed_priority_invoices"] = len(plan["collections"])
        assert len(plan["cash_decomposition"]["invoices"]) == plan["open_invoices"]
        partial_invoice = next(r for r in plan["cash_decomposition"]["invoices"] if r["invoice_id"] == "DP-HD-MOTPHAN")
        assert float(partial_invoice["outstanding"]) == 12_000_000
        expected = plan["opening_balance"]
        for week in plan["weeks"]:
            expected += week["cash_in"] + week.get("obligation_in", 0) - week["cash_out"]
            assert abs(expected - week["expected_balance"]) < 0.001
        rent = next(r for r in plan["t5"]["obligations"] if r["expense_id"] == "DP-THUE-DEMO")
        assert int(rent["remaining_amount"]) == 60_000_000, rent
        assert any(r.get("promise_date") or r.get("promised_date") for r in plan["collections"])
        passed("T1/T5/T6: 13-week forecast, partial rent only 60m, promise information")
        evidence = call("get", "/v1/forecasts/"+plan["id"]+"/explanations")
        assert evidence["t10"]["replay"]
        supported = [r for r in plan["collections"] if r.get("payment_explanation",{}).get("status") in ("ok", "available")]
        # Record the real explanation statuses; do not promise support where absent.
        report["explanation_statuses"] = sorted({r.get("payment_explanation",{}).get("status", "missing") for r in plan["collections"]})
        invoices = plan["cash_decomposition"]["invoices"]
        totals = {}
        for r in invoices:
            cid = r["customer_id"]
            totals[cid] = totals.get(cid, 0) + float(r.get("outstanding", r.get("amount",0)))
        customer = max(totals, key=totals.get)
        scenario = call("post", "/v1/forecasts/"+plan["id"]+"/scenarios", json=dict(customer_id=customer, customer_delay_weeks=2))
        shifted = call("post", "/v1/forecasts/"+plan["id"]+"/scenarios", json=dict(expense_id="DP-DEBT", expense_delay_weeks=2))
        assert len(scenario["weeks"]) == len(shifted["weeks"]) == 13
        passed("T10: explanation evidence, customer delay and expense shift replays")
        response = client.get("/v1/forecasts/"+plan["id"]+"/xlsx")
        response.raise_for_status()
        workbook = load_workbook(io.BytesIO(response.content), read_only=True, data_only=True)
        report["excel_sheets"] = workbook.sheetnames
        assert len(workbook.sheetnames) >= 6
        workbook.close()
        (rehearsal / "Ke-hoach-Dai-Phat.xlsx").write_bytes(response.content)
        passed("Excel export opens successfully")
        historical = call("post", "/v1/predict", json={**prediction, "cutoff":"2026-07-31", "opening_balance":540_000_000.0, "confirmed_weeks":[]})
        comparison = call("get", "/v1/forecasts/"+historical["id"]+"/actuals", params=dict(asof=manifest["cutoff"],payments_complete="true"))
        assert comparison["covered_weeks"] > 0 and comparison["prospective"] is False
        passed("Historical actuals comparison works and is marked retrospective")
        report.update(forecast_id=plan["id"], customer_for_scenario=customer,
            baseline_any_shortfall=plan.get("any_below_floor_probability"),
            scenario_delta=scenario["delta_any_shortfall_probability"], covered_historical_weeks=comparison["covered_weeks"],
            rehearsal=str(rehearsal), presentation_store_untouched=True, status="passed")
    (pack / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding="utf-8")
    (rehearsal / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
