"""Side-effect-free method outputs. No delivery, ensemble, implicit fit or imputation.

LocalArtifact contains trusted worker-created bytes, not client-uploaded pickle.
method_jobs/MethodStore provide durable offline fit; active lifecycle and the
canonical-to-legacy rule bridge remain separate work.
"""
from dataclasses import dataclass
from copy import deepcopy
from importlib.metadata import version
import io
import math
from pathlib import Path
import pickle
import sys

import joblib
import numpy as np

from finance_input import AccessScope
from finance_input.json_io import loads
from .import_files import canonical, digest, fail
from .ml_estimators import CompanyEstimator, ALGORITHMS
from .unsupervised_statistics import RobustZ
from .score_statistics import empirical_rank
from .snapshot_features import build_from_snapshot, utc, _selected, available, _ref
from .features import build_features
from .feature_contract import current_contract
from .rules import score_rules
from .entity_graph import EntityGraph
from .method_preprocess import VERSION as PREPROCESS, fit_preprocess, validate_preprocess, row_values, transform_frame

VERSION = 'method-output/1.1.0'
ARTIFACT_VERSION = 'company-method-artifact/1.0.0'
METHODS = ('robust_z', *ALGORITHMS)
RESERVED = {'tenant_id', 'company_id', 'record_id', 'transaction_id', 'revision',
            'snapshot_id', 'label', 'fraud_label', 'label_value', 'is_fraud', 'seed',
            'template', 'source_system', 'source_id', 'source_sha256', 'content_sha256', 'as_of'}


def _scope(scope):
    if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or not scope.actor_id or 'data.import' not in scope.permissions:
        fail(403, 'ACCESS_DENIED', 'Không có quyền đọc dữ liệu trong một doanh nghiệp.', 'Chọn đúng quyền và doanh nghiệp.')
    return scope.tenant_id, next(iter(scope.company_ids))


def _frame(frame, scope):
    tenant, company = _scope(scope)
    contract = dict(frame['contract']); fingerprint = contract.pop('fingerprint')
    if digest(canonical(contract)) != fingerprint:
        raise ValueError('Feature contract fingerprint mismatch')
    columns = contract['columns']
    if not columns or len(set(columns)) != len(columns) or any(not isinstance(c, str) or c in RESERVED for c in columns):
        raise ValueError('Predictor columns must be unique numeric features, without identifiers or labels')
    if not (len(frame['rows']) == len(frame['features']) == len(frame['missing']) == len(frame['evidence'])):
        raise ValueError('Feature rows/masks/evidence do not align')
    identities = set(); ceiling = utc(frame['as_of'])
    for index, (row, values, missing, evidence) in enumerate(zip(frame['rows'], frame['features'], frame['missing'], frame['evidence'])):
        if (row['tenant_id'], row['company_id']) != (tenant, company):
            fail(403, 'ACCESS_DENIED', 'Dữ liệu nằm ngoài doanh nghiệp được phép.', 'Chọn đúng snapshot và quyền.')
        key = row['record_id'], row['revision']
        if key in identities or not isinstance(row['record_id'], str) or not row['record_id'] or type(row['revision']) is not int or row['revision'] < 1 or row['row_index'] != index or evidence['row_index'] != index:
            raise ValueError('Duplicate/invalid feature row identity')
        identities.add(key)
        if utc(row['as_of']) < utc(row['event_at']) or max(utc(row['event_at']), utc(row['as_of'])) > ceiling:
            raise ValueError('Feature row exceeds job cutoff')
        if len(values) != len(columns) or len(missing) != len(columns):
            raise ValueError('Feature width mismatch')
        for value, flag in zip(values, missing):
            if type(flag) is not bool or flag != (value is None) or value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError('Invalid predictor or missing mask')
    if 'snapshot' in frame and (frame['snapshot']['tenant_id'], frame['snapshot']['company_id']) != (tenant, company):
        fail(403, 'ACCESS_DENIED', 'Snapshot nằm ngoài quyền đọc.', 'Chọn đúng snapshot.')
    return columns


def _versions():
    return dict(runtime=dict(python=sys.version.split()[0],platform=sys.platform,
                **{name: version(name) for name in ('numpy', 'scipy', 'scikit-learn', 'joblib')}),
                implementation={name: digest(Path(__file__).with_name(name).read_bytes())
                                for name in ('ml_estimators.py', 'unsupervised_statistics.py', 'score_statistics.py', 'method_adapters.py', 'method_preprocess.py')})


