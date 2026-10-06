"""I02: semantic failures must be rejected before a backend or job is invoked."""

import copy
import json

import pytest
from pydantic import ValidationError

from ls_prepost_mcp.core.contracts import (
    Artifact,
    CheckResult,
    CurveSpec,
    FieldSpec,
    JobResult,
    ModelRef,
    Selector,
)
from ls_prepost_mcp.outcomes import normalize_outcome
from ls_prepost_mcp.workflow_checks import evaluate_gate


def model():
    return ModelRef(
        kind="d3plot", files=[dict(path="case/d3plot", sha256="a" * 64, size_bytes=1024)], units="mm-ms-g"
    )


def field_request():
    return dict(
        quantity="stress",
        components=["xx", "yy", "zz", "xy", "yz", "zx"],
        units="MPa",
        backend="lsprepost",
        selector=dict(entity_type="shell", predicate=dict(kind="ids", ids=[101])),
        at=dict(kind="states", indices=[1, 3]),
        sampling=dict(kind="native_layer", layer="outer"),
        frame="global",
        averaging="none",
    )


def test_six_contracts_have_json_schema_and_round_trip_without_losing_semantics():
    objects = [
        model(),
        Selector(entity_type="node", predicate=dict(kind="none")),
        FieldSpec(**field_request()),
        CurveSpec(
            source=model(),
            database="nodout",
            entity_type="node",
            entity_ids=[101],
            component="z_displacement",
            units="mm",
            time_units="ms",
        ),
        Artifact(path="job/field.csv", kind="csv", sha256="b" * 64, size_bytes=128, verification="verified"),
        JobResult(operation="extract_field", status="succeeded", backend="lsprepost", data=dict(state=1)),
    ]
    for value in objects:
        assert type(value).model_validate_json(value.model_dump_json()) == value
        json.dumps(type(value).model_json_schema(), allow_nan=False)
    assert objects[1].predicate.kind == "none"  # empty selection is explicit
    assert objects[2].at.indices == (1, 3)
    assert objects[2].sampling.layer == "outer"


@pytest.mark.parametrize("bad", [True, False, 0, -1, "1", 1.5])
def test_user_ids_never_coerce_boolean_string_or_array_indices(bad):
    with pytest.raises(ValidationError):
        Selector(entity_type="node", predicate=dict(kind="ids", ids=[bad]))


def test_selector_discriminator_rejects_mixed_actions_and_keeps_boolean_tree():
    selection = Selector(
        entity_type="node",
        configuration="deformed",
        state=4,
        predicate=dict(
            kind="boolean",
            operator="intersection",
            operands=[dict(kind="parts", ids=[2]), dict(kind="box", minimum=[0, 0, 0], maximum=[10, 5, 1])],
        ),
    )
    assert selection.predicate.operands[0].ids == (2,)
    assert selection.state == 4
    with pytest.raises(ValidationError):
        Selector(entity_type="node", predicate=dict(kind="ids", ids=[1], radius=2))
    for predicate in (
        dict(kind="ids", ids=[1, 1]),
        dict(kind="box", minimum=[1, 0, 0], maximum=[0, 1, 1]),
        dict(kind="plane", origin=[0, 0, 0], normal=[0, 0, 0], tolerance=0),
        dict(kind="sphere", center=[0, 0, 0], radius=float("inf")),
    ):
        with pytest.raises(ValidationError):
            Selector(entity_type="node", predicate=predicate)


@pytest.mark.parametrize(
    "context",
    [
        dict(configuration="deformed"),
        dict(configuration="reference", state=2),
        dict(configuration="deformed", state=0),
    ],
)
def test_deformed_and_reference_coordinates_cannot_be_ambiguous(context):
    with pytest.raises(ValidationError):
        Selector(entity_type="node", predicate=dict(kind="all"), **context)


def test_include_occurrences_require_file_identity_and_acyclic_parentage():
    files = [
        dict(path="main.k", sha256="a" * 64, size_bytes=1),
        dict(path="part.k", sha256="b" * 64, size_bytes=2),
    ]
    tree = [
        dict(id="root", file_path="main.k", raw_reference="main.k"),
        dict(id="first", parent_id="root", file_path="part.k", raw_reference="part.k"),
        dict(
            id="second",
            parent_id="root",
            file_path="part.k",
            raw_reference="part.k",
            parameters=dict(v="&speed"),
        ),
    ]
    assert len(ModelRef(kind="keyword", files=files, include_tree=tree).include_tree) == 3
    for alteration in (dict(parent_id="missing"), dict(parent_id="first"), dict(file_path="unknown.k")):
        modified = copy.deepcopy(tree)
        modified[1].update(alteration)
        with pytest.raises(ValidationError):
            ModelRef(kind="keyword", files=files, include_tree=modified)


