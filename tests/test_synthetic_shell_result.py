import numpy as np
import pytest


def test_original_shell_fixture_has_known_layers_and_deletion_without_overwriting(tmp_path):
    pytest.importorskip("lasso")
    from lasso.dyna import D3plot

    from ls_prepost_mcp.jobs import fingerprint
    from ls_prepost_mcp.result_validity import load_physical_validity
    from tools.synthetic_shell_result import create_fixture

    source, truth = create_fixture(tmp_path / "fresh-fixture")
    original = fingerprint(source)
    database = D3plot(str(source))
    physical = load_physical_validity(source, [1,2,3], "shell")
    assert physical.user_ids.tolist() == [101,305,9001]
    assert physical.mask.sum(axis=1).tolist() == [3,2,1]
    stress = database.arrays["element_shell_stress"][:, :, 1, 0]
    assert [float(stress[i][physical.mask[i]].max()) for i in range(3)] == [2000.,60.,60.]
    assert np.array_equal(database.arrays["node_displacement"][0], database.arrays["node_coordinates"])
    assert truth["synthetic"] and not truth["solver_run"]
    with pytest.raises(FileExistsError):
        create_fixture(source.parent)
    assert fingerprint(source) == original
