"""I03 batch proofs for centralized path commands and generated SCL bytes."""

from pathlib import Path

import pytest

from ls_prepost_mcp.native import commands as nc
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = pytest.mark.native


@pytest.mark.parametrize("name", ["addition.k", "added nodes.k", "新增 节点.k"], ids=["plain", "spaces", "unicode"])
def test_import_keyword_saves_and_reopens_imported_node(native_case, name):  # noqa: F811
    service, source = native_case
    fragment = service.settings.workspace / "addition.k"
    fragment.write_text("*KEYWORD\n*NODE\n1001,7,8,9\n*END\n", encoding="utf8")
    prepared = service.prepare_native_program("cfile", code="\n".join([
        nc.import_keyword(name), nc.save_keyword("saved nodes.k")]),
        dependencies=[dict(path=str(fragment), name=name)],
        outputs=[dict(name="saved nodes.k", kind="keyword")], expected_counts=dict(nodes=9))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                             model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    saved = result["artifacts"][0]["path"]
    assert Path(saved) == Path(result["job_directory"]) / "saved nodes.k"
    assert result["process"]["configuration"]["source_modified"] is False
    assert "-nographics" in result["process"]["argv"]
    reopened = service.inspect_model(saved)
    assert reopened["status"] == "succeeded", reopened
    assert reopened["data"]["counts"]["nodes"] == 9
    nodes = service.list_nodes(saved, limit=20)
    assert nodes["status"] == "succeeded", nodes
    # Counts alone cannot prove that import retained the requested ID/coordinates.
    assert any(row == [1001, 7, 8, 9] for row in nodes["data"]["rows"])


@pytest.mark.parametrize("name", ["curve.txt", "input curve.txt", "输入 曲线.txt"], ids=["plain", "spaces", "unicode"])
def test_xydata_open_and_export_preserve_curve_samples(native_case, name):  # noqa: F811
    service, source = native_case
    curve = service.settings.workspace / "curve-source.txt"
    curve.write_text("3\n0,0\n1,2\n2,4\n", encoding="ascii")
    prepared = service.prepare_native_program("cfile", code="\n".join([
        nc.open_xydata(name), "newplot", 'show "' + name + '~1" 0', nc.save_xypair("export curve.xy")]),
        dependencies=[dict(path=str(curve), name=name)],
        outputs=[dict(name="export curve.xy", kind="text")], expected_counts=dict(nodes=8))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                             model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    assert Path(result["artifacts"][0]["path"]) == Path(result["job_directory"]) / "export curve.xy"
    assert "-nographics" in result["process"]["argv"]
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


@pytest.mark.parametrize("name", ["count nodes.scl", "节点 计数.scl"], ids=["spaces", "unicode"])
def test_scl_dependency_path_preserves_count_and_job_identity(native_case, name):  # noqa: F811
    service, source = native_case
    script = service.settings.workspace / "source.scl"
    nc.write_scl(script, '/*LS-SCRIPT*/\r\n/* 中文 */\r\ndefine:\r\nvoid main(void){\r\n'
                 'FILE *fp;\r\nInt n;\r\nn=SCLGetDataCenterInt("num_nodes");\r\n'
                 'fp=fopen("node count.txt","w");\r\nfprintf(fp,"%d\\n",n);\r\nfclose(fp);\r\n}\r\nmain();\r\n')
    before = script.read_bytes()
    prepared = service.prepare_native_program("cfile", code=nc.run_script(name, "scl"),
        dependencies=[dict(path=str(script), name=name)],
        outputs=[dict(name="node count.txt", kind="text")], expected_counts=dict(nodes=8))
    result = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"],
                                            model=str(source / "input.k"))
    assert result["status"] == "succeeded", result
    assert "-nographics" in result["process"]["argv"]
    directory = Path(result["job_directory"])
    assert (directory / name).read_bytes() == before == script.read_bytes()
    assert Path(result["artifacts"][0]["path"]) == directory / "node count.txt"
    assert (directory / "node count.txt").read_text().strip() == "8"
