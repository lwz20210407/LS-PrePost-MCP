"""Private per-process native preferences; never edit the user's LS-PrePost config."""

import hashlib
import os
import re
from pathlib import Path


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
    version = re.search(r"lsprepost[ _-]?(\d+\.\d+)", Path(executable).name, re.I)
    if not version:
        version = re.search(r"(?:LS-PrePost[^/\\]*?)(\d+\.\d+)", str(Path(executable).parent), re.I)
    if version and environ.get("APPDATA"):
        path = Path(environ["APPDATA"]) / "LSTC" / ("LS-PrePost" + version[1]) / "lsppconf"
        if path.is_file():
            return path.resolve()
    return None


def isolate_preferences(executable, directory, environ=None):
    """Copy existing preferences, preserve consent/Python settings and redirect only paths."""
    env = dict(os.environ if environ is None else environ)
    directory = Path(directory).resolve()
    source = locate_config(executable, env)
    if source is None:
        raise RuntimeError("No existing LS-PrePost lsppconf found. Start this installation once to complete setup, or set LSPP_CONFIG_SOURCE to its initialized lsppconf.")
    private = directory / "native-config"
    private.mkdir(exist_ok=False)
    content = source.read_bytes()
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Native configuration exceeds 2 MiB")
    source_sha = hashlib.sha256(content).hexdigest()
    overrides = {
        "session_file": directory / "lspost.cfile",
        "message_file": directory / "lspost.msg",
        "working_directory": directory,
        "filepath_workingdir": directory,
        "use_working_directory": "YES",
        "autosave_proj_file_path": directory / "tmp",
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
    env["LSTC_FILE"] = str(private)
    metadata = dict(
        directory=str(private),
        source=str(source),
        source_sha256=source_sha,
        source_modified=False,
        preserved_settings="Existing consent, Python home and non-path preferences are copied verbatim",
        first_run_note=None,
    )
    return env, metadata


def native_environment(executable, directory, environ=None):
    """Shared batch/session environment, with exclusive private preferences."""
    directory = Path(directory).resolve()
    temp = directory / "tmp"
    temp.mkdir(exist_ok=True)
    env, metadata = isolate_preferences(executable, directory, environ)
    env.update(TEMP=str(temp), TMP=str(temp))
    return env, metadata
