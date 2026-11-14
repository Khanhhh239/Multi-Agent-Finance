"""Signed, allocation-based P1 evaluation over already scoped causal sources.

Row contributions and simultaneous-group checks are deliberately separate.
No fitting, global history mutation, queue events or inferred opening balances.
"""
from collections import defaultdict

from .identity import normalize
from .import_files import canonical, digest
from .p1_inputs import _latest, _identity, _ref
from .rules import WEIGHTS
from .snapshot_features import available, utc

VERSION='p1-evaluation/1.0.0'
TOLERANCE_VND=1  # Retained rules.py and BatchControls comparison: total > gross + 1.


def prepare(sources,meta):
    """Validate source bindings and partition raw rows, without a P1 decision.

    Local input validation may check totals/sign consistency. Raw allocation
    and invoice rows are preserved for the encrypted numerical evaluator.
    """
    invoices=sources['p1_invoices'];transactions=sources['p1_transactions']
    allocations=sources['p1_allocations'];latest_allocs=_latest(allocations)
    by_invoice={_identity(r):r for r in invoices};by_tx={_identity(r):r for r in transactions}
    by_alloc={_identity(r):r for r in allocations}
    latest_invoice={r['record_id']:r for r in _latest(invoices)}
    latest_tx={r['record_id']:r for r in _latest(transactions)}
    latest_allocation={r['record_id']:r for r in latest_allocs}
    details=dict(version=VERSION,tolerance_vnd=TOLERANCE_VND,invoice_checks=[],simultaneous_checks=[],
        history_basis='source_declared_complete_scope_not_independent_verification_of_external_books',
        row_policy='strict_prior_plus_current; previous_payment_required; simultaneous_checks_do_not_contribute_to_row')

    def missing(code,message):return dict(error=(code,message),details=details)

    def invoice_root(row):
        visited=set()
        while row['kind']!='invoice':
            identity=_identity(row)
            if identity in visited:return None
            visited.add(identity);ref=row.get('adjusts_ref')
            parent=by_invoice.get(_identity(ref)) if ref else None
            if (not parent or available(parent)>available(row) or
                utc(parent['effective_at'])>utc(row['effective_at']) or
                parent.get('vendor_ref',{}).get('record_id')!=row.get('vendor_ref',{}).get('record_id')):
                return None
            row=parent
        number=normalize(row['number']);vendor=row.get('vendor_ref')
        return (vendor['record_id'],number) if vendor and number else None

    invoice_keys={identity:invoice_root(row) for identity,row in latest_invoice.items()}
    if not invoice_keys or any(k is None for k in invoice_keys.values()):
        return missing('p1_invoice_identity_or_adjustment_unresolved','Chưa xác định được nghĩa vụ hóa đơn hoặc chuỗi điều chỉnh hóa đơn; cần đối chiếu số hóa đơn, NCC và bản gốc.')
    bases=defaultdict(list);corrections=defaultdict(list)
    for identity,row in latest_invoice.items():
        (bases if row['kind']=='invoice' else corrections)[invoice_keys[identity]].append(row)
    caps={}
    for key,rows in bases.items():
        values={r['amount_vnd'] for r in rows}
        if len(values)!=1 or next(iter(values))<=0:
            return missing('p1_invoice_value_conflict','Các mã cùng nghĩa vụ có giá trị hóa đơn mâu thuẫn hoặc không dương; không tự chọn trần.')
        caps[key]=next(iter(values))+sum(r['amount_vnd'] for r in corrections[key])
        if caps[key]<=0:
            return missing('p1_invoice_cap_nonpositive','Giá trị nghĩa vụ sau điều chỉnh không dương; cần đối chiếu chứng từ trước khi áp dụng P1.')
    cutoff,event=utc(meta['as_of']),utc(meta['event_at'])
    groups=defaultdict(lambda:dict(prior=[],current=[],simultaneous=[]))
    allocated=defaultdict(int);correction_nets=defaultdict(int)
    for allocation in latest_allocs:
        tx=by_tx.get(_identity(allocation['transaction_ref']))
        inv=by_invoice.get(_identity(allocation['invoice_ref']))
        if not tx or not inv or latest_tx[tx['record_id']]['revision']!=tx['revision']:
            return missing('p1_allocation_revision_unresolved','Phân bổ chưa khớp phiên bản giao dịch/hóa đơn nhìn thấy; cần bổ sung hoặc sửa liên kết, không cộng cả hai revision.')
        key=invoice_keys[inv['record_id']]
        if key not in caps or invoice_root(inv)!=key:
            return missing('p1_invoice_revision_identity_conflict','Phiên bản hóa đơn làm thay đổi định danh nghĩa vụ; cần đối chiếu liên kết trước khi tính tổng.')
        amount=allocation['amount_vnd'];cash=tx['amount_vnd']
        if ((amount<0 and cash>=0) or (amount>0 and cash<=0) or
            (amount<0 and (allocation['kind'] not in ('adjustment','reversal') or tx['kind'] not in ('adjustment','reversal')))):
            return missing('p1_allocation_sign_conflict','Dấu tiền phân bổ không khớp khoản thanh toán/điều chỉnh; cần đối chiếu chứng từ, không lấy trị tuyệt đối.')
        allocated[_identity(tx)]+=amount
        root=allocation;visited=set()
        while root['kind']!='allocation':
            identity=_identity(root)
            if identity in visited:return missing('p1_adjustment_cycle','Chuỗi điều chỉnh phân bổ tạo vòng lặp.')
            visited.add(identity);ref=root.get('adjusts_ref');parent=by_alloc.get(_identity(ref)) if ref else None
            child_tx=by_tx.get(_identity(root['transaction_ref']))
            if (not parent or not child_tx or child_tx.get('adjusts_ref')!=parent['transaction_ref'] or
                latest_allocation[parent['record_id']]['revision']!=parent['revision'] or
                available(parent)>available(root) or utc(parent['effective_at'])>utc(root['effective_at']) or
                invoice_keys.get(parent['invoice_ref']['record_id'])!=key):
                return missing('p1_adjustment_link_unresolved','Điều chỉnh chưa gắn đúng phân bổ và giao dịch gốc trong cùng nghĩa vụ/thời gian; cần bổ sung căn cứ.')
            parent_tx=by_tx.get(_identity(parent['transaction_ref']))
            if not parent_tx or available(parent_tx)>available(child_tx) or utc(parent_tx['effective_at'])>utc(child_tx['effective_at']):
                return missing('p1_adjustment_source_unavailable','Nguồn thanh toán gốc chưa khả dụng tại thời điểm điều chỉnh.')
            root=parent
        if tx['kind'] in ('adjustment','reversal') and allocation['kind']=='allocation':
            return missing('p1_adjustment_allocation_unbound','Giao dịch điều chỉnh cần phân bổ điều chỉnh có liên kết gốc; không tự coi là khoản trả mới.')
        correction_nets[(key,root['record_id'])]+=amount
        if tx['record_id']==meta['record_id']:
            partition='current'
        elif (available(tx)<cutoff and available(allocation)<cutoff and
              utc(tx['effective_at'])<event and utc(allocation['effective_at'])<event):
            partition='prior'
        else:partition='simultaneous'
        groups[key][partition].append(allocation)
    for identity,total in allocated.items():
        if abs(total)>abs(by_tx[identity]['amount_vnd']):
            return missing('p1_allocated_exceeds_payment','Tổng phân bổ thuộc phạm vi đang xét vượt tiền giao dịch; cần sửa liên kết/số tiền, không tự cắt giảm.')
    if any(net<0 for net in correction_nets.values()):
        return missing('p1_adjustment_exceeds_original','Tổng giảm vượt khoản phân bổ gốc; cần đối chiếu chuỗi điều chỉnh, không tự đặt số dư về 0.')
    return dict(groups=groups,bases=bases,corrections=corrections,caps=caps,
                by_tx=by_tx,latest_invoice=latest_invoice,invoice_keys=invoice_keys,details=details)