@dataclass(frozen=True)
class LocalArtifact:
    """Immutable internal bytes; never deserialize artifacts supplied via HTTP."""
    artifact_id: str
    manifest: bytes
    payload: bytes


@dataclass(frozen=True)
class UnavailableArtifact:
    code: str
    message: str


def fit_local_reference(history, reference, scope, method_id, *, selected_columns, minimum_history, profile_id,
                        missing_policy='strict', fit_context=None):
    """Explicit offline fit + held-out reference step, not called by inference.

    The caller supplies technical-demo min-history/profile. This does not approve
    D-03 or replace a persistent authorized job/registry for production.
    """
    tenant, company = _scope(scope)
    columns = _frame(history, scope); _frame(reference, scope)
    if method_id not in METHODS or type(minimum_history) is not int or minimum_history < 5 or not isinstance(profile_id, str) or not profile_id:
        raise ValueError('An explicit supported demo method/history/profile is required')
    selected_columns = list(selected_columns)
    if not selected_columns or len(set(selected_columns)) != len(selected_columns) or any(c not in columns for c in selected_columns):
        raise ValueError('Invalid selected feature columns')
    if history['contract']['fingerprint'] != reference['contract']['fingerprint']:
        raise ValueError('History/reference contracts differ')
    if len(history['rows']) < minimum_history or not reference['rows']:
        raise ValueError('Insufficient history/reference; detector minimum is not inferred')
    end = max(max(utc(r['event_at']), utc(r['as_of'])) for r in history['rows'])
    start = min(min(utc(r['event_at']), utc(r['as_of'])) for r in reference['rows'])
    if end >= start:
        raise ValueError('Training must end strictly before held-out reference on both clocks')
    history_ids = {r['record_id'] for r in history['rows']}
    reference_ids = {r['record_id'] for r in reference['rows']}
    if history_ids & reference_ids:
        raise ValueError('History and held-out reference share transaction identities')
    fit_context = dict(fit_context or {})
    reference_end=max(max(utc(r['event_at']), utc(r['as_of'])) for r in reference['rows'])
    if fit_context.get('evaluation_start') and reference_end >= utc(fit_context['evaluation_start']):
        raise ValueError('Reference must end before evaluation starts')
    if fit_context.get('evaluation_mode') == 'prospective' and utc(fit_context['created_at']) >= utc(fit_context['evaluation_start']):
        raise ValueError('Prospective artifact must be created before evaluation starts')
    preprocess = fit_preprocess(history, selected_columns, missing_policy)
    model = RobustZ() if method_id == 'robust_z' else CompanyEstimator(method_id)
    model.fit(transform_frame(history, preprocess))
    scores = np.asarray(model.score(transform_frame(reference, preprocess)), dtype=float)
    if scores.shape != (len(reference['rows']),) or not np.isfinite(scores).all():
        raise ValueError('Invalid held-out reference scores')
    reference_scores = sorted(scores.tolist())
    stream = io.BytesIO(); joblib.dump((model, reference_scores), stream)
    payload = stream.getvalue()
    manifest = dict(version=ARTIFACT_VERSION, tenant_id=tenant, company_id=company,
        method_id=method_id, profile_id=profile_id, minimum_history=minimum_history,
        selected_columns=selected_columns, feature_contract=history['contract'],feature_contract_fingerprint=history['contract']['fingerprint'],
        preprocess=preprocess,preprocess_sha256=digest(canonical(preprocess)),model_version='mdl_'+digest(payload),fit_context=fit_context,
        preprocess_version=PREPROCESS, score_kind='empirical_midrank', higher_is_more_unusual=True,
        train_end=end.isoformat(), reference_start=start.isoformat(),
        reference_end=reference_end.isoformat(),
        history_hash=digest(canonical(history)), reference_data_hash=digest(canonical(reference)),
        history_binding=history.get('snapshot', history.get('source')), reference_binding=reference.get('snapshot', reference.get('source')),
        history_rows=len(history['rows']), reference_rows=len(reference['rows']),
        fitted_identity_hashes=sorted(digest(canonical(identity)) for identity in history_ids | reference_ids),
        fit_diagnostics=dict(converged=getattr(model, 'converged_', None)),
        reference_version=digest(canonical(reference_scores)), payload_sha256=digest(payload), versions=_versions())
    encoded = canonical(manifest)
    return LocalArtifact('mth_'+digest(encoded), encoded, payload)


