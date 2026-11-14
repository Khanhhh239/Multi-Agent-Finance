"""Explicit P1 source inputs and bounded export manifests; no risk calculation."""
from collections import Counter
from copy import deepcopy
import hashlib
import json

from finance_input.validation import issue,stamp
from .identity import normalize

VERSION='p1-inputs/1.1.0'
REF_FIELDS={'invoices':'invoice_refs','transactions':'transaction_refs','payment_allocations':'allocation_refs'}


def _bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def _time(row):return max(stamp(row['observed_at']),stamp(row['effective_at']))
def _ref(row):return dict(record_id=row['record_id'],revision=row['revision'])
def _identity(ref):return ref['record_id'],ref['revision']
def _latest(rows):
    result={}
    for row in rows:
        key=row['tenant_id'],row['company_id'],row['record_id']
        if key not in result or row['revision']>result[key]['revision']:result[key]=row
    return list(result.values())


def obligation_ids(invoices,ids):
    """Follow explicit corrections and the retained vendor/legal-number identity."""
    ids=set(ids)
    while True:
        keys={(r.get('vendor_ref',{}).get('record_id'),normalize(r['number'])) for r in invoices
              if r['record_id'] in ids and r['kind']=='invoice' and r.get('vendor_ref') and normalize(r['number'])}
        expanded=ids|{r['record_id'] for r in invoices if
            (r.get('adjusts_ref',{}).get('record_id') in ids) or
            (r['kind']=='invoice' and r.get('vendor_ref') and
             (r['vendor_ref']['record_id'],normalize(r['number'])) in keys)}
        expanded|={r['adjusts_ref']['record_id'] for r in invoices if r['record_id'] in expanded and r.get('adjusts_ref')}
        if expanded==ids:return ids
        ids=expanded


def manifest_records(bundle,claim):
    """Only explicit export scope; never infers completeness or missing rows."""
    tenant,cid=claim['tenant_id'],claim['company_id']
    known=stamp(claim['observed_at']);start=stamp(claim['covered_from']);end=stamp(claim['covered_through'])
    ids={r['record_id'] for r in claim['invoice_refs']}
    def visible(table):
        return [r for r in bundle.get(table,[]) if (r['tenant_id'],r['company_id'])==(tenant,cid) and stamp(r['observed_at'])<=known]
    invoices=[r for r in visible('invoices') if r['record_id'] in ids]
    allocations=[r for r in visible('payment_allocations') if r['invoice_ref']['record_id'] in ids
                 and stamp(r['effective_at'])<=end and
                 (claim['history_basis']=='since_inception' or stamp(r['effective_at'])>=start)]
    tx_ids={a['transaction_ref']['record_id'] for a in allocations}
    transactions=[r for r in visible('transactions') if r['record_id'] in tx_ids]
    return {table:sorted(rows,key=lambda r:(r['record_id'],r['revision'])) for table,rows in
            (('invoices',invoices),('transactions',transactions),('payment_allocations',allocations))}


def export_manifest(bundle,claim):
    """Exporter helper: computes refs/count/hash, not coverage_status or bounds."""
    rows=manifest_records(bundle,claim)
    result={REF_FIELDS[table]:[_ref(r) for r in records] for table,records in rows.items()}
    result.update(record_counts={t:len(r) for t,r in rows.items()},records_sha256=hashlib.sha256(_bytes(rows)).hexdigest())
    return result


