"""Legacy ten-feature schema and the shared observed-landmark T1 interface.

The eighteen-feature schema is defined in landmark_features.py. Both versions
freeze observed state at the forecast origin and advance one future-week
coordinate. IDs and private World state stay outside the estimator inputs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

SCHEMA = "t1-compact-landmark-v1"
FEATURES = (
    "relative_amount", "term_days", "age_days", "received_fraction",
    "receipt_recency_days", "customer_delay_180d", "company_delay_180d",
    "customer_settlements_180d", "customer_overdue_share", "company_overdue_share",
)
GROUPS = (
    ("invoice_terms", "Giá trị tương đối và kỳ hạn", (0, 1)),
    ("invoice_age", "Tuổi hóa đơn", (2,)),
    ("receipt_state", "Khoản đã thu và lần thu gần nhất", (3, 4)),
    ("customer_history", "Lịch sử khách trong 180 ngày", (5, 7)),
    ("company_history", "Lịch sử doanh nghiệp trong 180 ngày", (6,)),
    ("overdue_context", "Tỷ trọng dư nợ quá hạn trên 30 ngày", (8, 9)),
)
MAX_BACKGROUND = 24  # Used only by the explicit legacy24 explanation policy.
HORIZON = 13


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Ledger:
    """One tenant only; timestamps express when each record became available.

    Adjustments are negative noncash changes to the claim, not receipts. A
    closure using a credit note must never acquire a Paid label.
    """
    def __init__(self, invoices, payments, credits=None):
        self.invoices = invoices.copy()
        self.payments = payments.copy()
        self.credits = credits.copy() if credits is not None else pd.DataFrame(
            columns=["invoice_id", "date", "known_at", "amount"])
        for frame, columns in ((self.invoices, ("issue_date", "due_date", "known_at", "written_off_at")),
                               (self.payments, ("date", "known_at")),
                               (self.credits, ("date", "known_at"))):
            for column in columns:
                if column not in frame:
                    frame[column] = pd.NaT
                frame[column] = pd.to_datetime(frame[column])
        if self.invoices.invoice_id.duplicated().any():
            raise ValueError("Compact T1 ledger requires unique invoice IDs within one tenant")
        if "firm_id" in self.invoices and self.invoices.firm_id.nunique() > 1:
            raise ValueError("Build compact features separately for each tenant")
        self.invoices["amount"] = self.invoices.amount.astype(float)
        if not (self.invoices.amount > 0).all():
            raise ValueError("Invoice amounts must be positive")
        for frame in (self.payments, self.credits):
            frame["amount"] = frame.amount.astype(float)
            frame["available"] = frame[["date", "known_at"]].max(axis=1)
        self.payments = self.payments.sort_values(["available", "date", "invoice_id"], kind="stable")
        self.payments["cumulative"] = self.payments.groupby("invoice_id").amount.cumsum()

    def snapshot(self, cutoff):
        cutoff = pd.Timestamp(cutoff)
        inv = self.invoices
        frame = inv[(inv.issue_date <= cutoff) & (inv.known_at <= cutoff)].copy()
        pay = self.payments[self.payments.available <= cutoff]
        credits = self.credits[self.credits.available <= cutoff].groupby("invoice_id").amount.sum()
        frame["credit_amount"] = frame.invoice_id.map(credits).fillna(0).clip(lower=0)
        frame["claim_amount"] = (frame.amount-frame.credit_amount).clip(lower=0)
        frame["received"] = frame.invoice_id.map(pay.groupby("invoice_id").amount.sum()).fillna(0)
        frame["receipt_count"] = frame.invoice_id.map(pay.groupby("invoice_id").size()).fillna(0)
        recent = pay[pay.date > cutoff-pd.Timedelta(days=28)]
        frame["received_28d"] = frame.invoice_id.map(recent.groupby("invoice_id").amount.sum()).fillna(0)
        frame["remaining_amount"] = (frame.claim_amount-frame.received).clip(lower=0)
        frame["last_receipt"] = pay.groupby("invoice_id").date.max().reindex(frame.invoice_id).to_numpy()
        # Paid history requires cash to cover the original claim. Noncash
        # closures remain excluded from delay statistics and Paid targets.
        gross = self.invoices.set_index("invoice_id").amount
        full = pay[pay.cumulative >= pay.invoice_id.map(gross)-0.01]
        frame["settled"] = full.groupby("invoice_id").date.min().reindex(frame.invoice_id).to_numpy()
        frame["settled_known_at"] = full.groupby("invoice_id").available.min().reindex(frame.invoice_id).to_numpy()
        frame["written_off_at"] = frame.written_off_at.where(frame.written_off_at <= cutoff)
        frame.attrs["cutoff"] = str(cutoff.date())
        return frame

    def snapshot_features(self, cutoff):
        frame = self.snapshot(cutoff)
        opened = frame[(frame.remaining_amount > .01) & frame.written_off_at.isna()].copy()
        return opened, prepare_features(opened, frame, cutoff)

    def labels(self, opened, cutoff, label_end):
        """Cash-paid targets, independently of the feature snapshot.

        Only fully mature 91-day landmarks enter this experiment. Late-known
        pre-origin receipts and noncash claim revisions in follow-up are
        excluded; neither can be treated as newly arriving future cash.
        """
        cutoff, label_end = pd.Timestamp(cutoff), pd.Timestamp(label_end)
        if cutoff + pd.Timedelta(days=91) > label_end:
            raise ValueError("Compact labels need 91 complete follow-up days")
        end = cutoff+pd.Timedelta(days=91)
        pay = self.payments[self.payments.available <= label_end]
        gross = self.invoices.set_index("invoice_id").amount
        paid = pay[pay.cumulative >= pay.invoice_id.map(gross)-.01]
        dates = opened.invoice_id.map(paid.groupby("invoice_id").date.min())
        days = (dates-cutoff).dt.days.to_numpy(float)
        # A changed claim needs its own accounting target; do not silently
        # train this fixed-claim full-cash model on it.
        changes = self.credits[(self.credits.available > cutoff) & (self.credits.available <= end)]
        late = pay[(pay.date <= cutoff) & (pay.available > cutoff)]
        valid = ~opened.invoice_id.isin(set(changes.invoice_id) | set(late.invoice_id))
        valid &= opened.credit_amount <= .01
        valid &= np.isnan(days) | (days > 0)
        return np.where(np.isfinite(days), days, np.inf), valid.to_numpy()


def feature_context(history, cutoff):
    """Shared observed cohorts and amount scale for both landmark schemas."""
    cutoff = pd.Timestamp(cutoff)
    if pd.Timestamp(history.attrs.get("cutoff", cutoff)) != cutoff:
        raise ValueError("Feature history must use the forecast origin")
    history = history[(history.issue_date <= cutoff) & (history.known_at <= cutoff)]
    paid = history[history.settled.notna() & (history.settled <= cutoff) &
                   (history.settled_known_at <= cutoff) &
                   (history.settled > cutoff-pd.Timedelta(days=180))].copy()
    opened = history[(history.remaining_amount > .01) & history.written_off_at.isna()].copy()
    recent = history[history.issue_date > cutoff-pd.Timedelta(days=180)]
    scale = float(recent.amount.median()) if len(recent) else float(history.amount.median())
    return paid, opened, max(scale, 1.)


def prepare_features(opened, history, cutoff):
    """Same ten columns for World fitting, Workspace serving and explanation."""
    cutoff = pd.Timestamp(cutoff)
    paid, open_history, scale = feature_context(history, cutoff)
    paid["delay"] = (paid.settled-paid.due_date).dt.days.clip(-60, 180)
    company_delay = float(paid.delay.median()) if len(paid) else 0.
    stats = paid.groupby("customer_id").delay.agg(["median", "count"])
    counts = opened.customer_id.map(stats["count"]).fillna(0).to_numpy(float)
    medians = opened.customer_id.map(stats["median"]).fillna(company_delay).to_numpy(float)
    overdue = (cutoff-open_history.due_date).dt.days > 30
    open_history["overdue_amount"] = open_history.remaining_amount.where(overdue, 0)
    totals = open_history.groupby("customer_id")[["remaining_amount", "overdue_amount"]].sum()
    shares = totals.overdue_amount/totals.remaining_amount.clip(lower=1)
    total = float(open_history.remaining_amount.sum())
    company_share = float(open_history.overdue_amount.sum()/total) if total else 0.
    age = (cutoff-opened.issue_date).dt.days.clip(0, 730).to_numpy(float)
    received = (opened.received/opened.amount).clip(0, 1).to_numpy(float)
    recency = (cutoff-opened.last_receipt).dt.days.fillna(180).clip(0, 180).to_numpy(float)
    values = np.column_stack((
        np.log1p(np.clip(opened.amount.to_numpy(float)/scale, 0, 100)),
        (opened.due_date-opened.issue_date).dt.days.clip(0, 365).to_numpy(float),
        age, received, recency,
        (counts*medians+5*company_delay)/(counts+5),
        np.full(len(opened), company_delay), np.log1p(counts),
        opened.customer_id.map(shares).fillna(company_share).to_numpy(float),
        np.full(len(opened), company_share)))
    if not np.isfinite(values).all():
        raise ValueError("Compact features must be finite")
    return values


def workspace_context(data, cutoff):
    """Use the Workspace accounting view and dated, linked observed receipts."""
    from .data import observed, as_of, _payment_links, payment_target
    frame = observed(data, cutoff)
    visible = as_of(data, cutoff)
    links = _payment_links(visible.get("invoices", []))
    dates, counts, recent_amounts = {}, {}, {}
    for pay in visible.get("payments", []):
        if pd.Timestamp(pay["payment_date"]) <= pd.Timestamp(cutoff) and pd.Timestamp(pay["known_at"]) <= pd.Timestamp(cutoff):
            iid = payment_target(pay["invoice_id"], links)
            dates[iid] = max(dates.get(iid, pd.Timestamp.min), pd.Timestamp(pay["payment_date"]))
            counts[iid] = counts.get(iid, 0)+1
            if pd.Timestamp(pay["payment_date"]) > pd.Timestamp(cutoff)-pd.Timedelta(days=28):
                recent_amounts[iid] = recent_amounts.get(iid, 0)+float(pay["amount"])
    frame["last_receipt"] = pd.to_datetime(frame.invoice_id.map(dates))
    frame["receipt_count"] = frame.invoice_id.map(counts).fillna(0)
    frame["received_28d"] = frame.invoice_id.map(recent_amounts).fillna(0)
    frame.attrs["cutoff"] = str(pd.Timestamp(cutoff).date())
    return frame


class CompactT1:
    variant = "compact_world"
    name = "compact_world"
    feature_schema = SCHEMA
    feature_names = FEATURES
    shap_groups = GROUPS
    requires_ledger_context = True

    def __init__(self, booster, active=None, metadata=None):
        self.booster = booster
        self.active = tuple(range(len(self.feature_names))) if active is None else tuple(active)
        self.metadata = metadata or {}

    def prepare(self, frame, ages=None):
        context = frame.attrs.get("compact_context")
        if context is None:
            raise ValueError("Compact T1 requires an observed ledger context at the forecast cutoff")
        clock = pd.Timestamp(context.attrs["cutoff"])
        if ages is not None and not np.array_equal(np.maximum(np.asarray(ages), 0), (clock-frame.issue_date).dt.days.to_numpy()):
            raise ValueError("Compact T1 ages must match the context cutoff")
        targets = context.set_index("invoice_id").loc[frame.invoice_id].reset_index()
        if not np.allclose(targets.amount.to_numpy(float), frame.amount.to_numpy(float), atol=.01, rtol=0):
            raise ValueError("Serving invoices differ from the observed compact context")
        return self.prepare_state(targets, context, clock)

    @staticmethod
    def prepare_state(targets, context, clock):
        return prepare_features(targets, context, clock)

    def distribution(self, frame, ages=None, horizon=13):
        return self.distribution_from_features(self.prepare(frame, ages), horizon=horizon)

    def distribution_from_features(self, x, ages=None, horizon=13):
        if not 1 <= horizon <= 52:
            raise ValueError("Horizon outside supported T1 range")
        x = np.asarray(x, float)
        if x.ndim != 2 or x.shape[1] != len(self.feature_names) or not np.isfinite(x).all():
            raise ValueError("Compact feature schema mismatch")
        # Learned support is 13 weeks. Additional weeks retain the unresolved
        # tail, rather than extrapolating a hazard beyond the training contract.
        weeks = min(horizon, HORIZON)
        rows = np.repeat(x[:, self.active], weeks, axis=0)
        offsets = np.tile(np.arange(1, weeks+1), len(x))
        h = np.asarray(self.predict_hazard(np.column_stack((rows, offsets))), dtype=float).reshape(len(x), weeks)
        h = np.clip(h, 1e-6, 1-1e-6)
        survival = np.cumprod(1-h, axis=1)
        mass = np.column_stack((np.ones(len(x)), survival[:, :-1]))*h
        p = np.zeros((len(x), horizon+1))
        p[:, :weeks] = mass
        p[:, -1] = survival[:, -1]
        return p

    def predict_hazard(self, rows):
        return self.booster.predict(rows, num_threads=1)

    def save(self, directory, metadata):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        model = directory/"model.txt"
        self.booster.save_model(str(model))
        meta = dict(metadata, schema=SCHEMA, features=list(FEATURES), active=list(self.active),
                    model_sha256=sha256(model), max_horizon_weeks=HORIZON,
                    shap_groups=[dict(key=k, label=l, columns=list(c)) for k, l, c in GROUPS])
        (directory/"metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.metadata = meta

    @classmethod
    def load(cls, directory):
        import lightgbm as lgb
        directory = Path(directory)
        meta = json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
        if meta.get("schema") == "t1-landmark-18-v2":
            from .landmark_features import FEATURES as landmark_features, load_landmark

            if meta.get("features") != list(landmark_features):
                raise ValueError("Unknown landmark T1 feature schema")
            return load_landmark(directory, meta)
        if meta.get("schema") != SCHEMA or meta.get("features") != list(FEATURES):
            raise ValueError("Unknown compact T1 schema")
        if "compact_kind" in meta:
            from .compact_ensemble import load_compact_model

            return load_compact_model(directory, meta)
        if sha256(directory/"model.txt") != meta["model_sha256"]:
            raise ValueError("Compact T1 model hash mismatch")
        active = meta["active"]
        if not active or len(set(active)) != len(active) or any(not isinstance(i, int) or not 0 <= i < len(FEATURES) for i in active):
            raise ValueError("Invalid compact feature mask")
        booster = lgb.Booster(model_file=str(directory/"model.txt"))
        if booster.num_feature() != len(active)+1:
            raise ValueError("Compact estimator/schema dimension mismatch")
        return cls(booster, active, meta)


def load_workspace_bundle(directory, asof):
    """Explicit local loading; never activate a research artifact automatically."""
    model = CompactT1.load(directory)
    clock = pd.Timestamp(asof)
    ready = pd.Timestamp(model.metadata["available_asof"])
    if ready > clock:
        raise ValueError("Compact T1 used fit/selection labels after the requested forecast date")
    return dict(model=model, anchor=model, weight=1., asof=str(ready.date()),
                selected_method=model.variant, algorithm_version=model.feature_schema,
                feature_schema=model.feature_schema, feature_names=[model.feature_names[i] for i in model.active],
                dataset_hash=model.metadata["data_fingerprint"], synthetic_sandbox=True,
                code_hash=model.metadata["source_sha256"],
                limitation="Synthetic World candidate; cash T6 partial profiles and bank scopes remain separate. Beyond 13 weeks the remaining mass stays unresolved.")


def load_research_t1_bundle(run_directory, cutoff, company_bundle=None):
    """Verify a research release and replace T1, retaining other company learners."""
    directory = Path(run_directory)
    release = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    if not release.get("research_integration_accepted"):
        raise ValueError("Bản T1 nghiên cứu chưa đạt kiểm chứng tích hợp.")
    for name, digest in release["required_hashes"].items():
        if sha256(directory / name) != digest:
            raise ValueError("Bằng chứng hoặc artifact T1 đã thay đổi sau kiểm chứng.")
    research = load_workspace_bundle(directory / release["artifact_directory"], cutoff)
    result = dict(company_bundle or {})
    result.update(research)
    result["t1_provenance"] = {
        "source": "research_global_refit" if release.get("refit_accepted", True) else "research_global_retained",
        "run": directory.name,
        "metadata_sha256": sha256(directory / release["artifact_directory"] / "metadata.json"),
        "feature_context_contract": release["feature_context_contract"],
        "local_adaptation": False,
        "synthetic": True,
        "real_pilot_accepted": False,
    }
    return result


def explain_compact(rows, opened, components, cutoff, *, delay_days=0, delay_customer=None,
                    model_asof=None, probability_field="payment_probability_4w", output_field="payment_explanation",
                    background_policy="representative"):
    """Explain the served probability with a versioned grouped reference policy.

    The default uses census/weighted stratified references and sensitivity
    samples. legacy24 replays the earlier ten-feature experiment.
    """
    if background_policy == "representative":
        from .landmark_explanations import explain_landmark

        return explain_landmark(rows, opened, components, cutoff, delay_days=delay_days,
                                delay_customer=delay_customer, model_asof=model_asof,
                                probability_field=probability_field, output_field=output_field)
    if background_policy != "legacy24" or any(m.feature_schema != SCHEMA for w, m in components if w):
        raise ValueError("Legacy background requires the ten-feature compact schema")
    from .explanations import shapley_values
    if not rows:
        return None
    start = time.perf_counter()
    if any(not isinstance(m, CompactT1) for w, m in components if w):
        raise ValueError("Compact explanations require schema-compatible components")
    leaves = [(w, m) for w, m in components if w]
    if not np.isclose(sum(w for w, _ in leaves), 1.):
        raise ValueError("Invalid compact explanation weights")
    values = [m.prepare(opened) for _, m in leaves]
    # Background selection depends on current inputs only, not labels. Sorting
    # by amount then equidistant ranks retains scale coverage deterministically.
    ids = opened.invoice_id.astype(str).to_numpy()
    order = np.lexsort((ids, values[0][:, 0]))
    reference = order[np.unique(np.linspace(0, len(order)-1, min(MAX_BACKGROUND, len(order))).round().astype(int))]
    active = set(i for _, m in leaves for i in m.active)
    groups = [(k, l, c) for k, l, c in GROUPS if active.intersection(c)]
    dimensions = len(groups)
    masks = (np.arange(2**dimensions)[:, None] & (1 << np.arange(dimensions))) != 0
    column_masks = np.zeros((len(masks), len(FEATURES)), bool)
    for j, (_, _, columns) in enumerate(groups):
        column_masks[:, columns] = masks[:, j, None]
    positions = {str(iid): i for i, iid in enumerate(ids)}
    snapshot = dict(protocol="compact-t1-grouped-exact-v1", cutoff=str(pd.Timestamp(cutoff).date()),
                    schema=SCHEMA, invoice_ids=ids[reference].tolist(),
                    values=[v[reference].tolist() for v in values],
                    groups=[dict(key=k, columns=[FEATURES[i] for i in c if i in active]) for k, _, c in groups],
                    population=len(opened), count=len(reference), selection="deterministic_amount_rank_sample",
                    weighting="equal_per_selected_reference_invoice")
    reference_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    snapshot["hash"] = reference_hash
    for row in rows:
        i = positions[str(row["invoice_id"])]
        shift = int(np.ceil(delay_days/7)) if delay_days and (not delay_customer or row["customer_id"] == delay_customer) else 0
        week = max(0, 4-shift)
        game = np.zeros(len(masks))
        for (weight, model), prepared in zip(leaves, values):
            hybrids = np.where(column_masks[:, None, :], prepared[i], prepared[reference][None, :, :]).reshape(-1, len(FEATURES))
            prob = model.distribution_from_features(hybrids, horizon=4)[:, :week].sum(1) if week else np.zeros(len(hybrids))
            game += weight*prob.reshape(len(masks), len(reference)).mean(1)
        contribution = shapley_values(game[None, :], dimensions)[0]
        probability = float(row[probability_field])
        reconstructed = float(game[0]+contribution.sum())
        if not np.isclose(game[-1], probability, atol=1e-10, rtol=0) or not np.isclose(reconstructed, probability, atol=1e-10, rtol=0):
            raise ValueError("Compact explanation does not reconstruct served probability")
        factors = []
        for j, (key, label, columns) in enumerate(groups):
            raw = {FEATURES[c]: float(values[0][i, c]) for c in columns if c in active}
            factors.append(dict(feature=key, label=label, value=raw, value_unit="prepared_group",
                                contribution=float(contribution[j]), contribution_pp=float(100*contribution[j]),
                                direction="increase" if contribution[j] > 1e-12 else "decrease" if contribution[j] < -1e-12 else "neutral",
                                stability=dict(status="not_checked"),
                                business_review=dict(status="context_only", feature=key, value=raw,
                                                     reason="Grouped predictive attribution; no causal or contact-effect claim.")))
        row[output_field] = dict(protocol=snapshot["protocol"], status="available", method="exact_grouped_interventional_shapley",
                                  target=probability_field, horizon_weeks=4, cutoff=snapshot["cutoff"], model_asof=model_asof,
                                  model_version=SCHEMA, units="probability", contribution_units="percentage_points",
                                  probability=probability, baseline_probability=float(game[0]), reconstructed_probability=reconstructed,
                                  additivity_error=abs(reconstructed-probability), factors=sorted(factors, key=lambda f: -abs(f["contribution"])),
                                  scenario_shift_weeks=shift, reference=dict(kind="open_invoices_at_cutoff", **{k: snapshot[k] for k in ("count", "population", "selection", "weighting", "hash", "cutoff")}),
                                  group_count=dimensions, coalition_count=len(masks), background_count=len(reference),
                                  stability=dict(checked=False, sample_count=0),
                                  limitations=["Exact only for the declared groups and finite sampled background; individual feature contributions within groups are not available.",
                                               "Background sensitivity and hybrid support are not audited in this latency-bounded protocol.",
                                               "Attribution describes the model, not causation or collection effectiveness."])
    snapshot["elapsed_seconds"] = time.perf_counter()-start
    return snapshot
