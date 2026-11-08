from ..quality.completeness import flatten

KNOWN_PATHS={'record_type','invoice.issue_date','invoice.number','invoice.series','currency',
 'parties.seller.name','parties.seller.tax_id','parties.seller.address',
 'parties.buyer.name','parties.buyer.tax_id','parties.buyer.address',
 'totals.net','totals.vat','totals.gross','derived.invoice_direction',
 'context.vat_method','context.claim_input_vat','context.invoice_kind','context.payment_case','context.obligation_date',
 'item.description','item.quantity','item.unit_price','item.net','item.vat_rate','item.vat_treatment','item.vat_category',
 'group.net','group.vat_rate','group.vat_treatment','group.vat_category'}


def read_field(record,context,path,unit=None):
    if path not in KNOWN_PATHS:raise ValueError('unregistered planning field')
    if path.startswith('context.'):
        found=next((v for v in context.values if v.path==path),None)
        return found.field if found else None,path
    if path=='derived.invoice_direction':return record.derived.invoice_direction,path
    if path.startswith('item.'):
        if unit is None or len(unit.item_refs)!=1:return None,path
        item=next((i for i in record.items if i.item_id==unit.item_refs[0]),None)
        name=path[5:]
        return getattr(item,name,None) if item else None,'items.'+unit.item_refs[0]+'.'+name
    return flatten(record).get(path),path


def usable(field,quality,requirement):
    if field is None or field.status in ('MISSING','NOT_PROVIDED_BY_SOURCE','NOT_APPLICABLE'):
        return None,'MISSING_INPUT'
    if field.status!='PRESENT' or field.value in ('UNKNOWN',None):return None,'AMBIGUOUS_INPUT'
    if quality is None or quality.field_status!=field.status:return None,'VALIDATION_UNAVAILABLE'
    if quality.validation not in requirement.allowed_validity:
        return None,'INVALID_EXTRACTION' if quality.validation=='INVALID_SOURCE_CONTENT' else 'VALIDATION_UNAVAILABLE'
    if quality.validation=='INVALID_SOURCE_CONTENT' and field.provenance.deterministic_policy_version!=requirement.source_fidelity_policy:
        return None,'VALIDATION_UNAVAILABLE'
    if quality.reliability in ('DETERMINISTIC_VERIFIED','HUMAN_CONFIRMED'):
        expected='DETERMINISTIC' if quality.reliability=='DETERMINISTIC_VERIFIED' else 'HUMAN_CONFIRMED'
        if field.confidence_basis!=expected:return None,'RELIABILITY_MISMATCH'
        return field.value,None
    if quality.reliability=='CALIBRATED' and field.confidence_basis=='CALIBRATED':
        if quality.probability is not None and quality.probability==field.confidence and quality.probability>=requirement.min_confidence:
            return field.value,None
        return None,'LOW_CONFIDENCE'
    return None,'LOW_CONFIDENCE'


def decision(reasons):
    if not reasons:return 'ELIGIBLE','NONE',False
    if 'INVALID_EXTRACTION' in reasons:return 'NOT_EVALUATED_INVALID_EXTRACTION','REEXTRACT',True
    if any(r in reasons for r in ('AMBIGUOUS_INPUT','VALIDATION_UNAVAILABLE','RELIABILITY_MISMATCH','OBSERVATION_UNVERIFIED','TAXONOMY_UNVERIFIED')):
        return 'REVIEW_REQUIRED','HUMAN_REVIEW',True
    if 'LOW_CONFIDENCE' in reasons:return 'NOT_EVALUATED_LOW_CONFIDENCE','HUMAN_REVIEW',True
    return 'NOT_EVALUATED_MISSING_INPUT','REQUEST_DATA',False