def validate_p1_sources(bundle):
    """Called after schema, scope and ordinary reference checks succeeded."""
    errors=[];warnings=[]
    lookup={(r['tenant_id'],r['company_id'],t,r['record_id'],r['revision']):r
            for t in ('transactions','invoices','payment_allocations') for r in bundle.get(t,[])}
    for index,claim in enumerate(bundle.get('payment_history_coverage',[])):
        path=f'/payment_history_coverage/{index}'
        start,end,known=map(stamp,(claim['covered_from'],claim['covered_through'],claim['observed_at']))
        if start>end or end>known or stamp(claim['effective_at'])>end:
            errors.append(issue('P1_COVERAGE_TIME',path+'/covered_through',
                'Phạm vi lịch sử sai thứ tự hoặc kết thúc sau thời điểm nguồn được biết.',
                'Dùng covered_from <= covered_through <= observed_at và effective_at phù hợp; không khai báo phủ tương lai.'))
            continue
        ref_groups={'invoice_refs':claim['invoice_refs'],**{'manifest/'+f:claim['manifest'][f] for f in REF_FIELDS.values()}}
        for field,refs in ref_groups.items():
            if any(count>1 for count in Counter(_identity(r) for r in refs).values()):
                errors.append(issue('P1_DUPLICATE_MANIFEST_REF',path+'/'+field,'Manifest/scope có tham chiếu trùng.',
                    'Giữ một tham chiếu cho mỗi ID/revision; không bỏ phiên bản khác.'))
        for field,table in (('invoice_refs','invoices'),('manifest/invoice_refs','invoices'),
                            ('manifest/transaction_refs','transactions'),('manifest/allocation_refs','payment_allocations')):
            refs=claim['invoice_refs'] if field=='invoice_refs' else claim['manifest'][field.split('/')[1]]
            for pos,ref in enumerate(refs):
                row=lookup.get((claim['tenant_id'],claim['company_id'],table,*_identity(ref)))
                if row and stamp(row['observed_at'])>known:
                    errors.append(issue('P1_COVERAGE_REFERENCE_TIME',f'{path}/{field}/{pos}',
                        'Manifest tham chiếu nguồn chỉ được biết sau khai báo phạm vi.',
                        'Tạo revision phạm vi mới với observed_at thực sau khi nguồn được biết; không lùi thời gian.'))
        expected=export_manifest(bundle,claim)
        for field in REF_FIELDS.values():
            if sorted(map(_identity,claim['manifest'][field]))!=sorted(map(_identity,expected[field])):
                errors.append(issue('P1_MANIFEST_MEMBERSHIP',path+'/manifest/'+field,
                    'Danh sách manifest không khớp toàn bộ nguồn đã gửi thuộc phạm vi khai báo.',
                    'Xuất lại danh sách ID/revision và checksum từ cùng nguồn; không tự bỏ bản ghi hoặc dùng manifest cũ.'))
        for table,count in expected['record_counts'].items():
            if claim['manifest']['record_counts'][table]!=count:
                errors.append(issue('P1_MANIFEST_COUNT',path+'/manifest/record_counts/'+table,
                    'Số bản ghi khai báo không khớp nguồn trong phạm vi.', 'Xuất lại manifest từ đúng dữ liệu canonical và phạm vi.'))
        if claim['manifest']['records_sha256']!=expected['records_sha256']:
            errors.append(issue('P1_MANIFEST_CHECKSUM',path+'/manifest/records_sha256',
                'Dữ liệu đã đổi hoặc manifest không được tạo từ đúng nguồn canonical.',
                'Kiểm tra file/mapping và xuất lại manifest; không tái dùng kết quả kiểm tra cũ.'))
        declared_rows=manifest_records(bundle,claim)
        if claim['history_basis']=='since_inception' and any(stamp(a['effective_at'])<start for a in
                declared_rows['payment_allocations']+declared_rows['invoices']):
            errors.append(issue('P1_COVERAGE_RANGE',path+'/covered_from',
                'Có hóa đơn hoặc phân bổ cùng scope trước mốc bắt đầu dù nguồn khai báo từ đầu lịch sử.',
                'Đối chiếu và khai báo lại phạm vi thực; không loại dữ liệu trước mốc hoặc coi số đã trả là 0.'))
    for index,a in enumerate(bundle.get('payment_allocations',[])):
        prefix=(a['tenant_id'],a['company_id'])
        tx=lookup.get((*prefix,'transactions',*_identity(a['transaction_ref'])))
        inv=lookup.get((*prefix,'invoices',*_identity(a['invoice_ref'])))
        if tx and inv and tx.get('vendor_ref') and inv.get('vendor_ref') and tx['vendor_ref']['record_id']!=inv['vendor_ref']['record_id']:
            warnings.append(issue('P1_VENDOR_MISMATCH',f'/payment_allocations/{index}/invoice_ref',
                'NCC của giao dịch và hóa đơn chưa khớp; chưa đủ căn cứ đối chiếu P1.',
                'Đối chiếu nghĩa vụ, người nhận hoặc hồ sơ chi hộ; không tự đổi liên kết hay kết luận gian lận.'))
    return errors,warnings


