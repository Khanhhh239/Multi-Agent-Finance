"""Source bindings for retained rules, before any canonical rule evaluation.

Only the private resolver sees verified snapshot payloads. Public diagnostics
contain references and missing dependencies, never invented legacy DTO values.
"""
from copy import deepcopy
from pathlib import Path

from finance_input import schema
from .import_files import canonical, digest, fail
from .imports import DEFINITIONS
from .rules import RULE_NAMES
from .evidence_policy import required_columns as evidence_columns
from .authority_policy import AUTHORITY_REQUIRED, COVERAGE_REQUIRED
from .tax_risk import FIELDS as TAX_FIELDS
from .exception_validation import PROFILES
from .snapshot_features import _selected, _ref, available, utc

VERSION = 'rule-inputs/1.0.0'
ROLES = {'transaction_history':'transactions', 'vendor':'vendors',
         'employee':'employees', 'creator':'employees'}

# Fields absent from input contract 1.0.0 remain explicit dependencies. In
# particular, an observed approval limit is not an approved authority matrix.
PAYMENT = dict(transactions=('amount_vnd','kind','bank_account','bank_code','created_by_ref'),
               transaction_history=('amount_vnd','kind','bank_account','bank_code','created_by_ref'),
               approvals=('limit_vnd','employee_ref','decision'),
               approval_authorities=AUTHORITY_REQUIRED,
               invoices=('amount_vnd','number','vendor_ref'),
               payment_allocations=('transaction_ref','invoice_ref','amount_vnd'),
               supporting_documents=('subject_refs','document_kind','verification_status'),
               payment_requests=('request_id','purchase_order_id','approved_at'),
               supplier_payment_agreements=('total_vnd','approved_at','evidence_id'))
BASELINE = dict(transactions=('amount_vnd','accounting_lines'),
                transaction_history=('amount_vnd','accounting_lines'),
                journal_documents=('document_id','posted_at','observed_at'),
                journal_lines=('document_id','account_code','posted_at','debit_vnd','credit_vnd'),
                operating_schedules=('effective_from','effective_to','approved_at'))
DIGITS = dict(transactions=('amount_vnd','kind','posted_at','payment_channel','is_financial_entry'),
              transaction_history=('amount_vnd','kind','posted_at','payment_channel','is_financial_entry','created_by_ref'))
PAYROLL = dict(transactions=('amount_vnd','kind','employee_ref','payroll_period'),
               employee=('hired_at','terminated_at'),
               supporting_documents=('subject_refs','document_kind','verification_status'),
               payroll_entitlements=('payroll_period','entitled_amount_vnd','approved_at'))