def _method(method_id, frame, evidence, *, reason=None, missing=(), raw=None, score=None, manifest=None, details=None):
    manifest = manifest or {}
    details = dict(details or {})
    if manifest.get('preprocess'):
        details.update(model_version=manifest.get('model_version'),missing_policy=manifest['preprocess']['policy'],
                       ignored_training_features=list(manifest['preprocess']['dropped_columns']),
                       evaluation_mode=manifest.get('fit_context',{}).get('evaluation_mode','backtest'))
    result = dict(method_id=method_id, raw_score=raw, score=score,
        score_kind='rule_points' if method_id == 'rules' else 'empirical_midrank',
        available=reason is None, reason=None if reason is None else dict(code=reason[0], message=reason[1]),
        missing_features=list(missing), artifact_id=manifest.get('artifact_id'),
        preprocess_version=manifest.get('preprocess_version'),
        reference_version=manifest.get('reference_version'),
        feature_contract_fingerprint=frame['contract']['fingerprint'],
        evidence_refs=evidence.get('records', []), details=details)
    if reason is None and any(type(v) not in (float, int) or not math.isfinite(v) for v in (raw, score)):
        raise ValueError('Available method must have finite scores')
    if reason is not None and (raw is not None or score is not None):
        raise ValueError('Unavailable scores must be null')
    return result


def _statistical_scores(frame, scope, method_id, artifact):
    def unavailable(reason):
        return [_method(method_id, frame, e, reason=reason) for e in frame['evidence']]
    if artifact is None:
        return unavailable(('artifact_missing', 'Chưa có model và phân phối tham chiếu phù hợp; cần chạy job fit riêng.'))
    if isinstance(artifact, UnavailableArtifact):
        return unavailable((artifact.code,artifact.message))
    if not isinstance(artifact, LocalArtifact):
        return unavailable(('artifact_invalid', 'Artifact không thuộc bundle nội bộ được hỗ trợ.'))
    try:
        manifest = loads(artifact.manifest)
        if (manifest['tenant_id'], manifest['company_id']) != _scope(scope):
            fail(403, 'ACCESS_DENIED', 'Artifact nằm ngoài doanh nghiệp được phép.', 'Dùng artifact đúng doanh nghiệp.')
        if artifact.artifact_id != 'mth_'+digest(artifact.manifest) or digest(artifact.payload) != manifest['payload_sha256']:
            raise ValueError('artifact checksum')
        if manifest['version'] != ARTIFACT_VERSION or manifest['method_id'] != method_id or manifest['feature_contract_fingerprint'] != frame['contract']['fingerprint'] or manifest['preprocess_version'] != PREPROCESS or manifest['versions'] != _versions():
            return unavailable(('artifact_incompatible', 'Model, feature, tiền xử lý hoặc phiên bản triển khai không tương thích.'))
        if manifest['feature_contract'] != frame['contract'] or manifest['preprocess']['selected_columns'] != manifest['selected_columns']:
            return unavailable(('artifact_incompatible', 'Toàn bộ feature contract hoặc thứ tự tiền xử lý không khớp; cần fit phiên bản mới.'))
        validate_preprocess(frame,manifest['preprocess'])
        if digest(canonical(manifest['preprocess']))!=manifest['preprocess_sha256']:
            raise ValueError('preprocess checksum')
        manifest = dict(manifest, artifact_id=artifact.artifact_id)
        # Only locally created, scope/hash/version-checked worker bytes reach load.
        model, reference = joblib.load(io.BytesIO(artifact.payload))
        if not reference or digest(canonical(reference)) != manifest['reference_version']:
            raise ValueError('reference checksum')
    except (ValueError, KeyError, TypeError, EOFError, OSError, IndexError, pickle.UnpicklingError, AttributeError, ImportError):
        return unavailable(('artifact_invalid', 'Artifact hoặc phân phối tham chiếu không hợp lệ; chưa chấm bằng model này.'))
    results = [None]*len(frame['rows']); eligible = []; matrix = []; imputed = {}
    for index, (row, values, evidence) in enumerate(zip(frame['rows'], frame['features'], frame['evidence'])):
        prepared,missing,unavailable_reason = row_values(frame,values,manifest['preprocess'])
        context=manifest.get('fit_context',{})
        if unavailable_reason:
            results[index] = _method(method_id, frame, evidence, reason=(unavailable_reason, 'Chưa đủ dữ liệu cho các biến model cần dùng.'), missing=missing, manifest=manifest,
                details=dict(missing_reasons={c:evidence.get('missing_reasons', {}).get(c, 'source_unavailable') for c in missing}))
        elif utc(manifest['reference_end']) >= min(utc(row['event_at']), utc(row['as_of'])):
            results[index] = _method(method_id, frame, evidence, reason=('artifact_from_future', 'Model/reference không có trước thời điểm giao dịch; cần đúng phiên bản lịch sử.'), manifest=manifest)
        elif digest(canonical(row['record_id'])) in manifest['fitted_identity_hashes']:
            results[index] = _method(method_id, frame, evidence, reason=('artifact_training_overlap', 'Giao dịch đã thuộc tập fit/reference của artifact này; không trình bày như điểm ngoài mẫu.'), manifest=manifest)
        elif context.get('evaluation_start') and utc(context['evaluation_start']) > min(utc(row['event_at']),utc(row['as_of'])):
            results[index] = _method(method_id,frame,evidence,reason=('before_evaluation_period','Giao dịch chưa thuộc kỳ đánh giá của phiên bản model này.'),manifest=manifest)
        elif context.get('evaluation_mode')=='prospective' and utc(context['created_at']) >= min(utc(row['event_at']),utc(row['as_of'])):
            results[index] = _method(method_id,frame,evidence,reason=('artifact_not_yet_created','Phiên bản model chưa được tạo trước giao dịch trong chế độ prospective.'),manifest=manifest)
        else:
            eligible.append(index); matrix.append(prepared); imputed[index]=missing
    if eligible:
        try:
            raw = np.asarray(model.score(np.asarray(matrix, dtype=float)), dtype=float)
            if raw.shape != (len(eligible),) or not np.isfinite(raw).all():
                raise ValueError('Invalid model scores')
            ranks = empirical_rank(np.asarray(reference), raw)
            for index, value, rank in zip(eligible, raw, ranks):
                results[index] = _method(method_id, frame, frame['evidence'][index], raw=float(value), score=float(rank), manifest=manifest,
                    missing=imputed[index],details=dict(imputed_features=imputed[index],
                    missing_reasons={c:frame['evidence'][index].get('missing_reasons',{}).get(c,'source_unavailable') for c in imputed[index]}))
        except (ValueError, TypeError, FloatingPointError):
            for index in eligible:
                results[index] = _method(method_id, frame, frame['evidence'][index], reason=('scoring_failed', 'Model không trả được điểm hợp lệ; cần kiểm tra artifact.'), manifest=manifest)
    return results


