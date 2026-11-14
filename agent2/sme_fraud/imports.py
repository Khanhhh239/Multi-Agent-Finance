"""Agent2's input profile. No file I/O, persistence, fitting or alert delivery.

An authenticated backend must construct AccessScope before reading uploaded data.
This module is also callable offline for synthetic contract acceptance tests.
"""
from copy import deepcopy
import re

from finance_input import AccessScope, CONTRACT_VERSION, SUPPORTED_CONTRACT_VERSIONS, check_core, schema
from finance_input.money import minor
from finance_input.validation import issue, key, records, stamp
from . import p1_inputs

PROFILE_VERSION = "agent2-posted-vnd/1.1.0"
VALIDATOR_VERSION = "1.3.0"
REPORT_VERSION = "1.2.0"
DEFINITIONS = {"companies":"company", "transactions":"transaction", "vendors":"vendor",
               "invoices":"invoice", "payment_allocations":"allocation", "employees":"employee",
               "approvals":"approval", "supporting_documents":"document", "vendor_bank_history":"bank_history",
               "payment_history_coverage":"payment_history_coverage"}


def parse_vnd(value):
    """Adapter boundary only: exact signed VND, no float/grouping/rounding.

    Canonical bundles already require integers. CSV localized or ambiguous text
    must be mapped/confirmed upstream; it is never guessed here.
    """
    if isinstance(value, str) and not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError("Dùng số nguyên VND hoặc chuỗi thập phân chuẩn, không dấu phân nhóm.")
    result = minor(value, "VND")
    if abs(result) > 999999999999999999:
        raise ValueError("Số tiền vượt 18 chữ số VND.")
    return result


def _references(table, row):
    mapping = {
        "transactions": {"vendor_ref": "vendors", "employee_ref": "employees", "created_by_ref": "employees", "adjusts_ref": "transactions"},
        "invoices": {"vendor_ref": "vendors", "adjusts_ref": "invoices"},
        "payment_allocations": {"transaction_ref": "transactions", "invoice_ref": "invoices", "adjusts_ref": "payment_allocations"},
        "approvals": {"transaction_ref": "transactions", "employee_ref": "employees"},
        "vendor_bank_history": {"vendor_ref": "vendors"},
    }
    for field, target in mapping.get(table, {}).items():
        if row.get(field) is not None:
            yield field, target, row[field]
    for index, target in enumerate(row.get("subject_refs", [])):
        yield f"subject_refs/{index}", target["table"], target
    if table=='payment_history_coverage':
        for index,ref in enumerate(row['invoice_refs']):yield f'invoice_refs/{index}','invoices',ref
        for name,target in (('invoice_refs','invoices'),('transaction_refs','transactions'),('allocation_refs','payment_allocations')):
            for index,ref in enumerate(row['manifest'][name]):yield f'manifest/{name}/{index}',target,ref


