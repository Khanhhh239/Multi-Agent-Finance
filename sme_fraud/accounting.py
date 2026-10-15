"""Historical TT133/TT200 accounting templates for this benchmark's 2024-2025 scope.

Supported pairs are scenario-specific, not an exhaustive statutory whitelist.
Balanced, formally supported entries do not establish business authenticity.
"""
from __future__ import annotations

import copy
import hashlib
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta

VERSION = "2.0"
FRAMEWORKS = ("TT200", "TT133", "TT133", "TT133", "TT200")
ADDED_TYPES = ("material_issue", "production_completion", "vat_offset", "tools_purchase")
RAW_ACCOUNTS = ("111", "112", "131", "1331", "1332", "1388", "141", "152", "153", "154", "155", "156",
                "211", "214", "2293", "331", "3331", "334", "335", "621", "622", "627", "641", "642", "6421", "6422", "511", "632")
SOURCES = [
    dict(id="TT200", title="Thông tư 200/2014/TT-BTC", sections="TK 133, 138, 141, 154, 229, 334, 335, 641, 642; Phụ lục tài khoản",
         url="https://vbpl.moj.gov.vn/botuphap/Pages/vbpq-toanvan.aspx?ItemID=66801",
         official_index="https://congbao.chinhphu.vn/van-ban/thong-tu-so-200-2014-tt-btc-6697/3529.htm"),
    dict(id="TT133", title="Thông tư 133/2016/TT-BTC", sections="TK 133, 138, 141, 154, 229, 334, 335, 642; Phụ lục 1",
         url="https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=113560",
         full_text_mirror="https://lawplayer.com/vn/act/vn-vbpl-113560",
         official_index="https://congbao.chinhphu.vn/van-ban/thong-tu-so-133-2016-tt-btc-21048.htm"),
    dict(id="TT99_effective_date", title="Bộ Tài chính: thời điểm áp dụng TT99/2025",
         url="https://portal.mof.gov.vn/hoidapcstc/home/cthoidap/159102"),
    dict(id="TT45_asset_criteria",title="Bộ Tài chính: Điều 3 TT45/2013, tiêu chí TSCĐ",
         url="https://qlg.mof.gov.vn/hoidapcstc/home/cthoidap/149525"),
]


def normalise_account(account, framework):
    """Collapse expense coding, not the source ledger. 6421 differs by framework."""
    account = str(account)
    if account.startswith(("641", "642")):
        return "642"
    if account.startswith("133"):
        return "133"
    if account.startswith("138"):
        return "138"
    if account.startswith("229"):
        return "229"
    return account[:3] if len(account)>3 and account[:3] in {"111","112","211","214","333","334"} and not account.startswith("3331") else account


def expense_account(framework, purpose="admin"):
    return ("6421" if purpose=="selling" else "6422") if framework=="TT133" else ("641" if purpose=="selling" else "642")


def account_supported(account, framework):
    if account not in RAW_ACCOUNTS:
        return False
    return not (framework=="TT133" and account in {"641","621","622","627"})


def pair_supported(debit, credit, purpose, framework):
    """Return supported-for-this-template, never label a pair globally illegal."""
    admin, selling = expense_account(framework), expense_account(framework,"selling")
    costs = {admin, selling, "154", "621", "622", "627"}
    rules = {
        "vendor_payment": {("331","112"), ("331","111")},
        "stock_purchase": {("156","331"),("1331","331")},
        "material_purchase": {("152","331"),("1331","331")},
        "equipment_purchase": {("211","331"),("1332","331")},
        "tools_purchase": {("153","331"),("1331","331")},
        "sales_invoice": {("131","511"),("131","3331")},
        "revenue_accrual": {("131","511"),("131","3331")},
        "customer_receipt": {("112","131")},
        "cash_expense": {(admin,"111"),("1331","111")},
        "rent": {(admin,"112"),("1331","112")},
        "selling_expense": {(selling,"112"),("1331","112")},
        "payroll": {("334","112")},
        "salary_accrual": {(a,"334") for a in costs},
        "cost_allocation": {("154","621"),("154","622"),("154","627")},
        "cogs": {("632","156"),("632","155"),("632","154")},
        "production_completion": {("155","154")},
        "material_issue": {("154","152"),("621","152")},
        "expense_accrual": {(admin,"335")},
        "depreciation": {(admin,"214"),(selling,"214"),("154","214"),("627","214")},
        "tax_payment": {("3331","112")},
        "vat_offset": {("3331","1331")},
        "advance_issue": {("141","112")},
        "advance_settlement": {(admin,"141"),(selling,"141"),("154","141"),("1331","141")},
        "advance_reclassification": {("1388","141")},
        "bad_debt_provision": {(admin,"2293")},
        "advance_writeoff": {(admin,"1388"),("2293","1388")},
        "invoice_accrual": {(a,"331") for a in {"152","156","154","211",admin,selling,"1331","1332"}},
    }
    return account_supported(debit,framework) and account_supported(credit,framework) and (debit,credit) in rules.get(purpose,set())


