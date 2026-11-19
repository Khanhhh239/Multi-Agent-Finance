"""End-to-end Playwright browser acceptance for R2: Worker 8870 + Real FHE LR in /model-management Step 3."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests_he'), str(REPO_ROOT), str(REPO_ROOT / 'shared' / 'finance_input' / 'src')]

from test_portal_auth import PortalHarness, portal
from portal.agent2_he_training_runtime import TrainingLinuxRuntime
from portal.agent2_he4_runtime import linux_path
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.import_files import canonical
from sme_fraud.lr_fhe_training import LRFHETrainingService
from sme_fraud.review_server import make_server

MANAGED_ROOT = ROOT / '.runtime' / 'he-training-managed-v1'
CLOUD_BUNDLE = MANAGED_ROOT / 'cloud' / 'code'
CLOUD_CFG = MANAGED_ROOT / 'cloud' / 'worker-config.json'
BUILD_DIR = MANAGED_ROOT / 'cloud' / 'build'
ENTERPRISE_ROOT = MANAGED_ROOT / 'enterprise'
WSL_PYTHON = '/home/sang/.local/share/agent2/he4/bin/python'
WSL_DISTRO = 'Debian'


def _prepare_isolated_worker(tmp: Path, port: int) -> tuple[Path, Path]:
    orig = json.loads(CLOUD_CFG.read_text(encoding='utf-8'))
    cloud_dir = tmp / 'cloud'
    state_dir = cloud_dir / 'state'
    state_dir.mkdir(parents=True, exist_ok=True)
    wcfg = dict(orig, state=linux_path(state_dir))
    wcfg_path = cloud_dir / 'worker-config.json'
    wcfg_path.write_text(json.dumps(wcfg, ensure_ascii=False), encoding='utf-8')

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pub_hex = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex((MANAGED_ROOT / 'cloud' / 'worker-signing.key').read_text().strip())
    ).public_key().public_bytes_raw().hex()

    ent_copy = tmp / 'enterprise'
    for cid in ('C001', 'C002'):
        src_c = ENTERPRISE_ROOT / cid
        dst_c = ent_copy / cid
        dst_c.mkdir(parents=True, exist_ok=True)
        for f in ('enterprise.json', 'wrapping.dpapi.json', 'node-signing.dpapi.json'):
            shutil.copy2(src_c / f, dst_c / f)
        (dst_c / 'crypto').mkdir(exist_ok=True)
        for f in ('context.sealed', 'evaluation.keys'):
            try:
                (dst_c / 'crypto' / f).hardlink_to(src_c / 'crypto' / f)
            except OSError:
                shutil.copy2(src_c / 'crypto' / f, dst_c / 'crypto' / f)

    rt_cfg = {
        'worker_url': f'http://127.0.0.1:{port}',
        'worker_verify_key': pub_hex,
        'build': str(BUILD_DIR),
        'enterprise_root': str(ent_copy),
        'linux_python': WSL_PYTHON,
        'distro': WSL_DISTRO,
    }
    rt_path = tmp / 'batch-training-runtime.json'
    rt_path.write_text(json.dumps(rt_cfg, ensure_ascii=False), encoding='utf-8')
    return wcfg_path, rt_path


def run(output: Path) -> dict:
    from playwright.sync_api import sync_playwright, expect

    output.mkdir(parents=True, exist_ok=True)
    checks: list[str] = []
    errors: list[str] = []
    report: dict = {}

    tmp_base = REPO_ROOT / '.runtime' / 'tmp_r2_ui'
    tmp_base.mkdir(parents=True, exist_ok=True)
    port = 18873

    with tempfile.TemporaryDirectory(dir=tmp_base) as tmp_str:
        tmp = Path(tmp_str)
        wcfg_path, rt_path = _prepare_isolated_worker(tmp, port)
        worker_rt = TrainingLinuxRuntime(
            {
                'bundle': str(CLOUD_BUNDLE),
                'config': str(wcfg_path),
                'port': port,
                'distro': WSL_DISTRO,
                'python': WSL_PYTHON,
            },
            tmp / 'logs',
            start_timeout=30.0,
            health_timeout=2.0,
        )
        worker_rt.start()
        try:
            with PortalHarness() as h, sync_playwright() as p:
                pol = deepcopy(json.loads(h.access.read_text('utf-8')))
                for m in pol['memberships']:
                    m['role'] = 'director'
                    m['permissions'] = ['data.import', 'evidence.verify', 'model.fit']
                h.access.write_bytes(canonical(pol))

                import test_release_shadow_plan as support
                support.ShadowPlanTests.setUpClass()
                try:
                    f = support.ShadowPlanTests.fixture
                    h.agent.shutdown()
                    h.agent.server_close()
                    from sme_fraud.analysis_resources import VERSION as BINDINGS_VERSION
                    bindings_path = h.root / 'bindings.json'
                    bindings_path.write_bytes(canonical({
                        'version': BINDINGS_VERSION,
                        'bindings': [
                            {'tenant_id': 'demo', 'company_id': 'C001', 'statistics_artifact_id': None, 'ml_artifacts': {'isolation_forest': f.company_ctx['C001']['model_artifacts']['isolation_forest']['artifact_id']}},
                            {'tenant_id': 'demo', 'company_id': 'C002', 'statistics_artifact_id': None, 'ml_artifacts': {'ecod': f.company_ctx['C002']['model_artifacts']['ecod']['artifact_id']}},
                        ],
                    }))
                    res = AnalysisResources(f.models.path, bindings_path)
                    import os
                    prev_env = os.environ.get('AGENT2_BATCH_TRAINING_CONFIG')
                    os.environ['AGENT2_BATCH_TRAINING_CONFIG'] = str(rt_path)
                    try:
                        h.agent = make_server(0, h.authorizer, f.snapshots, res)
                    finally:
                        if prev_env is None:
                            os.environ.pop('AGENT2_BATCH_TRAINING_CONFIG', None)
                        else:
                            os.environ['AGENT2_BATCH_TRAINING_CONFIG'] = prev_env
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
                        # 1. Open /model-management and switch to Step 3
                        page.goto(h.portal_url + '/agent2/model-management#company=C001')
                        expect(page.locator('#active-model-title')).to_contain_text('C001-v1', timeout=20000)
                        page.locator('[data-step="3"]').click()
                        expect(page.locator('#step-panel-3')).to_be_visible(timeout=20000)

                        # 2. Select Logistic Regression (FHE · Worker 8870)
                        page.locator('.algo-card', has_text='Logistic Regression').click()
                        expect(page.locator('#lr-fhe-panel')).to_be_visible(timeout=20000)
                        expect(page.locator('#lr-worker-pill')).to_contain_text('Sẵn sàng', timeout=15000)
                        expect(page.locator('#lr-crypto-pill')).to_contain_text('Mạch & khóa hợp lệ')
                        expect(page.locator('#lr-feature-ratio')).to_have_text('2 / 33')
                        expect(page.locator('#lr-dataset-kpis .kpi-box')).to_have_count(6)
                        assert page.locator('input[type="file"]').count() == 0, 'No file upload allowed in Area B'
                        checks.append('Step 3 renders Logistic Regression FHE panel, live worker health, circuit/key version, 6 dataset KPIs, and locks 2/33 features')

                        # 3. Run Mode 1: Local Quantized Reference
                        page.locator('#lr-mode-local').click()
                        page.locator('#btn-lr-train').click()
                        expect(page.locator('#success-banner')).to_contain_text('tham chiếu local', timeout=30000)
                        expect(page.locator('#lr-compare-body tr')).to_have_count(3)
                        checks.append('Mode 1 runs Local Quantized Reference and displays 3-way validation comparison')

                        # 4. Run Mode 2: REAL FHE on Ciphertext via Worker 8870 (NO plaintext fallback)
                        page.locator('#lr-mode-fhe').click()
                        page.locator('#btn-lr-train').click()
                        expect(page.locator('#success-banner')).to_contain_text('Worker 8870', timeout=480000)
                        expect(page.locator('#lr-checkpoints-body tr')).to_have_count(3)  # cursor 0, 1, 2
                        expect(page.locator('#lr-stage-badge')).to_contain_text('chưa phát hành')
                        expect(page.locator('#lr-error-split-grid')).to_contain_text('0 lỗi')
                        expect(page.locator('#lr-error-split-grid')).to_contain_text('Sai số lượng tử hóa')
                        page.screenshot(path=str(output / 'r2_lr_fhe_validated_checkpoint.png'), full_page=True)
                        checks.append('Mode 2 completes real Concrete FHE training via Worker 8870, records batch checkpoints, decrypts locally, and proves 0 implementation error')

                        # 5. Test Idempotent Resume button (must not re-run duplicate batches)
                        page.locator('#btn-lr-resume').click()
                        expect(page.locator('#success-banner')).to_contain_text('idempotent', timeout=20000)
                        checks.append('Idempotent Resume preserves completed checkpoints without duplicate batch execution')

                        # 6. Promote validated Train Checkpoint -> Releasable Model
                        page.locator('#lr-promote-reason').fill('Đã đối chiếu giải mã local khớp 100% oracle lượng tử hóa (0 lỗi triển khai) và sai số lượng tử hóa trong ngưỡng.')
                        page.locator('#lr-promote-checked').check()
                        expect(page.locator('#btn-lr-promote')).to_be_enabled()
                        page.locator('#btn-lr-promote').click()
                        expect(page.locator('#lr-stage-badge')).to_contain_text('Model có thể phát hành', timeout=20000)
                        expect(page.locator('#lr-promoted-summary')).to_be_visible()
                        page.screenshot(path=str(output / 'r2_lr_fhe_releasable_model.png'), full_page=True)
                        checks.append('Explicit approval cleanly promotes Train Checkpoint to Releasable Model with version tag')

                        assert not errors, errors
                        report = dict(status='pass', checks=checks, errors=errors)
                    except Exception as exc:
                        report = dict(status='fail', checks=checks, error=str(exc), errors=errors)
                        page.screenshot(path=str(output / 'r2_failure.png'), full_page=True)
                        raise
                    finally:
                        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                        browser.close()
                finally:
                    support.ShadowPlanTests.tearDownClass()
        finally:
            worker_rt.stop()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output.resolve()), ensure_ascii=False, indent=2))
