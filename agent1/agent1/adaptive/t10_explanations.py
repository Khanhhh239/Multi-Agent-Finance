"""T10 reads engine evidence; paired scenarios replay the frozen serving bundle.

No language model calculates money or infers collection intervention effects.
Snapshots are internal encrypted store records, never client-supplied pickles.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import pickle
import platform

import numpy as np

PROTOCOL = "t10-settlement-partial-evidence-v1"
T6_VERSION = "settlement-partial-paths-v2"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _engine_sources():
    root = Path(__file__).resolve().parents[1]
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*.py"))}


def engine_identity():
    """Fail closed on source/runtime drift; never replay with today's other engine."""
    sources = {name: hashlib.sha256(value).hexdigest() for name, value in _engine_sources().items()}
    runtime = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "lightgbm", "xgboost", "torch", "scipy", "scikit-learn"):
        try:
            runtime[name] = version(name)
        except PackageNotFoundError:
            runtime[name] = None
    return dict(version=T6_VERSION, source_sha256=digest(sources), runtime=runtime)


def archive_engine(identity):
    """Retain exact source once per version, alongside pinned runtime versions."""
    sources = _engine_sources()
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in sources.items()}
    if digest(hashes) != identity["source_sha256"]:
        raise ValueError("Source engine thay đổi trong lúc tạo dự báo")
    return dict(id=identity["source_sha256"], identity=identity,
                sources={name: base64.b64encode(value).decode() for name, value in sources.items()})


def bundle_identity(bundle):
    try:
        models = pickle.dumps((bundle["weight"], bundle["model"], bundle["anchor"]), protocol=4)
    except (AttributeError, TypeError, pickle.PicklingError) as exc:
        raise ValueError("T1 cần artifact có thể lưu và phát lại để giải thích đúng phiên bản") from exc
    return dict(t1_version=bundle.get("t1_version") or "t1:" + hashlib.sha256(models).hexdigest(),
                t1_sha256=hashlib.sha256(models).hexdigest(),
                adapter_version=bundle["partial"].version, partial_version=bundle["partial"].digest,
                t6=engine_identity())


