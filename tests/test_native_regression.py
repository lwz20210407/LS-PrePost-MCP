import json
from pathlib import Path

import pytest

from tools.native_regression import (
    ROOT,
    Case,
    arguments,
    cases,
    parser_schema,
    resolve_value,
    run_case,
    verify_reports,
)


def test_every_manual_entrypoint_is_collected_and_gui_variants_are_explicit():
    catalog = cases()
    assert {case.script for case in catalog} == set((ROOT / "tools").glob("run_*.py"))
    assert len({case.id for case in catalog}) == len(catalog)
    programs = [c for c in catalog if c.script.stem == "run_program_acceptance"]
    assert {(c.variant, c.gui) for c in programs} == {("batch", False), ("gui", True)}


def test_schema_capture_does_not_run_acceptance_and_handles_loop_flags(tmp_path):
    source = tmp_path / "probe.py"
    source.write_text('''import argparse
p=argparse.ArgumentParser()
for name in ('workspace','executable','source'):
    p.add_argument('--'+name,required=True)
p.add_argument('--states',nargs='+',type=int)
a=p.parse_args()
raise RuntimeError('Acceptance body must not run during schema discovery')
''')
    schema = parser_schema(source)
    assert [row["flags"] for row in schema] == [["--workspace"], ["--executable"], ["--source"], ["--states"]]


@pytest.mark.parametrize("supplied", [
    {"workspace": "outside"}, {"keep-open": True}, {"skip-python": True},
    {"source": ["x", "--workspace", "outside"]}, {"states": [1, "--workspace", "outside"]},
])
def test_case_arguments_cannot_redirect_output_or_reduce_coverage(tmp_path, supplied):
    schema = [dict(flags=["--" + name], required=False, nargs=None, boolean=False)
              for name in ("workspace", "executable", "source", "keep-open", "skip-python")]
    schema.append(dict(flags=["--states"], required=False, nargs="+", boolean=False))
    with pytest.raises(ValueError):
        arguments(Case(Path("run_probe.py")), schema, supplied, tmp_path, "native.exe")


def test_cli_success_alone_cannot_pass_a_failed_native_inventory(tmp_path):
    (tmp_path / "native-results.json").write_text(json.dumps([dict(result=dict(status="failed"))]))
    with pytest.raises(AssertionError, match="failed or unverified"):
        verify_reports(Case(Path("run_native_acceptance.py")), tmp_path)


def test_negative_workflow_cases_remain_valid_when_the_script_asserts_them(tmp_path):
    (tmp_path / "acceptance.json").write_text(json.dumps(dict(cases={"rejected": dict(status="failed")})))
    evidence = verify_reports(Case(Path("run_workflow_gate_acceptance.py")), tmp_path)
    assert len(evidence) == 1 and len(evidence[0]["sha256"]) == 64


def test_real_script_failure_and_fresh_output_rules(tmp_path):
    script = tmp_path / "run_test.py"
    script.write_text('''import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--workspace');a=p.parse_args()
pathlib.Path(a.workspace,'acceptance.json').write_text(json.dumps({'status':'failed'}))
''')
    case = Case(script, "file")
    output = tmp_path / "case"
    with pytest.raises(AssertionError, match="rejected"):
        run_case(case, ["--workspace", str(output)], output, 10)
    assert (output / "stdout.log").exists()
    with pytest.raises(FileExistsError):
        run_case(case, ["--workspace", str(output)], output, 10)


def test_private_corpus_ids_do_not_resolve_from_a_guessed_path(tmp_path, monkeypatch):
    monkeypatch.setenv("LSPP_CORPUS_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="private ID only"):
        resolve_value({"corpus": "fangzhen"})