@pytest.mark.parametrize(
    "patch",
    [
        dict(backend="lasso"),
        dict(selector=dict(entity_type="node", predicate=dict(kind="all"))),
        dict(at=dict(kind="states", indices=[0])),
        dict(at=dict(kind="time", value=1)),
        dict(frame="local"),
        dict(coordinate_system_id=3),
        dict(components=["xx", "xx"]),
        dict(sampling=dict(kind="stored_point", index=1)),
        dict(units=" "),
    ],
)
def test_field_requests_reject_backend_layer_state_or_unit_confusion(patch):
    values = field_request()
    values.update(patch)
    with pytest.raises(ValidationError):
        FieldSpec(**values)


def test_reader_point_and_time_matching_are_explicit():
    values = field_request()
    values.update(
        backend="lasso",
        sampling=dict(kind="stored_point", index=2),
        at=dict(kind="time", value=0.5, units="ms", match="nearest"),
    )
    request = FieldSpec(**values)
    assert request.sampling.index == 2 and request.at.units == "ms"


def test_curve_global_ids_and_filter_parameters_are_strict():
    values = dict(
        source=model(),
        database="glstat",
        entity_type="global",
        component="kinetic_energy",
        units="J",
        time_units="s",
    )
    assert CurveSpec(**values).entity_ids == ()
    with pytest.raises(ValidationError):
        CurveSpec(**values, entity_ids=[1])
    with pytest.raises(ValidationError):
        CurveSpec(**values, filter=dict(kind="butterworth", order=True, cutoff_hz=10))
    with pytest.raises(ValidationError):
        CurveSpec(**values, filter=dict(kind="sae", cfc=600, cutoff_hz=10))


def test_verified_artifact_requires_hash_identity_and_never_opens_paths():
    with pytest.raises(ValidationError):
        Artifact(path="does-not-exist", kind="csv", verification="verified")
    Artifact(path="does-not-exist", kind="csv", sha256="f" * 64, size_bytes=0, verification="verified")
    with pytest.raises(ValidationError):
        Artifact(path="field.csv", kind="csv", sha256="bad")


@pytest.mark.parametrize(
    "status", ["prepared", "running", "completed_unverified", "timeout", "ready", None, True]
)
def test_job_status_schema_is_closed(status):
    with pytest.raises(ValidationError):
        JobResult(operation="inspect", status=status)
    assert JobResult.model_json_schema()["properties"]["status"]["enum"] == [
        "succeeded",
        "failed",
        "partial",
        "unverified",
    ]


def test_nonfinite_json_and_success_with_execution_error_are_rejected():
    with pytest.raises(ValidationError):
        JobResult(operation="inspect", status="succeeded", data=dict(rows=[float("nan")]))
    with pytest.raises(ValidationError):
        JobResult(operation="inspect", status="succeeded", error=dict(message="bad"))


def test_gate_uses_canonical_status_and_checks_not_legacy_envelope():
    job = JobResult(
        operation="check",
        status="failed",
        error=dict(message="Native execution failed"),
        checks=[CheckResult(name="quality", status="passed")],
        comparison_data=dict(status="succeeded", verification=dict(passed_checks=True)),
    )
    assert not evaluate_gate(job, [], "report_only")["passed"]
    job = JobResult(
        operation="check",
        status="succeeded",
        checks=[CheckResult(name="quality", status="failed")],
        comparison_data=dict(verification=dict(passed_checks=True)),
    )
    assert not evaluate_gate(job, [])["passed"]
    assert evaluate_gate(job, [], "report_only")["passed"]
    with pytest.raises(TypeError):
        evaluate_gate(dict(status="succeeded"), [])


def test_gate_revalidates_mutated_data_and_model_copy_bypasses():
    job = JobResult(operation="inspect", status="succeeded", data=dict(value=1.0))
    job.data["value"] = float("nan")
    with pytest.raises(ValidationError):
        evaluate_gate(job, [])
    bad = JobResult(operation="inspect", status="succeeded").model_copy(update=dict(status="running"))
    with pytest.raises(ValidationError):
        evaluate_gate(bad, [])


@pytest.mark.parametrize("kind", ["ids", "parts", "sets"])
def test_empty_id_selection_requires_explicit_none(kind):
    predicate = dict(kind=kind, ids=[])
    if kind == "sets":
        predicate["set_type"] = "node"
    with pytest.raises(ValidationError):
        Selector(entity_type="node", predicate=predicate)


@pytest.mark.parametrize("values", [dict(status="failed"), dict(status="failed", error={}),
                                     dict(status="partial"), dict(status="partial", warnings=["incomplete"]),
                                     dict(status="partial", data=dict(rows=3))])
def test_incomplete_outcomes_must_explain_failure_and_partial_outputs(values):
    with pytest.raises(ValidationError):
        JobResult(operation="read", **values)


