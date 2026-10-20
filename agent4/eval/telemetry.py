"""Sample total device memory, explicitly including other GPU processes."""
import json,subprocess,threading,time,os,ctypes
from pathlib import Path


class _MemoryStatus(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total_phys',ctypes.c_ulonglong),
              ('available_phys',ctypes.c_ulonglong),('total_page',ctypes.c_ulonglong),('available_page',ctypes.c_ulonglong),
              ('total_virtual',ctypes.c_ulonglong),('available_virtual',ctypes.c_ulonglong),('extended',ctypes.c_ulonglong)]


def physical_memory():
    if os.name!='nt':return {}
    status=_MemoryStatus();status.length=ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):return {}
    return {'ram_available_mib':status.available_phys/1024**2,'ram_load_pct':status.load}


class GPUSampler:
    def __init__(self,path,interval=1):
        self.path=Path(path);self.interval=interval;self.stop=threading.Event();self.samples=[];self.errors=0

    def sample(self):
        try:
            output=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.total,utilization.gpu','--format=csv,noheader,nounits'],text=True,timeout=5,
                                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            used,total,util=[int(x.strip()) for x in output.splitlines()[0].split(',')]
            self.samples.append({'unix':time.time(),'used_mib':used,'total_mib':total,'utilization_pct':util,**physical_memory()})
        except (OSError,ValueError,subprocess.SubprocessError):self.errors+=1

    def loop(self):
        while not self.stop.wait(self.interval):self.sample()

    def __enter__(self):
        self.sample();self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self

    def __exit__(self,*exc):
        self.stop.set();self.thread.join(timeout=6);self.sample()
        report={'report_notice':'formulas not accountant-approved','n':len(self.samples),'sample_errors':self.errors,
                'total_device_peak_mib':max((s['used_mib'] for s in self.samples),default=None),
                'minimum_available_ram_mib':min((s['ram_available_mib'] for s in self.samples if 'ram_available_mib' in s),default=None),
                'note':'Sampled total GPU memory, includes display and unrelated processes; not allocator peak. 1s cadence may miss transients.',
                'samples':self.samples}
        self.path.write_text(json.dumps(report,indent=2),encoding='utf8')
