"""Point-in-time features. Never reads labels, case IDs, splits, or future rows."""
from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from itertools import groupby

from .generate import PAIRS, parse
from .temporal_evidence import BankChangeHistory, bank_change_state
from .accounting import (NORMALISED_ACCOUNTS, PAIR_VOCABULARY, ACCOUNTING_FEATURE_DESCRIPTIONS,
                        accounting_features, normalise_account)

BASE_DESCRIPTIONS = {
    "log_amount": "log1p(số tiền VND); review tạm ứng dùng số dư cần rà soát",
    "amount_limit_ratio": "Số tiền / hạn mức của người lập; hạn mức nội bộ mô phỏng",
    "near_limit": "Số tiền trong [80%,100%) hạn mức người lập",
    "round_million": "Số tiền chia hết cho 1 triệu; dấu hiệu quan sát, không phải nhãn",
    "hour_sin": "sin(2*pi*giờ lập/24)", "hour_cos": "cos(2*pi*giờ lập/24)",
    "weekday_sin": "sin(2*pi*thứ lập/7)", "weekday_cos": "cos(2*pi*thứ lập/7)",
    "month_sin": "sin(2*pi*tháng/12)", "month_cos": "cos(2*pi*tháng/12)",
    "created_weekend": "Lập vào thứ 7 hoặc chủ nhật", "created_holiday": "Ngày lập thuộc lịch mô phỏng",
    "created_off_hours": "Giờ lập <8 hoặc >=19", "period_end_distance": "Số ngày từ ngày ghi sổ tới cuối tháng",
    "approval_log_hours": "log1p(giờ duyệt - giờ lập); chỉ chấm sau duyệt/ghi sổ",
    "self_approved": "Người lập = người duyệt", "self_approval_permitted": "Tự duyệt trong hạn mức nhân sự",
    "support_doc_count": "Số chứng từ đã có khi ghi sổ", "goods_receipt_verified": "Bằng chứng nhận hàng đã xác minh",
    "has_vendor": "Có NCC", "has_customer": "Có khách hàng", "has_employee_recipient": "Có nhân viên nhận tiền",
    "is_financial_entry": "1=bút toán tiền/sổ cái, 0=rà soát tạm ứng phi tài chính",
    "vendor_age_log_days": "log1p(tuổi pháp nhân vào thời điểm ghi sổ), không có NCC=0",
    "vendor_tenure_log_days": "log1p(số ngày từ onboard NCC đến ghi sổ)",
    "employee_bank_overlap": "Tài khoản thụ hưởng của NCC trùng nhân sự đã biết trong SME",
    "employee_phone_overlap": "SĐT NCC trùng nhân sự đã biết", "employee_address_overlap": "Địa chỉ NCC trùng nhân sự đã biết",
    "related_party_disclosed": "Khai báo bên liên quan đã tồn tại trước chấm điểm",
    "graph_employee_count": "Số nhân viên trong thành phần liên thông NCC theo TK/SĐT/người đại diện đã quan sát",
    "linked_vendor_count": "Số NCC trong thành phần liên thông đã quan sát; địa chỉ không được dùng làm cạnh mạnh",
    "recipient_employee_bank_count": "Số nhân viên đã biết cùng tài khoản thụ hưởng; hữu ích cho lương ma",
    "registry_risky_now": "Trạng thái gần nhất đã công bố và có hiệu lực là ceased/abandoned",
    "registry_risky_at_invoice": "Trạng thái rủi ro có hiệu lực trước ngày hóa đơn theo thông tin đã biết",
    "bank_changed_recently": "Đổi TK đã quan sát/có hiệu lực trong 14 ngày, đúng TK nhận; phiên bản as-of",
    "bank_change_verified": "Đổi TK gần đây đúng người nhận, callback/duyệt độc lập đã biết khi chấm",
    "invoice_log_gross": "log1p(tổng giá trị hóa đơn)", "invoice_payment_ratio": "Lần thanh toán hiện tại / tổng hóa đơn",
    "prior_invoice_payment_count": "Số lần trả hóa đơn cùng công ty+NCC+số HĐ trước hiện tại",
    "cumulative_invoice_payment_ratio": "(Tổng đã trả trước + lần hiện tại) / tổng HĐ; 0 nếu không thanh toán",
    "prior_same_amount_30d": "Số thanh toán cùng NCC+số tiền trong 30 ngày trước hiện tại",
    "recipient_count_3d": "Số thanh toán cùng tài khoản nhận trong 3 ngày trước hiện tại",
    "recipient_sum_limit_3d": "Tổng thanh toán cùng TK 3 ngày trước / hạn mức người lập hiện tại",
    "creator_count_7d": "Số thanh toán người lập 7 ngày trước hiện tại",
    "creator_sum_limit_7d": "Tổng thanh toán người lập 7 ngày trước / hạn mức hiện tại",
    "creator_recipients_7d": "Số TK người nhận khác nhau của người lập 7 ngày trước",
    "creator_near_limit_30d": "Số thanh toán cận hạn mức của người lập 30 ngày trước",
    "prior_type_history_log_count": "log1p(số giao dịch trước cùng SME+loại)",
    "log_amount_vs_history": "Độ lệch log tiền so với trung bình lịch sử trước cùng SME+loại",
    "amount_history_z": "Z-score log tiền so lịch sử trước, SD tối thiểu .25; chưa đủ 5 mẫu=0",
    "advance_age_days": "Số ngày từ giải ngân tạm ứng đến chấm điểm",
    "advance_overdue_days": "Ngày quá hạn theo hạn đã biết; gia hạn phê duyệt được áp dụng",
    "advance_open_fraction": "Tỷ lệ dư nợ trước sự kiện hiện tại, không đọc trạng thái đóng tương lai",
    "advance_extension_known": "Đã có gia hạn được phê duyệt trước chấm điểm",
    "attendance_known": "Đã có bản chấm công kỳ lương tại thời điểm chấm điểm",
    "attendance_days": "Số ngày làm việc quan sát trong kỳ, thiếu=0 kèm cờ attendance_known",
    "alternative_work_evidence": "Bằng chứng làm việc thay chấm công cho nhân sự từ xa",
    "employee_contract_on_file": "Hợp đồng có trong hồ sơ đã biết, không có người nhận NV=0",
    "payable_to_employee_bank": "Nợ 331/Có 111-112 trả NCC vào TK nhân viên đã biết; tín hiệu đối chiếu, không tự kết luận gian lận",
}
ACCOUNTS = NORMALISED_ACCOUNTS
FEATURE_DESCRIPTIONS = dict(BASE_DESCRIPTIONS)
FEATURE_DESCRIPTIONS.update({f"type_{t}":f"One-hot loại nghiệp vụ {t}" for t in PAIRS})
FEATURE_DESCRIPTIONS.update(ACCOUNTING_FEATURE_DESCRIPTIONS)
FEATURE_DESCRIPTIONS.update({f"{side}_{a}":f"One-hot tài khoản {side} {a}" for side in ("debit", "credit") for a in ACCOUNTS})
FEATURE_DESCRIPTIONS.update({f"pair_{d}_{c}":f"Cặp chuẩn hóa Nợ {d}/Có {c} xuất hiện trong bút toán nhiều dòng, gồm VAT; nhóm chi phí 642 dùng chung TT133/TT200" for d,c in PAIR_VOCABULARY})


