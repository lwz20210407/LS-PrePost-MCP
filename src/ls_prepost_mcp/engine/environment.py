"""Private per-process native preferences; never edit the user's LS-PrePost config."""

import hashlib
import os
import re
from pathlib import Path

from ..native.versions import installation_version


def locate_config(executable, environ):
    explicit = environ.get("LSPP_CONFIG_SOURCE")
    if explicit:
        path = Path(explicit).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("LSPP_CONFIG_SOURCE must be a configuration file")
        return path
    configured = environ.get("LSTC_FILE")
    if configured:
        path = Path(configured).expanduser() / "lsppconf"
        if path.is_file():
            return path.resolve()
    version = installation_version(executable)
    if version and environ.get("APPDATA"):
        path = Path(environ["APPDATA"]) / "LSTC" / ("LS-PrePost" + version) / "lsppconf"
        if path.is_file():
            return path.resolve()
    return None


def isolate_preferences(executable, directory, environ=None, *, batch=False, execution_directory=None):
    """Copy existing preferences, preserve consent/Python settings and redirect only paths."""
    env = dict(os.environ if environ is None else environ)
    directory = Path(directory).resolve()
    native_directory = directory
    if execution_directory is not None:
        native_directory = Path(execution_directory)
        if (not batch or os.name != "nt" or not native_directory.is_absolute()
                or native_directory.resolve(strict=True) != directory):
            raise ValueError("Native execution alias must resolve to this Windows batch job")
    source = locate_config(executable, env)
    if source is None:
        raise RuntimeError("No existing LS-PrePost lsppconf found. Start this installation once to complete setup, or set LSPP_CONFIG_SOURCE to its initialized lsppconf.")
    private = directory / "native-config"
    private.mkdir(exist_ok=False)
    content = source.read_bytes()
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Native configuration exceeds 2 MiB")
    source_sha = hashlib.sha256(content).hexdigest()
    native_cwd = "." if batch and str(native_directory).isascii() else native_directory
    overrides = {
        "session_file": native_directory / "lspost.cfile",
        "message_file": native_directory / "lspost.msg",
        # These two native preference fields tokenize at whitespace. The
        # process cwd is already owned. Non-ASCII cwd stays a documented gap:
        # the relative-path experiment caused 4.13 heap corruption on exit.
        "working_directory": native_cwd,
        "filepath_workingdir": native_cwd,
        "use_working_directory": "YES",
        "autosave_proj_file_path": native_directory / "tmp",
    }
    for key, value in overrides.items():
        text = str(value).replace("\\", "/")
        if any(c in text for c in "\r\n\x00"):
            raise ValueError("Native configuration path contains control characters")
        replacement = (key + " = " + text).encode("utf8")
        pattern = re.compile(rb"(?m)^" + key.encode("ascii") + rb"\s*=[^\r\n]*")
        if pattern.search(content):
            content = pattern.sub(lambda _: replacement, content)
        else:
            content += b"\n" + replacement + b"\n"
    (private / "lsppconf").write_bytes(content)
    env["LSTC_FILE"] = str(native_directory / "native-config")
    metadata = dict(
        directory=str(private),
        source=str(source),
        source_sha256=source_sha,
        source_modified=False,
        preserved_settings="Existing consent, Python home and non-path preferences are copied verbatim",
        first_run_note=None,
        execution_directory=str(native_directory),
    )
    return env, metadata


def native_environment(executable, directory, environ=None, *, batch=False, execution_directory=None):
    """Shared batch/session environment, with exclusive private preferences."""
    directory = Path(directory).resolve()
    temp = directory / "tmp"
    temp.mkdir(exist_ok=True)
    env, metadata = isolate_preferences(executable, directory, environ, batch=batch,
                                        execution_directory=execution_directory)
    native_temp = Path(execution_directory) / "tmp" if execution_directory is not None else temp
    env.update(TEMP=str(native_temp), TMP=str(native_temp))
    return env, metadata
