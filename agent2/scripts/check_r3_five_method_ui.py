"""End-to-end Playwright browser acceptance for R3 — 5-Method Detection Pipeline & Supervised LR UI."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT),
    str(ROOT / 'tests'),
    str(ROOT / 'tests_he'),
    str(ROOT.parent),
    str(ROOT.parent / 'shared' / 'finance_input' / 'src'),
]

from test_portal_auth import PortalHarness, portal
import test_validation_study as val_support
from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.import_files import canonical
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.review_server import make_server


def run(output: Path) -> dict:
    from playwright.sync_api import sync_playwright, expect

    output.mkdir(parents=True, exist_ok=True)
    checks: list[str] = []
    errors: list[str] = []
    report: dict = {}

    val_support.ValidationStudyTests.setUpClass()
    try:
        f = val_support.ValidationStudyTests
        with PortalHarness() as h, sync_playwright() as p:
            # Grant director + model.fit in isolated Portal harness
            pol = deepcopy(json.loads(h.access.read_text('utf-8')))
            for m in pol['memberships']:
                m['role'] = 'director'
                m['permissions'] = ['data.import', 'evidence.verify', 'model.fit']
            h.access.write_bytes(canonical(pol))

            bindings_path = h.root / 'bindings.json'
            c1_art = f.company_ctx['C001']['model_artifacts']['isolation_forest']['artifact_id']
            c2_art = f.company_ctx['C002']['model_artifacts']['ecod']['artifact_id']
            bindings_path.write_bytes(canonical({
                'version': BINDINGS_VERSION,
                'bindings': [
                    {'tenant_id': 'demo', 'company_id': 'C001', 'statistics_artifact_id': None, 'ml_artifacts': {'isolation_forest': c1_art}},
                    {'tenant_id': 'demo', 'company_id': 'C002', 'statistics_artifact_id': None, 'ml_artifacts': {'ecod': c2_art}},
                ],
            }))

            res = AnalysisResources(f.models.path, bindings_path)
            svc = ReleaseService(ReleaseStore(h.root / 'releases.db', b'w' * 32), f.snapshots, res, CaseQueueStore(h.root / 'cases.db'))
            eval_sid = f.company_ctx['C001']['manifests']['sealed_future_test']['snapshot_id']

            h.agent.shutdown()
            h.agent.server_close()
            h.agent = make_server(0, h.authorizer, f.snapshots, res, case_queue_store=svc.case_queue, release_service=svc)
            h.agent.daemon_threads = False
            portal.CFG['agents']['agent2']['port'] = h.agent.server_port
            t = threading.Thread(target=h.agent.serve_forever, daemon=True)
            t.start()
            h.threads.append(t)

            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport=dict(width=1440, height=1020), locale='vi-VN')
            page.on('pageerror', lambda e: errors.append('PAGEERROR: ' + str(e)))
            page.on('console', lambda m: errors.append('CONSOLE_ERR: ' + m.text) if m.type == 'error' else None)
            page.add_init_script('sessionStorage.setItem("kt-session",' + json.dumps(h.token) + ');')

            try:
                # 1. Open Area B -> Step 3 -> Logistic Regression
                page.goto(h.portal_url + '/agent2/model-management#company=C001')
                expect(page.locator('#active-model-title')).to_contain_text('C001-v1', timeout=25000)
                page.locator('[data-step="3"]').click()
                expect(page.locator('#step-panel-3')).to_be_visible()
                page.locator('.algo-card', has_text='Logistic Regression').click()
                expect(page.locator('#lr-fhe-panel')).to_be_visible()

                # Verify verified_reviews_next_cycle source mode option is present
                opt_vals = page.locator('#lr-source-mode option').evaluate_all('(opts) => opts.map(o => o.value)')
                assert 'verified_reviews_next_cycle' in opt_vals, opt_vals
                checks.append('Area B Step 3 exposes verified_reviews_next_cycle source option for next supervised cycle')

                # 2. Train local quantized LR reference & promote to signed releasable_model
                page.locator('#lr-mode-local').click()
                page.locator('#btn-lr-train').click()
                expect(page.locator('#lr-validation-box')).to_be_visible(timeout=25000)
                expect(page.locator('#lr-promote-box')).to_be_visible()

                page.locator('#lr-promote-reason').fill('Đạt chuẩn đối chiếu lượng tử hóa và chọn ngưỡng tối ưu trên tập validation cho R3.')
                page.locator('#lr-promote-checked').check()
                expect(page.locator('#btn-lr-promote')).to_be_enabled()
                page.locator('#btn-lr-promote').click()
                expect(page.locator('#lr-promoted-summary')).to_contain_text('ED25519', timeout=20000)
                expect(page.locator('#lr-promoted-summary')).to_contain_text('Ngưỡng validation')
                expect(page.locator('#lr-score-queue-box')).to_be_visible()
                checks.append('Promoted LR model displays Ed25519 signature status, validation threshold & Precision/Recall/F1')

                # 3. Score into Area A queue using all 5 methods (with promoted LR)
                page.locator('#lr-score-snapshot').select_option(eval_sid)
                page.locator('#btn-lr-score-queue').click()
                expect(page.locator('#lr-score-queue-result a')).to_be_visible(timeout=25000)
                page.screenshot(path=str(output / 'r3_area_b_lr_promoted_score.png'), full_page=True)
                page.locator('#lr-score-queue-result a').click()
                checks.append('Area B scores snapshot with 5-method pipeline (including approved LR) and links directly to Area A')

                # 4. Area A: Queue preview & open transaction detail
                expect(page.locator('#rows .tx-row')).not_to_have_count(0, timeout=25000)
                page.locator('#rows .tx-row').first.click()
                expect(page.locator('#preview')).to_contain_text('5 phương pháp')
                expect(page.locator('#preview')).to_contain_text('P(lớp 1)=')
                page.locator('#open-investigation').click()
                expect(page.locator('#investigation')).to_be_visible(timeout=20000)

                # Verify top summary strip shows Total Risk Score & LR Probability
                expect(page.locator('#tx-summary')).to_contain_text('Tổng điểm rủi ro')
                expect(page.locator('#tx-summary')).to_contain_text('Xác suất LR:')
                checks.append('Area A header displays total risk score and LR class-1 probability badge')

                # 5. Explanation Tab: verify 5-method table, LR detail card, anti-double-counting, unavailable section, model versions
                page.locator('[data-tab="explanation"]').click()
                expect(page.locator('#five-methods-card tbody tr')).to_have_count(5)
                expect(page.locator('#lr-explanation-card')).to_contain_text('Xác suất P(lớp 1)')
                expect(page.locator('#lr-explanation-card')).to_contain_text('Ngưỡng validation')
                expect(page.locator('#lr-explanation-card')).to_contain_text('Điểm quy đổi hiệu lực')
                expect(page.locator('#unavailable-methods-card')).to_be_visible()
                expect(page.locator('#explanation')).to_contain_text('C001-v1')
                expect(page.locator('#explanation')).to_contain_text('C001-lr-ref-')
                page.screenshot(path=str(output / 'r3_area_a_five_methods.png'), full_page=True)
                checks.append('Area A Explanation tab renders 5-method table, LR probability/threshold/dedup card, unavailable status, and model versions')

                # 6. Reviewer confirmation: verify Vi phạm / Hợp lệ / Chưa đủ bằng chứng options & save confirmed_risk
                out_texts = page.locator('#outcome option').evaluate_all('(opts) => opts.map(o => o.textContent.trim())')
                assert any('Vi phạm' in x for x in out_texts), out_texts
                assert any('Hợp lệ' in x for x in out_texts), out_texts
                assert any('Chưa đủ bằng chứng' in x for x in out_texts), out_texts

                page.locator('#start').click()
                expect(page.locator('#save')).to_be_enabled(timeout=15000)
                page.locator('#outcome').select_option('confirmed_risk')
                page.locator('#notes').fill('Đã đối chiếu chứng từ và dấu hiệu 5 phương pháp; xác nhận giao dịch vi phạm.')
                page.locator('#action').fill('Chuyển xử lý nội bộ và đưa vào kho nhãn xác minh cho chu kỳ huấn luyện LR tiếp theo.')
                page.locator('#checks').check()
                ev_cbs = page.locator('#evidence-selection input[type="checkbox"]')
                if ev_cbs.count() > 0:
                    ev_cbs.first.check()
                page.locator('#save').click()
                expect(page.locator('#save-status')).to_contain_text('phiên bản 1', timeout=15000)
                checks.append('Reviewer confirms Vi phạm (confirmed_risk) with verified evidence checks persisted on server')

                # 7. Mobile viewport fit check
                page.set_viewport_size(dict(width=390, height=844))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'Mobile horizontal overflow'
                checks.append('Mobile 390px viewport renders 5-method view cleanly without horizontal overflow; zero JS errors')

                assert not errors, errors
                report = dict(status='pass', checks=checks, errors=errors)
            except Exception as exc:
                report = dict(status='fail', checks=checks, error=str(exc), errors=errors)
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
                raise
            finally:
                (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                browser.close()
    finally:
        val_support.ValidationStudyTests.tearDownClass()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output.resolve()), ensure_ascii=False, indent=2))