def validate_input(bundle, scope):
    """Backend report for a closed, company-scoped bundle. No rows are dropped.

    Report is not a commit token. Snapshot store, report hashes and authentication
    integration are intentionally left for the remaining R1 work.
    """
    if isinstance(bundle,dict) and bundle.get('contract_version')=='agent2-rule-snapshot/1.0.0':
        from .rule_snapshot import validate
        return validate(bundle,scope)
    errors = check_core(bundle, scope)
    declared=bundle.get('contract_version') if isinstance(bundle,dict) else None
    contract=declared if isinstance(declared,str) and declared in SUPPORTED_CONTRACT_VERSIONS else CONTRACT_VERSION
    report = dict(contract_version=contract, validator_version=VALIDATOR_VERSION,
                  profile_version=PROFILE_VERSION, status="rejected", errors=errors,
                  report_version=REPORT_VERSION, warnings=[], counts={}, capabilities={}, analysis_limits={})
    if errors:
        return report
    warnings = report["warnings"]
    definitions = schema(contract)["$defs"]
    lookup = {key(table, row): row for table, _, row in records(bundle)}
    row_paths = {key(table, row): f"/{table}/{index}" for table, index, row in records(bundle)}
    adjustment_edges = {}
    for table, index, row in records(bundle):
        path = f"/{table}/{index}"
        for field, target, reference in _references(table, row):
            target_key = (row["tenant_id"], row["company_id"], target,
                          reference["record_id"], reference["revision"])
            linked = lookup.get(target_key)
            if linked is None:
                errors.append(issue("REFERENCE_MISSING", f"{path}/{field}",
                    "Không tìm thấy bản ghi được tham chiếu trong cùng doanh nghiệp và revision.",
                    "Bổ sung bản ghi nguồn hoặc sửa tham chiếu; không dùng bản ghi của doanh nghiệp khác."))
            elif target_key == key(table, row):
                errors.append(issue("SELF_REFERENCE", f"{path}/{field}", "Bản ghi không thể điều chỉnh chính nó.",
                                    "Dẫn định danh và revision của bản ghi gốc."))
            elif field == "adjusts_ref" and stamp(linked["observed_at"]) > stamp(row["observed_at"]):
                errors.append(issue("ADJUSTMENT_TIME", f"{path}/{field}", "Điều chỉnh được biết trước bản ghi gốc.",
                                    "Kiểm tra thời điểm nguồn được biết của hai bản ghi."))
            elif stamp(linked["observed_at"]) > stamp(row["observed_at"]):
                warnings.append(issue("REFERENCE_KNOWN_LATER", f"{path}/{field}",
                    "Nguồn liên quan chỉ được biết sau bản ghi này.",
                    "Giữ thời điểm nguồn; khi chấm quá khứ không dùng nguồn đến muộn."))
            if field == "adjusts_ref" and linked is not None:
                adjustment_edges[key(table, row)] = target_key
        adjustment = row.get("kind") in {"adjustment", "reversal", "credit_note"}
        if table in {"transactions", "invoices", "payment_allocations"}:
            if (row["amount_vnd"] < 0 or adjustment) and (
                not adjustment or not row.get("adjustment_reason", "").strip() or not row.get("adjusts_ref")
            ):
                field = "kind" if not adjustment else "adjustment_reason" if not row.get("adjustment_reason", "").strip() else "adjusts_ref"
                errors.append(issue("ADJUSTMENT_CONTEXT", path+"/"+field,
                    "Số âm hoặc khoản điều chỉnh cần loại, lý do và bản ghi gốc.",
                    "Chọn adjustment/reversal/credit_note phù hợp và bổ sung adjustment_reason, adjusts_ref; giữ nguyên dấu tiền."))
            if row["amount_vnd"] == 0:
                warnings.append(issue("ZERO_AMOUNT", path+"/amount_vnd", "Bản ghi có số tiền bằng 0.", "Xác nhận đây là bản ghi hợp lệ; không tự bỏ dòng."))
        for field in row.get("missing_fields", {}):
            # Missing metadata can describe only actual optional fields of this record.
            definition = definitions[DEFINITIONS[table]]
            if field not in definition["properties"] or field in definition["required"] or row.get(field) is not None:
                errors.append(issue("MISSING_CONFLICT", f"{path}/missing_fields/{field}",
                    "Trạng thái thiếu mâu thuẫn với trường dữ liệu.",
                    "Chỉ ghi trạng thái thiếu cho cột tùy chọn chưa có giá trị; không gắn cho cột bắt buộc."))
        verification_status = row.get("verification_status")
        if table=='vendors' and row.get('related_party_disclosed_at') and stamp(row['related_party_disclosed_at'])>stamp(row['observed_at']):
            errors.append(issue('DISCLOSURE_TIME',path+'/related_party_disclosed_at',
                'Ngày khai báo quan hệ sau thời điểm nguồn được biết.',
                'Ghi đúng observed_at của revision nhận khai báo; không lùi thời gian nguồn.'))
        verification = row.get("verification")
        if verification_status == "verified":
            if "evidence.verify" not in scope.permissions:
                errors.append(issue("VERIFICATION_PERMISSION", path+"/verification_status", "Chưa có quyền xác nhận nguồn đã được xác minh.",
                                    "Giữ unverified hoặc chuyển người có quyền evidence.verify đối chiếu căn cứ."))
            if not verification:
                errors.append(issue("VERIFICATION_MISSING", path+"/verification", "Đã xác minh nhưng chưa ghi người, thời điểm và căn cứ.",
                                    "Bổ sung verification hoặc giữ trạng thái chưa xác minh."))
            elif stamp(verification["verified_at"]) > stamp(row["observed_at"]):
                errors.append(issue("VERIFICATION_TIME", path+"/verification/verified_at", "Xác minh diễn ra sau thời điểm được biết của revision này.",
                                    "Tạo revision mới với observed_at đúng thời điểm xác minh được biết."))
        elif verification:
            errors.append(issue("VERIFICATION_CONFLICT", path+"/verification_status", "Thông tin xác minh không khớp trạng thái.",
                                "Dùng trạng thái verified khi đã có đủ căn cứ xác minh."))
        if table == "supporting_documents" and (row["source_kind"] == "simulated") != row["source"]["is_simulated"]:
            errors.append(issue("SOURCE_KIND_CONFLICT", path+"/source_kind", "Loại chứng từ không khớp nguồn mô phỏng.",
                                "Giữ rõ simulated cho chứng từ mô phỏng; không đổi thành bản gốc."))
    # Iterative walk avoids recursion limits for large correction histories.
    completed = set()
    for start in adjustment_edges:
        visited = set()
        current = start
        while current in adjustment_edges and current not in completed:
            if current in visited:
                errors.append(issue("ADJUSTMENT_CYCLE", row_paths[start]+"/adjusts_ref", "Tham chiếu điều chỉnh tạo vòng lặp.",
                                    "Dẫn chuỗi điều chỉnh tới bản ghi gốc, không tạo vòng."))
                break
            visited.add(current)
            current = adjustment_edges[current]
        completed.update(visited)
    if not any(e['code']!='VERIFICATION_PERMISSION' for e in errors):
        p1_errors,p1_warnings=p1_inputs.validate_p1_sources(bundle)
        errors.extend(p1_errors);warnings.extend(p1_warnings)
    report["counts"] = {table: len(rows) for table, rows in bundle.items() if isinstance(rows, list)}
    if errors:
        return report  # a rejected bundle never advertises usable capabilities
    for company in sorted({r["company_id"] for r in bundle["companies"]}):
        rows = {t: [r for r in bundle.get(t, []) if r["company_id"] == company]
                for t in ("transactions", "vendor_bank_history", "payment_allocations", "supporting_documents")}
        caps = {}
        for name, table in (("transaction_input", "transactions"), ("bank_change_input", "vendor_bank_history"),
                            ("invoice_payment_links", "payment_allocations"), ("document_input", "supporting_documents")):
            available = bool(rows[table])
            caps[name] = dict(available=available, reason="records_present" if available else "not_provided")
            if not available:
                warnings.append(issue("CAPABILITY_UNAVAILABLE", f"/{table}",
                    f"{company}: chưa có dữ liệu cho {name}.", "Bổ sung nguồn khi cần phân tích này; các phần có dữ liệu vẫn được giữ."))
        report["capabilities"][company] = caps
        payment_rows=[r for r in p1_inputs._latest(bundle['transactions']) if r['company_id']==company and r['kind']=='payment']
        p1_states=[p1_inputs.transaction_inputs(bundle,r)[1] for r in payment_rows]
        caps['p1_input']=dict(available=bool(p1_states) and all(s['available'] for s in p1_states),
            reason='source_declared_inputs_present' if p1_states and all(s['available'] for s in p1_states) else 'p1_sources_missing_or_limited')
        limits = analysis_limits(bundle, company)
        report["analysis_limits"][company] = limits
        for limit in limits:
            detail = issue(limit["code"], "/transactions", limit["message"], limit["action"])
            detail.update(company_id=company, affected_count=limit["affected_count"])
            warnings.append(detail)
    report["status"] = "accepted_with_warnings" if warnings else "accepted"
    return report


