"""Atomic checkpoints and a bounded, sequential Windows experiment runtime."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import time
from pathlib import Path

_JOB = None


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def available_gib():
    if os.name != 'nt':
        return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 2**30

    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total', 'page_available',
                                                  'virtual_total', 'virtual_available', 'extended')]
    state = Memory()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise ctypes.WinError()
    return state.available / 2**30


def available_commit_gib():
    if os.name != 'nt':
        return available_gib()
    class Memory(ctypes.Structure):
        _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong)] + [
            (name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available',
                                                 'virtual_total','virtual_available','extended')]
    state=Memory(); state.length=ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise ctypes.WinError()
    return state.page_available / 2**30


def memory_ready(physical, commit, preferred_physical):
    # The hard job limit remains 6 GiB. With ample commit headroom Windows may
    # page cold data; require 0.75 GiB physical and twice the job limit in that
    # case. This changes scheduling only, never experiment size or parameters.
    return commit >= 6 and (physical >= preferred_physical or
                           (physical >= min(.75,preferred_physical) and commit >= 12))


def wait_memory(required_gib, checkpoint):
    while True:
        physical,commit=available_gib(),available_commit_gib()
        if memory_ready(physical,commit,required_gib):
            return
        write_json(checkpoint, {'status': 'waiting_for_memory', 'available_gib': physical,
                               'available_commit_gib':commit,'preferred_physical_gib':required_gib,
                               'hard_job_cap_gib':6,'time': time.time(), 'pid': os.getpid()})
        time.sleep(30)


def limit_memory(gib=6):
    """Limit committed memory of this process and its children, without changing other tasks."""
    global _JOB
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (int(gib * 2**30), int(gib * 2**30)))
        return
    from ctypes import wintypes as W

    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', W.DWORD), ('min_working', ctypes.c_size_t), ('max_working', ctypes.c_size_t),
                    ('active_processes', W.DWORD), ('affinity', ctypes.c_size_t),
                    ('priority', W.DWORD), ('scheduling', W.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('reads', 'writes', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]

    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
    api.CreateJobObjectW.restype = W.HANDLE
    api.GetCurrentProcess.restype = W.HANDLE
    api.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
    api.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
    _JOB = api.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x00000200  # JOB_OBJECT_LIMIT_JOB_MEMORY
    limits.job_memory = int(gib * 2**30)
    if not _JOB or not api.SetInformationJobObject(_JOB, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not api.AssignProcessToJobObject(_JOB, api.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
