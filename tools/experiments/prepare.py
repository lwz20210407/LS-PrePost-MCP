"""I10: prepare all experiment sources and 75 matrix cells without launching LSPP."""

import argparse
import json
import shutil
import uuid
from pathlib import Path


def prepare(root, result):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    fixture = root / "fixture"
    fixture.mkdir()
    # Require the complete original synthetic three-state family.
    for path in result.parent.glob(result.name + "*"):
        if path.is_file():
            shutil.copy2(path, fixture / path.name)
    cells = []
    for desktop in ("unlocked", "locked", "rdp_disconnected"):
        for version in ("4.13", "4.10"):
            modes = ("runc", "nographics", "session") if version == "4.13" else ("runc", "nographics")
            for mode in modes:
                for language in ("command", "cfile", "scl", "python", "macro"):
                    cell = dict(
                        id=f"{version}-{mode}-{language}-{desktop}",
                        version=version,
                        mode=mode,
                        language=language,
                        desktop=desktop,
                        execution="not_run",
                        png="not_run",
                        mp4="not_run",
                    )
                    directory = root / cell["id"]
                    directory.mkdir()
                    rid = uuid.uuid4().hex
                    receipt = (
                        '/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nFILE *f;\nInt n;\nn=SCLGetDataCenterInt("num_nodes");\nf=fopen("'
                        + str(directory / "receipt.txt").replace("\\", "\\\\")
                        + '","w");\nfprintf(f,"'
                        + rid
                        + ' %d\\n",n);\nfclose(f);\n}\nmain();\n'
                    )
                    (directory / "receipt.scl").write_text(receipt, encoding="ascii")
                    export = 'save keyword "' + str(directory / "model.k") + '"'
                    (directory / "program.cfile").write_text(export + "\n", encoding="utf8")
                    (directory / "program.py").write_text(
                        "import LsPrePost\nLsPrePost.execute_command(" + repr(export) + ")\n", encoding="utf8"
                    )
                    (directory / "program.mac").write_text(
                        "*macro begin M0Export\n" + export + "\n*macro end\n", encoding="utf8"
                    )
                    # SCL runs a data query; no undocumented command-execution API is invented.
                    payload = dict(
                        command=export,
                        cfile='openc command "' + str(directory / "program.cfile") + '" nodialog',
                        scl='runscript "' + str(directory / "receipt.scl") + '"',
                        python='runpython "' + str(directory / "program.py") + '"',
                        macro=None,
                    )[language]
                    start = "" if mode == "session" else 'openc d3plot "' + str(fixture / result.name) + '"\n'
                    cell.update(request_id=rid, directory=str(directory), expected_nodes=8)
                    if language == "macro":
                        cell["execution"] = "unverified_native_launcher"
                        cell["note"] = (
                            "Load original program.mac and execute M0Export in native Macro panel; do not substitute flattened cfile for .mac execution."
                        )
                    else:
                        commands = start + payload + '\nrunscript "' + str(directory / "receipt.scl") + '"\n'
                        for lane, tail in dict(
                            execution="",
                            png='isometric\nauto fit\nprint png "'
                            + str(directory / "image.png")
                            + '" opaque enlisted "OGL1x1"\n',
                            mp4='anim stop\nanim first 1\nanim last 3\nanim incr 1\nmovie MP4/H264 640x480 "'
                            + str(directory / "movie")
                            + '" 5\n',
                        ).items():
                            (directory / (lane + ".cfile")).write_text(
                                commands + tail + ("exit\n" if mode != "session" else ""), encoding="utf8"
                            )
                    cells.append(cell)
    for mode in ("E1", "E2", "E3", "E4"):
        directory = root / mode
        directory.mkdir()
        (directory / "requests").mkdir()
        rid = uuid.uuid4().hex
        config = dict(experiment=mode, directory=str(directory), request_id=rid, timeout=180)
        (directory / "config.json").write_text(json.dumps(config), encoding="utf8")
        shutil.copy2(Path(__file__).with_name("native_probe.py"), directory / "native_probe.py")
        (directory / "bootstrap.py").write_text(
            "import sys\nsys.path.insert(0,"
            + repr(str(directory))
            + ")\nimport native_probe\nnative_probe.run("
            + repr(str(directory / "config.json"))
            + ")\n",
            encoding="utf8",
        )
        (directory / "start.cfile").write_text(
            'openc d3plot "'
            + str(fixture / result.name)
            + '"\nrunpython "'
            + str(directory / "bootstrap.py")
            + '"\n',
            encoding="utf8",
        )
    (root / "matrix.json").write_text(json.dumps(cells, indent=2), encoding="utf8")
    return cells


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--synthetic-d3plot", type=Path, required=True)
    args = parser.parse_args()
    print(
        "Prepared",
        len(prepare(args.output, args.synthetic_d3plot)),
        "matrix cells; no native process started",
    )
