"""Self-contained HE bootstrap for the Sổ Son platform (Windows + WSL). Idempotent; creates every key, build and config.

Run through scripts/setup_he.ps1 (uses agent2/.venv).  Stages:
  1. TenSEAL in the Agent 2 venv                      (CKKS enterprise node + worker)
  2. WSL Ubuntu + /opt/he4-venv + Concrete circuits    (TFHE four-branch node + worker)
  3. enterprise node / worker / DPAPI keys per machine (prepared_demo + prepare_he4_managed_demo)
  4. Portal config + data bootstrap + live runtime sync (queue, models, release bundles, C3, LR training)
No key, build or config is shipped in git; everything is generated on the machine that runs this script.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT2 = ROOT / 'agent2'
RUNTIME = ROOT / '.runtime'
DISTRO = os.environ.get('AGENT2_WSL_DISTRO', 'Ubuntu-24.04')
LINUX_PY = os.environ.get('AGENT2_HE_PYTHON', '/opt/he4-venv/bin/python')
READY = RUNTIME / 'he-ready.json'
PY = sys.executable


def say(msg):
    print(f'[he] {msg}', flush=True)


def run(cmd, **kw):
    kw.setdefault('check', True)
    return subprocess.run(cmd, **kw)


def wsl_path(p):
    p = Path(p).resolve()
    return '/mnt/' + p.drive[0].lower() + p.as_posix()[2:]


def wsl(*args, root=True, capture=False):
    cmd = ['wsl', '-d', DISTRO] + (['-u', 'root'] if root else []) + ['--'] + list(args)
    return run(cmd, capture_output=capture, text=capture, encoding='utf-8' if capture else None)


def distros():
    out = subprocess.run(['wsl', '-l', '-q'], capture_output=True).stdout
    return [x.strip() for x in out.decode('utf-16-le', 'ignore').replace('\x00', '').splitlines() if x.strip()]


def stage_tenseal():
    r = subprocess.run([PY, '-c', 'import tenseal, cryptography'], capture_output=True)
    if r.returncode:
        say('Cài TenSEAL 0.3.18 vào môi trường Agent 2...')
        run([PY, '-m', 'pip', 'install', '-q', 'tenseal==0.3.18', 'cryptography==50.0.2'])


def stage_wsl():
    if DISTRO not in distros():
        say(f'Cài WSL {DISTRO} (cần quyền quản trị lần đầu)...')
        run(['wsl', '--install', '-d', DISTRO, '--no-launch'])
        if DISTRO not in distros():
            raise SystemExit('WSL vừa được cài nhưng cần khởi động lại Windows. Khởi động lại rồi chạy lại setup_he.ps1.')
    say('Chuẩn bị Python 3.12 + Concrete 2.11.0 trong WSL...')
    wsl('bash', wsl_path(ROOT / 'scripts' / 'setup_he4_linux.sh'), wsl_path(ROOT))
    say('Biên dịch mạch TFHE (lần đầu mất vài phút)...')
    wsl('bash', wsl_path(ROOT / 'scripts' / 'build_he4_circuits.sh'), wsl_path(ROOT), LINUX_PY)


def stage_enterprise():
    env = dict(os.environ, AGENT2_WSL_DISTRO=DISTRO, AGENT2_HE_PYTHON=LINUX_PY, PYTHONUTF8='1')
    demo = RUNTIME / 'he-demo'
    if not (demo / 'prepared.json').is_file():
        say('Sinh khóa node CKKS, worker và dữ liệu C001/C002 (DPAPI theo máy)...')
        run([PY, '-m', 'experiments.he_inference.prepared_demo', 'prepare', '--output-dir', str(demo)], cwd=AGENT2, env=env)
    managed = RUNTIME / 'he4-managed'
    if not (managed / 'preparation.json').is_file():
        say('Sinh ngữ cảnh TFHE bảo vệ cho C001/C002 (mất vài phút)...')
        run([PY, 'scripts/prepare_he4_managed_demo.py', '--node', str(demo / 'enterprise' / 'node.json'),
             '--bindings', str(demo / 'enterprise' / 'he-ui-bindings.json'), '--output', str(managed),
             '--build-root', str(RUNTIME / 'he4'), '--port', '8869'], cwd=AGENT2, env=env)


def canonical(path, update):
    d = json.loads(Path(path).read_text('utf-8'))
    update(d)
    Path(path).write_text(json.dumps(d, sort_keys=True, separators=(',', ':')), encoding='utf-8')


def stage_config():
    plat = AGENT2 / '.runtime' / 'platform'
    plat.mkdir(parents=True, exist_ok=True)
    canonical(RUNTIME / 'he-demo' / 'enterprise' / 'node.json', lambda d: d.update(
        snapshot_db=str((plat / 'snapshots-v2.sqlite3').resolve()), model_db=str((plat / 'models-v2.sqlite3').resolve())))
    canonical(RUNTIME / 'he4-managed' / 'enterprise' / 'node.json', lambda d: d.update(linux_distro=DISTRO, linux_python=LINUX_PY))
    cfg_path = ROOT / 'portal' / 'config.local.json'
    cfg = json.loads(cfg_path.read_text('utf-8')) if cfg_path.is_file() else json.loads((ROOT / 'portal' / 'config.example.json').read_text('utf-8'))
    a = cfg.setdefault('agents', {}).setdefault('agent2', {})
    a['env'] = {'AGENT2_HE_NODE_CONFIG': str(RUNTIME / 'he-demo' / 'enterprise' / 'node.json'),
                'AGENT2_HE_BINDINGS': str(RUNTIME / 'he-demo' / 'enterprise' / 'he-ui-bindings.json'),
                'AGENT2_HE4_CONFIG': str(RUNTIME / 'he4-managed' / 'enterprise' / 'node.json')}
    a['he_worker'] = {'bundle': str(RUNTIME / 'he-demo' / 'worker' / 'bundle'), 'config': str(RUNTIME / 'he-demo' / 'worker' / 'service.json'), 'port': 8868}
    a['he4_worker'] = {'bundle': str(RUNTIME / 'he4-managed' / 'worker' / 'bundle'), 'config': str(RUNTIME / 'he4-managed' / 'worker' / 'worker.json'),
                       'port': 8869, 'distro': DISTRO, 'python': LINUX_PY}
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')


def stage_runtime():
    say('Nạp dữ liệu MPX10/C001/C002 và mô hình nền...')
    run([PY, '-X', 'utf8', 'data_pipeline/setup_runtime.py', '--mode', 'auto'], cwd=ROOT)
    say('Kích hoạt runtime HE: snapshot luật, mô hình, gói phát hành, mạch C3, hàng đợi điều tra...')
    run([PY, '-X', 'utf8', 'agent2/scripts/sync_portal_live_runtime.py'], cwd=ROOT,
        env=dict(os.environ, AGENT2_WSL_DISTRO=DISTRO, AGENT2_HE_PYTHON=LINUX_PY, PYTHONUTF8='1'))


def main():
    force = '--force' in sys.argv
    if READY.is_file() and not force:
        say('HE đã được thiết lập (xóa .runtime/he-ready.json hoặc dùng --force để làm lại).')
        return
    RUNTIME.mkdir(exist_ok=True)
    stage_tenseal()
    stage_wsl()
    stage_enterprise()
    stage_config()
    stage_runtime()
    READY.write_text(json.dumps({'status': 'ready', 'distro': DISTRO}), encoding='utf-8')
    say('Hoàn tất. Chạy run_web.bat để mở giao diện điều tra có HE.')


if __name__ == '__main__':
    main()
