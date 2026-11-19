"""End-to-end Playwright browser acceptance for R5 — Validation (9 Metrics), 4-Way Comparison & 9-State LR Model Registry."""
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

            h.agent.shutdown()
            h.agent.server_close()
            h.agent = make_server(0, h.authorizer, f.snapshots, res, case_queue_store=svc.case_queue, release_service=svc)
            h.agent.daemon_threads = False
            portal.CFG['agents']['agent2']['port'] = h.agent.server_port
            t = threading.Thread(target=h.agent.serve_forever, daemon=True)
            t.start()
            h.threads.append(t)

            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport=dict(width=1440, height=1080), locale='vi-VN')
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
                expect(page.locator('#lr-registry-section')).to_be_visible()
                expect(page.locator('#lr-reg-active-badge')).to_contain_text('Chưa có LR ACTIVE')

                # 2. Train local quantized reference LR
                page.locator('#lr-mode-local').click()
                page.locator('#btn-lr-train').click()
                expect(page.locator('#lr-validation-box')).to_be_visible(timeout=25000)
                expect(page.locator('#btn-lr-reg-register')).to_be_enabled()
                checks.append('Trained LR job enables registration into R5 LR Model Registry')

                # 3. Register v1 -> VALIDATING with quality_approved = false
                page.locator('#btn-lr-reg-register').click()
                expect(page.locator('#lr-reg-detail-box')).to_be_visible(timeout=15000)
                expect(page.locator('#lr-reg-title')).to_contain_text('C001-lr-v1')
                expect(page.locator('#lr-reg-state-pill')).to_have_text('VALIDATING')
                expect(page.locator('#lr-reg-qa-pill')).to_have_text('quality_approved = false')
                expect(page.locator('#btn-lr-tr-approve')).to_be_disabled()
                expect(page.locator('#btn-lr-tr-activate')).to_be_disabled()
                checks.append('Registered v1 starts in VALIDATING with quality_approved=false and approval/activation disabled')

                # 4. Validate on small_job_holdout -> BLOCKED (insufficient positives)
                page.locator('#lr-reg-eval-mode').select_option('small_job_holdout')
                page.locator('#btn-lr-reg-validate').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('BLOCKED', timeout=20000)
                expect(page.locator('#lr-reg-qa-pill')).to_have_text('quality_approved = false')
                expect(page.locator('#lr-reg-gate-grid .chk-item.fail')).not_to_have_count(0)
                expect(page.locator('#btn-lr-tr-shadow')).to_be_disabled()
                expect(page.locator('#btn-lr-tr-approve')).to_be_disabled()
                checks.append('Small holdout (only 2 positives) is strictly BLOCKED with quality_approved=false')

                # 5. Re-validate on representative_sme_benchmark -> CANDIDATE + 9 metrics + 4-way comparison
                page.locator('#lr-reg-eval-mode').select_option('representative_sme_benchmark')
                page.locator('#btn-lr-reg-validate').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('CANDIDATE', timeout=20000)
                expect(page.locator('#lr-reg-qa-pill')).to_have_text('quality_approved = true')
                expect(page.locator('#lr-reg-metrics-grid .kpi-box')).to_have_count(9)
                expect(page.locator('#lr-reg-gate-grid .chk-item.fail')).to_have_count(0)
                expect(page.locator('#lr-reg-compare-body tr')).to_have_count(5)
                expect(page.locator('#lr-reg-incremental-box')).to_contain_text('giá trị bổ sung thực sự')
                checks.append('Representative SME benchmark passes Quality Gate -> CANDIDATE with 9 metrics, 5 comparison rows & positive incremental value')

                # 6. Walk CANDIDATE -> SHADOW -> APPROVED -> ACTIVE
                page.locator('#lr-reg-reason').fill('Đưa phiên bản C001-lr-v1 vào chạy thử SHADOW sau khi đạt cổng chất lượng R5.')
                expect(page.locator('#btn-lr-tr-shadow')).to_be_enabled()
                page.locator('#btn-lr-tr-shadow').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('SHADOW', timeout=15000)

                page.locator('#lr-reg-reason').fill('Đã đối chiếu đầy đủ 9 metrics, Recall > 90%, FP/1000 trong ngưỡng và giá trị bổ sung 5 phương pháp.')
                # Must stay disabled without evidence confirmation checkbox!
                expect(page.locator('#btn-lr-tr-approve')).to_be_disabled()
                page.locator('#lr-reg-reviewed').check()
                expect(page.locator('#btn-lr-tr-approve')).to_be_enabled()
                page.locator('#btn-lr-tr-approve').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('APPROVED', timeout=15000)
                expect(page.locator('#lr-reg-meta-dl')).to_contain_text('Ed25519')

                page.locator('#lr-reg-reason').fill('Kích hoạt phiên bản C001-lr-v1 làm mô hình LR chính thức trong pipeline Agent2.')
                expect(page.locator('#btn-lr-tr-activate')).to_be_enabled()
                page.locator('#btn-lr-tr-activate').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('ACTIVE', timeout=15000)
                expect(page.locator('#lr-reg-active-badge')).to_have_text('ACTIVE · C001-lr-v1')
                checks.append('Strict lifecycle CANDIDATE -> SHADOW -> APPROVED (Ed25519 signed) -> ACTIVE verified in UI')

                # Capture crisp screenshot of R5 Registry section while v1 is ACTIVE
                page.locator('#lr-registry-section').scroll_into_view_if_needed()
                page.screenshot(path=str(output / 'r5_lr_model_registry.png'), full_page=True)

                # 7. Register v2 -> validate (compares against previous_lr_version = C001-lr-v1!) -> activate -> ROLLED_BACK restoring v1!
                page.locator('#btn-lr-reg-register').click()
                expect(page.locator('#lr-reg-title')).to_contain_text('C001-lr-v2', timeout=15000)
                page.locator('#lr-reg-eval-mode').select_option('representative_sme_benchmark')
                page.locator('#btn-lr-reg-validate').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('CANDIDATE', timeout=20000)
                expect(page.locator('#lr-reg-compare-body')).to_contain_text('LR phiên bản trước (C001-lr-v1)')

                page.locator('#lr-reg-reason').fill('Chuyển v2 vào SHADOW sau khi đối chiếu với phiên bản trước v1.')
                page.locator('#btn-lr-tr-shadow').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('SHADOW', timeout=15000)

                page.locator('#lr-reg-reason').fill('Phê duyệt v2 đạt đủ cổng chất lượng R5 và đối chiếu v1.')
                page.locator('#lr-reg-reviewed').check()
                page.locator('#btn-lr-tr-approve').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('APPROVED', timeout=15000)

                page.locator('#lr-reg-reason').fill('Kích hoạt v2 thay thế v1, lưu v1 làm rollback_target.')
                page.locator('#btn-lr-tr-activate').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('ACTIVE', timeout=15000)
                expect(page.locator('#lr-reg-active-badge')).to_have_text('ACTIVE · C001-lr-v2')
                expect(page.locator('#lr-reg-meta-dl')).to_contain_text('lrreg_')

                page.locator('#lr-reg-reason').fill('Kiểm thử hoàn nguyên khẩn cấp v2 về v1 theo quy trình R5.')
                expect(page.locator('#btn-lr-tr-rollback')).to_be_enabled()
                page.locator('#btn-lr-tr-rollback').click()
                expect(page.locator('#lr-reg-state-pill')).to_have_text('ROLLED_BACK', timeout=15000)
                expect(page.locator('#lr-reg-active-badge')).to_have_text('ACTIVE · C001-lr-v1')
                checks.append('v2 compares against previous LR v1, records rollback_target, and ROLLED_BACK automatically restores v1 as ACTIVE')

                # 8. Mobile viewport check & zero console errors
                page.set_viewport_size(dict(width=390, height=844))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'Mobile horizontal overflow on R5 UI'
                assert not errors, errors
                checks.append('Mobile 390px viewport fits without horizontal overflow; zero JS/console errors')

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
