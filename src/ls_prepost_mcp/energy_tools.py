"""Q12 JobResult wrapper over shared energy readers and dimensionless checks."""
import os
from pathlib import Path

from .core.contracts import Artifact, CheckResult, JobResult
from .core.validation import unit_label
from .domain.results import energy, energy_readers, mpp_shards
from .jobs import atomic_json, check_artifact, fingerprint
from .post_backend import write_csv


def _failed(error, job_id=None):
    return JobResult(operation="check_energy", status="failed", backend="energy-readers",
                     job_id=job_id, error={"type": type(error).__name__,
                                          "message": str(error) or type(error).__name__}).model_dump(mode="json")


def _binary(source):
    with source.open("rb") as stream:
        raw = stream.read(8)
    return (len(raw) == 8 and raw[0] >= 8 and all(size in (1, 2, 4, 8) for size in raw[1:5])
            and raw[5] <= 1)


class EnergyTools:
    def check_energy(self, path: str, units: str, include_parts: bool = True, matsum_path: str | None = None,
                     input_format: str = "auto", kinetic_ratio_limit: float | None = None,
                     hourglass_ratio_limit: float | None = None, residual_ratio_limit: float | None = None,
                     sliding_ratio_limit: float | None = None, ratio_floor: float = 1e-3,
                     relative_floor: float = 1e-12, time_units: str = "model_time") -> dict:
        """Q12: GLSTAT energy report plus optional MATSUM decomposition, no native process.

        Missing quantities/CSV cells stay null/empty. No threshold means metrics
        only. Ratios exclude |IE| below ratio_floor*max|IE| and report undefined
        counts. Balance requires recorded TE and external work, using their initial
        values as the reference. Nonstandard binary names are refused; binout reads
        use the existing confined standard MPP family, never a neighbour fallback.
        matsum_path selects an ASCII companion explicitly; otherwise use the sibling
        matsum for ASCII or the same binary family. Units are declarations only.
        """
        directory = manifest = None
        try:
            units, time_units = unit_label(units), unit_label(time_units)
            energy.validate_parameters(units, dict(kinetic_energy=kinetic_ratio_limit,
                hourglass_energy=hourglass_ratio_limit, energy_balance=residual_ratio_limit,
                sliding_energy=sliding_ratio_limit), ratio_floor, relative_floor)
            if type(include_parts) is not bool or input_format not in ("auto", "ascii", "binout"):
                raise ValueError("include_parts must be Boolean and input_format auto/ascii/binout")
            if matsum_path is not None and not include_parts:
                raise ValueError("matsum_path requires include_parts=True")
            source = self.settings.input_path(path)
            kind = input_format
            if kind == "auto":
                kind = "binout" if source.name.lower().startswith("binout") or _binary(source) else "ascii"
            part_source, sources = None, [source]
            if kind == "binout":
                if matsum_path is not None:
                    raise ValueError("Binary MATSUM must use the same confined binout family")
                source = self._database_source(str(source))
                sources = sorted({self.settings.input_path(str(p))
                                  for shard in mpp_shards.shards(source) for p in mpp_shards.lasso_reads(shard)})
            elif include_parts:
                candidate = Path(matsum_path) if matsum_path else source.with_name("matsum")
                if matsum_path is not None or os.path.lexists(candidate):
                    part_source = self.settings.input_path(str(candidate))
                    sources.append(part_source)
            identities = {p: fingerprint(p) for p in sources}
            directory, manifest = self.jobs.create("check_energy", dict(path=str(source), units=units, time_units=time_units,
                input_format=kind, include_parts=include_parts, kinetic_ratio_limit=kinetic_ratio_limit,
                hourglass_ratio_limit=hourglass_ratio_limit, residual_ratio_limit=residual_ratio_limit,
                sliding_ratio_limit=sliding_ratio_limit, ratio_floor=ratio_floor, relative_floor=relative_floor))
            data = energy_readers.read_binout_glstat(source) if kind == "binout" else energy_readers.read_ascii_glstat(source)
            parts, part_error = {}, None
            if include_parts:
                try:
                    if kind == "binout":
                        parts = energy_readers.read_binout_matsum(source)
                    elif part_source:
                        parts = energy_readers.read_ascii_matsum(part_source)
                    else:
                        raise ValueError("ASCII MATSUM companion not supplied or present")
                except (ValueError, OSError, KeyError, IndexError) as error:
                    part_error = str(error) or type(error).__name__
            report = energy.calculate_energy_balance(data, parts, units, kinetic_ratio_limit,
                hourglass_ratio_limit, residual_ratio_limit, sliding_ratio_limit, ratio_floor, relative_floor)
            summary = report["summary"]
            summary.update(backend="lasso-python" if kind == "binout" else "lsdyna-ascii",
                           input_format=kind, time_units=time_units, input_identities=list(identities.values()),
                           input_identity_policy="SHA256 up to 64 MiB; size/mtime otherwise",
                           parts_time_axis="stored MATSUM times; no interpolation to GLSTAT",
                           part_status="not_requested" if not include_parts else "unavailable" if part_error else "read")
            if any("sha256" not in identity for identity in identities.values()):
                summary["warnings"].append("Large source identities use size/mtime, not full content hashes")
            if part_error:
                summary["warnings"].append("MATSUM could not be read: " + part_error)
                summary["part_error"] = part_error
                if summary["verdict"] == "passed":
                    summary.update(global_verdict="passed", verdict="incomplete", passed=None)
            if kind == "binout":
                current = {self.settings.input_path(str(p))
                           for shard in mpp_shards.shards(source) for p in mpp_shards.lasso_reads(shard)}
                if current != set(identities):
                    raise ValueError("Energy input family membership changed while being read")
            artifacts = [write_csv(directory / "energy_balance.csv", list(energy.SERIES_HEADER),
                                   report["series_rows"], set(energy.SERIES_HEADER) - {"time"})]
            if report["part_series_rows"]:
                artifacts.append(write_csv(directory / "part_energy.csv", list(energy.PART_HEADER),
                    report["part_series_rows"], set(energy.PART_HEADER) - {"time", "part_id"}))
            if any(fingerprint(p) != identity for p, identity in identities.items()):
                raise ValueError("Energy input family changed while being read")
            atomic_json(directory / "summary.json", summary)
            artifacts.append(check_artifact(directory / "summary.json", "json"))
            incomplete = summary["verdict"] == "incomplete" or part_error is not None or not summary["time_monotonic"]
            result = JobResult(operation="check_energy", status="partial" if incomplete else "succeeded",
                backend=summary["backend"], job_id=manifest["job_id"], data=summary,
                warnings=summary["warnings"], checks=[CheckResult(name=name, status=check["status"])
                    for name, check in summary["checks"].items()], artifacts=[Artifact(
                        path=a["path"], kind=a["kind"], sha256=a.get("sha256"), size_bytes=a["size"],
                        verification="verified" if a.get("sha256") else "unverified", metadata=a)
                        for a in artifacts]).model_dump(mode="json")
        except Exception as error:
            result = _failed(error, manifest["job_id"] if manifest else None)
        if manifest:
            try:
                atomic_json(directory / "job.json", {**manifest, "status": result["status"], "result": result})
            except (OSError, ValueError) as error:
                result = _failed(error, manifest["job_id"])
        return result