def test_partial_with_outputs_and_not_applicable_check_aggregation():
    assert JobResult(operation="read", status="partial", warnings=["one file missing"], data=dict(rows=3))
    assert JobResult(operation="read", status="partial", error=dict(message="second file failed"),
                     artifacts=[dict(path="first.csv",kind="csv")])
    checks = [dict(name="a",status="passed"),dict(name="b",status="not_applicable")]
    result = JobResult(operation="read",status="succeeded",checks=checks)
    assert result.check_status == "passed" and evaluate_gate(result, [])["passed"]
    assert JobResult(operation="read",status="succeeded",checks=checks[1:]).check_status == "not_applicable"


def test_legacy_preparation_has_a_distinct_stage_without_a_fifth_status():
    prepared = normalize_outcome(
        "prepare_native_program", dict(status="prepared", data=dict(sha256="a" * 64))
    )
    assert (
        isinstance(prepared, JobResult) and prepared.status == "succeeded" and prepared.stage == "preparation"
    )
    assert not normalize_outcome("prepare_native_program", dict(status="succeeded")).execution_accepted
    assert not normalize_outcome("inspect_model", dict(status="prepared")).execution_accepted


def test_legacy_artifact_without_sha_is_not_promoted_to_verified_identity():
    result = normalize_outcome(
        "inspect_model",
        dict(
            status="succeeded",
            artifacts=[dict(path="big.csv", kind="csv", size=100, sha256=None, validated=True)],
        ),
    )
    assert result.artifacts[0].verification == "unverified"


def test_typed_check_cannot_omit_verdict_to_bypass_automatic_gate(tmp_path, monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    service = Service(Settings(tmp_path))
    called = []
    monkeypatch.setattr(
        service,
        "check_gui_keywords",
        lambda **kwargs: JobResult(operation="check_gui_keywords", status="succeeded"),
    )
    monkeypatch.setattr(service, "process_curve", lambda **kwargs: called.append(True))
    workflow = service.create_workflow(
        "Typed missing verdict",
        [
            dict(id="check", action="check_gui_keywords", arguments={}),
            dict(id="after", action="process_curve", arguments={}),
        ],
    )["artifacts"][0]["path"]
    result = service.run_workflow(workflow, session_id="test-session")
    assert result["status"] == "failed" and not called
    assert result["data"]["gates"]["check"]["reasons"] == ["quality_verdict_missing"]
    assert result["data"]["steps"]["check"]["status"] == "succeeded"


def test_canonical_preparation_requires_matching_stage():
    with pytest.raises(ValueError, match="stage"):
        normalize_outcome(
            "prepare_native_program", JobResult(operation="prepare_native_program", status="succeeded")
        )


def test_typed_results_flow_through_workflow_bindings_and_json_evidence(tmp_path, monkeypatch):
    from ls_prepost_mcp.config import Settings
    from ls_prepost_mcp.service import Service

    service = Service(Settings(tmp_path))
    observed = []

    def inspect(**kwargs):
        observed.append(kwargs)
        return JobResult(
            operation="inspect_model",
            status="succeeded",
            data=dict(value=3),
            evidence=[Artifact(path="native.log", kind="log")],
        )

    monkeypatch.setattr(service, "inspect_model", inspect)
    workflow = service.create_workflow(
        "Canonical result bindings",
        [
            dict(
                id="first",
                action="inspect_model",
                arguments={},
                checks=[dict(path=["data", "value"], operator="eq", value=3)],
            ),
            dict(
                id="second",
                action="inspect_model",
                arguments=dict(model={"$result": "first", "path": ["data", "value"]}),
            ),
        ],
    )["artifacts"][0]["path"]
    result = service.run_workflow(workflow)
    assert result["status"] == "succeeded"
    assert observed == [{}, {"model": 3}]
    assert result["data"]["steps"]["first"]["evidence"][0]["path"] == "native.log"


def test_curve_time_axis_is_explicit_and_interval_ordered():
    values = dict(
        source=model(),
        database="history",
        entity_type="node",
        entity_ids=[101],
        component="x",
        units="mm",
        time_units="ms",
    )
    spec = CurveSpec(**values, time_column="physical_time", time_range=[0, 10])
    assert spec.time_column == "physical_time" and spec.time_range == (0.0, 10.0)
    for interval in ([10, 0], [1, 1], [0, float("inf")]):
        with pytest.raises(ValidationError):
            CurveSpec(**values, time_range=interval)


def test_persisted_job_result_is_not_reinterpreted_as_a_legacy_envelope():
    value = JobResult(
        operation="check_gui_keywords",
        status="succeeded",
        checks=[CheckResult(name="quality", status="passed")],
    )
    restored = normalize_outcome("check_gui_keywords", json.loads(value.model_dump_json()))
    assert restored.check_status == "passed" and evaluate_gate(restored, [])["passed"]
    prepared = normalize_outcome("prepare_native_program", dict(status="prepared"))
    assert normalize_outcome(
        "prepare_native_program", json.loads(prepared.model_dump_json())
    ).execution_accepted
