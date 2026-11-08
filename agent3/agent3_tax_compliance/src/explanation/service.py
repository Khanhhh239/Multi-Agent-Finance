import json
from pathlib import Path
from ..canonicalization.derive import sha
from ..domain.cfr import CanonicalFinancialRecord
from ..legal_registry.registry import LegalRegistry
from ..quality.completeness import flatten
from ..orchestration.contracts import Explanation,RuleResultView,LegalCitation,SourceLink
from ..rules.contracts import ExecutionError

TEMPLATE=Path(__file__).resolve().parent/'templates/vi_v1.json'


def load_templates():return json.loads(TEMPLATE.read_text(encoding='utf-8'))


def render(evaluation_id,plan,result,inputs,templates):
    from ..rules.outcomes import token
    from ..rules.context import key_for
    record=CanonicalFinancialRecord.model_validate(inputs['record'])
    legal=LegalRegistry.model_validate(inputs['legal'])
    fields=flatten(record)
    docs={d.document_id:d for d in legal.documents}
    outcomes={token(o.key):o for o in result.outcomes}
    rows=[]
    actions=[]
    for entry in sorted(plan.entries,key=lambda e:(e.rule_id,e.rule_version or '',e.unit.unit_type,e.unit.unit_id)):
        outcome=outcomes.get(token(key_for(plan,entry))) if entry.rule_version else None
        invalid_result=result.aggregate.processing_status=='ERROR'
        citations=tuple(LegalCitation(document_id=b.document_id,locator=b.locator,official_url=docs[b.document_id].official_url,
            sha256=docs[b.document_id].sha256,locator_reviewed=legal.verified((b,))) for b in entry.legal_basis if b.document_id in docs)
        sources=[];paths=[]
        if outcome and outcome.context:
            paths=[p for c in outcome.context.conditions for p in c.field_paths]
        else:
            paths=[p for t in entry.traces for p in t.field_paths]
            family=next((f for f in inputs['ruleset']['families'] if f['rule_id']==entry.rule_id),None)
            selected=next((v for v in family['versions'] if v['version']==entry.rule_version),None) if family else None
            if selected:paths.extend([r['path'] for r in selected['required_fields']]+[r['field_path'] for r in selected['required_observations']])
        # Metadata is a navigation aid, never a guessed box when source text is absent.
        for path in dict.fromkeys(paths):
            expanded=['items.'+i+'.'+path.split('.',1)[1] for i in entry.unit.item_refs] if path.startswith(('item.','group.')) else [path]
            for canonical in expanded:
                field=fields.get(canonical)
                if field is not None:
                    sources.append(SourceLink(field_path=canonical,evidence=field.provenance.evidence,reference='cfr:'+plan.record_sha256+':'+canonical))
        action=outcome.error.next_action if outcome and outcome.error else entry.next_action
        if action!='NONE':actions.append(templates['actions'][action])
        text=templates['eligibility'].get(entry.eligibility,'Cần kiểm tra điều kiện đánh giá.')
        if outcome:
            text={'PASS':'Đơn vị kiểm tra này đã đạt theo model và revision được pin.',
                  'FAIL':'Đơn vị kiểm tra này không đạt theo model và revision được pin.',
                  'REVIEW':'Kết quả của đơn vị này cần người đối chiếu.'}.get(outcome.result,
                  'Kiểm tra gặp lỗi kỹ thuật; chưa có kết quả thuế cho đơn vị này.')
        if invalid_result:text='Chưa thể diễn giải kết quả của đơn vị này vì hợp đồng xử lý không hợp lệ.'
        rows.append(RuleResultView(evaluation_id=evaluation_id,result_id='unit-'+sha([entry.rule_id,entry.rule_version,entry.unit.model_dump(mode='json')])[:24],
            planning_evaluation_id=plan.evaluation_id,rule_id=entry.rule_id,rule_version=entry.rule_version,unit_type=entry.unit.unit_type,
            unit_id=entry.unit.unit_id,item_refs=entry.unit.item_refs,eligibility=entry.eligibility,applicability=entry.applicability,capability=entry.capability,
            review_required=entry.review_required or bool(outcome and outcome.result=='REVIEW'),
            execution_status='ERROR' if invalid_result else outcome.execution_status if outcome else 'NOT_RUN',result=outcome.result if outcome and not invalid_result else None,
            error=ExecutionError(code='OUTCOME_CONTRACT_ERROR',message='No valid tax result may be interpreted.') if invalid_result else outcome.error if outcome else None,attempt_id=outcome.attempt_id if outcome else None,outcome_key=outcome.key if outcome else None,
            reasons=entry.reasons,next_action='OPERATOR' if invalid_result else action,explanation=text,citations=citations,sources=tuple(sources),trace=outcome.trace if outcome and not invalid_result else None))
    aggregate=result.aggregate
    code=aggregate.verdict if aggregate.verdict is not None else 'PROCESSING_ERROR'
    notices=['Bản kỹ thuật: rule/model và mapping thực tế chưa được nghiệm thu pháp lý.',
             'Chất lượng trích xuất, phạm vi kiểm tra và kết quả rule là các thông tin riêng.']
    if aggregate.review_required:notices.append('Vẫn còn yêu cầu người đối chiếu, kể cả khi có kiểm tra không đạt.')
    if aggregate.coverage!='FULL':notices.append('Chưa kiểm tra đầy đủ mọi đơn vị trong phạm vi đã chọn.')
    if aggregate.operational_errors:notices.append('Có lỗi xử lý; xem từng mục để phục hồi.')
    scope=f'Chỉ áp dụng cho bản dữ liệu {record.revision}, planning {plan.evaluation_id}, ruleset '+next(p.version for p in plan.pins if p.name=='ruleset')+'.'
    explanation=Explanation(template_version=templates['version'],title=templates['titles'][code],text=templates['texts'][code],scope=scope,
        verdict=aggregate.verdict,notices=tuple(notices),next_actions=tuple(dict.fromkeys(actions)))
    return explanation,tuple(rows)
