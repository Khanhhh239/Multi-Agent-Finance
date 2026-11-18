"""Explicit payment completeness attestations and historical book confirmation."""

from __future__ import annotations

import pandas as pd


def _iso_date(value) -> str:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError("Ngày xác nhận đối soát không hợp lệ")
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None)
    return str(ts.date())


def _month_range(start_date: str, end_date: str) -> list[str]:
    s = pd.Timestamp(start_date).to_period("M")
    e = pd.Timestamp(end_date).to_period("M")
    if e < s:
        return []
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def _normalize_confirmed_months(periods) -> set[str]:
    covered: set[str] = set()
    for item in periods or ():
        if isinstance(item, str):
            text = item.strip()
            if len(text) == 7 and text[4] == "-":
                covered.add(str(pd.Period(text, freq="M")))
            else:
                covered.add(str(pd.Timestamp(text).to_period("M")))
        elif isinstance(item, dict) and "start_date" in item and "end_date" in item:
            covered.update(_month_range(_iso_date(item["start_date"]), _iso_date(item["end_date"])))
        else:
            raise ValueError("Kỳ đối soát phải là chuỗi 'YYYY-MM' hoặc khoảng {start_date, end_date}")
    return covered


def attest(data, cutoff, known_at, *, reconciled_through=None, start_date=None, periods=None):
    """Record payment completeness honestly with known_at = confirmation_date."""
    end = _iso_date(reconciled_through if reconciled_through is not None else cutoff)
    known = _iso_date(known_at)
    if end > known:
        raise ValueError(
            f"Ngày chốt sổ đối soát ({end}) không được vượt quá ngày xác nhận ({known})"
        )
    starts = [
        r["issue_date"]
        for r in data.get("invoices", [])
        if str(r.get("issue_date", "9999-12-31"))[:10] <= end
        and str(r.get("known_at", r.get("issue_date", "0001-01-01")))[:10] <= known
    ]
    first = _iso_date(start_date) if start_date is not None else min(starts, default=end)
    if first > end:
        raise ValueError(
            f"Ngày bắt đầu kỳ đối soát ({first}) phải trước hoặc bằng ngày chốt ({end})"
        )
    record = dict(
        start_date=first,
        end_date=end,
        known_at=known,
        complete=True,
        source=(
            "reconciled_historical_confirmation"
            if reconciled_through is not None
            else "payments_complete_confirmation"
        ),
    )
    if reconciled_through is not None:
        record["reconciled_through"] = end
        record["historical_reconciled"] = True
    if periods is not None:
        record["periods"] = list(periods)
    return record


def attest_reconciled_books(
    data, reconciled_through, confirmation_date, *, start_date=None, periods=None
):
    """Confirm reconciled historical ledger periods up to reconciled_through."""
    return attest(
        data,
        reconciled_through,
        confirmation_date,
        reconciled_through=reconciled_through,
        start_date=start_date,
        periods=periods,
    )


def reconciled_bounds(data, knowledge_end):
    """Return covered historical (start_date, end_date) intervals explicitly confirmed."""
    limit = _iso_date(knowledge_end)
    intervals = []
    for r in data.get("payment_coverage", []):
        if r.get("complete") is not True:
            continue
        if str(r.get("known_at", "9999-12-31"))[:10] > limit:
            continue
        if not (r.get("historical_reconciled") or r.get("reconciled_through")):
            continue
        if r.get("invoice_ids") is not None or r.get("customer_ids") is not None:
            continue
        end = _iso_date(r.get("reconciled_through") or r["end_date"])
        start = _iso_date(r["start_date"])
        if start <= end:
            intervals.append((start, end))
    return intervals


def max_covered_date(data, knowledge_end) -> str | None:
    """Return latest end_date/reconciled_through known by knowledge_end, if any."""
    limit = _iso_date(knowledge_end)
    ends = []
    for r in data.get("payment_coverage", []):
        if r.get("complete") is not True:
            continue
        if str(r.get("known_at", "9999-12-31"))[:10] > limit:
            continue
        if r.get("invoice_ids") is not None or r.get("customer_ids") is not None:
            continue
        ends.append(_iso_date(r.get("reconciled_through") or r["end_date"]))
    return max(ends) if ends else None


