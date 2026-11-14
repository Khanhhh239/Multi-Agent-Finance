"""Run generated sources, compare native engine, and probe missing-source behavior."""
import argparse,json,re,sys,time
from html import escape
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from finance_input import AccessScope
from finance_input.json_io import loads
from sme_fraud.native_rule_node import evaluate_bundle,validate_bundle,REQUIRED
from sme_fraud.rules import RULE_NAMES,score_rules
from sme_fraud.benford import monthly_diagnostics
from sme_fraud.import_files import canonical,digest


def run(source,output):
    manifest=loads((source/'manifest.json').read_bytes())
    if manifest.get('version')!='native-rule-demo/1.0.0' or manifest.get('synthetic_only') is not True or set(manifest['rule_ids'])!=set(RULE_NAMES):raise ValueError('Expected synthetic demo manifest')
    expected_ids={c+'_'+r+'_'+p for c in ('C001','C002') for r in [x for x in RULE_NAMES if not x.startswith('D')]+['D_GROUP'] for p in ('signal','control')}
    if len(manifest['cases'])!=len(expected_ids) or {c['case_id'] for c in manifest['cases']}!=expected_ids:raise ValueError('Incomplete or duplicate scenario manifest')
    output.mkdir(parents=True,exist_ok=False);checks=[];missing=[];source_unchanged=True;started=time.monotonic()
    for item in manifest['cases']:
        name=item['source_file']
        if not re.fullmatch(r'C00[12]_(?:[A-Z][0-9]|D_GROUP)_(?:signal|control)\.source\.json',name):raise ValueError('Unexpected source filename')
        path=source/name
        if path.resolve().parent!=source or path.stat().st_size>64*1024*1024:raise ValueError('Source path or size')
        raw=path.read_bytes()
        if digest(raw)!=item['source_sha256']:raise ValueError('Source checksum changed: '+name)
        bundle=loads(raw)
        if bundle['is_simulated'] is not True or bundle['company_id']!=item['company_id'] or bundle['tenant_id']!='native-demo':raise ValueError('Synthetic demo scope mismatch')
        scope=AccessScope('native-demo',frozenset({item['company_id']}),'synthetic-review',frozenset({'data.import'}));before=digest(canonical(bundle));timer=time.monotonic()
        result=evaluate_bundle(bundle,scope);elapsed=time.monotonic()-timer
        expected=item['expected'];codes=expected.get('rule_ids',[expected.get('rule_id')])
        # Independent direct engine invocation, not a comparison with the
        # expected label or a result copied from the adapter.
        tables={n:[deepcopy(r) for r in rows if r['observed_at']<=bundle['as_of'] and (n!='transactions' or r['posted_at']<=bundle['as_of'])] for n,rows in bundle['tables'].items()}
        parity=digest(canonical(score_rules(tables)))==result['native_reference_sha256']
        if len(codes)>1:
            direct=[d for d in monthly_diagnostics(tables,'phase4') if d['cutoff_at']<=bundle['as_of']]
            parity=parity and all(canonical([d for d in direct if d['rule_id']==r['rule_id']])==canonical(r['statistics']) for r in result['rules'] if r['rule_id'].startswith('D'))
        for code in codes:
            rule=next(r for r in result['rules'] if r['rule_id']==code)
            if code.startswith('D'):
                actual=any(d.get('signal') is True for d in rule['statistics'] if d['cutoff_at']==expected['cutoff_at']);available=any(d['status']=='evaluated' for d in rule['statistics'] if d['cutoff_at']==expected['cutoff_at'])
            else:actual=rule['matched'];available=rule['available']
            checks.append(dict(case_id=item['case_id'],company_id=item['company_id'],rule_id=code,expected_signal=expected['expected_signal'],actual_signal=actual,available=available,passed=available and actual==expected['expected_signal'],native_parity=parity,source_sha256=before,seconds=round(elapsed,4)))
        (output/(item['case_id']+'.result.json')).write_bytes(canonical(result))
        source_unchanged=source_unchanged and before==digest(canonical(bundle)) and digest(path.read_bytes())==item['source_sha256']
        # Fast missing-source probe for each transaction rule; one small-source
        # probe below covers D instead of repeating a large statistical run.
        if len(codes)==1 and expected['positive']:
            changed=deepcopy(bundle);table=REQUIRED[codes[0]][-1];changed['coverage'].pop(table,None)
            blocked=next(r for r in evaluate_bundle(changed,scope)['rules'] if r['rule_id']==codes[0])
            missing.append(dict(company_id=item['company_id'],rule_id=codes[0],removed_coverage=table,passed=blocked['status']=='unavailable' and blocked['matched'] is None and blocked['score'] is None))
        print(json.dumps(dict(case=item['case_id'],passed=all(c['passed'] for c in checks[-len(codes):]),seconds=round(elapsed,2))),flush=True)
    from sme_fraud.native_rule_demo import scenario
    for company in ('C001','C002'):
        small,_=scenario('B1',False,company);small['coverage'].pop('transactions');scope=AccessScope('native-demo',frozenset({company}),'synthetic-review',frozenset({'data.import'}));blocked=evaluate_bundle(small,scope)
        for r in blocked['rules']:
            if r['rule_id'].startswith('D'):missing.append(dict(company_id=company,rule_id=r['rule_id'],removed_coverage='transactions',passed=r['matched'] is None and any(g['reason']=='source_coverage_missing' for g in r['gaps'])))
    complete=len(checks)==140 and len(missing)==70 and {c['rule_id'] for c in checks}==set(RULE_NAMES)
    result=dict(status='passed' if complete and all(c['passed'] and c['native_parity'] is True for c in checks) and all(c['passed'] for c in missing) and source_unchanged else 'failed',
        rules_covered=len({c['rule_id'] for c in checks}),positive_control_checks=len(checks),missing_source_checks=len(missing),source_packages=len(manifest['cases']),native_parity_checks=sum(c['native_parity'] is not None for c in checks),source_unchanged=source_unchanged,
        native_parity_source_packages=len(manifest['cases']),checks=checks,missing_source=missing,seconds=round(time.monotonic()-started,3),is_simulated=True,model_fit_performed=False,new_he_execution=False,portal_changed=False,accuracy=None)
    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_reports(result,output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('checks','missing_source')},ensure_ascii=True));return result['status']=='passed'


