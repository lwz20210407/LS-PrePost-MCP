"""Create an original tiny binary fixture, explicitly not a solved engineering case."""

from importlib.metadata import version
from pathlib import Path

import numpy as np
from lasso.dyna import D3plot

from ls_prepost_mcp.jobs import atomic_json, fingerprint


def create_fixture(directory):
    directory = Path(directory).resolve()
    # The writer removes matching destination families. Require a fresh directory
    # so it cannot replace a caller's existing model/results.
    directory.mkdir(parents=True, exist_ok=False)
    if version("lasso-python") != "2.0.4":
        raise ValueError("Synthetic fixture writer is pinned to LASSO2.0.4")
    database = D3plot()
    coordinates = np.array([[x,y,0.] for y in (0.,1.) for x in (0.,1.,2.,3.)], dtype=np.float32)
    arrays = database.arrays
    arrays.update(
        node_coordinates=coordinates,
        node_ids=np.array([11,13,17,23,31,47,61,79], dtype=np.int32),
        part_ids=np.array([7,42], dtype=np.int32),
        element_shell_ids=np.array([101,305,9001], dtype=np.int32),
        element_shell_node_indexes=np.array([[0,1,5,4],[1,2,6,5],[2,3,7,6]], dtype=np.int32),
        element_shell_part_indexes=np.array([0,0,1], dtype=np.int32),
        timesteps=np.array([0.,.5,1.], dtype=np.float32),
        # The pinned writer uses the same absolute-coordinate convention as its reader.
        node_displacement=np.tile(coordinates, (3,1,1)),
        element_shell_stress=np.zeros((3,3,3,6), dtype=np.float32),
        element_shell_is_alive=np.array([[1,1,2],[1,0,2],[0,0,2]], dtype=np.float32),
    )
    for element, stress in enumerate((10.,1000.,30.)):
        for point in range(3):
            arrays["element_shell_stress"][:,element,point,0] = stress * (point+1)
    path = directory / "d3plot"
    database.write_d3plot(str(path))
    reread = D3plot(str(path))
    for name, expected in arrays.items():
        if name not in reread.arrays or not np.array_equal(reread.arrays[name], expected):
            raise ValueError("Synthetic binary round-trip changed " + name)
    truth = dict(synthetic=True, solver_run=False, purpose="Physical deletion, sparse user IDs and shell-point contract",
                 units=dict(stress="Pa", time="s", length="m"), states=[1,2,3], shell_ids=[101,305,9001],
                 retained_counts=[3,2,1], point2_maximum=[2000.,60.,60.],
                 point2_values={"101":20.,"305":2000.,"9001":60.},
                 deletion_codes=arrays["element_shell_is_alive"].tolist(), source=fingerprint(path))
    atomic_json(directory / "truth.json", truth)
    return path, truth
