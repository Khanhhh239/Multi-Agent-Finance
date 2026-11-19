"""Provision the encrypted-training stack (cloud worker tree + one key domain per contributing company).

Idempotent. Layout (matches what the Portal and LRFHETrainingService discover):
  .runtime/he-training-managed/
      cloud/{code,build,state,worker-config.json,worker-signing.key,<company>-evaluation.keys}   <- what a cloud operator receives
      enterprise/<company>/...                                                                   <- stays on each company's machine (DPAPI)
      batch-training-runtime.json                                                                <- company-side runtime config
Companies default to MPX10, C001, C002 (the three demo contributors); add more with --company.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT2 = ROOT / 'agent2'
sys.path[:0] = [str(AGENT2), str(ROOT / 'shared' / 'finance_input' / 'src')]

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat  # noqa: E402

from experiments.he4.windows_bridge import linux_path  # noqa: E402
from experiments.he_training import TARGET  # noqa: E402
from experiments.he_training import bundle as training_bundle  # noqa: E402
from experiments.he_training.enterprise import Enterprise  # noqa: E402
from experiments.he_training.protocol import atomic, canonical, sha, strict_json  # noqa: E402
from finance_input import AccessScope  # noqa: E402

DISTRO = os.environ.get('AGENT2_WSL_DISTRO', 'Ubuntu-24.04')
LINUX_PY = os.environ.get('AGENT2_HE_PYTHON', '/opt/he4-venv/bin/python')
BASE = ROOT / '.runtime' / 'he-training-managed'
CIRCUIT = ROOT / '.runtime' / 'he-training' / 'build'
DEFAULT_COMPANIES = ('MPX10', 'C001', 'C002')
PORT = 8870


def say(msg):
    print(f'[train-setup] {msg}', flush=True)


def link_or_copy(src, dst):
    if dst.exists():
        return
    try:
        dst.hardlink_to(src)
    except OSError:
        shutil.copy2(src, dst)


def prepare_cloud():
    cloud = BASE / 'cloud'
    (cloud / 'state').mkdir(parents=True, exist_ok=True)
    public = cloud / 'build'
    if not public.exists():
        public.mkdir()
        for name in ('manifest.json', 'server.zip', 'client.specs.json'):
            shutil.copy2(CIRCUIT / name, public / name)
    code = cloud / 'code'
    if not code.exists():
        training_bundle.build(code)
    key = cloud / 'worker-signing.key'
    if not key.exists():
        key.write_text(Ed25519PrivateKey.generate().private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex(), encoding='ascii')
    return cloud, key


def enroll(company, cloud, build, grants):
    scope = AccessScope('demo', frozenset({company}), 'enrollment-' + company, frozenset({'data.import', 'model.fit', 'evidence.verify'}))
    root = BASE / 'enterprise' / company
    say(f'Sinh khóa mã hóa riêng của {company} (lần đầu mất vài phút)...')
    node = Enterprise(root, build, scope, python=LINUX_PY, distro=DISTRO)
    keys = cloud / f'{company}-evaluation.keys'
    link_or_copy(node.root / 'crypto' / 'evaluation.keys', keys)
    grants[company] = dict(
        tenant_id='demo', company_id=company, active=True, node_verify_key=node.public_key, key_epoch=node.meta['key_epoch'],
        target=TARGET, verification_mode='synthetic_expected', evaluation_keys_file=linux_path(keys), evaluation_keys_sha256=sha(keys.read_bytes()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--company', action='append')
    a = p.parse_args()
    companies = tuple(a.company) if a.company else DEFAULT_COMPANIES
    if not (CIRCUIT / 'manifest.json').is_file():
        raise SystemExit('Thiếu mạch huấn luyện; chạy scripts/build_he_training_circuit.sh trước (setup_he.py làm việc này).')
    cloud, key = prepare_cloud()
    cfg_path = cloud / 'worker-config.json'
    grants = {}
    if cfg_path.is_file():
        for g in strict_json(cfg_path.read_bytes())['grants']:
            grants[g['company_id']] = g
    for company in companies:
        if company not in grants or not (BASE / 'enterprise' / company / 'enterprise.json').is_file():
            enroll(company, cloud, cloud / 'build', grants)
    atomic(cfg_path, canonical(dict(build=linux_path(cloud / 'build'), state=linux_path(cloud / 'state'), worker_signing_key=linux_path(key),
                                    batch_training=True, grants=sorted(grants.values(), key=lambda g: g['company_id']))))
    verify_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key.read_text().strip())).public_key().public_bytes_raw().hex()
    runtime = dict(worker_url=f'http://127.0.0.1:{PORT}', worker_verify_key=verify_key, build=str(cloud / 'build'),
                   enterprise_root=str(BASE / 'enterprise'), linux_python=LINUX_PY, distro=DISTRO)
    (BASE / 'batch-training-runtime.json').write_text(json.dumps(runtime, indent=2), encoding='utf-8')
    portal_cfg = ROOT / 'portal' / 'config.local.json'
    cfg = json.loads(portal_cfg.read_text('utf-8'))
    agent2 = cfg['agents']['agent2']
    agent2.setdefault('env', {})['AGENT2_BATCH_TRAINING_CONFIG'] = str(BASE / 'batch-training-runtime.json')
    agent2['he_training_worker'] = dict(bundle=str(cloud / 'code'), config=str(cfg_path), port=PORT, distro=DISTRO, python=LINUX_PY)
    portal_cfg.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    say('Hoàn tất: ' + ', '.join(sorted(grants)))


if __name__ == '__main__':
    main()
