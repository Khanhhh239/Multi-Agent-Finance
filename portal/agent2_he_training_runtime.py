"""Portal supervisor for the encrypted training worker (port 8870).

Owns lifecycle, bundle integrity verification, health check with timeout, and
controlled restart for `experiments.he_training.runner` -> `worker.py`. Uses
WSL on Windows and the configured native interpreter on Linux.
Never imports or touches enterprise secret keys.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

try:
    from .agent2_he4_runtime import linux_path
except ImportError:
    from agent2_he4_runtime import linux_path

REQUIRED_FIELDS = {'bundle', 'config', 'port', 'distro', 'python'}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrainingLinuxRuntime:
    """Managed WSL lifecycle controller for the ciphertext-only HE training worker."""

    def __init__(self, worker: dict, logs: Path | str, *, start_timeout: float = 30.0, health_timeout: float = 1.5):
        if not isinstance(worker, dict) or set(worker) != REQUIRED_FIELDS:
            raise ValueError('Cấu hình he_training_worker không hợp lệ.')
        if type(worker['port']) is not int or not 1 <= worker['port'] <= 65535:
            raise ValueError('Cổng he_training_worker không hợp lệ.')
        self.worker = dict(worker)
        self.logs = Path(logs)
        self.start_timeout = float(start_timeout)
        self.health_timeout = float(health_timeout)
        self.process: subprocess.Popen | None = None
        self.token: str | None = None
        self.verified: bool = False
        self.restart_count: int = 0
        self.last_started_at: str | None = None
        self.last_checked_at: str | None = None
        self.last_latency_ms: float | None = None
        self.last_error: str | None = None
        self._lock = threading.RLock()
        self.opener = build_opener(ProxyHandler({}))

    def _read_config_metadata(self) -> dict:
        meta = {
            'port': self.worker['port'],
            'batch_training': False,
            'grants_companies': [],
            'build_sha256': None,
            'profile': None,
            'concrete_version': None,
        }
        try:
            cfg_path = Path(self.worker['config']).resolve()
            cfg = json.loads(cfg_path.read_bytes())
            meta['batch_training'] = bool(cfg.get('batch_training'))
            meta['grants_companies'] = sorted(
                {g.get('company_id') for g in cfg.get('grants', []) if g.get('active') and g.get('company_id')}
            )
            build_dir = cfg_path.parent / 'build'
            manifest_path = build_dir / 'manifest.json'
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_bytes())
                meta['build_sha256'] = (manifest.get('files') or {}).get('server.zip')
                meta['profile'] = manifest.get('profile')
                meta['concrete_version'] = manifest.get('concrete_version')
                meta['features'] = manifest.get('features')
                meta['rows'] = manifest.get('rows')
                meta['max_steps'] = manifest.get('max_steps')
        except (OSError, ValueError, TypeError):
            pass
        return meta

    def validate_bundle(self) -> None:
        root = Path(self.worker['bundle']).resolve()
        manifest_path = root / 'bundle-manifest.json'
        if not manifest_path.is_file():
            raise ValueError('Thiếu bundle-manifest.json của worker huấn luyện mã hóa.')
        manifest = json.loads(manifest_path.read_bytes())
        if manifest.get('version') != 'he-training-public-bundle/0.1.0':
            raise ValueError('Phiên bản bundle worker huấn luyện mã hóa không hợp lệ.')
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        expected_files = set(manifest.get('files') or {})
        if actual != expected_files | {'bundle-manifest.json'}:
            raise ValueError('Danh sách tệp trong bundle worker 8870 không khớp manifest.')
        for rel, expected_sha in manifest['files'].items():
            path = (root / rel).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
                raise ValueError(f'Tệp bundle worker 8870 bị sai lệch kiểm tra toàn vẹn: {rel}')
        forbidden = ('enterprise', 'helper', 'sme_fraud', 'windows_bridge', 'dpapi', 'secret')
        if any(any(word in rel.lower() for word in forbidden) for rel in actual):
            raise ValueError('Phát hiện module doanh nghiệp trong bundle cloud worker 8870.')
        cfg_path = Path(self.worker['config']).resolve()
        if not cfg_path.is_file():
            raise ValueError('Thiếu tệp cấu hình worker-config.json cho worker 8870.')

    def health(self, *, timeout: float | None = None) -> dict | None:
        t0 = time.monotonic()
        eff_timeout = self.health_timeout if timeout is None else float(timeout)
        url = f'http://127.0.0.1:{self.worker["port"]}/health'
        try:
            with self.opener.open(Request(url), timeout=eff_timeout) as response:
                value = json.loads(response.read(4096))
            latency = round((time.monotonic() - t0) * 1000.0, 1)
            self.last_checked_at = _iso_now()
            self.last_latency_ms = latency
            if (
                isinstance(value, dict)
                and value.get('role') == 'he_training_worker'
                and value.get('version') == 'he-training-worker/0.1.0'
            ):
                return dict(value, latency_ms=latency)
            return None
        except (OSError, ValueError):
            self.last_checked_at = _iso_now()
            self.last_latency_ms = None
            return None

    def _port_open(self) -> bool:
        with socket.socket() as conn:
            conn.settimeout(0.25)
            return conn.connect_ex(('127.0.0.1', self.worker['port'])) == 0

    def state(self) -> dict:
        with self._lock:
            owned = self.process is not None and self.process.poll() is None
            probe = self.health()
            ready = bool(owned and self.verified and probe is not None and probe.get('batch_training') is True)
            listening = probe is not None or self._port_open()
            if ready:
                status = 'ready'
                message = f'Worker huấn luyện FHE (cổng {self.worker["port"]}) đã sẵn sàng.'
            elif owned:
                status = 'degraded'
                message = f'Worker huấn luyện FHE (cổng {self.worker["port"]}) không phản hồi health check.'
            elif listening:
                status = 'busy-port'
                message = f'Cổng {self.worker["port"]} đang bị tiến trình ngoài Portal chiếm dụng.'
            else:
                status = 'stopped'
                message = self.last_error or f'Worker huấn luyện FHE (cổng {self.worker["port"]}) đang tắt.'
            meta = self._read_config_metadata()
            return {
                'status': status,
                'ready': ready,
                'owned': owned,
                'can_recover': True,
                'port': self.worker['port'],
                'url': f'http://127.0.0.1:{self.worker["port"]}',
                'role': probe.get('role') if probe else 'he_training_worker',
                'version': probe.get('version') if probe else 'he-training-worker/0.1.0',
                'batch_training': bool(probe.get('batch_training')) if probe else meta['batch_training'],
                'latency_ms': probe.get('latency_ms') if probe else None,
                'restart_count': self.restart_count,
                'last_started_at': self.last_started_at,
                'last_checked_at': self.last_checked_at,
                'last_error': self.last_error,
                'message': message,
                'circuit': {
                    'profile': meta.get('profile'),
                    'concrete_version': meta.get('concrete_version'),
                    'build_sha256': meta.get('build_sha256'),
                    'features': meta.get('features'),
                    'rows': meta.get('rows'),
                    'max_steps': meta.get('max_steps'),
                    'grants_companies': meta.get('grants_companies'),
                },
            }

    def start(self) -> dict:
        with self._lock:
            self.validate_bundle()
            if self.process is not None and self.process.poll() is None:
                if self.health() is not None:
                    self.verified = True
                    self.last_error = None
                    return self.state()
                # Process alive but unresponsive: clean stop before relaunch
                self.stop()
            if self._port_open():
                self.last_error = (
                    f'Cổng worker huấn luyện FHE ({self.worker["port"]}) đang do tiến trình khác sử dụng; '
                    'Portal không tự chiếm quyền.'
                )
                raise ValueError(self.last_error)

            self.logs.mkdir(parents=True, exist_ok=True)
            self.token = secrets.token_hex(32)
            if os.name == 'nt':
                command = [
                    'wsl.exe', '-d', self.worker['distro'],
                    '--cd', linux_path(self.worker['bundle']),
                    '--exec', self.worker['python'], '-B', '-m', 'experiments.he_training.runner',
                    '--config', linux_path(self.worker['config']),
                    '--port', str(self.worker['port']),
                ]
                cwd = None
            else:
                command = [
                    self.worker['python'], '-B', '-m', 'experiments.he_training.runner',
                    '--config', str(Path(self.worker['config']).resolve()),
                    '--port', str(self.worker['port']),
                ]
                cwd = str(Path(self.worker['bundle']).resolve())
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            with (self.logs / 'agent2-he-training-worker.log').open('ab') as log:
                log.write(f'\n--- {_iso_now()} start worker 8870 ---\n'.encode('utf-8'))
                log.flush()
                self.process = subprocess.Popen(
                    command, cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                )
            assert self.process.stdin is not None
            self.process.stdin.write((json.dumps({'token': self.token}) + '\n').encode('utf-8'))
            self.process.stdin.flush()

            try:
                deadline = time.monotonic() + self.start_timeout
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        raise ValueError('Worker huấn luyện FHE (8870) thoát sớm khi khởi động.')
                    probe = self.health(timeout=1.0)
                    if probe is not None and probe.get('batch_training') is True:
                        self.verified = True
                        self.last_started_at = _iso_now()
                        self.last_error = None
                        return self.state()
                    time.sleep(0.2)
                raise ValueError(f'Worker huấn luyện FHE (8870) quá thời gian khởi động ({int(self.start_timeout)}s).')
            except Exception as exc:
                self.last_error = str(exc)
                self.stop()
                raise

    def stop(self) -> None:
        with self._lock:
            process = self.process
            if process is not None and process.poll() is None:
                try:
                    if process.stdin:
                        process.stdin.write((json.dumps({'action': 'stop', 'token': self.token}) + '\n').encode('utf-8'))
                        process.stdin.flush()
                        process.stdin.close()
                except (OSError, ValueError):
                    pass
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process is not None:
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    if not self._port_open():
                        break
                    time.sleep(0.2)
            self.process = None
            self.token = None
            self.verified = False

    def restart(self) -> dict:
        """Controlled stop + health-verified restart."""
        with self._lock:
            self.stop()
            self.restart_count += 1
            return self.start()