NORMALISED_ACCOUNTS = sorted({normalise_account(a,"TT133") for a in RAW_ACCOUNTS})
PAIR_VOCABULARY = sorted({
    (normalise_account(d,f),normalise_account(c,f))
    for f in ("TT133","TT200") for d in RAW_ACCOUNTS for c in RAW_ACCOUNTS
    if any(pair_supported(d,c,p,f) for p in (
        "vendor_payment","stock_purchase","material_purchase","equipment_purchase","tools_purchase","sales_invoice",
        "customer_receipt","cash_expense","rent","selling_expense","payroll","salary_accrual",
        "cost_allocation","cogs","production_completion","material_issue","expense_accrual",
        "depreciation","tax_payment","vat_offset","advance_issue","advance_settlement",
        "advance_reclassification","bad_debt_provision","advance_writeoff","invoice_accrual"))
})


def _parse(value):
    return datetime.fromisoformat(value)


def _stamp(value):
    return value.isoformat(timespec="seconds")


def _pick(key, modulus):
    return int(hashlib.sha256(str(key).encode()).hexdigest()[:12],16)%modulus


def _tax(gross, rate=.10):
    net = round(gross/(1+rate))
    return net, gross-net


def enrich_accounting(tables, seed=20261012):
    """Add balanced documents without changing scored IDs, labels or prevalence.

    Reads economic records and evidence flags, never labels or fraud variants.
    Auxiliary documents are not additional scored observations.
    """
    rng = random.Random(seed+133200)
    companies = {r["company_id"]:r for r in tables["companies"]}
    employees = {r["employee_id"]:r for r in tables["employees"]}
    vendors = {r["vendor_id"]:r for r in tables["vendors"]}
    customers = {r["customer_id"]:r for r in tables["customers"]}
    staff, buyers = defaultdict(list),defaultdict(list)
    for i,c in enumerate(tables["companies"]):
        c.update(accounting_framework=FRAMEWORKS[i%5], recorded_at="2023-01-01T00:00:00+07:00",
                 bank_account=f"BANK_COMPANY_SYN_{c['company_id']}",
                 vat_method="credit", inventory_method="perpetual", accounting_scope="2024-2025")
    for e in employees.values():
        c = companies[e["company_id"]]
        e["cost_center"] = "production" if c["industry"] in {"manufacturing","services","logistics"} and e["role"]=="operations" and e["department"] in {"operations","warehouse"} else "selling" if e["department"]=="sales" else "admin"
        if e["recorded_at"]<"2024-01-01":
            staff[e["company_id"]].append(e)
    for buyer in customers.values():
        buyers[buyer["company_id"]].append(buyer)
    documents, lines, links, edges, invoices = [],[],[],[],{}
    invoice_documents = {}
    evidence = {r["transaction_id"]:int(r["evidence_on_file"]) for r in tables["advance_events"] if r["transaction_id"]}
    serial = 0

    def document(row, purpose, at, pairs, primary=False, vat_account="", invoice_info=None):
        nonlocal serial
        serial += 1
        docid = f"JD{serial:09d}"
        framework = companies[row["company_id"]]["accounting_framework"]
        total = sum(amount for _,_,amount in pairs)
        records = Counter()
        for debit,credit,amount in pairs:
            assert amount>0 and pair_supported(debit,credit,purpose,framework), (purpose,debit,credit,framework)
            records[(debit,"debit")] += amount
            records[(credit,"credit")] += amount
            edges.append(dict(document_id=docid, company_id=row["company_id"], observed_at=_stamp(at),
                source_account=credit,target_account=debit,amount_vnd=amount,
                employee_id=row["employee_id"],vendor_id=row["vendor_id"],invoice_id=row["invoice_id"],
                advance_id=row["advance_id"],purpose=purpose))
        documents.append(dict(document_id=docid,company_id=row["company_id"],posted_at=_stamp(at),
            purpose=purpose,accounting_framework=framework,is_scored_observation=int(primary),
            transaction_id=row["transaction_id"] if primary else "", amount_vnd=total,
            employee_id=row["employee_id"],vendor_id=row["vendor_id"],customer_id=row["customer_id"],
            invoice_id=row["invoice_id"],advance_id=row["advance_id"],
            evidence_on_file=int(row["evidence_on_file"]),vat_rate=row["vat_rate"] if vat_account else 0,
            vat_account=vat_account,invoice_net_vnd=invoice_info[0] if invoice_info else 0,
            invoice_vat_vnd=invoice_info[1] if invoice_info else 0,
            invoice_gross_vnd=sum(invoice_info) if invoice_info else 0))
        for (account,direction),amount in records.items():
            lines.append(dict(document_id=docid,transaction_id=row["transaction_id"] if primary else "",
                company_id=row["company_id"],posted_at=_stamp(at),account_code=account,
                debit_vnd=amount if direction=="debit" else 0,credit_vnd=amount if direction=="credit" else 0,
                employee_id=row["employee_id"],vendor_id=row["vendor_id"],customer_id=row["customer_id"],
                invoice_id=row["invoice_id"],advance_id=row["advance_id"]))
        return docid

    def connect(source, target, at, kind):
        links.append(dict(source_document_id=source,target_document_id=target,observed_at=_stamp(at),link_type=kind))

    def remember_invoice(row, gross):
        if not row["invoice_id"]:
            return
        net,vat = _tax(gross,row["vat_rate"])
        row.update(invoice_gross_vnd=gross,invoice_net_vnd=net,invoice_vat_vnd=vat)
        invoices[row["invoice_id"]] = dict(invoice_id=row["invoice_id"],company_id=row["company_id"],
            vendor_id=row["vendor_id"],customer_id=row["customer_id"],invoice_number=row["invoice_number"],
            issued_at=row["invoice_issued_at"],recorded_at=max(row["created_at"],row["invoice_issued_at"]),
            net_amount_vnd=net,vat_amount_vnd=vat,gross_amount_vnd=gross,vat_rate=row["vat_rate"],
            vat_rate_source="illustrative_invoice_assumption_not_tax_eligibility_advice")

    for r in sorted(tables["transactions"],key=lambda x:(x["posted_at"],x["transaction_id"])):
        cid,kind,at = r["company_id"],r["txn_type"],_parse(r["posted_at"])
        c = companies[cid]
        f,industry = c["accounting_framework"],c["industry"]
        admin,selling = expense_account(f),expense_account(f,"selling")
        amount = int(r["amount_vnd"])
        is_revenue = kind=="sales_invoice" or (kind=="adjustment" and r["credit_account"]=="511")
        r.update(accounting_framework=f,accounting_purpose="",journal_document_id="",linked_document_id="",
            counterparty_account=r['recipient_account'],counterparty_type='vendor' if r['vendor_id'] else 'customer' if r['customer_id'] else 'employee' if r['employee_id'] else 'none',
            vat_rate=.10 if r["invoice_id"] or is_revenue else 0.,invoice_net_vnd=0,invoice_vat_vnd=0,
            evidence_on_file=evidence.get(r["transaction_id"],int(r["support_doc_count"]>0)),
            recognised_input_vat_vnd=0,recognised_output_vat_vnd=0,linked_input_vat_vnd=0,
            production_cost_vnd=0,writeoff_provision_vnd=0)
        prerequisites = []
        # This template assumes one standalone equipment item per invoice.
        # Under-threshold items are tools, not automatically qualifying fixed assets.
        if kind=='equipment_purchase' and _tax(amount,r['vat_rate'])[0]<30_000_000:
            r.update(txn_type='tools_purchase',debit_account='153')
            kind='tools_purchase'
        if kind=="material_purchase" and industry in {"manufacturing","services","logistics"} and _pick(r["transaction_id"],3)==0:
            # Record acquisition separately, then score the subsequent issue to production.
            acquisition = dict(r)
            gross = amount+round(amount*.10)
            acquisition.update(amount_vnd=gross,invoice_gross_vnd=gross,vat_rate=.10)
            remember_invoice(acquisition,gross)
            purchase_at = _parse(max(acquisition["created_at"],acquisition["invoice_issued_at"]))
            purchase_at = min(purchase_at,at)
            docid = document(acquisition,"material_purchase",purchase_at,[("152","331",amount),("1331","331",gross-amount)],
                             vat_account="1331",invoice_info=(amount,gross-amount))
            prerequisites.append((docid,"materials_received_before_issue"))
            r.update(txn_type="material_issue",vendor_id="",invoice_id="",invoice_number="",invoice_issued_at="",
                invoice_gross_vnd=0,invoice_net_vnd=0,invoice_vat_vnd=0,vat_rate=0.,recipient_account="",payment_channel="journal")
            kind = "material_issue"
        if kind=="tax_payment" and _pick(r["transaction_id"],3)==0:
            r.update(txn_type="vat_offset",recipient_account="",payment_channel="journal")
            kind = "vat_offset"
        if is_revenue:
            if not r["customer_id"]:
                r["customer_id"] = buyers[cid][_pick(r["transaction_id"],len(buyers[cid]))]["customer_id"]
            r.update(invoice_id=r["invoice_id"] or f"I_SYN_{r['transaction_id']}",
                invoice_number=r["invoice_number"] or f"HD{r['transaction_id'][1:]}",
                invoice_issued_at=r["invoice_issued_at"] or r["posted_at"],invoice_gross_vnd=amount)
        remember_invoice(r,int(r["invoice_gross_vnd"]))
        purpose = "revenue_accrual" if is_revenue and kind=="adjustment" else "expense_accrual" if kind=="adjustment" else kind
        r["accounting_purpose"] = purpose
        if not int(r["is_financial_entry"]):
            r.update(debit_account="",credit_account="",account_pair="",journal_signature="",recipient_account='',payment_channel='journal')
            continue
        debit,credit = r["debit_account"],r["credit_account"]
        debit = selling if debit=="641" else admin if debit=="642" else debit
        if kind=="adjustment" and not is_revenue:
            debit,credit = admin,"335"
            r["business_purpose"] = "Trích trước chi phí dịch vụ đã nhận, chưa đủ hóa đơn"
        if kind=="cogs":
            credit = "155" if industry=="manufacturing" else "154" if industry in {"services","logistics"} else "156"
            if credit=="155":
                docid = document(r,"production_completion",at,[("155","154",amount)])
                prerequisites.append((docid,"completed_goods_before_sale"))
        if kind=="material_issue":
            debit,credit = ("154" if f=="TT133" else "621"),"152"
            r["production_cost_vnd"] = amount
        if kind=="vat_offset":
            debit,credit = "3331","1331"
        if kind=="advance_writeoff":
            # Reclassify a documented compensation claim; it is not debt forgiveness.
            reclass_at = at-timedelta(days=10)
            reclass = document(r,"advance_reclassification",reclass_at,[("1388","141",amount)])
            prerequisites.append((reclass,"receivable_before_writeoff"))
            tables["advance_events"].append(dict(event_id=f"AE_RECLASS_{r['transaction_id']}",advance_id=r["advance_id"],
                company_id=cid,event_type="reclassification",observed_at=_stamp(reclass_at),new_due_at="",
                amount_vnd=amount,transaction_id="",evidence_on_file=r["evidence_on_file"]))
            provision = round(amount*.5) if _pick(r["transaction_id"],2)==0 else 0
            if provision:
                provision_doc = document(r,"bad_debt_provision",at-timedelta(days=5),[(admin,"2293",provision)])
                prerequisites.append((provision_doc,"provision_before_writeoff"))
            debit,credit = admin,"1388"
            r["writeoff_provision_vnd"] = provision
        if kind=="vendor_payment":
            legal_key = (cid,r["vendor_id"],r["invoice_number"])
            if legal_key not in invoice_documents:
                purchase = dict(r)
                purchase_at = _parse(max(r["created_at"],r["invoice_issued_at"]))
                cost = "154" if industry in {"manufacturing","services","logistics"} and _pick(r["transaction_id"],2)==0 else "156" if industry in {"trading","retail"} else admin
                net,vat = r["invoice_net_vnd"],r["invoice_vat_vnd"]
                purchase_doc = document(purchase,"invoice_accrual",purchase_at,
                    [(cost,"331",net),*( [("1331","331",vat)] if vat else [])],
                    vat_account="1331",invoice_info=(net,vat))
                invoice_documents[legal_key] = (purchase_doc,vat,net if cost=="154" else 0)
            purchase_doc,vat,production = invoice_documents[legal_key]
            prerequisites.append((purchase_doc,"invoice_before_payment"))
            r.update(linked_input_vat_vnd=vat,production_cost_vnd=production)
        if kind=="payroll":
            e = employees[r["employee_id"]]
            cost = ("154" if f=="TT133" else "622") if e["cost_center"]=="production" else selling if e["cost_center"]=="selling" else admin
            accrued = document(r,"salary_accrual",at,[(cost,"334",amount)])
            prerequisites.append((accrued,"salary_accrued_before_payment"))
            if cost in {"154","622"}:
                r["production_cost_vnd"] = amount
                if f=="TT200":
                    allocation = document(r,"cost_allocation",at,[("154","622",amount)])
                    connect(accrued,allocation,at,"labour_allocated_to_wip")
                    prerequisites.append((allocation,"production_cost_allocation"))
        pairs = [(debit,credit,amount)]
        vat_account = ""
        invoice_info = None
        if kind in {"stock_purchase","material_purchase","equipment_purchase","tools_purchase","rent","selling_expense"}:
            net,vat = _tax(amount,r["vat_rate"])
            vat_account = "1332" if kind=="equipment_purchase" else "1331"
            pairs = [(debit,credit,net),*( [(vat_account,credit,vat)] if vat else [])]
            r["recognised_input_vat_vnd"] = vat
            invoice_info = (net,vat)
        elif is_revenue:
            net,vat = _tax(amount,r["vat_rate"])
            pairs = [("131","511",net),*( [("131","3331",vat)] if vat else [])]
            r["recognised_output_vat_vnd"] = vat
            debit,credit,vat_account,invoice_info = "131","511","3331",(net,vat)
        elif kind=="advance_writeoff":
            provision = r["writeoff_provision_vnd"]
            pairs = [(admin,"1388",amount-provision),*( [("2293","1388",provision)] if provision else [])]
        primary = document(r,purpose,at,pairs,primary=True,vat_account=vat_account,invoice_info=invoice_info)
        r.update(debit_account=debit,credit_account=credit,account_pair=f"{debit}/{credit}",journal_document_id=primary,
            journal_signature=";".join(f"{d}/{cr}" for d,cr,_ in pairs),
            linked_document_id=prerequisites[0][0] if prerequisites else "")
        # Counterparty reference and actual beneficiary are different concepts.
        if kind=='customer_receipt':
            r.update(recipient_account=c['bank_account'],payment_channel='bank')
        elif credit not in {'111','112'}:
            r.update(recipient_account='',payment_channel='journal')
        elif kind=='tax_payment':
            r.update(recipient_account='BANK_TREASURY_SYN',payment_channel='bank')
        for docid,link_type in prerequisites:
            connect(docid,primary,at,link_type)
        r['counterparty_type']='vendor' if r['vendor_id'] else 'customer' if r['customer_id'] else 'employee' if r['employee_id'] else 'none'
        if r['counterparty_type']=='none':
            r['counterparty_account']=''
        elif r['customer_id']:
            r['counterparty_account']=customers[r['customer_id']]['bank_account']
        if kind=="material_issue" and f=="TT200":
            allocation = document(r,"cost_allocation",at,[("154","621",amount)])
            connect(primary,allocation,at,"materials_allocated_to_wip")
    tables["invoices"] = list(invoices.values())
    tables["journal_documents"],tables["journal_lines"] = documents,lines
    tables["document_links"],tables["account_flow_edges"] = links,edges
    return tables


