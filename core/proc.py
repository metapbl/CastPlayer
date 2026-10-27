"""외부 프로세스 공통: 콘솔 창 숨김, 부모 종료 시 자식 자동 종료(Windows Job Object)."""
from __future__ import annotations

import logging
import os
import subprocess

_LOGGER = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.POINTER(_ExtLimit), wintypes.DWORD]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL

    _JOB_LIMIT_KILL_ON_CLOSE = 0x2000
    _JOB_EXT_LIMIT_INFO = 9
    _PROCESS_SET_QUOTA_TERMINATE = 0x0100 | 0x0001
    _job_handle = None

    def _job():
        global _job_handle
        if _job_handle is None:
            h = _k32.CreateJobObjectW(None, None)
            if not h:
                raise ctypes.WinError(ctypes.get_last_error())
            info = _ExtLimit()
            info.BasicLimitInformation.LimitFlags = _JOB_LIMIT_KILL_ON_CLOSE
            if not _k32.SetInformationJobObject(
                    h, _JOB_EXT_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            _job_handle = h  # 프로세스 수명 동안 유지 → 종료 시 OS가 자식 일괄 종료
        return _job_handle

    def bind_to_job(proc: subprocess.Popen) -> None:
        try:
            job = _job()
            h = _k32.OpenProcess(_PROCESS_SET_QUOTA_TERMINATE, False, proc.pid)
            if not h:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not _k32.AssignProcessToJobObject(job, h):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _k32.CloseHandle(h)
        except OSError:
            _LOGGER.warning("Job Object 등록 실패(무시)", exc_info=True)
else:
    def bind_to_job(proc: subprocess.Popen) -> None:  # noqa: ARG001
        return None
