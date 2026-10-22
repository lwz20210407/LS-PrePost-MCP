"""Windows 10+ atomic Job assignment, with Popen's pipe and wait machinery.

CPython 3.11/3.12 only marshal handle_list in STARTUPINFO.lpAttributeList.
Use CreateProcessW directly for JOB_LIST; never patch subprocess globals.
This private launcher supports the engine's shell=False, close_fds=True calls.
"""

import ctypes
import os
import subprocess
import sys


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32), ("reserved", ctypes.c_void_p),
        ("desktop", ctypes.c_void_p), ("title", ctypes.c_void_p),
        ("x", ctypes.c_uint32), ("y", ctypes.c_uint32),
        ("x_size", ctypes.c_uint32), ("y_size", ctypes.c_uint32),
        ("x_chars", ctypes.c_uint32), ("y_chars", ctypes.c_uint32),
        ("fill", ctypes.c_uint32), ("flags", ctypes.c_uint32),
        ("show", ctypes.c_uint16), ("reserved_size", ctypes.c_uint16),
        ("reserved_data", ctypes.c_void_p), ("stdin", ctypes.c_void_p),
        ("stdout", ctypes.c_void_p), ("stderr", ctypes.c_void_p),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("process", ctypes.c_void_p), ("thread", ctypes.c_void_p),
                ("pid", ctypes.c_uint32), ("tid", ctypes.c_uint32)]


def _api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                                       ctypes.c_uint32, ctypes.POINTER(ctypes.c_size_t)]
    api.InitializeProcThreadAttributeList.restype = ctypes.c_int
    api.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t,
                                              ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                                              ctypes.c_void_p]
    api.UpdateProcThreadAttribute.restype = ctypes.c_int
    api.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    api.DeleteProcThreadAttributeList.restype = None
    api.CreateProcessW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p,
                                   ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(_StartupInfoEx),
                                   ctypes.POINTER(_ProcessInfo)]
    api.CreateProcessW.restype = ctypes.c_int
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    api.CloseHandle.restype = ctypes.c_int
    return api


def _environment_block(env):
    if env is None:
        return None
    entries = []
    for key, value in sorted(env.items(), key=lambda item: item[0].upper()):
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("Windows environment keys and values must be strings")
        if not key or "=" in key[1:] or "\0" in key or "\0" in value:
            raise ValueError("Invalid Windows environment entry")
        entries.append(key + "=" + value)
    return ctypes.create_unicode_buffer("\0".join(entries) + "\0")


def create_in_job(job_handle, executable, command, cwd, env, flags, std_handles, handle_list):
    """Create the process in its job, or fail without launching any user code."""
    api = _api()
    environment = _environment_block(env)
    startup = _StartupInfoEx()
    startup.startup.cb = ctypes.sizeof(startup)
    attributes = [(0x2000D, (ctypes.c_void_p * 1)(job_handle))]  # JOB_LIST
    if std_handles is not None:
        startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = std_handles
    if handle_list:
        attributes.append((0x20002, (ctypes.c_void_p * len(handle_list))(*handle_list)))
    size = ctypes.c_size_t()
    api.InitializeProcThreadAttributeList(None, len(attributes), 0, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    storage = ctypes.create_string_buffer(size.value)
    if not api.InitializeProcThreadAttributeList(storage, len(attributes), 0, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        for key, value in attributes:
            if not api.UpdateProcThreadAttribute(storage, 0, key, value, ctypes.sizeof(value), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
        startup.attributes = ctypes.cast(storage, ctypes.c_void_p)
        info = _ProcessInfo()
        # Unicode environment + STARTUPINFOEX. JOB_LIST membership is established
        # by the kernel, even if the host dies before CreateProcessW returns.
        if not api.CreateProcessW(executable, ctypes.create_unicode_buffer(command), None, None,
                                  bool(handle_list), flags | 0x80400, environment, cwd,
                                  ctypes.byref(startup), ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        api.CloseHandle(info.thread)
        return info
    finally:
        api.DeleteProcThreadAttributeList(storage)


class JobPopen(subprocess.Popen):
    """Keep Popen IO/communicate/timeout behavior, replace only Windows creation.

    _execute_child and Handle are private CPython APIs: supported versions are
    exercised on Windows in CI. Unsupported launch options are rejected explicitly.
    """

    def __init__(self, args, *, job_handle, **kwargs):
        self._job_handle = job_handle
        super().__init__(args, **kwargs)

    def _execute_child(self, args, executable, preexec_fn, close_fds, pass_fds, cwd, env,
                       startupinfo, creationflags, shell, p2cread, p2cwrite, c2pread, c2pwrite,
                       errread, errwrite, *unused):
        try:
            if shell or startupinfo is not None or not close_fds or pass_fds:
                raise ValueError("JobPopen requires shell=False, close_fds=True and no custom startupinfo")
            if not isinstance(args, str):
                args = subprocess.list2cmdline([args] if isinstance(args, (bytes, os.PathLike)) else args)
            executable = os.fsdecode(executable) if executable is not None else None
            cwd = os.fsdecode(cwd) if cwd is not None else None
            if "\0" in args or (executable is not None and "\0" in executable) or (cwd and "\0" in cwd):
                raise ValueError("embedded null character")
            std_handles = (int(p2cread), int(c2pwrite), int(errwrite)) if -1 not in (
                p2cread, c2pwrite, errwrite) else None
            handles = self._filter_handle_list(std_handles) if std_handles else []
            sys.audit("subprocess.Popen", executable, args, cwd, env)
            info = create_in_job(self._job_handle, executable, args, cwd, env,
                                 creationflags, std_handles, handles)
            self._handle = subprocess.Handle(info.process)
            self.pid = info.pid
            self._child_created = True
        finally:
            self._close_pipe_fds(p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite)
