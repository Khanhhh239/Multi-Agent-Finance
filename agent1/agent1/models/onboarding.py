"""Chọn chiến lược nghiên cứu từ kiểm định công ty nguồn, không học từ tgt."""
import json
from pathlib import Path
import math
from ..paths import OUT

STRATEGIES={'zero-shot','fine-tune','target-only','ensemble-b1d'}


def choose_strategy(M, n_rows, domain_distance, policy_path=None):
    """n_rows là số snapshot huấn luyện; khoảng cách miền là AUC trong [0.5,1].

    Khi thiếu bằng chứng hoặc ngoài miền đã kiểm định, giữ zero-shot và cổng
    NO-GO của dịch vụ. Hàm này không tự cho phép triển khai pilot.
    """
    if M<0 or n_rows<0 or not all(math.isfinite(float(x)) for x in [M,n_rows,domain_distance]) or not .5<=domain_distance<=1:
        raise ValueError('M/số hàng không âm, khoảng cách miền là AUC 0.5–1')
    path=Path(policy_path) if policy_path else OUT/'t1/onboarding_source_policy.json'
    if not path.exists():return 'zero-shot'
    policy=json.loads(path.read_text(encoding='utf-8'))
    if policy.get('target_used') is not False or policy.get('selection_domain')!='src_company_holdout':
        raise ValueError('Chính sách phải được chọn trên công ty nguồn giữ lại')
    if set(policy['training_firms']) & set(policy['validation_firms']):
        raise ValueError('Công ty nguồn train và validation phải tách biệt')
    if domain_distance>policy['max_validated_domain_auc']:return 'zero-shot'
    candidates=[r for r in policy['rules'] if r['months_history']<=M and r['min_rows']<=n_rows]
    if not candidates:return 'zero-shot'
    selected=max(candidates,key=lambda r:r['months_history'])['strategy']
    if selected not in STRATEGIES:raise ValueError('Chiến lược không được phép')
    return selected