def historical_end_for_origin(data, origin, knowledge_end) -> str | None:
    """If origin falls inside a confirmed historical book, return its reconciled_through."""
    day = _iso_date(origin)
    covering = [
        end for start, end in reconciled_bounds(data, knowledge_end) if start <= day <= end
    ]
    return max(covering) if covering else None


def followup_days(data, origin, label_end, invoice_id, customer_id, *, knowledge_end=None):
    origin_ts = pd.Timestamp(origin).normalize()
    label_ts = pd.Timestamp(label_end).normalize()
    known_ts = (
        label_ts
        if knowledge_end is None
        else pd.Timestamp(knowledge_end).normalize()
    )
    days = min(91, (label_ts - origin_ts).days)
    if days <= 0:
        return 0
    covered = [False] * days
    for r in data.get("payment_coverage", []):
        if (
            r.get("complete") is not True
            or pd.Timestamp(r["known_at"]).normalize() > known_ts
            or r.get("invoice_ids") is not None
            and invoice_id not in r["invoice_ids"]
            or r.get("customer_ids") is not None
            and customer_id not in r["customer_ids"]
        ):
            continue
        end_date = r.get("reconciled_through") or r["end_date"]
        first = max(1, (pd.Timestamp(r["start_date"]).normalize() - origin_ts).days)
        last = min(days, (pd.Timestamp(end_date).normalize() - origin_ts).days)
        for day in range(first, last + 1):
            covered[day - 1] = True
    return next((i for i, known in enumerate(covered) if not known), days)


