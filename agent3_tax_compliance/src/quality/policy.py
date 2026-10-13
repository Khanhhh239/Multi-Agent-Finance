from pathlib import Path
from .contracts import QualityPolicy

def load_policy(path=None):
    # JSON is a YAML subset; avoid introducing a parser dependency.
    path=path or Path(__file__).resolve().parents[2]/'configs/quality/quality_policy_v1.yaml'
    return QualityPolicy.model_validate_json(Path(path).read_text(encoding='utf-8'))

def profile_for(policy,record):
    for profile in policy.profiles:
        if profile.record_type==record.record_type: return profile
    raise ValueError('unsupported quality profile; do not silently use invoice expectations')

def confidence_reason(probability,threshold):
    if probability is None: return 'CONFIDENCE_UNAVAILABLE'
    if threshold is None: return 'ACCEPTANCE_THRESHOLD_UNAVAILABLE'
    return 'LOW_CONFIDENCE' if probability<threshold else None
