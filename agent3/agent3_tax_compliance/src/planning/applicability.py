from decimal import Decimal, InvalidOperation
from datetime import date
from ..canonicalization.normalize import exact_sum
from .contracts import PredicateTrace,FieldRequirement


def combine(states):
    if 'NO_MATCH' in states:return 'NO_MATCH'
    return 'UNKNOWN' if 'UNKNOWN' in states else 'MATCH'


def evaluate(rule,get_value,record,context):
    traces=[]
    for predicate in rule.predicates:
        path=predicate.requirement.path
        value,reason=get_value(predicate.requirement)
        state='UNKNOWN'
        if reason is None:
            expected=predicate.value
            try:
                if isinstance(value,Decimal):expected=Decimal(expected)
                elif isinstance(value,date):expected=date.fromisoformat(expected)
                if predicate.operator=='EQ':state='MATCH' if value==expected else 'NO_MATCH'
                else:
                    if not isinstance(value,Decimal):raise ValueError('GTE requires a Decimal field')
                    state='MATCH' if value>=Decimal(predicate.value) else 'NO_MATCH'
            except (ValueError, TypeError, InvalidOperation):
                reason='PREDICATE_TYPE_MISMATCH'
            if path=='context.payment_case' and value=='SPECIAL' and expected=='STANDARD':
                state='UNKNOWN';reason='SPECIAL_PAYMENT_POLICY_UNSUPPORTED'
        traces.append(PredicateTrace(policy=predicate.operator,field_paths=(path,),state=state,reason=reason or 'PREDICATE_EVALUATED'))
    if rule.non_cash_policy:
        amount,amount_reason=get_value(FieldRequirement(path='totals.gross'))
        currency,currency_reason=get_value(FieldRequirement(path='currency'))
        seller,seller_reason=get_value(FieldRequirement(path='parties.seller.tax_id'))
        on_date,date_reason=get_value(FieldRequirement(path='invoice.issue_date'))
        state='UNKNOWN';reason='THRESHOLD_INPUT_UNAVAILABLE';refs=()
        if amount_reason is None and currency_reason is None:
            if currency!='VND':reason='CURRENCY_CONVERSION_UNSUPPORTED'
            elif amount<0:reason='NEGATIVE_AMOUNT_POLICY_UNSUPPORTED'
            elif amount>=rule.inclusive_threshold:state='MATCH';reason='SINGLE_INVOICE_THRESHOLD'
            elif seller_reason is None and date_reason is None:
                daily=context.daily
                if daily is None or not daily.complete:reason='DAILY_PURCHASE_COMPLETENESS_UNKNOWN'
                else:
                    matching=[p for p in daily.purchases if p.issue_date==on_date and p.seller_tax_id==seller.replace('-','')]
                    current=next((p for p in matching if p.record_id==record.record_id),None)
                    from ..canonicalization.derive import sha
                    if current is None or current.revision!=record.revision or current.input_sha256!=sha(record.model_dump(mode='json')) or current.gross!=amount:
                        reason='DAILY_LEDGER_CURRENT_REVISION_MISMATCH'
                    else:
                        total=exact_sum(p.gross for p in matching)
                        state='MATCH' if total>=rule.inclusive_threshold else 'NO_MATCH'
                        reason='COMPLETE_DAILY_AGGREGATE';refs=(daily.verification_reference,daily.version)
        traces.append(PredicateTrace(policy=rule.non_cash_policy,field_paths=('totals.gross','currency','parties.seller.tax_id','invoice.issue_date'),
                                     state=state,reason=reason,evidence_refs=refs))
    return combine([t.state for t in traces]),tuple(traces)
