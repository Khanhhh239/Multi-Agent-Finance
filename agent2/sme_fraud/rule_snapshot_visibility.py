"""Keep non-visible candidates outside predictor frames and model inference.

The analysis still returns their requested identities with unavailable results.
This is orchestration, not a change to either feature contract or estimator.
"""
from .import_files import canonical, digest
from .snapshot_features import utc

REASON = 'transaction_not_visible_at_as_of'
MESSAGE = 'Giao dịch chưa phát sinh hoặc chưa được biết tại mốc phân tích đã khóa.'


def visible(row, as_of):
    cutoff = utc(as_of)
    return utc(row['observed_at']) <= cutoff and utc(row['posted_at']) <= cutoff


def unavailable_native(source):
    """No visible native core means no engine result, never a synthetic no-hit."""
    from .rules import RULE_NAMES
    rules = []
    for code, name in RULE_NAMES.items():
        kind = ('aggregate_diagnostic' if code.startswith('D') else 'source_diagnostic' if code == 'F4'
                else 'transaction_and_source' if code == 'F3' else 'master_quality' if code in ('B5', 'E3', 'E4') else 'transaction')
        rules.append(dict(rule_id=code, name=name, scope=kind, available=False, status='unavailable',
                          matched=None, score=None, reason='native_core_not_visible_at_as_of',
                          gaps=[dict(table='source', reason='native_core_not_visible_at_as_of')],
                          hits=[], groups=[], findings=[], statistics=[], evaluated_subscopes=0, unavailable_subscopes=0))
    return dict(rules=rules, native_reference_sha256=None, source_sha256=digest(canonical(source)))


def candidate_frame(data, scope, as_of, manifest):
    from .rule_snapshot_features import build_rule_feature_rows, feature_contract
    by_id = {row['transaction_id']: row for row in data['source']['tables']['transactions']}
    requested = data['candidate_transaction_ids']
    eligible = [identity for identity in requested if visible(by_id[identity], as_of)]
    excluded = [identity for identity in requested if identity not in eligible]
    if eligible:
        frame = build_rule_feature_rows(data, scope, as_of, snapshot=manifest,
                                       candidate_transaction_ids=eligible, candidates_only=True,
                                       require_exact_source_cutoff=True)
    else:
        # Do not replay all history, fabricate clocks, or ask a model to score
        # zero/future rows just to construct an empty candidate batch.
        contract = feature_contract()
        frame = dict(version=contract['version'], as_of=utc(as_of).isoformat(),
                     snapshot={k: manifest[k] for k in ('snapshot_id','tenant_id','company_id','checksum','data_checksum','contract_version')},
                     contract=contract, rows=[], features=[], missing=[], evidence=[],
                     manifest=dict(version=contract['version'], status='no_visible_candidates',
                                   source_contract=data['contract_version'], native_profile=data['source']['version'],
                                   snapshot_id=manifest['snapshot_id'], data_checksum=manifest['data_checksum'],
                                   tenant_id=scope.tenant_id, company_id=data['company_id'],
                                   as_of=utc(as_of).isoformat(), row_count=0, candidates_only=True,
                                   candidate_transaction_ids=[], bridge_sha256=contract['bridge_sha256'],
                                   feature_contract_fingerprint=contract['fingerprint']))
    provenance = dict(frame['manifest'])
    provenance.pop('manifest_sha256', None)
    provenance.update(requested_candidate_transaction_ids=list(requested),
                      unavailable_candidates=[dict(record_id=i, reason=REASON) for i in excluded])
    provenance['manifest_sha256'] = digest(canonical(provenance))
    frame['manifest'] = provenance
    return frame


def unavailable_scored_row(transaction, frame):
    from .method_adapters import _graph_unavailable
    from .rule_snapshot_features import _tx_revision
    # Identity/revision are output routing metadata, never a predictor row.
    revision, _ = _tx_revision(transaction)
    evidence = dict(records=[], missing_reasons={c: REASON for c in frame['contract']['columns']},
                    signed_amount_vnd=None, history_group=None, history_type_record_count=None)
    return dict(record_id=transaction['transaction_id'], revision=revision,
                methods={}, graph=_graph_unavailable(REASON, MESSAGE)), evidence
