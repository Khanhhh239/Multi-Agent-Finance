"""Parser process limits. Fail closed if the OS refuses the memory constraint."""
import os
import subprocess

from .models import IngestionError


def _windows_job(process, memory_mb, max_processes=2):
    import ctypes
    from ctypes import wintypes
    class Basic(ctypes.Structure):
        _fields_=[('ProcessTime',ctypes.c_longlong),('JobTime',ctypes.c_longlong),('Flags',wintypes.DWORD),
                  ('MinWorkingSet',ctypes.c_size_t),('MaxWorkingSet',ctypes.c_size_t),
                  ('ActiveProcesses',wintypes.DWORD),('Affinity',ctypes.c_size_t),
                  ('Priority',wintypes.DWORD),('Scheduling',wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
    class Extended(ctypes.Structure):
        _fields_=[('Basic',Basic),('IO',IO),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),
                  ('PeakProcessMemory',ctypes.c_size_t),('PeakJobMemory',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]; kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateJobObjectW(None,None)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    limits=Extended(); limits.Basic.Flags=0x100|0x200|0x2000|0x8
    # Windows venv python.exe is a redirector which starts the real interpreter.
    # Account for both processes, while enforcing the same total job memory cap.
    limits.Basic.ActiveProcesses=max_processes; limits.ProcessMemory=memory_mb*1024*1024
    limits.JobMemory=memory_mb*1024*1024
    if (not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits))
            or not kernel.AssignProcessToJobObject(handle,wintypes.HANDLE(int(process._handle)))):
        error=ctypes.WinError(ctypes.get_last_error()); kernel.CloseHandle(handle); raise error
    def close(): kernel.CloseHandle(handle)
    kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
    def peak_memory():
        observed=Extended()
        if not kernel.QueryInformationJobObject(handle,9,ctypes.byref(observed),ctypes.sizeof(observed),None):
            raise ctypes.WinError(ctypes.get_last_error())
        return observed.PeakJobMemory
    close.peak_memory=peak_memory
    return close


def _resume_windows_process(process):
    """Resume only after job assignment; descendants then inherit the job limits."""
    import ctypes
    from ctypes import wintypes
    class ThreadEntry(ctypes.Structure):
        _fields_=[('Size',wintypes.DWORD),('Usage',wintypes.DWORD),('ThreadId',wintypes.DWORD),
                  ('OwnerPid',wintypes.DWORD),('BasePriority',wintypes.LONG),('DeltaPriority',wintypes.LONG),('Flags',wintypes.DWORD)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Thread32First.argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)]
    kernel.Thread32Next.argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)]
    kernel.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]; kernel.OpenThread.restype=wintypes.HANDLE
    kernel.ResumeThread.argtypes=[wintypes.HANDLE]; kernel.ResumeThread.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    snapshot=kernel.CreateToolhelp32Snapshot(0x4,0)
    if snapshot==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=ThreadEntry(); entry.Size=ctypes.sizeof(entry)
        found=kernel.Thread32First(snapshot,ctypes.byref(entry))
        while found:
            if entry.OwnerPid==process.pid:
                thread=kernel.OpenThread(0x2,False,entry.ThreadId)
                if not thread: raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if kernel.ResumeThread(thread)==0xffffffff: raise ctypes.WinError(ctypes.get_last_error())
                finally: kernel.CloseHandle(thread)
                return
            found=kernel.Thread32Next(snapshot,ctypes.byref(entry))
        raise RuntimeError('suspended process thread not found')
    finally: kernel.CloseHandle(snapshot)


def run_bounded(command, payload, timeout, memory_mb, cwd, max_processes=2, environment=None):
    kwargs={}
    if environment is not None: kwargs['env']={**os.environ,**environment}
    if os.name=='nt':
        kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|0x00000004  # CREATE_SUSPENDED (Win32)
    else:
        def limit():
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(memory_mb*1024*1024,)*2)
        kwargs['preexec_fn']=limit
    process=subprocess.Popen(command,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs)
    close=lambda:None
    try:
        if os.name=='nt':
            close=_windows_job(process,memory_mb,max_processes)
            _resume_windows_process(process)
        # Worker blocks on stdin before loading parsers. Constraint is installed first.
        try:
            process.communicate(payload,timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
            raise IngestionError('WORKER_TIMEOUT','Reader exceeded wall time.',retryable=True,
                                 next_action='Retry within the attempt limit or submit a smaller document.')
        if process.returncode:
            error=IngestionError('WORKER_RESOURCE_ERROR','Reader exited without a complete result.',
                                 next_action='Reduce document size or inspect the worker environment; no automatic retry.')
            error.worker_exit_code=process.returncode
            raise error
        return {'peak_job_memory_bytes':close.peak_memory() if hasattr(close,'peak_memory') else None}
    except IngestionError:
        raise
    except Exception:
        raise IngestionError('PROCESSING_ERROR','Unable to enforce worker resource limits.',
                             next_action='Check OS process-limit support before retrying.') from None
    finally:
        if process.poll() is None: process.kill(); process.wait()
        close()