REQUIREMENTS = {
    'A1':PAYMENT, 'A2':PAYMENT,
    'A3':dict(PAYMENT, entity_links=('effective_at','observed_at','from_id','to_id','evidence_id'),
              vendors=('bank_account','bank_code','phone','address'),
              employees=('bank_account','bank_code','phone','address')),
    'A4':dict(PAYMENT, recurring_payments=('frequency','expected_amount_vnd','approved_at')),
    'A5':dict(BASELINE, recurring_payments=('frequency','expected_amount_vnd','approved_at')),
    'A6':dict(transactions=('amount_vnd','kind','payment_channel'),
              invoices=('amount_vnd','number','net_vnd','vat_vnd'),
              payment_allocations=('transaction_ref','invoice_ref','amount_vnd')),
    'B1':dict(transactions=('kind','bank_account','bank_code','accounting_lines','payment_channel'),
              vendor=('bank_account','bank_code','national_id','related_party_disclosed_at'),
              employees=('bank_account','bank_code','national_id')),
    'B2':dict(vendor=('address','phone','related_party_disclosed_at'),employees=('address','phone'),
              entity_links=('effective_at','observed_at','from_id','to_id','evidence_id')),
    'B3':dict(transactions=('amount_vnd','kind','payment_channel'),vendor=('registered_at',),
              transaction_history=('amount_vnd','kind','vendor_ref'),approvals=('limit_vnd',),
              supporting_documents=('document_kind','verification_status','subject_refs')),
    'B4':dict(invoices=('number','effective_at','vendor_ref'),vendor=('tax_id',),
              tax_risk_history=TAX_FIELDS,
              supporting_documents=('document_kind','verification_status','subject_refs')),
    'B5':dict(vendor=('bank_account','phone','address','related_party_disclosed_at'),
              vendors=('bank_account','phone','address','related_party_disclosed_at')),
    'B6':dict(transactions=('amount_vnd','kind'),vendor=('name',),
              transaction_history=('amount_vnd','kind','vendor_ref'),
              vendor_payment_schedules=('expected_amount_vnd','approved_at','effective_from','effective_to')),
    'B7':dict(transactions=('kind','bank_account','bank_code'),vendor=('bank_account','bank_code'),
              vendor_bank_history=('vendor_ref','bank_account','bank_code','verification_status','verification'),
              bank_account_changes=('change_id','vendor_id','new_account','new_bank_code','effective_at','observed_at','callback_verified','verified_at','approver_id'),
              employees=('name',)),
    'C1':dict(transactions=('created_at',),approvals=('approved_at','employee_ref'),
              creator=('name',),employees=('name',),
              companies=('saturday_operations',),
              operating_schedules=('effective_from','effective_to','approved_at'),calendar=('date','is_holiday')),
    'C2':dict(transactions=('amount_vnd','created_by_ref'),creator=('self_approval_limit_vnd',),
              approvals=('employee_ref','decision','limit_vnd','approved_at'),
              approval_authorities=('effective_from','effective_to','approved_at','scope','limit_vnd'),
              approval_authority_coverage=('coverage_start','coverage_end')),
    'C3':dict(transactions=('amount_vnd','created_at'),approvals=('approved_at','employee_ref'),
              approval_authorities=('authority_level','effective_from','effective_to','approved_at')),
    'C4':dict(transactions=('created_at','created_by_ref'),approvals=('approved_at','employee_ref'),
              leave_periods=tuple(evidence_columns('leave_periods')),
              system_actions=tuple(evidence_columns('system_actions')),
              leave_activity_authorizations=tuple(evidence_columns('leave_activity_authorizations'))),
    'D1':DIGITS, 'D2':DIGITS, 'D3':dict(DIGITS,approvals=('limit_vnd',)),
    'D4':DIGITS, 'D5':DIGITS,
    'D6':dict(DIGITS,transaction_history=(*DIGITS['transaction_history'],'department','project_id')),
    'E1':dict(PAYROLL,attendance=('payroll_period','employee_id','days_worked_observed','alternative_work_evidence')),
    'E2':dict(PAYROLL,employment_events=tuple(evidence_columns('employment_events')),
              payroll_settlements=tuple(evidence_columns('payroll_settlements'))),
    'E3':dict(vendor=('name',),vendors=('name',)),
    'E4':dict(vendor=('bank_account','phone','address','related_party_disclosed_at'),
              vendors=('bank_account','phone','address','related_party_disclosed_at')),
    'F1':dict(transactions=('amount_vnd','accounting_lines','created_by_ref'),
              journal_audit_log=('entry_origin','entered_at','observed_at','employee_id'),
              closing_periods=('period_start','period_end','closing_at','approved_at'),
              materiality_policies=('materiality_vnd','approved_at','effective_from','effective_to')),
    'F2':dict(transactions=('created_by_ref',),approvals=('employee_ref','approved_at'),
              workflow_policies=tuple(evidence_columns('workflow_policies')),
              override_events=tuple(evidence_columns('override_events'))),
    'F3':dict(document_series=tuple(evidence_columns('document_series')),
              document_register=tuple(evidence_columns('document_register')),
              document_cancellations=tuple(evidence_columns('document_cancellations'))),
    'F4':dict(transactions=('amount_vnd','kind','accounting_lines'),
              receivable_invoices=tuple(evidence_columns('receivable_invoices')),
              receipt_allocations=tuple(evidence_columns('receipt_allocations')),
              receipt_coverage=tuple(evidence_columns('receipt_coverage')),
              receivable_explanations=tuple(evidence_columns('receivable_explanations'))),
    'P1':dict(transactions=('amount_vnd','kind','payment_channel'),
              invoices=('amount_vnd','number','vendor_ref'),
              payment_allocations=('transaction_ref','invoice_ref','amount_vnd'),
              transaction_history=('amount_vnd','kind')),
    'P2':dict(transactions=('amount_vnd','payment_channel','vat_treatment'),
              invoices=('amount_vnd','vat_vnd'),supporting_documents=('document_kind','verification_status','subject_refs'),
              cash_limit_policies=('limit_vnd','effective_from','approved_at')),
    'T1':dict(advances=('original_amount_vnd','original_due_at','recorded_at','employee_id'),
              advance_events=('event_type','amount_vnd','observed_at'),
              transactions=('amount_vnd','advance_id')),
    'T2':dict(advances=('original_amount_vnd','employee_id'),advance_events=('event_type','observed_at','evidence_on_file'),
              transactions=('amount_vnd','advance_id'),
              supporting_documents=('document_kind','verification_status','subject_refs')),
}
KINDS = {**{r:('payment',) for r in ('A1','A2','A3','A6','B6','B7','P1')},
         'E1':('payroll',),'E2':('payroll',)}
