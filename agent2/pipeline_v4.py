"""Weekly, company-scoped v4 pipeline; raw inputs do not require truth files."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

from .alerting import build_cases
from .deployment_v4 import PreparedV4Detector, policy_components
from .explain_check import check
from .explain_v4 import observations, rule_observations, entity_observations
from .inference_v4 import ReducedInput, build, week_bounds
from .pipeline import to_case_queue
from .review_store_v4 import clean
from .sealed_v4 import file_hashes
from .target_signals import TargetSignals
from .monitoring import population_stability

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_config(frozen_path, model_path, output):
    output, model_path = Path(output), Path(model_path).resolve()
    if output.exists():
        raise FileExistsError(f"configuration already exists: {output}")
    frozen = json.loads(Path(frozen_path).read_text(encoding="utf-8"))
    config = {"schema_version": 2, "profile": "precision", "budget": 3, "frozen": frozen,
              "model_path": os.path.relpath(model_path, output.parent.resolve()), "model_sha256": sha(model_path),
              "calibration_days": 90, "minimum_history_rows": 20, "training_data_kind": "synthetic"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


class OperationalV4Detector:
    def __init__(self, config, profile=None):
        if isinstance(config, (str, Path)):
            path = Path(config).resolve()
            self.config = json.loads(path.read_text(encoding="utf-8"))
            base = path.parent
        else:
            self.config, base = dict(config), ROOT
        cfg = self.config
        if cfg.get("schema_version") != 2 or cfg.get("budget", 3) != 3:
            raise ValueError("requires v4 schema_version=2 and the registered budget=3")
        frozen = cfg["frozen"]
        if frozen["hashes"] != file_hashes(ROOT):
            raise ValueError("feature code differs from the frozen model configuration")
        self.profile = profile or cfg.get("profile", "precision")
        self.model_sha256 = None
        if self.profile == "cold":
            bundle = {"schema_version": 2, "frozen": frozen, "models": {}}
        else:
            model = (base / cfg["model_path"]).resolve()
            self.model_sha256 = sha(model)
            if self.model_sha256 != cfg["model_sha256"]:
                raise ValueError("pretrained model checksum differs from configuration")
            bundle = joblib.load(model)
            if bundle.get("frozen") != frozen:
                raise ValueError("pretrained model belongs to another frozen configuration")
        self.prepared = PreparedV4Detector(bundle, self.profile)
        components = policy_components(self.prepared.name)
        with_if = any("L4" in name for name in components)
        with_ae = with_if or any("AE" in name for name in components)
        self.signals = TargetSignals(with_ae=with_ae, with_if=with_if)

    def _transform(self, frame):
        result = self.signals.transform(frame)
        wide = result.select_dtypes("float64").columns
        result[wide] = result[wide].astype(np.float32)
        return result

    def fit(self, train, valid):
        self.signals.fit(train)
        self.prepared.fit(self._transform(train), self._transform(valid))
        self.history_end = max(train.t.max(), valid.t.max())
        return self

    def alerts(self, frame):
        if len(frame) and frame.t.min() <= self.history_end:
            raise ValueError("scoring rows must follow the history and calibration periods")
        return self.prepared.alerts(self._transform(frame), 3)


def explain_alerts(frame, flags, entity, score, change_parts=None):
    parts = entity.parts(frame)
    lines, texts, fallback = [], pd.Series("", index=frame.index), 0
    for position in np.flatnonzero(flags):
        row = frame.iloc[position]
        row_parts = {name: float(values[position]) for name, values in parts.items()}
        selected = [name for name, value in row_parts.items() if value >= 4]
        # Direct boolean observations are useful even if a pooled tail is small.
        selected += [name for name in ("receipt_payer_mismatch", "payee_not_on_master", "payroll_after_leave",
                                      "payroll_off_calendar", "refund_to_foreign_account", "offquarter_writeoff")
                     if float(row.get(name, 0)) > 0]
        found = rule_observations(row)[:2] + observations(row, dict.fromkeys(selected))[:2] + entity_observations(row, row_parts)[:2]
        if change_parts:
            from .explain_v5 import change_observations
            found += change_observations(row, {n: float(v[position]) for n, v in change_parts.items()}, top=1)
        if not found:
            fallback += 1
            found = [{"feature": "ranking_only", "text": "Giao dịch được ưu tiên rà soát theo điểm xếp hạng; chưa có lý do nghiệp vụ cụ thể đủ bằng chứng.",
                      "evidence": {"ranking_score": float(score[position])}}]
        for item in found:
            if not check(item["text"], item["evidence"])["ok"]:
                raise ValueError("numeric explanation evidence check failed")
        texts.iloc[position] = " | ".join(dict.fromkeys(x["text"] for x in found))
        lines.append({"company_id": row.company_id, "transaction_id": row.transaction_id, "observations": found})
    return texts, lines, fallback


def run(data, out, config, week, company_id=None, profile=None):
    out, data = Path(out), Path(data)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"refusing to overwrite a prior operational run: {out}")
    out.mkdir(parents=True, exist_ok=True)
    if company_id is None:
        ids = pd.read_csv(data / "transactions.csv", dtype=str, usecols=["company_id"]).company_id.unique()
        if len(ids) != 1:
            raise ValueError("--company is required for input containing multiple companies")
        company_id = str(ids[0])
    timer, times = time.perf_counter(), {}
    try:
        frame, input_report, input_hashes = build(data, out / "input_snapshot", company_id, week)
    except ReducedInput:
        from .reduced_v4 import run_reduced
        return run_reduced(data, out, config, week, company_id)
    times["input_features_rules"] = time.perf_counter() - timer
    start, end = (x.tz_localize(None) for x in week_bounds(week))
    history = frame[frame.t < start]
    cfg = json.loads(Path(config).read_text(encoding="utf-8")) if isinstance(config, (str, Path)) else dict(config)
    if len(history) < cfg.get("minimum_history_rows", 20):
        raise ValueError("insufficient history for the frozen policy; day-one peer mode is not yet validated")
    calibration_start = start - pd.Timedelta(days=cfg.get("calibration_days", 90))
    train, valid = history[history.t < calibration_start], history[history.t >= calibration_start]
    if train.empty or valid.empty:
        raise ValueError("history does not cover separate training and calibration periods")
    deploy = frame[(frame.t >= start) & (frame.t < end)].reset_index(drop=True)
    if deploy.empty:
        raise ValueError("no transactions in the requested week")
    timer = time.perf_counter()
    det = OperationalV4Detector(config, profile).fit(train, valid)
    flags, score, _ = det.alerts(deploy)
    v6_status, v6_score, v6_sha = "not_configured", None, None
    if cfg.get("v6_model_path"):             # secondary information only: never changes which rows are alerted
        try:
            from .v6_model import V6Scorer
            base_v6 = Path(config).resolve().parent if isinstance(config, (str, Path)) else ROOT
            scorer = V6Scorer.load((base_v6 / cfg["v6_model_path"]).resolve(), cfg.get("v6_model_sha256"))
            v6_score, v6_sha = scorer.score(det._transform(deploy)), scorer.sha256
            v6_status = "used_as_secondary_score"
        except Exception as error:           # degrade gracefully (e.g. cold profile lacks the unsupervised columns)
            v6_status = f"skipped: {type(error).__name__}"
    v6_columns = {} if v6_score is None else {"v6_score": v6_score[flags], "v6_percentile": V6Scorer.percentile(v6_score)[flags]}
    from .feedback_v4 import vectors, aggregate, apply as apply_feedback
    feedback_matrix = vectors(deploy, det.signals.entity)
    feedback_sha256 = None
    if cfg.get('feedback_path'):
        base_path = Path(config).resolve().parent if isinstance(config, (str, Path)) else ROOT
        feedback_path = (base_path / cfg['feedback_path']).resolve()
        feedback_sha256 = sha(feedback_path)
        if feedback_sha256 != cfg.get('feedback_sha256'):
            raise ValueError('feedback artifact checksum differs from configuration')
        artifact = json.loads(feedback_path.read_text(encoding='utf-8'))
        flags, score = apply_feedback(deploy, score, deploy.rule_hard.to_numpy() > 0,
                                      feedback_matrix, artifact, company_id, start.tz_localize('Asia/Ho_Chi_Minh'))
    times["fit_target_and_score"] = time.perf_counter() - timer
    timer = time.perf_counter()
    change_parts, change_status = None, "used"
    try:   # v5 change observations: explanations only, never alter ranking or alerts
        from .change_ops import ChangeExplainer, lenient_change_features
        cf = lenient_change_features(out / "input_snapshot")
        keep = [c for c in cf.columns if c not in deploy.columns or c == "transaction_id"]
        hist = train[["transaction_id", "txn_type"]].merge(cf[keep], on="transaction_id", how="left").fillna(0)
        deploy = deploy.merge(cf[keep], on="transaction_id", how="left")
        deploy[keep[1:]] = deploy[keep[1:]].fillna(0)
        change_parts = ChangeExplainer().fit(hist).parts(deploy)
    except Exception as error:   # explanations degrade gracefully; record why
        change_status = f"skipped: {type(error).__name__}"
    deploy["explanation_vi"], evidence, fallback = explain_alerts(deploy, flags, det.signals.entity, score, change_parts)
    cases = build_cases(deploy, flags, score)
    cases['feedback_vector'] = aggregate(cases, deploy, feedback_matrix)
    hard_ids = set(deploy.loc[flags & (deploy.rule_hard.to_numpy() > 0), "transaction_id"])
    if len(cases):
        hard = cases.transaction_ids.map(lambda ids: bool(hard_ids.intersection(ids)))
        cases.loc[hard, "priority"] = "cao_nhat"
    cases["action_vi"] = cases.priority.map({"cao_nhat": "Ưu tiên đối chiếu chứng từ và người nhận tiền trong ngày.",
                                           "cao": "Đối chiếu chứng từ và phê duyệt trong hai ngày.",
                                           "trung_binh": "Rà soát trong tuần và ghi nhận kết luận."})
    cases["iso_week"] = week
    queue = to_case_queue(cases)
    rule_lookup = deploy.set_index("transaction_id").rule_ids.to_dict()
    queue["rule_ids"] = cases.transaction_ids.map(lambda ids: "|".join(sorted({r for tid in ids for r in str(rule_lookup.get(tid, "")).split("|") if r})))
    queue["iso_week"] = week
    cases['rule_ids'] = queue.rule_ids
    cases["sla_due_at"], cases["sla_basis"] = queue.sla_due_at, queue.sla_basis
    cases["explanation_vi"] = cases.reason
    cases.assign(transaction_ids=cases.transaction_ids.map(json.dumps), feedback_vector=cases.feedback_vector.map(json.dumps)).to_csv(out / "cases.csv", index=False, encoding="utf-8-sig")
    queue.to_csv(out / "case_queue.csv", index=False, encoding="utf-8-sig")
    deploy.loc[flags, ["company_id", "transaction_id", "posted_at", "txn_type", "amount_vnd", "rule_ids", "explanation_vi"]].assign(ranking_score=score[flags], **v6_columns).to_csv(out / "alerts.csv", index=False, encoding="utf-8-sig")
    with (out / "explanations.jsonl").open("w", encoding="utf-8") as stream:
        for line in evidence:
            stream.write(json.dumps(clean(line), ensure_ascii=False, allow_nan=False) + "\n")
    times["explain_and_export"] = time.perf_counter() - timer
    report = {"company_id": company_id, "week": week, "profile": det.profile, "chosen_policy": det.prepared.name,
              "budget_per_company_week": 3, "rows_history": len(history), "rows_scored": len(deploy), "alert_rows": int(flags.sum()),
              "cases": len(cases), "model_sha256": det.model_sha256, "model_version": det.model_sha256 or f"cold:{det.prepared.name}",
              "training_data_kind": "none" if det.profile == "cold" else "synthetic", "input_data_kind": cfg.get("input_data_kind", "unspecified"),
              "explanation_numbers_supported": True, "ranking_only_explanations": fallback,
              "priority_score_is_fraud_probability": False, "input_report": input_report,
              "change_observations": change_status, "v6_secondary_score": v6_status, "v6_model_sha256": v6_sha,
              "timing_seconds": times, "median_alert_ranking_score": float(np.median(score[flags])) if flags.any() else None}
    report['feedback_sha256'] = feedback_sha256
    report['policy_variant'] = 'unvalidated_feedback' if feedback_sha256 else 'frozen'
    if feedback_sha256:
        report['chosen_policy'] = f'feedback({det.prepared.name})'
        report['model_version'] = f"{report['model_version']}:feedback:{feedback_sha256}"
    report["feature_psi"] = {col: population_stability(train[col], deploy[col]) for col in
                             ("log_amount", "price_logratio", "p_logratio", "receipt_days_late", "customer_amount_logz") if col in train}
    report["psi_reference_rows"], report["psi_current_rows"] = len(train), len(deploy)
    code = {str(path.relative_to(ROOT)): sha(path) for directory in ("agent2", "sme_fraud") for path in (ROOT / directory).rglob("*.py")}
    manifest = {"created_at": dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(), "config": cfg,
                "code_sha256": code, "input_snapshot_sha256": input_hashes, "model_sha256": det.model_sha256,
                'feedback_sha256': feedback_sha256,
                "history_end": det.history_end.isoformat(), "week": week, "company_id": company_id,
                "labels_read": False}
    report['model_manifest'] = {'model_sha256': det.model_sha256, 'feedback_sha256': feedback_sha256,
                                'policy': report['chosen_policy'], 'frozen_code_hashes': cfg['frozen']['hashes']}
    for name, payload in (("report.json", report), ("run_manifest.json", manifest)):
        (out / name).write_text(json.dumps(clean(payload), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report, cases
