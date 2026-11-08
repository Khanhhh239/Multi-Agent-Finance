"""Prepare typed, revision-bound inputs. Readiness is never a tax verdict."""
import hashlib
from decimal import Decimal
from pathlib import Path
from ..canonicalization.derive import sha
from ..domain.cfr import CanonicalFinancialRecord
from ..domain.field import FieldObject
from ..domain.evidence import Provenance
from ..planning.contracts import PlanningContext,ContextValue,FieldObservation,ItemClassification
from ..planning.selector import select
from ..planning.eligibility import usable
from ..planning.contracts import FieldRequirement
from ..quality.contracts import FieldQuality
from ..rules.contracts import PaymentProof
from .contracts import ReviewDossier

VERSION='business-preparation-20261016-v1'


def implementation_sha():
    root=Path(__file__).parent
    return sha({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))})


def observed(field):
    return field.value if field is not None and field.status=='PRESENT' else None


def bind_scope(record,dossier):
    if (dossier.tenant_id,dossier.taxpayer_id,dossier.record_id,dossier.record_revision,dossier.record_sha256)!=(
        record.tenant_id,record.taxpayer_id,record.record_id,record.revision,sha(record.model_dump(mode='json'))):
        raise ValueError('stale or cross-scope dossier')
    if not {p.item_id for p in dossier.products}<={i.item_id for i in record.items}:
        raise ValueError('review references an unknown item')


def human(value,dossier,refs):
    return FieldObject(value=value,status='PRESENT',source='business-review',confidence_basis='HUMAN_CONFIRMED',
        provenance=Provenance(method='business-review',adapter_version=VERSION,review_event_id=dossier.review_id,
                              derived_from=tuple(refs)))


def quality(path):
    return FieldQuality(field_path=path,field_status='PRESENT',validation='VALID',reliability='HUMAN_CONFIRMED',critical=False)