def analysis_limits(bundle, company):
    """Source coverage in this bundle, not detector readiness or a risk verdict.

    Current record revisions are used so an older verified document cannot mask a
    later unverified revision. Historical feature coverage is assessed at replay.
    """
    latest = {}
    for table, index, row in records(bundle):
        if row["company_id"] != company:
            continue
        identity = (table, row["record_id"])
        if identity not in latest or row["revision"] > latest[identity][1]["revision"]:
            latest[identity] = (index, row)
    txs = [entry for (table, _), entry in latest.items() if table == "transactions"]
    source_rows = lambda name: [r for (table, _), (_, r) in latest.items() if table == name]
    allocations = source_rows("payment_allocations")
    invoices_by_tx = {}
    for row in allocations:
        target = row["transaction_ref"]
        invoices_by_tx.setdefault((target["record_id"], target["revision"]), set()).add(
            ("invoices", row["invoice_ref"]["record_id"], row["invoice_ref"]["revision"]))
    original_subjects = set()
    for row in source_rows("supporting_documents"):
        if row["source_kind"] == "original" and not row["source"]["is_simulated"] and row["verification_status"] == "verified":
            original_subjects.update((r["table"], r["record_id"], r["revision"]) for r in row["subject_refs"])
    bank_vendors = {(r["vendor_ref"]["record_id"], r["vendor_ref"]["revision"]) for r in source_rows("vendor_bank_history")}
    approved = {(r["transaction_ref"]["record_id"], r["transaction_ref"]["revision"]) for r in source_rows("approvals") if r["decision"] == "approved"}
    missing_docs = []; missing_bank = []; missing_invoice = []; missing_approval = []
    for index, row in txs:
        identity = (row["record_id"], row["revision"])
        subjects = {("transactions", *identity)} | invoices_by_tx.get(identity, set())
        entry = dict(table="transactions", row=index+1, record_id=row["record_id"], revision=row["revision"])
        if not subjects.intersection(original_subjects):
            missing_docs.append(entry)
        vendor = row.get("vendor_ref")
        if vendor and (vendor["record_id"], vendor["revision"]) not in bank_vendors:
            missing_bank.append(entry)
        if row["kind"] == "payment" and identity not in invoices_by_tx:
            missing_invoice.append(entry)
        if row["kind"] in {"payment", "payroll"} and identity not in approved:
            missing_approval.append(entry)
    limits = []
    p1_missing=[]
    for index,row in txs:
        if row['kind']=='payment':
            _,state=p1_inputs.transaction_inputs(bundle,row)
            if not state['available']:
                p1_missing.append(dict(table='transactions',row=index+1,record_id=row['record_id'],revision=row['revision'],gaps=state['gaps']))
    if p1_missing:
        limits.append(dict(code='P1_INPUT_UNAVAILABLE',analysis='p1_input',
            message='P1 chưa đủ đầu vào kênh/liên kết/phạm vi lịch sử đã khai báo; không thay lịch sử thiếu bằng 0.',
            action='Xem gaps từng giao dịch; bổ sung nguồn theo contract 1.1.0 và xuất lại manifest, không suy từ tài khoản hoặc số tiền.',
            affected_count=len(p1_missing),affected_rows=p1_missing[:20],affected_rows_truncated=len(p1_missing)>20,
            coverage_basis='source_declared_manifest_not_complete_external_books'))
    for code, analysis, affected, message, action in [
        ("DOCUMENT_BASIS_MISSING", "document_verification", missing_docs,
         "Có giao dịch chưa có chứng từ gốc đã xác minh gắn với giao dịch hoặc hóa đơn liên quan; chưa đủ căn cứ kết luận nghiệp vụ.",
         "Bổ sung và đối chiếu chứng từ đúng giao dịch/nghĩa vụ. Bản mô phỏng hoặc bản xuất không tự là chứng từ gốc đã xác minh."),
        ("BANK_HISTORY_MISSING", "bank_change_analysis", missing_bank,
         "Chưa có lịch sử tài khoản tương ứng của NCC cho một số giao dịch; chưa đánh giá được thay đổi tài khoản từ nguồn hiện có.",
         "Bổ sung bank history có thời điểm hiệu lực và thời điểm được biết; không giả lịch sử từ tài khoản hiện tại."),
        ("INVOICE_LINK_MISSING", "payment_reconciliation", missing_invoice,
         "Có khoản thanh toán chưa có liên kết phân bổ hóa đơn; chưa đối chiếu được nghĩa vụ và số đã trả cho các khoản này.",
         "Bổ sung payment_allocations và hóa đơn có nguồn; không tự gán một hóa đơn theo số tiền gần giống."),
        ("APPROVAL_BASIS_MISSING", "approval_trace", missing_approval,
         "Chưa có bản ghi phê duyệt approved gắn với một số khoản chi/lương; chưa xác nhận được dấu vết phê duyệt.",
         "Bổ sung nguồn phê duyệt phù hợp chính sách. Thiếu bản ghi không tự chứng minh khoản chi chưa được duyệt."),
    ]:
        if affected:
            limits.append(dict(code=code, analysis=analysis, message=message, action=action,
                               affected_count=len(affected), affected_rows=affected[:20],
                               affected_rows_truncated=len(affected)>20, coverage_basis="submitted_bundle_current_revisions"))
    return limits


def records_as_of(bundle, scope, as_of):
    """Select visible revisions, not features or a persistent DataSnapshot.

    Effective and observed times both constrain visibility. Late-arriving revisions
    cannot overwrite old knowledge. Simultaneous feature replay remains R1 work.
    """
    report = validate_input(bundle, scope)
    if report["status"] == "rejected":
        raise ValueError("Không thể đọc gói bị từ chối; xem ValidationReport.")
    cutoff = stamp(as_of)
    visible = {}
    for table, _, row in records(bundle):
        if stamp(row["observed_at"]) > cutoff or stamp(row["effective_at"]) > cutoff:
            continue
        identity = key(table, row)[:-1]
        old = visible.get(identity)
        if old is None or row["revision"] > old["revision"]:
            visible[identity] = row
    result = {table: [] for table, _, _ in records(bundle)}
    for identity, row in sorted(visible.items()):
        result[identity[2]].append(deepcopy(row))
    return result
