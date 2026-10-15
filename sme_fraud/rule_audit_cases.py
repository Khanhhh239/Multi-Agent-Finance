"""Independent business examples through raw records and the real causal engine.

Expected outcomes are declared before scoring. Known deviations are returned as
audit findings, not hidden by changing detector thresholds or synthetic truth.
"""
from datetime import datetime, timedelta

from .accounting import enrich_accounting
from .features import build_features
from .generate import Generator, TZ, stamp
from .rules import score_rules


class Case:
    def __init__(self):
        self.g = Generator(0, 0, 20261013, 1)
        self.tables = self.g.tables
        self.rows = []
        self.vendor = self.tables['vendors'][12]
        self.maker = self.tables['employees'][2]
        self.director = self.tables['employees'][0]
        self.worker = self.tables['employees'][10]
        self.at = datetime(2025, 8, 12, 11, tzinfo=TZ)

    def pay(self, at=None, amount=9_000_000, kind='vendor_payment', vendor=None, **values):
        at = at or self.at
        period = 'train' if at.year == 2024 else 'validation' if at.month <= 6 else 'test'
        row = self.g.transaction('C001', period, at, kind, vendor or self.vendor,
            self.worker, amount, self.maker['employee_id'], self.director['employee_id'], 1)
        row.update(transaction_id=f'AUDIT_{len(self.rows):04}', support_doc_count=2,
                   goods_receipt_verified=1)
        row.update(values)
        self.rows.append(row)
        return row

    def sequence(self, amounts, *, days=1, start=None, vendors=None, **values):
        start = start or self.at
        for i, amount in enumerate(amounts):
            row = self.pay(start + timedelta(days=days*i), amount,
                           vendor=vendors[i] if vendors else None, **values)
        return row

    def new_vendor(self):
        self.vendor = self.g.vendor('C001', self.at-timedelta(days=10),
                                    registered=self.at-timedelta(days=30))
        return self.vendor

    def shared_vendors(self, field='phone'):
        vendors = self.tables['vendors'][12:15]
        for v in vendors:
            v[field] = vendors[0][field]
        return vendors

    def attendance(self, *, alternative=0, leave=0):
        self.at = self.at.replace(day=28)
        for row in self.tables['attendance']:
            if row['employee_id'] == self.worker['employee_id'] and row['payroll_period'] == '2025-08':
                row.update(days_worked_observed=0, alternative_work_evidence=alternative,
                           approved_leave_days=leave,
                           leave_type='approved_paid_leave' if leave else '')
        self.worker['contract_on_file'] = 1
        payment = self.pay(kind='payroll')
        if leave:
            self.tables['payroll_entitlements'].append(dict(entitlement_id='AUDIT_PAID_LEAVE',
                company_id='C001', employee_id=self.worker['employee_id'], payroll_period='2025-08',
                leave_type='paid_leave', status='approved', required_work_days=22,
                approved_paid_leave_days=leave, entitled_amount_vnd=payment['amount_vnd'],
                evidence_on_file=1, evidence_id='HR_APPROVED_PAYROLL_202508',
                approver_id=self.director['employee_id'],
                approved_at=stamp(self.at-timedelta(days=4)), observed_at=stamp(self.at-timedelta(days=3))))
        return payment

    def change(self, verified=False, scheduled=False):
        effective = self.at-timedelta(days=5)
        self.tables['bank_account_changes'].append(dict(change_id='AUDIT_CHANGE',
            company_id='C001', vendor_id=self.vendor['vendor_id'],
            old_account=self.vendor['bank_account'], new_account='AUDIT_NEW_BANK',
            observed_at=stamp(effective-timedelta(days=4) if scheduled else effective),
            effective_at=stamp(effective), callback_verified=int(verified),
            verified_at=stamp(effective+timedelta(hours=1)) if verified else '',
            approver_id=self.director['employee_id'] if verified else ''))
        if scheduled:
            self.pay(effective-timedelta(days=2), 1_000_000, kind='cash_expense')
        return self.pay(amount=50_000_000, recipient_account='AUDIT_NEW_BANK')

    def score(self):
        self.tables['transactions'] = self.rows
        # The financial templates see ordinary source evidence, never labels.
        enrich_accounting(self.tables, 20261013)
        self.features = build_features(self.tables)
        return score_rules(self.tables, features=self.features, config=getattr(self, 'config', {}))


