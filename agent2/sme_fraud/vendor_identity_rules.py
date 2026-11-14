"""B5/E4 over complete, point-in-time canonical master bindings.

Preserves the retained default phase2 master-quality policy. No legacy DTO
placeholders, history fabrication, aggregate risk score or HE fallback.
"""
from .identity import normalize
from .noise_policy import assign_noise_points,evidence_id
from .rules import DEFAULT_CONFIG
from .snapshot_features import utc


def evaluate(sources,meta):
    if len(sources['vendor'])!=1 or not sources['vendors']:
        raise ValueError('Ready vendor identity lacks required master bindings')
    vendor=sources['vendor'][0];others=sources['vendors']
    if not any((v['record_id'],v['revision'])==(vendor['record_id'],vendor['revision']) for v in others):
        raise ValueError('Current vendor missing from comparison master')
    fields=('bank_account','phone','address');shared={}
    for field in fields:
        token=normalize(vendor[field],field)
        peers=sorted(v['record_id'] for v in others if v['record_id']!=vendor['record_id'] and token and normalize(v[field],field)==token)
        if peers:shared[field]=peers
    hits=[];proof={}
    if shared:
        ids=sorted({vendor['record_id']}|{i for values in shared.values() for i in values})
        weak=set(shared)=={'address'};at=utc(meta['event_at'])
        proof=dict(shared_fields=shared,vendor_ids=ids,overlap_kind='shared_address_only' if weak else 'shared_bank_or_phone',
            declared_vendor_ids=sorted(v['record_id'] for v in others if v['record_id'] in ids and v['related_party_disclosed_at'] and utc(v['related_party_disclosed_at'])<=at))
        shared_id=evidence_id('vendor_overlap',meta['company_id'],dict(vendor_ids=ids,tokens={f:normalize(vendor[f],f) for f in shared}))
        hits=[dict(rule_id='B5',points=1 if weak else 3,intrinsic_points=1 if weak else 3,
            scoring_role='master_quality',hard_trigger=0,evidence=proof,evidence_id=shared_id,aliases=['E4'])]
        assign_noise_points(hits,DEFAULT_CONFIG['operational_score'])
    return dict(matched=bool(hits),score=hits[0]['points'] if hits else 0,
        intrinsic_points=hits[0]['intrinsic_points'] if hits else 0,
        details=dict(evidence=proof,hits=hits,scoring_role='master_quality',source_rule_id='B5',aliases=['E4'],
            observed_other_vendor_count=len(others)-1,comparison_fields=list(fields),
            bank_comparison='retained_untyped_account_token_not_verified_bank_identity',
            score_reason=hits[0]['score_reason'] if hits else 'Không thấy thông tin trùng trong các NCC đã cung cấp; chưa xác nhận đầy đủ master ngoài snapshot.'))
