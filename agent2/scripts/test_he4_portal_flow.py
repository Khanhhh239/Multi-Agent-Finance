"""Real Portal fixture + two native HE workers + per-company protected keys."""
import argparse
import json
from pathlib import Path
import socket
import sys
import threading
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT/'tests'),str(ROOT.parent)]
from web_support import WebHarness
from portal.agent2_he4_runtime import LinuxRuntime,linux_path
from experiments.he4.bundle import build
from experiments.he4.windows_bridge import CryptoBridge
from experiments.he4.web import FourWorkbench
from experiments.he_inference.protocol import canonical,public_hex
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.review_server import make_server
from portal import server as portal


def run(output,build_root):
    from playwright.sync_api import sync_playwright,expect
    if output.exists():raise ValueError('new output directory required')
    output.mkdir(parents=True);started=time.monotonic();checks=[];errors=[]
    builds={k:(build_root/p).resolve() for k,p in {'statistics':'build-statistics-v1','rules':'build-rules-difference-v1','graph':'build-graph-difference-v1'}.items()}
    prepared=output.parent/'portal-key-contexts';prepared.mkdir(exist_ok=True)
    with WebHarness(state_key_file=prepared/'wrapping.dpapi.json') as f:
        root=f.pair.enterprise/'four';root.mkdir();pins=[]
        for company in ('C001','C002'):
            config=dict(f.pair.env['configs'][company],version='company-fit-config/1.0.0',method_id='robust_z',profile_id='he4-portal-synthetic')
            fit=run_fit_job(f.h.store,f.pair.env['models'],f.pair.env['auth'],f.pair.env['fit_header'],company,config,'fit-portal-four-'+company)
            if fit.get('error'):raise AssertionError(fit)
            pins.append(dict(tenant_id='demo',company_id=company,statistics_artifact_id=fit['job']['artifact_id']))
        (root/'bindings.json').write_bytes(canonical(dict(version='he4-company-bindings/1.0.0',bindings=pins)))
        bridge=CryptoBridge(prepared/'private',f.pair.state_key_path)
        for company in ('C001','C002'):
            scope=f.pair.env['auth'].authorize(f.pair.env['fit_header'],company)
            for profile,bundle in builds.items():
                _,vault,_,_=bridge.context(scope,bundle)
                if not (vault/'context.sealed').exists():bridge.provision(scope,bundle)
                print(json.dumps(dict(stage='prepared',company=company,profile=profile)),flush=True)
        cloud=f.pair.worker_root/'four';cloud.mkdir();build(cloud/'bundle');key=Ed25519PrivateKey.generate();(cloud/'signing.hex').write_text(key.private_bytes_raw().hex())
        (cloud/'grants.json').write_bytes(canonical(f.pair.grants))
        config=cloud/'worker.json';config.write_bytes(canonical(dict(version='he4-worker/0.1.0',state_dir=linux_path(cloud/'state'),grants_file=linux_path(cloud/'grants.json'),signing_key_file=linux_path(cloud/'signing.hex'),builds={k:linux_path(v) for k,v in builds.items()})))
        with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
        enterprise=dict(version='he4-enterprise/1.0.0',state_dir=str(root/'jobs'),enterprise_root=str(prepared/'private'),state_key_file=str(f.pair.state_key_path),worker_url=f'http://127.0.0.1:{port}',worker_verify_key=public_hex(key),builds={k:str(v) for k,v in builds.items()},bindings_file=str(root/'bindings.json'),linux_distro='Debian',linux_python='/home/sang/.local/share/agent2/he4/bin/python')
        (root/'node.json').write_bytes(canonical(enterprise))
        runtime=LinuxRuntime(dict(bundle=str(cloud/'bundle'),config=str(config),port=port,distro='Debian',python=enterprise['linux_python']),ROOT,f.pair.node_config,root/'node.json',Path(sys.executable),output/'logs')
        try:
            runtime.start();checks.append('actual managed WSL preflight verifies all company contexts and signed worker readiness')
            print(json.dumps(dict(stage='worker-ready')),flush=True)
            f.h.agent.shutdown();f.h.agent.server_close()
            f.backend=FourWorkbench(f.node,f.bindings,enterprise)
            f.h.agent=make_server(0,f.h.authorizer,f.h.store,he_backend=f.backend);portal.CFG['agents']['agent2']['port']=f.h.agent.server_port
            thread=threading.Thread(target=f.h.agent.serve_forever,daemon=True);thread.start();f.h.threads.append(thread)
            results={}
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f.h.portal_url+'/agent2/encrypted-analysis');page.locator('#portal-login').click()
                page.locator('#gate-password').fill('Synthetic-HE-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-HE-2026!');page.locator('#gate-submit').click()
                expect(page.locator('#intake')).to_be_visible(timeout=15000)
                for company in ('C001','C002'):
                    page.goto(f.h.portal_url+'/agent2/encrypted-analysis');expect(page.locator('#company option')).to_have_count(2)
                    page.locator('#company').select_option(company);expect(page.locator('#dataset option')).to_have_count(2)
                    page.locator('#dataset').select_option(f.pair.env['queries'][company]);expect(page.locator('#run')).to_be_enabled(timeout=30000);page.locator('#run').click()
                    expect(page.locator('#rows .transaction')).to_have_count(5,timeout=20*60*1000)
                    run_id=page.locator('#result-meta dd').last.inner_text();results[company]=run_id
                    blocks=page.locator('#rows .transaction').first
                    for text in ('Đối chiếu thanh toán','So sánh với lịch sử doanh nghiệp','Quan hệ giữa các đối tượng','Phân tích bất thường'):expect(blocks).to_contain_text(text)
                    expect(page.locator('#review-cases article')).to_have_count(5,timeout=30000)
                    page.screenshot(path=str(output/(company+'.png')),full_page=True)
                    page.reload();expect(page.locator('#rows .transaction')).to_have_count(5,timeout=30000);expect(page.locator('#result-meta dd').last).to_have_text(run_id)
                    checks.append(company+': five native encrypted results, all four branch statuses, review cases and same run after reload')
                    print(json.dumps(dict(stage='completed',company=company)),flush=True)
                if results['C001']==results['C002']:raise AssertionError('company run collision')
                if errors:raise AssertionError(errors)
                browser.close()
            checks.append('no JavaScript errors and no company run collision')
            report=dict(status='passed',actual_fhe=True,portal_fixture=True,simulated_data=True,checks=checks,count=len(checks),browser_errors=errors,seconds=time.monotonic()-started,live_services_changed=False)
            (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
        finally:runtime.stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--build-root',type=Path,required=True);a=p.parse_args();run(a.output.resolve(),a.build_root.resolve())