def run_cases():
    results = []

    def run(rule, code, description, expected, prepare, scope='business_expectation'):
        case = Case()
        target = prepare(case)
        tid = target['transaction_id']
        scored = case.score()
        hits = [r for r in scored['hits'] if r['transaction_id'] == tid and r['rule_id'] == rule]
        points = sum(r['points'] for r in hits)
        actual = points > 0
        feature = next(f for f in case.features if f['transaction_id'] == tid)
        evidence_fields = ('bank_changed_recently', 'bank_change_verified', 'attendance_known',
                           'attendance_days', 'alternative_work_evidence', 'self_approval_permitted')
        results.append(dict(rule_id=rule, case_id=code, description=description,
            expected_active=expected, actual_active=actual, passed=actual == expected,
            observed_points=points, scope=scope, target_transaction_id=tid,
            transactions=case.rows, observed_hits=hits,
            source_records=dict(vendor=case.vendor, maker=case.maker, worker=case.worker,
                bank_changes=case.tables['bank_account_changes'],
                payroll_entitlements=case.tables['payroll_entitlements'],
                attendance=[r for r in case.tables['attendance']
                            if r['employee_id'] == target['employee_id'] and r['payroll_period'] == target['payroll_period']],
                vendor_status=[r for r in case.tables['vendor_status_history'] if r['vendor_id'] == target['vendor_id']]),
            causal_observables={key: feature[key] for key in evidence_fields}))

    run('A1', 'A1_two_payments', 'Hai khoản 9 triệu trong 3 ngày, hạn mức 20 triệu', True,
        lambda c: c.sequence([9_000_000]*2))
    run('A1', 'A1_installments', 'Hai đợt có hồ sơ, cùng hóa đơn 18 triệu, tổng chưa vượt', False,
        lambda c: c.sequence([9_000_000]*2, invoice_number='ONE_INV', invoice_gross_vnd=18_000_000))
    run('A2', 'A2_three_payments', 'Ba khoản 9 triệu cùng người lập/người nhận trong 30 ngày', True,
        lambda c: c.sequence([9_000_000]*3, days=7))
    run('A2', 'A2_installments', 'Ba đợt có hồ sơ cùng hóa đơn 27 triệu trong 3 ngày', False,
        lambda c: c.sequence([9_000_000]*3, invoice_number='ONE_INV', invoice_gross_vnd=27_000_000))
    run('A2', 'A2_long_installments', 'Ba đợt hợp lệ cùng hóa đơn 27 triệu, cách nhau 7 ngày', False,
        lambda c: c.sequence([9_000_000]*3, days=7, invoice_number='ONE_INV', invoice_gross_vnd=27_000_000))
    run('A3', 'A3_network', 'Ba NCC chung SĐT, ba khoản 9 triệu', True,
        lambda c: c.sequence([9_000_000]*3, vendors=c.shared_vendors()))
    run('A3', 'A3_address_only', 'Ba NCC chỉ chung địa chỉ văn phòng, TK/SĐT khác nhau', False,
        lambda c: c.sequence([9_000_000]*3, vendors=c.shared_vendors('address')),
        'documented_adaptation')
    run('A3', 'A3_short_branch', 'Hai NCC chung SĐT, hai khoản 9 triệu/3 ngày theo nhánh A1', True,
        lambda c: c.sequence([9_000_000]*2, vendors=c.shared_vendors()[:2]), 'literal_spec')
    run('A4', 'A4_three_near', 'Ba khoản chi 17 triệu cận hạn mức 20 triệu', True,
        lambda c: c.sequence([17_000_000]*3, kind='cash_expense'))
    run('A4', 'A4_two_near', 'Chỉ hai khoản cận hạn mức', False,
        lambda c: c.sequence([17_000_000]*2, kind='cash_expense'))
    run('A4', 'A4_month_boundary', 'Ba khoản qua hai tháng lịch; không tháng nào đủ ba', False,
        lambda c: c.sequence([17_000_000]*3, kind='cash_expense',
                             start=datetime(2025, 1, 31, 11, tzinfo=TZ)), 'literal_spec')

    def rounded(c, base=1_000_000, amount=2_000_000):
        c.sequence([base + (i%5-2)*10_000 for i in range(20)], kind='cash_expense',
                   start=c.at-timedelta(days=25))
        return c.pay(amount=amount, kind='cash_expense')

    run('A5', 'A5_high_tail', 'Khoản tròn cao hơn baseline biến động trên 2 sigma', True, rounded)
    run('A5', 'A5_fixed_rent', 'Tiền thuê cố định 20 triệu, baseline không có biến động', False,
        lambda c: c.sequence([20_000_000]*21, kind='rent'))
    run('A5', 'A5_low_tail', 'Khoản tròn thấp hơn baseline trên 2 sigma theo độ lệch tuyệt đối', True,
        lambda c: rounded(c, 10_000_000, 2_000_000), 'literal_spec')
    run('A6', 'A6_over_round', 'Thanh toán 2.001.000, hóa đơn 1.990.007', True,
        lambda c: c.pay(amount=2_001_000, invoice_gross_vnd=1_990_007))
    run('A6', 'A6_partial', 'Trả trước 1 triệu trên hóa đơn lẻ 1.990.007 có hồ sơ', False,
        lambda c: c.pay(amount=1_000_000, invoice_gross_vnd=1_990_007))

    def overlap(c, field, kind='vendor_payment', disclosed=False):
        c.vendor[field] = c.worker[field]
        if disclosed:
            c.vendor['related_party_disclosed_at'] = '2023-01-01T00:00:00+07:00'
        return c.pay(kind=kind)

    run('B1', 'B1_employee_bank', 'TK nhận tiền NCC trùng TK nhân viên', True,
        lambda c: overlap(c, 'bank_account'))
    run('B1', 'B1_unrelated', 'NCC độc lập, không chung TK/định danh nhân viên', False,
        lambda c: c.pay())
    run('B1', 'B1_rent', 'Chi thuê NCC có TK trùng nhân viên, kiểm tra master theo mô tả', True,
        lambda c: overlap(c, 'bank_account', 'rent'), 'literal_spec')
    run('B2', 'B2_phone', 'SĐT NCC trùng SĐT nhân viên chưa công bố', True,
        lambda c: overlap(c, 'phone'))
    run('B2', 'B2_unrelated', 'NCC không có đường liên kết với nhân viên', False,
        lambda c: c.pay())
    run('B2', 'B2_disclosed', 'Quan hệ SĐT đã công bố trước giao dịch', False,
        lambda c: overlap(c, 'phone', disclosed=True))

    def shell(c, valid=False, previous=False):
        c.new_vendor()
        if previous:
            c.pay(c.at-timedelta(days=3), 1_000_000, kind='stock_purchase')
        return c.pay(amount=50_000_000, goods_receipt_verified=int(valid),
                     support_doc_count=2 if valid else 0)

    run('B3', 'B3_new_shell', 'NCC thành lập 30 ngày, khoản lớn đầu tiên thiếu giao nhận', True, shell)
    run('B3', 'B3_new_valid', 'NCC mới có xác nhận giao nhận và hồ sơ', False,
        lambda c: shell(c, valid=True))
    run('B3', 'B3_prior_purchase', 'NCC mới đã có giao dịch mua hàng trước khoản chi lớn', False,
        lambda c: shell(c, previous=True), 'literal_spec')

    def risky(c, historical=False, late=False):
        effective = c.at-timedelta(days=10)
        c.g.status(c.vendor, 'ceased', effective,
                   c.at+timedelta(days=2) if late else effective)
        return c.pay(invoice_issued_at=stamp(effective+timedelta(days=-5 if historical else 2)))

    run('B4', 'B4_risky_issue', 'Trạng thái rủi ro có hiệu lực và đã biết trước phát hành', True, risky)
    run('B4', 'B4_historical', 'Hóa đơn phát hành trước ngừng hoạt động, đã giao nhận', False,
        lambda c: risky(c, historical=True))
    run('B4', 'B4_late_observed', 'Thông tin rủi ro chỉ công bố sau thanh toán', False,
        lambda c: risky(c, late=True), 'causal_temporal')

    for rule in ('B5', 'E4'):
        run(rule, f'{rule}_shared', 'Hai mã NCC chung SĐT trong master', True,
            lambda c: c.pay(vendor=c.shared_vendors()[0]))
        run(rule, f'{rule}_unique', 'NCC có TK/SĐT/địa chỉ riêng', False, lambda c: c.pay())

    def dormant(c, amount):
        c.sequence([1_000_000+(i%5)*10_000 for i in range(20)],
                   start=datetime(2024, 1, 10, 11, tzinfo=TZ))
        return c.pay(amount=amount)

    run('B6', 'B6_dormant_high', 'Ngừng chi trên 180 ngày rồi nhận khoản vượt P90 của 20 khoản trước', True,
        lambda c: dormant(c, 5_000_000))
    run('B6', 'B6_dormant_low', 'Ngừng chi lâu nhưng khoản mới thấp hơn P90', False,
        lambda c: dormant(c, 900_000))
    run('B7', 'B7_unverified', 'Đổi TK 5 ngày trước khoản lớn, chưa callback', True, lambda c: c.change())
    run('B7', 'B7_verified', 'Đổi TK đã callback và duyệt độc lập trước thanh toán', False,
        lambda c: c.change(verified=True))
    run('B7', 'B7_scheduled_change', 'Đổi TK quan sát trước hiệu lực; có giao dịch ở giữa hai mốc', True,
        lambda c: c.change(scheduled=True), 'causal_temporal')
    run('C1', 'C1_late', 'Lập và duyệt lúc 23 giờ', True,
        lambda c: c.pay(at=c.at.replace(hour=23)))
    run('C1', 'C1_saturday', 'Thứ Bảy trong giờ tại công ty cho phép vận hành', False,
        lambda c: c.pay(at=datetime(2025, 8, 16, 11, tzinfo=TZ)), 'documented_adaptation')
    run('C2', 'C2_illegal_self', 'Kế toán tự duyệt 5 triệu, quyền tự duyệt 2 triệu', True,
        lambda c: c.pay(amount=5_000_000, approver_id=c.maker['employee_id']))
    run('C2', 'C2_legal_self', 'Kế toán tự duyệt 1 triệu trong quyền 2 triệu', False,
        lambda c: c.pay(amount=1_000_000, approver_id=c.maker['employee_id']))
    run('C3', 'C3_fast_large', 'Duyệt 100 triệu trong 20 giây', True,
        lambda c: c.pay(amount=100_000_000, created_at=stamp(c.at-timedelta(seconds=20))))
    run('C3', 'C3_normal_delay', 'Duyệt 100 triệu sau một giờ', False,
        lambda c: c.pay(amount=100_000_000))
    run('E1', 'E1_no_attendance', 'Có bảng công kỳ lương, 0 ngày và thiếu bằng chứng thay thế', True,
        lambda c: c.attendance())
    run('E1', 'E1_remote', '0 ngày tại chỗ nhưng có bằng chứng làm việc từ xa', False,
        lambda c: c.attendance(alternative=1))
    run('E1', 'E1_paid_leave', 'Nghỉ hưởng lương đã duyệt 22 ngày, hợp đồng và hồ sơ đầy đủ', False,
        lambda c: c.attendance(leave=22))

    def names(c, similar):
        c.tables['vendors'] = c.tables['vendors'][12:14]
        c.tables['vendors'][0]['name'] = 'ABC Co., Ltd' if similar else 'Gốm Bình Minh'
        c.tables['vendors'][1]['name'] = 'A.B.C Co Ltd' if similar else 'Vận tải Hải Đăng'
        return c.pay()

    run('E3', 'E3_name_variants', 'ABC Co., Ltd và A.B.C Co Ltd, hai mã NCC', True,
        lambda c: names(c, True))
    run('E3', 'E3_distinct_names', 'Hai NCC với tên ngành nghề/thương hiệu khác nhau', False,
        lambda c: names(c, False))
    run('F1', 'F1_material_close', 'Điều chỉnh 30 triệu ngày cuối tháng, trọng yếu 20 triệu', True,
        lambda c: c.pay(c.at.replace(day=31), 30_000_000, kind='adjustment'))
    run('F1', 'F1_midmonth', 'Điều chỉnh trọng yếu giữa tháng', False,
        lambda c: c.pay(amount=30_000_000, kind='adjustment'))

    def close_exempt(c):
        c.config = {'materiality_vnd_by_company': {'C001': 10_000_000}}
        c.maker = c.director
        return c.pay(c.at.replace(day=31), 15_000_000, kind='adjustment',
                     approver_id=c.director['employee_id'], support_doc_count=3)

    run('F1', 'F1_documented_close', 'Điều chỉnh cuối tháng có hồ sơ, tự duyệt trong quyền', False, close_exempt)
    return results