def accounting_features(row, primary_lines, company, prior_pair_count, prior_total):
    framework = company["accounting_framework"]
    debit_accounts = {line["account_code"] for line in primary_lines if int(line["debit_vnd"])}
    credit_accounts = {line["account_code"] for line in primary_lines if int(line["credit_vnd"])}
    norm_debits = {normalise_account(a,framework) for a in debit_accounts}
    norm_credits = {normalise_account(a,framework) for a in credit_accounts}
    pair = (normalise_account(row["debit_account"],framework),normalise_account(row["credit_account"],framework))
    raw_pairs=[tuple(item.split('/')) for item in row['journal_signature'].split(';') if item]
    observed_pairs={(normalise_account(d,framework),normalise_account(c,framework)) for d,c in raw_pairs}
    amount = int(row["amount_vnd"])
    financial = int(row["is_financial_entry"])
    f = dict(framework_tt133=int(framework=="TT133"),
        pair_supported_for_scenario=int(bool(financial and raw_pairs and all(pair_supported(d,c,row['accounting_purpose'],framework) for d,c in raw_pairs))),
        account_outside_framework=int(any(not account_supported(a,framework) for a in debit_accounts|credit_accounts)),
        pair_prior_log_count=__import__("math").log1p(prior_pair_count),
        pair_prior_frequency=prior_pair_count/prior_total if prior_total else 0,
        journal_line_count=len(primary_lines),
        journal_balance_difference_ratio=abs(sum(int(l["debit_vnd"])-int(l["credit_vnd"]) for l in primary_lines))/amount,
        invoice_vat_fraction=int(row["invoice_vat_vnd"])/int(row["invoice_gross_vnd"]) if int(row["invoice_gross_vnd"]) else 0,
        input_vat_fraction=int(row["recognised_input_vat_vnd"])/amount,
        output_vat_fraction=int(row["recognised_output_vat_vnd"])/amount,
        linked_input_vat_fraction=int(row["linked_input_vat_vnd"])/int(row["invoice_gross_vnd"]) if int(row["invoice_gross_vnd"]) else 0,
        vat_invoice_arithmetic_gap=abs(int(row["invoice_net_vnd"])+int(row["invoice_vat_vnd"])-int(row["invoice_gross_vnd"]))/max(1,int(row["invoice_gross_vnd"])),
        advance_recipient_is_vendor=int('141' in norm_debits and bool(row['vendor_id'])),
        advance_writeoff_evidence_missing=int(row["txn_type"]=="advance_writeoff" and not int(row["evidence_on_file"])),
        writeoff_provision_fraction=int(row["writeoff_provision_vnd"])/amount,
        production_cost_fraction=int(row["production_cost_vnd"])/amount)
    f.update({f"{side}_{a}":int(a in values) for side,values in (("debit",norm_debits),("credit",norm_credits)) for a in NORMALISED_ACCOUNTS})
    f.update({f"pair_{d}_{c}":int(financial and (d,c) in observed_pairs) for d,c in PAIR_VOCABULARY})
    return f


