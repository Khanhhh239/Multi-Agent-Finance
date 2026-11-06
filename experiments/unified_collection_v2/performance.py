"""Process RSS sampled during work; peak is measured rather than a matrix estimate."""
import ctypes
import os
import threading
import time


def rss_bytes():
    if os.name=="nt":
        class Counters(ctypes.Structure):
            _fields_=[("cb",ctypes.c_ulong),("faults",ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
                ("peak_ws","ws","peak_paged","paged","peak_nonpaged","nonpaged","pagefile","peak_pagefile")]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        kernel = ctypes.WinDLL("kernel32",use_last_error=True)
        api = ctypes.WinDLL("psapi",use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        api.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
        api.GetProcessMemoryInfo.restype = ctypes.c_int
        handle = kernel.GetCurrentProcess()
        if not api.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb):
            raise OSError("Cannot measure process working set")
        return int(value.ws)
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)


class MemoryMeter:
    def __enter__(self):
        self.baseline = self.peak = rss_bytes()
        self.stop = threading.Event()
        self.start = time.perf_counter()
        def sample():
            while not self.stop.wait(.05):
                self.peak = max(self.peak,rss_bytes())
        self.thread = threading.Thread(target=sample,daemon=True)
        self.thread.start()
        return self

    def __exit__(self,*args):
        self.peak = max(self.peak,rss_bytes())
        self.stop.set()
        self.thread.join()
        self.seconds = time.perf_counter()-self.start

    def result(self):
        return {"seconds":self.seconds,"rss_baseline_mib":self.baseline/2**20,"rss_peak_sampled_mib":self.peak/2**20,
                "rss_increment_sampled_mib":(self.peak-self.baseline)/2**20,"sampling_seconds":.05}
