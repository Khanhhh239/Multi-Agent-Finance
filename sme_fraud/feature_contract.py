"""Bind feature caches and fitted estimators to semantics, not just column names."""
import hashlib
import json
from pathlib import Path

VERSION = 'causal-evidence-20261024-v4'
RELATIONSHIP_SEMANTICS = dict(
    version='current-relationships-v1', state='current_as_of_posted_at',
    current_features=['employee_phone_overlap_current', 'employee_address_overlap_current',
                      'graph_employee_count_current', 'linked_vendor_count_current'],
    historical_features=[], historical_window_days=None,
    master_time='recorded_at', link_time='observed_at', cutoff_inclusive=True,
    master_precedes_equal_time_mirror=True, graph_membership='current_company_members_only')
IMPLEMENTATION = ('feature_contract.py', 'features.py', 'accounting.py', 'generate.py',
                  'temporal_evidence.py', 'exception_validation.py', 'feature_evidence.py', 'identity.py',
                  'identity_graph.py', 'case_identity.py',
                  'payment_evidence.schema.json', 'evidence_sources.schema.json')


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def current_contract():
    from .features import FEATURE_DESCRIPTIONS
    root = Path(__file__).resolve().parent
    contract = dict(version=VERSION, columns=list(FEATURE_DESCRIPTIONS),
                    descriptions=FEATURE_DESCRIPTIONS, dtype='float32', finite=True,
                    relationship_semantics=RELATIONSHIP_SEMANTICS,
                    implementation_sha256={name: sha(root / name) for name in IMPLEMENTATION})
    return dict(contract, fingerprint=digest(contract))


def input_fingerprint(files):
    inputs = {name: entry['sha256'] if isinstance(entry, dict) else entry
              for name, entry in files.items() if name not in {'features.csv', 'labels.csv', 'splits.csv'}}
    return digest(inputs)


def cache_contract(files):
    return dict(current_contract(), input_fingerprint=input_fingerprint(files),
                feature_csv_sha256=files['features.csv']['sha256'])


def validate_cache(metadata):
    actual = metadata.get('feature_contract')
    expected = current_contract()
    if not actual:
        raise ValueError('Legacy feature cache has no semantic provenance; rebuild it before scoring')
    if metadata.get('feature_columns') != expected['columns']:
        raise ValueError('Manifest ordered feature columns mismatch')
    if actual.get('fingerprint') != expected['fingerprint'] or any(actual.get(k) != v for k, v in expected.items()):
        raise ValueError('Feature cache semantics/schema mismatch; rebuild the cache')
    if actual.get('input_fingerprint') != input_fingerprint(metadata['files']):
        raise ValueError('Feature cache input binding mismatch; rebuild the cache')
    if actual.get('feature_csv_sha256') != metadata['files']['features.csv']['sha256']:
        raise ValueError('Feature cache content binding mismatch')
    return actual


def model_compatibility(artifact, metadata, sklearn_version):
    """Return all incompatibilities; legacy artifacts never silently acquire provenance."""
    contract = validate_cache(metadata)
    reasons = []
    if artifact.get('feature_columns') != contract['columns']:
        reasons.append('ordered_columns_mismatch')
    if artifact.get('feature_contract_fingerprint') != contract['fingerprint']:
        reasons.append('semantic_provenance_missing_or_mismatched')
    if artifact.get('sklearn_version') != sklearn_version:
        reasons.append('sklearn_version_missing_or_mismatched')
    if artifact.get('dataset_version') != metadata.get('version'):
        reasons.append('dataset_format_version_mismatch')
    if getattr(artifact.get('model'), 'n_features_in_', None) != len(contract['columns']):
        reasons.append('estimator_input_width_mismatch')
    if not artifact.get('training_feature_fingerprint'):
        reasons.append('training_provenance_missing')
    if artifact.get('score_direction') != 'higher_is_more_anomalous':
        reasons.append('score_direction_mismatch')
    return dict(compatible=not reasons, reasons=reasons, feature_contract_fingerprint=contract['fingerprint'])


def require_model(artifact, metadata, sklearn_version):
    result = model_compatibility(artifact, metadata, sklearn_version)
    if not result['compatible']:
        raise ValueError('IF model incompatible: ' + ', '.join(result['reasons']))
    return result
