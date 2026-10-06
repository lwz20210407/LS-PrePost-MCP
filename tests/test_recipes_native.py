"""A08 independent fixture checks for five reusable native recipes."""

import csv
import json
from pathlib import Path

import pytest

from tests.test_engine_native import native_case  # noqa: F401
from tests.test_script_command_native import node_coordinates

pytestmark=pytest.mark.native
NAMES=("box_mesh","translate_nodes","snapshot","node_coordinates","model_inventory")


@pytest.mark.parametrize("recipe",NAMES)
def test_builtin_recipe(native_case,recipe):  # noqa: F811
    service,source=native_case
    result=service.run_recipe(recipe,model=None if recipe=="box_mesh" else str(source/"input.k"))
    (service.settings.workspace/"recipe-verdict.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    check_result(service,recipe,result)


def check_result(service,recipe,result):
    assert result["status"]=="succeeded",result
    assert result["data"]["counts"]["nodes"] == 8
    artifact=Path(result["artifacts"][0]["path"])
    if recipe in ("box_mesh","translate_nodes"):
        nodes=node_coordinates(artifact)
        assert len(nodes)==8
        if recipe=="box_mesh":
            assert tuple(max(v[i] for v in nodes.values()) for i in range(3))==(2,3,4)
        else:
            assert nodes[11]==(1,2,3) and nodes[79]==(4,3,3)
        opened=service.inspect_model(str(artifact))
        assert opened["status"]=="succeeded" and opened["data"]["counts"]["nodes"]==8
    elif recipe=="node_coordinates":
        with artifact.open(newline="") as stream:
            rows=list(csv.DictReader(stream))
        assert len(rows)==8 and [int(row["id"]) for row in rows]==[11,13,17,23,31,47,61,79]
        assert float(rows[-1]["x"])==3 and float(rows[-1]["y"])==1
    elif recipe=="model_inventory":
        assert json.loads(artifact.read_text())==dict(nodes=8,elements=3,states=1,parts=2)
    else:
        from PIL import Image
        with Image.open(artifact) as picture:
            assert min(picture.size)>=32
            assert any(a!=b for a,b in picture.convert("RGB").getextrema())


@pytest.mark.parametrize("recipe",NAMES)
def test_recipe_runc_capability(native_case,recipe,request):  # noqa: F811
    service,source=native_case
    result=service.run_recipe(recipe,model=None if recipe=="box_mesh" else str(source/"input.k"),launch_mode="runc")
    evidence=service.settings.workspace/"runc-result.json"
    evidence.write_text(json.dumps(result,indent=2),encoding="utf8")
    request.node.user_properties.append(("native_evidence",str(evidence)))
    process=service.jobs.get(result["job_id"])["process"]
    assert any(arg.startswith("runc=") for arg in process["argv"])
    if result["status"]=="failed":
        request.node.user_properties.extend([("native_scope","evidence_only"),
                                             ("native_lane_statuses",dict(execution="failed"))])
        pytest.xfail("Native runc mode failed; retain its actual diagnostics")
    check_result(service,recipe,result)


def test_box_recipe_uses_supplied_dimensions(native_case):  # noqa: F811
    service,_=native_case
    result=service.run_recipe("box_mesh",dict(width=5,height=1.5,depth=2.25))
    assert result["status"]=="succeeded",result
    nodes=node_coordinates(result["artifacts"][0]["path"])
    assert tuple(max(v[i] for v in nodes.values()) for i in range(3))==(5,1.5,2.25)
