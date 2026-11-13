"""Freeze Workspace T1 training and T6, then diagnose four mature origins.

Run from the repository root. Train T1 independently at each historical origin;
do not activate models, synthesize missing schedules, or tune T6 on the outcomes.
"""

import argparse
import csv
import hashlib
import importlib
from importlib.metadata import version
import json
import os
import pickle
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from agent1.adaptive.cash_history import evaluate_plan, weekly_cash
from agent1.adaptive.data import account_scope, fingerprint, parse_rows
from agent1.adaptive.data import suggested_mapping, validate_dataset
from experiments.t1_compact.historical_workspace import SOURCE as HISTORICAL_SOURCE, forecast, train

PROTOCOL = "workspace-trained-t1-t6-baseline-v2"
KINDS = ("invoices", "bank", "payments", "statements", "outflows", "actions")
CUTOFFS = ("2025-09-30", "2025-12-31", "2026-04-30", "2026-07-31")
HORIZON = 13


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    if not rows:
        raise ValueError("No measured rows")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def freeze_runtime(output, data_dir):
    """Copy a consistent local source/input snapshot without touching live files."""
    frozen = output / "runtime_source"
    inputs = output / "inputs"
    for attempt in range(3):
        paths = sorted([p for package in (
                            "agent1", "agent1_service", "experiments/t1_compact",
                            "outputs/t1/global_local_families_20261113/source_snapshot/agent1/adaptive",
                        )
                        for p in ROOT.joinpath(package).rglob("*")
                        if p.is_file() and p.suffix in {".py", ".json"}]
                       + [Path(__file__)])
        paths += [data_dir / f"{i:02}_{kind}.csv" for i, kind in enumerate(KINDS, 1)]
        paths += [data_dir / "manifest.json"]
        entries = []
        for path in paths:
            content = path.read_bytes()
            target = inputs / path.name if path.parent == data_dir else frozen / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            entries.append(dict(original=str(path.resolve()), snapshot=str(target.resolve()),
                                sha256=hashlib.sha256(content).hexdigest()))
        if all(sha256(Path(item["original"])) == item["sha256"] for item in entries):
            write_json(output / "snapshot.json", dict(source_root=str(ROOT), attempts=attempt + 1, files=entries))
            return frozen / "scripts/business" / Path(__file__).name, inputs
    raise ValueError("Live files kept changing during source capture; snapshot was not run")