def check_reconciled_completeness(
    data,
    reconciled_through,
    *,
    confirmation_date=None,
    start_date=None,
    periods=None,
    minimum_fit_snapshots=60,
    minimum_fit_invoices=20,
    minimum_validation_snapshots=20,
    minimum_audit_snapshots=20,
    validation_offsets_days=(210, 182),
    stride_days=28,
    lookback_days=730,
):
    """Validate historical period continuity and 91-day resolved cohort sufficiency.

    Returns actionable Vietnamese diagnostics listing missing periods/months
    and deficient fit/validation/audit cohorts without mutating `data`.
    """
    end = _iso_date(reconciled_through)
    known = _iso_date(confirmation_date) if confirmation_date is not None else max(
        end, str(pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date())
    )
    if end > known:
        raise ValueError(
            f"Ngày chốt sổ đối soát ({end}) không được vượt quá ngày xác nhận ({known})"
        )

    invoices = [
        r
        for r in data.get("invoices", [])
        if str(r.get("issue_date", "9999-12-31"))[:10] <= end
        and str(r.get("known_at", r.get("issue_date", "0001-01-01")))[:10] <= known
    ]
    payments = [
        r
        for r in data.get("payments", [])
        if str(r.get("payment_date", "9999-12-31"))[:10] <= end
        and str(r.get("known_at", r.get("payment_date", "0001-01-01")))[:10] <= known
    ]
    messages_vi: list[str] = []
    missing_periods: list[str] = []
    missing_cohorts: list[dict] = []

    if not invoices:
        msg = (
            f"Chưa có hóa đơn đầu ra hợp lệ nào trước hoặc tại ngày chốt đối soát {end}. "
            "Vui lòng tải lên bảng hóa đơn (invoices) và khoản thu (payments)."
        )
        return dict(
            ok=False,
            reconciled_through=end,
            confirmation_date=known,
            start_date=start_date,
            missing_periods=[],
            missing_cohorts=[dict(cohort="invoices", available=0, required=minimum_fit_invoices)],
            counts=dict(
                invoices=0,
                payments=len(payments),
                fit_snapshots=0,
                fit_unique_invoices=0,
                validation_snapshots=0,
                audit_snapshots=0,
            ),
            messages_vi=[msg],
            summary_vi=msg,
        )

    first = _iso_date(start_date) if start_date is not None else min(r["issue_date"][:10] for r in invoices)
    expected_months = _month_range(first, end)

    if periods is not None:
        confirmed_months = _normalize_confirmed_months(periods)
        unconfirmed = [m for m in expected_months if m not in confirmed_months]
        if unconfirmed:
            missing_periods.extend(unconfirmed)
            messages_vi.append(
                f"Thiếu xác nhận đối soát đầy đủ ở các kỳ: {', '.join(unconfirmed)}. "
                f"Vui lòng đối soát và xác nhận liên tục từ {expected_months[0]} đến {expected_months[-1]}."
            )

    statements = [
        r
        for r in data.get("statements", [])
        if str(r.get("start_date", "9999-12-31"))[:10] <= end
        and str(r.get("known_at", r.get("end_date", "0001-01-01")))[:10] <= known
    ]
    if statements:
        by_account: dict[str, list[dict]] = {}
        for s in statements:
            by_account.setdefault(s["account"], []).append(s)
        for account, rows in sorted(by_account.items()):
            rows.sort(key=lambda r: r["start_date"])
            gaps: list[str] = []
            for prev, curr in zip(rows, rows[1:]):
                gap_start = pd.Timestamp(prev["end_date"]) + pd.Timedelta(days=1)
                gap_end = pd.Timestamp(curr["start_date"]) - pd.Timedelta(days=1)
                if gap_start <= gap_end:
                    label = f"{account}:{gap_start.date()}..{gap_end.date()}"
                    gaps.append(label)
            last_end = pd.Timestamp(rows[-1]["end_date"])
            if last_end < pd.Timestamp(end):
                gap_start = last_end + pd.Timedelta(days=1)
                gaps.append(f"{account}:{gap_start.date()}..{end}")
            if gaps:
                for g in gaps:
                    if g not in missing_periods:
                        missing_periods.append(g)
                messages_vi.append(
                    f"Tài khoản sao kê '{account}' còn thiếu kỳ sao kê đối soát: {', '.join(gaps)}."
                )

    active_months = {r["issue_date"][:7] for r in invoices} | {
        r["payment_date"][:7] for r in payments
    }
    for s in statements:
        active_months.update(_month_range(s["start_date"][:10], min(end, s["end_date"][:10])))
    if len(expected_months) >= 3:
        empty_intermediate = [
            m for m in expected_months[1:-1] if m not in active_months and m not in missing_periods
        ]
        if empty_intermediate:
            missing_periods.extend(empty_intermediate)
            messages_vi.append(
                f"Sổ lịch sử bị trống dữ liệu hóa đơn/thanh toán ở các tháng trung gian: "
                f"{', '.join(empty_intermediate)}. Vui lòng kiểm tra và nạp bổ sung nếu còn thiếu chứng từ."
            )

    from .t1_data import landmarks, rolling_landmarks

    staged_cov = attest_reconciled_books(
        data, end, known, start_date=first, periods=periods
    )
    staged = dict(
        data,
        payment_coverage=[*data.get("payment_coverage", []), staged_cov],
    )
    end_ts = pd.Timestamp(end).normalize()
    known_ts = pd.Timestamp(known).normalize()
    val_origins = sorted(end_ts - pd.Timedelta(days=int(d)) for d in validation_offsets_days)
    val_first = val_origins[0]
    audit_origin = end_ts - pd.Timedelta(days=91)
    span_days = (end_ts - pd.Timestamp(first).normalize()).days
    min_required_span = max(validation_offsets_days) + 7

    if span_days < min_required_span:
        needed_from = str((end_ts - pd.Timedelta(days=min_required_span)).date())
        missing_cohorts.append(
            dict(
                cohort="historical_span_days",
                available=int(span_days),
                required=int(min_required_span),
                needed_start_date=needed_from,
            )
        )
        messages_vi.append(
            f"Độ dài lịch sử sổ đã chốt mới đạt {span_days} ngày (từ {first} đến {end}), "
            f"cần tối thiểu {min_required_span} ngày (từ {needed_from} trở về trước) để tách đủ "
            "3 cửa sổ huấn luyện, kiểm định (validation) và hậu kiểm (audit) 91 ngày không chồng lấn."
        )

    fit = rolling_landmarks(
        staged,
        val_first,
        lookback_days=lookback_days,
        stride_days=stride_days,
        knowledge_end=known_ts,
    )
    fit = fit[fit.followup_days >= 7].reset_index(drop=True)
    fit_n = int(len(fit))
    fit_inv_n = int(fit.invoice_id.nunique()) if not fit.empty else 0

    if fit_n < minimum_fit_snapshots or fit_inv_n < minimum_fit_invoices:
        missing_cohorts.append(
            dict(
                cohort="fit",
                through=str(val_first.date()),
                snapshots=fit_n,
                required_snapshots=minimum_fit_snapshots,
                unique_invoices=fit_inv_n,
                required_invoices=minimum_fit_invoices,
            )
        )
        messages_vi.append(
            f"Cửa sổ huấn luyện (trước {val_first.date()}) mới có {fit_n}/{minimum_fit_snapshots} "
            f"snapshot ({fit_inv_n}/{minimum_fit_invoices} hóa đơn mở độc lập). "
            f"Cần bổ sung hóa đơn và lịch sử thu tiền trước ngày {val_first.date()}."
        )

    val_parts = []
    for origin in val_origins:
        part = landmarks(staged, origin, audit_origin, knowledge_end=known_ts)
        part = part[part.followup_days >= 91].reset_index(drop=True)
        val_parts.append((origin, part))
        if len(part) < minimum_validation_snapshots:
            missing_cohorts.append(
                dict(
                    cohort="validation",
                    origin=str(origin.date()),
                    followup_through=str((origin + pd.Timedelta(days=91)).date()),
                    available=int(len(part)),
                    required=minimum_validation_snapshots,
                )
            )
            messages_vi.append(
                f"Mốc kiểm định (validation {origin.date()}, theo dõi 91 ngày đến "
                f"{(origin + pd.Timedelta(days=91)).date()}) mới có {len(part)}/{minimum_validation_snapshots} "
                "hóa đơn đủ điều kiện. Cần bổ sung dữ liệu công nợ mở tại mốc này."
            )

    audit_df = landmarks(staged, audit_origin, end_ts, knowledge_end=known_ts)
    audit_df = audit_df[audit_df.followup_days >= 91].reset_index(drop=True)
    audit_n = int(len(audit_df))
    if audit_n < minimum_audit_snapshots:
        missing_cohorts.append(
            dict(
                cohort="audit",
                origin=str(audit_origin.date()),
                followup_through=end,
                available=audit_n,
                required=minimum_audit_snapshots,
            )
        )
        messages_vi.append(
            f"Mốc hậu kiểm (audit {audit_origin.date()}, theo dõi 91 ngày đến {end}) "
            f"mới có {audit_n}/{minimum_audit_snapshots} hóa đơn đủ 91 ngày đối soát. "
            f"Cần bổ sung hóa đơn mở tại {audit_origin.date()} và đối soát thanh toán đến {end}."
        )

    val_n = int(sum(len(p) for _, p in val_parts))
    ok = not missing_periods and not missing_cohorts
    summary = (
        f"Sổ lịch sử đã đối soát đầy đủ từ {first} đến {end} (xác nhận ngày {known}): "
        f"đủ điều kiện học thích nghi ({fit_n} mẫu fit, {val_n} mẫu validation, {audit_n} mẫu audit)."
        if ok
        else " | ".join(messages_vi)
    )
    return dict(
        ok=ok,
        reconciled_through=end,
        confirmation_date=known,
        start_date=first,
        missing_periods=missing_periods,
        missing_cohorts=missing_cohorts,
        counts=dict(
            invoices=len(invoices),
            payments=len(payments),
            fit_snapshots=fit_n,
            fit_unique_invoices=fit_inv_n,
            validation_snapshots=val_n,
            audit_snapshots=audit_n,
        ),
        messages_vi=messages_vi,
        summary_vi=summary,
    )