REQUIREMENTS['C2']['approval_authorities']=AUTHORITY_REQUIRED
REQUIREMENTS['C2']['approval_authority_coverage']=COVERAGE_REQUIRED
REQUIREMENTS['C3']['approval_authorities']=AUTHORITY_REQUIRED
REQUIREMENTS['C3']['approval_authority_coverage']=COVERAGE_REQUIRED
# Use the retained contracts for typed evidence, rather than inventing their
# column names while the canonical input contract does not yet include them.
for requirements in REQUIREMENTS.values():
    for table in tuple(requirements):
        if table in PROFILES:requirements[table]=tuple(PROFILES[table]['required'])
assert set(REQUIREMENTS)==set(RULE_NAMES), 'Every retained rule needs an explicit source plan'


def source_catalog():
    """Static audit map, not a declaration that sources or evaluators exist."""
    definitions=schema()['$defs']
    result=[]
    for code,requirements in REQUIREMENTS.items():
        bindings=[]
        for role,fields in requirements.items():
            table=ROLES.get(role,role)
            supported=definitions[DEFINITIONS[table]]['properties'] if table in DEFINITIONS else {}
            bindings.append(dict(role=role,table=table,fields=list(fields),
                                 contract_missing_fields=[f for f in fields if f not in supported]))
        result.append(dict(rule_id=code,name=RULE_NAMES[code],bindings=bindings,
                           applicable_kinds=list(KINDS.get(code,())),evaluation_status='not_evaluated'))
    return result


def _gap(table,field,code,record=None,reference=None):
    result=dict(table=table,field=field,code=code,
        action='Bổ sung nguồn có định danh, phiên bản và thời điểm thực sự được biết; kiểm tra lại và tạo snapshot mới, không lùi observed_at.')
    if code in ('source_not_in_input_contract','field_not_in_input_contract'):
        result['action']='Nguồn/trường này chưa thuộc hợp đồng đầu vào 1.0.0. Cần adapter hoặc hợp đồng phiên bản mới được kiểm thử trước khi nhập; không thêm cột tùy ý hoặc dùng giá trị thay thế.'
    if record:result['record_id']=record['record_id'];result['revision']=record['revision']
    if reference:result['reference']=dict(reference)
    return result


