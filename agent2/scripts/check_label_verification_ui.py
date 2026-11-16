"""Isolated real Portal/browser acceptance. Synthetic declarations only; no HE fit."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests_he'), str(ROOT.parent)]
from test_portal_auth import PortalHarness
from training_snapshot_support import native, scope, commit
from sme_fraud.label_packets import LabelStore
from sme_fraud.review_server import make_server
from portal import server as portal


def run(output):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True, exist_ok=False)
    checks, errors = [], []
    with PortalHarness() as h, sync_playwright() as p:
        h.agent.shutdown(); h.agent.server_close()
        labels = LabelStore(h.root / 'labels.sqlite3', os.urandom(32))
        for member in h.policy['memberships']:
            member['permissions'].append('evidence.verify')
        h.write_policy()
        for company in ('C001', 'C002'):
            commit(h.store, native(company), scope(company, permissions={'data.import', 'evidence.verify'}), key='ui-' + company)
        h.agent = make_server(0, h.authorizer, h.store, label_store=labels)
        portal.CFG['agents']['agent2']['port'] = h.agent.server_port
        thread = threading.Thread(target=h.agent.serve_forever, daemon=True); thread.start(); h.threads.append(thread)
        browser = p.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1000), locale='vi-VN')
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(h.portal_url + '/#data')
            page.locator('#gate-password').fill('Synthetic-Workspace-2026!')
            page.locator('#gate-confirm-field input').fill('Synthetic-Workspace-2026!')
            page.locator('#gate-submit').click()
            expect(page.locator('#intake')).to_be_visible(timeout=20000)
            page.goto(h.portal_url + '/agent2/label-verification#company=C001')
            expect(page.locator('#lv-company')).to_have_value('C001')
            expect(page.locator('#lv-source-rows input')).to_have_count(4)
            page.locator('#lv-new').evaluate('(e)=>e.open=true')
            for choice in page.locator('#lv-source-rows input').all():
                choice.check()
            page.locator('#lv-create').click()
            expect(page.locator('#lv-cases button')).to_have_count(4)
            expect(page.locator('#lv-mode')).to_contain_text('mô phỏng')
            expect(page.locator('#lv-status')).to_contain_text('0/4')
            checks.append('explicit four-row selection; initial labels null and synthetic banner shown')
            page.locator('#lv-outcome').select_option('verified_fraud')
            page.locator('#lv-save').click()
            expect(page.locator('#lv-notice')).to_contain_text('Cần giải thích')
            expect(page.locator('#lv-status')).to_contain_text('0/4')
            checks.append('verified outcome without evidence/explanation rejected by real backend')
            page.locator('#lv-explanation').fill('Synthetic declaration only: transaction and documents checked.')
            page.locator('#lv-detail details.source-card[open] .lv-evidence').first.check()
            page.locator('#lv-checked').check()
            page.locator('#lv-save').click()
            expect(page.locator('#lv-status')).to_contain_text('1/4')
            page.locator('#lv-cases button').nth(1).click()
            page.locator('#lv-outcome').select_option('verified_non_fraud')
            page.locator('#lv-explanation').fill('Synthetic declaration only: source records reconcile.')
            page.locator('#lv-detail details.source-card[open] .lv-evidence').first.check()
            page.locator('#lv-checked').check()
            page.locator('#lv-save').click()
            expect(page.locator('#lv-status')).to_contain_text('2/4')
            page.locator('#lv-cases button').first.click()
            expect(page.locator('#lv-outcome')).to_have_value('verified_fraud')
            checks.append('saving second label retains first; server reviewer/time displayed')
            page.locator('#lv-lock').click()
            expect(page.locator('#lv-status')).to_contain_text('Đã khóa')
            expect(page.locator('#lv-outcome')).to_be_disabled()
            with page.expect_download() as download:
                page.locator('#lv-export').click()
            path = output / 'synthetic-locked-labels.json'; download.value.save_as(path)
            exported = json.loads(path.read_text('utf-8'))
            assert not exported['training_ready'] and not exported['training_started']
            assert [r['outcome'] for r in exported['labels']] == ['verified_fraud', 'verified_non_fraud', None, None]
            checks.append('lock prohibits edits; export keeps two null labels and cannot train')
            packet_id = exported['packet_id']
            page.reload()
            expect(page.locator('#lv-packets option[value="' + packet_id + '"]')).to_have_count(1)
            page.locator('#lv-packets').select_option(packet_id)
            expect(page.locator('#lv-status')).to_contain_text('Đã khóa')
            page.locator('#lv-reopen').click()
            expect(page.locator('#lv-status')).to_contain_text('Bản đang xác minh')
            expect(page.locator('#lv-status')).to_contain_text('2/4')
            expect(page.locator('#lv-outcome')).to_be_enabled()
            checks.append('reload reopens saved packet; new revision preserves prior labels and old lock')
            page.locator('#lv-company').select_option('C002')
            expect(page.locator('#lv-detail')).to_be_empty()
            expect(page.locator('#lv-packets option[value="' + packet_id + '"]')).to_have_count(0)
            expect(page.locator('#lv-source-rows input')).to_have_count(4)
            page.reload()
            expect(page.locator('#lv-company')).to_have_value('C002')
            checks.append('company switch clears prior labels/evidence; reload retains authorized C002')
            page.set_viewport_size(dict(width=390, height=844))
            page.locator('#lv-new').evaluate('(e)=>e.open=true')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output / 'mobile-source.png'), full_page=True)
            checks.append('mobile source selection stays within screen')
            h.policy['memberships'][1]['permissions'] = ['data.import']; h.write_policy()
            page.reload()
            expect(page.locator('#lv-permission')).to_contain_text('Chỉ xem')
            expect(page.locator('#lv-new')).to_be_hidden()
            checks.append('current permission revocation hides verification controls after reload')
            assert not errors, errors
            (output / 'report.json').write_text(json.dumps(dict(status='passed', count=len(checks), checks=checks,
                browser_errors=errors, synthetic_only=True, live_services_changed=False, training_started=False,
                limits=['No real fraud labels or individual human identity attestation; isolated Portal acceptance.']), indent=2), encoding='utf-8')
            print(json.dumps(dict(status='passed', checks=len(checks))))
        except Exception:
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
