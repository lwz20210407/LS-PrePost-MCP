"""Opt-in visible nested cfile, SCL/data, Python modules and bundled macro replay."""

import argparse
import json
import uuid
from pathlib import Path

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.jobs import atomic_json
from ls_prepost_mcp.service import Service


def accept(workspace, executable):
    root = Path(workspace).resolve() / ("bundle-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    service = Service(Settings(root, Path(executable), timeout=120))
    sid = service.start_gui_session()["session_id"]
    checks = []

    def asset(name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf8")
        return dict(path=str(path), name=name)

    def checked(name, result, status="succeeded"):
        atomic_json(root / (name+".json"), result)
        assert result["status"] == status, result.get("error")
        checks.append(name)
        print(name, flush=True)
        return result

    def execute(name, language, code, dependencies, outputs):
        prepared = checked(name+"-prepare", service.prepare_native_program(language, code=code,
            dependencies=dependencies, outputs=outputs, expected_counts=dict(nodes=8, elements=1)), "prepared")
        return checked(name, service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], session_id=sid))

    try:
        service.show_gui_session(sid, maximize=True)
        shape = asset("lib/shape.cfile", "meshing boxsolid create 0 0 0 2 3 4 1 1 1 0\nmeshing boxsolid accept 1 1 1 boxsolid\n")
        build = asset("lib/build.cfile", 'openc command "lib/shape.cfile" nodialog\n')
        execute("nested-cfile", "cfile", 'openc command "lib/build.cfile" nodialog\nsave keyword "mesh.k"\n',
                [build,shape], [dict(name="mesh.k",kind="keyword")])
        execute("single-command", "command", 'save keyword "command.k"', [], [dict(name="command.k",kind="keyword")])
        datum = asset("data/value.txt", "5\n")
        scl = '/*LS-SCRIPT*/\ndefine:\nvoid main(void){FILE *fi,*fo;Int n,b;char *buf;buf=malloc(32);fi=fopen("data/value.txt","r");fgets(buf,32,fi);b=atoi(buf);free(buf);fclose(fi);n=SCLGetDataCenterInt("num_nodes");fo=fopen("sum.txt","w");fprintf(fo,"%d\\n",n+b);fclose(fo);}\nmain();\n'
        result = execute("scl-data", "scl", scl, [datum], [dict(name="sum.txt",kind="text")])
        assert int(Path(result["artifacts"][0]["path"]).read_text()) == 13
        for value in (7,19):
            helper = asset("helper.py", "VALUE="+str(value)+"\n")
            result = execute("python-"+str(value), "python", 'import helper,json\njson.dump(helper.VALUE,open("value.json","w"))',
                             [helper], [dict(name="value.json",kind="json")])
            assert json.loads(Path(result["artifacts"][0]["path"]).read_text()) == value
        helper = asset("pkg/helper.py", 'import json\ndef calculate(factor):\n    return json.load(open("data/config.json"))["base"]*factor\n')
        init = asset("pkg/__init__.py", "")
        config = asset("data/config.json", '{"base":5}')
        macro = checked("macro", service.create_native_macro("bundle scale", "python",
            'from pkg.helper import calculate\nimport json\njson.dump(calculate({{factor}}),open("value.json","w"))',
            dict(factor=2), outputs=[dict(name="value.json",kind="json")], expected_counts=dict(nodes=8),
            dependencies=[helper,init,config]))
        # The macro must use its captured config, not this subsequently changed original.
        Path(config["path"]).write_text('{"base":99}')
        service.start_session_recording(sid)
        result = checked("macro-run", service.run_native_macro(macro["artifacts"][0]["path"], dict(factor=2), session_id=sid))
        assert json.loads(Path(result["artifacts"][0]["path"]).read_text()) == 10
        record = checked("recording", service.stop_session_recording(sid))
        assert record["managed_steps"] == 1
        template = checked("template", service.parameterize_workflow(record["workflow"],
            [dict(step_id="step1", path=["parameters","factor"], parameter="factor")]))
        checked("post-macro-checkpoint", service.checkpoint_gui_session(sid))
        replay = checked("replay", service.run_workflow(template["artifacts"][0]["path"], dict(factor=4), sid))
        assert json.loads(Path(replay["data"]["steps"]["step1"]["artifacts"][0]["path"]).read_text()) == 20
        atomic_json(root / "acceptance.json", dict(status="succeeded", checks=checks,
            scope="Visible4.13.4 nested cfile mesh, SCL declared data, fresh Python helpers across bundles, frozen package/data macro assets and changed-parameter recorded GUI replay. No arbitrary imports/includes/global macro-menu certification."))
    finally:
        atomic_json(root / "closed.json", service.close_gui_session(sid, save_checkpoint=False))
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--executable", required=True)
    args = parser.parse_args()
    print(accept(args.workspace, args.executable))
