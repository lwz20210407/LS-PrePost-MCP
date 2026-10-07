"""I01 process ownership exercised with real children, not mocked exit codes."""

import ctypes
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import psutil
import pytest

from ls_prepost_mcp.engine import BatchEngine, BatchJob
from ls_prepost_mcp.engine.processes import OwnedProcess, _ExtendedLimits


def tree_source(marker, *, exit_parent=False):
    redirection = ",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL" if exit_parent else ""
    return (
        "import json,os,subprocess,sys,time\nfrom pathlib import Path\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
        "creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)" + redirection + ")\n"
        f"Path({str(marker)!r}).write_text(json.dumps([os.getpid(),child.pid]))\n"
        "print('ready',flush=True)\ntime.sleep(" + ("0.5" if exit_parent else "60") + ")\n"
    )


def started(marker):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            pids = json.loads(marker.read_text())
            owners = [psutil.Process(pid) for pid in pids]
            for owner in owners:
                owner.create_time()
            return owners
        except (OSError, ValueError, psutil.NoSuchProcess):
            time.sleep(0.01)
    pytest.fail("Controlled child tree did not start")


def running(owner):
    try:
        return owner.is_running() and owner.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def assert_stopped(owners):
    deadline = time.monotonic() + 5
    while any(running(p) for p in owners) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not any(running(p) for p in owners)


def cleanup(owners):
    # Failure cleanup addresses only identities captured from this test's marker.
    for owner in reversed(owners):
        try:
            owner.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(owners, timeout=5)


def test_owned_process_preserves_output_and_closes_pipes(tmp_path):
    with OwnedProcess([sys.executable, "-c", "print('complete')"], cwd=tmp_path,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) as owned:
        stdout, stderr = owned.process.communicate(timeout=15)
        assert stdout.strip() == b"complete" and stderr == b""
    assert owned.process.returncode == 0
    assert owned.process.stdout.closed and owned.process.stderr.closed
    if os.name == "nt":
        assert owned.job.handle is None
        assert ctypes.sizeof(_ExtendedLimits) == (144 if ctypes.sizeof(ctypes.c_void_p) == 8 else 112)


