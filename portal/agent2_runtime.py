"""Own only the HE worker launched for Agent2; stdlib-only Portal boundary."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import build_opener,ProxyHandler,HTTPRedirectHandler,Request

WORKER_FILES=('__init__.py','protocol.py','cloud_worker.py','http_common.py','worker_store.py','worker_server.py')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def read_json(path):
    with Path(path).open('rb') as stream:raw=stream.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Cấu hình quá lớn.')
    return json.loads(raw)


def stop_owned(process):
    if process is None or process.poll() is not None:return
    if os.name=='nt':
        result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and process.poll() is None:process.terminate()
    else:process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


class Runtime:
    def __init__(self,python,agent_root,node_config,bindings,worker,logs):
        if not isinstance(worker,dict) or set(worker)!={'bundle','config','port'} or type(worker['port']) is not int or not 1<=worker['port']<=65535:
            raise ValueError('Chưa có cấu hình bộ xử lý Agent2 hợp lệ.')
        self.python=str(python);self.agent_root=Path(agent_root).resolve()
        self.node_config=Path(node_config).resolve();self.bindings=Path(bindings).resolve()
        self.bundle=Path(worker['bundle']).resolve();self.config=Path(worker['config']).resolve()
        self.port=worker['port'];self.logs=Path(logs);self.process=None;self.verified=False
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def validate_bundle(self):
        try:
            manifest=read_json(self.bundle/'worker-manifest.json')
            expected=manifest['sha256']
            if manifest['version']!='he-worker-bundle/1.0.0':raise ValueError()
            actual={p.relative_to(self.bundle).as_posix() for p in self.bundle.rglob('*') if p.is_file()}
            if actual!=set(expected)|{'worker-manifest.json'}:raise ValueError()
            for name,value in expected.items():
                path=(self.bundle/name).resolve()
                if not path.is_relative_to(self.bundle) or hashlib.sha256(path.read_bytes()).hexdigest()!=value:raise ValueError()
            for name in WORKER_FILES:
                if (self.bundle/'experiments/he_inference'/name).read_bytes()!=(self.agent_root/'experiments/he_inference'/name).read_bytes():raise ValueError()
        except (OSError,ValueError,KeyError,TypeError):
            raise ValueError('Bộ xử lý chưa đúng phiên bản. Người quản lý cần cập nhật gói worker.') from None

    def preflight(self,keys_only=False):
        command=[self.python,'-X','utf8','-B','-m','experiments.he_inference.readiness',
            '--node-config',str(self.node_config),'--bindings',str(self.bindings),'--worker-port',str(self.port)]
        if keys_only:command.append('--keys-only')
        # Private keys are opened only by the DN interpreter, not the Portal.
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','SYSTEMDRIVE','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS'}}
        env.update(PYTHONPATH=str(self.agent_root),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        try:
            result=subprocess.run(command,cwd=self.agent_root,env=env,capture_output=True,timeout=25,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            value=json.loads(result.stdout)
            if result.returncode or value.get('status')!='ready':raise ValueError()
        except (OSError,ValueError,subprocess.SubprocessError):
            raise ValueError('Chưa xác nhận được kết nối hoặc khóa phân tích. Kiểm tra cấu hình và tài khoản chạy node.') from None

    def health(self):
        try:
            with self.opener.open(Request(f'http://127.0.0.1:{self.port}/health'),timeout=.7) as response:
                value=json.loads(response.read(4096))
            return value if value.get('role')=='ciphertext_worker' else None
        except (OSError,ValueError):return None

    def state(self):
        owned=self.process is not None and self.process.poll() is None
        ready=owned and self.verified and self.health() is not None
        return dict(status='ready' if ready else 'unavailable',owned=owned,can_recover=True,
            message='Bộ xử lý đã kết nối.' if ready else 'Bộ xử lý mất kết nối. Kết nối lại để tiếp tục yêu cầu đã lưu.')

    def start(self):
        self.validate_bundle();self.preflight(keys_only=True)
        if self.process is not None and self.process.poll() is None:
            try:self.preflight();self.verified=True;return
            except ValueError:self.verified=False;raise
        # Never adopt/terminate a process just because it listens on this port.
        with socket.socket() as sock:
            sock.settimeout(.3)
            if sock.connect_ex(('127.0.0.1',self.port))==0:
                raise ValueError('Cổng bộ xử lý đang được dùng bởi tiến trình khác. Người quản lý cần kiểm tra; Portal không tự dừng tiến trình đó.')
        env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','TEMP','TMP','SYSTEMDRIVE','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS'}}
        env.update(PYTHONPATH=str(self.bundle),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        self.logs.mkdir(parents=True,exist_ok=True)
        with (self.logs/'agent2-worker.log').open('ab') as log:
            self.process=subprocess.Popen([self.python,'-X','utf8','-B','-m','experiments.he_inference.worker_server',
                '--config',str(self.config),'--port',str(self.port)],cwd=self.bundle,env=env,
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                if self.process.poll() is not None:raise ValueError('Bộ xử lý chưa khởi động được. Người quản lý cần kiểm tra nhật ký.')
                if self.health() is not None:break
                time.sleep(.1)
            else:raise ValueError('Bộ xử lý chưa sẵn sàng. Thử kết nối lại.')
            self.preflight();self.verified=True
        except Exception:
            stop_owned(self.process);self.process=None;self.verified=False;raise

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            # The caller stops the DN first. Let accepted evaluations commit
            # their ciphertext before stopping this worker's owned tree.
            deadline=time.monotonic()+20;idle_since=None
            while time.monotonic()<deadline:
                health=self.health()
                if health is None:break
                if health.get('active_evaluations',0)==0:
                    idle_since=idle_since or time.monotonic()
                    if time.monotonic()-idle_since>=.5:break
                else:idle_since=None
                time.sleep(.1)
            stop_owned(self.process)
        self.process=None;self.verified=False