def evaluate(sources,meta):
    bound=prepare(sources,meta)
    if 'error' in bound:return bound
    groups,bases,corrections,caps,by_tx,latest_invoice,invoice_keys,details=(bound[k] for k in
        ('groups','bases','corrections','caps','by_tx','latest_invoice','invoice_keys','details'))
    def missing(code,message):return dict(error=(code,message),details=details)
    matched=False
    refs=lambda rows:sorted((_ref(r) for r in rows),key=lambda r:(r['record_id'],r['revision']))
    txrefs=lambda rows:sorted({(_identity(r['transaction_ref'])) for r in rows})
    for key,parts in sorted(groups.items()):
        if not parts['current']:continue
        prior,current,simultaneous=(parts[k] for k in ('prior','current','simultaneous'))
        prior_net=sum(r['amount_vnd'] for r in prior);current_net=sum(r['amount_vnd'] for r in current)
        simultaneous_net=sum(r['amount_vnd'] for r in simultaneous)
        previous_payment=any(by_tx[_identity(a['transaction_ref'])]['kind']=='payment' and a['amount_vnd']>0 for a in prior)
        row_total=prior_net+current_net;cap=caps[key]
        hit=previous_payment and current_net>0 and row_total>cap+TOLERANCE_VND
        matched|=hit
        details['invoice_checks'].append(dict(vendor_id=key[0],normalized_invoice_number=key[1],
            invoice_refs=refs([r for r in latest_invoice.values() if invoice_keys[r['record_id']]==key]),
            invoice_gross_vnd=cap,prior_paid_vnd=prior_net,current_allocated_vnd=current_net,
            cumulative_paid_vnd=row_total,excess_vnd=max(0,row_total-cap),previous_payment=previous_payment,
            matched=hit,prior_allocation_refs=refs(prior),current_allocation_refs=refs(current),
            simultaneous_allocation_refs=refs(simultaneous),related_transaction_refs=[dict(record_id=i,revision=v) for i,v in txrefs(prior)]))
        members=current+simultaneous
        if len(txrefs(members))<2:continue
        total=row_total+simultaneous_net;group_hit=total>cap+TOLERANCE_VND
        identity=[meta['tenant_id'],meta['company_id'],key,meta['event_at'],meta['as_of'],refs(members)]
        details['simultaneous_checks'].append(dict(group_id='P1G_'+digest(canonical(identity))[:24],
            tenant_id=meta['tenant_id'],company_id=meta['company_id'],rule_id='P1',event_at=meta['event_at'],as_of=meta['as_of'],
            vendor_id=key[0],normalized_invoice_number=key[1],matched=group_hit,
            points=WEIGHTS['P1'] if group_hit else 0,hard_trigger=int(group_hit),
            score_role='group_only_not_row_contribution',prior_paid_vnd=prior_net,
            group_allocated_vnd=current_net+simultaneous_net,cumulative_paid_vnd=total,invoice_gross_vnd=cap,
            excess_vnd=max(0,total-cap),allocation_refs=refs(members),prior_allocation_refs=refs(prior),
            transaction_refs=[dict(record_id=i,revision=v) for i,v in txrefs(members)]))
    if not details['invoice_checks']:
        return missing('p1_current_allocation_unresolved','Không có phân bổ hiện hành khớp giao dịch để đánh giá P1.')
    return dict(matched=matched,score=WEIGHTS['P1'] if matched else 0,
        intrinsic_points=WEIGHTS['P1'] if matched else 0,details=details)
