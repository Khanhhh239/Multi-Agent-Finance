"""Real browser: Portal start/stop, key-ready worker, outage and same-job resume."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT/'tests'),str(ROOT.parent)]
from test_managed_worker import ManagedHarness
from portal import server as portal
from portal.agent2_runtime import stop_owned
from experiments.he_inference.registry_demo import database_dump


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    def passed(name):checks.append(dict(check=name,passed=True))
    with ManagedHarness() as f:
        before={name:database_dump(f.pair.env[name]) for name in ('snapshot_db','model_db')}
        keys=[f.pair.node_key_path.read_bytes(),f.pair.state_key_path.read_bytes()]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);context=browser.new_context(viewport=dict(width=1440,height=1050));page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f.h.portal_url+'/#data');expect(page.locator('#gate')).to_be_visible()
            page.locator('#gate-password').fill('Synthetic-Managed-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-Managed-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
            passed('login uses isolated test Portal; no live account changed')
            page.goto(f.h.portal_url+'/#agent2');expect(page.locator('#agent-start')).to_be_visible();page.locator('#agent-start').click()
            expect(page.locator('#agent-frame')).to_be_visible(timeout=45000)
            assert portal.HE_RUNTIME.state()['status']=='ready';assert portal.HE_RUNTIME.process.poll() is None
            passed('Bật Agent2 starts owned worker, verifies keys and opens DN UI')
            frame=page.frame_locator('#agent-frame');frame.get_by_role('link',name='Chạy phân tích bảo mật').click()
            expect(frame.locator('#company option')).to_have_count(2);frame.locator('#dataset').select_option(f.pair.env['queries']['C001'])
            expect(frame.locator('#run')).to_be_enabled();frame.locator('#run').click();expect(frame.locator('#results')).to_be_visible(timeout=45000)
            expect(frame.locator('#result-summary')).to_contain_text('5 có điểm');first=frame.locator('#result-meta dd').last.inner_text()
            code,c001=f.h.request(f.h.url('he/jobs/'+first+'/result','C001'))
            assert code==200 and c001['company_id']=='C001' and c001['snapshot_id']==f.pair.env['queries']['C001']
            assert {r['record_id'] for r in c001['rows']}=={'T0','T1','T2','T3','T4'}
            passed('verified worker produces all five C001 decrypted results')
            page.screenshot(path=str(output/'01-ready.png'),full_page=True)
            old_worker=portal.HE_RUNTIME.process;old_node=portal.PROCS['agent2']
            page.locator('#agent-toggle').click();expect(page.locator('#agent-frame')).to_be_hidden(timeout=20000)
            assert old_worker.poll() is not None and old_node.poll() is not None
            assert not portal.port_open(f.worker_port) and not portal.port_open(f.port)
            passed('Tắt Agent2 stops exactly the owned DN and worker trees')
            page.locator('#agent-start').click();expect(page.locator('#agent-frame')).to_be_visible(timeout=45000)
            frame=page.frame_locator('#agent-frame');frame.get_by_role('link',name='Chạy phân tích bảo mật').click()
            expect(frame.locator('#results')).to_be_visible(timeout=30000);expect(frame.locator('#result-meta dd').last).to_have_text(first)
            passed('start again restores same saved result/job under the Portal session')
            frame.locator('#company').select_option('C002');frame.locator('#dataset').select_option(f.pair.env['queries']['C002'])
            node=portal.PROCS['agent2'];stop_owned(portal.HE_RUNTIME.process)
            frame.locator('#run').click();expect(frame.locator('#reconnect')).to_be_visible(timeout=20000)
            expect(frame.locator('#progress-help')).to_contain_text('Yêu cầu đã lưu')
            expect(frame.locator('#job-meta dd').first).to_contain_text('herun_',timeout=20000)
            job=frame.locator('#job-meta dd').first.text_content();assert job.startswith('herun_'),repr(job)
            expect(frame.locator('#run')).to_have_text('Tiếp tục phân tích')
            expect(page.locator('#agent2-recover')).to_be_visible(timeout=10000)
            passed('outage shows a short recoverable message and keeps the original request')
            page.screenshot(path=str(output/'02-worker-offline.png'),full_page=True)
            frame.locator('#reconnect').click();expect(frame.locator('#results')).to_be_visible(timeout=60000)
            expect(frame.locator('#result-meta dd').last).to_have_text(job);expect(frame.locator('#result-summary')).to_contain_text('5 có điểm')
            code,c002=f.h.request(f.h.url('he/jobs/'+job+'/result','C002'))
            assert code==200 and c002['company_id']=='C002' and c002['snapshot_id']==f.pair.env['queries']['C002']
            assert {r['record_id'] for r in c002['rows']}=={'T0','T1','T2','T3','T4'}
            assert portal.PROCS['agent2'] is node
            expect(page.locator('#agent2-recover')).to_be_hidden(timeout=10000)
            passed('Kết nối lại restarts only worker and resumes same C002 job')
            page.screenshot(path=str(output/'03-recovered.png'),full_page=True)
            page.reload();frame=page.frame_locator('#agent-frame');frame.get_by_role('link',name='Chạy phân tích bảo mật').click()
            expect(frame.locator('#results')).to_be_visible(timeout=30000);expect(frame.locator('#result-meta dd').last).to_have_text(job)
            passed('reload after recovery retains the same result and run ID')
            assert f.h.request(f.h.url('he/jobs/'+first+'/result','C001'))[1]==c001
            assert f.h.request(f.h.url('he/jobs/'+job+'/result','C002'))[1]==c002
            passed('reload and lifecycle preserve every score and row, not only job IDs')
            for company,other_job in [('C001',job),('C002',first)]:
                assert f.h.request(f.h.url('he/jobs/'+other_job+'/result',company))[0]==404
                assert f.h.request(f.h.url('he/jobs/'+other_job,company))[0]==404
                assert f.h.request(f.h.url('he/jobs/'+other_job+'/resume',company),{})[0]==404
            passed('cross-company result, status and resume reads rejected in both directions')
            for company,other in [('C001','C002'),('C002','C001')]:
                code,catalog=f.h.request(f.h.url('he/datasets',company))
                assert code==200 and {d['snapshot_id'] for d in catalog['datasets']}=={f.pair.env['queries'][company],f.pair.env['training'][company]}
                assert f.h.request(f.h.url('he/jobs',company),dict(snapshot_id=f.pair.env['queries'][other]),headers={'Idempotency-Key':'cross-company-rejected'})[0]==404
            passed('catalogs isolate company snapshots; another company snapshot cannot be submitted')
            with closing(sqlite3.connect(f.pair.worker_root/'state/jobs.sqlite3')) as conn:
                assert conn.execute("SELECT count(*) FROM jobs WHERE state='done'").fetchone()[0]==2
            passed('only two worker computations for two companies across lifecycle/reloads')
            assert not errors,errors;passed('no browser JavaScript errors')
            context.close();browser.close()
        assert before=={name:database_dump(f.pair.env[name]) for name in before}
        assert keys==[f.pair.node_key_path.read_bytes(),f.pair.state_key_path.read_bytes()]
        passed('snapshots, model registry and protected key files unchanged')
    report=dict(status='passed',count=len(checks),checks=checks,browser_errors=errors,data='synthetic_only',real_he=True,servers='isolated Portal and managed DN/worker',live_services_changed=False)
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(status='passed',checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
