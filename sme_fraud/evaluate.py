"""Unsupervised Isolation Forest with a validation-only alert threshold."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

# Optional workspace installation; never modify the bundled runtime dependencies.
local_packages = Path(__file__).resolve().parents[1]/".runtime"/"site-packages"
if local_packages.exists():
    sys.path.insert(0, str(local_packages))

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve, roc_auc_score

from .features import FEATURE_DESCRIPTIONS
from .feature_contract import validate_cache, sha, digest, require_model


def wilson(successes, total):
    if not total:
        return None
    z = 1.95996398454
    p = successes/total
    scale = 1+z*z/total
    center = (p+z*z/(2*total))/scale
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/scale
    return [max(0,center-half), min(1,center+half)]


def threshold_metrics(y, scores, threshold):
    predicted = scores>=threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0,1]).ravel()
    return dict(threshold=float(threshold), alerts=int(tp+fp), alert_rate=float(predicted.mean()),
        tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn), precision=float(tp/(tp+fp)) if tp+fp else 0.,
        recall=float(tp/(tp+fn)) if tp+fn else 0., fpr=float(fp/(fp+tn)) if fp+tn else 0.,
        precision_wilson_95=wilson(tp,tp+fp), recall_wilson_95=wilson(tp,tp+fn),
        false_alerts_per_1000_normal=float(fp/(fp+tn)*1000) if fp+tn else 0.)


def evaluate(dataset: Path, output: Path, alert_budget=.003, seed=20261012, n_estimators=300):
    if not 0<alert_budget<.5:
        raise ValueError("Alert budget must be between 0 and .5")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty report: {output}")
    output.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((dataset/'manifest.json').read_text(encoding='utf-8'))
    contract = validate_cache(metadata)
    if sha(dataset / 'features.csv') != metadata['files']['features.csv']['sha256']:
        raise ValueError('Feature checksum differs from manifest')
    features = pd.read_csv(dataset/"features.csv", dtype={"transaction_id":"string"})
    columns = list(FEATURE_DESCRIPTIONS)
    if list(features.columns)!=["transaction_id", *columns]:
        raise ValueError("Features must exactly match the explicit allowlist; never pass IDs or labels to fit")
    split = pd.read_csv(dataset/"splits.csv", dtype="string").set_index("transaction_id")["split"]
    partitions = features["transaction_id"].map(split)
    if partitions.isna().any() or not features["transaction_id"].is_unique:
        raise ValueError("Missing split or duplicate observation IDs")
    x = features[columns].to_numpy(dtype=np.float32)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite feature values")
    masks = {name:partitions.eq(name).to_numpy() for name in ("train","validation","test")}
    model = IsolationForest(n_estimators=n_estimators, max_samples=min(2048,int(masks["train"].sum())),
                            contamination="auto", random_state=seed, n_jobs=-1)
    # No labels are used for selecting rows, fitting trees, or choosing thresholds.
    model.fit(x[masks["train"]])
    validation_scores = -model.score_samples(x[masks["validation"]])
    scores = -model.score_samples(x[masks["test"]])
    threshold = float(np.quantile(validation_scores, 1-alert_budget, method="higher"))
    artifact = dict(model=model, feature_columns=columns, threshold=threshold,
                     score_direction="higher_is_more_anomalous", seed=seed,dataset_version=metadata['version'],
                     expense_normalisation='641/642/6421/6422 -> ML expense group 642',
                     sklearn_version=sklearn.__version__, feature_contract_fingerprint=contract['fingerprint'],
                     training_feature_fingerprint=digest([features.loc[masks['train'], 'transaction_id'].tolist(),
                         hashlib.sha256(x[masks['train']].tobytes()).hexdigest()]))
    require_model(artifact, metadata, sklearn.__version__)
    joblib.dump(artifact, output/"isolation_forest.joblib")
    truth = pd.read_csv(dataset/"labels.csv", keep_default_na=False).set_index("transaction_id")
    test_ids = features.loc[masks["test"],"transaction_id"].tolist()
    ground = truth.loc[test_ids].reset_index()
    y = ground["is_fraud"].to_numpy(dtype=int)
    if len(np.unique(y))!=2:
        raise ValueError("Test must contain both fraud and normal observations")
    predicted = scores>=threshold
    report = dict(dataset=str(dataset), dataset_version=metadata['version'],seed=seed, sklearn_version=sklearn.__version__,
        train_rows=int(masks["train"].sum()), validation_rows=int(masks["validation"].sum()), test_rows=len(y),
        test_fraud_rows=int(y.sum()), test_prevalence=float(y.mean()), feature_count=len(columns),
        model_parameters=model.get_params(), threshold_policy="Unlabelled validation score quantile at fixed alert budget",
        requested_validation_alert_budget=alert_budget,
        average_precision=float(average_precision_score(y,scores)),
        random_ranking_ap_reference=float(y.mean()), roc_auc=float(roc_auc_score(y,scores)),
        selected_threshold=threshold_metrics(y,scores,threshold), threshold_sweep=[], top_k=[],
        per_fraud_type=[], per_variant=[], hard_negatives=[], case_recall={})
    for budget in (.001, .003, .005):
        cutoff = float(np.quantile(validation_scores,1-budget,method="higher"))
        report["threshold_sweep"].append(dict(validation_alert_budget=budget,**threshold_metrics(y,scores,cutoff)))
    order = np.argsort(-scores,kind="stable")
    for k in (25,50,100,250):
        k = min(k,len(y))
        tp = int(y[order[:k]].sum())
        report["top_k"].append(dict(k=k,true_positives=tp,precision=tp/k,recall=tp/int(y.sum())))
    for column, target in (("fraud_type","per_fraud_type"),("variant","per_variant")):
        for kind in sorted(ground.loc[ground["is_fraud"].eq(1),column].unique()):
            mask = ground[column].eq(kind).to_numpy() & (y==1)
            hits, support = int(predicted[mask].sum()),int(mask.sum())
            report[target].append(dict(name=kind,support=support,detected=hits,recall=hits/support,
                                       recall_wilson_95=wilson(hits,support)))
    hard_types = ground.loc[ground["is_fraud"].eq(0),"hard_negative_type"]
    for kind in sorted(set(hard_types)-{""}):
        mask = ground["hard_negative_type"].eq(kind).to_numpy() & (y==0)
        report["hard_negatives"].append(dict(name=kind,rows=int(mask.sum()),false_alerts=int(predicted[mask].sum()),
                                             fpr=float(predicted[mask].mean())))
    positive_cases = ground.loc[y==1,["case_id"]].copy()
    positive_cases["detected"] = predicted[y==1]
    cases = positive_cases.groupby("case_id")["detected"].any()
    report["case_recall"] = dict(fraud_cases=len(cases),detected_cases=int(cases.sum()),recall=float(cases.mean()),
                                 definition="Any labelled fraudulent observation in a case is alerted")
    ids_to_framework=pd.read_csv(dataset/'transactions.csv',usecols=['transaction_id','accounting_framework']).set_index('transaction_id')['accounting_framework']
    test_frameworks=ids_to_framework.loc[test_ids].to_numpy()
    report['per_accounting_framework']=[]
    for framework in ('TT133','TT200'):
        mask=test_frameworks==framework
        if mask.any():
            report['per_accounting_framework'].append(dict(framework=framework,rows=int(mask.sum()),
                fraud_rows=int(y[mask].sum()),**threshold_metrics(y[mask],scores[mask],threshold)))
    report["limitations"] = [
        "Synthetic scores do not establish real-world precision or measured fraud prevalence in Vietnamese SMEs.",
        "Repeated known SMEs across chronological splits; this is not an unseen-company benchmark.",
        "Small per-type support at 0.1%; Wilson intervals are descriptive row-level intervals, not cluster-robust intervals.",
        "Subtle fraud, first split payments and registry changes reported later may have no observable red flag at scoring time.",
        "Average precision is the non-interpolated AP metric, not trapezoidal area under the PR curve.",
        "Isolation Forest scores measure anomalies, not calibrated probabilities of fraud.",
    ]
    (output/"metrics.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    scored = pd.DataFrame(dict(transaction_id=test_ids,anomaly_score=scores,alert=predicted.astype(int)))
    scored.to_csv(output/"scores_test.csv",index=False,encoding="utf-8-sig")
    precision, recall, cutoffs = precision_recall_curve(y,scores)
    # Compact PR curve; thresholds correspond to the first len(precision)-1 points.
    indices = np.unique(np.linspace(0,len(cutoffs)-1,min(250,len(cutoffs))).astype(int))
    pd.DataFrame(dict(threshold=cutoffs[indices],precision=precision[indices],recall=recall[indices])).to_csv(
        output/"precision_recall_curve.csv",index=False,encoding="utf-8-sig")
    lines = ["# Kết quả Isolation Forest trên dữ liệu tổng hợp", "",
        f"Phiên bản dữ liệu: {metadata['version']}. Mã chi phí ML chuẩn hóa về nhóm 642; sổ cái giữ mã theo TT133/TT200.",
        f"Tập test: {len(y):,} quan sát; {y.sum():,} gian lận ({y.mean():.2%}).",
        f"Average precision (AP): {report['average_precision']:.4f}. Mốc tỷ lệ dương tính: {y.mean():.4f}.",
        "Ngưỡng cảnh báo lấy từ validation chưa gán nhãn; train không dùng nhãn.", "",
        "| Ngân sách validation | Precision test | Recall test | Cảnh báo sai | Tổng cảnh báo |",
        "| --- | ---: | ---: | ---: | ---: |"]
    for row in report["threshold_sweep"]:
        lines.append(f"| {row['validation_alert_budget']:.1%} | {row['precision']:.1%} | {row['recall']:.1%} | {row['fp']} | {row['alerts']} |")
    lines += ["", "| Loại gian lận | Số mẫu test | Phát hiện | Recall |", "| --- | ---: | ---: | ---: |"]
    for row in report["per_fraud_type"]:
        lines.append(f"| {row['name']} | {row['support']} | {row['detected']} | {row['recall']:.1%} |")
    lines += ["", "Kết quả chỉ đo trên mô phỏng. AP dùng `average_precision_score`; điểm IF không phải xác suất gian lận.",
              "Đọc `metrics.json` để xem khoảng Wilson, precision@k, recall theo vụ, biến thể và báo nhầm trên hard negatives."]
    (output/"report_vi.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/sme_fraud_003"))
    parser.add_argument("--output",type=Path,default=Path("reports/sme_fraud_003"))
    parser.add_argument("--alert-budget",type=float,default=.003)
    parser.add_argument("--seed",type=int,default=20261012)
    parser.add_argument("--trees",type=int,default=300)
    args = parser.parse_args()
    report = evaluate(args.data,args.output,args.alert_budget,args.seed,args.trees)
    print(json.dumps({"average_precision":report["average_precision"],"selected_threshold":report["selected_threshold"]},indent=2))


if __name__=="__main__":
    main()
