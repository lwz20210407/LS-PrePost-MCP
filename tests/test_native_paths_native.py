"""I03 batch proofs for centralized path commands and generated SCL bytes."""

from pathlib import Path

import pytest

from ls_prepost_mcp.native import commands as nc
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = pytest.mark.native


def test_import_keyword_saves_and_reopens_imported_node(native_case):  # noqa: F811
    service, source = native_case
    fragment = service.settings.workspace / "addition.k"
    fragment.write_text("*KEYWORD\n*NODE\n1001,7,8,9\n*END\n", encoding="utf8")
    prepared = service.prepare_native_program("cfile", code="\n".join([
        nc.import_keyword("addition.k"), nc.save_keyword("saved.k")]),
        dependencies=[dict(path=str(fragment), name="addition.k")],
        outputs=[dict(name="saved.k", kind="keyword")], expected_counts=dict(nodes=9))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                             model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    saved = result["artifacts"][0]["path"]
    reopened = service.inspect_model(saved)
    assert reopened["status"] == "succeeded", reopened
    assert reopened["data"]["counts"]["nodes"] == 9
    nodes = service.list_nodes(saved, limit=20)
    assert nodes["status"] == "succeeded", nodes
    # Counts alone cannot prove that import retained the requested ID/coordinates.
    assert any(row == [1001, 7, 8, 9] for row in nodes["data"]["rows"])


def test_xydata_open_and_export_preserve_curve_samples(native_case):  # noqa: F811
    service, source = native_case
    curve = service.settings.workspace / "curve-source.txt"
    curve.write_text("3\n0,0\n1,2\n2,4\n", encoding="ascii")
    prepared = service.prepare_native_program("cfile", code="\n".join([
        nc.open_xydata("curve.txt"), "newplot", 'show "curve.txt~1" 0', nc.save_xypair("export.xy")]),
        dependencies=[dict(path=str(curve), name="curve.txt")],
        outputs=[dict(name="export.xy", kind="text")], expected_counts=dict(nodes=8))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                             model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    rows = []
    for line in Path(result["artifacts"][0]["path"]).read_text(encoding="utf8").splitlines():
        values = line.split()
        if len(values) == 2:
            try:
                rows.append(tuple(float(value) for value in values))
            except ValueError:
                pass
    assert rows == [(0, 0), (1, 2), (2, 4)]


def test_scl_utf8_comment_and_count_artifact(native_case):  # noqa: F811
    service, source = native_case
    code = ('/*LS-SCRIPT*/\r\n/* UTF-8 中文注释 */\r\ndefine:\r\nvoid main(void){\r\n'
            'FILE *fp;\r\nInt n;\r\nn=SCLGetDataCenterInt("num_nodes");\r\n'
            'fp=fopen("count.txt","w");\r\nfprintf(fp,"%d\\n",n);\r\nfclose(fp);\r\n}\r\nmain();\r\n')
    prepared = service.prepare_native_program("scl", code=code, outputs=[dict(name="count.txt", kind="text")],
                                               expected_counts=dict(nodes=8))
    script = Path(prepared["job_directory"]) / "program.scl"
    assert script.read_bytes() == code.replace("\r\n", "\n").encode("utf8")
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                             model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    assert Path(result["artifacts"][0]["path"]).read_text().strip() == "8"