def _gap(table,field,code,record=None):
    result=dict(table=table,field=field,code=code,
        action='Bổ sung nguồn hoặc khai báo phạm vi thực, xuất lại manifest và tạo snapshot mới; không tự suy kênh hoặc điền lịch sử thiếu bằng 0.')
    if record:result.update(record_id=record['record_id'],revision=record['revision'])
    return result


def transaction_inputs(bundle,tx):
    """P1 source gate at first availability; no amount totals or risk labels."""
    tenant,cid=tx['tenant_id'],tx['company_id'];event=stamp(tx['effective_at']);cutoff=_time(tx)
    def visible(table):
        return [r for r in bundle.get(table,[]) if (r['tenant_id'],r['company_id'])==(tenant,cid)
                and stamp(r['observed_at'])<=cutoff and stamp(r['effective_at'])<=event]
    gaps=[];allocs=_latest(visible('payment_allocations'))
    current=[a for a in allocs if a['transaction_ref']['record_id']==tx['record_id']]
    if not current:gaps.append(_gap('payment_allocations','transaction_ref','p1_current_allocation_missing',tx))
    inv_ids=obligation_ids(visible('invoices'),{a['invoice_ref']['record_id'] for a in current})
    invoice_rows=[r for r in visible('invoices') if r['record_id'] in inv_ids]
    related=[a for a in allocs if a['invoice_ref']['record_id'] in inv_ids]
    tx_ids={a['transaction_ref']['record_id'] for a in related}|{tx['record_id']}
    tx_rows=[r for r in visible('transactions') if r['record_id'] in tx_ids]
    # A known cash correction must not silently disappear because its allocation
    # was omitted. Include it as evidence and require the explicit link.
    corrections=[r for r in _latest(visible('transactions')) if r.get('adjusts_ref',{}).get('record_id') in tx_ids]
    for row in corrections:
        if not any(a['transaction_ref']==_ref(row) and a['invoice_ref']['record_id'] in inv_ids for a in allocs):
            gaps.append(_gap('payment_allocations','transaction_ref','p1_adjustment_allocation_missing',row))
    tx_rows=list({(r['record_id'],r['revision']):r for r in tx_rows+corrections}.values())
    by_inv={_identity(r):r for r in invoice_rows};by_tx={_identity(r):r for r in tx_rows}
    if tx.get('payment_channel') not in ('bank','cash'):
        gaps.append(_gap('transactions','payment_channel','p1_channel_missing_or_unsupported',tx))
    for row in tx_rows:
        if row.get('payment_channel') not in ('bank','cash'):
            gaps.append(_gap('transactions','payment_channel','p1_channel_missing_or_unsupported',row))
        if row['kind'] not in ('payment','adjustment','reversal'):
            gaps.append(_gap('transactions','kind','p1_transaction_kind_unsupported',row))
    for a in related:
        t=by_tx.get(_identity(a['transaction_ref']));inv=by_inv.get(_identity(a['invoice_ref']))
        if t is None:gaps.append(_gap('transactions','transaction_ref','referenced_revision_unavailable',a))
        if inv is None:gaps.append(_gap('invoices','invoice_ref','referenced_revision_unavailable',a))
        if a in current and a['transaction_ref']['revision']!=tx['revision']:
            gaps.append(_gap('payment_allocations','transaction_ref','p1_current_revision_mismatch',a))
        if t and inv and (not t.get('vendor_ref') or not inv.get('vendor_ref') or
                         t['vendor_ref']['record_id']!=inv['vendor_ref']['record_id']):
            gaps.append(_gap('payment_allocations','invoice_ref','p1_vendor_link_unresolved',a))
    vendors={_identity(r):r for r in visible('vendors')};used_vendors={}
    for row in invoice_rows+tx_rows:
        ref=row.get('vendor_ref')
        if ref and _identity(ref) in vendors:used_vendors[_identity(ref)]=vendors[_identity(ref)]
        else:gaps.append(_gap('vendors','vendor_ref','referenced_revision_unavailable',row))
    claims=_latest(visible('payment_history_coverage'));relevant_claims=[];selected=[]
    for identity in sorted(inv_ids):
        candidates=[c for c in claims if identity in {r['record_id'] for r in c['invoice_refs']}]
        relevant_claims.extend(candidates)
        if not candidates:
            gaps.append(_gap('payment_history_coverage','invoice_refs','p1_history_scope_missing'));continue
        newest=max(stamp(c['observed_at']) for c in candidates)
        top=[c for c in candidates if stamp(c['observed_at'])==newest]
        signatures={_bytes({k:c[k] for k in ('covered_from','covered_through','history_basis','coverage_status','manifest')}) for c in top}
        if len(signatures)>1:
            gaps.append(_gap('payment_history_coverage','manifest','p1_history_scope_conflict'));continue
        claim=sorted(top,key=lambda c:(c['record_id'],c['revision']))[0];selected.append(claim)
        expected=export_manifest(bundle,claim)
        if (claim['manifest']['record_counts']!=expected['record_counts'] or
            claim['manifest']['records_sha256']!=expected['records_sha256'] or
            any(sorted(map(_identity,claim['manifest'][f]))!=sorted(map(_identity,expected[f])) for f in REF_FIELDS.values())):
            gaps.append(_gap('payment_history_coverage','manifest','p1_history_manifest_mismatch',claim))
        if claim['coverage_status']!='complete' or claim['history_basis']!='since_inception':
            gaps.append(_gap('payment_history_coverage','coverage_status','p1_history_scope_partial_or_unknown',claim))
        if stamp(claim['covered_through'])<event:
            gaps.append(_gap('payment_history_coverage','covered_through','p1_history_scope_ends_before_transaction',claim))
        # Changes learned since the export invalidate its completeness for this
        # cutoff; future-effective rows do not affect a past transaction.
        relevant_rows=[r for r in invoice_rows if r['record_id']==identity]
        related_allocs=[a for a in related if a['invoice_ref']['record_id']==identity]
        relevant_rows+=related_allocs
        related_tx={a['transaction_ref']['record_id'] for a in related_allocs}
        relevant_rows+=[r for r in tx_rows if r['record_id'] in related_tx]
        if any(stamp(r['observed_at'])>stamp(claim['observed_at']) for r in relevant_rows):
            gaps.append(_gap('payment_history_coverage','manifest','p1_history_scope_stale',claim))
    # Empty history is only a potential known empty within an explicit, bound
    # source declaration. It is never proof of complete external books.
    payload=dict(p1_invoices=invoice_rows,
                 p1_allocations=[a for a in visible('payment_allocations') if a['invoice_ref']['record_id'] in inv_ids],
                 p1_transactions=tx_rows,p1_vendors=list(used_vendors.values()),
                 payment_history_coverage=list({(c['record_id'],c['revision']):c for c in relevant_claims}.values()))
    for rows in payload.values():rows.sort(key=lambda r:(r['record_id'],r['revision']))
    unique={_bytes(g):g for g in gaps}
    diagnostics=dict(version=VERSION,available=not unique,
        payment_channel=tx.get('payment_channel'),
        history_basis='source_declaration_bound_to_submitted_records_only_not_verified_external_books',
        selected_scope_refs=[_ref(c) for c in selected],
        gaps=[unique[k] for k in sorted(unique)])
    return deepcopy(payload),diagnostics
