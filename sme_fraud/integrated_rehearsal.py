"""Fresh synthetic rules -> guarded IF shadow -> review app -> dry-run notifications.

Reuses the attested v4 cache and model, never fits, and keeps all earlier runs intact.
The operational app receives a copy of the new baseline, never IF study selections.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
import gc
import http.client
import json
from pathlib import Path
import shutil
import threading
import time
from unittest.mock import patch

from .feature_contract import sha, validate_cache
from .shadow_scoring import guarded, source_checks

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'integrated-rehearsal-20261028-v1'
TAGS = ('001', '003')
FORBIDDEN = {'labels.csv', 'splits.csv', 'oracle.json', 'control_oracle.jsonl'}
NOW = '2026-10-28T10:00:00+07:00'
CUTOFF = '2025-12-31T23:59:59+07:00'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def rows(path):
    import csv
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def jsonl(path, values):
    with Path(path).open('w', encoding='utf-8') as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False)+'\n')


def fresh_output(output, inputs):
    output = guarded(output)
    if output.exists():
        raise FileExistsError('Use a fresh integration workspace; existing runs cannot be overwritten')
    for source in inputs:
        source = guarded(source)
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('Integration workspace must be separate from its inputs')
    if output == ROOT or output.is_relative_to(ROOT/'data'):
        raise ValueError('Use a new reports workspace, outside source datasets')
    for parent in (output, *output.parents):
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
            raise ValueError('Linked integration workspace rejected')
    return output


@contextmanager
def no_truth_access():
    original = Path.open
    attempted = []

    def checked(path, *args, **kwargs):
        resolved = path.resolve()
        if (resolved.name in FORBIDDEN or 'sealed_truth' in resolved.parts
                or any(p.casefold() in {'005', 'sme_fraud_005'} for p in resolved.parts)):
            attempted.append(str(resolved))
            raise AssertionError('Truth/split/holdout access is forbidden during integration')
        return original(path, *args, **kwargs)

    with patch.object(Path, 'open', checked):
        yield attempted


def copy_cache(source, target):
    """Copy only manifest-attested CSV inputs, preserving the original provenance bytes."""
    source, target = guarded(source), guarded(target)
    metadata = read_json(source/'manifest.json')
    if metadata.get('is_synthetic') is not True or metadata.get('role') != 'reporting':
        raise ValueError('Integration accepts attested synthetic reporting sources only')
    validate_cache(metadata)
    checks = source_checks(source, metadata)
    if any(not n.endswith('.csv') or n in FORBIDDEN for n in checks):
        raise ValueError('Only declared source/cache CSV files may be copied')
    target.mkdir(parents=True, exist_ok=False)
    for name in checks:
        shutil.copyfile(source/name, target/name)
    shutil.copyfile(source/'manifest.json', target/'manifest.json')
    if source_checks(target, metadata) != checks or sha(source/'manifest.json') != sha(target/'manifest.json'):
        raise ValueError('Source copy changed the frozen cache or its provenance')
    return dict(files=len(checks), manifest_sha256=sha(target/'manifest.json'),
                feature_contract_fingerprint=metadata['feature_contract']['fingerprint'],
                raw_values_and_timestamps_modified=False, features_rebuilt=False)


def baseline_delta(prior, current):
    before = {r['transaction_id']: r for r in rows(prior/'rule_scores.csv')}
    after = {r['transaction_id']: r for r in rows(current/'rule_scores.csv')}
    if before.keys() != after.keys():
        raise ValueError('Old and new baseline transaction universes differ')
    fields = ('rule_score', 'base_score', 'recurrence_points', 'hard_trigger', 'operational_alert')
    changed = [dict(transaction_id=tid, before={k:before[tid][k] for k in fields},
                    after={k:after[tid][k] for k in fields}) for tid in sorted(before)
               if any(before[tid][k] != after[tid][k] for k in fields)]
    def counts(directory):
        with (directory/'rule_hits.jsonl').open(encoding='utf-8') as stream:
            hits = [json.loads(line) for line in stream if line.strip()]
        return dict(cases=len(rows(directory/'case_queue.csv')), hits=len(hits),
                    rule_hit_counts=dict(Counter(r['rule_id'] for r in hits)))
    old_cases = {r['case_id']: r['scope_hash'] for r in rows(prior/'case_queue.csv')}
    new_cases = {r['case_id']: r['scope_hash'] for r in rows(current/'case_queue.csv')}
    return dict(before=counts(prior), after=counts(current), changed_transaction_scores=changed,
                added_case_ids=sorted(new_cases.keys()-old_cases.keys()),
                removed_case_ids=sorted(old_cases.keys()-new_cases.keys()),
                changed_shared_case_scopes=sorted(k for k in old_cases.keys() & new_cases.keys() if old_cases[k] != new_cases[k]),
                interpretation='Changes describe deterministic software behavior, not fraud accuracy')


def accounting_tables(source, tables, metadata):
    extra = {}
    for name in ('account_flow_edges', 'document_links', 'invoices'):
        filename = name+'.csv'
        entry = metadata['files'].get(filename)
        if not entry or sha(source/filename) != entry['sha256']:
            raise ValueError('Accounting source missing or changed: '+filename)
        extra[name] = rows(source/filename)
    return dict(tables, **extra)


def score_baseline(source, target, plan_path, prior):
    from .rules import load_inputs, score_rules
    from .case_queue import review_queue, operational_members, cash_information_members
    from .source_snapshot import inspect_sources
    from .generate import write_csv
    from .a5_coverage import write_coverage
    from .threshold_artifacts import write_parameters
    from .audit_accounting import check_accounting
    from .sync_entity_graph import sync as sync_graph
    from .sync_dynamic_thresholds import sync as sync_thresholds
    from .dynamic_thresholds import ThresholdPolicy

    target.mkdir(parents=True)
    tables, features, metadata = load_inputs(source)
    accounting = check_accounting(accounting_tables(source, tables, metadata))
    result = score_rules(tables, config=read_json(plan_path)['rule_config'], features=features)
    result['evidence_findings'].extend(inspect_sources(tables, CUTOFF))
    cases, events = review_queue(result, tables)
    members = {t for c in cases if c['case_type'] != 'information_request' for t in json.loads(c['transaction_ids'])}
    gaps = {t for c in cases if c['case_type'] == 'information_request' for t in json.loads(c['transaction_ids'])}
    if members != operational_members(result) or gaps != cash_information_members(result)-members:
        raise AssertionError('Baseline queue membership does not match operational rule evidence')
    for name, data in (('rule_scores', result['scores']), ('case_queue', cases), ('case_events', events)):
        clean = [{k:v for k,v in row.items() if k != 'known_risky_prior_ids'} for row in data]
        fields = list(dict.fromkeys(k for row in clean for k in row))
        write_csv(target/(name+'.csv'), clean, fields)
    for name, data in (('rule_hits', result['hits']), ('batch_events', result['batch_events']),
                       ('evidence_findings', result['evidence_findings'])):
        jsonl(target/(name+'.jsonl'), data)
    write_json(target/'rule_config.json', result['config'])
    write_json(target/'rule_coverage.json', result['coverage'])
    write_json(target/'accounting_validation.json', accounting)
    write_coverage(target, result)
    write_parameters(target, result['dynamic_parameters'], result['dynamic_policy'], result['dynamic_source_summary'])
    graph = sync_graph(source, target/'entity_graph', CUTOFF)
    graph_repeat = sync_graph(source, target/'entity_graph', CUTOFF)
    thresholds = sync_thresholds(source, target/'thresholds', CUTOFF, policy=ThresholdPolicy.from_config(result['config']))
    threshold_repeat = sync_thresholds(source, target/'thresholds', CUTOFF, policy=ThresholdPolicy.from_config(result['config']))
    if graph_repeat['changed'] or threshold_repeat['changed']:
        raise AssertionError('Graph/threshold synchronization is not idempotent')
    delta = baseline_delta(prior, target)
    write_json(target/'comparison_previous.json', delta)
    files = {p.name:sha(p) for p in target.iterdir() if p.is_file()}
    write_json(target/'predictions_frozen.json', dict(files=files, plan_sha256=sha(plan_path),
        source_manifest_sha256=sha(source/'manifest.json'), oracle_joined=False,
        financial_fraud_labels_loaded=False, integration_version=VERSION))
    summary = dict(transactions=len(tables['transactions']), cases=len(cases), hits=len(result['hits']),
                   operational_members=len(members), information_request_members=len(gaps),
                   changed_transaction_scores=len(delta['changed_transaction_scores']),
                   accounting=accounting, graph=graph, thresholds=thresholds,
                   graph_and_threshold_repeat_unchanged=True)
    del tables, features, result, cases, events
    gc.collect()
    return summary


def fake_people(company):
    from .review_roles import ReviewPrincipal
    names = (('ACC', 'accountant', 'Kế toán viên'), ('CHIEF', 'chief_accountant', 'Kế toán trưởng'),
             ('DIR', 'director', 'Giám đốc'))
    return [ReviewPrincipal('SIM_'+prefix+'_'+company, 'SIM_PERSON_'+prefix+'_'+company,
                            'MÔ PHỎNG · '+name+' '+company, role, (company,)) for prefix, role, name in names]


def dry_config(companies, base_port=8821):
    recipients = {}
    for company in companies:
        recipients[company] = [dict(user_id=p.user_id, person_id=p.person_id, role=p.role,
            display_name=p.display_name, channels=dict(email=[p.user_id.lower()+'@example.invalid'],
                                                     zalo=[p.user_id])) for p in fake_people(company)]
    return dict(dry_run=True, replay_existing=True, daily_budget=5,
                case_url=f'http://127.0.0.1:{base_port}/', role_recipients=recipients)


def prepare_app(output):
    from .review_store import ReviewStore
    from .review_workflow import TwoStageReview
    app = output/'app'
    if app.exists():
        raise FileExistsError('An app workspace already exists')
    app.mkdir()
    target = app/'snapshots'
    for tag in TAGS:
        source = output/'baseline'/('sme_fraud_'+tag)
        destination = target/source.name
        destination.mkdir(parents=True)
        for name in read_json(source/'predictions_frozen.json')['files']:
            shutil.copyfile(source/name, destination/name)
    store = ReviewStore(output/'source', target, app/'review.sqlite3', scenarios=list(TAGS),
                        clock=lambda:datetime.fromisoformat(NOW))
    store.prepare()
    workflow = TwoStageReview(store)
    companies = sorted({r['company_id'] for r in store.metadata()['companies']})
    config = dry_config(companies)
    write_json(app/'notifications.dry_run.json', config)
    write_json(app/'integration_qa.json', dict(kind=VERSION, is_synthetic=True, source_root=str(output/'source'),
        baseline_plan_sha256=sha(output/'baseline/evaluation_plan.json'), simulated_clock=NOW,
        independent_reviews=0, actual_review_minutes=None, real_accounts_created=0,
        if_operational_queue_write=False, external_messages_sent=0))
    with store.connection() as db:
        case_rows = [dict(r) for r in db.execute('SELECT scenario,case_id,data FROM cases')]
    for row in case_rows:
        detail = store.detail(row['scenario'], row['case_id'])
        if detail['case']['case_id'] != row['case_id']:
            raise AssertionError('App detail binding differs from the new baseline')
    write_json(app/'loaded_cases.json', dict(cases=len(case_rows), all_details_loaded=True))
    return store, workflow, config


class HttpClient:
    """Loopback API checks; never controls browser UI."""
    def __init__(self, server):
        self.server = server
        self.csrf = self.request('GET', '/api/meta')['csrf_token']

    def request(self, method, path, body=None, expected=200):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=90)
        headers = {'Content-Type':'application/json', 'X-CSRF-Token':getattr(self, 'csrf', '')}
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            payload = response.read()
            if response.status != expected:
                raise AssertionError((path, response.status, payload[:350]))
            return json.loads(payload) if 'application/json' in response.getheader('Content-Type', '') else payload
        finally:
            connection.close()


def verify_app(output, store, workflow, config):
    from .review_server import make_server
    from .notifications import Notifications
    from .notification_audit import history as delivery_history
    from .review_roles import workflow_events
    from .feedback import read_audit
    from .notification_channels import TRANSPORTS
    actors = fake_people('C001')
    service = Notifications(store, config)
    servers, clients = [], []
    for actor in (*actors, None):
        server = make_server(store, port=0, qa=True, instance_id=VERSION,
            notifications=service, review_workflow=workflow,
            identity_provider=lambda request, p=actor:p)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        clients.append(HttpClient(server))
    acc, chief, director, anonymous = clients
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(dict(check=name, passed=True))
    try:
        meta = acc.request('GET', '/api/meta')
        check('both_new_cohorts_loaded', meta['scenarios'] == list(TAGS))
        for tag in TAGS:
            check('health_'+tag, acc.request('GET', '/api/health')['instance_id'] == VERSION)
            check('queue_'+tag, bool(acc.request('GET', '/api/cases?scenario='+tag)['items']))
            check('coverage_'+tag, len(acc.request('GET', '/api/coverage?scenario='+tag)) >= 35)
            check('a5_'+tag, bool(acc.request('GET', '/api/a5-coverage?scenario='+tag)))
        for filename in ('/', '/app.js', '/styles.css', '/review_workflow.js', '/case_graph.js'):
            check('asset_'+filename, bool(acc.request('GET', filename)))
        with store.connection() as db:
            candidates = [json.loads(r[0]) for r in db.execute(
                "SELECT data FROM cases WHERE scenario='003' AND company_id='C001' ORDER BY priority DESC,score DESC,opened_at,case_id")]
            other = db.execute("SELECT case_id FROM cases WHERE scenario='003' AND company_id='C002' LIMIT 1").fetchone()[0]
        if len(candidates) < 3:
            raise AssertionError('Need three existing baseline cases for independent integration stories')
        selected = candidates[:3]
        write_json(output/'app/browser_cases.json', dict(scenario='003', company_id='C001',
            api_story=selected[0]['case_id'], browser_story=selected[1]['case_id'],
            missing_documents_story=selected[2]['case_id'], simulated_outcomes_only=True))
        case = selected[0]['case_id']
        path = '/api/case?scenario=003&id='+case
        detail = acc.request('GET', path)
        check('evidence_and_scope_from_latest_snapshot', detail['case']['case_id'] == case and bool(detail['hits']))
        acc.request('GET', '/api/case?scenario=003&id='+other, expected=403)
        check('company_scope_enforced', True)
        anonymous.request('GET', '/api/notifications?scenario=003', expected=403)
        check('anonymous_notification_history_blocked', True)

        def body(client, decision='information_gap'):
            state = client.request('GET', path)['review_workflow']
            return dict(scenario='003', case_id=case, decision=decision,
                reason='MÔ PHỎNG TÍCH HỢP: kiểm tra luồng kỹ thuật; không phải kết luận kế toán.',
                missing_evidence='MÔ PHỎNG: cần người thật đối chiếu chứng từ nguồn.',
                active_minutes=1, timing_method='measured_stopwatch',
                expected_event_hash=state['latest_event_hash'], expected_scope_hash=state['case_scope_hash'])

        def preview():
            return chief.request('POST', '/api/notifications/preview', dict(scenario='003'))

        # A transport call is a test failure even if a configuration regression enables it.
        from contextlib import ExitStack
        with ExitStack() as stack:
            for channel in TRANSPORTS:
                stack.enter_context(patch.dict(TRANSPORTS, {channel:lambda *a,**k:(_ for _ in ()).throw(AssertionError('External transport prohibited'))}))
            check('submit_accountant', acc.request('POST', '/api/review-workflow/primary', body(acc))['stage'] == 'pending_final')
            preview()
            acc.request('POST', '/api/review-workflow/finalize', body(acc), expected=403)
            check('accountant_cannot_finalize', True)
            stale = body(chief)
            check('chief_returns', chief.request('POST', '/api/review-workflow/return', body(chief))['stage'] == 'returned')
            preview()
            check('accountant_resubmits', acc.request('POST', '/api/review-workflow/primary', body(acc))['stage'] == 'pending_final')
            chief.request('POST', '/api/review-workflow/finalize', stale, expected=409)
            check('stale_finalization_rejected', True)
            preview()
            check('director_finalizes_gap', director.request('POST', '/api/review-workflow/finalize', body(director))['stage'] == 'finalized')
            preview()
            check('information_gap_stays_open', acc.request('GET', path)['case']['status'] != 'closed')
            with store.connection() as db:
                before = [tuple(r) for r in db.execute('SELECT job_id,status,attempts FROM notification_outbox ORDER BY job_id')]
            preview()
            with store.connection() as db:
                after = [tuple(r) for r in db.execute('SELECT job_id,status,attempts FROM notification_outbox ORDER BY job_id')]
            check('repeat_preview_no_duplicate_jobs_or_attempts', before == after)
        with store.connection() as db:
            events = workflow_events(db)
            audit = delivery_history(db)
            jobs = [dict(r) for r in db.execute('SELECT * FROM notification_outbox')]
            allocations = [dict(r) for r in db.execute('SELECT * FROM notification_allocations')]
            stages = Counter(e['kind'] for e in events)
        feedback = read_audit(store.report('003')/'feedback_audit.jsonl')
        check('workflow_hash_chain_verified', len(events) == 5)
        check('only_simulated_delivery', bool(jobs) and all(j['mode']=='dry_run' and j['status'] in {'simulated','cancelled'} and j['attempts'] <= 1 for j in jobs))
        check('all_recipients_are_fake_and_company_scoped', all(j['company_id']=='C001' and
            (j['recipient'].endswith('@example.invalid') or j['recipient'].startswith('SIM_')) for j in jobs))
        check('notification_budget_preserved', max(Counter((r['day'],r['scenario'],r['company_id']) for r in allocations).values(), default=0) <= 5)
        for kind, prefix in (('review_submitted','sim_chief_'), ('review_returned','sim_acc_'), ('review_finalized','sim_acc_')):
            matched = [j for j in jobs if j['kind']==kind]
            check('recipient_'+kind, bool(matched) and all(j['recipient'].lower().startswith(prefix) for j in matched))
        write_json(output/'app/api_checks.json', checks)
        write_json(output/'app/workflow_trace.json', dict(is_synthetic=True, simulated_minutes_only=True,
            independent_reviews=0, actual_review_minutes=None, events=events, feedback=feedback))
        write_json(output/'app/notification_verification.json', dict(jobs=len(jobs), delivery_events=len(audit),
            kinds=dict(Counter(j['kind'] for j in jobs)), statuses=dict(Counter(j['status'] for j in jobs)),
            hash_chain_verified=True, max_attempts=max(j['attempts'] for j in jobs),
            external_messages_sent=0, repeat_idempotent=True, api_checks=len(checks)))
        return dict(api_checks=len(checks), app_cases=read_json(output/'app/loaded_cases.json')['cases'],
                    workflow_event_kinds=dict(stages), simulated_jobs=len(jobs), external_messages_sent=0)
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def run(output, prior, protocol):
    from .rules import DEFAULT_CONFIG
    from .train_source_model import IsolationForest
    from .audit_model_windows import audit_model_windows
    from .compare_shadow import run_comparison
    from .audit_if_coverage import audit_coverage
    from .compare_if_discovery import run_discovery
    prior, protocol = guarded(prior), guarded(protocol)
    output = fresh_output(output, (prior, protocol.parent))
    output.mkdir(parents=True)
    baseline = output/'baseline'
    baseline.mkdir()
    code = {p.relative_to(ROOT).as_posix():sha(p) for directory in ('sme_fraud','review_ui')
            for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.js','.css','.html'}}
    plan = dict(version=VERSION, is_synthetic=True, cohorts=list(TAGS), source=str(prior/'cache'),
        model_root=str(prior/'models'), evaluation_scope=read_json(prior/'evaluation_scope.json'),
        models_fitted=0, if_mode='shadow', operational_if_admission=False, threshold_retuned=False,
        rule_config=DEFAULT_CONFIG, code_sha256=code, protocol_sha256=sha(protocol),
        baseline_source_cutoff=CUTOFF, app_clock=NOW, app_daily_slots=5, app_daily_minutes=120,
        simulated_reviews_only=True, real_accounts_created=0, external_messages_sent=0,
        independent_reviews=0, actual_review_minutes=None,
        limitations=['Synthetic integrated rehearsal, not real-source acceptance or independent ML benefit',
                    'IF comparison/reranking is diagnostic; guarded discovery is the primary policy',
                    'App imports the baseline only; no IF study outcome is a business conclusion'])
    write_json(output/'evaluation_plan.json', plan)
    write_json(baseline/'evaluation_plan.json', plan)
    reports = []
    start = time.monotonic()
    try:
        with no_truth_access() as attempted, patch.object(IsolationForest, 'fit', side_effect=AssertionError('No model fitting in integrated replay')):
            for tag in TAGS:
                cohort = 'sme_fraud_'+tag
                print(tag+': copying verified v4 source/cache; original remains untouched', flush=True)
                source = output/'source'/cohort
                cache = copy_cache(prior/'cache'/cohort, source)
                model = prior/'models'/cohort/'isolation_forest.joblib'
                training = read_json(model.parent/'training_run.json')
                if sha(model) != training['model_sha256']:
                    raise ValueError('Existing frozen model no longer matches its training record')
                temporal = output/'temporal'/cohort
                audit_model_windows(source, model, temporal, model_sha256=training['model_sha256'])
                print(tag+': scoring latest rules + graph + rolling A5; rebuilding queue', flush=True)
                scored = score_baseline(source, baseline/cohort, baseline/'evaluation_plan.json', prior/'baseline'/cohort)
                comparison = output/'comparison'/cohort
                print(tag+': evaluation-only IF scoring and equal-budget diagnostic comparison', flush=True)
                compared = run_comparison(source, baseline/cohort, model, comparison,
                    model_sha256=training['model_sha256'], scope=plan['evaluation_scope'])
                coverage_dir = output/'coverage'/cohort
                coverage = audit_coverage(source, baseline/cohort, comparison, temporal, coverage_dir)
                print(tag+': running discovery with zero-additional-delay guard on the NEW baseline', flush=True)
                discovery = run_discovery(source, baseline/cohort, comparison, coverage_dir,
                    output/'discovery'/cohort, protocol=protocol)
                for scenario in discovery['scenarios']:
                    if (scenario['mandatory_displacements'] or scenario['budget_violations']
                            or scenario['max_common_baseline_delay_days'] or scenario['unmatched_frozen_historical_work']):
                        raise AssertionError('Guarded shadow violated baseline reservation or shared capacity')
                reports.append(dict(cohort=tag, cache=cache, baseline=scored,
                    model_sha256=training['model_sha256'], evaluation_rows=compared['shadow_rows'],
                    coverage=coverage, discovery=discovery))
                write_json(output/(cohort+'.json'), reports[-1])
            print('Preparing the review app from copies of the new baseline only', flush=True)
            store, workflow, config = prepare_app(output)
            app = verify_app(output, store, workflow, config)
        if attempted:
            raise AssertionError('Unexpected forbidden access attempt')
        if any(sha(ROOT/name) != value for name,value in code.items()):
            raise ValueError('Implementation changed during the integrated rehearsal')
        summary = dict(status='technical_integration_passed', version=VERSION, source_transactions=sum(r['baseline']['transactions'] for r in reports),
            cases=sum(r['baseline']['cases'] for r in reports), evaluation_rows=sum(r['evaluation_rows'] for r in reports),
            guarded_scenarios=sum(len(r['discovery']['scenarios']) for r in reports), app=app,
            models_fitted=0, threshold_retuned=False, if_mode='shadow', if_operational_queue_write=False,
            forbidden_access_attempts=attempted, holdout_005_loaded=False, source_timestamps_modified=False,
            real_accounts_created=0, independent_reviews=0, actual_review_minutes=None,
            ml_operational_benefit='not_proven', real_source_acceptance='awaiting_real_data',
            browser_acceptance='pending', seconds=round(time.monotonic()-start,3))
        write_json(output/'summary.json', summary)
        return summary
    except Exception as error:
        write_json(output/'status.failed.json', dict(status='failed', error_type=type(error).__name__,
            error=str(error), completed_cohorts=[r['cohort'] for r in reports]))
        raise


def serve(output, base_port=8821):
    from .review_store import ReviewStore
    from .review_workflow import TwoStageReview
    from .notifications import Notifications
    from .review_server import make_server
    output = guarded(output)
    app = output/'app'
    marker = read_json(app/'integration_qa.json')
    if (marker.get('kind') != VERSION or marker.get('is_synthetic') is not True
            or read_json(output/'summary.json')['status'] != 'technical_integration_passed'):
        raise ValueError('Only a successful synthetic integrated QA workspace may be served')
    if type(base_port) is not int or not 1024 <= base_port <= 65532:
        raise ValueError('Invalid loopback port range')
    store = ReviewStore(output/'source', app/'snapshots', app/'review.sqlite3', scenarios=list(TAGS),
        clock=lambda:datetime.fromisoformat(marker['simulated_clock']))
    store.prepare()
    workflow = TwoStageReview(store)
    config = read_json(app/'notifications.dry_run.json')
    if config.get('dry_run') is not True:
        raise ValueError('Integrated QA forbids live notifications')
    config['case_url'] = f'http://127.0.0.1:{base_port}/'
    servers = []
    try:
        for index, actor in enumerate((*fake_people('C001'), None)):
            service = Notifications(store, config)
            server = make_server(store, port=base_port+index, qa=True, instance_id=VERSION,
                notifications=service, review_workflow=workflow, identity_provider=lambda request,p=actor:p)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f'{actor.role if actor else "anonymous"}: http://127.0.0.1:{base_port+index}/', flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run','serve'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prior', type=Path, default=ROOT/'reports/rr09_ml_completion_20261024/ml_v4')
    parser.add_argument('--protocol', type=Path, default=ROOT/'examples/ml_if_discovery_shadow/delay_guard_protocol.json')
    parser.add_argument('--base-port', type=int, default=8821)
    args = parser.parse_args()
    if args.action == 'serve':
        serve(args.output, args.base_port)
    else:
        print(json.dumps(run(args.output, args.prior, args.protocol), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