def _graph_unavailable(code='graph_sources_missing', message='Chưa đủ nguồn đối tượng/quan hệ tại thời điểm giao dịch.'):
    return dict(available=False, reason=dict(code=code, message=message), nodes=[], links=[], findings=[], information_gaps=[], evidence_refs=[])


def _graph(tables, row, vendor_id='', employee_id='', refs=()):
    graph = EntityGraph(tables, row['company_id'], row['as_of'])
    kind, identity = ('vendor', vendor_id) if vendor_id else ('employee', employee_id)
    if not identity:
        return _graph_unavailable()
    try:
        seed = graph.actor(kind, identity)
    except KeyError:
        return _graph_unavailable('graph_entity_unknown', 'Đối tượng tham chiếu chưa có nguồn khả dụng tại thời điểm giao dịch.')
    data = graph.to_json([seed], depth=2, max_nodes=None)
    return dict(available=True, reason=None, nodes=data['nodes'], links=data['links'], findings=data['findings'],
                information_gaps=data['information_gaps'], evidence_refs=list(refs), scope=data['scope'])


def _checked_graph(graph, row):
    if graph is None:
        return _graph_unavailable()
    if type(graph.get('available')) is not bool or graph['available'] and graph.get('reason') is not None:
        raise ValueError('Invalid graph availability')
    if graph['available']:
        if graph['scope']['company_id'] != row['company_id']:
            fail(403, 'ACCESS_DENIED', 'Đồ thị nằm ngoài doanh nghiệp được phép.', 'Dùng đồ thị đúng doanh nghiệp và thời điểm.')
        if utc(graph['scope']['as_of']) != utc(row['as_of']):
            raise ValueError('Graph cutoff does not match the transaction')
        for ref in graph['evidence_refs']:
            if utc(ref['observed_at']) > utc(row['as_of']) or utc(ref['effective_at']) > utc(row['event_at']):
                raise ValueError('Graph source exceeds transaction knowledge/event cutoff')
        for link in graph['links']:
            if utc(link['evidence']['observed_at']) > utc(row['as_of']):
                raise ValueError('Graph edge comes from the future')
    elif not graph.get('reason', {}).get('code') or not graph['reason'].get('message'):
        raise ValueError('Unavailable graph needs a reason')
    return graph


