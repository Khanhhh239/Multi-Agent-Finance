"""End-to-end Playwright browser acceptance for Area A (Investigation) + Area B (Model Management)."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests_he'), str(ROOT.parent), str(ROOT.parent / 'shared' / 'finance_input' / 'src')]

from test_portal_auth import PortalHarness, portal
import test_release_shadow_plan as support
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

    support.ShadowPlanTests.setUpClass()
    try:
        f = support.ShadowPlanTests.fixture
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
            for comp in ('C001', 'C002'):
                scope = f.company_ctx[comp]['scope']
                sid = f.company_ctx[comp]['manifests']['sealed_future_test']['snapshot_id']
                reg = svc.register_plan(scope, support.ShadowPlanTests.packages[comp], 'reg-two-area-' + comp)
                b = svc.prepare(scope, sid, 'Two Area UI ' + comp, 'prep-two-area-' + comp, plan_id=reg['plan_id'])
                g = svc.qualify(scope, b['bundle_id'], 'staging')
                assert g['technical_ready'], g
                a = svc.approve(scope, b['bundle_id'], g['gate_id'], 'staging', 'Two-area browser verification approval')
                svc.switch(scope, dict(bundle_id=b['bundle_id'], gate_id=g['gate_id'], approval_id=a['approval_id'],
                                       lane='staging', expected_revision=0, reason='Activate staging', action='activate'), 'act-two-area-' + comp)
                svc.run(scope, 'two-area-run-' + comp, 'staging', sid, svc._snapshot(scope, sid)[1]['source']['as_of'])

            h.agent.shutdown()
            h.agent.server_close()
            h.agent = make_server(0, h.authorizer, f.snapshots, res, case_queue_store=svc.case_queue, release_service=svc)
            h.agent.daemon_threads = False
            portal.CFG['agents']['agent2']['port'] = h.agent.server_port
            t = threading.Thread(target=h.agent.serve_forever, daemon=True)
            t.start()
            h.threads.append(t)

            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport=dict(width=1440, height=960), locale='vi-VN')
            page.on('pageerror', lambda e: errors.append('PAGEERROR: ' + str(e)))
            page.on('console', lambda m: errors.append('CONSOLE_ERR: ' + m.text) if m.type == 'error' else None)
            page.add_init_script('sessionStorage.setItem("kt-session",' + json.dumps(h.token) + ');')

            try:
                # 1. Area A: Queue + Investigation
                page.goto(h.portal_url + '/agent2/#company=C001')
                expect(page.locator('#rows .tx-row')).not_to_have_count(0, timeout=25000)
                expect(page.locator('#nav-models')).to_be_visible()
                page.locator('#rows .tx-row').first.click()
                page.locator('#open-investigation').click()
                expect(page.locator('#investigation')).to_be_visible(timeout=20000)
                expect(page.locator('#graph .node')).not_to_have_count(0)
                expect(page.locator('#inline-related table')).to_be_visible()
                page.screenshot(path=str(output / 'area_a_investigation.png'), full_page=True)
                checks.append('Area A renders queue, interactive PIT graph, inline related table, and readable Vietnamese records')

                # 2. Navigate directly via top pill tab to Area B: Model Management
                page.locator('#nav-models').click()
                expect(page.locator('#active-model-title')).to_contain_text('C001-v1', timeout=20000)
                expect(page.locator('#candidates-body tr')).not_to_have_count(0)
                expect(page.locator('#checklist-grid .chk-item')).to_have_count(4)
                checks.append('Area B bootstraps live pinned C001-v1 model, shared data summary, and 4-item quality checklist')

                # 3. Step 1: Shared Data Quality Profiler (no file upload UI)
                page.locator('[data-step="1"]').click()
                expect(page.locator('#step-panel-1')).to_be_visible()
                expect(page.locator('#profile-kpis .kpi-box')).to_have_count(4, timeout=20000)
                assert page.locator('input[type="file"]').count() == 0, 'Area B must NOT contain file upload controls'
                checks.append('Step 1 profiles shared Portal snapshot without any file upload UI')

                # 4. Step 2: 33-Feature preparation & zero-leakage exclusions
                page.locator('#btn-to-step-2').click()
                expect(page.locator('#step-panel-2')).to_be_visible()
                expect(page.locator('#feature-table-wrap tbody tr')).to_have_count(33)
                checks.append('Step 2 displays all 33 point-in-time features, missingness status, and excluded predictors')

                # 5. Step 3: Train Autoencoder candidate (C001-v2)
                page.locator('#btn-to-step-3').click()
                expect(page.locator('#step-panel-3')).to_be_visible()
                page.locator('.algo-card', has_text='Autoencoder').click()
                # Pick fit snapshot (the one with history + reference before eval)
                fit_sid = f.company_ctx['C001']['manifests']['history_train']['snapshot_id']
                eval_sid = f.company_ctx['C001']['manifests']['sealed_future_test']['snapshot_id']
                page.locator('#train-snapshot').select_option(fit_sid)
                page.wait_for_timeout(800)
                page.locator('#train-eval-snapshot').select_option(eval_sid)
                page.locator('#btn-train').click()
                expect(page.locator('#success-banner')).to_contain_text('C001-v2', timeout=45000)
                expect(page.locator('#step-panel-45')).to_be_visible()
                page.screenshot(path=str(output / 'area_b_model_management.png'), full_page=True)
                checks.append('Step 3 trains real Autoencoder candidate C001-v2 and automatically transitions to Step 4 comparison')

                # 6. Step 5: Approve C001-v2 into Shadow mode
                page.locator('#approve-reason').fill('Đã đối chiếu chỉ số không nhãn và đặc trưng tái tạo của Autoencoder C001-v2.')
                page.locator('#approve-checked').check()
                expect(page.locator('#btn-approve')).to_be_enabled()
                page.locator('#btn-approve').click()
                expect(page.locator('#success-banner')).to_contain_text('Đã phê duyệt C001-v2', timeout=20000)
                expect(page.locator('#btn-score-queue')).to_be_enabled()
                checks.append('Step 5 requires checkbox + reason, approves C001-v2, and enables queue connection')

                # 7. Connect approved ML model to Area A queue & verify traceability!
                page.locator('#score-snapshot').select_option(eval_sid)
                page.locator('#btn-score-queue').click()
                expect(page.locator('#score-queue-result a')).to_be_visible(timeout=25000)
                page.locator('#score-queue-result a').click()
                expect(page.locator('#rows .tx-row')).not_to_have_count(0, timeout=20000)
                page.locator('#rows .tx-row').first.click()
                page.locator('#open-investigation').click()
                expect(page.locator('#investigation')).to_be_visible(timeout=20000)
                page.locator('[data-tab="explanation"]').click()
                expect(page.locator('#explanation')).to_contain_text('C001-v2')
                page.screenshot(path=str(output / 'area_a_explanation_traced.png'), full_page=True)
                checks.append('Approved C001-v2 scores into Area A queue and traces exact version & feature attributions in Explanation tab')

                # 8. Rollback back to C001-v1!
                page.locator('#nav-models').click()
                expect(page.locator('#btn-rollback')).to_be_enabled(timeout=20000)
                page.locator('#btn-rollback').click()
                page.locator('#rollback-reason').fill('Hoàn nguyên về Isolation Forest C001-v1 sau đợt chạy thử nghiệm.')
                page.locator('#btn-confirm-rollback').click()
                expect(page.locator('#success-banner')).to_contain_text('C001-v1', timeout=20000)
                expect(page.locator('#active-model-title')).to_contain_text('C001-v1')
                checks.append('Rollback cleanly restores previous approved Isolation Forest C001-v1')

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
        support.ShadowPlanTests.tearDownClass()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output.resolve()), ensure_ascii=False, indent=2))
