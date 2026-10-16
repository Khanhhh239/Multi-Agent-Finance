"""Trusted row restrictions, compiled separately and ANDed with user filters.

Custom metrics must explicitly opt in only after every underlying read is
scoped. A subledger query that cannot guarantee this fails closed.
"""
from __future__ import annotations

SCOPE_COLUMNS = {'branch':'branch_code','salesperson':'employee_code','customer':'partner_code',
                 'vendor':'partner_code','department':'department_code','item':'item_code',
                 'product_line':'product_line','cost_category':'cost_category'}
SAFE_CUSTOM = {'dso','dpo','dio','cash_conversion_cycle','expense_spikes','mgmt_vs_tax_gap'}

def compile_scope(engine, metric, scope):
    from .engine import FilterError,ScopeNotSupported
    if scope is None:
        return '',[],{}
    if not isinstance(scope,dict):
        raise FilterError('Phạm vi phải là ánh xạ chiều tới danh sách mã.')
    if metric.kind=='custom' and metric.id not in SAFE_CUSTOM and scope:
        raise ScopeNotSupported(f"Chỉ số '{metric.label}' chưa hỗ trợ giới hạn phạm vi hàng.")
    conditions,args,canonical = [],[],{}
    for key,values in sorted(scope.items()):
        if key not in SCOPE_COLUMNS:
            raise FilterError(f'Chiều phạm vi không hỗ trợ: {key}.')
        if not isinstance(values,list) or any(not isinstance(v,str) for v in values):
            raise FilterError('Phạm vi phải chứa danh sách mã chính xác; không dùng tên gần đúng.')
        codes = []
        for value in values:
            matches = engine.resolve_entity(key,value)
            if matches != [value]:
                raise FilterError(f'Phạm vi yêu cầu mã chính xác: {value}.')
            codes.append(value)
        codes = sorted(set(codes))
        canonical[key] = codes
        if not codes:
            conditions.append('FALSE')
        else:
            conditions.append(SCOPE_COLUMNS[key]+' IN ('+','.join('?' for _ in codes)+')')
            args.extend(codes)
    return (' AND '+' AND '.join(conditions) if conditions else ''),args,canonical