def prepare(record,dossier,rules,legal,profile,assessment):
    record=CanonicalFinancialRecord.model_validate_json(record.model_dump_json())
    if dossier:
        dossier=ReviewDossier.model_validate_json(dossier.model_dump_json());bind_scope(record,dossier)
    if (assessment.tenant_id,assessment.taxpayer_id,assessment.record_id,assessment.record_revision,assessment.input_sha256)!=(
        record.tenant_id,record.taxpayer_id,record.record_id,record.revision,sha(record.model_dump(mode='json'))):
        raise ValueError('stale quality assessment')
    qs={q.field_path:q for q in assessment.fields}
    def reliable(field,path):
        value,reason=usable(field,qs.get(path),FieldRequirement(path=path))
        if field and field.confidence_basis=='CALIBRATED' and field.provenance.calibration_version not in assessment.calibration_versions:
            return None,'LOW_CONFIDENCE'
        return value,reason
    on,day_reason=reliable(record.invoice.issue_date if record.invoice else None,'invoice.issue_date')
    kind_by_id={d.evidence_id:d.kind for d in dossier.documents} if dossier else {}
    values=[];observations=[];classifications=[];checks=[];payment=None
    def refs(part):return tuple('document:'+d.evidence_id+':'+d.sha256 for d in dossier.documents if d.evidence_id in part.evidence_ids)
    def value(path,v,part):
        if v is not None:values.append(ContextValue(path=path,field=human(v,dossier,refs(part)),quality=quality(path),verification_reference=dossier.review_reference))
    def check(rule_id,unit,state,reason,evidence=()):
        family=next(f for f in rules.families if f.rule_id==rule_id)
        version,selection,select_reason=select(family,on if day_reason is None else None)
        if not version:state='NEEDS_REVIEW';reason=select_reason
        checks.append(dict(rule_id=rule_id,unit_id=unit,rule_version=version.version if version else None,
            readiness=state,reason=reason,evidence_refs=list(evidence),
            legal_basis=[b.model_dump(mode='json') for b in version.legal_basis] if version else [],
            release_blocked=not version or version.publication!='APPROVED_TECHNICAL' or not legal.verified(version.legal_basis)))
    invoice=dossier.invoice if dossier else None
    reason='INVOICE_REVIEW_MISSING';state='NEEDS_REVIEW'
    if invoice:
        value('context.vat_method',invoice.vat_method,invoice);value('context.claim_input_vat',invoice.claim_input_vat,invoice)
        if invoice.form=='ORDINARY' and 'INVOICE' in {kind_by_id[i] for i in invoice.evidence_ids}:
            value('context.invoice_kind',invoice.invoice_kind,invoice)
            if invoice.invoice_kind!='VAT':state='NOT_IN_SCOPE';reason='NON_VAT_DOCUMENT'
            elif invoice.document_complete and invoice.seller_tax_id_observed!='UNKNOWN' and profile is not None and 'complete-content-v1' in profile.absence_fidelity_policies:
                seller=record.parties.seller.tax_id if record.parties.seller else None
                kind=invoice.seller_tax_id_observed
                if kind=='PRESENT_VALUE' and reliable(seller,'parties.seller.tax_id')[1] is None:
                    state='READY_FOR_TECHNICAL_CHECK';reason='PRESENCE_REVIEWED'
                elif kind=='CONFIRMED_ABSENT' and (seller is None or seller.status=='MISSING'):
                    state='READY_FOR_TECHNICAL_CHECK';reason='ABSENCE_REVIEWED'
                else:reason='REVIEW_CONFLICTS_WITH_CFR'
                if state=='READY_FOR_TECHNICAL_CHECK':
                    observations.append(FieldObservation(observation_id=dossier.review_id+'.seller',field_path='parties.seller.tax_id',
                        kind=kind,fidelity_policy='complete-content-v1',validator_version=VERSION,method='HUMAN_REVIEW',
                        evidence_reference=refs(invoice)[0],document_complete=True,source_id=record.source_id,
                        source_record_id=record.record_id,source_revision=record.revision,profile_id=profile.profile_id,
                        profile_version=profile.version,verification_reference=dossier.review_reference))
            else:reason='COMPLETE_DOCUMENT_REVIEW_OR_CAPABILITY_REQUIRED'
        else:reason='SPECIAL_OR_UNKNOWN_INVOICE_FORM'
    check('INV_CONTENT_001',record.record_id,state,reason,refs(invoice) if invoice else ())

    reviewed={p.item_id:p for p in dossier.products} if dossier else {}
    for item in record.items:
        product=reviewed.get(item.item_id);category=None;state='NEEDS_REVIEW';reason='PRODUCT_CLASSIFICATION_MISSING'
        treatment,treatment_reason=reliable(item.vat_treatment,'items.'+item.item_id+'.vat_treatment')
        if treatment_reason is None and treatment in ('KCT','KKKNT'):state='NOT_IN_SCOPE';reason='SPECIAL_VAT_TREATMENT'
        elif invoice and invoice.vat_method=='DIRECT':state='NOT_IN_SCOPE';reason='DIRECT_METHOD_OUTSIDE_REDUCTION_RATE_CHECK'
        elif product and on and day_reason is None:
            kinds={kind_by_id[i] for i in product.evidence_ids}
            if not product.effective_from<=on<product.effective_to:reason='PRODUCT_REVIEW_OUTSIDE_INTERVAL'
            elif not kinds & {'PRODUCT_CATALOGUE','CONTRACT'}:reason='INDEPENDENT_PRODUCT_EVIDENCE_REQUIRED'
            elif not product.legal_context_checked:reason='PRODUCT_LEGAL_CONTEXT_NOT_CHECKED'
            elif 'EXCLUDED' in (product.annex_i,product.annex_ii):
                category='REDUCTION_EXCLUDED';state='NOT_IN_SCOPE';reason='EXCLUDED_FROM_REDUCTION_NOT_GENERAL_RATE_VERDICT'
            elif product.base_vat_rate!=Decimal('0.10'):
                state='NOT_IN_SCOPE';reason='BASE_RATE_NOT_TEN_PERCENT'
            elif 'UNKNOWN' in (product.annex_i,product.annex_ii):reason='ANNEX_CLASSIFICATION_UNRESOLVED'
            elif treatment_reason:reason='VAT_TREATMENT_NOT_USABLE'
            elif not invoice or invoice.vat_method!='DEDUCTION' or invoice.form!='ORDINARY' or invoice.invoice_kind!='VAT':reason='VAT_CONTEXT_NOT_CONFIRMED'
            else:
                category='REDUCTION_CANDIDATE'
                rate,rate_reason=reliable(item.vat_rate,'items.'+item.item_id+'.vat_rate')
                state='READY_FOR_TECHNICAL_CHECK' if rate_reason is None else 'NEEDS_REVIEW'
                reason='RATE_DIFFERS_FROM_SCOPED_EIGHT_PERCENT' if rate_reason is None and rate!=Decimal('0.08') else 'PRODUCT_REVIEWED' if rate_reason is None else 'VAT_RATE_NOT_USABLE'
            if category:
                classifications.append(ItemClassification(item_id=item.item_id,item_code=product.product_code,
                    category=human(category,dossier,refs(product)),quality=quality('items.'+item.item_id+'.vat_category'),
                    evidence_kind='HUMAN_CLASSIFICATION',verification_reference=dossier.review_reference))
        check('VAT_RATE_001',item.item_id,state,reason,refs(product) if product else ())
    if not record.items:check('VAT_RATE_001',record.record_id,'NEEDS_REVIEW','ITEM_DISCOVERY_EMPTY')

    review=dossier.payment if dossier else None
    state='NEEDS_REVIEW';reason='PAYMENT_REVIEW_MISSING'
    if review:
        if review.case!='UNKNOWN':value('context.payment_case',review.case,review)
        if review.case!='STANDARD':reason='SPECIAL_OR_UNKNOWN_PAYMENT_CASE'
        else:
            seller,seller_reason=reliable(record.parties.seller.tax_id if record.parties.seller else None,'parties.seller.tax_id')
            buyer,buyer_reason=reliable(record.parties.buyer.tax_id if record.parties.buyer else None,'parties.buyer.tax_id')
            gross,gross_reason=reliable(record.totals.gross,'totals.gross')
            currency,currency_reason=reliable(record.currency,'currency')
            kinds={kind_by_id[i] for i in review.evidence_ids}
            if any((seller_reason,buyer_reason,gross_reason,currency_reason)):reason='PAYMENT_DEPENDENCIES_NOT_USABLE'
            elif currency!='VND' or gross<0:reason='PAYMENT_CURRENCY_OR_NEGATIVE_UNSUPPORTED'
            elif (seller.replace('-',''),buyer.replace('-',''))!=(review.seller_tax_id.replace('-',''),review.buyer_tax_id.replace('-','')):reason='PAYMENT_PARTIES_MISMATCH'
            elif not review.full_settlement or review.amount!=gross:reason='PARTIAL_OR_EXCESS_SETTLEMENT_UNSUPPORTED'
            elif not review.execution_confirmed:reason='SETTLEMENT_EXECUTION_NOT_CONFIRMED'
            elif (review.settlement=='VERIFIED_NON_CASH' and review.method in ('BANK_TRANSFER','CARD') and 'BANK_STATEMENT' in kinds or
                  review.settlement=='VERIFIED_CASH' and review.method=='CASH' and 'CASH_RECEIPT' in kinds or
                  review.settlement=='VERIFIED_CASH' and review.method=='CASH_DEPOSIT_TO_SELLER' and 'BANK_STATEMENT' in kinds):
                present=review.settlement=='VERIFIED_NON_CASH'
                payment=PaymentProof(tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,record_id=record.record_id,
                    record_revision=record.revision,record_sha256=sha(record.model_dump(mode='json')),
                    field=human(present,dossier,refs(review)),quality=quality('payment.non_cash_evidence'),verification_reference=dossier.review_reference)
                state='READY_FOR_TECHNICAL_CHECK';reason='SETTLEMENT_REVIEWED_THRESHOLD_STILL_REQUIRED'
            else:reason='SETTLEMENT_PROOF_MISSING_OR_UNSUPPORTED'
    check('VAT_NON_CASH_PAYMENT_001',record.record_id,state,reason,refs(review) if review else ())
    context=PlanningContext(tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,record_id=record.record_id,
        record_revision=record.revision,values=tuple(values),observations=tuple(observations),classifications=tuple(classifications),
        daily=dossier.daily.ledger if dossier and dossier.daily else None)
    return dict(schema_version='business-readiness-v1',implementation_sha256=implementation_sha(),
        tenant_id=record.tenant_id,taxpayer_id=record.taxpayer_id,record_id=record.record_id,record_revision=record.revision,
        record_sha256=sha(record.model_dump(mode='json')),quality_sha256=sha(assessment.model_dump(mode='json')),
        dossier_sha256=sha(dossier.model_dump(mode='json')) if dossier else None,legal_registry_version=legal.version,
        ruleset_version=rules.version,checks=checks,planning_context=context.model_dump(mode='json'),
        payment_proof=payment.model_dump(mode='json') if payment else None,technical_only=True,tax_verdict=None,
        release_blockers=['LEGAL_RULE_APPROVAL_PENDING','PRODUCT_TAXONOMY_APPROVAL_PENDING'],
        notes=['Readiness does not override source capability, quality, applicability, daily-ledger or publication gates.',
               'Reviewed inputs are local operator attestations; file hashes do not prove legal correctness.'])