def attach_evidence(plan, opened, trace, probabilities, partial, bundle, *, invoice_shifts):
    """Attach the exact adapter arithmetic, including state-dependent partial support."""
    horizon = len(plan["weeks"])
    positions = {str(iid): i for i, iid in enumerate(opened.invoice_id)}
    profile = partial.record()
    profile["mean_ratios"] = partial.means.tolist()
    profile["cell_definitions"] = [dict(cell=cell, received_cash_state=bool(cell % 2),
        overdue_days_band=("<=0", "1..90", ">=91")[cell // 2]) for cell in range(6)]
    identity = bundle_identity(bundle)
    for row in plan["cash_decomposition"]["invoices"]:
        i = positions[row["invoice_id"]]
        amount, shift = row["outstanding"], int(invoice_shifts[i])
        weeks, remaining = [], amount
        for week in range(horizon):
            source = week - shift
            before = remaining
            if source >= 0:
                full = float(amount * trace["settlement"][i, source])
                piece = float(amount * trace["partial"][i, source])
                h = float(trace["hazard"][i, source])
                states = [dict(cell=int(trace["cells"][i, source, s]),
                               received_cash_state=bool(s),
                               expected_opening_debt=float(amount * trace["state_debt"][i, source, s]))
                          for s in (0, 1)]
                p = float(probabilities[i, source])
            else:
                full = piece = h = p = 0.0
                states = []
            total = full + piece
            if not np.isclose(total, row["expected_by_week"][week], rtol=1e-12, atol=1e-6):
                raise ValueError("Bằng chứng adapter không khớp tiền đã dự báo")
            remaining = max(0.0, before - total)
            weeks.append(dict(week=week + 1, source_week=source + 1 if source >= 0 else None,
                              expected_opening_debt=before, settlement_probability=p,
                              settlement_hazard=h, expected_from_settlement=full,
                              expected_from_partial=piece, expected_receipt=total,
                              expected_remaining_debt=remaining, partial_states=states))
        row["receipt_explanation"] = dict(
            target="expected_invoice_receipt_by_week", units="VND", status="verified",
            shift_weeks=shift, t1_settlement_distribution=probabilities[i].tolist(),
            t1_tail_probability=float(probabilities[i, -1]), weeks=weeks,
            source="active_t1_and_partial_adapter", partial_profile_ref="t10.partial_profile",
            formula="settlement = sum(state_debt) * hazard; partial = sum(state_debt * (1-hazard) * q[cell] * mean_ratio[cell])",
        )
    cells = profile.get("evidence", {}).get("cells", [])
    plan["t10"] = dict(
        protocol=PROTOCOL, identity=identity, partial_profile=profile,
        provenance=dict(model_asof=bundle["asof"], serving_manifest=bundle.get("serving_manifest")),
        partial_support_status="recorded_training_evidence" if len(cells) == 6 else "support_not_recorded",
        targets=dict(settlement="payment_probability_4w", receipts="expected_invoice_receipt_by_week",
                     accounting="expected_balance", sensitivity="paired_t6_balance_and_shortfall_probability"),
        feature_cash_attribution=dict(status="not_computed",
            reason="SHAP T1 chỉ giải thích xác suất tất toán 4 tuần. Ảnh hưởng feature lên tiền phải chấm cả T1 + adapter."),
        checks=dict(adapter_components_reconcile=True, accounting_reconciles=True),
        assumptions=[
            "Partial q là xác suất trả từng phần khi chưa tất toán trong tuần; tỷ lệ trả tính trên dư nợ còn lại.",
            "Dư nợ kỳ vọng là trung bình trên các trạng thái. Không nhân thêm xác suất tất toán vào tiền engine đã tính.",
            "Mức hỗ trợ partial gồm tuần quan sát, tuần hiệu dụng, số tuần partial và prior nguồn; không phải độ tin cậy đã hiệu chỉnh.",
            "Phân rã kế toán cộng khớp số dư kỳ vọng. P10/P50/P90 lấy từ đường tiền của toàn danh mục; không cộng phân vị từng hóa đơn.",
            "Kịch bản là độ nhạy trong mô hình. Không suy gọi điện hay biện pháp thu nợ chắc chắn tạo ra thay đổi đó.",
        ],
    )
    plan["t6_version"] = identity["t6"]


def _forecast_digest(plan):
    value = deepcopy(plan)
    value.get("t10", {}).pop("replay", None)
    return digest(value)


def freeze_replay(plan, data, bundle, kwargs):
    """One snapshot per forecast; caller commits snapshot and forecast atomically."""
    from .data import as_of
    if bundle_identity(bundle) != plan["t10"]["identity"]:
        raise ValueError("Bundle hoặc engine thay đổi trong lúc tạo forecast")
    artifact = pickle.dumps(bundle, protocol=4)
    snapshot = dict(id=plan["id"], protocol=PROTOCOL, data=as_of(deepcopy(data), plan["cutoff"]),
                    bundle=base64.b64encode(artifact).decode(),
                    bundle_sha256=hashlib.sha256(artifact).hexdigest(),
                    kwargs=deepcopy(kwargs), identity=deepcopy(plan["t10"]["identity"]),
                    forecast_sha256=_forecast_digest(plan))
    sha = digest(snapshot)
    snapshot["sha256"] = sha
    plan["t10"]["replay"] = dict(status="frozen", snapshot_sha256=sha,
                                  forecast_sha256=snapshot["forecast_sha256"],
                                  data_sha256=digest(snapshot["data"]),
                                  bundle_sha256=snapshot["bundle_sha256"])
    return snapshot


def replay_scenario(plan, snapshot, *, customer_id=None, customer_delay_weeks=0,
                    expense_id=None, expense_delay_weeks=0):
    """Replay baseline and scenario with identical invoice/operating draws."""
    from .methods import forecast

    if (type(customer_delay_weeks) is not int or not 0 <= customer_delay_weeks <= 13
            or type(expense_delay_weeks) is not int or not 0 <= expense_delay_weeks <= 52):
        raise ValueError("Số tuần kịch bản không hợp lệ")
    if not snapshot or not plan.get("t10", {}).get("replay"):
        raise ValueError("Kế hoạch cũ thiếu snapshot T10; không thể mô phỏng bằng phiên bản đang dùng thay thế")
    saved = deepcopy(snapshot)
    sha = saved.pop("sha256", None)
    if (digest(saved) != sha or sha != plan["t10"]["replay"]["snapshot_sha256"]
            or snapshot["id"] != plan["id"] or snapshot["forecast_sha256"] != _forecast_digest(plan)):
        raise ValueError("Snapshot hoặc forecast T10 đã thay đổi")
    if snapshot["identity"]["t6"] != engine_identity():
        raise ValueError("Phiên bản engine/runtime T6 đã thay đổi; cần môi trường đúng bản đã lưu để chạy kịch bản")
    # Internally produced, hash-verified artifact; the HTTP API accepts no pickle.
    artifact = base64.b64decode(snapshot["bundle"], validate=True)
    if hashlib.sha256(artifact).hexdigest() != snapshot["bundle_sha256"]:
        raise ValueError("Artifact bundle không khớp snapshot")
    bundle = pickle.loads(artifact)
    # Verify the stored artifact bytes, not a re-pickle of the loaded estimator:
    # numpy/booster object aliasing can change pickle bytes without changing T1.
    if (bundle["partial"].digest != snapshot["identity"]["partial_version"]
            or bundle["partial"].version != snapshot["identity"]["adapter_version"]
            or bundle.get("t1_version") is not None and bundle["t1_version"] != snapshot["identity"]["t1_version"]):
        raise ValueError("Phiên bản T1/adapter/partial không khớp snapshot")
    kwargs = dict(snapshot["kwargs"], shap_limit=0, return_paths=True)
    base = forecast(snapshot["data"], bundle=bundle, **kwargs)
    for original, repeated in zip(plan["weeks"], base["weeks"], strict=True):
        fields = ("cash_in", "cash_out", "expected_balance", "median_balance", "below_floor_probability")
        if (not np.allclose([original[f] for f in fields], [repeated[f] for f in fields], rtol=1e-12, atol=1e-6)
                or not np.allclose(list(original["balance_quantiles"].values()),
                                   list(repeated["balance_quantiles"].values()), rtol=1e-12, atol=1e-6)):
            raise ValueError("Phát lại T6 không khớp forecast đã lưu")
    if plan["any_below_floor_probability"] != base["any_below_floor_probability"]:
        raise ValueError("Phát lại xác suất thiếu tiền cả kỳ không khớp forecast đã lưu")
    customers = {r["customer_id"] for r in plan["cash_decomposition"]["invoices"]}
    if customer_id is not None and customer_id not in customers:
        raise ValueError("Khách không thuộc forecast đã lưu")
    expense_ids = {r["expense_id"] for r in plan["cash_decomposition"]["outflows"]}
    if expense_id is not None and expense_id not in expense_ids:
        raise ValueError("Khoản chi không thuộc forecast đã lưu")
    if expense_delay_weeks and not expense_id:
        raise ValueError("Cần chọn khoản chi để dời")
    extra = dict(kwargs.get("receipt_shifts") or {})
    for customer in sorted(customers if customer_id is None else {customer_id}):
        extra[customer] = extra.get(customer, 0) + customer_delay_weeks
    kwargs["receipt_shifts"] = extra
    shifts = dict(kwargs.get("expense_shifts") or {})
    if expense_id:
        shifts[expense_id] = shifts.get(expense_id, 0) + expense_delay_weeks
    kwargs["expense_shifts"] = shifts
    changed = forecast(snapshot["data"], bundle=bundle, **kwargs)
    x, y = np.asarray(base.pop("balance_paths")), np.asarray(changed.pop("balance_paths"))
    floor = plan["cash_floor"]
    event_diff = (y < floor).any(1).astype(float) - (x < floor).any(1)
    weeks = []
    for a, b in zip(base["weeks"], changed["weeks"], strict=True):
        delta = {key: b[key] - a[key] for key in ("expected_balance", "median_balance", "below_floor_probability")}
        delta["balance_quantiles"] = {q: b["balance_quantiles"][q] - a["balance_quantiles"][q]
                                      for q in ("0.1", "0.5", "0.9")}
        weeks.append(dict(week=a["week"], date=a["date"], baseline=a, scenario=b, delta=delta))
    return dict(protocol=PROTOCOL, forecast_id=plan["id"], snapshot_sha256=sha,
                identity=snapshot["identity"], target="paired_t6_balance_and_shortfall_probability",
                t10=dict(changed["t10"], identity=snapshot["identity"]),
                assumptions=dict(customer_id=customer_id, customer_delay_weeks=customer_delay_weeks,
                                 expense_id=expense_id, expense_delay_weeks=expense_delay_weeks,
                                 relative_to="saved_forecast", intervention_effect=False),
                random_numbers=dict(method="same_invoice_order_and_operating_draws", seed=kwargs["simulation_seed"],
                                    paths=kwargs["simulation_paths"], paired=True),
                band_status="raw_simulation", saved_band_status=plan["band_status"],
                baseline_any_shortfall_probability=base["any_below_floor_probability"],
                scenario_any_shortfall_probability=changed["any_below_floor_probability"],
                delta_any_shortfall_probability=float(event_diff.mean()),
                delta_probability_mc_standard_error=float(event_diff.std(ddof=1) / np.sqrt(len(event_diff))),
                weeks=weeks, scenario_cash_decomposition=changed["cash_decomposition"],
                outflows_pushed_beyond_horizon=changed["t5"]["outflows_pushed_beyond_horizon"],
                limitations=["So sánh dùng phân vị MC thô của toàn danh mục; không áp dải nới từ sai số quá khứ cho kịch bản chưa kiểm chứng.",
                             "Dịch toàn bộ chuỗi thu tương lai của khách; khoản ra ngoài kỳ vẫn là dư nợ, không coi là mất vốn.",
                             "Khoản chi bị dời ngoài kỳ vẫn là nghĩa vụ chưa thanh toán, không phải khoản chi đã được xóa.",
                             "Đây là giả định trong mô hình, không phải tác động nhân quả của việc gọi điện hoặc biện pháp thu nợ."])
