"""Portal owns the HE4 worker via WSL on Windows or a child process on Linux."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from urllib.request import build_opener,ProxyHandler,Request


def linux_path(path):
    p=Path(path).resolve()
    if os.name != 'nt':return str(p)
    if len(p.drive)!=2 or p.drive[1]!=':':raise ValueError('Local Windows drive required')
    return '/mnt/'+p.drive[0].lower()+'/'+p.as_posix()[3:]


class LinuxRuntime:
    def __init__(self,worker,agent_root,node_config,he4_config,python,logs):
        if set(worker)!={'bundle','config','port','distro','python'} or type(worker['port']) is not int or not 1<=worker['port']<=65535:raise ValueError('HE4 worker config')
        self.worker=dict(worker);self.agent_root=Path(agent_root).resolve();self.node_config=Path(node_config);self.he4_config=Path(he4_config)
        self.python=str(python);self.logs=Path(logs);self.process=None;self.token=None;self.verified=False
        self.opener=build_opener(ProxyHandler({}))

    def validate_bundle(self):
        root=Path(self.worker['bundle']).resolve();manifest=json.loads((root/'bundle-manifest.json').read_bytes())
        if manifest['version']!='he4-public-bundle/0.1.0':raise ValueError('HE4 bundle version')
        actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
        if actual!=set(manifest['files'])|{'bundle-manifest.json'}:raise ValueError('HE4 bundle file list')
        for name,expected in manifest['files'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected or path.read_bytes()!=(self.agent_root/name).read_bytes():raise ValueError('HE4 bundle integrity')
        if any('enterprise' in n or 'sme_fraud' in n or 'windows_bridge' in n for n in actual):raise ValueError('Enterprise module in cloud bundle')

    def preflight(self,keys_only=False):
        command=[self.python,'-X','utf8','-B','-m','experiments.he4.preflight','--node-config',str(self.node_config),'--config',str(self.he4_config)]
        if keys_only:command.append('--keys-only')
        env=dict(os.environ)
        source_paths=[str(self.agent_root),str(self.agent_root.parent)]
        if env.get('PYTHONPATH'):source_paths.append(env['PYTHONPATH'])
        env['PYTHONPATH']=os.pathsep.join(source_paths)
        result=subprocess.run(command,cwd=self.agent_root,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:value=json.loads(result.stdout)
        except ValueError:raise ValueError('Chưa kiểm tra được khóa phân tích bốn nhánh.') from None
        if result.returncode or value.get('status')!='ready':raise ValueError('Chưa sẵn sàng khóa, phiên bản hoặc kết nối phân tích bốn nhánh.')

    def health(self):
        try:
            with self.opener.open(Request(f'http://127.0.0.1:{self.worker["port"]}/health'),timeout=.7) as response:value=json.loads(response.read(4096))
            return value if value.get('role')=='ciphertext_worker' and value.get('version')=='he4-worker/0.1.0' else None
        except (OSError,ValueError):return None

    def state(self):
        owned=self.process is not None and self.process.poll() is None
        return dict(owned=owned,status='ready' if owned and self.verified and self.health() else 'unavailable',can_recover=True)

    def start(self):
        # Re-opening Agent 2 while this worker is alive and already verified must not re-run the Concrete preflight
        # (each run loads every company key vault in WSL: 1-2 minutes) — that was the lag on every unlock/restart.
        if self.process is not None and self.process.poll() is None and self.verified and self.health():
            return
        self.validate_bundle();self.preflight(keys_only=True)
        if self.process is not None and self.process.poll() is None:
            self.preflight();self.verified=True;return
        with socket.socket() as connection:
            connection.settimeout(.3)
            if connection.connect_ex(('127.0.0.1',self.worker['port']))==0:raise ValueError('Cổng HE4 đang do tiến trình khác dùng; Portal không tự nhận hoặc dừng tiến trình đó.')
        self.logs.mkdir(parents=True,exist_ok=True);self.token=secrets.token_hex(32)
        if os.name == 'nt':
            command=['wsl.exe','-d',self.worker['distro'],'--cd',linux_path(self.worker['bundle']),'--exec',self.worker['python'],'-B','-m','experiments.he4.runner','--config',linux_path(self.worker['config']),'--port',str(self.worker['port'])]
            cwd=None
        else:
            command=[self.worker['python'],'-B','-m','experiments.he4.runner','--config',str(Path(self.worker['config']).resolve()),'--port',str(self.worker['port'])]
            cwd=str(Path(self.worker['bundle']).resolve())
        with (self.logs/'agent2-he4-worker.log').open('ab') as log:
            self.process=subprocess.Popen(command,cwd=cwd,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.process.stdin.write((json.dumps(dict(token=self.token))+'\n').encode());self.process.stdin.flush()
        try:
            end=time.monotonic()+30
            while time.monotonic()<end:
                if self.process.poll() is not None:raise ValueError('Worker HE4 chưa khởi động được.')
                if self.health():break
                time.sleep(.1)
            else:raise ValueError('Worker HE4 chưa sẵn sàng.')
            self.preflight();self.verified=True
        except Exception:self.stop();raise

    def stop(self):
        process=self.process
        if process is not None and process.poll() is None:
            try:
                process.stdin.write((json.dumps(dict(action='stop',token=self.token))+'\n').encode());process.stdin.flush();process.stdin.close()
            except (OSError,ValueError):pass
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                # Closing/killing this wrapper closes the supervisor input;
                # never kill Linux processes by a port or guessed PID.
                process.kill();process.wait(timeout=5)
                deadline=time.monotonic()+8
                while self.health() and time.monotonic()<deadline:time.sleep(.2)
                if self.health():raise ValueError('Chưa xác nhận được worker HE4 đã dừng. Giữ phiên và kiểm tra nhật ký.')
        if process is not None:
            # WSL's Windows forwarding listener may outlive the owned Linux
            # session briefly. Wait for release, never adopt or kill a listener.
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with socket.socket() as connection:
                    connection.settimeout(.2)
                    busy=connection.connect_ex(('127.0.0.1',self.worker['port']))==0
                if not busy:break
                time.sleep(.2)
        self.process=None;self.token=None;self.verified=False


class CombinedRuntime:
    def __init__(self,legacy,extra):self.legacy,self.extra=legacy,extra
    @property
    def process(self):return self.legacy.process
    def state(self):
        a=self.legacy.state();b=self.extra.state();ready=a['status']=='ready' and b['status']=='ready'
        return dict(status='ready' if ready else 'unavailable',owned=a['owned'] or b['owned'],can_recover=True,message='Bộ xử lý đã kết nối.' if ready else 'Một bộ xử lý mất kết nối. Kết nối lại để tiếp tục đúng yêu cầu đã lưu.')
    def start(self):
        old_running=self.legacy.process is not None and self.legacy.process.poll() is None
        self.legacy.start()
        try:self.extra.start()
        except Exception:
            if not old_running:self.legacy.stop()
            raise
    def stop(self):
        try:self.extra.stop()
        finally:self.legacy.stop()
