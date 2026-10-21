"""Declared P2 controls: expectations are independent of detector output."""
from copy import deepcopy
from datetime import datetime, timedelta

from .accounting import enrich_accounting, account_supported, pair_supported
from .generate import stamp, TZ
from .rule_audit_cases import Case
from .rules import DEFAULT_CONFIG

VERSION = 'p2-controls-20261018-v1'
AT = datetime(2025, 8, 12, 11, tzinfo=TZ)


def expected(category=None, *, a5_suppressed=None):
    points, priority, route = {
        None: (0, '', ''), 'information_request': (0, 'thap', 'information_request'),
        'vat_document_review': (8, 'trung_binh', 'transaction'),
        'verified_internal_breach': (14, 'cao', 'transaction')}[category]
    result = dict(p2_present=category is not None, category=category, points=points,
                  case_type=route, priority=priority)
    if a5_suppressed is not None:
        result['a5_suppressed'] = a5_suppressed
    return result


def declarations():
    """Names, source parameters and outcomes are locked before any scoring."""
    specifications = []
    def add(identity, group, title, recipe, outcomes, **settings):
        specifications.append(dict(control_id=identity, group=group, title_vi=title,
            recipe=recipe, settings=settings, expected=outcomes))
    for identity, title, amount, at, outcome in (
        ('FULL_BELOW','Hóa đơn đủ, dưới ngưỡng đối chiếu',4_999_999,AT,None),
        ('FULL_EQUAL','Hóa đơn đủ, đúng ngưỡng đối chiếu',5_000_000,AT,'vat_document_review'),
        ('FULL_ABOVE','Hóa đơn đủ, trên ngưỡng đối chiếu',5_000_001,AT,'vat_document_review'),
        ('OLD_BELOW','Mốc lịch sử: dưới ngưỡng phiên bản cũ',19_999_999,AT.replace(year=2024),None),
        ('OLD_EQUAL','Mốc lịch sử: đúng ngưỡng phiên bản cũ',20_000_000,AT.replace(year=2024),'vat_document_review')):
        add(identity,'full_invoice',title,'single',[expected(outcome)],amount=amount,at=stamp(at))
    add('FULL_BANK','full_invoice','Hóa đơn đủ, trả qua ngân hàng','single',[expected()],amount=30_000_000,bank=True)
    for identity, title, missing in (
        ('NO_INVOICE','Không có thông tin hóa đơn','all'),
        ('NO_DATE','Thiếu ngày hóa đơn','date'),
        ('NO_GROSS','Thiếu tổng tiền hóa đơn','gross'),
        ('NO_IDENTITY','Thiếu mã và số hóa đơn','identity'),
        ('FUTURE_INVOICE','Hóa đơn chỉ có sau lúc chi','future')):
        add(identity,'missing_documents',title,'single',[expected('information_request')],amount=5_000_000,missing=missing)
    add('INSTALL_CASH','installments','Hai đợt tiền mặt nhỏ thuộc một hóa đơn lớn','installments',
        [expected('vat_document_review')]*2,amounts=[3_000_000,3_000_000],gross=12_000_000)
    add('INSTALL_SMALL','installments','Hai đợt nhỏ, hóa đơn tổng dưới ngưỡng','installments',
        [expected()]*2,amounts=[2_000_000,2_000_000],gross=4_000_000)
    add('INSTALL_MIXED','installments','Một đợt ngân hàng và một đợt tiền mặt','installments',
        [expected(),expected('vat_document_review')],amounts=[19_000_000,1_000_000],gross=20_000_000,mixed=True)
    add('INSTALL_SAME_TIME','installments','Hai khoản cùng thời điểm dùng cùng hóa đơn','installments',
        [expected('vat_document_review')]*2,amounts=[1_000_000,1_000_000],gross=10_000_000,same_time=True)
    add('INSTALL_GAP','installments','Có tổng hóa đơn nhưng chưa có ngày phát hành','installments',
        [expected('information_request')]*2,amounts=[3_000_000,3_000_000],gross=12_000_000,missing_date=True)
    for identity, title, recipe, outcomes, settings in (
        ('REFUND_FULL','Hoàn đủ tiền mặt sau khoản chi','refund',[expected('vat_document_review'),expected()],dict(amount=5_000_000,returns=[5_000_000])),
        ('REFUND_PART','Hoàn một phần tiền mặt','refund',[expected('vat_document_review'),expected()],dict(amount=6_000_000,returns=[1_000_000])),
        ('REFUND_BANK','Hoàn khoản chi qua ngân hàng','refund',[expected(),expected()],dict(amount=6_000_000,returns=[6_000_000],bank=True)),
        ('REVERSAL_JOURNAL','Đảo bút toán, không có khoản chi mới','refund',[expected('vat_document_review'),expected()],dict(amount=5_000_000,returns=[5_000_000],journal=True)),
        ('RECEIPT_UNLINKED','Thu tiền mặt chưa nối chứng từ gốc; không phải chi','receipt',[expected()],dict(amount=5_000_000)),
        ('REFUND_MULTI','Hai lần hoàn một phần, giữ bằng chứng khoản gốc','refund',[expected('vat_document_review'),expected(),expected()],dict(amount=10_000_000,returns=[3_000_000,2_000_000]))):
        add(identity,'refund_reversal',title,recipe,outcomes,**settings)
    for identity, title, amount, bank, missing, outcome in (
        ('RECUR_SMALL','Định kỳ đã duyệt, tiền mặt dưới ngưỡng',1_000_000,False,False,None),
        ('RECUR_BANK','Định kỳ đã duyệt, trả ngân hàng',10_000_000,True,False,None),
        ('RECUR_CASH','Định kỳ đã duyệt vẫn cần đối chiếu thanh toán',5_000_000,False,False,'vat_document_review'),
        ('RECUR_GAP','Hợp đồng định kỳ không thay thế hóa đơn còn thiếu',5_000_000,False,True,'information_request')):
        add(identity,'recurring',title,'recurring',[expected(outcome)]*3,amount=amount,bank=bank,missing=missing)
    add('RECUR_A5','recurring','Định kỳ có bằng chứng được loại khỏi tín hiệu A5','warm_recurring',
        [expected()]*22+[expected(a5_suppressed=True)])
    for identity, title, mode, amount, outcome in (
        ('LIMIT_VERIFIED','Hạn mức đã xác minh, hóa đơn vẫn thiếu','verified',2_000_001,'verified_internal_breach'),
        ('LIMIT_UNVERIFIED','Hạn mức chỉ có con số, chưa có xác minh','unverified',2_000_001,'information_request'),
        ('LIMIT_FUTURE','Xác minh hạn mức chỉ có sau thời điểm chi','future',2_000_001,'information_request'),
        ('LIMIT_EXPIRED','Hạn mức đã hết hiệu lực lúc chi','expired',2_000_001,'information_request'),
        ('LIMIT_FOREIGN','Ngoại tệ chưa xác minh số tiền VND','foreign',5_000_000,'information_request')):
        add(identity,'internal_limit',title,'limit',[expected(outcome)],mode=mode,amount=amount)
    return specifications


