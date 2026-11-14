"""Business reconciliation through the real UI; frozen hand ledger, not engine output.

All source records are synthetic. Uses temporary Portal sessions and SQLite only.
Expected money/status tables below are written independently before running HTTP.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from test_portal_auth import PortalHarness
from portal import server as portal

FACTS=('invoice_gross_vnd','prior_paid_vnd','current_allocated_vnd','cumulative_paid_vnd','excess_vnd')
# VND. Frozen ledger authored from invoice I001 (10m) and the four allocations.
HAND={
    'OLD':dict(amount=4_000_000,prior=0,current=4_000_000,total=4_000_000,excess=0,status='no_signal',group=False),
    'A':dict(amount=4_000_000,prior=4_000_000,current=4_000_000,total=8_000_000,excess=0,status='needs_review',group=True),
    'B':dict(amount=4_000_000,prior=4_000_000,current=4_000_000,total=8_000_000,excess=0,status='needs_review',group=True),
    'OVER':dict(amount=1_000_000,prior=12_000_000,current=1_000_000,total=13_000_000,excess=3_000_000,status='needs_review',group=False),
    'MISSING':dict(amount=2_000_000,prior=None,current=None,total=None,excess=None,status='unavailable',group=False),
}
GROUP=dict(prior_paid_vnd=4_000_000,group_allocated_vnd=8_000_000,cumulative_paid_vnd=12_000_000,invoice_gross_vnd=10_000_000,excess_vnd=2_000_000)


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def first_payment_probe(data):
    """One payment, no near-name peer; isolates the prior-payment policy condition."""
    from sme_fraud.p1_inputs import export_manifest
    v=deepcopy(data);v['transactions']=v['transactions'][:1];tx=v['transactions'][0]
    tx.update(record_id='FIRST_OVER',amount_vnd=11_000_000,description='Mô phỏng: khoản đầu 11 triệu trên hóa đơn 10 triệu')
    tx['source']['record_id']='FIRST_OVER'
    v['payment_allocations']=v['payment_allocations'][:1];allocation=v['payment_allocations'][0]
    allocation.update(record_id='A_FIRST_OVER',amount_vnd=11_000_000,transaction_ref=dict(record_id='FIRST_OVER',revision=1));allocation['source']['record_id']='A_FIRST_OVER'
    v['vendors']=v['vendors'][:1];v['payment_history_coverage']=v['payment_history_coverage'][:1]
    claim=v['payment_history_coverage'][0];claim['manifest']=export_manifest(v,claim)
    return v


def run(output):
    from playwright.sync_api import sync_playwright,expect
    if output.exists() and any(output.iterdir()):raise ValueError('Use a new empty output directory; do not overwrite review evidence.')
    output.mkdir(parents=True,exist_ok=True);checks=[];findings=[];browser_errors=[]
    source=json.loads((ROOT/'sme_fraud/web/import-demo.json').read_text('utf-8'))
    write(output/'source.json',source);write(output/'hand_expectations.json',dict(rows=HAND,group=GROUP,invoice_id='I001',invoice_vnd=10_000_000,transactions_total_vnd=15_000_000,allocated_total_vnd=13_000_000,unlinked_vnd=2_000_000,independent_of_engine=True))
    def check(name,condition,detail=None):
        checks.append(dict(check=name,passed=bool(condition),detail=detail))
        if not condition:raise AssertionError(name+': '+str(detail))
    # Independent source crossfoot: no score/evaluator or feature builder is called here.
    txs={r['record_id']:r for r in source['transactions']};allocations=source['payment_allocations']
    check('frozen input IDs and transaction amounts',set(txs)==set(HAND) and all(txs[k]['amount_vnd']==v['amount'] for k,v in HAND.items()))
    check('invoice face value',source['invoices'][0]['record_id']=='I001' and source['invoices'][0]['amount_vnd']==10_000_000)
    check('15m transactions = 13m allocated + 2m unlinked',sum(r['amount_vnd'] for r in txs.values())==15_000_000 and sum(r['amount_vnd'] for r in allocations)==13_000_000 and not any(r['transaction_ref']['record_id']=='MISSING' for r in allocations))
    check('missing channel is absent, not fabricated', 'payment_channel' not in txs['MISSING'])
    check('source scope is only simulation',all(r['source']['is_simulated'] for rows in source.values() if isinstance(rows,list) for r in rows))
    with PortalHarness() as h, ExitStack() as stack:
        # Only liveness labels of other agent pages are stubbed. Auth/import/analysis remain real HTTP.
        def status(aid):return dict(id=aid,number=int(aid[-1]),name=portal.AGENTS[aid]['name'],summary='Mô phỏng rà nghiệp vụ',state='running' if aid=='agent2' else 'stopped',owned=False,port=h.agent.server_port if aid=='agent2' else 1,url='/agent2/' if aid=='agent2' else '/',root='isolated-business-review',log='/api/agents/'+aid+'/log',exit_code=None)
        stack.enter_context(patch.object(portal,'agent_state',side_effect=status))
        portal.write_json(portal.COMPANY_FILE,dict(portal.COMPANY_FIELDS,code='C001',legal_name='Doanh nghiệp mô phỏng C001'))
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);context=browser.new_context(viewport=dict(width=1440,height=1000));page=context.new_page();page.on('pageerror',lambda error:browser_errors.append(str(error)))
            page.goto(h.portal_url+'/#data');page.locator('#gate-password').fill('Synthetic-Business-Review-Only!');page.locator('#gate-confirm-field input').fill('Synthetic-Business-Review-Only!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible()
            page.evaluate('location.hash="agent2"');frame=page.frame_locator('#agent-frame');expect(frame.locator('#identity')).to_be_visible();frame.locator('#company').select_option('C001')
            def path(part):return '/agent2/api/v1/companies/C001/'+part
            def upload_save(data,stem):
                if frame.locator('#analysis-panel').is_visible():frame.locator('#new-import').click()
                raw=json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
                frame.locator('#file').set_input_files(dict(name=stem+'.json',mimeType='application/json',buffer=raw))
                with page.expect_response(lambda r:'/imports/' in r.url and r.url.endswith('/preview')) as response:frame.locator('#validate').click()
                report=response.value.json();write(output/(stem+'-preview.json'),report);check(stem+': preview accepted with disclosed limits',report['status']=='accepted_with_warnings')
                expect(frame.locator('#limits')).to_be_visible();expect(frame.locator('#limits')).to_contain_text('Chứng từ gốc');expect(frame.locator('#save')).to_be_disabled()
                frame.locator('#limits details').first.locator('summary').click()
                page.screenshot(path=str(output/(stem+'-preview.png')),full_page=True)
                frame.locator('#ack').check()
                with page.expect_response(lambda r:'/imports/' in r.url and r.url.endswith('/commit')) as response:frame.locator('#save').click()
                receipt=response.value.json();write(output/(stem+'-receipt.json'),receipt);snapshot=receipt['snapshot'];expect(frame.locator('#analysis-panel')).to_be_visible()
                # Fetch the exact committed data using the same browser session, without returning its credential.
                result=page.evaluate('''async path=>{const r=await fetch(path,{headers:{'X-Platform':'1','X-Session':sessionStorage.getItem('kt-session')}});return {status:r.status,text:await r.text()};}''',path('snapshots/'+snapshot['snapshot_id']+'/data'))
                check(stem+': saved source is exact semantic input',result['status']==200 and json.loads(result['text'])==data)
                check(stem+': committed checksum verified',hashlib.sha256(result['text'].encode()).hexdigest()==snapshot['data_checksum'])
                (output/(stem+'-snapshot-data.json')).write_text(result['text'],encoding='utf-8')
                return snapshot,report
            def analyze(at,stem):
                frame.locator('#as-of').fill(at)
                with page.expect_response(lambda r:r.url.endswith('/analyze')) as response:frame.locator('#analyze').click()
                check(stem+': analysis HTTP 200',response.value.status==200)
                result=response.value.json();write(output/(stem+'.json'),result);expect(frame.locator('#results')).to_be_visible();return result
            def inspect_full_page(stem):
                # A whole Portal screenshot clips the iframe. Inspect the same saved
                # snapshot in the actual separate-tab UI to see the entire ledger.
                with page.expect_popup() as opened:page.locator('#agent-newtab').click()
                tab=opened.value;tab.on('pageerror',lambda error:browser_errors.append(str(error)))
                expect(tab.locator('#analysis-panel')).to_be_visible()
                tab.locator('#as-of').fill('2026-10-30T09:00:00')
                with tab.expect_response(lambda r:r.url.endswith('/analyze')) as response:tab.locator('#analyze').click()
                check(stem+': separate-tab analysis HTTP 200',response.value.status==200)
                expect(tab.locator('#results')).to_be_visible();tab.screenshot(path=str(output/(stem+'-full.png')),full_page=True)
                return tab,response.value.json()
            snapshot,preview=upload_save(source,'main')
            main=analyze('2026-10-30T09:00:00','main-results');rows={r['transaction_id']:r for r in main['rows']}
            check('five transactions retained',set(rows)==set(HAND) and main['row_count']==5)
            for identity,hand in HAND.items():
                row=rows[identity];payment=row['checks']['payment_invoice'];check(identity+': amount and status',row['amount_vnd']==hand['amount'] and payment['status']==hand['status'])
                if identity=='MISSING':
                    check('MISSING: unknown remains without numeric payment facts',payment['facts']==[] and payment['available'] is False and payment['needs_review'] is None and bool(payment['missing_sources']))
                else:
                    expected=dict(zip(FACTS,(10_000_000,hand['prior'],hand['current'],hand['total'],hand['excess'])))
                    actual={k:payment['facts'][0][k] for k in FACTS};check(identity+': manual invoice/prior/current/total/excess',actual==expected,dict(expected=expected,actual=actual))
                    refs=payment['facts'][0]['invoice_refs'];check(identity+': exact invoice reference',len(refs)==1 and refs[0]['record_id']=='I001' and refs[0]['revision']==1)
                check(identity+': simultaneous membership not repeated',bool(payment['group_refs'])==hand['group'])
            group,=main['groups'];check('one group A+B: 4m + 8m = 12m; excess 2m',all(group[k]==v for k,v in GROUP.items()) and {r['record_id'] for r in group['transaction_refs']}=={'A','B'} and group['status']=='needs_review')
            check('A and B point to the one root group',rows['A']['checks']['payment_invoice']['group_refs']==rows['B']['checks']['payment_invoice']['group_refs']==[group['group_id']])
            check('vendor-name review is not a confirmed duplicate',all(r['checks']['vendor_names']['status']=='needs_review' for r in rows.values()) and {v['name'] for v in source['vendors']}=={'North Harbor Equipment','North Harbour Equipment'})
            check('summary scope: 5 flagged rows, one missing check, one group',main['summary']['transactions_to_review']==5 and main['summary']['unavailable_checks']==1 and main['summary']['groups_to_review']==1 and main['summary']['analysis_complete'] is False)
            limits=preview['analysis_limits']['C001'];counts={x['code']:x['affected_count'] for x in limits};check('preview discloses original docs/approvals/bank-history missing for all 5',all(counts.get(k)==5 for k in ('DOCUMENT_BASIS_MISSING','APPROVAL_BASIS_MISSING','BANK_HISTORY_MISSING')))
            page.screenshot(path=str(output/'main-results.png'),full_page=True)
            full_tab,full_result=inspect_full_page('main-results')
            check('main: separate-tab binding is unchanged',full_result['snapshot']==main['snapshot'] and full_result['analysis_id']==main['analysis_id'])
            full_tab.locator('#filter').select_option('unavailable');expect(full_tab.locator('#rows .transaction')).to_have_count(1)
            missing_text=full_tab.locator('#rows .check-result').first.inner_text()
            check('MISSING: UI does not render unknown prior history as zero','Chưa đủ nguồn' in missing_text and 'Đã trả trước:' not in missing_text)
            full_tab.screenshot(path=str(output/'main-missing-full.png'),full_page=True)
            full_tab.locator('#filter').select_option('all')
            presentation=dict(preview_limits_hidden_after_commit=full_tab.locator('#preview-panel').is_hidden(),results_display_all_source_limit_headings=all(t in full_tab.locator('#results').inner_text() for t in ('Chứng từ gốc','Lịch sử tài khoản nhà cung cấp','Phê duyệt khoản chi')),vendor_source_names_in_business_response=all(v['name'] in json.dumps(main,ensure_ascii=False) for v in source['vendors']),invoice_number_in_business_response=source['invoices'][0]['number'] in json.dumps(main,ensure_ascii=False))
            full_tab.close()
            frame.locator('#filter').select_option('unavailable');expect(frame.locator('#rows .transaction')).to_have_count(1);expect(frame.locator('#rows')).to_contain_text('MISSING');page.screenshot(path=str(output/'main-missing.png'),full_page=True);frame.locator('#filter').select_option('all')
            for day,ids in [(1,{'OLD'}),(2,{'OLD','A','B'}),(3,{'OLD','A','B','OVER'})]:
                result=analyze(f'2026-10-{day:02d}T09:00:00',f'asof-oct{day:02d}');past={r['transaction_id']:r for r in result['rows']}
                check(f'Oct {day}: no future rows and stable historical checks',set(past)==ids and all(r['checks']==rows[k]['checks'] for k,r in past.items()))
                check(f'Oct {day}: same immutable snapshot',result['snapshot']==main['snapshot'])
            check('read-only reruns retain one snapshot',h.count()==1)
            # Persist a tiny business-policy probe separately; do not change any evaluator.
            probe=first_payment_probe(source);write(output/'first-payment-source.json',probe);probe_snapshot,_=upload_save(probe,'first-payment');probe_result=analyze('2026-10-30T09:00:00','first-payment-results')
            p1=probe_result['rows'][0]['checks']['payment_invoice'];check('first-payment probe: arithmetic 11m - 10m = 1m',p1['facts'][0]['excess_vnd']==1_000_000 and p1['facts'][0]['prior_paid_vnd']==0)
            presentation['first_payment_status']=p1['status'];presentation['first_payment_transactions_to_review']=probe_result['summary']['transactions_to_review']
            page.screenshot(path=str(output/'first-payment-results.png'),full_page=True)
            full_tab,full_probe=inspect_full_page('first-payment-results')
            check('probe: separate-tab binding is unchanged',full_probe['snapshot']==probe_result['snapshot'])
            text=full_tab.locator('#rows .check-result').first.inner_text()
            presentation['first_payment_UI_has_no_signal_and_excess']=('Chưa thấy tín hiệu' in text and 'Phần vượt: 1.000.000 đ' in text)
            full_tab.close();write(output/'presentation_observations.json',presentation)
            candidates=[
                dict(id='BR-026-01',priority='high',classification='business_policy_decision_required',title='Khoản đầu 11 triệu trên hóa đơn 10 triệu chưa được gắn cờ',evidence='first-payment-results.json',detail='P1 cần có thanh toán trước theo policy hiện tại. Kết quả no_signal nhưng facts có phần vượt 1 triệu; không được hiểu no_signal là hợp lệ. Không tự thay luật khi chưa chốt phạm vi.'),
                dict(id='BR-026-02',priority='medium',classification='coverage_presentation_gap',title='Một kiểm tra chưa đủ nguồn không phải chỉ một giao dịch thiếu chứng từ',evidence='main-preview.json / main-results.json',detail='Preview báo cả 5 thiếu chứng từ gốc, phê duyệt, lịch sử tài khoản. Kết quả đếm 1 unavailable cho hai kiểm tra đang chạy, còn preview bị ẩn sau lưu. Nên giữ tóm tắt giới hạn nguồn bên cạnh kết quả.'),
                dict(id='BR-026-03',priority='medium',classification='business_evidence_usability_gap',title='Màn hình chưa hiện số hóa đơn và cặp tên NCC cần đối chiếu',evidence='main-results.json / source.json',detail='DTO có refs I001/V001/V_PEER nhưng không có số 0000123 hoặc hai tên nguồn. Người rà phải mở tệp JSON để biết chi tiết; nên bổ sung trường nghiệp vụ cho phép, không lộ tham số/điểm.'),
            ]
            if p1['status']=='no_signal' and p1['facts'][0]['excess_vnd']>0:findings.append(candidates[0])
            if presentation['preview_limits_hidden_after_commit'] and not presentation['results_display_all_source_limit_headings']:findings.append(candidates[1])
            if not presentation['vendor_source_names_in_business_response'] or not presentation['invoice_number_in_business_response']:findings.append(candidates[2])
            check('only two isolated snapshots for main and probe',h.count()==2)
            check('no JavaScript errors',not browser_errors,browser_errors)
            write(output/'checks.json',dict(checks=checks,count=len(checks),all_passed=all(c['passed'] for c in checks),browser_errors=browser_errors))
            write(output/'findings.json',findings)
            write(output/'summary.json',dict(status='arithmetic_reconciled_open_business_findings',primary_transactions=5,probe_transactions=1,source_kind='synthetic_only',checks=len(checks),all_checks_passed=True,findings=len(findings),main_snapshot=snapshot,probe_snapshot=probe_snapshot,live_services_touched=False,production_data_written=False,original_documents_verified=False,human_business_signoff=False,rule_model_or_UI_changed=False))
            context.close();browser.close()
    print(json.dumps(dict(status='arithmetic_reconciled_open_business_findings',checks=len(checks),findings=len(findings))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
