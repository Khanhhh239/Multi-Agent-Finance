"""One-command operations for the encrypted-training cloud and its contributing companies.

  Cloud operator (holds only public keys and ciphertext):
    python scripts/he_cloud.py serve  [--bind 0.0.0.0] [--port 8870] [--public-url http://HOST:8870]
    python scripts/he_cloud.py info                       # prints the worker verify key and circuit hash to give to companies
    python scripts/he_cloud.py register --package DIR     # import one company's public enrollment package

  Each company (keeps its secret key on its own machine):
    python scripts/he_cloud.py enroll --company MA_DN --cloud http://HOST:8870 --worker-key HEX [--build DIR]

`enroll` creates the company's own key domain locally, writes a public enrollment package (verify key, key epoch,
evaluation keys) and points this installation's runtime config at the cloud.  Nothing secret leaves the company.
On a single demo machine, scripts/setup_he_training.py does enroll + register for the three demo companies at once.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_he_training as base  # noqa: E402
from experiments.he4.windows_bridge import linux_path  # noqa: E402
from experiments.he_training.protocol import atomic, canonical, sha, strict_json  # noqa: E402

CLOUD = base.BASE / 'cloud'
CFG = CLOUD / 'worker-config.json'


def verify_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    raw = bytes.fromhex((CLOUD / 'worker-signing.key').read_text().strip())
    return Ed25519PrivateKey.from_private_bytes(raw).public_key().public_bytes_raw().hex()


def cmd_serve(a):
    cfg = strict_json(CFG.read_bytes())
    if a.public_url:
        cfg['allowed_hosts'] = sorted({*(cfg.get('allowed_hosts') or []), a.public_url.split('//')[-1].split('/')[0].split(':')[0]})
        atomic(CFG, canonical(cfg))
    code = CLOUD / 'code'
    runner = ['-m', 'experiments.he_training.runner', '--standalone', '--config', '{cfg}', '--port', str(a.port), '--bind-host', a.bind]
    if os.name == 'nt':
        command = ['wsl.exe', '-d', base.DISTRO, '--cd', linux_path(code), '--exec', base.LINUX_PY, '-B'] + [linux_path(CFG) if x == '{cfg}' else x for x in runner]
    else:
        command = [base.LINUX_PY, '-B'] + [str(CFG) if x == '{cfg}' else x for x in runner]
    env = dict(os.environ, AGENT2_HE_AGGREGATOR_URL=a.public_url or '')
    print(f'Cloud huấn luyện mã hóa: {a.bind}:{a.port} | khóa xác minh worker: {verify_key()}', flush=True)
    subprocess.run(command, cwd=None if os.name == 'nt' else code, env=env, check=False)


def cmd_info(_):
    manifest = strict_json((CLOUD / 'build' / 'manifest.json').read_bytes())
    print(json.dumps(dict(worker_verify_key=verify_key(), circuit_server_sha256=manifest['files']['server.zip'],
                          companies=sorted(g['company_id'] for g in strict_json(CFG.read_bytes())['grants'])), indent=2))


def cmd_register(a):
    pkg = Path(a.package)
    grant = strict_json((pkg / 'grant.json').read_bytes())
    keys = CLOUD / f"{grant['company_id']}-evaluation.keys"
    shutil.copyfile(pkg / 'evaluation.keys', keys)
    if sha(keys.read_bytes()) != grant['evaluation_keys_sha256']:
        keys.unlink()
        raise SystemExit('Khóa đánh giá không khớp mã băm trong gói; bỏ qua.')
    grant['evaluation_keys_file'] = linux_path(keys)
    cfg = strict_json(CFG.read_bytes())
    cfg['grants'] = [g for g in cfg['grants'] if g['company_id'] != grant['company_id']] + [grant]
    atomic(CFG, canonical(cfg))
    print(f"Đã đăng ký {grant['company_id']}. Khởi động lại 'serve' để áp dụng.")


def cmd_enroll(a):
    build = Path(a.build) if a.build else base.CIRCUIT
    scope = base.AccessScope('demo', frozenset({a.company}), 'enrollment-' + a.company, frozenset({'data.import', 'model.fit', 'evidence.verify'}))
    node = base.Enterprise(base.BASE / 'enterprise' / a.company, build, scope, python=base.LINUX_PY, distro=base.DISTRO)
    out = base.BASE / 'exports' / a.company
    out.mkdir(parents=True, exist_ok=True)
    keys = out / 'evaluation.keys'
    shutil.copyfile(node.root / 'crypto' / 'evaluation.keys', keys)
    grant = dict(tenant_id='demo', company_id=a.company, active=True, node_verify_key=node.public_key, key_epoch=node.meta['key_epoch'], target=base.TARGET,
                 verification_mode='human_verified' if a.real_labels else 'synthetic_expected', evaluation_keys_sha256=sha(keys.read_bytes()))
    (out / 'grant.json').write_text(json.dumps(grant, indent=2))
    runtime = base.BASE / 'batch-training-runtime.json'
    cfg = json.loads(runtime.read_text()) if runtime.is_file() else {}
    cfg.update(worker_url=a.cloud.rstrip('/'), worker_verify_key=a.worker_key, build=str(build), enterprise_root=str(base.BASE / 'enterprise'),
               linux_python=base.LINUX_PY, distro=base.DISTRO)
    runtime.write_text(json.dumps(cfg, indent=2))
    print(f'Gói đăng ký công khai: {out}  (gửi cho vận hành cloud chạy: he_cloud.py register --package <thư mục>)')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve'); s.add_argument('--bind', default='127.0.0.1'); s.add_argument('--port', type=int, default=base.PORT); s.add_argument('--public-url'); s.set_defaults(fn=cmd_serve)
    sub.add_parser('info').set_defaults(fn=cmd_info)
    r = sub.add_parser('register'); r.add_argument('--package', required=True); r.set_defaults(fn=cmd_register)
    e = sub.add_parser('enroll'); e.add_argument('--company', required=True); e.add_argument('--cloud', required=True); e.add_argument('--worker-key', required=True)
    e.add_argument('--build'); e.add_argument('--real-labels', action='store_true'); e.set_defaults(fn=cmd_enroll)
    a = p.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
