"""Real isolated Portal routing acceptance; no live credentials or databases.

Uses the real HTTP authorization, import/analysis and workspace backends.
HE navigation is covered without submitting a new encrypted job. This is
not a claim about HE circuit accuracy or recovery.
"""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests_he'), str(ROOT.parent)]
from web_support import WebHarness


def run(output):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True, exist_ok=False)
    checks, errors = [], []
    with WebHarness() as f, sync_playwright() as p:
        # Select the production HE4 landing page without replacing routing,
        # authorization or dataset APIs. No HE4 jobs/circuits are exercised here.
        f.backend.settings = None
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1050), locale='vi-VN')
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(f.h.portal_url + '/#data')
            page.locator('#gate-password').fill('Synthetic-Workspace-2026!')
            page.locator('#gate-confirm-field input').fill('Synthetic-Workspace-2026!')
            page.locator('#gate-submit').click()
            expect(page.locator('#intake')).to_be_visible(timeout=20000)

            def frame():
                return page.frame_locator('#agent-frame')

            def workspace(company):
                expect(frame().locator('#ws-company')).to_have_value(company, timeout=30000)
                expect(frame().locator('#ws-home')).to_be_visible(timeout=30000)

            def select_memory(company, screen='workspace', **extra):
                status, context = f.h.request('/agent2/api/v1/ui/context')
                assert status == 200, context
                saved = dict(version=1, actor=context['actor_id'], context=context['context_id'],
                             company=company, page=screen, **extra)
                page.evaluate('(v)=>sessionStorage.setItem("agent2.company.selection",JSON.stringify(v))', saved)

            page.goto(f.h.portal_url + '/#agent2')
            workspace('C001')
            frame().locator('#ws-company').select_option('C002')
            workspace('C002')
            page.reload()
            workspace('C002')
            checks.append('Outer Portal reload retains workspace C002 instead of default C001')
            with page.expect_popup() as opened:
                page.locator('#agent-newtab').click()
            separate = opened.value
            expect(separate.locator('#ws-company')).to_have_value('C002', timeout=30000)
            expect(separate.locator('#ws-home')).to_be_visible(timeout=30000)
            separate.close()
            checks.append('Open separate tab retains authorized C002 with a fresh context check')

            frame().get_by_role('link', name='Nhập dữ liệu mới', exact=True).click()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            frame().locator('#file').set_input_files(ROOT / 'examples/rule_bridge_models/C002_5_giao_dich.json')
            frame().locator('#validate').click()
            expect(frame().locator('#save-panel')).to_be_visible(timeout=30000)
            frame().locator('#ack').check()
            frame().locator('#save').click()
            expect(frame().locator('#analysis-panel')).to_be_visible(timeout=30000)
            snapshot = frame().locator('#snapshot-meta dd').first.text_content()
            as_of = frame().locator('#as-of').input_value()
            with page.expect_response(lambda r: r.url.endswith('/analyze'), timeout=60000) as reply:
                frame().locator('#analyze').click()
            result = reply.value.json()
            assert reply.value.status == 200 and result['row_count'] == 5, result
            analysis = result['analysis_id']
            page.reload()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            expect(frame().locator('#analysis-panel')).to_be_visible(timeout=30000)
            expect(frame().locator('#snapshot-meta dd').first).to_have_text(snapshot)
            expect(frame().locator('#as-of')).to_have_value(as_of)
            with page.expect_response(lambda r: r.url.endswith('/analyze'), timeout=60000) as reply:
                frame().locator('#analyze').click()
            restored = reply.value.json()
            assert reply.value.status == 200 and restored['analysis_id'] == analysis
            checks.append('Real import/commit/analyze of five C002 rows: outer reload restores same screen, snapshot, as_of and analysis ID')
            page.evaluate('sessionStorage.removeItem("agent2.company.selection");localStorage.setItem("agent2.workspace.company","C001")')
            page.reload()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            expect(frame().locator('#snapshot-meta dd').first).to_have_text(snapshot, timeout=30000)
            checks.append('Legacy C002 import preference migrates ahead of stale workspace C001')
            page.screenshot(path=str(output / '01-C002-reloaded.png'), full_page=True)

            frame().get_by_role('link', name='Công việc và báo cáo', exact=True).click()
            workspace('C002')
            checks.append('Import-to-workspace navigation carries C002')
            frame().locator('#ws-company').select_option('C001')
            workspace('C001')
            frame().get_by_role('link', name='Nhập dữ liệu mới', exact=True).click()
            expect(frame().locator('#company')).to_have_value('C001', timeout=30000)
            expect(frame().locator('#analysis-panel')).to_be_hidden()
            checks.append('Switching to C001 clears C002 snapshot/results and carries company into import')
            frame().locator('#company').select_option('C002')
            page.reload()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            checks.append('Company selection persists even before saving another file')

            # Explicit links take precedence over an authorized stored selection.
            frame().locator('header a[href*="workspace"]').first.evaluate(
                '(a)=>{a.href="/agent2/workspace#company=C001";a.click();}')
            workspace('C001')
            page.reload()
            workspace('C001')
            checks.append('Explicit authorized company deep link overrides stored C002 and survives outer reload')

            frame().locator('#ws-company').select_option('C002')
            workspace('C002')
            frame().get_by_role('link', name='Chạy phân tích', exact=True).click()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            expect(frame().locator('#dataset option')).not_to_have_count(0, timeout=30000)
            dataset = frame().locator('#dataset').input_value()
            page.reload()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            expect(frame().locator('#dataset')).to_have_value(dataset, timeout=30000)
            checks.append('Encrypted-analysis screen and C002 dataset survive outer reload without changing/submitting jobs')

            # Navigate to settings without a company hash: shared selection applies.
            frame().locator('header a[href*="workspace"]').first.evaluate(
                '(a)=>{a.href="/agent2/analysis-settings";a.click();}')
            expect(frame().locator('#fit')).to_be_disabled(timeout=30000)
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            page.wait_for_function('JSON.parse(sessionStorage.getItem("agent2.company.selection"))?.page==="analysis-settings"')
            page.reload()
            expect(frame().locator('#company')).to_have_value('C002', timeout=30000)
            expect(frame().locator('#fit')).to_be_disabled()
            checks.append('Settings inherits C002 and reloads that page; routing does not grant fit permission')

            # Removing grants invalidates the stored route before iframe loading.
            f.h.policy['memberships'][1]['permissions'] = []
            f.h.write_policy()
            company_requests = []
            def collect(request):
                if '/agent2/api/v1/companies/' in request.url:
                    company_requests.append(request.url.split('/companies/', 1)[1].split('/', 1)[0])
            page.on('request', collect)
            page.reload()
            workspace('C001')
            expect(frame().locator('#ws-company option')).to_have_count(1)
            expect(frame().locator('#ws-detail')).to_be_empty()
            assert 'C002' not in company_requests, company_requests
            assert f.h.request(f.h.url('snapshots/' + snapshot, 'C002'))[0] == 403
            checks.append('Revoked C002 grant: fresh context falls back to authorized C001, no C002 data request, server still rejects snapshot read')
            page.remove_listener('request', collect)
            frame().locator('header a[href*="workspace"]').first.evaluate(
                '(a)=>{a.href="/agent2/workspace#company=C002&run=herun_00000000000000000000000000000000";a.click();}')
            workspace('C001')
            expect(frame().locator('#ws-run')).to_be_hidden()
            checks.append('Revoked deep link drops foreign run and cannot retain private review state')

            f.h.policy['memberships'][0]['permissions'] = []
            f.h.write_policy()
            page.reload()
            expect(frame().locator('#ws-company option')).to_have_count(0, timeout=30000)
            expect(frame().locator('#ws-home')).to_be_hidden()
            expect(frame().locator('#ws-run')).to_be_hidden()
            checks.append('No company grants shows no company or private content instead of silently defaulting to C001')

            for member in f.h.policy['memberships']:
                member['permissions'] = ['data.import']
            f.h.write_policy()
            select_memory('C002')
            page.evaluate('localStorage.setItem("agent2.workspace.company","C002")')
            f.h.policy['actor_id'] = 'new-routing-reviewer'
            f.h.write_policy()
            page.reload()
            workspace('C001')
            checks.append('Changed actor ignores previous actor company and snapshot preferences')

            select_memory('C002', 'https://invalid.example/steal')
            page.reload()
            workspace('C002')
            assert page.locator('#agent-frame').get_attribute('src').startswith(f.h.portal_url + '/agent2/')
            checks.append('Stored arbitrary page cannot navigate iframe outside allowlisted Agent2 pages')
            page.evaluate('sessionStorage.setItem("agent2.company.selection","{broken")')
            page.reload()
            workspace('C001')
            checks.append('Malformed stored route is ignored without JavaScript error')

            # A real context response is held while the user leaves Agent2.
            held = threading.Event()
            def delayed(route):
                response = route.fetch()
                held.set()
                page.locator('.nav-link[data-view="overview"]').click()
                route.fulfill(response=response)
            page.route('**/agent2/api/v1/ui/context', delayed, times=1)
            page.goto(f.h.portal_url + '/#overview')
            page.goto(f.h.portal_url + '/#agent2')
            expect(page.locator('#view-overview')).to_be_visible(timeout=30000)
            assert held.is_set()
            expect(page.locator('#agent-frame')).not_to_have_attribute('src', timeout=30000)
            checks.append('Late context response after leaving Agent2 cannot reopen the old iframe')
            assert not errors, errors
            report = dict(status='passed', count=len(checks), checks=checks, browser_errors=errors,
                          servers='real isolated Portal + enterprise backend', synthetic_data=True,
                          live_services_changed=False, he_jobs_submitted=False,
                          he4_landing_metadata_fixture=True,
                          limits=['Settings lifecycle service is not configured in this fixture; only routing and disabled controls checked.',
                                  'No live Portal login or human business validation claimed.'])
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(dict(status='passed', checks=len(checks))))
        except Exception as error:
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            debug = dict(frames=[dict(url=x.url, text=x.locator('body').inner_text()[:800]) for x in page.frames],
                         iframe=page.locator('#agent-frame').evaluate('(e)=>({src:e.getAttribute("src"), marker:e.dataset.src,hidden:e.hidden})'))
            (output / 'failure.json').write_text(json.dumps(dict(checks=checks, error=str(error), browser_errors=errors, debug=debug), indent=2), encoding='utf-8')
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())