class UnionFind:
    def __init__(self):
        self.parent, self.size, self.employees, self.vendors = {}, {}, {}, {}

    def add(self, node, employee=False, vendor=False):
        if node not in self.parent:
            self.parent[node], self.size[node] = node, 1
            self.employees[node], self.vendors[node] = int(employee), int(vendor)

    def root(self, node):
        if node not in self.parent:
            self.add(node)
        while node!=self.parent[node]:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def join(self, left, right):
        l, r = self.root(left), self.root(right)
        if l==r:
            return
        if self.size[l]<self.size[r]:
            l, r = r, l
        self.parent[r] = l
        self.size[l] += self.size[r]
        self.employees[l] += self.employees[r]
        self.vendors[l] += self.vendors[r]


class Stream:
    def __init__(self, rows, column="observed_at"):
        self.rows = sorted(rows, key=lambda r: r[column])
        self.column, self.index = column, 0

    def until(self, now, inclusive=True):
        while self.index<len(self.rows):
            row = self.rows[self.index]
            value = row[self.column]
            if value>now or (not inclusive and value==now):
                break
            self.index += 1
            yield row


def build_features(tables):
    """All histories are past-only; simultaneous transactions update after their batch."""
    import calendar
    transactions = sorted(tables["transactions"], key=lambda r:(r["posted_at"],r["transaction_id"]))
    employee_stream = Stream(tables["employees"], "recorded_at")
    vendor_stream = Stream(tables["vendors"], "recorded_at")
    streams = {name:Stream(tables.get(name, [])) for name in (
        "entity_links", "attendance", "vendor_status_history", "advance_events")}
    bank_changes = BankChangeHistory(tables.get('bank_account_changes', []))
    advance_stream = Stream(tables.get("advances", []), "recorded_at")
    holiday_dates = {r["date"] for r in tables["calendar"]}
    graph = defaultdict(UnionFind)
    employees, vendors, advances = {}, {}, {}
    employee_tokens = defaultdict(Counter)
    attendance, statuses = {}, defaultdict(list)
    advance_due, advance_closed, advance_extended = {}, defaultdict(int), set()
    invoice_paid, invoice_count = defaultdict(int), defaultdict(int)
    same_amount, recipient_history, creator_history = defaultdict(deque), defaultdict(deque), defaultdict(deque)
    history = defaultdict(lambda: [0, 0., 0.])
    companies = {c['company_id']:c for c in tables['companies']}
    journal_lines = defaultdict(list)
    for line in tables.get('journal_lines',[]):
        if line['transaction_id']:
            journal_lines[line['transaction_id']].append(line)
    pair_counts,company_financial_counts = Counter(),Counter()
    features = []
    for now, batch_iterator in groupby(transactions, key=lambda r:r["posted_at"]):
        batch = list(batch_iterator)
        for e in employee_stream.until(now):
            employees[e["employee_id"]] = e
            g = graph[e["company_id"]]
            g.add(e["employee_id"], employee=True)
            for field in ("bank_account", "phone", "address"):
                employee_tokens[(e["company_id"], field)][e[field]] += 1
        for v in vendor_stream.until(now):
            vendors[v["vendor_id"]] = v
            graph[v["company_id"]].add(v["vendor_id"], vendor=True)
        for edge in streams["entity_links"].until(now):
            graph[edge["company_id"]].join(edge["source_id"], edge["target_id"])
        for event in streams["attendance"].until(now):
            attendance[(event["employee_id"],event["payroll_period"])] = event
        for event in streams["vendor_status_history"].until(now):
            statuses[event["vendor_id"]].append(event)
        bank_changes.advance(now)
        for event in advance_stream.until(now):
            aid = event["advance_id"]
            advances[aid], advance_due[aid] = event, event["original_due_at"]
        # A settlement/writeoff being scored must not erase its own pre-event outstanding balance.
        for event in streams["advance_events"].until(now, inclusive=False):
            aid = event["advance_id"]
            if event["event_type"]=="extension":
                advance_due[aid] = event["new_due_at"]
                advance_extended.add(aid)
            elif event['event_type']!='reclassification':
                advance_closed[aid] += int(event["amount_vnd"])
        at = parse(now)
        for r in batch:
            cid, vid, eid, creator = r["company_id"],r["vendor_id"],r["employee_id"],r["creator_id"]
            v, e = vendors.get(vid), employees.get(eid)
            user = employees[creator]
            created = parse(r["created_at"])
            amount, limit = int(r["amount_vnd"]), int(r["approval_limit_vnd"])
            log_amount = math.log1p(amount)
            is_payment = r["txn_type"]=="vendor_payment"
            key = (cid, vid, r["invoice_number"])
            invoice_gross = int(r["invoice_gross_vnd"])
            g = graph[cid]
            root = g.root(vid) if v else None
            known_status = [s for s in statuses.get(vid, []) if s["effective_at"]<=now]
            current = max(known_status, key=lambda s:s["effective_at"]) if known_status else None
            invoice_status = [s for s in known_status if s["effective_at"]<=r["invoice_issued_at"]]
            issuer = max(invoice_status, key=lambda s:s["effective_at"]) if invoice_status else None
            change = bank_changes.current(cid, vid, now)
            changed_recently, verified = bank_change_state(change, r, employees, now)
            same = same_amount[(cid,vid,amount)] if is_payment else deque()
            while same and (at-parse(same[0])).total_seconds()>30*86400:
                same.popleft()
            recipient = recipient_history[(cid,r["recipient_account"])] if is_payment else deque()
            while recipient and (at-parse(recipient[0][0])).total_seconds()>3*86400:
                recipient.popleft()
            creator_rows = creator_history[(cid,creator)]
            while creator_rows and (at-parse(creator_rows[0][0])).total_seconds()>30*86400:
                creator_rows.popleft()
            creator_7d = [item for item in creator_rows if (at-parse(item[0])).total_seconds()<=7*86400]
            num, mean, m2 = history[(cid,r["txn_type"])]
            aid = r["advance_id"]
            advance = advances.get(aid)
            active_fraction = max(0, 1-advance_closed[aid]/int(advance["original_amount_vnd"])) if advance else 0
            att = attendance.get((eid,r["payroll_period"]))
            f = dict(transaction_id=r["transaction_id"], log_amount=log_amount, amount_limit_ratio=amount/limit,
                near_limit=int(.8<=amount/limit<1), round_million=int(amount%1_000_000==0),
                hour_sin=math.sin(2*math.pi*created.hour/24), hour_cos=math.cos(2*math.pi*created.hour/24),
                weekday_sin=math.sin(2*math.pi*created.weekday()/7), weekday_cos=math.cos(2*math.pi*created.weekday()/7),
                month_sin=math.sin(2*math.pi*at.month/12), month_cos=math.cos(2*math.pi*at.month/12),
                created_weekend=int(created.weekday()>=5), created_holiday=int(created.date().isoformat() in holiday_dates),
                created_off_hours=int(created.hour<8 or created.hour>=19),
                period_end_distance=calendar.monthrange(at.year,at.month)[1]-at.day,
                approval_log_hours=math.log1p(max(0,(parse(r["approved_at"])-created).total_seconds()/3600)),
                self_approved=int(creator==r["approver_id"]),
                self_approval_permitted=int(creator==r["approver_id"] and amount<=int(user["self_approval_limit_vnd"])),
                support_doc_count=int(r["support_doc_count"]), goods_receipt_verified=int(r["goods_receipt_verified"]),
                has_vendor=int(bool(v)), has_customer=int(bool(r["customer_id"])), has_employee_recipient=int(bool(e)),
                is_financial_entry=int(r["is_financial_entry"]),
                vendor_age_log_days=math.log1p(max(0,(at-parse(v["registered_at"])).days)) if v else 0,
                vendor_tenure_log_days=math.log1p(max(0,(at-parse(v["onboarded_at"])).days)) if v else 0,
                employee_bank_overlap=int(bool(v and employee_tokens[(cid,"bank_account")][r["recipient_account"]])),
                employee_phone_overlap=int(bool(v and employee_tokens[(cid,"phone")][v["phone"]])),
                employee_address_overlap=int(bool(v and employee_tokens[(cid,"address")][v["address"]])),
                related_party_disclosed=int(bool(v and v["related_party_disclosed_at"] and v["related_party_disclosed_at"]<=now)),
                graph_employee_count=g.employees[root] if root else 0, linked_vendor_count=g.vendors[root] if root else 0,
                recipient_employee_bank_count=employee_tokens[(cid,"bank_account")][r["recipient_account"]] if e else 0,
                registry_risky_now=int(bool(current and current["status"]!="active")),
                registry_risky_at_invoice=int(bool(issuer and issuer["status"]!="active")),
                bank_changed_recently=int(changed_recently), bank_change_verified=int(verified),
                invoice_log_gross=math.log1p(invoice_gross), invoice_payment_ratio=amount/invoice_gross if invoice_gross else 0,
                prior_invoice_payment_count=invoice_count[key] if is_payment else 0,
                cumulative_invoice_payment_ratio=(invoice_paid[key]+amount)/invoice_gross if is_payment and invoice_gross else 0,
                prior_same_amount_30d=len(same), recipient_count_3d=len(recipient),
                recipient_sum_limit_3d=sum(item[1] for item in recipient)/limit,
                creator_count_7d=len(creator_7d), creator_sum_limit_7d=sum(item[1] for item in creator_7d)/limit,
                creator_recipients_7d=len({item[2] for item in creator_7d}),
                creator_near_limit_30d=sum(item[3] for item in creator_rows),
                prior_type_history_log_count=math.log1p(num), log_amount_vs_history=log_amount-mean if num else 0,
                amount_history_z=(log_amount-mean)/max(.25,math.sqrt(m2/max(1,num-1))) if num>=5 else 0,
                advance_age_days=(at-parse(advance["issued_at"])).days if advance else 0,
                advance_overdue_days=max(0,(at-parse(advance_due[aid])).days) if advance and active_fraction>0 else 0,
                advance_open_fraction=active_fraction, advance_extension_known=int(aid in advance_extended),
                attendance_known=int(bool(att)), attendance_days=int(att["days_worked_observed"]) if att else 0,
                alternative_work_evidence=int(att["alternative_work_evidence"]) if att else 0,
                employee_contract_on_file=int(e["contract_on_file"]) if e else 0,
                payable_to_employee_bank=int(r['debit_account']=='331' and r['credit_account'] in {'111','112'} and
                    bool(employee_tokens[(cid,'bank_account')][r['recipient_account']])))
            f.update({f"type_{t}":int(r["txn_type"]==t) for t in PAIRS})
            framework = companies[cid]['accounting_framework']
            pair_key = (cid,normalise_account(r['debit_account'],framework),normalise_account(r['credit_account'],framework))
            af = accounting_features(r,[l for l in journal_lines[r['transaction_id']] if l['posted_at']<=now],
                                     companies[cid],pair_counts[pair_key],company_financial_counts[cid])
            f.update(af)
            features.append({k:round(value, 8) if isinstance(value,float) else value for k,value in f.items()})
        for r in batch:
            cid, amount, limit = r["company_id"],int(r["amount_vnd"]),int(r["approval_limit_vnd"])
            if int(r['is_financial_entry']):
                framework = companies[cid]['accounting_framework']
                pair_counts[(cid,normalise_account(r['debit_account'],framework),normalise_account(r['credit_account'],framework))] += 1
                company_financial_counts[cid] += 1
            if r["txn_type"]=="vendor_payment":
                key = (cid,r["vendor_id"],r["invoice_number"])
                invoice_paid[key] += amount
                invoice_count[key] += 1
                same_amount[(cid,r["vendor_id"],amount)].append(now)
                recipient_history[(cid,r["recipient_account"])].append((now,amount))
                creator_history[(cid,r["creator_id"])].append((now,amount,r["recipient_account"],int(.8<=amount/limit<1)))
            h = history[(cid,r["txn_type"])]
            log_amount = math.log1p(amount)
            h[0] += 1
            delta = log_amount-h[1]
            h[1] += delta/h[0]
            h[2] += delta*(log_amount-h[1])
    return features