def load_demo(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("synthetic") is not True:
        raise ValueError("This diagnostic runner is restricted to the synthetic demo")
    data, inventory = {}, {}
    for index, kind in enumerate(KINDS, 1):
        path = folder / f"{index:02}_{kind}.csv"
        raw = pd.read_csv(path, dtype=str)
        rows, errors, warnings = parse_rows(raw, kind, suggested_mapping(raw.columns, kind), date_format="%Y-%m-%d", number_format="plain")
        if errors:
            raise ValueError(f"{kind}: {errors[:2]}")
        if len(rows) != manifest["counts"][kind]:
            raise ValueError(f"Manifest count mismatch: {kind}")
        data[kind] = rows
        inventory[kind] = dict(path=str(path.resolve()), sha256=sha256(path), rows=len(rows), warnings=warnings)
    validate_dataset(data)
    inventory["manifest"] = dict(path=str((folder / "manifest.json").resolve()), sha256=sha256(folder / "manifest.json"))
    return data, inventory


def knowledge_snapshot(data, cutoff):
    # This runner handles the six flat demo tables, not live record histories.
    return {kind: [r for r in data.get(kind, []) if r["known_at"] <= cutoff] for kind in KINDS}


def opening_balance(data, cutoff, accounts):
    total = 0
    for account in accounts:
        statements = [r for r in data["statements"] if r["account"] == account and r["end_date"] == cutoff and r["known_at"] <= cutoff]
        if len(statements) != 1:
            raise ValueError(f"Need one certified closing statement at {cutoff} for {account}")
        total += statements[0]["closing_balance"]
    if not accounts:
        raise ValueError("No reconciled bank account at the origin")
    return total


def validate_origins(cutoffs, truth_asof):
    if not cutoffs or list(cutoffs) != sorted(set(cutoffs)):
        raise ValueError("Origins must be unique and ordered")
    last_end = None
    for cutoff in cutoffs:
        start = date.fromisoformat(cutoff)
        end = start + timedelta(weeks=HORIZON)
        if end > date.fromisoformat(truth_asof):
            raise ValueError(f"Immature 13-week origin: {cutoff}")
        if last_end is not None and start < last_end:
            raise ValueError("Diagnostic origins must not overlap")
        last_end = end


def fit_origin_t1(origin_data, cutoff, mode, progress):
    if mode == "history":
        return None
    bundle = train(origin_data, cutoff, progress=progress)
    if bundle["asof"] != cutoff:
        raise ValueError("T1 must be trained at the historical cutoff")
    return bundle


def training_config():
    return dict(methods="all default CATALOG candidates", neural_max_iter=int(os.environ.get("AGENT1_NEURAL_MAX_ITER", "100")), neural_batch_size=int(os.environ.get("AGENT1_NEURAL_BATCH_SIZE", "128")), thread_limit=2)


def training_code_hash():
    names = ("methods.py", "data.py", "operating.py", "cash_history.py", "new_credit.py", "risk.py", "collections.py", "collection_explanations.py", "cash_explanations.py")
    return hashlib.sha256(b"".join((HISTORICAL_SOURCE / name).read_bytes() for name in names)).hexdigest()


def cached_t1(output, cutoff, origin_data):
    path = output / "models" / f"{cutoff}.pkl"
    metadata = path.with_suffix(".json")
    if not path.exists() or not metadata.exists():
        return None
    details = json.loads(metadata.read_text(encoding="utf-8"))
    if details.get("training_config") != training_config() or details.get("artifact_sha256") != sha256(path):
        return None
    # Only this runner's locally generated, hash-checked checkpoint is reused.
    bundle = pickle.loads(path.read_bytes())
    if bundle["asof"] != cutoff or bundle["dataset_hash"] != fingerprint(origin_data) or bundle["code_hash"] != training_code_hash():
        return None
    if bundle["dependencies"] != {name: version(name) for name in bundle["dependencies"]}:
        return None
    return bundle


def cash_equivalent(left, right):
    """Compare money/probabilities; threaded tree sums may differ by roundoff.

    SHAP presentation/reference hashes are outside this T6 cash check. A genuine
    cash difference of one VND is rejected; the tolerance is one hundredth VND.
    """
    for key in ("cutoff", "mode", "horizon_weeks", "opening_balance", "open_invoices", "outstanding", "unknown_outflow_weeks", "alerts"):
        if left.get(key) != right.get(key):
            return False
    if len(left.get("weeks", [])) != len(right.get("weeks", [])):
        return False
    for a, b in zip(left.get("weeks", []), right.get("weeks", [])):
        for key in ("week", "date", "outflow_status"):
            if a.get(key) != b.get(key):
                return False
        for key in ("cash_in", "cash_out", "balance", "low", "high", "new_credit_in", "obligation_in"):
            if not np.isclose(a.get(key, 0), b.get(key, 0), rtol=0, atol=0.01):
                return False
        if not np.isclose(a.get("below_floor_probability", 0), b.get("below_floor_probability", 0), rtol=0, atol=1e-12):
            return False
    a_inv = {r["invoice_id"]: r for r in left.get("cash_decomposition", {}).get("invoices", [])}
    b_inv = {r["invoice_id"]: r for r in right.get("cash_decomposition", {}).get("invoices", [])}
    if a_inv.keys() != b_inv.keys():
        return False
    for key in a_inv:
        if not np.allclose(a_inv[key]["expected_by_week"], b_inv[key]["expected_by_week"], rtol=0, atol=0.01):
            return False
    a_prob = {r["invoice_id"]: r["payment_probability_4w"] for r in left.get("collections", [])}
    b_prob = {r["invoice_id"]: r["payment_probability_4w"] for r in right.get("collections", [])}
    return a_prob.keys() == b_prob.keys() and all(np.isclose(a_prob[k], b_prob[k], rtol=0, atol=1e-12) for k in a_prob)


def forecast_pair(data, origin_data, cutoff, balance, bundle, mode, cash_floor):
    if mode == "workspace" and bundle is None:
        raise ValueError("Workspace T1 baseline requires a trained bundle")
    options = dict(bundle=bundle, cash_floor=cash_floor, horizon_weeks=HORIZON)
    plan = forecast(data, cutoff, balance, **options)
    replay = forecast(origin_data, cutoff, balance, **options)
    if not cash_equivalent(plan, replay):
        raise ValueError(f"Future-record removal changed the forecast: {cutoff}")
    if mode == "workspace" and plan["mode"] != "company_trained":
        raise ValueError("Forecast did not use the trained Workspace T1 path")
    return plan


def model_details(bundle):
    if bundle is None:
        return dict(mode="history_baseline", trained=False)
    model = bundle["model"]
    members = getattr(model, "members", [model])
    return dict(mode="company_trained", trained=True, asof=bundle["asof"],
                selected_method=bundle["selected_method"],
                selected_weight=bundle["selected_weight"], serving_weight=bundle["weight"],
                serving_members=[m.variant for m in members],
                train_n=bundle["train_n"], validation_n=bundle["validation_n"],
                audit=bundle["audit"], windows=bundle["windows"],
                selection=bundle["selection"], dependencies=bundle["dependencies"],
                code_hash=bundle["code_hash"])


def score_rows(rows):
    truth = np.asarray([r["actual_balance"] for r in rows], float)
    prediction = np.asarray([r["predicted_balance"] for r in rows], float)
    low = np.asarray([r["p10"] for r in rows], float)
    high = np.asarray([r["p90"] for r in rows], float)
    probability = np.asarray([r["below_floor_probability"] for r in rows], float)
    actual = np.asarray([r["shortfall"] for r in rows], bool)
    alert = np.asarray([r["alert"] for r in rows], bool)
    if not len(rows) or not np.isfinite(np.r_[truth, prediction, low, high, probability]).all():
        raise ValueError("Metrics require complete finite outcomes")
    if np.any(low > high) or np.any((probability < 0) | (probability > 1)):
        raise ValueError("Invalid forecast interval or probability")
    hits = int((actual & alert).sum())
    return dict(
        weeks=len(rows), mae_balance_vnd=float(np.abs(prediction - truth).mean()),
        bias_balance_vnd=float((prediction - truth).mean()),
        coverage80=float(((low <= truth) & (truth <= high)).mean()),
        mean_width80_vnd=float((high - low).mean()),
        interval_score80_vnd=float(((high - low) + 10 * np.maximum(low - truth, 0) + 10 * np.maximum(truth - high, 0)).mean()),
        brier_weekly_shortfall=float(np.square(probability - actual).mean()),
        actual_shortfall_weeks=int(actual.sum()), alert_weeks=int(alert.sum()),
        true_alert_weeks=hits, false_alert_weeks=int((alert & ~actual).sum()),
        missed_shortfall_weeks=int((~alert & actual).sum()),
        recall_weekly=hits / int(actual.sum()) if actual.any() else None,
        precision_weekly=hits / int(alert.sum()) if alert.any() else None,
        mae_cumulative_opening_ar_vnd=float(np.mean([abs(r["cumulative_ar_error"]) for r in rows])),
        mae_weekly_opening_ar_vnd=float(np.mean([abs(r["predicted_in"] - r["actual_opening_ar_in"]) for r in rows])),
    )


def measured_rows(data, plan, truth_asof, accounts):
    actual = evaluate_plan(data, plan, truth_asof, accounts)
    if len(actual) != HORIZON or not all(r["covered"] and r["balance_available"] for r in actual):
        raise ValueError("Need reconciled bank coverage for all 13 outcome weeks")
    if plan["operating_included"] or plan["new_credit_included"] or any(w["cash_out"] or w.get("obligation_in", 0) for w in plan["weeks"]):
        raise ValueError("Opening-AR scope bridge requires the locked demo fallback with no historical scheduled movements")
    cutoff = plan["cutoff"]
    opened = {r["invoice_id"] for r in plan["cash_decomposition"]["invoices"]}
    bank = {r["bank_id"]: r for r in data["bank"] if r["known_at"] <= truth_asof and r["account"] in accounts}
    invoices = {r["invoice_id"]: r for r in data["invoices"]}
    ar, new_ar = np.zeros(HORIZON), np.zeros(HORIZON)
    for payment in data["payments"]:
        txn = bank.get(payment.get("bank_id"))
        if payment["known_at"] > truth_asof or txn is None:
            continue
        delta = (date.fromisoformat(txn["date"]) - date.fromisoformat(cutoff)).days
        if not 1 <= delta <= HORIZON * 7:
            continue
        week = (delta - 1) // 7
        if payment["invoice_id"] in opened:
            ar[week] += payment["amount"]
        elif invoices[payment["invoice_id"]]["issue_date"] > cutoff:
            new_ar[week] += payment["amount"]
    cash = weekly_cash(data, str(date.fromisoformat(cutoff) + timedelta(days=1)), HORIZON, truth_asof, accounts)
    cumulative_ar_error, scope_effect, rows = 0.0, 0.0, []
    for i, (prediction, outcome) in enumerate(zip(plan["weeks"], actual)):
        other_in = outcome["actual_in"] - ar[i]
        if other_in < -0.01:
            raise ValueError("Opening-AR allocations exceed bank cash")
        cumulative_ar_error += prediction["cash_in"] - ar[i]
        scope_effect += outcome["actual_out"] - other_in
        error = prediction["balance"] - outcome["actual_balance"]
        if not np.isclose(error, cumulative_ar_error + scope_effect, rtol=1e-12, atol=0.01):
            raise ValueError("Bank/AR error bridge does not reconcile")
        rows.append(dict(
            cutoff=cutoff, week=i + 1, date=prediction["date"],
            opening_balance=plan["opening_balance"], predicted_in=prediction["cash_in"],
            predicted_out=prediction["cash_out"], predicted_balance=prediction["balance"],
            p10=prediction["low"], p90=prediction["high"],
            below_floor_probability=prediction["below_floor_probability"],
            actual_in=outcome["actual_in"], actual_out=outcome["actual_out"],
            actual_balance=outcome["actual_balance"], balance_error=error,
            absolute_balance_error=abs(error), interval_hit=outcome["interval_hit"],
            cash_floor=plan["cash_floor"], alert=outcome["alert"], shortfall=outcome["shortfall"],
            actual_opening_ar_in=float(ar[i]), actual_new_invoice_in=float(new_ar[i]),
            actual_cash_sales_in=float(cash[i, 2]),
            actual_other_unmodelled_in=float(other_in - new_ar[i] - cash[i, 2]),
            cumulative_ar_error=float(cumulative_ar_error), cumulative_scope_effect=float(scope_effect),
            outflow_status=prediction["outflow_status"],
        ))
    return rows


def report(summary, rows, output):
    def millions(v):
        return f"{v / 1e6:,.2f}"

    trained = summary["t1_mode"] == "workspace"
    lines = [
        "# Mốc ban đầu T6 Workspace · 12/11/2026", "",
        "Chẩn đoán hồi cứu trên Đại Phát, dữ liệu 100% synthetic. Giữ nguyên thuật toán và cấu hình mặc định; không kích hoạt model, không chỉnh ngưỡng cảnh báo hoặc khoảng dự báo.", "",
        "## Phạm vi đã chạy", "",
        ("- T1 Workspace lịch sử được chạy từ snapshot qua `experiments.t1_compact.historical_workspace.train()`, toàn bộ danh mục cũ, chọn trên validation, audit độc lập và refit đến ngày chốt. Không dùng pipeline T1 global → local hiện tại. Truyền `bundle` thực vào `forecast()`; kiểm tra kết quả mang mode `company_trained`."
         if trained else "- Đây chỉ là đối chứng dự phòng `history_baseline`, `bundle=None`; không đánh giá model T1 đã học."),
        "- T6 giữ 400 đường mô phỏng độc lập, seed 7 và kỳ 13 tuần.",
        "- Không bật ước lượng hoạt động hoặc hóa đơn bán chịu mới; không thêm lịch chi từ kết quả tương lai.",
        "- Số dư đầu mỗi mốc lấy từ sao kê đã chốt và đã biết tại đúng ngày đó. Ngưỡng tiền 200 triệu VND giữ theo cấu hình demo.",
        "- Bốn gốc không chồng lấn được chọn trước khi chấm. Mỗi tuần kết quả có đủ sao kê; nhãn cuối được đọc tại 31/10/2026.",
        "- Đã đối chiếu dòng tiền khi truyền toàn bộ dữ liệu với khi loại các bản ghi biết sau ngày chốt: dung sai tiền 0,01 VND, xác suất 1e-12. Không so hash/nội dung SHAP vì tổng xác suất cây chạy nhiều luồng có sai khác làm tròn. Không dùng kế hoạch hồi cứu làm dữ liệu hiệu chỉnh prospective.", "",
        "## Kết quả theo ngày chốt", "",
        "Đơn vị tiền trong bảng: triệu VND. MAE và độ phủ tính trên 13 số dư cuối tuần.", "",
        "| Ngày chốt | Số dư đầu | MAE số dư | Độ phủ P10–P90 | Độ rộng TB | MAE thu AR lũy kế | Báo giả / bỏ sót (tuần) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for origin in summary["origins"]:
        m = origin["metrics"]
        lines.append(f"| {origin['cutoff']} | {millions(origin['opening_balance'])} | {millions(m['mae_balance_vnd'])} | {m['coverage80']:.1%} | {millions(m['mean_width80_vnd'])} | {millions(m['mae_cumulative_opening_ar_vnd'])} | {m['false_alert_weeks']} / {m['missed_shortfall_weeks']} |")
    m = summary["overall"]
    lines += ["", "## Gộp 52 tuần dự báo", "",
        f"- MAE số dư: **{millions(m['mae_balance_vnd'])} triệu VND**; bias (dự báo trừ thực tế): **{millions(m['bias_balance_vnd'])} triệu VND**.",
        f"- Độ phủ P10–P90: **{m['coverage80']:.1%}**; độ rộng trung bình: **{millions(m['mean_width80_vnd'])} triệu VND**; interval score 80%: **{millions(m['interval_score80_vnd'])} triệu VND** (nhỏ hơn tốt hơn).",
        f"- MAE thu từ công nợ mở: **{millions(m['mae_weekly_opening_ar_vnd'])} triệu/tuần**, **{millions(m['mae_cumulative_opening_ar_vnd'])} triệu lũy kế**.",
        f"- Tuần dưới ngưỡng tiền thực tế: **{m['actual_shortfall_weeks']}**; tuần cảnh báo: **{m['alert_weeks']}**; báo giả: **{m['false_alert_weeks']}**; bỏ sót: **{m['missed_shortfall_weeks']}**.",
        f"- Brier xác suất xuống dưới ngưỡng từng tuần: **{m['brier_weekly_shortfall']:.6f}**. Đây không phải xác suất thiếu tiền ít nhất một lần trong cả kỳ.", "",
        "## Cách đọc sai số", "",
        "Bộ Đại Phát có đủ hóa đơn, thanh toán và sao kê quá khứ, nhưng 27 lịch chi chỉ được biết ngày 31/10/2026 và đến hạn sau đó. Cả bốn ngày chốt đều chưa có lịch chi; mọi tuần dự báo báo trạng thái chi chưa biết. Không xác nhận các tuần đó là không có chi.", "",
        "Nhánh mặc định chỉ dự thu công nợ mở. Sao kê thực tế còn có thu hóa đơn mới, bán thu ngay, chi biến đổi và khoản chi cuối tháng của máy phát. Vì vậy điểm số dư ngân hàng đầy đủ đo cả khoảng trống phạm vi, không được quy toàn bộ thành lỗi thuật toán T6 hoặc T1.", "",
        "Từng tuần có đẳng thức kiểm tra: `sai số số dư = sai số thu AR lũy kế + tác động phạm vi lũy kế`, trong đó `tác động phạm vi = tổng chi thực tế − tổng thu ngoài công nợ mở`. Không thay đổi dòng tiền thật để làm điểm đẹp hơn.", "",
        "MAE thu AR lũy kế tách riêng phần công nợ mở tại ngày chốt; đây là chẩn đoán sai số thu trong phạm vi hiện có, không phải điểm số dư đầy đủ đã sửa.", "",
        "## Giới hạn và việc tiếp theo", "",
        "- Một doanh nghiệp synthetic từ một máy phát; các tuần trong mỗi gốc có phụ thuộc. Không tính khoảng tin cậy từ 52 tuần như 52 quan sát độc lập.",
        ("- Đây là T1 học lại đúng quy trình Workspace tại từng gốc, không lấy model học sau ngày chốt để chấm ngược quá khứ; không phải competing-risks V6. Nếu audit từ chối hoặc chọn tỷ trọng 0, giữ nguyên chính sách dự phòng của Workspace và ghi rõ trong bảng T1."
         if trained else "- Đây là nhánh dự phòng, không phải baseline của T1 đã học nối vào T6."),
        "- Khoảng dự báo thô, không hiệu chỉnh. Không có chuỗi kế hoạch prospective đủ điều kiện để dùng bộ hiệu chỉnh hiện hành.",
        "- Đối chiếu phần phạm vi thu/chi trước khi lựa chọn thay đổi thuật toán. Giữ bộ điểm này để so sánh cùng giao thức sau mỗi sửa đổi.",
        "- Các World v4/v6 còn config/manifest nhưng không còn Parquet ở lần kiểm tra này; không tái sinh hoặc thay dữ liệu để giả thành lần chạy lại nghiên cứu cũ.",
    ]
    if not m["actual_shortfall_weeks"]:
        lines += ["- Không có tuần thiếu tiền theo ngưỡng đã chọn: recall để trống, chưa đánh giá được khả năng phát hiện thiếu hụt. Không đổi ngưỡng sau khi xem kết quả để tạo sự kiện."]
    if trained:
        lines += ["", "## T1 thực sự đưa vào T6", "",
                  "Tỷ trọng là phần của model được chọn, phần còn lại là mốc lịch sử khách theo đúng cơ chế Workspace.", "",
                  "| Ngày chốt | Ứng viên chọn | Tỷ trọng phục vụ | Audit Brier 4 tuần | Mốc lịch sử | Audit chấp nhận |",
                  "|---|---|---:|---:|---:|---|" ]
        for origin in summary["origins"]:
            t1 = origin["t1"]
            audit = t1["audit"]
            lines.append(f"| {origin['cutoff']} | {t1['selected_method']} | {t1['serving_weight']:.2f} | {audit['candidate_brier4']:.6f} | {audit['baseline_brier4']:.6f} | {audit['accepted']} |")
    lines += ["", "## Tệp và tái lập", "",
        "- `weekly.csv`: 52 tuần dự báo, thực tế và phân rã sai số.",
        "- `metrics.csv`: điểm toàn kỳ, tuần 1–4 và tuần 5–13, gộp và theo gốc.",
        "- `summary.json`: điểm tổng và chi tiết từng ngày chốt.",
        "- `protocol.json`: cấu hình khóa, hash dữ liệu và mã nguồn, phiên bản thư viện.",
        "- `plans/`: nguyên kết quả dự báo từ hàm phục vụ hiện có.",
        "- `models/`: bundle T1 và hồ sơ chọn model/audit từng ngày chốt (chỉ có ở chế độ Workspace).",
        "- `runtime_source/`, `inputs/`, `snapshot.json`: mã nguồn và dữ liệu cố định dùng riêng cho lần đo; không phụ thuộc các sửa đổi đồng thời ở workspace.", "",
        "```powershell", ".\\.venv\\Scripts\\python.exe -X utf8 agent1/scripts/business/backtest_t6_baseline.py" + (" --t1-mode history" if not trained else ""), "```", "",
    ]
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "pilot/demo_dai_phat")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--t1-mode", choices=("workspace", "history"), default="workspace")
    parser.add_argument("--cutoffs", nargs="+", default=list(CUTOFFS))
    parser.add_argument("--frozen-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.output is None:
        name = "baseline_workspace_trained_t1_20261112" if args.t1_mode == "workspace" else "baseline_workspace_history_reference_20261112"
        args.output = ROOT / "outputs/t6" / name
    if not args.frozen_runtime:
        if args.t1_mode == "workspace":
            import psutil
            if psutil.virtual_memory().available < 3 * 1024**3:
                raise ValueError("Workspace training requires at least 3 GiB available RAM")
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        script, inputs = freeze_runtime(output, args.data_dir.resolve())
        print("Captured isolated source and data snapshot; running unchanged forecast code", flush=True)
        result = subprocess.run([sys.executable, "-X", "utf8", str(script),
                                 "--frozen-runtime", "--data-dir", str(inputs),
                                 "--output", str(output), "--t1-mode", args.t1_mode,
                                 "--cutoffs", *args.cutoffs], check=False)
        if result.returncode:
            raise SystemExit(result.returncode)
        return
    importlib.import_module("agent1.adaptive.obligations")
    print("Frozen runtime and calendar resources verified", flush=True)
    started = time.perf_counter()
    data, inventory = load_demo(args.data_dir)
    truth_asof = max(r["known_at"] for r in data["statements"])
    validate_origins(args.cutoffs, truth_asof)
    sources = list((ROOT / "agent1/adaptive").glob("*.py")) + [Path(__file__)]
    source_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in sources}
    protocol = dict(
        protocol=PROTOCOL, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        synthetic=True, t1_mode=args.t1_mode, model_mode="company_trained" if args.t1_mode == "workspace" else "history_baseline",
        model_training=args.t1_mode == "workspace", trained_t1_required=args.t1_mode == "workspace",
        training_config=training_config(),
        future_removal_check=dict(target="weekly cash, per-invoice cash contributions and T1 four-week probabilities", money_atol_vnd=0.01, probability_atol=1e-12),
        horizon_weeks=HORIZON, cutoffs=args.cutoffs, truth_asof=truth_asof,
        cash_floor=200_000_000, simulations=400, forecast_seed=7,
        timing_dependence="independent", operating_included=False,
        confirmed_outflow_weeks=[], calibration="none",
        selection="Fixed month-end origins before scoring; non-overlapping outcome windows",
        full_data_hash=fingerprint(data), input_files=inventory, source_hashes=source_hashes,
        python=sys.version, dependencies={"numpy": np.__version__, "pandas": pd.__version__},
        limitations=["one synthetic company", "missing historical expense schedules", "no operating/new-credit forecasts", "retrospective, not prospective", "not a product gate or real-world validation"],
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "protocol.json", protocol)
    all_rows, origins = [], []
    with threadpool_limits(limits=2):
        for cutoff in args.cutoffs:
            print(f"Forecast {cutoff}: starting", flush=True)
            origin_data = knowledge_snapshot(data, cutoff)
            accounts = account_scope(origin_data, cutoff)
            balance = opening_balance(origin_data, cutoff, accounts)
            tick = time.perf_counter()
            bundle = cached_t1(output, cutoff, origin_data) if args.t1_mode == "workspace" else None
            reused = bundle is not None
            if reused:
                print(f"T1 {cutoff}: reusing hash-verified training checkpoint", flush=True)
            else:
                bundle = fit_origin_t1(origin_data, cutoff, args.t1_mode, lambda message: print(f"T1 {cutoff}: {message}", flush=True))
            t1 = model_details(bundle)
            t1["training_seconds"] = round(time.perf_counter() - tick, 3)
            t1["training_config"] = training_config()
            t1["reused_checkpoint"] = reused
            if reused:
                previous = json.loads((output / "models" / f"{cutoff}.json").read_text(encoding="utf-8"))
                t1["training_seconds"] = previous["training_seconds"]
            if bundle is not None:
                model_path = output / "models" / f"{cutoff}.pkl"
                model_path.parent.mkdir(parents=True, exist_ok=True)
                model_path.write_bytes(pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL))
                t1["artifact_sha256"] = sha256(model_path)
                write_json(model_path.with_suffix(".json"), t1)
                print(f"T1 {cutoff}: selected={t1['selected_method']}, serving_weight={t1['serving_weight']}, audit_accepted={t1['audit']['accepted']}", flush=True)
            tick = time.perf_counter()
            plan = forecast_pair(data, origin_data, cutoff, balance, bundle, args.t1_mode, protocol["cash_floor"])
            rows = measured_rows(data, plan, truth_asof, accounts)
            metrics = score_rows(rows)
            horizon_end = str(date.fromisoformat(cutoff) + timedelta(weeks=HORIZON))
            origins.append(dict(cutoff=cutoff, horizon_end=horizon_end, opening_balance=balance,
                accounts=accounts, open_invoices=plan["open_invoices"], outstanding=plan["outstanding"],
                origin_data_hash=fingerprint(origin_data), future_removal_invariance=True,
                t1=t1,
                unknown_outflow_weeks=plan["unknown_outflow_weeks"],
                forecast_and_replay_seconds=round(time.perf_counter() - tick, 3), metrics=metrics))
            write_json(output / "plans" / f"{cutoff}.json", dict(plan=plan, origin=origins[-1]))
            all_rows.extend(rows)
            print(f"Forecast {cutoff}: 13/13 covered, MAE={metrics['mae_balance_vnd']:,.0f} VND, coverage={metrics['coverage80']:.1%}", flush=True)
    for path in sources:
        if sha256(path) != source_hashes[str(path.relative_to(ROOT))]:
            raise ValueError(f"Code changed during measurement: {path}")
    for item in inventory.values():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Input changed during measurement: {item['path']}")
    groups = [("all", all_rows)] + [(origin["cutoff"], [r for r in all_rows if r["cutoff"] == origin["cutoff"]]) for origin in origins]
    metrics = []
    for cutoff, group in groups:
        for horizon, subset in (("w1-13", group), ("w1-4", [r for r in group if r["week"] <= 4]), ("w5-13", [r for r in group if r["week"] >= 5])):
            metrics.append(dict(cutoff=cutoff, horizon=horizon, **score_rows(subset)))
    summary = dict(protocol=PROTOCOL, t1_mode=args.t1_mode, cutoffs=args.cutoffs, origins=origins, overall=score_rows(all_rows), elapsed_seconds=round(time.perf_counter() - started, 3))
    write_csv(output / "weekly.csv", all_rows)
    write_csv(output / "metrics.csv", metrics)
    write_json(output / "summary.json", summary)
    report(summary, all_rows, output)
    protocol.update(status="complete", elapsed_seconds=summary["elapsed_seconds"], results={p.name: sha256(p) for p in output.iterdir() if p.is_file() and p.name != "protocol.json"})
    write_json(output / "protocol.json", protocol)
    print(json.dumps(dict(output=str(output), overall=summary["overall"], elapsed_seconds=summary["elapsed_seconds"]), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