@pytest.mark.parametrize("interruption", [None, KeyboardInterrupt, SystemExit])
def test_engine_timeout_and_interrupt_reap_real_tree(tmp_path, monkeypatch, interruption):
    marker = tmp_path / "tree.json"
    owners = []
    launched = []

    @contextmanager
    def launch(args, **kwargs):
        with OwnedProcess([sys.executable, "-u", "-c", tree_source(marker)], **kwargs) as owned:
            launched.append(owned.process)
            owners.extend(started(marker))
            if interruption:
                def interrupt(**kwargs):
                    raise interruption()
                owned.process.communicate = interrupt
            yield owned

    monkeypatch.setattr("ls_prepost_mcp.engine.batch.OwnedProcess", launch)
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.require_capability", lambda *a: {})
    monkeypatch.setattr("ls_prepost_mcp.engine.batch.native_environment", lambda *a, **kw: (dict(os.environ), {}))
    try:
        job = BatchJob(Path(sys.executable), tmp_path / "job.cfile", tmp_path, 0.2)
        if interruption:
            with pytest.raises(interruption):
                BatchEngine().run(job)
        else:
            result = BatchEngine().run(job)
            assert result.status == "failed" and result.data["timed_out"] is True
            assert "ready" in (tmp_path / "stdout.log").read_text()
            assert result.data["process_isolation"] in ("windows_job", "posix_process_group")
        assert_stopped(owners)
        assert all(p.returncode is not None and p.stdout.closed and p.stderr.closed for p in launched)
    finally:
        cleanup(owners)


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic process assignment")
def test_failed_assignment_never_runs_the_child(tmp_path, monkeypatch):
    marker = tmp_path / "must-not-run.txt"

    from ls_prepost_mcp.engine import windows_job

    create = windows_job.create_in_job

    def reject(job_handle, *args):
        # Real CreateProcessW rejects a non-job HANDLE in JOB_LIST.
        return create(0, *args)

    monkeypatch.setattr(windows_job, "create_in_job", reject)
    owner = OwnedProcess([sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"], cwd=tmp_path)
    with pytest.raises(OSError):
        with owner:
            pytest.fail("Cannot enter an uncontained child")
    assert owner.process is None and owner.job.handle is None
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows kill-on-close job includes lingering children")
def test_normal_parent_exit_also_closes_its_lingering_child(tmp_path):
    marker = tmp_path / "tree.json"
    owners = []
    try:
        with OwnedProcess([sys.executable, "-u", "-c", tree_source(marker, exit_parent=True)], cwd=tmp_path,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as owned:
            owners.extend(started(marker))
            stdout, stderr = owned.process.communicate(timeout=15)
            assert owned.process.returncode == 0 and stdout.strip() == b"ready" and not stderr
        assert_stopped(owners)
    finally:
        cleanup(owners)


@pytest.mark.skipif(os.name != "nt", reason="Windows job handles close on host termination")
def test_host_abrupt_exit_kills_only_its_job(tmp_path):
    marker, permission = tmp_path / "tree.json", tmp_path / "exit-now"
    script = tmp_path / "host.py"
    script.write_text(
        "import os,sys,time\nfrom pathlib import Path\nfrom ls_prepost_mcp.engine.processes import OwnedProcess\n"
        f"owned=OwnedProcess([sys.executable,'-u','-c',{tree_source(marker)!r}])\n"
        "owned.__enter__()\n"
        f"while not Path({str(permission)!r}).exists(): time.sleep(0.01)\n"
        "os._exit(77)\n", encoding="utf8")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"), PYTHONDONTWRITEBYTECODE="1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=tmp_path,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    host = subprocess.Popen([sys.executable, str(script)], cwd=tmp_path, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)
    owners = []
    try:
        owners.extend(started(marker))
        permission.touch()
        assert host.wait(timeout=15) == 77
        assert_stopped(owners)
        assert unrelated.poll() is None
    finally:
        for child in (host, unrelated):
            if child.poll() is None:
                child.kill()
            child.wait(timeout=15)
            if child.stderr:
                child.stderr.close()
        cleanup(owners)


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic Job assignment at process creation")
def test_host_killed_before_popen_returns_reaps_child(tmp_path):
    """Pause after the OS creates a process, before Popen returns to OwnedProcess."""
    marker = tmp_path / "created.json"
    script = tmp_path / "creation_host.py"
    script.write_text(
        "import json,subprocess,sys,time,psutil\nfrom pathlib import Path\n"
        "from ls_prepost_mcp.engine.processes import OwnedProcess\n"
        "original = subprocess.Popen._close_pipe_fds\n"
        "def pause(self, *args):\n"
        "    original(self, *args)\n"
        "    children = psutil.Process().children()\n"
        f"    Path({str(marker)!r}).write_text(json.dumps([p.pid for p in children]))\n"
        "    while True: time.sleep(0.01)\n"
        "subprocess.Popen._close_pipe_fds = pause\n"
        "with OwnedProcess([sys.executable, '-c', 'import time; time.sleep(60)']): pass\n",
        encoding="utf8",
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
               PYTHONDONTWRITEBYTECODE="1")
    flags = subprocess.CREATE_NO_WINDOW
    owners = []
    with subprocess.Popen([sys.executable, str(script)], cwd=tmp_path, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags) as host:
        try:
            owners.extend(started(marker))
            assert len(owners) == 1
            assert running(owners[0])
            host.kill()
            host.wait(timeout=15)
            assert_stopped(owners)
        finally:
            if host.poll() is None:
                host.kill()
            host.wait(timeout=15)
            cleanup(owners)


@pytest.mark.skipif(os.name != "nt", reason="Windows CreateProcessW environment and pipe integration")
def test_atomic_launch_preserves_unicode_args_environment_cwd_and_pipes(tmp_path):
    directory = tmp_path / "空间 with spaces"
    directory.mkdir()
    arguments = ["", "带 空格", 'quoted"value', "trailing\\"]
    source = (
        "import json,os,sys; "
        "print(json.dumps([sys.argv[1:],os.getcwd(),os.environ['I01_VALUE'],sys.stdin.read()])); "
        "sys.stderr.buffer.write(b'error\\xff')"
    )
    with OwnedProcess([sys.executable, "-c", source, *arguments], cwd=directory,
                      env=dict(os.environ, I01_VALUE="中文=value"), stdin=subprocess.PIPE,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) as owned:
        stdout, stderr = owned.process.communicate(b"input", timeout=15)
        assert owned.process.returncode == 0
        assert json.loads(stdout) == [arguments, str(directory), "中文=value", "input"]
        assert stderr == b"error\xff"


@pytest.mark.skipif(os.name != "nt", reason="Windows exact job membership and handle allowlist")
def test_child_is_in_exact_job_and_does_not_inherit_unrelated_handle(tmp_path):
    from ls_prepost_mcp.engine.processes import WindowsJob

    unrelated = WindowsJob()
    os.set_handle_inheritable(unrelated.handle, True)
    try:
        source = (
            "import ctypes,sys,time; api=ctypes.WinDLL('kernel32',use_last_error=True); "
            "api.GetHandleInformation.argtypes=[ctypes.c_void_p,ctypes.c_void_p]; "
            f"flags=ctypes.c_uint32(); print(api.GetHandleInformation({unrelated.handle},ctypes.byref(flags)),flush=True); "
            "time.sleep(60)"
        )
        with OwnedProcess([sys.executable, "-u", "-c", source], cwd=tmp_path,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as owned:
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
            api.IsProcessInJob.restype = ctypes.c_int
            member = ctypes.c_int()
            assert api.IsProcessInJob(int(owned.process._handle), owned.job.handle, ctypes.byref(member))
            assert member.value == 1
            assert owned.process.stdout.readline().strip() == b"0"
    finally:
        unrelated.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows atomic creation failures")
@pytest.mark.parametrize("failure", ["executable", "cwd", "attribute"])
def test_creation_failure_closes_job_without_running_code(tmp_path, monkeypatch, failure):
    from ls_prepost_mcp.engine import windows_job

    marker = tmp_path / "must-not-run"
    args = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"]
    directory = tmp_path
    if failure == "executable":
        args[0] = str(tmp_path / "nonexistent.exe")
    elif failure == "cwd":
        directory = tmp_path / "nonexistent"
    else:
        api = windows_job._api()

        def reject(*args):
            ctypes.set_last_error(50)  # ERROR_NOT_SUPPORTED, no fallback launch
            return 0

        api.UpdateProcThreadAttribute = reject
        monkeypatch.setattr(windows_job, "_api", lambda: api)
    owner = OwnedProcess(args, cwd=directory, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with pytest.raises(OSError):
        with owner:
            pytest.fail("Creation failure must propagate")
    assert owner.process is None and owner.job.handle is None
    assert not marker.exists()
