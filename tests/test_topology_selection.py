import math

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.embedded import topology_shell_ids
from ls_prepost_mcp.service import Service


def folded():
    c = math.cos(math.pi/6)
    return ({101:[1,2,5,4],205:[2,3,6,5],309:[3,7,8,6],413:[4,9,10,11]},
            {1:[0,0,0],2:[1,0,0],3:[1+c,0,.5],4:[0,1,0],5:[1,1,0],6:[1+c,1,.5],
             7:[1+c+.5,0,.5+c],8:[1+c+.5,1,.5+c],9:[-1,1,0],10:[-1,2,0],11:[0,2,0]})


def test_node_adjacency_and_edge_propagation_have_different_contracts():
    faces, xyz = folded()
    assert topology_shell_ids(faces, xyz, [101], "adjacent", 1, 30) == [101,205,413]
    assert topology_shell_ids(faces, xyz, [101], "adjacent", 2, 30) == [101,205,309,413]
    assert topology_shell_ids(faces, xyz, [101], "propagate", 1, 20) == [101]
    assert topology_shell_ids(faces, xyz, [101], "propagate", 1, 45) == [101,205,309]
    faces[205] = list(reversed(faces[205]))
    assert topology_shell_ids(faces, xyz, [101], "propagate", 1, 45) == [101,205,309]


def test_invisible_bridge_blocks_propagation_and_missing_seeds_fail():
    faces, xyz = folded()
    faces.pop(205)
    assert topology_shell_ids(faces, xyz, [101], "propagate", 1, 80) == [101]
    with pytest.raises(ValueError, match="visible"):
        topology_shell_ids(faces, xyz, [205], "propagate", 1, 80)


@pytest.mark.parametrize("args", [dict(seed_ids=[True]),dict(seed_ids=[]),dict(seed_ids=[1],rings=0),
    dict(seed_ids=[1],feature_angle=float("nan")),dict(seed_ids=[1],scope="all"),
    dict(seed_ids=[1],mode="propagate",rings=2),dict(seed_ids=[1],mode="adjacent",feature_angle=45.)])
def test_invalid_topology_requests_do_not_contact_gui(tmp_path, monkeypatch, args):
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(service, "_session_manager", lambda: pytest.fail("Invalid request contacted GUI"))
    with pytest.raises(ValueError):
        service.select_gui_shell_topology("absent", **args)
    assert not list(tmp_path.iterdir())
