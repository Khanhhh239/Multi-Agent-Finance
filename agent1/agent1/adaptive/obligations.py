"""T5 ledger: known schedules, bank settlements and remaining cash movements."""

from collections import Counter

import pandas as pd

from agent1.calendar_vn import next_business_day
from agent1.rules.obligations import CATEGORIES, extended_schedule


def validate_obligations(data):
    from .data import as_of, vnd
    from agent1.reconciliation.pipeline import NON_AR

    expenses = {r['expense_id']: r for r in data.get('outflows', [])}
    if len(expenses) != len(data.get('outflows', [])):
        raise ValueError('Mã lần đến hạn T5 bị trùng')
    for r in expenses.values():
        if r.get('status', 'open') not in {'open', 'cancelled'}:
            raise ValueError('Trạng thái T5 phải là open hoặc cancelled; đã trả tính từ phân bổ sao kê')
        if pd.isna(pd.Timestamp(r.get('known_at'))) or pd.isna(pd.Timestamp(r.get('date'))):
            raise ValueError('Thiếu ngày đến hạn hoặc ngày ghi nhận T5')
        if r.get('forecast_date') and r['forecast_date'] < r['date']:
            raise ValueError('Ngày dự kiến trả còn lại phải từ ngày đến hạn')
        if r['category'] in CATEGORIES:
            if not str(r.get('source', '')).strip() or r.get('verified') is not True:
                raise ValueError('Nghĩa vụ mở rộng cần source và verified=true từ hồ sơ đã xác nhận')
            if r.get('refund_approved_at') and r['category'] == 'vat_refund' and r['date'] < r['refund_approved_at']:
                raise ValueError('Ngày nhận hoàn trước quyết định')
            if r.get('business_day', 'none') not in {'none', 'following', 'preceding'}:
                raise ValueError('Quy ước ngày làm việc không hợp lệ')

    paid = Counter()
    used = Counter()
    for r in data.get('payments', []):
        used[r.get('bank_id', '')] += vnd(r['amount'])
    seen = set()
    snapshots = {}
    bank = {r['bank_id']: r for r in data.get('bank', [])}
    for payment in data.get('expense_payments', []):
        key = payment['settlement_id']
        if key in seen:
            raise ValueError('Mã thanh toán T5 bị trùng')
        seen.add(key)
        identifier = payment['expense_id']
        target = expenses.get(identifier)
        if target is None:
            raise ValueError('Thanh toán T5 tham chiếu lần đến hạn chưa có: ' + identifier)
        known = payment['known_at']
        if known < payment['payment_date']:
            raise ValueError('Ngày ghi nhận thanh toán T5 trước ngày chi/thu thực tế')
        snapshot = snapshots.setdefault(known, None)
        if snapshot is None:
            snapshot = as_of(data, known)
            snapshots[known] = snapshot
        original = next((r for r in snapshot.get('outflows', []) if r['expense_id'] == identifier and r['known_at'] <= known), None)
        if original is None:
            raise ValueError('Thanh toán T5 được ghi nhận trước nghĩa vụ')
        direction = 'in' if target['category'] == 'vat_refund' else 'out'
        if (original['category'] == 'vat_refund') != (direction == 'in'):
            raise ValueError('Không được đổi chiều nghĩa vụ đã có thanh toán')
        txn = bank.get(payment['bank_id'])
        observed = next((r for r in snapshot.get('bank', []) if r['bank_id'] == payment['bank_id'] and r['known_at'] <= known), None)
        for line in (txn, observed):
            if not line or line['direction'] != direction or line['date'] != payment['payment_date']:
                raise ValueError('Thanh toán T5 sai tham chiếu, ngày hoặc chiều sao kê')
            if direction == 'in' and (line.get('cash_flow_class') not in NON_AR or line.get('component', 'other') != 'other'):
                raise ValueError('Tiền hoàn phải được phân loại dòng phi công nợ trên sao kê')
            if direction == 'out' and target['category'] != 'variable_cost' and line.get('component') == 'variable_cost':
                raise ValueError('Khoản chi cố định T5 không được gán thành chi biến đổi trên sao kê')
        if direction == 'in' and (not original.get('refund_approved_at') or original['refund_approved_at'] > payment['payment_date']):
            raise ValueError('Nhận hoàn T5 trước quyết định')
        amount = vnd(payment['amount'])
        if amount <= 0:
            raise ValueError('Số tiền thanh toán T5 phải dương')
        paid[identifier] += amount
        used[payment['bank_id']] += amount
        if paid[identifier] > vnd(target['amount']):
            raise ValueError('Thanh toán T5 vượt nghĩa vụ: ' + identifier)
        if used[payment['bank_id']] > vnd(txn['amount']):
            raise ValueError('Phân bổ vượt số tiền sao kê: ' + payment['bank_id'])
        observed_paid = sum(vnd(r['amount']) for r in snapshot.get('expense_payments', [])
                            if r['expense_id'] == identifier and r['known_at'] <= known)
        observed_used = sum(vnd(r['amount']) for kind in ('payments', 'expense_payments')
                            for r in snapshot.get(kind, [])
                            if r.get('bank_id') == payment['bank_id'] and r['known_at'] <= known)
        if observed_paid > vnd(original['amount']) or observed_used > vnd(observed['amount']):
            raise ValueError('Phân bổ T5 vượt số tiền được biết tại ngày ghi nhận')

    for r in expenses.values():
        target = r.get('replaces_expense_id')
        if not target:
            continue
        if target not in expenses or target == r['expense_id']:
            raise ValueError('Mã lịch T5 được thay thế không hợp lệ')
        prior = as_of(data, r['known_at'])
        if not any(p['expense_id'] == target and p['known_at'] <= r['known_at'] for p in prior.get('outflows', [])):
            raise ValueError('Mã lịch T5 được thay thế chưa được biết tại ngày ghi nhận')
        if (expenses[target]['category'] == 'vat_refund') != (r['category'] == 'vat_refund'):
            raise ValueError('Không được thay lịch chi bằng khoản thu hoặc ngược lại')
        if paid[target]:
            raise ValueError('Lịch T5 đã thanh toán phải sửa theo cùng mã, không tách sang mã thay thế')
        seen = {r['expense_id']}
        while target:
            if target in seen:
                raise ValueError('Vòng lặp thay thế lịch T5')
            seen.add(target)
            target = expenses[target].get('replaces_expense_id')
            if target and target not in expenses:
                raise ValueError('Mã lịch T5 được thay thế không tồn tại')


