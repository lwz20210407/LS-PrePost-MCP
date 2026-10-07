"""I01: native admission bounds repeated INCLUDE expansion before launching LS-PrePost."""
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.domain import model as api
from ls_prepost_mcp.service import Service


def _tree(root, layers):
    for index in range(layers + 1):
        text = (f"*INCLUDE\nl{index + 1}.k\n*INCLUDE\nl{index + 1}.k\n"
                if index < layers else "*NODE\n")
        (root / f"l{index}.k").write_text("*KEYWORD\n" + text + "*END\n", encoding="ascii")
    return root / "l0.k"


def test_default_budget_rejects_doubling_tree_before_native_launch(tmp_path, monkeypatch):
    main = _tree(tmp_path, 14)  # 32766 references, only 15 unique files.
    service = Service(Settings(tmp_path))
    monkeypatch.setattr(Settings, "native_executable", lambda self: tmp_path / "unused.exe")
    monkeypatch.setattr("ls_prepost_mcp.service.run_batch",
                        lambda *a, **kw: pytest.fail("must reject before native launch"))
    monkeypatch.setattr(service.jobs, "create",
                        lambda *a, **kw: pytest.fail("must reject before creating a job"))
    with pytest.raises(ValueError, match="Keyword include reference limit exceeded") as error:
        service.inspect_model(str(main))
    message = str(error.value)
    assert "kind=reference_limit" in message
    assert "relative=l" in message and "name_line=" in message
    assert "reason=More than 20000 include references" in message


@pytest.mark.parametrize("budget,passes", [(13, False), (14, True), (15, True)])
def test_repeated_subtrees_count_towards_exact_boundary(tmp_path, budget, passes):
    main = _tree(tmp_path, 3)  # 14 references, including repeated descendants.
    settings = Settings(tmp_path)
    if passes:
        settings.check_keyword_includes(main, max_references=budget)
    else:
        with pytest.raises(ValueError, match="kind=reference_limit"):
            settings.check_keyword_includes(main, max_references=budget)


def test_zero_allows_no_includes_and_stops_before_resolving_first_name(tmp_path, monkeypatch):
    main = _tree(tmp_path, 0)
    settings = Settings(tmp_path)
    settings.check_keyword_includes(main, max_references=0)
    main.write_text("*KEYWORD\n*INCLUDE\nnever-resolve.k\n*END\n", encoding="ascii")
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        assert path.name != "never-resolve.k", "over-budget name reached filesystem resolution"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="kind=reference_limit, relative=l0.k, name_line=3, reason="):
        settings.check_keyword_includes(main, max_references=0)


@pytest.mark.parametrize("budget", [True, False, -1, 1.5, "20", None])
def test_invalid_budget_rejected_before_any_input_path_access(tmp_path, monkeypatch, budget):
    settings = Settings(tmp_path)
    main = tmp_path / "missing.k"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid budget must be rejected before filesystem access")

    with monkeypatch.context() as patch:
        for method in ("resolve", "stat", "lstat", "open"):
            patch.setattr(Path, method, forbidden)
        with pytest.raises(ValueError, match="max_references"):
            settings.check_keyword_includes(main, max_references=budget)


def test_preflight_receives_budget_without_network_override(tmp_path, monkeypatch):
    main = _tree(tmp_path, 0)
    preflight = api.preflight_includes
    calls = []

    def checked(source, **kwargs):
        calls.append(kwargs)
        return preflight(source, **kwargs)

    monkeypatch.setattr(api, "preflight_includes", checked)
    Settings(tmp_path).check_keyword_includes(main)
    assert calls == [{"max_references": 20000}]


@pytest.mark.parametrize("external", [False, True])
def test_missing_and_outside_inputs_still_rejected(tmp_path, external):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    main = allowed / "main.k"
    name = "../outside.k" if external else "missing.k"
    (tmp_path / "outside.k").write_text("*KEYWORD\n*END\n", encoding="ascii")
    main.write_text(f"*KEYWORD\n*INCLUDE\n{name}\n*END\n", encoding="ascii")
    with pytest.raises(ValueError, match="outside" if external else "kind=missing.*name_line=3"):
        Settings(allowed).check_keyword_includes(main, max_references=1)


@pytest.mark.parametrize("candidate_only", [False, True])
def test_confinement_precedes_reference_limit_diagnostic(tmp_path, monkeypatch, candidate_only):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    main = _tree(allowed, 1)
    outside = tmp_path / "outside.k"
    outside.write_text("*KEYWORD\n*END\n", encoding="ascii")
    report = api.preflight_includes(main, max_references=1)
    assert not report["ok"]
    if candidate_only:
        report["references"][0]["candidates"].append(str(outside))
    else:
        report["files"].append({"path": str(outside)})
    monkeypatch.setattr(api, "preflight_includes", lambda source, **kwargs: report)
    with pytest.raises(ValueError, match="outside"):
        Settings(allowed).check_keyword_includes(main)