def write_reports(result,output):
    checks=result['checks'];missing=result['missing_source'];html_rows=[]
    lines=['# Kiểm chứng 35 luật tại node doanh nghiệp','',f"Trạng thái: **{result['status']}**. {len(checks)} đối chiếu ca trúng/đối chứng, {len(missing)} kiểm tra thiếu nguồn. Dữ liệu mô phỏng; không phải độ chính xác gian lận.",'','| Luật | C001: trúng / đối chứng / thiếu nguồn | C002: trúng / đối chứng / thiếu nguồn |','|---|---|---|']
    for code in RULE_NAMES:
        cells=[]
        for company in ('C001','C002'):
            tests=[c for c in checks if c['rule_id']==code and c['company_id']==company];miss=[c for c in missing if c['rule_id']==code and c['company_id']==company]
            flags=[len([c for c in tests if c['expected_signal']==positive])==1 and all(c['passed'] for c in tests if c['expected_signal']==positive) for positive in (True,False)]
            flags.append(bool(miss) and all(c['passed'] for c in miss))
            cells.append(' / '.join('Đạt' if flag else 'Cần sửa' for flag in flags))
        lines.append('| '+code+' | '+' | '.join(cells)+' |')
        html_rows.append('<tr><th scope="row">'+escape(code)+'</th><td>'+escape(RULE_NAMES[code])+'</td>'+''.join('<td>'+escape(c)+'</td>' for c in cells)+'</tr>')
    lines+=['','Nhóm D chấm theo tập/cutoff, F4 theo hóa đơn phải thu, E3/B5/E4 theo chất lượng master. E4 dùng alias B5 của engine, không cộng điểm lần hai. Chưa tính điểm tổng hoặc đưa kết quả vào queue.','',
        'Gói nguồn native này chạy tại DN. Hợp đồng snapshot 1.1.0 và phần HE Portal chưa được mở rộng bởi phép thử này. File nguồn/expected tách nhau; manifest ràng buộc checksum; không dùng expected để tạo feature hoặc quyết định luật.','']
    (output/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    page='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kiểm chứng 35 luật Agent2</title>
<style>body{font:17px/1.6 system-ui,sans-serif;color:#193348;background:#f4f7fa;margin:0}main{max-width:1200px;margin:32px auto;padding:28px;background:white;border-radius:16px}h1{font-size:30px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d5dfe6;padding:12px;text-align:left}thead{background:#eaf3f0}.note{padding:16px;background:#fff5db;border-radius:10px}.scroll{overflow:auto}a{color:#05665d}small{color:#466072}</style>
<main><h1>Kiểm chứng 35 luật tại node doanh nghiệp</h1><p><strong>Dữ liệu mô phỏng · Kiểm thử kỹ thuật</strong></p>
<p>Trạng thái: <strong>STATUS</strong>. Đã đối chiếu 35 luật trên C001/C002: 140 ca trúng và đối chứng, 70 ca thiếu nguồn. 120 gói dữ liệu nguồn được so với engine giữ lại.</p>
<p>Trong bảng, ba mục lần lượt là: <strong>ca cần cảnh báo / ca đối chứng / thiếu nguồn trả chưa khả dụng</strong>. “Đạt” nghĩa là đúng kết quả kỳ vọng của ca thử.</p>
<p class="note">Kết quả này chưa chứng minh độ chính xác phát hiện gian lận trên doanh nghiệp thật. Gói nguồn chạy tại node doanh nghiệp, chưa đưa 35 luật lên HE hoặc Portal. Không tải gói native này vào màn hình nhập snapshot 1.1.0.</p>
<div class="scroll"><table><thead><tr><th>Luật</th><th>Nội dung</th><th>C001</th><th>C002</th></tr></thead><tbody>ROWS</tbody></table></div>
<p>Nhóm D là chẩn đoán theo tập dữ liệu; F4 theo khoản phải thu. E3/B5/E4 là kiểm tra master. E4 dùng alias B5, không cộng điểm lần hai. Không cộng điểm tổng hoặc tự đưa vào hàng đợi.</p>
<p><a href="report.json">Kết quả chi tiết JSON</a> · <a href="REPORT.md">Báo cáo Markdown</a></p><small>Nguồn và kết quả kỳ vọng được giữ riêng. Thiếu nguồn không được xem là không vi phạm.</small></main></html>'''
    (output/'REPORT.html').write_text(page.replace('STATUS',escape(result['status'])).replace('ROWS',''.join(html_rows)),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();raise SystemExit(0 if run(a.input_dir.resolve(),a.output_dir.resolve()) else 1)
