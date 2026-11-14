"""Isolated Portal manager lifecycle and company-role UI acceptance."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT/'tests'),str(ROOT.parent)]
from test_he4_config_api import ConfigurationAPI


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[];ConfigurationAPI.setUpClass();f=ConfigurationAPI.f
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f.h.portal_url+'/#data');page.locator('#gate-password').fill('Synthetic-HE-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-HE-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
            page.goto(f.h.portal_url+'/agent2/analysis-settings');page.locator('#company').select_option('C002');expect(page.locator('#settings')).to_be_visible();expect(page.locator('#draft')).to_be_disabled();expect(page.locator('#permission')).to_contain_text('quyền xem')
            checks.append('manager without model.fit can read but cannot change configuration')
            f.h.policy['memberships'][1]['permissions'].append('model.fit');f.h.write_policy();page.reload();page.locator('#company').select_option('C002');expect(page.locator('#draft')).to_be_enabled()
            cfg=f.pair.env['configs']['C002'];page.locator('#snapshot').select_option(cfg['snapshot_id'])
            for field in ('history_start','history_end','reference_start','reference_end','evaluation_start'):page.locator('#'+field).fill(cfg[field][:19])
            page.locator('#minimum_history').fill('20');page.locator('#evaluation_mode').select_option('backtest');page.locator('#draft').click()
            try:expect(page.locator('#fit')).to_be_enabled()
            except Exception:
                page.screenshot(path=str(output/'draft-failure.png'),full_page=True)
                raise AssertionError('draft failed: '+page.locator('#notice').inner_text())
            page.locator('#fit').click();expect(page.locator('#activate')).to_be_enabled(timeout=40000)
            expect(page.locator('#status')).to_contain_text('Chưa có kết luận');checks.append('explicit draft then offline fit prepares both company models')
            page.locator('#activate').click();expect(page.locator('#status')).to_contain_text('Đã kích hoạt');expect(page.locator('#activate')).to_be_disabled();page.reload();page.locator('#company').select_option('C002');expect(page.locator('#status')).to_contain_text('Đã kích hoạt');checks.append('activation and model revision survive browser reload')
            page.screenshot(path=str(output/'manager.png'),full_page=True)
            page.locator('#company').select_option('C001');expect(page.locator('#settings')).to_be_hidden();expect(page.locator('#permission')).to_contain_text('chưa được cấp quyền');expect(page.locator('#history')).to_have_text('');checks.append('switching to a reader company clears private manager configuration')
            if errors:raise AssertionError(errors)
            browser.close()
        report=dict(status='passed',checks=checks,count=len(checks),browser_errors=errors,real_models=True,circuit_metadata_mocked=True,live_services_changed=False)
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:ConfigurationAPI.tearDownClass()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())
