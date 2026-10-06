from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.core.contracts import JobResult
from ls_prepost_mcp.native_macros import compile_macro
from ls_prepost_mcp.service import Service

SOURCE = '''$ test authored for this project
*macro begin select node
parameter N1 1
genselect clear
genselect target node
genselect node add node &N1(n)
*macro end
'''


def test_native_macro_prepare_reuses_cfile_contract_and_retains_native_forms(tmp_path):
    service = Service(Settings(tmp_path))
    original = tmp_path/'original.mac'
    original.write_text(SOURCE, encoding='utf8')
    before = original.read_bytes()
    prepared = service.prepare_native_program('macro', path=str(original), parameters={'N1': 102}, expected_counts={'nodes': 4})
    assert prepared['status'] == 'prepared'
    assert prepared['data']['language'] == 'cfile'
    assert prepared['data']['native_macro']['pick_domains'] == {'N1': 'node'}
    job = Path(prepared['job_directory'])
    assert (job/'program.cfile').read_text().endswith('genselect node add node 102\n')
    assert 'parameter N1 102' in (job/'bound.mac').read_text()
    assert '&N1(n)' in (job/'bound.mac').read_text()
    assert (job/'source.mac').read_text() == SOURCE
    assert original.read_bytes() == before
    # The unchanged execution route verifies the compiled program identity.
    (job/'program.cfile').write_text('front\n')
    with pytest.raises(ValueError, match='changed'):
        service.execute_native_program(prepared['job_id'], prepared['data']['sha256'])


def test_multiple_blocks_require_explicit_selection_and_isolate_defaults():
    source = SOURCE + '*macro begin second\nparameter N1 9\nident node &N1\n*macro end\n'
    with pytest.raises(ValueError, match='Multiple'):
        compile_macro(source, {})
    commands, _, meta = compile_macro(source, {}, 'second')
    assert commands == 'parameter N1 9\nident node 9\n' and meta['parameters'] == {'N1': 9}
    with pytest.raises(ValueError, match='Unknown native macro_name'):
        compile_macro(source, {}, 'absent')


def test_longest_name_braces_numeric_notation_and_comments():
    source = '*macro begin test\nparameter N1 1\nparameter N10 1e2\nparameter R -0.5\n$ &ignored\ncustom &N10 &N1 &{N1}-R &R\n*macro end'
    commands, _, _ = compile_macro(source, {})
    assert commands.endswith('$ &ignored\ncustom 100.0 1 1-R -0.5\n')


@pytest.mark.parametrize('value', [0, -1, 1.0, True, float('nan'), '2\nexit'])
def test_pick_parameters_cannot_be_non_ids_or_commands(value):
    with pytest.raises(ValueError):
        compile_macro(SOURCE, {'N1': value})


@pytest.mark.parametrize('body', [
    'genselect node add node &missing(n)',
    'parameter N1 1+2\nident node &N1',
    'parameter N1 1\nparameter N1 2\nident node &N1',
    'front\nparameter N1 2\nident node &N1',
    'interactive',
    'front; interactive',
    'ident node &N1(x)',
    'ident node &{broken',
    'ident node {{N1}}',
    'ident node &N1(n)\nident element &N1(e)',
])
def test_unresolved_or_unsupported_macro_semantics_fail_preparation(body):
    with pytest.raises(ValueError):
        compile_macro('*macro begin a\n' + body + '\n*macro end', {})


@pytest.mark.parametrize('source', [
    '*macro begin a\nfront',
    '*macro end',
    'front\n*macro begin a\ntop\n*macro end',
    '*macro begin a\n*macro begin b\ntop\n*macro end',
    '*macro begin a\nfront\n*macro end\n*macro begin a\nfront\n*macro end',
])
def test_malformed_blocks_do_not_silently_execute_partial_content(source):
    with pytest.raises(ValueError):
        compile_macro(source, {})


def test_unknown_parameters_and_non_macro_selector_rejected(tmp_path):
    with pytest.raises(ValueError, match='Unknown native macro parameters'):
        compile_macro(SOURCE, {'typo': 2})
    with pytest.raises(ValueError, match='macro_name only'):
        Service(Settings(tmp_path)).prepare_native_program('cfile', code='front', macro_name='a')


@pytest.mark.parametrize('body,line', [
    ('interactive', 8),
    ('parameter N1 1+2\nident node &N1', 8),
    ('parameter N1 1\nparameter N1 2\nident node &N1', 9),
    ('ident node &missing(n)', 8),
    ('front; interactive', 8),
    ('ident node &N1(x)', 8),
    ('ident node &{broken', 8),
])
def test_macro_syntax_errors_refer_to_original_multiblock_lines(body, line):
    source = '*macro begin first\nfront\n*macro end\n\n$ comment\n*macro begin second\n$ retained comment\n' + body + '\n*macro end'
    with pytest.raises(ValueError, match='^line {}:'.format(line)):
        compile_macro(source, {}, 'second')


def test_prepared_native_macro_executes_through_existing_contract(tmp_path, monkeypatch):
    exe = tmp_path/'native.exe'
    exe.write_bytes(b'test identity')
    service = Service(Settings(tmp_path, exe))
    prepared = service.prepare_native_program('macro', code=SOURCE, expected_counts={'nodes': 4})

    def execute(executable, cfile, directory, **kwargs):
        assert (directory/'program.cfile').read_text().endswith('genselect node add node 1\n')
        (directory/'complete.txt').write_text('4 1 1')
        return JobResult(operation=kwargs["operation"], job_id=directory.name, status="unverified", data=dict(returncode=0, timed_out=False))

    monkeypatch.setattr('ls_prepost_mcp.programs.run_batch', execute)
    result = service.execute_native_program(prepared['job_id'], prepared['data']['sha256'])
    assert result['status'] == 'succeeded'
