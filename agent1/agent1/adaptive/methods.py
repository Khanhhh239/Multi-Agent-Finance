"""T1 global/local entry point and T6 forecast serving. No scratch-local T1 bag."""

import numpy as np
import pandas as pd
from .data import observed, as_of, _payment_links, payment_target
from .cash_adapter import expected_cash_components, iter_cash_paths, VERSION as ADAPTER_VERSION


def train(data, asof, progress=lambda x: None, names=None, *, incumbent=None, catalog=None, policy=None):
    """Production T1 uses pretrained families only; no scratch-local ensemble."""
    from .t1_update import train_update

    if names is not None:
        raise ValueError("T1 mới chỉ chọn global Neural/LightGBM/XGBoost và các bản học tiếp; names của catalog local cũ không còn được dùng.")
    result = train_update(data, asof, progress, incumbent=incumbent, catalog=catalog, policy=policy)
    from .risk import train_risk

    progress("Đang kiểm định rủi ro và chính sách thu hồi độc lập với T1")
    result["risk"] = train_risk(data, pd.Timestamp(asof))
    # Ranking remains a separate policy. Do not backtest a freshly selected T1
    # on older origins or fit the removed customer/scratch-local T1 in triage.
    result["collection_policy"] = (incumbent or {}).get("collection_policy", "amount")
    result["collection_evaluation"] = (incumbent or {}).get("collection_evaluation", {"status": "fixed_amount_policy", "policy": "amount"})
    return result


