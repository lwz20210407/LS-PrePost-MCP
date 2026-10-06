"""A03 arrays/CSV checked against embedded Python and fixed user-ID geometry."""

import csv
import json

import pytest

from ls_prepost_mcp.sessions import Sessions
from tests.test_engine_native import native_case  # noqa: F401

pytestmark = pytest.mark.native

SCL = '''/*LS-SCRIPT*/
define:
void main(void){
Int n,i,k; Int *ids=NULL; Float *x=NULL,*y=NULL,*z=NULL,*sums=NULL; FILE *fp;
n=SCLGetDataCenterInt("num_nodes");
ids=malloc(n*sizeof(Int)); x=malloc(n*sizeof(Float)); y=malloc(n*sizeof(Float)); z=malloc(n*sizeof(Float));
sums=malloc(n*sizeof(Float));
k=SCLGetDataCenterIntArray("node_ids",&ids,0,0);
k=SCLGetDataCenterFloatArray("node_x",NODE,0,&x);
k=SCLGetDataCenterFloatArray("node_y",NODE,0,&y);
k=SCLGetDataCenterFloatArray("node_z",NODE,0,&z);
fp=fopen("nodes.csv","w"); fprintf(fp,"id,x,y,z,sum\\n");
for(i=0;i<n;i=i+1){sums[i]=x[i]+y[i]+z[i];}
for(i=0;i<n;i=i+1){fprintf(fp,"%d,%.9g,%.9g,%.9g,%.9g\\n",ids[i],x[i],y[i],z[i],sums[i]);}
fclose(fp); free(ids);free(x);free(y);free(z);free(sums);
}
main();
'''

PYTHON = '''import csv,DataCenter as dc
ids=[int(v) for v in dc.get_data("node_ids")]
x=[float(v) for v in dc.get_data("node_x",type=dc.Type.NODE)]
y=[float(v) for v in dc.get_data("node_y",type=dc.Type.NODE)]
z=[float(v) for v in dc.get_data("node_z",type=dc.Type.NODE)]
with open("python-nodes.csv","w",newline="") as stream:
    writer=csv.writer(stream); writer.writerow(["id","x","y","z","sum"])
    writer.writerows((uid,a,b,c,a+b+c) for uid,a,b,c in zip(ids,x,y,z))
'''


def rows(path):
    with open(path, newline="") as stream:
        return {int(r["id"]): tuple(float(r[k]) for k in ("x", "y", "z", "sum")) for r in csv.DictReader(stream)}


@pytest.mark.parametrize("context", ["batch", "session"])
def test_scl_array_csv_and_compile_line(native_case, context):  # noqa: F811
    service, source = native_case
    sid = None
    options = dict(model=str(source / "input.k"))
    if context == "session":
        sid = Sessions(service.settings).start(transport="queue")["session_id"]
        assert service.open_in_gui_session(sid, str(source / "input.k"))["status"] == "succeeded"
        options = dict(session_id=sid)
    try:
        result = service.run_script("scl", SCL, context=context, **options,
                                    outputs=[dict(name="nodes.csv", kind="csv")], expected_counts=dict(nodes=8))
        (service.settings.workspace / "scl-result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        assert result["status"] == "succeeded", result
        actual = rows(result["artifacts"][0]["path"])
        assert actual == dict(zip([11,13,17,23,31,47,61,79],
                                 [(0,0,0,0),(1,0,0,1),(2,0,0,2),(3,0,0,3),(0,1,0,1),(1,1,0,2),(2,1,0,3),(3,1,0,4)]))
        if "4.13" in str(service.settings.executable):
            prepared = service.prepare_native_program("python", code=PYTHON, outputs=[dict(name="python-nodes.csv",kind="csv")])
            equivalent = service.execute_native_program(prepared["job_id"], prepared["data"]["sha256"], **options)
            assert equivalent["status"] == "succeeded", equivalent
            assert rows(equivalent["artifacts"][0]["path"]) == actual
        invalid = service.run_script("scl", '/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nInt n = ;\n}\nmain();\n',
                                     context=context, **options)
        (service.settings.workspace / "scl-error.json").write_text(json.dumps(invalid, indent=2), encoding="utf8")
        assert invalid["status"] == "failed", invalid
        assert any(d["line"] == 4 for d in invalid["data"]["diagnostics"]), invalid
    finally:
        if sid:
            service.close_gui_session(sid, save_checkpoint=False)
