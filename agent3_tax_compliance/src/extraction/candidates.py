from ..domain.evidence import Provenance,stable_candidate_id
from ..domain.field import Candidate,FieldObject
from .contracts import ExtractionCandidate,RawScore,ExtractionIssue


def make_candidate(path,raw,normalized,blocks,reason='UNIQUE_VALUE'):
    blocks=tuple({b.block_id:b for b in blocks}.values())
    evidence=tuple(b.evidence.model_copy(update={'span':b.evidence.span or (0,len(b.text_raw))}) for b in blocks if b.evidence and b.text_raw)
    identifier=stable_candidate_id(path+'='+normalized,raw,evidence)
    scores=tuple(RawScore(block_id=b.block_id,value=o.raw_score,kind=o.score_kind,semantics=o.score_semantics)
                 for b in blocks for o in b.origins if o.method=='OCR')
    return ExtractionCandidate(candidate_id=identifier,semantic_field=path,raw_value=raw,normalized_value=normalized,
        evidence_refs=evidence,block_refs=tuple(b.block_id for b in blocks),raw_scores=scores,selection_reason=reason)


def provenance(candidates=(),method='label-region-v1'):
    ev={e.model_dump_json():e for c in candidates for e in c.evidence_refs}
    return Provenance(method=method,adapter_version='extractor-v1',evidence=tuple(ev.values()))


def choose(path,candidates,issues):
    candidates=tuple({c.candidate_id:c for c in candidates}.values())
    values={c.normalized_value for c in candidates}
    prov=provenance(candidates)
    if not values: return FieldObject(status='MISSING',source='document',provenance=prov),()
    ambiguous=len(values)>1
    marked=tuple(c.model_copy(update={'selection_reason':'COMPETING_VALUE' if ambiguous else c.selection_reason}) for c in candidates)
    domain=tuple(Candidate(candidate_id=c.candidate_id,raw_value=c.raw_value,value=c.normalized_value,provenance=provenance((c,))) for c in marked)
    if ambiguous:
        issues.append(ExtractionIssue(code='AMBIGUOUS_FIELD',field_path=path,message='Competing observed values require review.',
                                      block_refs=tuple(ref for c in marked for ref in c.block_refs)))
    if any(not c.evidence_refs for c in marked):
        issues.append(ExtractionIssue(code='GEOMETRY_UNAVAILABLE',field_path=path,message='Text has no source geometry.'))
    return FieldObject(status='AMBIGUOUS' if ambiguous else 'PRESENT',value=None if ambiguous else next(iter(values)),
                       source='document',provenance=prov,candidates=domain),marked
