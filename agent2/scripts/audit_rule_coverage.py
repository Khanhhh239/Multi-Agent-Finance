"""Read-only audit of rule catalog, canonical source gaps, evaluators and HE wiring.

Replays public synthetic C001/C002 sources locally. No fit, worker requests,
Portal authentication, live DB writes, or operational policy changes.
"""
import argparse,ast,hashlib,json,os,sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parent
sys.path.insert(0,str(ROOT))
from finance_input import schema
from sme_fraud.imports import DEFINITIONS,validate_input
from sme_fraud.rule_sources import source_catalog,_resolve
from sme_fraud.rule_evaluation import SUPPORTED,_evaluate
from sme_fraud.rules import RULE_NAMES,rule_coverage
from sme_fraud.snapshot_features import build_feature_rows
from experiments.he4.p1_demo import scope

LABELS={
 'transactions':'Giao dịch','transaction_history':'Lịch sử giao dịch',
 'vendor':'NCC liên quan','vendors':'Danh mục NCC','employee':'Nhân viên liên quan',
 'creator':'Người lập','employees':'Danh mục nhân viên','companies':'Doanh nghiệp',
 'approvals':'Phê duyệt','approval_authorities':'Ma trận thẩm quyền',
 'approval_authority_coverage':'Phạm vi lịch sử quyền','invoices':'Hóa đơn',
 'payment_allocations':'Phân bổ thanh toán','supporting_documents':'Chứng từ',
 'payment_requests':'Yêu cầu chi/liên kết PO','supplier_payment_agreements':'Thỏa thuận thanh toán',
 'entity_links':'Lịch sử liên kết đối tượng','recurring_payments':'Lịch trả định kỳ',
 'journal_documents':'Chứng từ sổ cái','journal_lines':'Dòng sổ cái',
 'operating_schedules':'Lịch vận hành','tax_risk_history':'Lịch sử rủi ro nguồn thuế',
 'vendor_payment_schedules':'Lịch trả NCC theo mùa/kỳ','vendor_bank_history':'Lịch sử tài khoản NCC',
 'bank_account_changes':'Thay đổi TK/callback/người duyệt','calendar':'Lịch ngày nghỉ',
 'leave_periods':'Kỳ nghỉ phép','system_actions':'Log thao tác','leave_activity_authorizations':'Ủy quyền làm việc khi nghỉ',
 'payroll_entitlements':'Quyền hưởng lương','attendance':'Chấm công/bằng chứng làm việc',
 'employment_events':'Sự kiện nhân sự','payroll_settlements':'Quyết toán/truy lĩnh lương',
 'journal_audit_log':'Log nguồn bút toán','closing_periods':'Lịch khóa sổ','materiality_policies':'Chính sách trọng yếu',
 'workflow_policies':'Quy trình chuẩn','override_events':'Log ghi đè quy trình',
 'document_series':'Dải số chứng từ','document_register':'Sổ đăng ký chứng từ','document_cancellations':'Sổ hủy chứng từ',
 'receivable_invoices':'Hóa đơn phải thu','receipt_allocations':'Phân bổ thu tiền',
 'receipt_coverage':'Phạm vi lịch sử thu','receivable_explanations':'Giải trình công nợ',
 'p1_invoices':'Hóa đơn gốc/điều chỉnh','p1_allocations':'Phân bổ hiện tại/trước đó/đồng thời',
 'p1_transactions':'Giao dịch thanh toán/điều chỉnh','p1_vendors':'NCC của nghĩa vụ',
 'payment_history_coverage':'Khai báo phạm vi lịch sử/manifest','cash_limit_policies':'Chính sách chi tiền mặt',
 'advances':'Sổ tạm ứng','advance_events':'Sự kiện giải ngân/hoàn ứng/xóa nợ',
}

