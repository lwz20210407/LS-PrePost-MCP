"""Owned batch lifetimes. Windows children join a kill-on-close job before running."""

import ctypes
import os
import signal
import subprocess

import psutil


class _BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", ctypes.c_uint32), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_processes", ctypes.c_uint32),
                ("affinity", ctypes.c_size_t), ("priority", ctypes.c_uint32),
                ("scheduling", ctypes.c_uint32)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _BasicLimits), ("io_counters", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


class WindowsJob:
    """An unnamed, non-inheritable job; assignment failure never resumes the child."""

    def __init__(self):
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        api.CreateJobObjectW.restype = ctypes.c_void_p
        api.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        api.SetInformationJobObject.restype = ctypes.c_int
        api.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        api.AssignProcessToJobObject.restype = ctypes.c_int
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        api.CloseHandle.restype = ctypes.c_int
        self.api = api
        self.handle = api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        # Popen owns this exact process handle, not a later lookup by executable name.
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle is not None:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


class OwnedProcess:
    """Reap a batch child on success, failure or BaseException, with bounded waits.

    POSIX uses a fresh process group while the unreaped leader retains its PID.
    Windows uses a suspended launch plus an OS-owned job, including host exit.
    This is lifetime management for trusted jobs, not a script sandbox.
    """

    def __init__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.process = None
        self.job = None
        self.mechanism = "windows_job" if os.name == "nt" else "posix_process_group"

    def __enter__(self):
        try:
            if os.name == "nt":
                self.job = WindowsJob()
                self.kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4  # CREATE_SUSPENDED
            else:
                self.kwargs["start_new_session"] = True
            self.process = subprocess.Popen(self.args, **self.kwargs)
            if self.job is not None:
                self.job.assign(self.process)
                psutil.Process(self.process.pid).resume()
            return self
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def stop(self):
        try:
            if self.job is not None:
                self.job.close()
            elif self.process is not None and self.process.returncode is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            if self.process is not None and self.process.returncode is None:
                self.process.kill()

    def __exit__(self, exc_type, error, traceback):
        try:
            self.stop()
            if self.process is not None:
                self.process.wait(timeout=15)
        except Exception as cleanup_error:
            if error is None:
                raise
            error.add_note("Owned process cleanup failed: " + repr(cleanup_error))
        finally:
            if self.process is not None:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    if stream is not None:
                        stream.close()
        return False
