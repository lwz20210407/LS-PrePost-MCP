"""Explicit local configuration and file access boundaries."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from .native.commands import quoted_path
from .native.versions import require_installation


def command_path(path: Path) -> str:
    return quoted_path(path, "posix")


def scl_command_path(path: Path) -> str:
    """Native Windows SCL resolves slash-style drive paths against its open-folder preference."""
    return quoted_path(path, "native")


@dataclass(frozen=True)
class Settings:
    workspace: Path
    executable: Path | None = None
    allowed_roots: tuple[Path, ...] = ()
    timeout: float = 120.0
    profiles: dict[str, Path] = field(default_factory=dict)
    dpf_path: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "workspace", Path(self.workspace).expanduser().resolve())
        object.__setattr__(self, "allowed_roots", tuple(Path(p).expanduser().resolve() for p in self.allowed_roots))
        if self.executable is not None:
            object.__setattr__(self, "executable", Path(self.executable).expanduser().resolve())
        if not 0 < self.timeout <= 3600:
            raise ValueError("timeout must be in (0, 3600] seconds")
        object.__setattr__(self, "profiles", {name: Path(value).expanduser().resolve() for name, value in self.profiles.items()})
        if self.dpf_path is not None:
            object.__setattr__(self, "dpf_path", str(Path(self.dpf_path).expanduser().resolve()))

    @classmethod
    def from_env(cls):
        workspace = os.environ.get("LSPP_WORKSPACE")
        if not workspace:
            raise ValueError("Set LSPP_WORKSPACE to an explicit local job directory")
        exe = os.environ.get("LSPP_EXECUTABLE")
        roots = tuple(Path(p) for p in os.environ.get("LSPP_ALLOWED_ROOTS", "").split(os.pathsep) if p)
        profiles = json.loads(os.environ.get("LSPP_EXECUTABLES", "{}"))
        return cls(Path(workspace), Path(exe) if exe else None, roots,
                   float(os.environ.get("LSPP_TIMEOUT", "120")), profiles, os.environ.get("LSPP_DPF_PATH"))

    def input_path(self, value: str, *, base: Path | None = None) -> Path:
        return self._input_path(value, base=base, directory=False)

    def input_directory(self, value: str) -> Path:
        """A search directory subject to the same network and allowed-root rules as files."""
        return self._input_path(value, base=None, directory=True)

    def _input_path(self, value: str, *, base: Path | None, directory: bool) -> Path:
        from .domain.model.includes import is_network

        # Reject Windows network/device syntax before filesystem resolution, even
        # on non-Windows hosts. Allowed-root checks cannot undo an earlier read.
        if is_network(str(value)) or PureWindowsPath(value).is_reserved():
            raise ValueError("Network and device input paths are not supported")
        p = Path(value).expanduser()
        if not p.is_absolute():
            p = (base or self.workspace) / p
        if is_network(str(p)) or PureWindowsPath(p).is_reserved():
            raise ValueError("Network and device input paths are not supported")
        p = p.resolve(strict=True)
        if not (p.is_dir() if directory else p.is_file()):
            raise ValueError("Input must be a directory" if directory else "Input must be a regular file")
        if not any(p.is_relative_to(root) for root in (self.workspace, *self.allowed_roots)):
            raise ValueError("Input is outside the configured allowed roots")
        command_path(p)
        return p

    def native_executable(self) -> Path:
        if self.executable is None or not self.executable.is_file():
            raise ValueError("LSPP_EXECUTABLE must point to an installed LS-PrePost executable")
        require_installation(self.executable)
        return self.executable

    def check_keyword_includes(self, path: Path, *, native_cwd: Path | None = None,
                               max_references: int = 20000) -> None:
        """Apply native policy; bound expanded references (0 rejects any INCLUDE name)."""
        self._keyword_report(path, native_cwd, max_references, allow_paths=False)

    def native_keyword_report(self, path: Path, *, max_references: int = 20000) -> dict:
        """Admit a complete tree for an owned normalized snapshot, including checked search dirs.

        Other native callers retain the existing plain-Include policy. Snapshot callers
        must normalize every filename/path card before handing the tree to LS-PrePost.
        """
        return self._keyword_report(path, None, max_references, allow_paths=True)

    def _keyword_report(self, path, native_cwd, max_references, *, allow_paths):
        if isinstance(max_references, bool) or not isinstance(max_references, int) or max_references < 0:
            raise ValueError("max_references must be an integer >= 0")
        from .domain.model import preflight_includes

        source = self.input_path(str(path))
        report = preflight_includes(source, max_references=max_references)
        references = report["references"]
        # Confinement errors take precedence over diagnostics about external contents.
        for entry in report["files"]:
            self.input_path(entry["path"])
        for ref in references:
            for candidate in ref["candidates"]:
                self.input_path(candidate)
            if allow_paths and ref["kind"] == "path" and ref["path"] is not None:
                self.input_directory(ref["path"])
        failure = ""
        if not report["ok"]:
            problem = next(p for p in report["problems"] if p["severity"] == "error")
            legacy = {"cycle": "Cyclic keyword include chain", "limit": "Keyword include limit exceeded",
                      "reference_limit": "Keyword include reference limit exceeded"}
            reason = problem.get("reason") or problem.get("hint") or "INCLUDE preflight failed"
            failure = "{}: kind={}, relative={}, name_line={}, reason={}".format(
                legacy.get(problem["kind"], "Keyword include preflight failed"), problem["kind"],
                problem["relative"], problem["name_line"], reason)
        details = "; " + failure if failure else ""
        for ref in references:
            directory = allow_paths and ref["kind"] == "path" and ref["keyword"] in (
                "*INCLUDE_PATH", "*INCLUDE_PATH_RELATIVE")
            if (directory and ref["keyword"] == "*INCLUDE_PATH_RELATIVE"
                    and Path(ref["file"]).parent != source.parent):
                raise ValueError("Nested INCLUDE_PATH_RELATIVE semantics require separate native validation")
            if ref["keyword"] != "*INCLUDE" and not directory:
                raise ValueError("Only plain *INCLUDE is supported in this release: " + ref["keyword"] + details)
            if "&" in ref["name"] or "%" in ref["name"]:
                raise ValueError("Parameterized includes require a future resolver" + details)
        if failure:
            raise ValueError(failure)
        if allow_paths and any(p["kind"] == "ambiguous" for p in report["problems"]):
            raise ValueError("Ambiguous INCLUDE resolution cannot be normalized for native reading")
        # A plain header with only comments is a disabled include alternative,
        # not a missing filename. Native 4.13 reads the remaining tree correctly.
        # Never extend that exception to unsupported INCLUDE variants.
        for problem in report["problems"]:
            if problem["kind"] == "empty_include" and problem["keyword"] != "*INCLUDE":
                raise ValueError("Only plain *INCLUDE is supported in this release: " + problem["keyword"])
        for entry in report["files"]:
            _check_include_layout(Path(entry["path"]))
        for ref in references:
            if native_cwd is not None and not Path(ref["name"]).is_absolute():
                # Native batches run in the job directory, not the source directory.
                # A cwd-relative alternative must not bypass the preflight tree.
                alternate = native_cwd / ref["name"]
                if alternate.exists():
                    checked = self.input_path(str(alternate))
                    if ref["path"] is None or checked != Path(ref["path"]).resolve():
                        raise ValueError("Native working-directory INCLUDE resolves to a different file")
        return report


def _check_include_layout(path):
    """Reject ignored keyword placement; filename parsing stays in shared preflight."""
    ended = False
    with path.open(encoding="latin1") as stream:
        for number, raw in enumerate(stream):
            content = raw[3:] if number == 0 and raw.startswith("\xef\xbb\xbf") else raw
            line = content.lstrip()
            if line.upper().startswith("*INCLUDE"):
                if line != content:
                    raise ValueError("INCLUDE keywords must start in the first column")
                if ended:
                    raise ValueError("INCLUDE after *END is not supported for native loading")
            header = line.split("$", 1)[0].split(",", 1)[0].strip().upper()
            if header == "*END":
                ended = True