NEXT={
 'A1':'Nối yêu cầu chi–PO–hóa đơn–hợp đồng và quyền theo thời điểm; đối chiếu engine cho khoản trả nhiều đợt hợp lệ và nhóm đồng thời.',
 'A2':'Như A1, thêm lịch sử toàn nghĩa vụ và cửa sổ 30 ngày; không dùng phần lịch sử thiếu như đã trả bằng 0.',
 'A3':'Như A1, thêm phiên bản liên kết/cụm và rút liên kết; graph thành phần chưa thay thế luật chia nhỏ qua cụm.',
 'A4':'Nối lịch định kỳ và quyền/phê duyệt; kiểm ngoại lệ lương/chi định kỳ, giữ chính sách kỳ của engine.',
 'A5':'Nối lịch sử sổ cái/lịch hoạt động/chi định kỳ đúng thời điểm; đối chiếu baseline và tiêu chí làm tròn. RobustZ riêng chưa phải A5.',
 'A6':'Bổ sung phần giá trị gốc/thuế của hóa đơn và liên kết phân bổ; đối chiếu làm tròn và điều chỉnh có dấu.',
 'B1':'Nối định danh ngân hàng/CCCD và khai báo bên liên quan; phân biệt thiếu mã ngân hàng với trùng đã xác định. Graph chưa là B1.',
 'B2':'Nối lịch sử quan hệ và thuộc tính liên hệ; không gom chỉ từ địa chỉ đơn lẻ hoặc dùng cạnh đến muộn cho quá khứ.',
 'B3':'Bổ sung ngày thành lập và đủ lịch sử xác định lần giao dịch đầu; làm rõ phạm vi mua/giao dịch kinh tế/thanh toán theo chính sách.',
 'B4':'Nối feed thuế có nguồn, ngày hiệu lực/công bố/được biết và checksum; không suy trạng thái hiện tại cho hóa đơn quá khứ.',
 'B5':'Nối thông tin master và khai báo quan hệ; tách phát hiện chất lượng master, không tự cộng điểm giao dịch hai lần với E4.',
 'B6':'Nối lịch sử và lịch trả theo mùa/kỳ; phân biệt ngủ đông với khoản chi định kỳ được duyệt.',
 'B7':'Nối sự kiện đổi tài khoản, callback và phê duyệt đúng thời điểm; lịch sử TK hiện có chưa thay toàn bộ sự kiện xác minh.',
 'C1':'Bổ sung thời điểm lập/duyệt và lịch vận hành/nghỉ; không lấy observed_at/effective_at thay thời gian thao tác.',
 'C2':'Nối ma trận quyền/ủy quyền cùng coverage; hạn mức trên nhân viên/giao dịch chưa thay quyền được duyệt.',
 'C3':'Nối hai mốc lập–duyệt và cấp quyền thực tế; đối chiếu trường hợp duyệt tự động/được phép theo chính sách.',
 'C4':'Nối khoảng nghỉ phép, log thao tác và ủy quyền ngoại lệ; tổng ngày nghỉ theo tháng chưa đủ.',
 'D1':'Nối ngày ghi sổ/cờ bút toán tài chính và lịch sử đủ điều kiện; đánh giá theo nhóm, không coi p-value là xác suất gian lận.',
 'D2':'Như D1, giữ tập đủ điều kiện cho chữ số thứ hai và mẫu tối thiểu theo engine.',
 'D3':'Như D1, thêm hạn mức/phân đoạn người lập; tín hiệu thống kê chưa chứng minh ý đồ.',
 'D4':'Nối lịch sử đuôi số kỳ trước, không giả phân bố đều; kiểm sàng lọc số tiền đủ điều kiện.',
 'D5':'Nối mẫu Benford đủ điều kiện, đối chiếu MAD trên nhóm; RobustZ hai biến không thay MAD chữ số đầu.',
 'D6':'Như D1, thêm phòng ban/dự án và đủ mẫu từng phân đoạn; không gộp doanh nghiệp hoặc nhóm thiếu dữ liệu.',
 'E1':'Nối kỳ lương/chấm công/quyền hưởng và bằng chứng thay thế; thiếu chấm công chưa tự là lương sai.',
 'E2':'Nối nghỉ việc/tái tuyển dụng, kỳ công và hồ sơ quyết toán/truy lĩnh; không kết luận chỉ từ ngày chuyển tiền.',
 'E3':'Giữ evaluator tên hiện có; chuẩn bị thiết kế so chuỗi HE nếu mở rộng. Điểm chất lượng master bằng 0 vẫn có thể matched=true.',
 'E4':'Như B5, bổ sung thuộc tính định danh/khai báo quan hệ và tách chất lượng master; không coi graph hiện tại là E4 đã hoàn thành.',
 'F1':'Nối log thủ công, lịch khóa sổ và mức trọng yếu được duyệt; loại suy diễn từ nhãn adjustment/cuối tháng.',
 'F2':'Nối quy trình bắt buộc, log override và quyền ngoại lệ; không suy ghi đè chỉ từ người duyệt.',
 'F3':'Nối dải số, sổ đăng ký và sổ hủy đầy đủ; ID giao dịch ngẫu nhiên chưa phải số chứng từ.',
 'F4':'Nối hóa đơn phải thu, thu tiền/phân bổ, coverage và giải trình; không suy chưa thu tiền chỉ từ số dư/tài khoản.',
 'P1':'Giữ adapter đã có; cần đủ kênh/liên kết/coverage và trong miền HE. Kiểm thêm nguồn thật, không tự cắt lịch sử cho vừa giới hạn.',
 'P2':'Nối VAT và chính sách tiền mặt theo hiệu lực; kiểm chứng phân loại bằng chứng, không tự kết luận xử lý thuế.',
 'T1':'Nối sổ tạm ứng và sự kiện có dấu, hạn gốc/gia hạn; đối chiếu dư nợ tại cutoff, không suy từ chi tiền đơn lẻ.',
 'T2':'Như T1, thêm sự kiện xóa nợ và hồ sơ/ủy quyền; thiếu hồ sơ cần trả thiếu nguồn, không tự khẳng định gian lận.',
}