def score_batch(frame, scope, *, artifacts=None, methods=METHODS, rule_output=None, graphs=None):
    """Every row goes through every requested adapter, regardless of rule flags."""
    _frame(frame, scope)
    if len(set(methods)) != len(methods) or any(m not in METHODS for m in methods):
        raise ValueError('Unknown/duplicate requested methods')
    artifacts = artifacts or {}; graphs = graphs or {}
    rule_rows = {}; rule_hits = {}; native_diagnostics = None
    if rule_output is not None:
        if rule_output['input_checksum'] != frame.get('source', {}).get('checksum') or frame.get('source', {}).get('profile') != 'retained-native':
            raise ValueError('Rule output is not bound to the same native input')
        # Returned diagnostics/hits/scores must not share mutable objects with
        # the worker's source result. Keep batch findings separate from rows.
        rule_output=deepcopy(rule_output)
        expected = {(r['company_id'], r['record_id']) for r in frame['rows']}
        for result in rule_output['result']['scores']:
            key = result['company_id'], result['transaction_id']
            if key not in expected or key in rule_rows:
                raise ValueError('Foreign/duplicate rule output')
            rule_rows[key] = result
        for hit in rule_output['result']['hits']:
            key = hit['company_id'], hit['transaction_id']
            if key not in expected:
                raise ValueError('Foreign rule evidence')
            rule_hits.setdefault(key, []).append(hit)
        diagnostic_output={k:v for k,v in rule_output['result'].items() if k not in {'scores','hits'}}
        company=_scope(scope)[1]
        for records in diagnostic_output.values():
            if isinstance(records,list):
                for record in records:
                    if isinstance(record,dict) and 'company_id' in record and record['company_id']!=company:
                        fail(403,'ACCESS_DENIED','Chẩn đoán luật nằm ngoài doanh nghiệp được phép.','Dùng kết quả engine đúng nguồn và doanh nghiệp.')
        known_ids={r['record_id'] for r in frame['rows']}
        for event in diagnostic_output.get('batch_events',[]):
            if any(identity not in known_ids for identity in event['transaction_ids']+event['related_transaction_ids']):
                raise ValueError('Batch evidence references transactions outside the bound input')
        native_diagnostics=dict(input_checksum=rule_output['input_checksum'],
            implementation_sha256=rule_output['implementation_sha256'],output=diagnostic_output)
    # This call is deliberately independent of rule_rows/rule_ids/hard_trigger.
    scored = {method:_statistical_scores(frame, scope, method, artifacts.get(method)) for method in methods}
    rows = []
    for index, (row, evidence) in enumerate(zip(frame['rows'], frame['evidence'])):
        key = row['company_id'], row['record_id']
        source = rule_rows.get(key)
        if source is None:
            reason = ('rule_sources_unavailable', 'Luồng snapshot chưa có bộ chuyển đổi đầy đủ sang hợp đồng luật cũ; chưa thể đánh giá luật từ nguồn hiện tại.') if rule_output is None else ('rule_result_missing', 'Bộ luật không trả kết quả cho giao dịch này; cần kiểm tra đầu ra, không tự điền điểm 0.')
            rules = _method('rules', frame, evidence, reason=reason)
        else:
            rules = _method('rules', frame, evidence, raw=source['rule_score'], score=source['rule_score'],
                details=dict(native_score=source, hits=rule_hits.get(key, []), coverage=rule_output['result']['coverage'],
                             rule_implementation_sha256=rule_output['implementation_sha256']))
        rows.append(dict(**row, methods=dict(rules=rules, **{m:scored[m][index] for m in methods}),
                         graph=_checked_graph(graphs.get((row['record_id'], row['revision'])), row)))
    result=dict(version=VERSION, score_meaning='Priority/anomaly measures, not calibrated fraud probabilities; no ensemble or alert decision.',
                feature_contract_fingerprint=frame['contract']['fingerprint'], row_count=len(rows), rows=rows)
    if native_diagnostics is not None:result['native_rule_diagnostics']=native_diagnostics
    return result


