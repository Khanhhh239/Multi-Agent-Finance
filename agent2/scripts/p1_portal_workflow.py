"""Reloadable live acceptance steps. Never exports browser credentials."""
import json
from pathlib import Path
import re
import sqlite3
import time
from playwright.sync_api import expect
from experiments.he4.p1_demo import save_snapshot,inspect
from experiments.he4.p1_portal_check import reconcile
from sme_fraud.import_files import canonical,digest

ROOT=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:8800'


def open_job(page,company,snapshot,job):
    page.goto(URL+'/agent2/encrypted-analysis')
    expect(page.locator('#company option[value="'+company+'"]').first).to_be_attached(timeout=30000)
    page.locator('#company').select_option(company)
    expect(page.locator('#dataset option[value="'+snapshot+'"]').first).to_be_attached(timeout=30000)
    page.locator('#dataset').select_option(snapshot)
    if job:
        expect(page.locator('#previous-runs option[value="'+job+'"]').first).to_be_attached(timeout=30000)
        page.get_by_text('Xem lại lần phân tích đã lưu',exact=True).click()
        page.locator('#previous-runs').select_option(job)
        return job
    expect(page.locator('#run')).to_be_enabled(timeout=30000)
    endpoint='/agent2/api/v1/companies/'+company+'/he/jobs'
    with page.expect_response(lambda r:r.url==URL+endpoint and r.request.method=='POST',timeout=60000) as response:
        page.locator('#run').click()
    reply=response.value
    if reply.status!=202:raise AssertionError(dict(stage='ui_submit',status=reply.status,response=reply.json()))
    identity=reply.json().get('job_id')
    if not isinstance(identity,str) or not re.fullmatch(r'herun_[a-f0-9]{32}',identity):raise AssertionError('server did not return a valid job id')
    return identity