def he_rules():
    path=ROOT/'experiments/he4/snapshot_adapter.py';tree=ast.parse(path.read_text('utf-8'))
    entry=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_snapshot')
    calls={n.func.id for n in ast.walk(entry) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert 'p1_plan' in calls,'Review changed HE rule routing before updating this audit'
    plan=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='p1_plan')
    ids={n.value.value for n in ast.walk(plan) if isinstance(n,ast.keyword) and n.arg=='rule_id' and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)}
    assert ids=={'P1'},'Review changed HE coverage before updating this audit'
    return ids


def binding_details(binding,contract):
    b=dict(binding);b['fields']=list(dict.fromkeys(b['fields']));b['contract_missing_fields']=list(dict.fromkeys(b['contract_missing_fields']))
    b['table_in_import_profile']=b['table'] in DEFINITIONS and DEFINITIONS[b['table']] in schema(contract)['$defs']
    b['source_label']=LABELS.get(b['role'],b['role'])
    return b


def demo_replay(company):
    folder=REPO/'Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113'
    manifest=json.loads((folder/'evidence-manifest.json').read_text('utf-8'));hashes={f['path']:f['sha256'] for f in manifest['files']}
    blobs={}
    for kind in ('source','result'):
        name=company+'-'+kind+'.json';raw=(folder/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==hashes[name],name;blobs[kind]=json.loads(raw)
    data=blobs['source'];as_of=blobs['result']['as_of'];authority=scope(company)
    assert not validate_input(data,authority)['errors']
    assert all(r['source']['is_simulated'] for table,records in data.items() if isinstance(records,list) for r in records)
    frame=build_feature_rows(data,authority,as_of);private,public=_resolve(data,frame,authority)
    per_rule={code:dict(source_statuses=Counter(),result_statuses=Counter(),gap_codes=Counter(),missing_dependencies=set()) for code in RULE_NAMES}
    for meta in frame['rows']:
        key=meta['record_id'],meta['revision'];evaluated=_evaluate(private[key],public[key],authority,meta)
        for source,result in zip(public[key]['rules'],evaluated['rules']):
            assert source['rule_id']==result['rule_id'];entry=per_rule[source['rule_id']]
            entry['source_statuses'][source['source_status']]+=1;entry['result_statuses'][result['status']]+=1
            for gap in source['gaps']:
                entry['gap_codes'][gap['code']]+=1;entry['missing_dependencies'].add((gap['table'],gap['field'],gap['code']))
    for item in per_rule.values():item['missing_dependencies']=[dict(table=t,field=f,reason=c) for t,f,c in sorted(item['missing_dependencies'])]
    return dict(company_id=company,contract_version=data['contract_version'],as_of=as_of,row_count=len(frame['rows']),
        source_file=company+'-source.json',source_file_sha256=hashes[company+'-source.json'],
        scope='public synthetic archived source, local canonical replay only; not live data or new HE execution',rules=per_rule)


def gap_text(bindings):
    tables=[];fields={}
    for b in bindings:
        if not b['table_in_import_profile']:
            if b['table'] not in tables:tables.append(b['table'])
        elif b['contract_missing_fields']:fields.setdefault(b['table'],set()).update(b['contract_missing_fields'])
    parts=[]
    if tables:parts.append('Bảng chưa nối: '+', '.join(LABELS.get(t,t) for t in tables))
    if fields:parts.append('Trường chưa có: '+', '.join('`'+t+'.'+f+'`' for t,fs in fields.items() for f in sorted(fs)))
    return '; '.join(parts) or 'Không thiếu trường khai báo ở mức schema; vẫn phải kiểm dữ liệu, liên kết và lịch sử thực tế.'


def build(audit_date):
    assert set(NEXT)==set(RULE_NAMES) and len(RULE_NAMES)==35
    legacy={r['rule_id']:r for r in rule_coverage()};he=he_rules();rows=[]
    for rule in source_catalog('1.1.0'):
        code=rule['rule_id'];bindings=[binding_details(b,'1.1.0') for b in rule['bindings']]
        rows.append(dict(rule_id=code,name=rule['name'],group=code[0],applicable_kinds=rule['applicable_kinds'],
            legacy_catalog_present=True,legacy_static_coverage=legacy[code],legacy_static_coverage_is_runtime_readiness=False,
            source_map_declared=True,contract_version='1.1.0',bindings=bindings,contract_schema_has_gaps=any(not b['table_in_import_profile'] or b['contract_missing_fields'] for b in bindings),
            snapshot_evaluator_supported=code in SUPPORTED,he_rule_routed=code in he,
            related_he_component='graph, not equivalent to this rule' if code in {'A3','B1','B2','B5','E4'} else 'RobustZ2, not equivalent to this rule' if code=='A5' or code.startswith('D') else None,
            gap_summary=gap_text(bindings),next_work=NEXT[code]))
    sources=['agent2/sme_fraud/rules.py','agent2/sme_fraud/rule_sources.py','agent2/sme_fraud/rule_evaluation.py','agent2/sme_fraud/imports.py','agent2/sme_fraud/snapshot_features.py','agent2/sme_fraud/p1_inputs.py','agent2/sme_fraud/p1_evaluation.py','agent2/sme_fraud/authority_policy.py','agent2/sme_fraud/evidence_policy.py','agent2/sme_fraud/exception_validation.py','agent2/sme_fraud/tax_risk.py','agent2/experiments/he4/snapshot_adapter.py','agent2/experiments/he4/inputs.py','shared/finance_input/src/finance_input/input.schema.json','shared/finance_input/src/finance_input/validation.py',str(Path(__file__).relative_to(REPO)).replace('\\','/')]
    return dict(version='rule-coverage-audit/1.0.0',audit_date=audit_date,contract_version='1.1.0',read_only=True,
        summary=dict(catalog_rules=len(rows),declared_source_maps=len(rows),snapshot_evaluator_rules=[r['rule_id'] for r in rows if r['snapshot_evaluator_supported']],
            missing_snapshot_evaluators=sum(not r['snapshot_evaluator_supported'] for r in rows),he_rule_ids=sorted(he),
            rules_with_contract_schema_gaps=sum(r['contract_schema_has_gaps'] for r in rows)),
        source_fingerprints=[dict(path=n,sha256=hashlib.sha256((REPO/n).read_bytes()).hexdigest()) for n in sources],rules=rows,
        demos=[demo_replay(c) for c in ('C001','C002')],live_db_accessed=False,portal_changed=False,model_fit_performed=False,new_he_execution=False)


def markdown(value,folder):
    summary=value['summary']
    lines=['# Trạng thái 35 luật Agent2 — '+value['audit_date'],'',
        '**Phạm vi: code hiện tại, hợp đồng nhập 1.1.0 và luồng snapshot/HE mới. Đây là kiểm kê, không phải nghiệm thu nghiệp vụ hoặc sửa luật.**','',
        '| Lớp | Trạng thái |','|---|---|',
        '| Danh mục/lõi cũ | Có 35 mã luật; mức sẵn sàng còn tùy nguồn và policy, không mặc định cả 35 đã hoàn thiện. |',
        '| Khai báo nguồn (`rule_sources`) | Có bản đồ nguồn cho đủ 35 luật; khai báo chưa có nghĩa nguồn đã nhập được hoặc luật đã chạy. |',
        '| Evaluator snapshot mới | Có P1 và E3 khi đủ nguồn; 33 luật chưa có evaluator đã nối. |',
        '| HE của nhánh luật trên Portal | Mới P1 trong miền đã kiểm chứng; 34 luật chưa nối HE. |',
        '| Schema/import 1.1.0 | '+str(summary['rules_with_contract_schema_gaps'])+' luật còn ít nhất một bảng/trường phụ thuộc chưa được nhận theo bản đồ nguồn hiện tại. |','',
        '“Bảng/trường chưa nối” dưới đây nói về hợp đồng nhập/adapter hiện tại, **không kết luận doanh nghiệp không có nguồn đó**. Có thể cần bổ sung bảng hoặc ánh xạ có kiểm chứng từ nguồn đã tồn tại. Không tự lấy `effective_at`/`observed_at` thay ngày ghi sổ/lập/duyệt hoặc tự điền số 0.','',
        'Nguồn được liệt kê theo khai báo trong code hiện tại. Một luật có thể có các nhánh dùng nguồn khác nhau; khi nối evaluator cần tách phần đủ nguồn và phần thiếu, không mặc định mọi trường đều cần đồng thời cho mọi nhánh. Ví dụ ngân hàng và CCCD của B1 cần được đánh giá theo căn cứ tương ứng.','',
        '“Adapter” trong bảng là **evaluator trên snapshot mới**. Phần source map đã có khai báo cho cả 35. Cột HE chỉ ghi luật đã nối; graph/RobustZ chạy riêng chưa đồng nghĩa luật B/A/D tương ứng đã hoàn thành.','',
        '| Luật | Nội dung | Nguồn cần | Thiếu trong đường nhập 1.1.0 | Evaluator snapshot | HE luật |',
        '|---|---|---|---|---|---|']
    for r in value['rules']:
        names=list(dict.fromkeys(b['source_label'] for b in r['bindings']))
        lines.append('| '+r['rule_id']+' | '+r['name']+' | '+'; '.join(names)+' | '+r['gap_summary']+' | '+('Có, phụ thuộc nguồn' if r['snapshot_evaluator_supported'] else 'Chưa')+' | '+('Có P1, giới hạn' if r['he_rule_routed'] else 'Chưa')+' |')
    lines+=['','## Việc cần làm cho từng luật','', '| Luật | Việc còn thiếu để đưa vào luồng mới |','|---|---|']
    for r in value['rules']:lines.append('| '+r['rule_id']+' | '+r['next_work']+' |')
    lines+=['','## Đối chiếu trên hai bộ mô phỏng đã lưu','',
        'Chạy lại resolver/evaluator local trên nguồn C001/C002 công khai đã khóa checksum, mỗi DN 8 giao dịch. Không gọi worker, không fit, không truy cập DB hoặc phiếu live. Mốc `as_of` lấy từ run đã lưu. Đây chưa là kiểm thử đủ các họ rủi ro: bộ này chủ yếu phục vụ P1, không có ca lương/nghỉ phép/override đầy đủ.','',
        '| Luật | C001: đã đánh giá / thiếu nguồn hoặc evaluator / không áp dụng | C002: đã đánh giá / thiếu nguồn hoặc evaluator / không áp dụng |','|---|---|---|']
    for r in value['rules']:
        cells=[]
        for demo in value['demos']:
            c=demo['rules'][r['rule_id']]['result_statuses'];cells.append(f"{c.get('evaluated_hit',0)+c.get('evaluated_no_hit',0)} / {c.get('unavailable',0)} / {c.get('not_applicable',0)}")
        lines.append('| '+r['rule_id']+' | '+' | '.join(cells)+' |')
    lines+=['','Các cột trên là số giao dịch, không phải số vụ gian lận. Với P1, nhóm đồng thời có kết quả riêng ngoài kết quả từng giao dịch. `not_applicable` không chứng minh luật đã kiểm thử đủ; `unavailable` không phải không vi phạm. JSON kèm theo tách `source_statuses`, `result_statuses` và nguyên nhân thiếu cụ thể.','',
        'E3 dùng SequenceMatcher trên tên chuẩn hóa, chưa có so chuỗi HE; vai trò là chất lượng master nên điểm giao dịch bằng 0 vẫn có thể có tín hiệu. B5/E4 cũng cần giữ riêng vai trò chất lượng master theo policy. Nhóm D là chẩn đoán thống kê theo nhóm, không mặc định điểm gian lận riêng cho từng giao dịch.','',
        'P1 HE giới hạn tối đa 4 source amounts trong mỗi tổng, đầu vào signed64/tính signed128; không tự cắt lịch sử để vừa miền. Graph tối đa 4 đối tượng, chỉ thuộc tính master theo thời điểm, chưa lịch sử cạnh đầy đủ. RobustZ hai biến là nhánh thống kê riêng. Các thành phần này chưa thay thế 35 luật.','',
        '## Căn cứ và cách tái lập','',
        '- [Danh mục và mô tả mức phủ lõi cũ](../agent2/sme_fraud/rules.py). Metadata `rule_coverage()` là mô tả tĩnh; `score_rules()` còn điều chỉnh theo nguồn/policy, không lấy metadata tĩnh làm chứng nhận sẵn sàng.',
        '- [Bản đồ nguồn](../agent2/sme_fraud/rule_sources.py), [hợp đồng nhập](../agent2/sme_fraud/imports.py), [schema 1.1.0](../shared/finance_input/src/finance_input/input.schema.json).',
        '- [Evaluator snapshot](../agent2/sme_fraud/rule_evaluation.py): allowlist `SUPPORTED` hiện P1/E3; các luật khác trả thiếu nguồn hoặc thiếu evaluator.',
        '- [Adapter snapshot → HE](../agent2/experiments/he4/snapshot_adapter.py): nhánh rules gọi `p1_plan`; graph/statistics là nhánh riêng.',
        '- [JSON chi tiết](rule_coverage_status_20261114.json): field/role/table, gaps theo từng luật, fingerprint code và kết quả replay.',
        '- [Bằng chứng P1 native trên Portal trước đây](../Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113/REPORT.md); audit này không chạy HE mới.','',
        '```powershell',
        '& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/audit_rule_coverage.py --output-dir .runtime/rule-coverage-new --audit-date 2026-11-14',
        '```','',
        'Dùng thư mục đầu ra mới. Ngày trên là ngày lập bảng, không dùng thay `as_of` nghiệp vụ. Audit chỉ xuất báo cáo; không thay schema, detector, model, quyền, hàng đợi hoặc Portal.','']
    prefix=Path(os.path.relpath(REPO,folder)).as_posix()
    return '\n'.join(lines).replace('(../agent2/', '('+prefix+'/agent2/').replace('(../shared/', '('+prefix+'/shared/').replace('(../Agent2_Spec_v2_1/', '('+prefix+'/Agent2_Spec_v2_1/')


def run(output,audit_date):
    value=build(audit_date)
    assert value['summary']['catalog_rules']==35 and len({r['rule_id'] for r in value['rules']})==35
    assert set(value['summary']['snapshot_evaluator_rules'])=={'E3','P1'} and value['summary']['he_rule_ids']==['P1']
    for demo in value['demos']:
        assert all(sum(r['result_statuses'].values())==demo['row_count'] for r in demo['rules'].values())
    output.mkdir(parents=True,exist_ok=False)
    (output/'rule_coverage_status_20261114.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'rule_coverage_status_20261114.md').write_text(markdown(value,output),encoding='utf-8')
    print(json.dumps(dict(status='passed',summary=value['summary'],demo_companies=[d['company_id'] for d in value['demos']],read_only=True),ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--audit-date',default='2026-11-14');args=parser.parse_args();run(args.output_dir.resolve(),args.audit_date)