def native_inputs(tables, scope, *, config=None):
    """Full native source profile only; never project canonical missing fields."""
    tenant, company = _scope(scope)
    tables = {name:rows for name, rows in tables.items() if name not in {'labels', 'splits'}}
    for records in tables.values():
        if isinstance(records, list) and any(r.get('company_id', company) != company for r in records):
            fail(403, 'ACCESS_DENIED', 'Nguồn native chứa doanh nghiệp ngoài phạm vi.', 'Tách nguồn theo doanh nghiệp trước khi chấm.')
    features = build_features(tables); by_id = {r['transaction_id']:r for r in features}
    contract = current_contract(); rows = sorted(tables['transactions'], key=lambda r:(utc(r['posted_at']), r['transaction_id']))
    if len({r['transaction_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate native transaction identity')
    metadata = [dict(row_index=i, tenant_id=tenant, company_id=company, record_id=r['transaction_id'], revision=1,
                     event_at=utc(r['posted_at']).isoformat(), as_of=utc(r['posted_at']).isoformat()) for i,r in enumerate(rows)]
    matrix = [[by_id[r['transaction_id']][c] for c in contract['columns']] for r in rows]
    checksum = digest(canonical(tables))
    frame = dict(as_of=max((r['as_of'] for r in metadata), default='1970-01-01T00:00:00+00:00'),
        contract=contract, features=matrix, missing=[[False]*len(contract['columns']) for r in rows], rows=metadata,
        evidence=[dict(row_index=i, records=[], missing_reasons={}) for i in range(len(rows))],
        source=dict(profile='retained-native', checksum=checksum))
    _frame(frame, scope)
    result = score_rules(tables, config=config, features=features)
    graphs = {(r['transaction_id'], 1):_graph(tables, meta, r.get('vendor_id', ''), r.get('employee_id', '')) for r,meta in zip(rows,metadata)}
    return frame, dict(input_checksum=checksum, result=result,
        implementation_sha256=digest(Path(__file__).with_name('rules.py').read_bytes())), graphs


def score_snapshot(store, scope, snapshot_id, as_of, *, artifacts=None, methods=METHODS, recheck=None):
    """R1 snapshot path: source-backed graph and ML; unsupported legacy rules explicit."""
    frame = build_from_snapshot(store, scope, snapshot_id, as_of, recheck)
    bundle = loads(store.get_snapshot(scope, snapshot_id, recheck, data=True))
    from .rule_sources import _resolve
    rule_payloads, rule_inputs = _resolve(bundle, frame, scope)
    transactions = {(r['record_id'], r['revision']):r for r in bundle['transactions']}
    graphs = {}
    for row in frame['rows']:
        tx = transactions[(row['record_id'], row['revision'])]
        sources = {table:_selected(bundle[table], row['company_id'], utc(row['as_of']), utc(row['event_at'])) for table in ('vendors', 'employees')}
        projected = {}; refs = []
        for table, identifier, label in (('vendors', 'vendor_id', 'name'), ('employees', 'employee_id', 'full_name')):
            projected[table] = []
            for record in sources[table][0].values():
                projected[table].append(dict(company_id=row['company_id'], **{identifier:record['record_id'], label:record['name']},
                    recorded_at=available(record).isoformat(), bank_account=record.get('bank_account') or '',
                    bank_code=record.get('bank_code') or '', **({'address':record.get('address') or ''} if table=='vendors' else {})))
                refs.append(_ref(table, record))
        def known(table, field):
            ref = tx.get(field)
            return ref['record_id'] if ref and (ref['record_id'], ref['revision']) in sources[table][1] else ''
        graphs[(row['record_id'], row['revision'])] = _graph(projected, row, known('vendors', 'vendor_ref'), known('employees', 'employee_ref'), sorted(refs,key=lambda r:(r['table'],r['record_id'],r['revision'])))
    result = score_batch(frame, scope, artifacts=artifacts, methods=methods, graphs=graphs)
    from .rule_evaluation import _evaluate
    for row in result['rows']:
        key=(row['record_id'],row['revision'])
        row['methods']['rules']['details']['rule_inputs'] = rule_inputs[key]
        row['methods']['rules']['details']['rule_results'] = _evaluate(rule_payloads[key],rule_inputs[key],scope,row)
        row['methods']['rules']['reason'] = dict(row['methods']['rules']['details']['rule_results']['aggregate']['reason'])
    if recheck is not None and recheck() != scope:
        fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi trước khi trả kết quả chấm.', 'Chạy lại theo quyền hiện hành.')
    return dict(result, snapshot=frame['snapshot'])
