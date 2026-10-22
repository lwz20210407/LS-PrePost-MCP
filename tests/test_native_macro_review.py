"""A05 review: reproducible evidence and explicit compiler-only boundaries."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.native_macros import compile_macro
from ls_prepost_mcp.service import Service

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/decisions/evidence/a05/evidence.json'


def evidence():
    return json.loads(EVIDENCE.read_text(encoding='utf8'))


def blob(ref):
    return subprocess.check_output(['git', 'cat-file', 'blob', ref], cwd=ROOT)


def require_history():
    if not (ROOT / '.git').exists():
        pytest.skip('Historical evidence requires a Git checkout')
    if subprocess.check_output(['git', 'rev-parse', '--is-shallow-repository'], cwd=ROOT).strip() == b'true':
        pytest.skip('Historical evidence requires full Git history')


def test_p1_88a_committed_baseline_counts_match_report(tmp_path):
    require_history()
    recorded = evidence()['local_tests']
    baseline = recorded['baseline']
    # Run the exact committed test blob against the recorded main implementations.
    # The rest of the package comes from this checkout, without editing its files.
    overlay = tmp_path / 'overlay' / 'ls_prepost_mcp'
    overlay.mkdir(parents=True)
    (overlay / '__init__.py').write_text('__version__ = "0.4.0"\n')
    for name, identity in baseline['implementation_files'].items():
        source = blob(identity['git_blob_id'])
        assert blob(baseline['implementation_revision'] + ':' + name) == source
        assert hashlib.sha256(source).hexdigest() == identity['sha256_lf']
        (overlay / Path(name).name).write_bytes(source)
    test_source = blob(baseline['test_git_blob_id'])
    assert blob(baseline['test_revision'] + ':tests/test_native_macro_parameters.py') == test_source
    assert hashlib.sha256(test_source).hexdigest() == baseline['test_sha256_lf']
    test = tmp_path / 'test_baseline.py'
    test.write_bytes(test_source)
    launcher = tmp_path / 'run.py'
    launcher.write_text('''import json,sys
from pathlib import Path
import ls_prepost_mcp
ls_prepost_mcp.__path__.append(sys.argv[1])
import ls_prepost_mcp.native_macros as nm
import ls_prepost_mcp.programs as pg
assert Path(nm.__file__).parent == Path(pg.__file__).parent == Path(sys.argv[2])
import pytest
class Results:
    def __init__(self): self.counts = dict(passed=0, failed=0, collected=0)
    def pytest_collection_finish(self, session): self.counts['collected'] = len(session.items)
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' and report.outcome in ('passed', 'failed'):
            self.counts[report.outcome] += 1
r = Results()
code = pytest.main([sys.argv[3], '-q', '-p', 'no:cacheprovider', '--basetemp', sys.argv[4]], plugins=[r])
Path(sys.argv[5]).write_text(json.dumps(dict(exitcode=int(code), **r.counts)))
''', encoding='utf8')
    output = tmp_path / 'counts.json'
    env = dict(os.environ, PYTHONPATH=str(overlay.parent), PYTHONDONTWRITEBYTECODE='1',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    result = subprocess.run([sys.executable, str(launcher), str(ROOT / 'src/ls_prepost_mcp'),
                             str(overlay), str(test), str(tmp_path / 'cases'), str(output)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    counts = json.loads(output.read_text())
    assert counts == dict(exitcode=1, collected=45,
                         failed=recorded['baseline_new_tests_failed'],
                         passed=recorded['baseline_new_tests_passed'])
    report = (EVIDENCE.parent / 'report.md').read_text(encoding='utf8')
    assert f"{counts['failed']} failed / {counts['passed']} passed" in report


def test_p1_88b_historical_disk_bytes_are_reconstructible_from_committed_blobs():
    require_history()
    data = evidence()
    for run in data['native']:
        assert run['certifies_current_head'] is False
        assert run['evidence_status'] == 'historical_only'
        for name, raw_hash in run['source_files'].items():
            identity = data['native_source_provenance'][name]
            source = blob(identity['git_blob_id'])
            assert blob(identity['git_revision'] + ':' + name) == source
            assert b'\r' not in source
            assert hashlib.sha256(source).hexdigest() == identity['sha256_lf']
            lines = source.splitlines(keepends=True)
            assert len(lines) == identity['line_count']
            lf_only = set(identity['lf_only_lines'])
            assert all(1 <= number <= len(lines) for number in lf_only)
            raw = b''.join(line if number in lf_only else line.replace(b'\n', b'\r\n')
                           for number, line in enumerate(lines, 1))
            assert hashlib.sha256(raw).hexdigest() == identity['raw_sha256'] == raw_hash
            assert raw.replace(b'\r\n', b'\n') == source


@pytest.mark.parametrize('path', ['../outside.k', 'C:/outside.k', '//example.invalid/share/out.k'])
def test_p2_88c_ordinary_output_paths_are_reviewed_source_not_sandboxed(tmp_path, path):
    prepared = Service(Settings(tmp_path)).prepare_native_program('macro',
        code='*macro begin export\nsave keyword &file\n*macro end', parameters={'file': path})
    assert prepared['data']['rendered_source'].endswith(f'save keyword "{path}"\n')
    assert 'no security sandbox' in prepared['execution_scope']
    # Preparation must not open the output, including the synthetic UNC path.
    assert sorted(p.name for p in tmp_path.iterdir()) == ['jobs']


@pytest.mark.parametrize('body', ['title "unterminated', 'parameter n 1\ntitle "&n'])
def test_p2_88d_unbalanced_quotes_are_an_explicit_preparation_error(body):
    with pytest.raises(ValueError, match='Unbalanced native argument quotes'):
        compile_macro('*macro begin title\n' + body + '\n*macro end', {})


@pytest.mark.parametrize('value', ['中文 result', 'x' * 4096, '$value', '#value'])
def test_p2_88e_compile_only_string_boundaries(value):
    commands, _, _ = compile_macro('*macro begin test\ntitle &text\n*macro end', {'text': value})
    assert commands.endswith(f'title "{value}"\n')


@pytest.mark.parametrize('value', ['x\u2029y', 'x\u200by', 'x\u202ey', 'x\ufeffy', 'x\ud800y'])
def test_p2_88e_unicode_separators_controls_and_surrogates_fail_before_job_creation(tmp_path, value):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).prepare_native_program('macro',
            code='*macro begin test\ntitle &text\n*macro end', parameters={'text': value})
    assert not (tmp_path / 'jobs').exists()


def test_p2_88f_bound_macro_retains_references_without_native_equivalence_claim():
    commands, native, meta = compile_macro('*macro begin test\nsave keyword &file\n*macro end',
                                           {'file': 'space name.k'})
    assert 'save keyword "space name.k"' in commands
    assert 'save keyword &file' in native
    assert 'save keyword "space name.k"' not in native
    assert 'no native Macro/Exec' in meta['scope']
