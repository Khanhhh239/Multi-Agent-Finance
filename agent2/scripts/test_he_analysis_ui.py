"""Real-browser HE user flow via Portal; no mocked scores or plaintext worker."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT/'tests'),str(ROOT.parent)]
from web_support import WebHarness
from experiments.he_inference.registry_demo import database_dump
from portal import server as portal


def run(output):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[];requests=[]
    def passed(name):checks.append(dict(check=name,passed=True))
    with WebHarness() as f:
        h=f.h; before={k:database_dump(f.pair.env[k]) for k in ('snapshot_db','model_db')}
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            context=browser.new_context(viewport=dict(width=1365,height=950));page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:requests.append(dict(url=request.url,method=request.method,body=request.post_data)) if '/he/' in request.url or str(f.pair.worker_port) in request.url else None)
            url=h.portal_url+'/agent2/encrypted-analysis'
            page.goto(url);expect(page.locator('#portal-access')).to_be_visible();expect(page.locator('#connection')).to_be_hidden();passed('locked Portal requires login and never offers local credentials')
            page.locator('#portal-login').click();expect(page.locator('#gate')).to_be_visible();page.locator('#gate-password').fill('Synthetic-HE-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-HE-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
            page.goto(url);expect(page.locator('#company option')).to_have_count(2);expect(page.locator('#connection')).to_be_hidden();expect(page.locator('#selection .grid select')).to_have_count(2);passed('existing Portal login opens company and dataset selectors with history in collapsed details')
            page.locator('#company').select_option('C001');expect(page.locator('#dataset option')).to_have_count(2)
            page.locator('#dataset').select_option(f.pair.env['queries']['C001']);expect(page.locator('#run')).to_be_enabled();page.locator('#run').click();expect(page.locator('#rows .transaction')).to_have_count(5,timeout=45000);expect(page.locator('#result-summary')).to_contain_text('5 có điểm');passed('C001 runs encrypted inference and returns all five decrypted rows')
            first=page.locator('#result-meta dd').last.inner_text();page.screenshot(path=str(output/'01-completed-desktop.png'),full_page=True)
            expect(page.locator('#review-cases article')).to_have_count(5,timeout=20000)
            review=page.locator('#review-cases article').first
            evidence=review.locator('details').first;evidence.locator('summary').first.click();expect(evidence).to_contain_text('Nguồn được biết lúc');expect(evidence.locator('table').first).to_contain_text('Tài khoản');evidence.locator('summary').first.click();passed('evidence shows dates, provenance and accounting entries before technical JSON')
            review.get_by_role('button',name='Bắt đầu rà',exact=True).click()
            review.get_by_label('Đã kiểm tra gì và căn cứ nào?').fill('Kiểm thử giao diện: chưa có hóa đơn gốc.')
            review.get_by_label('Cần ai làm gì tiếp theo?').fill('Yêu cầu kế toán cung cấp hóa đơn gốc.')
            review.get_by_label('Tài liệu còn thiếu').fill('Hóa đơn gốc')
            review.get_by_role('button',name='Lưu kết quả rà',exact=True).click()
            expect(review).to_contain_text('Đã lưu phiên bản 1 tại doanh nghiệp.')
            passed('review saves inconclusive feedback on server with explanation and action')
            expect(page.locator('#review-cases')).to_contain_text('1/5 phiếu đã ghi kết quả')
            page.get_by_label('Hiển thị phiếu',exact=True).select_option('pending');expect(page.locator('#review-cases article:visible')).to_have_count(4)
            page.get_by_label('Hiển thị phiếu',exact=True).select_option('reviewed');expect(page.locator('#review-cases article:visible')).to_have_count(1)
            page.get_by_label('Hiển thị phiếu',exact=True).select_option('all');passed('server acknowledgment updates review counts and outcome filters')
            page.locator('#run').click();expect(page.locator('#rows .transaction')).to_have_count(5);expect(page.locator('#result-meta dd').last).to_have_text(first);passed('repeated click reads the same result and run ID')
            page.reload();expect(page.locator('#rows .transaction')).to_have_count(5,timeout=30000);expect(page.locator('#result-meta dd').last).to_have_text(first);passed('reload restores completed result without retyping credentials or choosing a model')
            expect(page.locator('#review-cases article')).to_have_count(5,timeout=20000)
            expect(page.locator('#review-cases article').first.get_by_label('Đã kiểm tra gì và căn cứ nào?')).to_have_value('Kiểm thử giao diện: chưa có hóa đơn gốc.')
            passed('review feedback survives browser reload and remains bound to the same run')
            page.locator('#company').select_option('C002');expect(page.locator('#dataset option')).to_have_count(2);page.locator('#dataset').select_option(f.pair.env['queries']['C002']);expect(page.locator('#results')).to_be_hidden();expect(page.locator('#result-meta dd')).to_have_count(0);expect(page.locator('#job-meta dd')).to_have_count(0);passed('company switch immediately clears previous result and dataset context')
            f.pair._stop(f.pair.worker_process);page.locator('#run').click()
            expect(page.locator('#job-meta dd').first).to_contain_text('herun_',timeout=20000)
            job=page.locator('#job-meta dd').first.inner_text()
            expect(page.locator('#progress-panel')).to_be_visible();page.screenshot(path=str(output/'02-waiting-worker.png'),full_page=True)
            page.reload();expect(page.locator('#progress-panel')).to_be_visible(timeout=20000);passed('reload during worker outage restores the original durable request')
            f.pair.restart_worker();f.backend.node.worker_url=f'http://127.0.0.1:{f.pair.worker_port}'
            expect(page.locator('#rows .transaction')).to_have_count(5,timeout=60000);expect(page.locator('#result-meta')).to_contain_text(job);expect(page.locator('#result-summary')).to_contain_text('5 có điểm');passed('worker recovery returns C002 result under the same job ID')
            with closing(sqlite3.connect(f.pair.worker_root/'state/jobs.sqlite3')) as conn:
                # Table name belongs to the actual worker store, never a mocked counter.
                count=conn.execute('SELECT count(*) FROM jobs WHERE state=?',('done',)).fetchone()[0]
            assert count==2,count;passed('two company analyses create exactly two worker computations despite retries and reloads')
            page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(output/'03-completed-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'mobile overflow'
            passed('mobile view remains within the viewport')
            page.set_viewport_size(dict(width=1365,height=950));page.locator('#dataset').select_option(f.pair.env['training']['C002']);page.locator('#run').click();expect(page.locator('#result-summary')).to_contain_text('0 có điểm',timeout=30000);expect(page.locator('#rows .transaction').first).to_contain_text('thời điểm giao dịch');passed('training-period data stays unavailable with an explanation rather than fabricated zero scores')
            f.pins['bindings']=[];f.write_pins();page.reload();expect(page.locator('#availability')).to_contain_text('Chưa có model');page.locator('#company').select_option('C001');expect(page.locator('#dataset option')).to_have_count(2);page.locator('#dataset').select_option(f.pair.env['training']['C001']);expect(page.locator('#run')).to_be_disabled();passed('missing configured model disables new analysis with a clear explanation')
            f.pins['bindings']=[dict(tenant_id='demo',company_id=c,artifact_id=f.pair.env['artifacts'][c]) for c in ('C001','C002')];f.write_pins()
            h.policy['memberships'][0]['status']='revoked';h.write_policy();page.reload();expect(page.locator('#company option')).to_have_count(1);expect(page.locator('#company')).to_have_value('C002');passed('revoked company disappears after current authorization is checked')
            session=page.evaluate('sessionStorage.getItem("kt-session")');portal.SESSIONS[session]=time.time()-1;page.reload();expect(page.locator('#portal-access')).to_be_visible(timeout=15000);expect(page.locator('#results')).to_be_hidden();expect(page.locator('#connection')).to_be_hidden();passed('expired Portal login clears private results with no local fallback')
            submissions=[r for r in requests if r['method']=='POST' and r['url'].endswith('/he/jobs')]
            assert submissions and all(set(json.loads(r['body']))=={'snapshot_id'} for r in submissions)
            assert not any(r['url'].startswith(f'http://127.0.0.1:{f.pair.worker_port}/') for r in requests)
            assert not any('token=' in r['url'] or 'session=' in r['url'] for r in requests)
            passed('browser submits only snapshot references to the DN backend, never direct worker requests or credential URLs')
            assert not errors,errors;passed('browser has no JavaScript errors')
            context.close();browser.close()
        assert all(database_dump(f.pair.env[k])==v for k,v in before.items());passed('source snapshots and models remain unchanged')
    report=dict(status='passed',count=len(checks),checks=checks,browser_errors=errors,data='synthetic_only',browser='Chrome via Playwright',real_he=True,live_services_changed=False)
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(status='passed',checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