ACCOUNTING_FEATURE_DESCRIPTIONS = {
    "framework_tt133":"Công ty áp dụng TT133 trong kỳ 2024-2025; 0=TT200",
    "pair_supported_for_scenario":"Cặp chính được template nghiệp vụ hỗ trợ; 0 không đồng nghĩa trái luật hay gian lận",
    "account_outside_framework":"Mã sổ cái nằm ngoài tập tài khoản hỗ trợ của chế độ kế toán trong benchmark",
    "pair_prior_log_count":"log1p(số quan sát trước cùng công ty và cặp tài khoản chuẩn hóa)",
    "pair_prior_frequency":"Tần suất cặp chuẩn hóa trong các quan sát tài chính trước của công ty",
    "journal_line_count":"Số dòng bút toán chính, bao gồm VAT và dự phòng nếu có",
    "journal_balance_difference_ratio":"|Tổng Nợ - Tổng Có| / giá trị chứng từ",
    "invoice_vat_fraction":"Thuế trên hóa đơn / tổng hóa đơn; thuế suất giả định minh họa",
    "input_vat_fraction":"VAT đầu vào ghi Nợ 133 trong bút toán chính / giá trị chứng từ",
    "output_vat_fraction":"VAT đầu ra ghi Có 3331 trong bút toán chính / giá trị chứng từ",
    "linked_input_vat_fraction":"VAT đầu vào đã ghi ở chứng từ hóa đơn liên kết / tổng hóa đơn; không ghi lại khi trả tiền",
    "vat_invoice_arithmetic_gap":"Sai lệch số học (net + VAT - gross) / gross, không xác minh đủ điều kiện khấu trừ",
    "advance_recipient_is_vendor":"Nghiệp vụ cấp tạm ứng 141 có NCC nhận và không có nhân viên nhận",
    "advance_writeoff_evidence_missing":"Xóa nợ thiếu hồ sơ đối chiếu/phê duyệt ở thời điểm ghi sổ",
    "writeoff_provision_fraction":"Tỷ lệ xóa nợ được bù bằng dự phòng 2293 đã có",
    "production_cost_fraction":"Chi phí gắn vào 154, trực tiếp hoặc qua 621/622, đã biết khi chấm điểm",
}