def build_control(spec):
    c = Case()
    config = deepcopy(DEFAULT_CONFIG)
    settings = spec['settings']
    returns = []
    def pay(amount, at=AT, *, invoice=True, bank=False, vendor=False, **fields):
        row = c.pay(at, amount, kind='vendor_payment' if vendor else 'rent' if bank else 'cash_expense',
            created_at=stamp(at-timedelta(minutes=30)), approved_at=stamp(at),
            invoice_id='I_CONTROL' if invoice else '', invoice_number='HD_CONTROL' if invoice else '',
            invoice_issued_at=stamp(at-timedelta(days=4)) if invoice else '', invoice_gross_vnd=amount if invoice else 0)
        if not bank:
            row.update(payment_channel='cash', credit_account='111')
        row.update(fields)
        return row
    def pattern(amount, kind, vendor=''):
        c.tables['recurring_payments'].append(dict(pattern_id='PAT_CONTROL',company_id='C001',vendor_id=vendor,employee_id='',
            txn_type=kind,contract_id='',invoice_number='',frequency='monthly',expected_amount_vnd=amount,tolerance_vnd=0,
            effective_from='2025-01-01',effective_to='2025-12-31',status='approved',evidence_on_file=1,
            evidence_id='SYNTHETIC_APPROVED_RECURRING',approver_id=c.director['employee_id'],
            approved_at='2025-01-01T09:00:00+07:00',observed_at='2025-01-01T10:00:00+07:00'))
    recipe = spec['recipe']
    if recipe == 'single':
        at = datetime.fromisoformat(settings.get('at',stamp(AT)))
        row = pay(settings['amount'],at,bank=settings.get('bank',False))
        missing = settings.get('missing')
        if missing in {'all','identity'}: row.update(invoice_id='',invoice_number='')
        if missing in {'all','date'}: row['invoice_issued_at']=''
        if missing in {'all','gross'}: row['invoice_gross_vnd']=0
        if missing == 'future': row['invoice_issued_at']=stamp(at+timedelta(hours=1))
    elif recipe == 'installments':
        for i, amount in enumerate(settings['amounts']):
            at = AT if settings.get('same_time') else AT+timedelta(days=2*i)
            row = pay(amount,at,vendor=True,bank=bool(settings.get('mixed') and i==0),invoice_gross_vnd=settings['gross'],
                      invoice_issued_at='' if settings.get('missing_date') else stamp(AT-timedelta(days=4)),contract_id='CONTRACT_CONTROL')
            c.tables['transaction_documents'].append(dict(record_id='DOC_'+row['transaction_id'],company_id='C001',
                vendor_id=row['vendor_id'],transaction_id=row['transaction_id'],document_type='invoice',invoice_number=row['invoice_number'],
                invoice_gross_vnd=settings['gross'],status='verified',evidence_id='SOURCE_'+row['transaction_id'],
                verifier_id=c.director['employee_id'],verified_at=stamp(AT-timedelta(days=3)),observed_at=stamp(AT-timedelta(days=2))))
        c.tables['supplier_payment_agreements'].append(dict(agreement_id='AGR_CONTROL',company_id='C001',vendor_id=c.vendor['vendor_id'],
            contract_id='CONTRACT_CONTROL',invoice_number='HD_CONTROL',total_vnd=settings['gross'],status='approved',evidence_on_file=1,
            evidence_id='SYNTHETIC_AGREEMENT',approver_id=c.director['employee_id'],approved_at=stamp(AT-timedelta(days=3)),observed_at=stamp(AT-timedelta(days=2))))
    elif recipe in {'refund','receipt'}:
        original = pay(settings['amount'],bank=settings.get('bank',False),invoice=not settings.get('bank')) if recipe=='refund' else None
        for i, amount in enumerate(settings.get('returns',[settings['amount']])):
            row = pay(amount,AT+timedelta(days=i+1),invoice=False)
            returns.append((row,original,'bank' if settings.get('bank') else 'journal' if settings.get('journal') else 'cash'))
    elif recipe == 'recurring':
        for month in (8,9,10):
            row = pay(settings['amount'],AT.replace(month=month),bank=settings['bank'],invoice=not settings['missing'])
            if row['invoice_id']:
                row.update(invoice_id=f'I_MONTH_{month}',invoice_number=f'HD_MONTH_{month}')
        pattern(settings['amount'],c.rows[-1]['txn_type'],c.rows[-1]['vendor_id'])
    elif recipe == 'warm_recurring':
        for i in range(22): pay(1_000_000,AT-timedelta(days=40-i),invoice=False)
        pay(3_000_000)
        pattern(3_000_000,'cash_expense')
    elif recipe == 'limit':
        mode = settings['mode']
        config['cash_limit_vnd_by_company']={'C001':2_000_000}
        record=dict(limit_vnd=2_000_000,source_ref='SYNTHETIC_APPROVED_CASH_LIMIT',verified_by='SYNTHETIC_CFO',
                    verified_at='2024-01-01T09:00:00+07:00',effective_from='2024-01-01T00:00:00+07:00',effective_to='')
        if mode=='future': record['verified_at']=stamp(AT+timedelta(days=1))
        if mode=='expired': record['effective_to']=stamp(AT)
        if mode!='unverified': config['cash_limit_evidence_by_company']={'C001':record}
        pay(settings['amount'],invoice=False,currency='USD' if mode=='foreign' else 'VND')
    else:
        raise ValueError('Unknown control recipe')
    c.tables['transactions']=c.rows
    enrich_accounting(c.tables,20261018)
    for row, original, channel in returns:
        # Source-only return entries: positive receipt amounts, no negative expense.
        row.update(debit_account='112' if channel=='bank' else '111',credit_account='642',
                   accounting_purpose='cash_refund',payment_channel=channel,recipient_account='',
                   original_transaction_id=original['transaction_id'] if original else '',
                   account_pair=('112' if channel=='bank' else '111')+'/642',journal_signature=('112' if channel=='bank' else '111')+'/642',
                   linked_document_id=original['journal_document_id'] if original else '')
        doc = next(d for d in c.tables['journal_documents'] if d['document_id']==row['journal_document_id'])
        doc['purpose']='cash_refund'
        for line in c.tables['journal_lines']:
            if line['document_id']==doc['document_id']:
                line['debit_vnd'],line['credit_vnd']=line['credit_vnd'],line['debit_vnd']
                if line['debit_vnd']: line['account_code']=row['debit_account']
        for edge in c.tables['account_flow_edges']:
            if edge['document_id']==doc['document_id']:
                edge.update(source_account='642',target_account=row['debit_account'],purpose='cash_refund')
        if original:
            c.tables['document_links'].append(dict(source_document_id=original['journal_document_id'],target_document_id=doc['document_id'],
                observed_at=row['posted_at'],link_type='cash_return_of'))
    # No truth, expected status, group or fixture recipe is handed to the engine.
    tables={name:rows for name,rows in c.tables.items() if name not in {'labels','splits','features'}}
    return tables,config


