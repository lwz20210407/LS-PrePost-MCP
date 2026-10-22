"""A05 bounded string arguments; these are compiler tests, not Macro/Exec evidence."""

from pathlib import Path

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.native_macros import compile_macro
from ls_prepost_mcp.service import Service


def macro(body):
    return '*macro begin strings\n' + body + '\n*macro end\n'


def test_string_defaults_and_overrides_preserve_literal_text_and_numeric_types():
    source = macro('parameter name "output file"\nparameter scale -1.5e2\n'
                   'save keyword &name\ncustom &scale "prefix &{name}.k"')
    commands, native, metadata = compile_macro(source, {'name': '中文 result'})
    assert commands == ('parameter name "中文 result"\nparameter scale -150.0\n'
                        'save keyword "中文 result"\ncustom -150.0 "prefix 中文 result.k"\n')
    assert metadata['parameters'] == {'name': '中文 result', 'scale': -150.0}
    assert 'save keyword &name' in native
    assert compile_macro(native, {})[0] == commands
    assert '"output file"' in compile_macro(source, {})[0]


@pytest.mark.parametrize('value', ['', '123', "author's result", 'path/file.k'])
def test_strings_are_quoted_once_in_both_reference_contexts(value):
    commands, _, _ = compile_macro(macro('custom &text "&{text}"'), {'text': value})
    assert commands.endswith('custom "' + value + '" "' + value + '"\n')


@pytest.mark.parametrize('value', ['x\nexit', 'x\rquit', 'x\tquit', 'x\x00', 'x\x7f',
                                  'x\u2028quit', 'x\u0085quit', '"\nexit', 'x;exit',
                                  '&other', '&{other}', 'x"y', 'x\\', '{{other}}'])
def test_string_injection_is_rejected_before_job_creation(tmp_path, value):
    with pytest.raises(ValueError):
        Service(Settings(tmp_path)).prepare_native_program('macro', code=macro('custom &text'),
                                                          parameters={'text': value})
    assert not (tmp_path / 'jobs').exists()


@pytest.mark.parametrize('body', ['&text', '"&text" arg', 'custom prefix&text',
                                 'custom &{text}.k', 'custom "&text',
                                 'custom "prefix\\&text"'])
def test_string_references_cannot_change_command_or_ambiguous_token_boundaries(body):
    with pytest.raises(ValueError, match='^line 2:'):
        compile_macro(macro(body), {'text': 'exit'})


@pytest.mark.parametrize('default', ['foo', '1+2', '"foo" + "bar"', '"&other"', '"x\\"'])
def test_nonliteral_or_unsafe_defaults_report_original_multiblock_line(default):
    source = '*macro begin first\nfront\n*macro end\n' + macro('parameter text ' + default + '\ncustom &text')
    with pytest.raises(ValueError, match='^line 5:'):
        compile_macro(source, {}, 'strings')


@pytest.mark.parametrize('value', ['2', True, float('inf'), float('nan'), [], {}, None, 10**400])
def test_picks_remain_finite_positive_integer_user_ids(value):
    with pytest.raises(ValueError):
        compile_macro(macro('ident node &node(n)'), {'node': value})


@pytest.mark.parametrize('params', [[], {'bad-name': 1}, {1: 'bad'}, {'text': 'x' * 4097}])
def test_parameter_shape_is_bounded(params):
    with pytest.raises(ValueError):
        compile_macro(macro('custom &text'), params)


def test_string_script_dependency_is_captured_and_tamper_detected(tmp_path):
    helper = tmp_path / 'original.cfile'
    helper.write_text('top\n')
    service = Service(Settings(tmp_path))
    source = macro('openc command &file nodialog')
    with pytest.raises(ValueError, match='not declared'):
        service.prepare_native_program('macro', code=source, parameters={'file': 'lib/child file.cfile'})
    prepared = service.prepare_native_program('macro', code=source,
        parameters={'file': 'lib/child file.cfile'},
        dependencies=[{'path': str(helper), 'name': 'lib/child file.cfile'}])
    assert prepared['data']['script_references']['program.cfile'] == ['lib/child file.cfile']
    directory = Path(prepared['job_directory'])
    assert (directory / 'source.mac').read_text() == source
    (directory / 'lib/child file.cfile').write_text('front\n')
    with pytest.raises(ValueError, match='Dependency changed'):
        service.execute_native_program(prepared['job_id'], prepared['data']['sha256'])


def test_other_languages_keep_numeric_template_contract(tmp_path):
    with pytest.raises(ValueError, match='finite named numbers'):
        Service(Settings(tmp_path)).prepare_native_program('cfile', code='custom {{text}}',
                                                          parameters={'text': 'hello'})


def test_prepared_string_change_invalidates_execution_identity(tmp_path):
    service = Service(Settings(tmp_path))
    prepared = service.prepare_native_program('macro', code=macro('save keyword &file'),
                                              parameters={'file': 'approved.k'})
    directory = Path(prepared['job_directory'])
    program = directory / 'program.cfile'
    program.write_text(program.read_text().replace('approved.k', 'other.k'))
    with pytest.raises(ValueError, match='Source changed'):
        service.execute_native_program(prepared['job_id'], prepared['data']['sha256'])