def forecast(
    data,
    cutoff,
    balance,
    bundle=None,
    delay_days=0,
    expense_multiplier=1.0,
    confirmed_weeks=(),
    cash_floor=0.0,
    shared_customer_risk=False,
    delay_customer=None,
    include_operating=False,
    horizon_weeks=13,
    simulation_paths=1000,
    shap_limit=30,
    simulation_seed=7,
    return_paths=False,
    expense_shifts=None,
    receipt_shifts=None,
):
    if type(horizon_weeks) is not int or not 1 <= horizon_weeks <= 52:
        raise ValueError("Kỳ dự báo phải từ 1 đến 52 tuần.")
    if type(simulation_paths) is not int or not 100 <= simulation_paths <= 10000:
        raise ValueError("Số đường mô phỏng phải từ 100 đến 10000.")
    if type(shap_limit) is not int or not 0 <= shap_limit <= 30:
        raise ValueError("Số hóa đơn giải thích SHAP phải từ 0 đến 30.")
    if type(simulation_seed) is not int or not 0 <= simulation_seed < 2**32:
        raise ValueError("Seed mô phỏng không hợp lệ.")
    horizon = horizon_weeks
    # Keep four-week collections scores and short-term receipt cohorts comparable.
    receipt_horizon = max(13, horizon)
    clock = pd.Timestamp(cutoff)
    data = as_of(data, clock)
    frame = observed(data, clock)
    opened = frame[frame.remaining_amount > 0.01].copy()
    open_before_rules = len(opened)
    links = _payment_links([r for r in data.get("invoices", []) if r["issue_date"] <= cutoff and r["known_at"] <= cutoff])
    actions = sorted(
        (
            dict(r, invoice_id=payment_target(r["invoice_id"], links))
            for r in data.get("actions", [])
            if r["date"] <= cutoff and r["known_at"] <= cutoff
        ),
        key=lambda r: (r["date"], r["known_at"], r["event_id"]),
    )
    lost = {r["invoice_id"] for r in actions if r["kind"] == "write_off"}
    writeoff_excluded = int(opened.invoice_id.isin(lost).sum())
    opened = opened[~opened.invoice_id.isin(lost)]
    opened.attrs["cutoff"] = str(clock.date())
    if delay_days and delay_customer and delay_customer not in set(opened.customer_id):
        raise ValueError("Khách đã chọn không có hóa đơn đang mở tại ngày dự báo.")
    disputes = {}
    promises = {}
    deferred = {}
    resolved_promises = []
    ledger = frame.set_index("invoice_id")
    for event in actions:
        iid = event["invoice_id"]
        if event["kind"] in ("resolved", "dispute"):
            disputes[iid] = event["kind"] == "dispute"
        if event["kind"] in ("skip", "contact"):
            deferred[iid] = (clock - pd.Timestamp(event["date"])).days < 7
        if event["kind"] == "promise":
            promises[iid] = event["promise_date"]
            deadline = pd.Timestamp(event["promise_date"]) + pd.Timedelta(days=3)
            if deadline <= clock and iid in ledger.index:
                inv = ledger.loc[iid]
                if pd.isna(inv.settled) or inv.settled >= pd.Timestamp(event["date"]):
                    resolved_promises.append(
                        dict(
                            customer_id=inv.customer_id,
                            made_date=pd.Timestamp(event["date"]),
                            promised_date=pd.Timestamp(event["promise_date"]),
                            kept=bool(inv.settled <= deadline),
                        )
                    )
    reliability = {}
    if resolved_promises:
        from agent1.models.t8_promise import PromiseReliability

        reliability = (
            PromiseReliability()
            .fit(pd.DataFrame(resolved_promises), clock)
            .stats.reliability.to_dict()
        )
    # Descriptive drift signal; thresholds do not change the active model.
    paid = frame.dropna(subset=["settled"]).copy()
    recent = paid[paid.settled > clock - pd.Timedelta(days=28)]
    prior = paid[
        paid.settled.between(
            clock - pd.Timedelta(days=112), clock - pd.Timedelta(days=28)
        )
    ]
    shift_days = None
    if min(len(recent), len(prior)) >= 20:
        shift_days = float(
            (recent.settled - recent.due_date).dt.days.median()
            - (prior.settled - prior.due_date).dt.days.median()
        )
    if bundle is None:
        from .t1_catalog import GlobalCatalog
        bundle = GlobalCatalog().default_bundle(clock)
    if pd.Timestamp(bundle["asof"]) > clock:
        raise ValueError("Phiên bản học sau ngày dự báo")
    partial = bundle.get("partial")
    if partial is None or partial.version != ADAPTER_VERSION:
        raise ValueError("Bundle dự báo thiếu nhánh partial; cập nhật phiên bản T1 + adapter")
    if pd.Timestamp(partial.fitted_through) > clock:
        raise ValueError("Nhánh partial được học sau ngày dự báo")
    if bundle and any(getattr(bundle.get(key), "requires_ledger_context", False)
                      for key in ("model", "anchor")):
        from .compact_t1 import workspace_context

        opened.attrs["compact_context"] = workspace_context(data, clock)
    if opened.empty:
        p = np.zeros((0, receipt_horizon + 1))
        serving_components = []
    else:
        ages = (clock - opened.issue_date).dt.days.to_numpy()
        if bundle:
            serving_components = [
                (bundle["weight"], bundle["model"]),
                (1 - bundle["weight"], bundle["anchor"]),
            ]
            options = {"horizon": receipt_horizon} if receipt_horizon != 13 else {}
            p = bundle["weight"] * bundle["model"].distribution(
                opened, ages, **options
            ) + (1 - bundle["weight"]) * bundle["anchor"].distribution(
                opened, ages, **options
            )
    raw_payment_times = p.copy()
    cash_trace = expected_cash_components(p, opened, partial)
    cash_fractions = cash_trace["cash"].copy()
    partial_profile = np.any(np.abs(cash_fractions - p) > 1e-12, axis=1)
    partial_n = int(partial_profile.sum())
    receipt_shifts = receipt_shifts or {}
    if receipt_shifts and shap_limit:
        raise ValueError("Kịch bản dời thu dùng SHAP đã lưu của kế hoạch gốc; đặt shap_limit=0 khi mô phỏng lại.")
    if (not isinstance(receipt_shifts, dict) or any(type(v) is not int or not 0 <= v <= 52
                                                   for v in receipt_shifts.values())
            or set(receipt_shifts) - set(opened.customer_id.astype(str))):
        raise ValueError("Khách hàng hoặc số tuần dời thu không hợp lệ.")
    invoice_shifts = np.array([
        (int(np.ceil(delay_days / 7)) if delay_days and (not delay_customer or str(c) == delay_customer) else 0)
        + receipt_shifts.get(str(c), 0) for c in opened.customer_id
    ], dtype=int)
    for i in np.flatnonzero(invoice_shifts):
        shift = invoice_shifts[i]
        p[i] = 0
        cash_fractions[i] = 0
        for k in range(receipt_horizon + 1):
            p[i, min(receipt_horizon, k + shift)] += raw_payment_times[i, k]
            cash_fractions[i, min(receipt_horizon, k + shift)] += cash_trace["cash"][i, k]
    payment_times = p.copy()
    amounts = opened.remaining_amount.to_numpy()
    incoming = (cash_fractions[:, :receipt_horizon] * amounts[:, None]).sum(0)[:horizon].copy()
    cash_fractions = np.column_stack((cash_fractions[:, :horizon], cash_fractions[:, horizon:].sum(1)))
    from .obligations import cash_schedule

    t5 = cash_schedule(data, clock, horizon, expense_multiplier)
    expense_shifts = expense_shifts or {}
    if (not isinstance(expense_shifts, dict) or any(type(v) is not int or not 0 <= v <= 52
                                                   for v in expense_shifts.values())
            or set(expense_shifts) - {r['expense_id'] for r in t5['outflows']}):
        raise ValueError("Khoản chi hoặc số tuần dời chi không hợp lệ.")
    moved, beyond = [], []
    for row in t5['outflows']:
        shift_out = expense_shifts.get(row['expense_id'], 0)
        row = dict(row, week=row['week'] + shift_out,
                   date=str((pd.Timestamp(row['date']) + pd.Timedelta(weeks=shift_out)).date()))
        (moved if row['week'] <= horizon else beyond).append(row)
    t5.update(outflows=moved, outflows_pushed_beyond_horizon=beyond,
              scenario_expense_shifts=expense_shifts)
    outgoing = np.zeros(horizon)
    obligation_in = np.zeros(horizon)
    known_variable = np.zeros(horizon)
    scheduled = np.zeros(horizon, bool)
    scheduled_outflows = t5['outflows']
    for r in scheduled_outflows:
        week = r['week'] - 1
        outgoing[week] += r['amount']
        scheduled[week] = True
        if r['category'] == 'variable_cost':
            known_variable[week] += r['amount']
    for r in t5['inflows']:
        obligation_in[r['week'] - 1] += r['amount']
    coverage = [
        ("scheduled" if i + 1 in confirmed_weeks else "scheduled_unconfirmed")
        if scheduled[i]
        else "confirmed_zero"
        if i + 1 in confirmed_weeks
        else "unknown"
        for i in range(horizon)
    ]
    operating = bundle.get("operating") if bundle and include_operating else None
    operating_weeks = min(horizon, 13) if operating else 0
    estimate = None
    new_credit = None
    variable_cost_topup = np.zeros(horizon)
    if include_operating and not operating:
        raise ValueError(
            "Chưa có phiên bản được kiểm định trên lịch sử sao kê cho bán thu ngay và chi biến đổi."
        )
    if operating:
        from .operating import available_history, predict_candidate

        series, gap = available_history(data, cutoff, operating["accounts"])
        if len(series) < 52:
            raise ValueError("Thiếu tuần sao kê đã đối chiếu đến ngày dự báo.")
        estimate = predict_candidate(
            operating["name"], operating["model"], series, gap
        )[:operating_weeks]
        if operating.get("credit"):
            from .new_credit import build, point

            m = build(data, cutoff, operating["accounts"])
            if m is not None:
                new_credit = point(m, operating["credit"]["kind"])[:operating_weeks]
                incoming[:operating_weeks] += new_credit
        incoming[:operating_weeks] += estimate[:, 0]
        variable_cost_topup[:operating_weeks] = np.maximum(
            0, estimate[:, 1] * expense_multiplier - known_variable[:operating_weeks]
        )
        outgoing += variable_cost_topup
    incoming += obligation_in
    expected = balance + np.cumsum(incoming - outgoing)
    rng = np.random.default_rng(simulation_seed)
    paths = np.full((simulation_paths, horizon), float(balance)) - np.cumsum(outgoing)
    paths += np.cumsum(obligation_in)
    if operating:
        errors = operating["residuals"][:, :operating_weeks]
        draws = np.maximum(0, estimate + errors[rng.integers(0, len(errors), simulation_paths)])
        costs = known_variable[:operating_weeks]
        added = np.maximum(0, draws[:, :, 1] * expense_multiplier - costs)
        point_added = np.maximum(0, estimate[:, 1] * expense_multiplier - costs)
        operating_movements = draws[:, :, 0] - added + point_added
        if new_credit is not None:
            residuals = operating["credit"]["residuals"][:, :operating_weeks]
            operating_movements += np.maximum(
                0, new_credit + residuals[rng.integers(len(residuals), size=simulation_paths)]
            )
        movement = np.zeros_like(paths)
        movement[:, :operating_weeks] = operating_movements
        paths += np.cumsum(movement, axis=1)
    # Multiple cash receipts per invoice/path; settlement collects its residual.
    # Always draw in the same invoice order, including when only one customer
    # is shifted. Partitioning the book before draws breaks paired scenarios.
    cash_events = np.zeros((simulation_paths, receipt_horizon))
    for i, invoice_paths in enumerate(iter_cash_paths(
            raw_payment_times, opened, partial, amounts, rng, simulation_paths,
            shared_customer=shared_customer_risk)):
        weeks_shift = invoice_shifts[i]
        if weeks_shift < receipt_horizon:
            cash_events[:, weeks_shift:] += invoice_paths.receipts[:, :receipt_horizon - weeks_shift]
    paths += np.cumsum(cash_events[:, :horizon], axis=1)
    low, median, high = np.quantile(paths, [0.1, 0.5, 0.9], axis=0)
    from .risk import predict_risk

    risk_values = predict_risk(bundle.get("risk") if bundle else None, opened)
    triage_p = payment_times[:, :4].sum(1)
    priorities = [
        dict(
            invoice_id=str(r.invoice_id),
            customer_id=str(r.customer_id),
            outstanding=int(r.remaining_amount),
            write_off_probability_365d_at_issue=risk_values[i],
            overdue_days=max(0, (clock - r.due_date).days),
            due_date=str(r.due_date.date()),
            disputed=disputes.get(r.invoice_id, False),
            promised_date=promises.get(r.invoice_id),
            promise_reliability=reliability.get(r.customer_id),
            reason=(
                "Chờ giải quyết tranh chấp"
                if disputes.get(r.invoice_id)
                else "Kiểm tra lời hứa đã đến hạn"
                if promises.get(r.invoice_id, "9999") <= cutoff
                else "Ưu tiên theo giá trị công nợ và kiểm định lịch sử"
            ),
            payment_probability_4w=float(payment_times[i, :4].sum()),
            triage_probability_4w=float(triage_p[i]),
        )
        for i, r in enumerate(opened.itertuples())
        if not deferred.get(r.invoice_id)
    ]
    from .collection_explanations import rank_with_explanations

    priorities, collection_ranking = rank_with_explanations(
        priorities,
        policy=bundle.get("collection_policy", "amount") if bundle else "amount",
        cutoff=str(clock.date()),
        evaluation=bundle.get("collection_evaluation") if bundle else None,
        has_serving_model=bundle is not None,
        model_asof=bundle.get("asof") if bundle else None,
        delay_days=delay_days,
        delay_customer=delay_customer,
        eligibility={
            "open_before_rules": open_before_rules,
            "writeoff_excluded": writeoff_excluded,
            "recent_contact_or_skip_excluded": sum(bool(deferred.get(i)) for i in opened.invoice_id),
            "cooldown_days": 7,
        },
        probability_source={
            "method": "active_t1", "label": "T1 đang dùng cho dự báo",
            "asof": bundle.get("asof"), "model_version": bundle.get("t1_version"),
            "scenario_shift_applied": bool(delay_days),
            "detail": "Cùng phân phối T1 đang dự báo; không fit thêm model customer local.",
        },
    )
    explanation_references = {}
    if priorities:
        from .explanations import explain_collections

        explanation_rows = priorities[:shap_limit]
        for row in priorities[shap_limit:]:
            row["payment_explanation"] = dict(status="deferred", target="payment_probability_4w",
                probability=row["payment_probability_4w"], cutoff=str(clock.date()),
                reason="Chưa tính SHAP cho hóa đơn này theo giới hạn giải thích của kế hoạch.")
        reference = explain_collections(
            explanation_rows, opened, serving_components, clock,
            delay_days=delay_days, delay_customer=delay_customer,
            model_asof=bundle.get("asof") if bundle else None,
        )
        if reference:
            explanation_references[reference["hash"]] = reference
        if collection_ranking["uses_probability"]:
            reference = explain_collections(
                explanation_rows, opened, serving_components, clock,
                delay_days=delay_days, delay_customer=delay_customer,
                model_asof=bundle.get("asof"),
                probability_field="triage_probability_4w",
                output_field="triage_explanation",
            )
            if reference:
                explanation_references[reference["hash"]] = reference
            for row in priorities[shap_limit:]:
                row["triage_explanation"] = dict(status="deferred", target="triage_probability_4w",
                    probability=row["triage_probability_4w"], cutoff=str(clock.date()),
                    reason="Chưa tính SHAP theo giới hạn giải thích của kế hoạch.")
            for row in priorities:
                row["ranking_explanation"]["probability_explanation"] = row.pop("triage_explanation")
    result = dict(
        t1_provenance=bundle.get("t1_provenance") if bundle else None,
        compute_budget=dict(simulation_paths=simulation_paths, simulation_seed=simulation_seed,
                            shap_limit=shap_limit, explained_invoices=min(shap_limit, len(priorities)),
                            displayed_invoices=len(priorities), all_open_invoices_forecast=True),
        explanation_references=explanation_references,
        cutoff=str(clock.date()),
        horizon_weeks=horizon,
        operating_weeks=operating_weeks,
        mode="company_trained" if bundle else "history_baseline",
        open_invoices=len(opened),
        partial_cash_supported=partial_n,
        adapter_version=ADAPTER_VERSION,
        partial_version=partial.digest,
        serving_manifest=bundle.get("serving_manifest"),
        written_off_count=len(lost),
        payment_delay_shift_days=shift_days,
        operating_included=estimate is not None,
        new_credit_included=new_credit is not None,
        outstanding=float(amounts.sum()),
        minimum_balance=float(expected.min()),
        opening_balance=float(balance),
        t5=t5,
        cash_floor=float(cash_floor),
        unknown_outflow_weeks=[i + 1 for i, v in enumerate(coverage) if v in {"unknown", "scheduled_unconfirmed"}],
        timing_dependence="shared_customer_stress"
        if shared_customer_risk
        else "independent",
        band_protocol="settlement-partial-paths-v2",
        band_status="raw_simulation",
        any_below_floor_probability=float((paths < cash_floor).any(axis=1).mean()),
        weeks=[
            dict(
                week=i + 1,
                date=str((clock + pd.Timedelta(days=7 * (i + 1))).date()),
                cash_in=float(incoming[i]),
                new_credit_in=float(new_credit[i])
                if new_credit is not None and i < operating_weeks
                else 0.0,
                obligation_in=float(obligation_in[i]),
                cash_out=float(outgoing[i]),
                balance=float(expected[i]),
                expected_balance=float(expected[i]),
                median_balance=float(median[i]),
                balance_quantiles={"0.1": float(low[i]), "0.5": float(median[i]), "0.9": float(high[i])},
                low=float(low[i]),
                high=float(high[i]),
                outflow_status=coverage[i],
                below_floor_probability=float((paths[:, i] < cash_floor).mean()),
            )
            for i in range(horizon)
        ],
        collections=priorities,
        collection_ranking=collection_ranking,
        alerts=[
            dict(
                week=i + 1,
                message="Có nguy cơ xuống dưới mức tiền tối thiểu. Kiểm tra thu, chi và phạm vi lịch.",
            )
            for i in range(horizon)
            if expected[i] < cash_floor or (paths[:, i] < cash_floor).mean() >= 0.25
        ],
        assumptions=[
            f"Ước lượng hoạt động áp dụng cho {operating_weeks} tuần đầu; các tuần sau chỉ tính công nợ và lịch chi đã biết."
            if operating_weeks and horizon > operating_weeks
            else "Có ước lượng bán thu ngay và chi biến đổi từ sao kê."
            if operating
            else "Chỉ gồm công nợ đang mở và lịch chi đã khai báo; chưa gồm doanh số mới.",
            "Đã gồm ước lượng thu hóa đơn bán chịu phát hành trong kỳ dự báo."
            if new_credit is not None
            else "Chưa gồm thu từ hóa đơn bán chịu chưa phát hành.",
            f"Adapter xét trả từng phần cho toàn bộ {len(opened)} khoản mở, gồm khoản chưa từng thu; {partial_n} khoản có tiền kỳ vọng thay đổi so với chỉ dự báo tất toán.",
            (
                "Kịch bản căng thẳng: hóa đơn cùng khách chịu chung một cú sốc."
                if shared_customer_risk
                else "Mô phỏng thời điểm trả độc lập."
            )
            + " Xác suất cảnh báo lấy từ mô phỏng; trạng thái hiệu chỉnh dải tiền được lưu riêng.",
            "Danh sách thu hồi xếp theo phương án đã kiểm định hoặc theo dư nợ khi dùng mốc.",
            "T5 chỉ dự báo phần nghĩa vụ còn lại sau thanh toán đã ghi nhận. Khoản chi đến/quá hạn chưa trả chuyển sang ngày làm việc kế tiếp; số dư đầu đã gồm giao dịch thực tế đến ngày chốt.",
            "Khoản hoàn đã duyệt nhưng quá ngày dự kiến nhận cần ngày dự kiến mới; không tự coi là tiền sẽ về ngay.",
        ],
        pilot_ready=False,
    )
    from .cash_explanations import explain_cash

    cash_sales = np.zeros(horizon)
    credit_receipts = np.zeros(horizon)
    if estimate is not None:
        cash_sales[:operating_weeks] = estimate[:, 0]
    if new_credit is not None:
        credit_receipts[:operating_weeks] = new_credit
    result["cash_decomposition"] = explain_cash(
        opened, cash_fractions[:, :horizon] * amounts[:, None], result["weeks"],
        cutoff=str(clock.date()), opening_balance=balance, cash_floor=cash_floor,
        scheduled_outflows=scheduled_outflows, cash_sales=cash_sales,
        scheduled_inflows=t5['inflows'], obligation_in=obligation_in,
        new_credit=credit_receipts, variable_cost_topup=variable_cost_topup,
        partial_profile=partial_profile, partial_supported=partial_n,
        written_off_count=writeoff_excluded,
        model_asof=bundle.get("asof") if bundle else str(clock.date()),
    )
    from .t10_explanations import attach_evidence
    attach_evidence(result, opened, cash_trace, raw_payment_times, partial, bundle,
                    invoice_shifts=invoice_shifts)
    # Research callers can freeze full joint paths before opening held-out truth.
    # The public serving API keeps its compact JSON response.
    if return_paths:
        result["balance_paths"] = paths.tolist()
    return result
