"""Pending native proofs for explicit aliases; require --run-native and a lease.

These retain numeric/readback assertions. Offline rejection is not native success.
"""

from pathlib import Path

import pytest

from ls_prepost_mcp.native import commands as nc
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = pytest.mark.native


@pytest.mark.parametrize("reader", ["keyword", "xy", "scl"])
def test_explicit_ascii_bundle_alias_from_unicode_source(native_case, reader):  # noqa: F811
    service, fixture = native_case
    source = service.settings.workspace / "中文 源文件.txt"
    if reader == "keyword":
        payload = b"*KEYWORD\n*NODE\n1001,7,8,9\n*END\n"
        code = nc.import_keyword("input data.txt") + "\n" + nc.save_keyword("saved.k")
        output, kind, count = "saved.k", "keyword", 9
    elif reader == "xy":
        payload = b"3\n0,0\n1,2\n2,4\n"
        code = '\n'.join([nc.open_xydata("input data.txt"), "newplot", 'show "input data.txt~1" 0',
                          nc.save_xypair("export.xy")])
        output, kind, count = "export.xy", "text", 8
    else:
        payload = ('/*LS-SCRIPT*/\n/* 中文注释 */\ndefine:\nvoid main(void){\n'
                   'FILE *fp;\nInt n;\nn=SCLGetDataCenterInt("num_nodes");\n'
                   'fp=fopen("count.txt","w");\nfprintf(fp,"%d\\n",n);\nfclose(fp);\n}\nmain();\n').encode()
        code = nc.run_script("input data.txt", "scl")
        output, kind, count = "count.txt", "text", 8
    source.write_bytes(payload)
    prepared = service.prepare_native_program("cfile", code=code,
        dependencies=[dict(path=str(source), name="input data.txt")],
        outputs=[dict(name=output, kind=kind)], expected_counts=dict(nodes=count))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                            model=str(fixture / "input.k"), graphics=False)
    assert result["status"] == "succeeded", result
    directory = Path(result["job_directory"])
    assert directory.name == result["job_id"] != prepared["job_id"]
    assert result["data"]["bundle_sha256"] == prepared["data"]["sha256"]
    assert (directory / "input data.txt").read_bytes() == source.read_bytes() == payload
    artifact = Path(result["artifacts"][0]["path"])
    assert artifact.resolve() == (directory / output).resolve()
    if reader == "keyword":
        reopened = service.inspect_model(str(artifact))
        assert reopened["status"] == "succeeded", reopened
        assert reopened["data"]["counts"]["nodes"] == 9
        nodes = service.list_nodes(str(artifact), limit=20)
        assert nodes["status"] == "succeeded", nodes
        assert [1001, 7, 8, 9] in nodes["data"]["rows"]
    elif reader == "xy":
        rows = []
        for line in artifact.read_text(encoding="utf8").splitlines():
            values = line.split()
            if len(values) == 2:
                try:
                    rows.append(tuple(float(value) for value in values))
                except ValueError:
                    pass
        assert rows == [(0, 0), (1, 2), (2, 4)]
    else:
        assert artifact.read_text().strip() == "8"