def execute(page,api,output,restart,receipts,manifest,references,checks):
    receipts_path=output/'receipts.json'
    if restart and not receipts.get('_backend_restarted'):
        # Do not stop unrelated in-progress work for a review renderer fix.
        for relative in ('.runtime/he-four-managed-v1/enterprise/jobs/jobs.sqlite3','.runtime/he-company-demo/enterprise/state/jobs.sqlite3'):
            with sqlite3.connect((ROOT/relative).resolve().as_uri()+'?mode=ro',uri=True) as c:
                if c.execute("SELECT count(*) FROM jobs WHERE phase NOT IN ('completed','failed','expired')").fetchone()[0]:raise AssertionError('finish pending work before restarting backend')
        api('/api/agents/agent2/stop',{});api('/api/agents/agent2/start',{})
        receipts['_backend_restarted']=True;receipts_path.write_bytes(canonical(receipts));print(json.dumps(dict(stage='backend_restarted_preserving_portal_session')),flush=True)
    for config in manifest['published_snapshots']:
        company=config['company_id'];snapshot=config['snapshot_id'];base='/agent2/api/v1/companies/'+company
        if any(c['company_id']==company for c in checks):continue
        saved=receipts.get(company)
        repair_path=output/'retest-failed-admission.json'
        if saved and repair_path.exists():
            repair=json.loads(repair_path.read_bytes())
            if repair.get('company_id')==company and repair.get('failed_job')==saved['job_id']:
                if repair.get('snapshot_id')!=snapshot:raise AssertionError('retest snapshot mismatch')
                failed=api(base+'/he/jobs/'+saved['job_id'])
                if failed['phase']!='failed' or failed.get('reason')!='HE4_EXPIRED':raise AssertionError('only the recorded expired-admission failure can be retested')
                receipts.setdefault('_failed_attempts',[]).append(dict(saved,company_id=company,reason=failed['reason']))
                receipts.pop(company);saved=None;receipts_path.write_bytes(canonical(receipts));repair_path.unlink()
                print(json.dumps(dict(stage='explicit_retest_after_fix_original_failure_retained',company=company,failed_job=repair['failed_job'])),flush=True)
        if saved and not re.fullmatch(r'herun_[a-f0-9]{32}',saved.get('job_id','')):
            receipts.pop(company);saved=None
        if saved and saved['snapshot_id']!=snapshot:raise AssertionError('receipt snapshot changed')
        if not saved:
            runs=api(base+'/he/runs')['runs']
            existing=next((r for r in runs if r['snapshot_id']==snapshot and r['analysis_mode']=='four_encrypted_branches' and r['phase'] not in ('failed','expired')),None)
            job=open_job(page,company,snapshot,existing['job_id'] if existing else None)
            saved=dict(snapshot_id=snapshot,job_id=job);receipts[company]=saved;receipts_path.write_bytes(canonical(receipts))
        job=saved['job_id'];last=None;started=time.monotonic();resume_requested=False
        while True:
            state=api(base+'/he/jobs/'+job,company=company,job=job)
            if state['phase']!=last:
                last=state['phase'];print(json.dumps(dict(stage='job_status',company=company,job_id=job,phase=last)),flush=True)
                (output/'progress.json').write_bytes(canonical(dict(company_id=company,job_id=job,phase=last,completed_companies=len(checks))))
            if last=='completed':break
            if last in ('failed','expired'):raise AssertionError(dict(company=company,job=job,state=state))
            if last=='waiting_authorization' and not resume_requested:
                api(base+'/he/jobs/'+job+'/resume',{},company=company,job=job);resume_requested=True
            elif last!='waiting_authorization':resume_requested=False
            time.sleep(3)
        result=api(base+'/he/jobs/'+job+'/result',company=company,job=job)
        metadata=api(base+'/snapshots/'+snapshot,company=company,job=job)
        raw=api(base+'/snapshots/'+snapshot+'/data',company=company,job=job)
        if digest(canonical(raw))!=config['checksum']:raise AssertionError('prepared source differs from Portal snapshot')
        if result['snapshot_id']!=snapshot or result['as_of']!=metadata['created_at']:raise AssertionError('snapshot/result cutoff binding')
        ref_id=save_snapshot(references,company,raw);reference,_=inspect(references,company,ref_id,result['as_of'])
        packet=api(base+'/he/jobs/'+job+'/reviews',company=company,job=job);comparison=reconcile(company,raw,result,packet,reference)
        for name,value in (('result',result),('review-packet',packet),('source',raw),('engine',reference),('reconciliation',comparison)):(output/(company+'-'+name+'.json')).write_bytes(canonical(value))
        open_job(page,company,snapshot,job)
        expect(page.locator('#rows > article.transaction')).to_have_count(8,timeout=30000);expect(page.locator('#review-cases > article.transaction')).to_have_count(8,timeout=30000)
        # Validate the visible record joins, without writing feedback.
        review=page.locator('#review-cases > article.transaction').filter(has=page.get_by_role('heading',name=re.compile(r'^Giao dịch P1_T06 ·')))
        review.get_by_text('Chứng từ và nguồn đối chiếu',exact=True).click()
        expect(review).to_contain_text('P1_A_P1_T07');expect(review).to_contain_text('P1_COV_6');expect(review).to_contain_text('Hóa đơn trong phạm vi')
        card=page.locator('#rows > article.transaction').filter(has=page.get_by_role('heading',name='Giao dịch P1_T03',exact=True))
        rule=card.locator('.check-result').filter(has=page.get_by_role('heading',name='Đối chiếu thanh toán',exact=True));rule.locator('summary').click();rule.screenshot(path=str(output/(company+'-P1-T03.png')))
        peer=review.get_by_text('P1_A_P1_T07 · Dữ liệu mô phỏng',exact=True).locator('..').locator('..');peer.screenshot(path=str(output/(company+'-peer-allocation.png')))
        page.reload();expect(page.locator('#rows > article.transaction')).to_have_count(8,timeout=30000);expect(page.locator('#review-cases > article.transaction')).to_have_count(8,timeout=30000);expect(page.locator('#result-meta dd').last).to_have_text(job)
        checks.append(dict(company_id=company,job_id=job,row_count=8,p1_source_engine_parity=True,review_cases=8,reload_same_run=True,elapsed_seconds=time.monotonic()-started))
        print(json.dumps(dict(stage='completed',company=company)),flush=True)
