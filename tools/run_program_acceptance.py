"""Opt-in native command/cfile/SCL/Python/macro acceptance using synthetic data."""

import argparse
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    root = args.workspace.resolve() / ("native-programs-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    examples = Path(__file__).resolve().parents[1] / "examples" / "native"
    service = Service(Settings(root, args.executable.resolve(), (examples,), timeout=60))
    results = []

    def check(name, call, expected="succeeded"):
        result = call()
        results.append(dict(name=name, result=result))
        atomic_json(root / "acceptance.json", results)
        if result.get("status", result.get("state")) != expected:
            raise RuntimeError(
                name + " did not meet expected status; inspect " + str(root / "acceptance.json")
            )
        print(name + ": " + expected, flush=True)
        return result

    def run(name, language, outputs, model=None, code=None, path=None):
        prepared = check(
            name + "-prepare",
            lambda: service.prepare_native_program(
                language, code=code, path=path, outputs=outputs, expected_counts={"nodes": 8, "elements": 1}
            ),
            "prepared",
        )
        return check(
            name,
            lambda: service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], model),
        )

    mesh = run("cfile", "cfile", [dict(name="mesh.k", kind="keyword")], path=str(examples / "box.cfile"))
    model = mesh["artifacts"][0]["path"]
    run(
        "command", "command", [dict(name="command.k", kind="keyword")], model, code='save keyword "command.k"'
    )
    scl = run(
        "scl", "scl", [dict(name="nodes.txt", kind="text")], model, path=str(examples / "node_count.scl")
    )
    if int(Path(scl["artifacts"][0]["path"]).read_text()) != 8:
        raise RuntimeError("SCL output count mismatch")
    if not args.skip_python:
        run(
            "python",
            "python",
            [dict(name="nodes.json", kind="json")],
            model,
            path=str(examples / "node_count.py"),
        )
    code = (examples / "box.cfile").read_text().replace("2 3 4", "{{width}} 3 4")
    macro = check(
        "macro-define",
        lambda: service.create_native_macro(
            "box width",
            "cfile",
            code,
            {"width": 2},
            outputs=[dict(name="mesh.k", kind="keyword")],
            expected_counts={"nodes": 8, "elements": 1},
        ),
    )
    modified = check(
        "macro-run", lambda: service.run_native_macro(macro["artifacts"][0]["path"], {"width": 5})
    )
    if not args.skip_python:
        nodes = check("macro-nodes", lambda: service.list_nodes(modified["artifacts"][0]["path"]))
        if max(row[1] for row in nodes["data"]["rows"]) != 5:
            raise RuntimeError("Macro width not reflected in native coordinates")
    if args.gui:
        started = check("gui-start", service.start_gui_session, "ready")
        sid = started["session_id"]
        check("gui-open", lambda: service.open_in_gui_session(sid, model))
        check(
            "gui-command",
            lambda: service.execute_gui_command(
                sid,
                'save keyword "raw_saved.k"',
                outputs=[dict(name="raw_saved.k", kind="keyword")],
                expected_counts={"nodes": 8},
            ),
        )
        check("gui-unverified", lambda: service.execute_gui_command(sid, "top"), "completed_unverified")
        check("gui-close", lambda: service.close_gui_session(sid), "closed")
    print("Evidence: " + str(root / "acceptance.json"))


if __name__ == "__main__":
    main()