def _resolve(bundle,frame,scope):
    """Internal only: bundle/frame from scoped, immutable snapshot reads.

    Return private payloads separately from safe diagnostics. Never call a rule,
    feature fit, model fit, or use the placeholder DTO of snapshot_features.
    """
    if len(scope.company_ids)!=1 or 'data.import' not in scope.permissions:
        fail(403,'ACCESS_DENIED','Không đủ quyền đọc nguồn luật của một doanh nghiệp.','Chọn đúng doanh nghiệp và quyền đọc.')
    cid=next(iter(scope.company_ids))
    if bundle['tenant_id']!=scope.tenant_id:
        fail(403,'ACCESS_DENIED','Nguồn luật khác tenant.','Chọn snapshot đúng quyền.')
    for table in DEFINITIONS:
        if any((r['tenant_id'],r['company_id'])!=(scope.tenant_id,cid) for r in bundle[table]):
            fail(403,'ACCESS_DENIED','Nguồn luật chứa bản ghi ngoài doanh nghiệp.','Dùng snapshot chỉ chứa doanh nghiệp được phép.')
    transactions={(r['record_id'],r['revision']):r for r in bundle['transactions']}
    catalog=source_catalog();private={};public={}
    for meta in frame['rows']:
        if (meta['tenant_id'],meta['company_id'])!=(scope.tenant_id,cid):
            fail(403,'ACCESS_DENIED','Giao dịch ngoài phạm vi nguồn luật.','Chọn snapshot đúng quyền.')
        key=meta['record_id'],meta['revision'];tx=transactions[key]
        event,cutoff=utc(meta['event_at']),utc(meta['as_of'])
        if event!=utc(tx['effective_at']) or cutoff!=available(tx) or cutoff>utc(frame['as_of']):
            raise ValueError('Rule source cutoff does not match snapshot feature row')
        selected={t:_selected(bundle[t],cid,cutoff,event) for t in DEFINITIONS if t!='transactions'}
        history,history_versions=_selected(bundle['transactions'],cid,cutoff,event,strict=True,exclude={tx['record_id']})
        visible_transactions={k:r for k,r in transactions.items() if utc(r['observed_at'])<=cutoff and utc(r['effective_at'])<=event}
        sources={'transactions':[tx],'transaction_history':list(history.values())}
        links=[]

        def resolve(table,ref,owner,field):
            if not ref:return None
            target=selected[table][1].get((ref['record_id'],ref['revision']))
            if target is None:links.append(_gap(table,field,'referenced_revision_unavailable',owner,ref))
            return target

        for role,table,field in (('vendor','vendors','vendor_ref'),('employee','employees','employee_ref'),('creator','employees','created_by_ref')):
            exact=resolve(table,tx.get(field),tx,field)
            # An explicit old reference must be known; then the master in force
            # at this cutoff governs contextual comparisons, as in R1.
            sources[role]=[selected[table][0][exact['record_id']]] if exact else []
        for table in ('companies','vendors','employees'):
            sources[table]=list(selected[table][0].values())
        allocations=[];invoices={}
        for a in selected['payment_allocations'][0].values():
            if a['transaction_ref']['record_id']!=tx['record_id']:continue
            if a['transaction_ref']['revision']!=tx['revision']:
                links.append(_gap('transactions','transaction_ref','allocation_targets_other_transaction_revision',a,a['transaction_ref']))
                continue
            allocations.append(a)
            invoice=resolve('invoices',a['invoice_ref'],a,'invoice_ref')
            if invoice:
                invoices[(invoice['record_id'],invoice['revision'])]=invoice
                resolve('vendors',invoice.get('vendor_ref'),invoice,'vendor_ref')
        prior_allocations=[]
        past,_=_selected(bundle['payment_allocations'],cid,cutoff,event,strict=True)
        for a in past.values():
            if a['invoice_ref']['record_id'] not in {i[0] for i in invoices}:continue
            ref=a['transaction_ref']
            if ref['record_id']==tx['record_id']:continue
            h=visible_transactions.get((ref['record_id'],ref['revision']))
            if h is None:
                links.append(_gap('transactions','transaction_ref','referenced_revision_unavailable',a,ref));continue
            # Simultaneous rows cannot enter each other's histories, even if an
            # allocation itself was already visible. Signed corrections survive.
            if not (utc(h['effective_at'])<event and available(h)<cutoff):continue
            prior_allocations.append(a)
            resolve('invoices',a['invoice_ref'],a,'invoice_ref')
            if (ref['record_id'],ref['revision']) not in history_versions:
                links.append(_gap('transactions','transaction_ref','history_revision_unavailable',a,ref))
        sources['invoices']=list(invoices.values())
        sources['payment_allocations']=allocations+prior_allocations
        sources['approvals']=[]
        for a in selected['approvals'][0].values():
            if a['transaction_ref']!={'record_id':tx['record_id'],'revision':tx['revision']}:continue
            sources['approvals'].append(a)
            resolve('employees',a['employee_ref'],a,'employee_ref')
        vendor_ids={v['record_id'] for v in sources['vendor']}
        sources['vendor_bank_history']=[]
        for b in selected['vendor_bank_history'][0].values():
            if b['vendor_ref']['record_id'] in vendor_ids:
                sources['vendor_bank_history'].append(b);resolve('vendors',b['vendor_ref'],b,'vendor_ref')
        subjects={('transactions',tx['record_id'],tx['revision'])}|{('invoices',*k) for k in invoices}
        sources['supporting_documents']=[d for d in selected['supporting_documents'][0].values()
            if any((s['table'],s['record_id'],s['revision']) in subjects for s in d['subject_refs'])]
        for table,records in sources.items():records.sort(key=lambda r:(r['record_id'],r['revision']))
        entries=[]
        for plan in catalog:
            code=plan['rule_id'];gaps=[];refs={};bound={}
            applicable=not plan['applicable_kinds'] or tx['kind'] in plan['applicable_kinds']
            if applicable:
                for binding in plan['bindings']:
                    role,table=binding['role'],binding['table'];records=sources.get(role,[])
                    bound[role]=records
                    if table not in DEFINITIONS:
                        gaps.append(_gap(table,'*','source_not_in_input_contract'));continue
                    if not records:gaps.append(_gap(table,'*','no_visible_source'))
                    for field in binding['contract_missing_fields']:
                        gaps.append(_gap(table,field,'field_not_in_input_contract'))
                    for record in records:
                        ref=_ref(table,record);refs[(table,record['record_id'],record['revision'])]=ref
                        for field in binding['fields']:
                            if field not in binding['contract_missing_fields'] and (record.get(field) is None or field in record.get('missing_fields',{})):
                                gaps.append(_gap(table,field,'field_not_provided',record))
                relevant={ROLES.get(role,role) for role in REQUIREMENTS[code]}
                # Only dependencies used by this rule propagate link failures.
                gaps.extend(g for g in links if g['table'] in relevant and
                    (g['field'] not in ('invoice_ref','transaction_ref') or 'payment_allocations' in relevant))
            state='not_applicable' if not applicable else 'unavailable' if gaps else 'ready'
            entries.append(dict(rule_id=code,name=plan['name'],source_status=state,
                evaluation_status='not_evaluated',required_bindings=plan['bindings'],
                gaps=sorted(gaps,key=canonical),evidence_refs=[refs[k] for k in sorted(refs)],
                source_checksum=digest(canonical(bound)) if applicable else None))
        private[key]=deepcopy(sources)
        public[key]=dict(version=VERSION,evaluation_status='not_evaluated',rules=entries,
            implementation_sha256=digest(Path(__file__).read_bytes()),
            coverage_basis='known_records_in_this_snapshot_only_not_complete_external_books',
            history_policy='effective_at<event_at AND available_at<as_of; self and simultaneous groups excluded',
            score_status='unavailable_until_canonical_rule_evaluators_are_validated')
    return private,public