def cash_schedule(data, cutoff, horizon=13, multiplier=1.0):
    """Bank cash is already in the opening balance; project only the remainder.

    Overdue outgoing obligations move to the next business day. Overdue refunds
    require a newly declared forecast_date rather than promising immediate cash.
    """
    from .data import as_of, vnd

    clock = pd.Timestamp(cutoff).normalize()
    known = str(clock.date())
    data = as_of(data, cutoff)
    expenses = [r for r in data.get('outflows', []) if r['known_at'] <= known]
    replaced = {r['replaces_expense_id'] for r in expenses if r.get('replaces_expense_id')}
    paid = Counter()
    payments = []
    for r in data.get('expense_payments', []):
        if r['known_at'] <= known and r['payment_date'] <= known:
            paid[r['expense_id']] += vnd(r['amount'])
            payments.append(dict(r))
    ledger, outgoing, incoming = [], [], []
    for index, r in enumerate(expenses):
        # Legacy offline forecast callers allowed unnamed rows. Connected
        # imports still require a stable expense_id before any bank allocation.
        identifier = str(r.get('expense_id') or f'ROW-{index + 1}')
        amount = vnd(r['amount'])
        settled = paid[identifier]
        remaining = amount - settled
        if remaining < 0:
            raise ValueError('Thanh toán T5 vượt nghĩa vụ: ' + identifier)
        due = pd.Timestamp(r['date'])
        direction = 'inflow' if r['category'] == 'vat_refund' else 'outflow'
        row = dict(expense_id=identifier, due_date=r['date'], known_at=r['known_at'],
                   category=r['category'], direction=direction, obligation_amount=amount,
                   settled_amount=settled, remaining_amount=remaining, source=r.get('source', ''),
                   status='partial' if settled else 'open', overdue=bool(due <= clock))
        if identifier in replaced:
            row['status'] = 'replaced'
        elif r.get('status') == 'cancelled':
            row['status'] = 'cancelled'
        elif not remaining:
            row['status'] = 'paid'
        else:
            if r['category'] in CATEGORIES:
                frame = extended_schedule([dict(r, obligation_id=identifier, due_date=r['date'])],
                                          asof=clock, start=due - pd.Timedelta(days=31),
                                          end=due + pd.Timedelta(days=31), strict=True)
                if frame.empty:
                    row['status'] = 'awaiting_approval'
                    ledger.append(row)
                    continue
                due = frame.iloc[0].date
                row['overdue'] = bool(due <= clock)
                row['known_at'] = str(frame.iloc[0].known_at.date())
            projected = pd.Timestamp(r.get('forecast_date') or due)
            if projected <= clock:
                if direction == 'inflow':
                    row['status'] = 'awaiting_refund_date'
                    ledger.append(row)
                    continue
                projected = next_business_day(clock, include_self=False)
                row['status'] = 'overdue'
            days = (projected - clock).days
            if 1 <= days <= horizon * 7:
                movement = dict(row, date=str(projected.date()), week=(days - 1) // 7 + 1,
                                original_amount=remaining,
                                amount=float(remaining * (multiplier if direction == 'outflow' else 1.0)))
                (incoming if direction == 'inflow' else outgoing).append(movement)
                row.update(forecast_date=movement['date'], week=movement['week'])
        ledger.append(row)
    return dict(protocol='t5-ledger-v1', obligations=ledger, payments=payments,
                outflows=outgoing, inflows=incoming,
                overdue_policy='next_business_day_outgoing;explicit_date_for_overdue_refund')
