"""Operator-assisted acceptance on the running Portal; never handles passwords.

Uses the existing C001/C002 synthetic packet, owned worker only. A new Chrome
window asks the operator to log in. Credentials/session are never exported.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.he_inference.registry_demo import database_dump


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def powershell(command):
    return json.loads(subprocess.check_output(
        ['powershell', '-NoProfile', '-Command', command],
        creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8-sig'))


def run(output, portal_url, packet, login_timeout):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True, exist_ok=False)
    prepared = json.loads((packet / 'prepared.json').read_text('utf-8'))
    assert prepared['data'] == 'synthetic_only'
    companies = {c['company_id']: c for c in prepared['companies']}
    node = json.loads((packet / 'enterprise/node.json').read_text('utf-8'))
    private_files = [Path(node[k]) for k in ('state_key_file', 'provisioning_key_file')]
    before_keys = [hashlib.sha256(p.read_bytes()).hexdigest() for p in private_files]
    before_data = {k: digest(database_dump(node[k])) for k in ('snapshot_db', 'model_db')}
    with urlopen(portal_url + '/api/state') as r:
        before_agents = {a['id']: (a['state'], a['owned']) for a in json.load(r)['agents'] if a['id'] != 'agent2'}
    checks = []; errors = []; results = {}; fault = {}

    def passed(name, **evidence):
        checks.append(dict(check=name, passed=True, **evidence))
        print('PASS: ' + name, flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=False)
        context = browser.new_context(viewport=dict(width=1440, height=1050))
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))

        def api(path, body=None):
            return page.evaluate('''async ({path,body})=>{
              const h={'X-Platform':'1','X-Session':sessionStorage.getItem('kt-session')||''};
              if(body!==null)h['Content-Type']='application/json';
              const r=await fetch(path,{method:body===null?'GET':'POST',headers:h,
                body:body===null?undefined:JSON.stringify(body)});
              return {status:r.status,value:await r.json()};
            }''', dict(path=path, body=body))

        def result(company, job):
            r = api(f'/agent2/api/v1/companies/{company}/he/jobs/{job}/result')
            assert r['status'] == 200, r
            v = r['value']; assert v['company_id'] == company and v['row_count'] == 5
            assert len(v['rows']) == 5 and all(row['available'] for row in v['rows'])
            assert {row['record_id'] for row in v['rows']} == {'T0','T1','T2','T3','T4'}
            return v

        def open_analysis():
            frame = page.frame_locator('#agent-frame')
            frame.get_by_role('link', name='Chạy phân tích bảo mật').click()
            expect(frame.locator('#selection')).to_be_visible(timeout=20000)
            return frame

        try:
            page.goto(portal_url + '/#data')
            print('AWAITING_OPERATOR_LOGIN: ' + portal_url, flush=True)
            expect(page.locator('#intake')).to_be_visible(timeout=login_timeout * 1000)
            auth = api('/agent2/api/v1/ui/context')
            assert auth['status'] == 200 and set(auth['value']['companies']) >= {'C001','C002'}, auth
            passed('operator login authorizes C001/C002 without exporting credentials')
            page.goto(portal_url + '/#agent2')
            state = api('/api/state')['value']
            a2 = next(a for a in state['agents'] if a['id']=='agent2')
            if a2['state'] != 'running': page.locator('#agent-start').click()
            expect(page.locator('#agent-frame')).to_be_visible(timeout=45000)
            frame = open_analysis()
            frame.locator('#company').select_option('C001')
            frame.locator('#dataset').select_option(companies['C001']['evaluation_snapshot_id'])
            expect(frame.locator('#run')).to_be_enabled()
            frame.locator('#run').click()
            expect(frame.locator('#results')).to_be_visible(timeout=60000)
            first = frame.locator('#result-meta dd').last.text_content()
            results['C001'] = result('C001', first)
            passed('C001 returns exactly five available rows', job_id=first, result_sha256=digest(results['C001']))
            page.screenshot(path=str(output/'01-c001.png'), full_page=True)

            page.locator('#agent-toggle').click()
            expect(page.locator('#agent-frame')).to_be_hidden(timeout=30000)
            stopped = next(a for a in api('/api/state')['value']['agents'] if a['id']=='agent2')
            assert stopped['state']=='stopped' and stopped['dependency']['status']!='ready', stopped
            passed('Portal stops its Agent2 and worker')
            page.locator('#agent-start').click()
            expect(page.locator('#agent-frame')).to_be_visible(timeout=45000)
            frame = open_analysis()
            expect(frame.locator('#results')).to_be_visible(timeout=30000)
            assert frame.locator('#result-meta dd').last.text_content()==first
            assert result('C001', first)==results['C001']
            passed('start again restores the identical C001 job and result')

            # Resolve the actual worker wrapper from operator-controlled config,
            # then verify its parent is the live Portal listener. Never kill by port.
            ps = powershell("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
            listeners = powershell("Get-NetTCPConnection -LocalPort 8800,8868 -State Listen | Select-Object LocalPort,OwningProcess | ConvertTo-Json -Compress")
            live = {p['LocalPort']:p['OwningProcess'] for p in listeners}
            candidates = [p for p in ps if p['ParentProcessId']==live[8800]
                          and ' -m experiments.he_inference.worker_server ' in (p['CommandLine'] or '')
                          and str(packet/'worker/service.json').lower() in (p['CommandLine'] or '').lower()]
            assert len(candidates)==1, 'worker ownership not uniquely verified'
            worker = candidates[0]
            assert any(p['ProcessId']==live[8868] and p['ParentProcessId']==worker['ProcessId'] for p in ps)
            with closing(sqlite3.connect(Path(node['state_dir'])/'jobs.sqlite3')) as c:
                old_jobs = {r[0] for r in c.execute('SELECT id FROM jobs')}
            frame.locator('#company').select_option('C002')
            frame.locator('#dataset').select_option(companies['C002']['evaluation_snapshot_id'])
            expect(frame.locator('#results')).to_be_hidden()
            expect(frame.locator('#run')).to_be_enabled()
            ready = threading.Event()

            def disconnect():
                try:
                    ready.set(); deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        with closing(sqlite3.connect(Path(node['state_dir'])/'jobs.sqlite3')) as c:
                            rows=c.execute("SELECT id,phase FROM jobs WHERE company='C002'").fetchall()
                        for job, phase in rows:
                            if job not in old_jobs and phase=='preparing':
                                # Injection is after submission/preflight, before
                                # worker claims the native computation.
                                fault.update(job_id=job, phase_at_disconnect=phase, worker_pid=worker['ProcessId'])
                                subprocess.run(['taskkill','/PID',str(worker['ProcessId']),'/T','/F'],
                                    check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
                                return
                        time.sleep(.02)
                    fault['error']='preparing phase not observed; no process stopped'
                except Exception as e: fault['error']=str(e)

            thread=threading.Thread(target=disconnect,daemon=True);thread.start();ready.wait(2)
            frame.locator('#run').click()
            expect(frame.locator('#reconnect')).to_be_visible(timeout=45000)
            thread.join(5);assert 'error' not in fault and fault.get('job_id'),fault
            expect(frame.locator('#progress-help')).to_contain_text('Yêu cầu đã lưu')
            job=frame.locator('#job-meta dd').first.text_content();assert job==fault['job_id']
            passed('worker disconnected after C002 submission; original request kept', **fault)
            page.screenshot(path=str(output/'02-c002-offline.png'), full_page=True)
            frame.locator('#reconnect').click()
            expect(frame.locator('#results')).to_be_visible(timeout=60000)
            assert frame.locator('#result-meta dd').last.text_content()==job
            results['C002']=result('C002',job)
            passed('reconnect completes the same C002 job with five available rows', job_id=job, result_sha256=digest(results['C002']))
            page.screenshot(path=str(output/'03-c002-recovered.png'), full_page=True)
            page.reload();frame=open_analysis()
            expect(frame.locator('#results')).to_be_visible(timeout=30000)
            assert frame.locator('#result-meta dd').last.text_content()==job
            assert result('C002',job)==results['C002']
            passed('reload preserves C002 job and identical results')

            for company, other in [('C001','C002'),('C002','C001')]:
                other_job=results[other]['run_id']
                assert api(f'/agent2/api/v1/companies/{company}/he/jobs/{other_job}/result')['status']==404
            passed('cross-company job reads rejected despite shared T0-T4 identifiers')
            assert results['C001']['snapshot_id']!=results['C002']['snapshot_id']
            assert [r['score'] for r in results['C001']['rows']] != [r['score'] for r in results['C002']['rows']]
            passed('company snapshots and scores remain distinct')
            assert before_data=={k:digest(database_dump(node[k])) for k in before_data}
            assert before_keys==[hashlib.sha256(p.read_bytes()).hexdigest() for p in private_files]
            passed('model registry, source snapshots and protected keys unchanged')
            after_agents={a['id']:(a['state'],a['owned']) for a in api('/api/state')['value']['agents'] if a['id']!='agent2'}
            assert before_agents==after_agents
            passed('other agents unchanged')
            assert not errors,errors;passed('no browser JavaScript errors')
            report=dict(status='passed',checks=checks,count=len(checks),browser_errors=errors,
                portal=portal_url,data='existing C001/C002 synthetic packet',fault=fault,
                results=results,scope='disconnect after submission, before native worker claim; not a native-compute crash test')
            (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(status='passed',checks=len(checks))),flush=True)
        except Exception as e:
            (output/'failure.json').write_text(json.dumps(dict(status='failed',checks=checks,fault=fault,error=str(e)),ensure_ascii=False,indent=2),encoding='utf-8')
            try:page.screenshot(path=str(output/'failure.png'),full_page=True)
            except Exception:pass
            # Restore managed service if fault injection succeeded. No new jobs.
            if fault.get('job_id'):
                try:api('/api/agents/agent2/recover',{})
                except Exception:pass
            raise
        finally:
            context.close();browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--portal',default='http://127.0.0.1:8800')
    parser.add_argument('--packet',type=Path,default=ROOT/'.runtime/he-company-demo')
    parser.add_argument('--login-timeout',type=int,default=900)
    args=parser.parse_args()
    if args.portal!='http://127.0.0.1:8800':parser.error('this acceptance targets the configured desktop Portal 8800 only')
    run(args.output_dir.resolve(),args.portal,args.packet.resolve(),args.login_timeout)
