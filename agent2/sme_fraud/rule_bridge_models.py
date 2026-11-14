"""Explicit offline operator preparation/activation for simulated C001/C002.

The service context is scoped to generated demo exports only. It is not a
Portal user credential and never changes Portal permissions or HE bindings.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from finance_input import AccessScope
from .analysis_resources import AnalysisResources
from .import_files import canonical, digest
from .method_jobs import run_fit_job
from .method_store import MethodStore
from .rule_bridge_demo import COMPANIES, VERSION, fit_config, source_data
from .rule_snapshot_features import feature_contract
from .snapshot_analysis import analyze_snapshot
from .snapshots import SnapshotStore


def _access(path):
    from portal.agent2_bridge import identity
    value = identity(path, datetime.now(timezone.utc).timestamp() + 60)
    members = {row['company_id']: row for row in value['memberships']}
    if value['tenant_id'] != 'demo' or any(c not in members or members[c]['status'] != 'active'
            or 'data.import' not in members[c]['permissions'] for c in COMPANIES):
        raise ValueError('This operator command requires the existing demo tenant C001/C002 import grants; it never grants access')
    return value


def _scope(company):
    if company not in COMPANIES:
        raise ValueError('Only generated simulated companies are allowed')
    return AccessScope('demo', frozenset({company}), 'rule-bridge-demo-setup', frozenset({'data.import', 'model.fit'}))


class _DemoFitOperator:
    def __init__(self, access_file):
        self.access_file = access_file

    def authorize(self, authorization, company):
        # Administrative invocation for a fixed synthetic producer, matching
        # the existing HE demo preparation pattern. No browser can invoke it.
        _access(self.access_file)
        return _scope(company)


def _commit(store, data, key, authorizer):
    if data['source'].get('is_simulated') is not True or data['tenant_id'] != 'demo' or data['company_id'] not in COMPANIES:
        raise ValueError('Only generated synthetic exports may be prepared')
    scope = authorizer.authorize(None, data['company_id'])
    recheck = lambda: authorizer.authorize(None, data['company_id'])
    draft = store.upload(scope, canonical(data), key + '.json', key + '-upload', recheck)
    report = store.preview(scope, draft['import_id'], draft['revision'], recheck)
    if report['status'] == 'rejected':
        raise ValueError(report['errors'])
    request = {k: report[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
    request.update(expected_revision=report['revision'], acknowledge=True)
    return store.commit(scope, draft['import_id'], request, key + '-save', recheck)['snapshot']['snapshot_id']


def _model_hashes(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        return {r[0]: digest(r[1] + r[2]) for r in db.execute('SELECT artifact_id,manifest_json,payload FROM method_artifacts')}


def _backup_db(source, destination):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(destination)) as target:
            src.backup(target)


def prepare(snapshot_db, model_db, bindings_file, access_file, output):
    snapshot_db, model_db, bindings_file, access_file, output = map(Path, (snapshot_db, model_db, bindings_file, access_file, output))
    _access(access_file)
    original_bindings = bindings_file.read_bytes()
    old = json.loads(original_bindings)
    # Reuse strict server config parsing rather than guessing invalid bindings.
    for company in COMPANIES:
        _, error = AnalysisResources(model_db, bindings_file).selection(_scope(company))
        if error not in (None, 'binding_missing'):
            raise ValueError('Existing analysis bindings are invalid')
    sources = {c: source_data(c) for c in COMPANIES}
    output.mkdir(parents=True, exist_ok=False)
    backup = output / 'backup'; backup.mkdir()
    _backup_db(snapshot_db, backup / 'snapshots.sqlite3')
    _backup_db(model_db, backup / 'models.sqlite3')
    (backup / 'analysis-bindings.json').write_bytes(original_bindings)
    access_hash = digest(access_file.read_bytes())
    old_models = _model_hashes(model_db)
    (output / 'PREPARING').write_text('Not activated. Keep backups and use the completed prepared.json receipt.\n', encoding='utf-8')
    snapshots, models = SnapshotStore(snapshot_db), MethodStore(model_db)
    auth = _DemoFitOperator(access_file)
    records, new_bindings = [], []
    data_root = output / 'data'; data_root.mkdir()
    for company, method in COMPANIES.items():
        history, evaluation = sources[company]
        history_file, evaluation_file = company + '_lich_su_fit.json', company + '_5_giao_dich.json'
        (data_root / history_file).write_bytes(canonical(history))
        (data_root / evaluation_file).write_bytes(canonical(evaluation))
        train_id = _commit(snapshots, history, 'rule-bridge-demo-v1-' + company + '-history', auth)
        eval_id = _commit(snapshots, evaluation, 'rule-bridge-demo-v1-' + company + '-evaluation', auth)
        artifacts, metadata = {}, {}
        for chosen in (method, 'robust_z'):
            result = run_fit_job(snapshots, models, auth, None, company, fit_config(train_id, chosen),
                                 'rule-bridge-demo-v1-' + company + '-' + chosen)
            if result['job']['status'] != 'succeeded':
                raise ValueError('Offline preparation failed: ' + str(result['job'].get('failure_code')))
            manifest = result['manifest']
            if manifest['history_rows'] != 32 or manifest['reference_rows'] != 8 or manifest['feature_contract_fingerprint'] != feature_contract()['fingerprint']:
                raise ValueError('Model contract or independent history/reference does not match the demo')
            artifacts[chosen] = result['job']['artifact_id']
            metadata[chosen] = dict(history_rows=manifest['history_rows'], reference_rows=manifest['reference_rows'],
                                    model_version=manifest['model_version'], reference_version=manifest['reference_version'],
                                    selected_columns=manifest['selected_columns'],
                                    dropped_columns=manifest['preprocess']['dropped_columns'])
        new_bindings.append(dict(tenant_id='demo', company_id=company,
                                 statistics_artifact_id=artifacts['robust_z'], ml_artifacts={method: artifacts[method]}))
        records.append(dict(company_id=company, method_id=method, history_snapshot_id=train_id, evaluation_snapshot_id=eval_id,
                            as_of=evaluation['source']['as_of'], evaluation_file='data/' + evaluation_file,
                            evaluation_sha256=digest(canonical(evaluation)), artifacts=artifacts, models=metadata))
    preserved = [r for r in old['bindings'] if (r['tenant_id'], r['company_id']) not in {('demo', c) for c in COMPANIES}]
    candidate = canonical(dict(version='analysis-bindings/1.0.0', bindings=preserved + new_bindings))
    (output / 'analysis-bindings.candidate.json').write_bytes(candidate)
    receipt = dict(version=VERSION, status='prepared_not_activated', source_kind='simulated', evaluation_mode='backtest',
                   snapshot_db=str(snapshot_db.resolve()), model_db=str(model_db.resolve()),
                   bindings_file=str(bindings_file.resolve()), access_file=str(access_file.resolve()),
                   original_bindings_sha256=digest(original_bindings), candidate_bindings_sha256=digest(candidate),
                   access_sha256=access_hash, original_model_hashes=old_models,
                   feature_contract_fingerprint=feature_contract()['fingerprint'], companies=records,
                   portal_permissions_changed=False, he_execution=False, production_approved=False)
    (output / 'prepared.json').write_bytes(canonical(receipt))
    check(output, candidate=True)
    (output / 'PREPARING').unlink()
    return receipt


def check(output, *, candidate=False):
    output = Path(output)
    receipt = json.loads((output / 'prepared.json').read_bytes())
    if receipt['version'] != VERSION or receipt['feature_contract_fingerprint'] != feature_contract()['fingerprint']:
        raise ValueError('Prepared model contract no longer matches current bridge')
    _access(receipt['access_file'])
    bindings = output / 'analysis-bindings.candidate.json' if candidate else Path(receipt['bindings_file'])
    if digest(bindings.read_bytes()) != receipt['candidate_bindings_sha256']:
        raise ValueError('Bindings do not match the verified candidate receipt')
    current = _model_hashes(receipt['model_db'])
    if any(current.get(k) != v for k, v in receipt['original_model_hashes'].items()):
        raise ValueError('An existing model changed')
    snapshots = SnapshotStore(receipt['snapshot_db'])
    resources = AnalysisResources(receipt['model_db'], bindings)
    checks = []
    for item in receipt['companies']:
        authorizer = _DemoFitOperator(receipt['access_file'])
        scope = authorizer.authorize(None, item['company_id'])
        recheck = lambda c=item['company_id']: authorizer.authorize(None, c)
        if digest((output / item['evaluation_file']).read_bytes()) != item['evaluation_sha256']:
            raise ValueError('Evaluation source file changed')
        result = analyze_snapshot(snapshots, scope, item['evaluation_snapshot_id'], item['as_of'], technical=True, resources=resources,recheck=recheck)
        if result['row_count'] != 5 or any(not row['methods'][item['method_id']]['available']
                or not row['methods']['robust_z']['available'] for row in result['rows']):
            raise ValueError('The evaluation batch is not fully compatible/available')
        checks.append(dict(company_id=item['company_id'], snapshot_id=item['evaluation_snapshot_id'], analysis_id=result['analysis_id'],
                           rows=5, ml_available=5, statistics_available=5,
                           method_id=item['method_id'], artifact_id=item['artifacts'][item['method_id']],
                           positions=[row['methods'][item['method_id']]['score'] for row in result['rows']]))
    report = dict(status='passed', companies=checks, source_kind='simulated', backtest=True, he_execution=False,
                  bindings='candidate' if candidate else 'portal', old_models_preserved=len(receipt['original_model_hashes']))
    (output / ('candidate-check.json' if candidate else 'portal-check.json')).write_bytes(canonical(report))
    return report


def activate(output):
    output = Path(output)
    receipt = json.loads((output / 'prepared.json').read_bytes())
    check(output, candidate=True)
    bindings = Path(receipt['bindings_file'])
    lock = bindings.with_name(bindings.name + '.demo-activate.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = None
    try:
        os.close(descriptor)
        if digest(Path(receipt['access_file']).read_bytes()) != receipt['access_sha256']:
            raise ValueError('Portal access policy changed after preparation; recheck before activation')
        current_hash = digest(bindings.read_bytes())
        if current_hash != receipt['candidate_bindings_sha256']:
            if current_hash != receipt['original_bindings_sha256']:
                raise ValueError('Analysis bindings changed after preparation; not replacing them')
            payload = (output / 'analysis-bindings.candidate.json').read_bytes()
            with tempfile.NamedTemporaryFile(dir=bindings.parent, prefix=bindings.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name); stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, bindings); temporary = None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
        lock.unlink()
    report = check(output)
    (output / 'activated.json').write_bytes(canonical(dict(status='activated_demo_only', bindings_sha256=receipt['candidate_bindings_sha256'],
                                                         companies=list(COMPANIES), portal_permissions_changed=False)))
    return report
