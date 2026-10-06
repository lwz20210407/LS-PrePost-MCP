"""L3 scenario definitions: one YAML file per natural-language task, graded only by deterministic checks.

A scenario names its fixtures, the prompt a user would type, the checks on the final workspace state
and a reference solution (``oracle``: MCP tool calls) that proves the task is solvable with the
current tool surface. ``{last}`` in an oracle argument is the main deck written by the previous step.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

SCENARIOS = Path(__file__).parents[2] / "tests" / "l3" / "scenarios"
FIXTURES = Path(__file__).parents[2] / "tests" / "l3" / "fixtures"
KEYWORD_SUFFIXES = (".k", ".key", ".dyn", ".kw")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Check(Strict):
    check: str
    params: dict = Field(default_factory=dict)


class OracleStep(Strict):
    tool: str
    args: dict


class Limits(Strict):
    max_turns: int = Field(30, ge=1, le=200)
    timeout_s: int = Field(900, ge=30, le=7200)


class Scenario(Strict):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^(pre|post|auto)\d{2}_[a-z0-9_]+$")
    domain: Literal["pre", "post", "auto"]
    task_ids: list[str] = Field(min_length=1)
    title: str
    prompt: str = Field(min_length=10)
    fixtures: list[str] = Field(min_length=1)
    model: str | None = None  # main input deck; the final deck is the newest job output with this name
    checks: list[Check] = Field(min_length=1)
    limits: Limits = Limits()
    oracle: list[OracleStep] = Field(default_factory=list)
    oracle_answer: str = ""
    notes: str = ""


class _Loader(yaml.SafeLoader):
    """YAML 1.2 floats: PyYAML (YAML 1.1) reads 4.77e8 or -1.0e5 as strings."""


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:(?:\d[\d_]*)?\.\d+(?:[eE][-+]?\d+)?|\d[\d_]*\.(?:[eE][-+]?\d+)?|\d[\d_]*[eE][-+]?\d+)$"
               r"|^[-+]?\.(?:inf|Inf|INF)$|^\.(?:nan|NaN|NAN)$"),
    list("-+0123456789."))


def load(path: Path) -> Scenario:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506 - SafeLoader subclass
    scenario = Scenario.model_validate(data)
    if path.stem != scenario.id or path.parent.name != scenario.domain:
        raise ValueError(f"{path}: file must be <domain>/<id>.yaml")
    missing = [name for name in scenario.fixtures if not (FIXTURES / name).is_file()]
    if missing:
        raise ValueError(f"{scenario.id}: missing fixtures {missing}")
    if scenario.model is not None and scenario.model not in scenario.fixtures:
        raise ValueError(f"{scenario.id}: model must be one of the fixtures")
    return scenario


def load_all(domain: str | None = None, ids: tuple[str, ...] = ()) -> list[Scenario]:
    paths = sorted(SCENARIOS.glob(f"{domain or '*'}/*.yaml"))
    scenarios = [load(path) for path in paths]
    if len({s.id for s in scenarios}) != len(scenarios):
        raise ValueError("Duplicate scenario IDs")
    if ids:
        unknown = sorted(set(ids) - {s.id for s in scenarios})
        if unknown:
            raise ValueError(f"Unknown scenarios: {unknown}")
        scenarios = [s for s in scenarios if s.id in ids]
    return scenarios


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Workspace:
    """A fresh directory per run: the fixtures, their hashes, and the jobs the agent creates."""

    root: Path
    scenario: Scenario
    input_hashes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, root: Path, scenario: Scenario) -> Workspace:
        root = root.resolve()
        if root.exists() and any(root.iterdir()):
            raise ValueError(f"Workspace {root} is not empty")
        root.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for name in scenario.fixtures:
            shutil.copyfile(FIXTURES / name, root / name)
            hashes[name] = sha256(root / name)
        return cls(root, scenario, hashes)

    def outputs(self) -> list[Path]:
        jobs = self.root / "jobs"
        if not jobs.is_dir():
            return []
        return [p for p in jobs.rglob("*") if p.is_file() and p.suffix.lower() in KEYWORD_SUFFIXES]

    def _job_order(self, path: Path) -> tuple[str, int]:
        """Order outputs by their job's creation (unchanged files may be copied with the input's mtime)."""
        job = self.root / "jobs" / path.relative_to(self.root / "jobs").parts[0]
        try:
            created = str(json.loads((job / "job.json").read_text(encoding="utf-8")).get("created_at", ""))
        except (OSError, ValueError):
            created = ""
        return created, job.stat().st_mtime_ns

    def final_deck(self) -> Path | None:
        """Deck named like the input model from the newest job, else any keyword file of the newest job."""
        outputs = self.outputs()
        if self.scenario.model:
            named = [p for p in outputs if p.name == self.scenario.model]
            if named:
                return max(named, key=self._job_order)
        return max(outputs, key=self._job_order) if outputs else None


__all__ = ["Check", "FIXTURES", "Limits", "OracleStep", "SCENARIOS", "Scenario", "Workspace", "load", "load_all",
           "sha256"]
