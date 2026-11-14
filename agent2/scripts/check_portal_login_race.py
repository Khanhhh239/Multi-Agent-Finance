"""Isolated browser regression: stale polls must not undo a newer login/logout."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent),str(ROOT/'scripts')]
from test_portal_auth import PortalHarness
from check_he4_p1_portal import page_request


def run(output):
    from playwright.sync_api import sync_playwright,expect
    with PortalHarness() as h,sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page();held=[];armed=None
        def intercept(route):
            nonlocal armed
            if armed and bool(route.request.headers.get('x-session'))==(armed=='authenticated'):
                armed=None
                response=route.fetch();held.append((route,response.body(),response.headers,response.status))
            else:route.continue_()
        page.route('**/api/state',intercept)
        page.goto(h.portal_url+'/#data');expect(page.locator('#gate')).to_be_visible()
        page.locator('#gate-password').fill('Synthetic-Race-2026!')
        page.locator('#gate-confirm-field input').fill('Synthetic-Race-2026!')
        armed='anonymous'
        for _ in range(100):
            if held:break
            page.wait_for_timeout(100)
        if not held:raise AssertionError('background pre-login poll not captured')
        page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        if page_request(page,'/agent2/api/v1/ui/context')['status']!=200:raise AssertionError('synthetic login failed')
        route,body,headers,status=held.pop();route.fulfill(status=status,body=body,headers=headers)
        page.wait_for_timeout(300)
        value=page_request(page,'/agent2/api/v1/ui/context')
        preserved=value['status']==200
        logout_safe=False
        if preserved:
            armed='authenticated'
            for _ in range(100):
                if held:break
                page.wait_for_timeout(100)
            if not held:raise AssertionError('authenticated poll not captured')
            page.locator('#lock-now').click();expect(page.locator('#gate')).to_be_visible(timeout=15000)
            route,body,headers,status=held.pop();route.fulfill(status=status,body=body,headers=headers)
            page.wait_for_timeout(300)
            logout_safe=page.locator('#gate').is_visible() and not page.locator('#intake').is_visible() and page_request(page,'/agent2/api/v1/ui/context')['status']==401
        report=dict(status='passed' if preserved and logout_safe else 'failed',stale_prelogin_poll_preserves_login=preserved,stale_authenticated_poll_does_not_reopen_after_logout=logout_safe,context_status=value['status'],servers='isolated fixture',credentials_exported=False,live_services_changed=False)
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
        browser.close();print(json.dumps(report))
        if report['status']!='passed':raise AssertionError('late poll changed the newer authentication state')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output.resolve())