def check_books(tables):
    """Reconcile positive journals and explicit return links without editing CDM."""
    from collections import defaultdict
    tx={r['transaction_id']:r for r in tables['transactions']}
    docs={r['document_id']:r for r in tables['journal_documents']}
    companies={r['company_id']:r for r in tables['companies']}
    lines,edges=defaultdict(list),defaultdict(list)
    for line in tables['journal_lines']: lines[line['document_id']].append(line)
    for edge in tables['account_flow_edges']: edges[edge['document_id']].append(edge)
    for identity,doc in docs.items():
        ls,es=lines[identity],edges[identity]
        debit=sum(int(r['debit_vnd']) for r in ls);credit=sum(int(r['credit_vnd']) for r in ls)
        assert debit==credit==int(doc['amount_vnd'])>0
        for line in ls:
            assert (int(line['debit_vnd'])>0) != (int(line['credit_vnd'])>0)
            assert account_supported(line['account_code'],doc['accounting_framework'])
        assert sum(int(e['amount_vnd']) for e in es)==debit
        for account in {r['account_code'] for r in ls}:
            assert sum(int(e['amount_vnd']) for e in es if e['target_account']==account)==sum(int(r['debit_vnd']) for r in ls if r['account_code']==account)
            assert sum(int(e['amount_vnd']) for e in es if e['source_account']==account)==sum(int(r['credit_vnd']) for r in ls if r['account_code']==account)
        for edge in es:
            assert edge['company_id']==doc['company_id'] and edge['observed_at']==doc['posted_at']
            assert pair_supported(edge['target_account'],edge['source_account'],doc['purpose'],doc['accounting_framework']) or (
                doc['purpose']=='cash_refund' and edge['target_account'] in {'111','112'} and edge['source_account']=='642')
        if int(doc['is_scored_observation']):
            row=tx[doc['transaction_id']]
            assert row['journal_document_id']==identity and row['posted_at']==doc['posted_at'] and int(row['amount_vnd'])==debit
            assert row['accounting_framework']==companies[row['company_id']]['accounting_framework']
            if doc['purpose']=='cash_refund': assert row['debit_account'] in {'111','112'} and row['credit_account']=='642'
    refunds=defaultdict(int)
    for link in tables['document_links']:
        source,target=docs[link['source_document_id']],docs[link['target_document_id']]
        assert source['company_id']==target['company_id']
        assert max(source['posted_at'],target['posted_at'])<=link['observed_at']
        if link['link_type']=='cash_return_of':
            assert source['posted_at']<target['posted_at']
            refunds[source['document_id']]+=int(target['amount_vnd'])
            assert refunds[source['document_id']]<=int(source['amount_vnd'])
    for invoice in tables['invoices']:
        assert int(invoice['net_amount_vnd'])+int(invoice['vat_amount_vnd'])==int(invoice['gross_amount_vnd'])
    return dict(status='passed',transactions=len(tx),documents=len(docs),journal_lines=len(tables['journal_lines']),
                return_links=sum(r['link_type']=='cash_return_of' for r in tables['document_links']),
                scope='Positive balanced fixture journals; cash_refund is a local receipt template, not a new statutory account whitelist')
