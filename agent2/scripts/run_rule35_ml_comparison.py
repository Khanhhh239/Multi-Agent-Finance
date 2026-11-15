"""Offline isolated evaluation: '35 rules' vs '35 rules + ML' for C001 & C002."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SHARED_SRC = ROOT.parent / 'shared' / 'finance_input' / 'src'
for path in (str(ROOT), str(SHARED_SRC), str(ROOT / 'tests')):
    if path not in sys.path:
        sys.path.insert(0, path)

from finance_input import AccessScope
from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.comparison_store import ComparisonStore
from sme_fraud.import_files import canonical, digest
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.review_store import ReviewStore
from sme_fraud.rule35_comparison import (
    make_rule35_plan,
    rule35_cases_for,
    rule35_report_for,
)
from sme_fraud.rule35_ml_eval_demo import (
    COMPANY_METHODS,
    EVAL_AS_OF,
    FIT_END,
    build_eval_source,
    build_fit_source,
    fit_config,
)
from sme_fraud.rule_snapshot import analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore


def _policy_payload(token):
    return dict(
        policy_version='1.0.0',
        principals=[
            dict(
                actor_id='eval-director',
                tenant_id='demo',
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                status='active',
                expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                memberships=[
                    dict(company_id=c, role='director', status='active', permissions=['data.import', 'model.fit'])
                    for c in ('C001', 'C002')
                ],
            )
        ],
    )


def _commit(store, scope, data, key):
    draft = store.upload(scope, canonical(data), f'{key}.json', key + '-upload')
    preview = store.preview(scope, draft['import_id'], 1)
    if preview['status'] == 'rejected':
        raise RuntimeError(f'Snapshot {key} rejected: {preview["errors"]}')
    req = {k: preview[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
    req.update(expected_revision=preview['revision'], acknowledge=True)
    return store.commit(scope, draft['import_id'], req, key + '-commit')['snapshot']


def run_evaluation(out_dir: Path, *, clean: bool = True):
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = out_dir / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)

    token = secrets.token_urlsafe(32)
    header = 'Bearer ' + token
    policy_path = out_dir / 'auth-policy.json'
    policy_path.write_bytes(canonical(_policy_payload(token)))
    auth = FileAuthorizer(policy_path)

    snapshots = SnapshotStore(out_dir / 'snapshots.sqlite3')
    models = MethodStore(out_dir / 'models.sqlite3')
    review_key = digest(b'rule35-eval-review-key-2026').encode()[:32]
    cmp_key = digest(b'rule35-eval-comparison-key-2026').encode()[:32]
    reviews = ReviewStore(out_dir / 'reviews.sqlite3', review_key)
    comparisons = ComparisonStore(out_dir / 'comparisons.sqlite3', cmp_key)

    bindings_rows = []
    fit_manifests = {}
    eval_bundles = {}
    eval_manifests = {}

    for company, ml_method in COMPANY_METHODS.items():
        scope = auth.authorize(header, company)
        fit_data = build_fit_source(company, tenant_id='demo')
        fit_snap = _commit(snapshots, scope, fit_data, f'fit-{company.lower()}')
        fit_manifests[company] = fit_snap

        rz_res = run_fit_job(snapshots, models, auth, header, company,
                             fit_config(fit_snap['snapshot_id'], 'robust_z'), f'fit-{company}-rz')
        if rz_res['job']['status'] != 'succeeded':
            raise RuntimeError(f'{company} robust_z fit failed: {rz_res}')

        ml_res = run_fit_job(snapshots, models, auth, header, company,
                             fit_config(fit_snap['snapshot_id'], ml_method), f'fit-{company}-{ml_method}')
        if ml_res['job']['status'] != 'succeeded':
            raise RuntimeError(f'{company} {ml_method} fit failed: {ml_res}')

        bindings_rows.append(dict(
            tenant_id='demo',
            company_id=company,
            statistics_artifact_id=rz_res['job']['artifact_id'],
            ml_artifacts={ml_method: ml_res['job']['artifact_id']},
        ))

        ev_data = build_eval_source(company, tenant_id='demo')
        ev_snap = _commit(snapshots, scope, ev_data, f'eval-{company.lower()}')
        eval_bundles[company] = ev_data
        eval_manifests[company] = ev_snap

    bindings_path = out_dir / 'analysis-bindings.json'
    bindings_path.write_bytes(canonical(dict(version=BINDINGS_VERSION, bindings=bindings_rows)))
    resources = AnalysisResources(model_db=out_dir / 'models.sqlite3', bindings_file=bindings_path)
    no_ml_resources = AnalysisResources()

    summary = dict(generated_at=datetime.now(timezone.utc).isoformat(), companies={})
    for company, ml_method in COMPANY_METHODS.items():
        scope = auth.authorize(header, company)
        ev_snap = eval_manifests[company]
        ev_data = eval_bundles[company]

        ana_with_ml = analyze_rule_snapshot(snapshots, scope, ev_snap['snapshot_id'], EVAL_AS_OF,
                                            technical=True, resources=resources)
        ana_no_ml = analyze_rule_snapshot(snapshots, scope, ev_snap['snapshot_id'], EVAL_AS_OF,
                                          technical=True, resources=no_ml_resources)

        assert ana_with_ml['native_reference_sha256'] == ana_no_ml['native_reference_sha256']
        assert [r['rule_coverage'] for r in ana_with_ml['rows']] == [r['rule_coverage'] for r in ana_no_ml['rows']]

        cases = rule35_cases_for(snapshots, scope, ana_with_ml, reviews, raw_data=ev_data)
        plan = make_rule35_plan(
            ana_with_ml,
            cases,
            ev_snap,
            ml_method=ml_method,
            raw_data=ev_data,
        )
        saved = comparisons.put(scope, plan)
        reloaded = comparisons.get(scope, ana_with_ml['analysis_id'])
        assert reloaded['plan_sha256'] == saved['plan_sha256']

        tech_report = rule35_report_for(reloaded['plan'], cases, redaction='technical')
        review_report = rule35_report_for(reloaded['plan'], cases, redaction='review')

        (reports_dir / f'{company}_technical_report.json').write_text(
            json.dumps(tech_report, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        (reports_dir / f'{company}_review_report.json').write_text(
            json.dumps(review_report, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        summary['companies'][company] = dict(
            ml_method=ml_method,
            fit_snapshot_id=fit_manifests[company]['snapshot_id'],
            eval_snapshot_id=ev_snap['snapshot_id'],
            analysis_id=ana_with_ml['analysis_id'],
            analysis_context_id=ana_with_ml['analysis_context_id'],
            plan_id=saved['plan_id'],
            plan_sha256=saved['plan_sha256'],
            report_sha256=tech_report['report_sha256'],
            baseline_selected=tech_report['baseline']['metrics']['selected'],
            combined_selected=tech_report['combined']['metrics']['selected'],
            ml_addition_summary=tech_report['ml_addition_summary'],
            coverage=tech_report['coverage'],
            baseline_rows=tech_report['baseline']['transactions'],
            added_rows=tech_report['added'],
        )

    (reports_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', default=str(ROOT.parent / '.runtime' / 'rule35-ml-eval'))
    args = parser.parse_args()
    result = run_evaluation(Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
