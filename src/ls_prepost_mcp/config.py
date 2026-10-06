"""Explicit local configuration and file access boundaries."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

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
        p = Path(value).expanduser()
        if not p.is_absolute():
            p = (base or self.workspace) / p
        p = p.resolve(strict=True)
        if not p.is_file():
            raise ValueError("Input must be a regular file")
        if not any(p.is_relative_to(root) for root in (self.workspace, *self.allowed_roots)):
            raise ValueError("Input is outside the configured allowed roots")
        command_path(p)
        return p

    def native_executable(self) -> Path:
        if self.executable is None or not self.executable.is_file():
            raise ValueError("LSPP_EXECUTABLE must point to an installed LS-PrePost executable")
        require_installation(self.executable)
        return self.executable

    def check_keyword_includes(self, path: Path, seen: set[Path] | None = None) -> None:
        """Validate plain *INCLUDE chains; explicitly reject unsupported resolution rules."""
        seen = set() if seen is None else seen
        if path in seen:
            raise ValueError("Cyclic keyword include chain")
        if len(seen) >= 100:
            raise ValueError("Keyword include limit exceeded")
        seen.add(path)
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        pending = False
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("$"):
                continue
            if line.startswith("*"):
                if pending:
                    raise ValueError("Empty *INCLUDE card")
                keyword = line.split(",")[0].upper().split()[0]
                if keyword.startswith("*INCLUDE"):
                    if keyword != "*INCLUDE":
                        raise ValueError("Only plain *INCLUDE is supported in this release: " + keyword)
                    pending = True
            elif pending:
                if "&" in line or "%" in line:
                    raise ValueError("Parameterized includes require a future resolver")
                child = self.input_path(line.strip('\"'), base=path.parent)
                self.check_keyword_includes(child, set(seen))
                pending = False
        if pending:
            raise ValueError("Empty *INCLUDE card")
