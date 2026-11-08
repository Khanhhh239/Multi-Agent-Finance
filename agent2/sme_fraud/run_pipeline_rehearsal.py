"""Replay existing 001/003 through the current pipeline and isolated HTTP review.

Predictions freeze before the synthetic source oracle is joined. Holdout 005
is fingerprinted as opaque files only, never loaded, scored or reviewed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import gc
import hashlib
import http.client
import json
from pathlib import Path
import threading
import time
import traceback
from unittest.mock import patch
from urllib.parse import urlencode

from .rules import DEFAULT_CONFIG, load_inputs, score_rules
from .features import build_features, FEATURE_DESCRIPTIONS
from .feature_contract import sha, digest
from .audit_accounting import check_accounting
from .generate import write_csv
from .case_queue import review_queue, operational_members, cash_information_members
from .source_snapshot import inspect_sources
from .real_source_acceptance import predictions_from_result, RULES
from .run_synthetic_readiness import metrics, key
from .threshold_sources import extract_observations
from .dynamic_thresholds import DynamicThresholds, ThresholdPolicy
from .threshold_artifacts import write_parameters
from .sync_dynamic_thresholds import sync as sync_thresholds, load_snapshot as load_thresholds
from .sync_entity_graph import sync as sync_graph, load_snapshot as load_graph
from .entity_graph import EntityGraph, node_id
from .review_store import ReviewStore, TZ
from .review_server import make_server
from .notifications import Notifications


TAGS = ('001', '003')
CUTOFF = '2025-12-31T23:59:59+07:00'
START = '2025-01-01T00:00:00+07:00'
REVIEWER = 'SIM_PIPELINE_BOT'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def read_csv(path):
    import csv
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def jsonl(path, rows):
    with Path(path).open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')


def input_guard(data_root, baseline, output):
    data_root, baseline, output = (Path(p).resolve() for p in (data_root, baseline, output))
    for source in (data_root, baseline):
        if output == source or source in output.parents or output in source.parents:
            raise ValueError('Rehearsal output must be separate from both input roots')
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Use a fresh output directory; existing results are preserved')
    for tag in TAGS:
        manifest = read_json(data_root/f'sme_fraud_{tag}'/'manifest.json')
        if manifest.get('role') != 'reporting' or manifest.get('is_synthetic') is not True:
            raise ValueError('This runner accepts existing synthetic reporting 001/003 only')
        if not (baseline/f'sme_fraud_{tag}'/'review_packet.csv').is_file():
            raise ValueError('The existing preselected source review packet is required')
    return data_root, baseline, output


def fingerprint_inputs(data_root, baseline):
    protected = {}
    # Opaque hashing is also applied to holdout commitments and truth files;
    # neither their JSON nor their labels are deserialized.
    for name, directory in (('data',data_root), ('baseline',baseline)):
        for path in sorted(directory.rglob('*')):
            if path.is_file() and not path.name.endswith(('-wal','-shm','.lock')):
                protected[name+'/'+path.relative_to(directory).as_posix()] = sha(path)
    return protected


def verify_manifest(directory):
    manifest = read_json(directory/'manifest.json')
    for name, entry in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or (directory/relative).resolve().parent != directory.resolve():
            raise ValueError('Source files must be immediate manifest members')
        expected = entry['sha256'] if isinstance(entry,dict) else entry
        if sha(directory/name) != expected:
            raise ValueError('Source manifest checksum mismatch: '+name)
    return manifest


def verified_table(directory, manifest, name):
    entry = manifest['files'][name+'.csv']
    if sha(directory/(name+'.csv')) != (entry['sha256'] if isinstance(entry,dict) else entry):
        raise ValueError('Accounting source checksum mismatch: '+name)
    return read_csv(directory/(name+'.csv'))


def assert_network_scope(network, company, cutoff):
    assert network['graph']['company_id'] == network['scope']['company_id'] == company
    assert network['graph']['as_of'] == network['scope']['as_of'] == cutoff
    for node in network['nodes']:
        # Company is encoded in the node namespace; node attributes deliberately
        # do not repeat company_id. Actor and contact identities are distinct.
        identity = node['entity_id'] if node['type'] in {'employee','vendor'} else node['value']
        assert node['id'] == node_id(company,node['type'],identity), 'Cross-company node namespace'


def graph_checks(tables, payload, cutoff):
    kinds, path_count = Counter(), 0
    for company, graph in payload['companies'].items():
        nodes = {r['id']:r for r in graph['nodes']}
        if len(nodes) != len(graph['nodes']):
            raise AssertionError('Duplicate graph node')
        assert_network_scope(graph,company,cutoff)
        kinds.update(r['type'] for r in nodes.values())
        for edge in graph['links']:
            assert edge['source'] in nodes and edge['target'] in nodes
            assert edge['observed_at'] <= cutoff
        components = [node for group in graph['components'] for node in group]
        assert len(components) == len(set(components)) == len(nodes)
        if graph['findings']:
            finding = next((f for f in graph['findings'] if len(f['entity_nodes']) >= 2),None)
            if finding:
                live = EntityGraph(tables,company,cutoff)
                path = live.shortest_path(*finding['entity_nodes'][:2])
                assert path['found'] and path['hops'] == 2
                path_count += 1
    assert set(kinds) <= {'employee','vendor','bank_account','phone','address','tax_code'}
    return dict(node_types=dict(kinds), company_paths_checked=path_count,
                company_isolation=True, edge_foreign_keys=True, components_partition_nodes=True)


def threshold_checks(tables, result, batch, cutoff):
    records, _ = extract_observations(tables)
    verifier = DynamicThresholds(records,ThresholdPolicy.from_config(result['config']))
    expected = verifier.parameter_table(cutoff)
    assert expected == batch['parameters'], 'Batch threshold table differs from full-source engine'
    assert {r['window_days'] for r in expected} == {30,60,90}
    assert all((r['status']=='ready') == (r['threshold_vnd'] is not None) for r in expected)
    for company in batch['company_files']:
        assert company in {r['company_id'] for r in tables['companies']}
    a5 = sorted((h for h in result['hits'] if h['rule_id']=='A5'),key=lambda h:(h['detected_at'],h['transaction_id']))[:20]
    causal = DynamicThresholds(records,ThresholdPolicy.from_config(result['config']))
    txs = {r['transaction_id']:r for r in tables['transactions']}
    for hit in a5:
        signal,evidence = causal.evaluate_transaction(txs[hit['transaction_id']])
        assert signal
        assert evidence['selected_parameter'] == hit['evidence']['selected_parameter']
        assert evidence['threshold_vnd'] == hit['evidence']['threshold_vnd']
        assert evidence['selected_parameter']['as_of'] == hit['detected_at']
    return dict(batch_rows=len(expected), statuses=dict(Counter(r['status'] for r in expected)),
                rule_a5_hits=sum(h['rule_id']=='A5' for h in result['hits']),
                causal_a5_evidence_replayed=len(a5), batch_matches_independent_instance=True,
                cold_start_rows=sum(r['threshold_vnd'] is None for r in expected))


def source_comparison(baseline, target, predictions):
    # This is called only after prediction/config/queue hashes have been frozen.
    if baseline.name not in {f'sme_fraud_{tag}' for tag in TAGS}:
        raise ValueError('Only reporting 001/003 source oracles may be joined')
    if not (target/'predictions_frozen.json').is_file():
        raise ValueError('Freeze detector artifacts before joining the source oracle')
    frozen = read_json(target/'predictions_frozen.json')['files']
    if any(sha(target/name) != expected for name,expected in frozen.items()):
        raise ValueError('Detector artifact changed after freeze')
    controls = read_json(baseline/'sealed_truth'/'oracle.json')
    mapped = {key(row):row for row in predictions}
    comparison = [dict(row, actual=mapped[key(row)]['prediction'],
                       detector_status=mapped[key(row)]['detector_status']) for row in controls]
    write_json(target/'control_comparison.json',comparison)
    mismatches = [r for r in comparison if r['expected'] is not r['actual']]
    write_json(target/'mismatches.json',mismatches)
    result = dict(overall=metrics(comparison),by_rule={rule:metrics([r for r in comparison if r['rule_id']==rule]) for rule in RULES},
                  financial_fraud_precision=None,independent_reviewed_units=0,
                  oracle_scope='Declared synthetic source predicates, including unknown outcomes')
    write_json(target/'control_metrics.json',result)
    return len(controls),len(mismatches)


def score_cohort(data_root, baseline_root, output, tag, plan):
    if tag not in TAGS:
        raise ValueError('Only reporting 001/003 may be scored by this runner')
    start = time.perf_counter()
    source, prior, target = (root/f'sme_fraud_{tag}' for root in (data_root,baseline_root,output))
    target.mkdir()
    manifest = verify_manifest(source)
    tables, cached, _ = load_inputs(source)
    assert manifest.get('role') == 'reporting'
    for name in ('account_flow_edges','document_links','invoices'):
        tables[name] = verified_table(source,manifest,name)
    accounting = check_accounting(tables)
    write_json(target/'accounting_validation.json',accounting)
    print(f'{tag}: {len(tables["transactions"]):,} transactions, accounting validated; rebuilding features',flush=True)
    rebuilt = build_features(tables)
    # NumPy is loaded by the threshold module using the repository runtime.
    import numpy as np
    assert [r['transaction_id'] for r in rebuilt] == [r['transaction_id'] for r in cached]
    actual = np.asarray([[r[k] for k in FEATURE_DESCRIPTIONS] for r in rebuilt],dtype=np.float32)
    existing = np.asarray([[r[k] for k in FEATURE_DESCRIPTIONS] for r in cached],dtype=np.float32)
    assert np.isfinite(actual).all() and np.array_equal(actual,existing), 'Rebuilt causal features differ from the committed cache'
    feature_check = dict(rows=len(rebuilt),columns=len(FEATURE_DESCRIPTIONS),cache_replayed_exactly=True,
        dtype='float32',matrix_sha256=hashlib.sha256(actual.tobytes()).hexdigest(),
        ordered_ids_sha256=digest([r['transaction_id'] for r in rebuilt]),truth_loaded=False)
    write_json(target/'feature_replay.json',feature_check)
    del actual,existing,cached
    print(f'{tag}: scoring current rules; no oracle loaded',flush=True)
    result = score_rules(tables,config=plan['rule_config'],features=rebuilt)
    result['evidence_findings'].extend(inspect_sources(tables,CUTOFF))
    cases,events = review_queue(result,tables)
    expected_members = operational_members(result)
    actual_members = {tid for row in cases if row['case_type'] != 'information_request' for tid in json.loads(row['transaction_ids'])}
    assert actual_members == expected_members, 'Queue membership differs from operational events'
    gap_members = {tid for row in cases if row['case_type'] == 'information_request' for tid in json.loads(row['transaction_ids'])}
    assert gap_members == cash_information_members(result)-expected_members
    packet = read_csv(prior/'review_packet.csv')
    predictions = predictions_from_result(result,tables,packet,CUTOFF)
    for name,rows in (('rule_scores',result['scores']),('case_queue',cases),('case_events',events)):
        write_csv(target/(name+'.csv'),[{k:v for k,v in r.items() if k!='known_risky_prior_ids'} for r in rows])
    for name,rows in (('rule_hits',result['hits']),('batch_events',result['batch_events']),('evidence_findings',result['evidence_findings'])):
        jsonl(target/(name+'.jsonl'),rows)
    write_json(target/'rule_config.json',result['config'])
    write_json(target/'rule_coverage.json',result['coverage'])
    from .a5_coverage import write_coverage
    write_coverage(target,result)
    write_json(target/'predictions.json',predictions)
    write_csv(target/'review_packet.csv',packet,list(packet[0]))
    write_parameters(target,result['dynamic_parameters'],result['dynamic_policy'],result['dynamic_source_summary'])
    print(f'{tag}: exporting NetworkX and company rolling tables',flush=True)
    graph_run = sync_graph(source,target/'entity_graph',CUTOFF)
    graph_payload = load_graph(target/'entity_graph')
    assert not sync_graph(source,target/'entity_graph',CUTOFF)['changed']
    graph_check = graph_checks(tables,graph_payload,CUTOFF)
    write_json(target/'entity_graph_checks.json',graph_check)
    threshold_run = sync_thresholds(source,target/'thresholds',CUTOFF,policy=ThresholdPolicy.from_config(result['config']))
    threshold_payload = load_thresholds(target/'thresholds')
    assert not sync_thresholds(source,target/'thresholds',CUTOFF,policy=ThresholdPolicy.from_config(result['config']))['changed']
    threshold_check = threshold_checks(tables,result,threshold_payload,CUTOFF)
    write_json(target/'threshold_checks.json',threshold_check)
    # Freeze detector outputs and policy before even deserializing the oracle.
    names = ['rule_scores.csv','rule_hits.jsonl','case_queue.csv','case_events.csv','batch_events.jsonl',
             'evidence_findings.jsonl','rule_config.json','rule_coverage.json','predictions.json','review_packet.csv',
             'dynamic_threshold_parameters.csv','dynamic_threshold_parameters.json','dynamic_threshold_policy.json']
    frozen = {name:sha(target/name) for name in names}
    write_json(target/'predictions_frozen.json',dict(files=frozen,plan_sha256=sha(output/'evaluation_plan.json'),
        source_manifest_sha256=sha(source/'manifest.json'),oracle_joined=False,financial_fraud_labels_loaded=False,
        model_fit=False,model_scored=False))
    controlled,mismatches = source_comparison(prior,target,predictions)
    prior_config = read_json(prior/'rule_config.json')
    prior_cases = read_csv(prior/'case_queue.csv')
    prior_hits = [json.loads(line) for line in (prior/'rule_hits.jsonl').read_text(encoding='utf-8').splitlines() if line]
    changes = dict(configuration_changes={name:dict(before=prior_config.get(name),after=value)
        for name,value in result['config'].items() if prior_config.get(name)!=value},
        before=dict(cases=len(prior_cases),hits=len(prior_hits),rule_hit_counts=dict(Counter(r['rule_id'] for r in prior_hits))),
        after=dict(cases=len(cases),hits=len(result['hits']),rule_hit_counts=dict(Counter(r['rule_id'] for r in result['hits']))),
        removed_case_ids=sorted({r['case_id'] for r in prior_cases}-{r['case_id'] for r in cases}),
        added_case_ids=sorted({r['case_id'] for r in cases}-{r['case_id'] for r in prior_cases}),
        interpretation='Changed case IDs can reflect changed scope; these counts are not population fraud precision')
    write_json(target/'comparison_previous.json',changes)
    summary = dict(tag=tag,transactions=len(tables['transactions']),companies=len(tables['companies']),
        journal_documents=accounting['journal_documents'],journal_lines=accounting['journal_lines'],
        rule_hits=len(result['hits']),cases=len(cases),source_cases=sum(c['case_type']=='source' for c in cases),
        information_request_cases=sum(c['case_type']=='information_request' for c in cases),
        operational_members=len(expected_members),features=feature_check,entity_graph=graph_run,
        thresholds=threshold_run,threshold_checks=threshold_check,controlled_units=controlled,
        control_mismatches=mismatches,prediction_files=frozen,elapsed_seconds=round(time.perf_counter()-start,3))
    write_json(target/'scoring_summary.json',summary)
    print(f'{tag}: {len(cases)} cases, {controlled} controls, {mismatches} mismatches',flush=True)
    del tables,rebuilt,result,cases,events,graph_payload,threshold_payload
    gc.collect()
    return summary


class HttpProbe:
    def __init__(self, store, service):
        self.server = make_server(store,port=0,qa=True,instance_id='synthetic-pipeline-rehearsal',notifications=service)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.token = self.request('GET','/api/meta')['csrf_token']

    def request(self, method, path, body=None, expected=200):
        connection = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)
        headers = {'Content-Type':'application/json'}
        if hasattr(self,'token'):
            headers['X-CSRF-Token'] = self.token
        try:
            connection.request(method,path,json.dumps(body) if body is not None else None,headers)
            response = connection.getresponse()
            content = response.read()
            assert response.status == expected,(path,response.status,content[:300])
            return json.loads(content) if response.getheader('Content-Type','').startswith('application/json') else content
        finally:
            connection.close()

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10)
        assert not self.thread.is_alive()


def outbox_rows(store):
    with store.connection() as db:
        return [dict(r) for r in db.execute('SELECT job_id,mode,scenario,company_id,kind,channel,status,attempts,error_code,created_at,payload FROM notification_outbox ORDER BY scenario,company_id,created_at,job_id')]


def review_rehearsal(data_root, output, review_at):
    now = [datetime.fromisoformat(review_at).astimezone(TZ)]
    database = output/'review.sqlite3'
    store = ReviewStore(data_root,output,database,scenarios=list(TAGS),clock=lambda:now[0])
    store.prepare()
    service = Notifications(store,dict(dry_run=True,replay_existing=True))
    probe = HttpProbe(store,service)
    selected,details,graph_apis = {},[],[]
    feedback_expected = []
    try:
        for asset in ('/','/app.js','/case_graph.js','/vendor/cytoscape.min.js'):
            assert probe.request('GET',asset)
        probe.request('GET','/data/labels.csv',expected=404)
        probe.request('GET','/vendor/manifest.json',expected=404)
        for tag in TAGS:
            queue = probe.request('GET','/api/cases?'+urlencode(dict(scenario=tag,daily=1,limit=100)))
            companies = sorted({r['company_id'] for r in queue['items']})
            assert companies
            counts = Counter(r['company_id'] for r in queue['items'])
            assert max(counts.values())<=5
            selected[tag] = queue
            service.plan(tag)  # Keep jobs pending while the review closes cases.
            firsts = [next(r for r in queue['items'] if r['company_id']==company) for company in companies]
            for index,row in enumerate(firsts):
                detail = probe.request('GET','/api/case?'+urlencode(dict(scenario=tag,id=row['case_id'])))
                assert detail['case']['company_id'] == row['company_id']
                assert 'is_fraud' not in json.dumps(detail) and 'fraud_type' not in json.dumps(detail)
                network = detail['entity_network']
                assert_network_scope(network,row['company_id'],row['last_seen_at'])
                balances = []
                for item in detail['documents']:
                    debit = sum(int(line['debit_vnd']) for line in item['lines'])
                    credit = sum(int(line['credit_vnd']) for line in item['lines'])
                    assert debit==credit
                    balances.append(dict(document_id=item['document']['document_id'],debit_vnd=debit,credit_vnd=credit))
                details.append(dict(scenario=tag,case_id=row['case_id'],company_id=row['company_id'],
                    network_nodes=len(network['nodes']),documents=balances,source_case=row['case_type']=='source'))
                if index==0:
                    graph = probe.request('GET','/api/entity-graph?'+urlencode(dict(scenario=tag,company=row['company_id'],as_of=CUTOFF,max_nodes=1000)))
                    assert_network_scope(graph,row['company_id'],CUTOFF)
                    graph_apis.append(dict(scenario=tag,company_id=row['company_id'],scope=graph['scope']))
                if index<3:
                    decision = ('false_positive','confirmed_suspicion','information_gap')[index]
                    body = dict(scenario=tag,case_id=row['case_id'],decision=decision,reviewer=REVIEWER,
                        reason='SIMULATED E2E exercise only; not an independent accounting or fraud conclusion.',expected_hash='')
                    probe.request('POST','/api/feedback',dict(body,reason=''),expected=400)
                    event = probe.request('POST','/api/feedback',body)
                    probe.request('POST','/api/feedback',body,expected=409)
                    feedback_expected.append(dict(scenario=tag,case_id=row['case_id'],decision=decision,event_hash=event['event_hash']))
        for tag in TAGS:
            probe.request('POST','/api/notifications/preview',dict(scenario=tag))
        while any(j['status']=='pending' for j in outbox_rows(store)):
            service.dispatch()
        frozen_jobs = {r['job_id']:digest(r) for r in outbox_rows(store)}
        assert all(r['status'] in {'simulated','cancelled'} for r in outbox_rows(store))
        before_audit = {tag:sha(output/f'sme_fraud_{tag}'/'feedback_audit.jsonl') for tag in TAGS}
    finally:
        probe.close()
    # New application objects and HTTP server: SQLite/audit persistence, not
    # just a second request to the same in-memory instance.
    store = ReviewStore(data_root,output,database,scenarios=list(TAGS),clock=lambda:now[0])
    store.prepare()
    service = Notifications(store,dict(dry_run=True,replay_existing=True))
    probe = HttpProbe(store,service)
    try:
        for event in feedback_expected:
            detail = probe.request('GET','/api/case?'+urlencode(dict(scenario=event['scenario'],id=event['case_id'])))
            assert detail['case']['feedback']['event_hash'] == event['event_hash']
            assert detail['case']['status'] == ('awaiting_information' if event['decision']=='information_gap' else 'closed')
            assert detail['audit_integrity']=='passed'
            assert event['case_id'] in store.admissions(event['scenario'])[0]
        for tag in TAGS:
            probe.request('POST','/api/notifications/preview',dict(scenario=tag))
            assert sha(output/f'sme_fraud_{tag}'/'feedback_audit.jsonl') == before_audit[tag]
        assert {r['job_id']:digest(r) for r in outbox_rows(store)} == frozen_jobs,'Restart duplicated or rewrote completed notifications'
        first_day = now[0].date().isoformat()
        limits = {first_day:5}
        day_results = [dict(day=first_day,budget=5,states={tag:service.status(tag)['counts'] for tag in TAGS})]
        for days,budget in ((1,5),(2,10)):
            now[0] = datetime.fromisoformat(review_at).astimezone(TZ)+timedelta(days=days)
            probe.request('POST','/api/budget',dict(daily_budget=budget))
            for tag in TAGS:
                probe.request('POST','/api/notifications/preview',dict(scenario=tag))
            while any(j['status']=='pending' for j in outbox_rows(store)):
                service.dispatch()
            limits[now[0].date().isoformat()] = budget
            day_results.append(dict(day=now[0].date().isoformat(),budget=budget,
                states={tag:service.status(tag)['counts'] for tag in TAGS}))
        with store.connection() as db:
            allocations = [dict(r) for r in db.execute('SELECT mode,day,scenario,company_id,case_id,scope_hash FROM notification_allocations ORDER BY day,scenario,company_id,case_id')]
        buckets = Counter((r['day'],r['scenario'],r['company_id']) for r in allocations)
        assert all(count<=limits[day] for (day,tag,company),count in buckets.items())
        assert all(r['mode']=='dry_run' for r in allocations)
        jobs = outbox_rows(store)
        assert all(r['status'] in {'simulated','cancelled'} and r['mode']=='dry_run' for r in jobs)
        for row in jobs:
            row.update(json.loads(row.pop('payload')))
        write_json(output/'notification_outbox.mock.json',jobs)
        write_csv(output/'notification_allocations.mock.csv',allocations)
        write_json(output/'feedback_events.mock.json',feedback_expected)
        write_json(output/'api_detail_checks.json',details)
        write_json(output/'api_graph_checks.json',graph_apis)
        write_json(output/'daily_priority_before_feedback.json',selected)
        result = dict(reviewed_by_bot=len(feedback_expected),independent_human_reviews=0,
            detailed_cases_checked=len(details),balanced_api_documents=sum(len(r['documents']) for r in details),
            feedback_and_admissions_survive_restart=True,notification_restart_idempotent=True,
            feedback_audit_sha256=before_audit,day_results=day_results,
            notification_jobs=len(jobs),notification_statuses=dict(Counter(r['status'] for r in jobs)),
            notification_kinds=dict(Counter(r['kind'] for r in jobs)),
            daily_allocation_counts=[dict(day=d,scenario=t,company_id=c,cases=n,limit=limits[d]) for (d,t,c),n in sorted(buckets.items())],
            external_messages_sent=0,mode='dry_run',browser_visual_qa=False,
            initial_review_at=review_at,final_review_at=now[0].isoformat())
        write_json(output/'review_notification_checks.json',result)
        return result
    finally:
        probe.close()


def run(data_root, baseline, output, review_at):
    data_root,baseline,output = input_guard(data_root,baseline,output)
    when = datetime.fromisoformat(review_at)
    if when.utcoffset() is None or when <= datetime.fromisoformat(CUTOFF):
        raise ValueError('Review clock must be timezone-aware and after the source cutoff')
    protected = fingerprint_inputs(data_root,baseline)
    output.mkdir(parents=True,exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    code = {p.relative_to(project).as_posix():sha(p) for directory,pattern in
            ((project/'sme_fraud','*.py'),(project/'review_ui','*.js')) for p in directory.glob(pattern)}
    code.update({p.relative_to(project).as_posix():sha(p) for p in (project/'review_ui/index.html',project/'review_ui/styles.css',project/'review_ui/vendor/cytoscape.min.js')})
    plan = dict(version='existing-source-pipeline-rehearsal-v1',tags=list(TAGS),data_root=str(data_root),baseline=str(baseline),
        source_cutoff=CUTOFF,review_at=review_at,rule_config=dict(DEFAULT_CONFIG),code_sha256=code,
        protected_inputs_sha256=protected,financial_fraud_labels_loaded=False,model_fit=False,model_scored=False,
        oracle_policy='Join only reporting 001/003 source oracle after predictions freeze',holdout_policy='005 opaque hashes only; no input load, prediction, oracle parse, UI or review',
        review_policy='SIM_PIPELINE_BOT in a new report/database; no independent human review',
        notification_policy='Dry-run only, fail if an external transport is invoked',real_gate='awaiting_real_data',
        pass_criteria=['Manifest hashes valid; accounting balanced; rebuilt features match committed float32 cache',
            'Current rules and exact-account rolling thresholds produce causal evidence',
            'Full NetworkX batch and UI JSON preserve company and temporal scope',
            'Queue membership reconciles operational events; source controls match including unknown',
            'HTTP feedback persists across restart; stale writes are rejected',
            'Mock notifications respect 5/10 daily case caps and restart idempotence',
            'Frozen predictions, source inputs and holdout remain unchanged'])
    write_json(output/'evaluation_plan.json',plan)
    started = time.perf_counter()
    try:
        summaries = [score_cohort(data_root,baseline,output,tag,plan) for tag in TAGS]
        print('001/003: checking HTTP queue, synthetic decisions, restart and mock notifications',flush=True)
        external_attempts = []
        def forbidden(*args,**kwargs):
            external_attempts.append(True)
            raise AssertionError('External transport invoked during synthetic rehearsal')
        with patch('sme_fraud.notification_channels.smtplib.SMTP',forbidden), patch('sme_fraud.notification_channels.smtplib.SMTP_SSL',forbidden), patch('sme_fraud.notification_channels.build_opener',forbidden):
            review = review_rehearsal(data_root,output,review_at)
        assert not external_attempts
        after = fingerprint_inputs(data_root,baseline)
        assert after == protected,'Protected input artifact set or hash changed'
        assert all(sha(output/f'sme_fraud_{s["tag"]}'/name)==checksum for s in summaries for name,checksum in s['prediction_files'].items()),'Frozen detector outputs changed during review'
        unchanged_code = {name:sha(project/name) for name in code}
        assert unchanged_code == code,'Implementation changed during rehearsal'
        mismatches = sum(s['control_mismatches'] for s in summaries)
        summary = dict(status='passed' if mismatches==0 else 'control_mismatches_require_review',
            successful=mismatches==0,cohorts=summaries,review=review,controlled_units=sum(s['controlled_units'] for s in summaries),
            control_mismatches=mismatches,protected_input_files=len(protected),protected_inputs_unchanged=True,
            holdout_005_scored=False,holdout_005_oracle_parsed=False,model_fit=False,model_scored=False,
            source_oracle_joined_after_freeze=True,independent_human_reviews=0,real_gate='awaiting_real_data',
            code_unchanged=True,external_transport_attempts=0,elapsed_seconds=round(time.perf_counter()-started,3))
        write_json(output/'summary.json',summary)
        print(json.dumps({k:summary[k] for k in ('status','controlled_units','control_mismatches','protected_input_files','holdout_005_scored','elapsed_seconds')},ensure_ascii=False),flush=True)
        return summary
    except Exception as error:
        write_json(output/'failure.json',dict(status='failed',stage_error=type(error).__name__,message=str(error),traceback=traceback.format_exc(),
            protected_inputs_unchanged=fingerprint_inputs(data_root,baseline)==protected,holdout_005_scored=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,default=Path('data/synthetic_sources_20261017_v2'))
    parser.add_argument('--baseline',type=Path,default=Path('reports/synthetic_sources_20261017_v2'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--review-at',default='2026-10-18T09:00:00+07:00')
    args = parser.parse_args()
    result = run(args.data_root,args.baseline,args.output,args.review_at)
    if not result['successful']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
