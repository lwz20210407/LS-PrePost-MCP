"""Python-independent SCL inventory for older LS-PrePost installations."""
import re
import shutil
from pathlib import Path

from .jobs import atomic_json, fingerprint, now
from .native import commands as nc
from .runner import execute, failure_message


def inspect_database(settings, jobs, source: Path) -> dict:
    family = sorted(p for p in source.parent.iterdir() if p.is_file() and
                    (p.name == source.name or re.fullmatch(re.escape(source.name) + r"\d+", p.name)))
    family = [settings.input_path(str(p)) for p in family]
    if len(family) > 1000 or sum(p.stat().st_size for p in family) > 256 * 1024 * 1024:
        raise ValueError("SCL compatibility mode stages at most 1000 files / 256 MiB")
    directory, manifest = jobs.create("inspect_d3plot_scl", {"source": str(source), "backend": "lsprepost", "channel": "scl"})
    manifest.update(backend="lsprepost", native_channel="scl", inputs=[fingerprint(p) for p in family])
    try:
        for p in family:
            suffix = p.name[len(source.name):]
            shutil.copyfile(p, directory / ("d3plot" + suffix))
        script = ('/*LS-SCRIPT*/\ndefine:\nvoid main(void)\n{\n'
                  'Int nn, ne, ns;\nFILE *fp;\n'
                  'nn=SCLGetDataCenterInt("num_nodes");\n'
                  'ne=SCLGetDataCenterInt("num_elements");\n'
                  'ns=SCLGetDataCenterInt("num_states");\n'
                  'fp=fopen("counts.txt","w");\n'
                  'fprintf(fp,"%d %d %d\\n",nn,ne,ns);\nfclose(fp);\n}\nmain();\n')
        nc.write_scl(directory / "inventory.scl", script)
        commands = directory / "commands.cfile"
        nc.write_cfile(commands, ["new", nc.open_model("d3plot", "d3plot", openc=True), nc.run_script("inventory.scl", "scl"), "exit"])
        process = execute(settings.native_executable(), commands, directory, timeout=settings.timeout, graphics=False)
        manifest["process"] = process
        if process.get("engine_status") == "failed" or process["returncode"] != 0 or process["timed_out"]:
            raise RuntimeError(failure_message(process, "Native SCL inventory process failed"))
        nodes, elements, states = [int(x) for x in (directory / "counts.txt").read_text().split()]
        if min(nodes, elements, states) <= 0:
            raise ValueError("SCL inventory did not produce valid model counts")
        manifest.update(status="succeeded", data={"backend": "lsprepost", "native_channel": "scl",
                       "counts": {"nodes": nodes, "elements": elements, "states": states},
                       "requires_python": False, "staged_files": len(family)})
    except Exception as exc:
        manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
    manifest.update(finished_at=now(), job_directory=str(directory),
                    logs=[str(p) for p in directory.glob("*.log")] + [str(p) for p in directory.glob("lspost.*")])
    atomic_json(directory / "job.json", manifest)
    return manifest
