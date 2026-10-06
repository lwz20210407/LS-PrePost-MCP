"""Q06 binout across MPP shards: shards written with lasso's own LSDA writer."""
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("lasso.dyna")

from lasso.dyna import Binout  # noqa: E402
from lasso.dyna.lsda_py3 import Lsda  # noqa: E402

from ls_prepost_mcp.domain.results import mpp_shards  # noqa: E402
from ls_prepost_mcp.domain.results.lasso_backend import ResultsError, binout_curves  # noqa: E402


def _shard(path: Path, database: str, ids: list[int], times: list[float], scale: float = 1.0,
           branch: str | None = None, first: int = 1) -> None:
    """One database (or branch) whose x_force of entity i at time t is scale * t * (i + 1)."""
    f = Lsda(str(path), "w")
    root = f"/{database}" + (f"/{branch}" if branch else "")
    f.cd(root + "/metadata", 1)
    f.write("ids", Lsda.I4, ids)
    for k, t in enumerate(times, start=first):
        f.cd(f"{root}/d{k:06d}", 1)
        f.write("time", Lsda.R8, [t])
        f.write("x_force", Lsda.R8, [scale * t * (i + 1) for i in range(len(ids))])
    f.close()


def test_state_name_collision_is_merged_where_the_lasso_glob_drops_samples(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "nodfor", [7, 9], [0.0, 0.1, 0.2, 0.3])
    _shard(tmp_path / "binout0003", "nodfor", [7, 9], [0.4, 0.5, 0.6])
    glob_times = Binout(str(tmp_path / "binout*")).read("nodfor", "time")
    assert len(glob_times) == 4  # d000001-d000003 of binout0000 are replaced by binout0003's
    result = binout_curves(tmp_path / "binout0000", "nodfor", "x_force")
    assert result["time"] == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert result["ids"] == [7, 9] and result["shards"] == ["binout0000", "binout0003"]
    assert np.allclose(result["values"], [[t, 2 * t] for t in result["time"]])
    assert result["repeated_times_dropped"] == 0


def test_repeated_time_must_carry_identical_values(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0002", "jntforc", [5], [0.0], branch="type0")
    _shard(tmp_path / "binout0006", "jntforc", [5], [0.0, 1.0, 2.0], branch="type0")
    result = binout_curves(tmp_path, "jntforc", "x_force", branch="type0")
    assert result["time"] == [0.0, 1.0, 2.0] and result["repeated_times_dropped"] == 1
    _shard(tmp_path / "binout0002", "jntforc", [5], [1.0], scale=2.0, branch="type0")
    with pytest.raises(ResultsError, match="time 1 is stored in several shards with different values"):
        binout_curves(tmp_path, "jntforc", "x_force", branch="type0")


def test_different_entities_are_refused_unless_one_shard_is_named(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "nodout", [1, 2], [0.0, 1.0])
    _shard(tmp_path / "binout0001", "nodout", [3], [0.0, 1.0])
    with pytest.raises(ResultsError, match="different entities"):
        binout_curves(tmp_path, "nodout", "x_force")
    one = binout_curves(tmp_path, "nodout", "x_force", shard="binout0001")
    assert one["ids"] == [3] and one["shards"] == ["binout0001"]
    with pytest.raises(ResultsError, match="No shard named"):
        binout_curves(tmp_path, "nodout", "x_force", shard="binout0009")


def test_catalog_and_nested_branches(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0000", "elout", [11, 12], [0.0, 1.0], branch="shell")
    _shard(tmp_path / "binout0005", "elout", [21], [0.0, 1.0], branch="beam")
    _shard(tmp_path / "binout0005%001", "elout", [21], [2.0], branch="beam", first=3)  # continuation
    (tmp_path / "binout.txt").write_text("not a shard")
    catalog = mpp_shards.catalog(tmp_path / "binout0005")
    assert catalog["shards"] == ["binout0000", "binout0005"]
    assert catalog["entries"] == {"elout/beam": ["binout0005"], "elout/shell": ["binout0000"]}
    assert catalog["split"] == {}
    with pytest.raises(ResultsError, match=r"give branch= one of \['beam', 'shell'\]"):
        binout_curves(tmp_path, "elout", "x_force")
    beam = binout_curves(tmp_path, "elout", "x_force", branch="beam")
    assert beam["time"] == [0.0, 1.0, 2.0]  # lasso opens the %001 continuation with its base file
    with pytest.raises(ResultsError, match="has no 'y_force'"):
        binout_curves(tmp_path, "elout", "y_force", branch="shell")


def test_three_level_branch_is_found(tmp_path: Path) -> None:
    _shard(tmp_path / "binout0007", "bndout", [4], [0.0, 1.0], branch="velocity/nodes")
    assert mpp_shards.catalog(tmp_path)["entries"] == {"bndout/velocity/nodes": ["binout0007"]}
    result = binout_curves(tmp_path, "bndout", "x_force", branch="velocity/nodes")
    assert result["time"] == [0.0, 1.0] and result["ids"] == [4]


def test_missing_folder_and_no_binout(tmp_path: Path) -> None:
    with pytest.raises(ResultsError, match="No binout files"):
        mpp_shards.shards(tmp_path)
    with pytest.raises(ResultsError, match="does not exist"):
        mpp_shards.shards(tmp_path / "nope" / "binout")
