import pytest

from ls_prepost_mcp.core.script_parameters import cfile_diagnostics, render_cfile


def test_cfile_parameters_preserve_source_lines_and_windows_paths():
    source = 'meshing boxsolid create 0 0 0 {{width}} 3 4 1 1 1 0\nsave keyword "{{file}}"\n'
    result = render_cfile(source, dict(width=5, file=r"C:\job folder\mesh.k"))
    assert result.splitlines() == ['meshing boxsolid create 0 0 0 5 3 4 1 1 1 0', 'save keyword "C:\\job folder\\mesh.k"']


@pytest.mark.parametrize("value", ['x"\nexit', 'x;exit', 'x\rquit', '\x00', True, float("nan"), "{{other}}"])
def test_cfile_rejects_parameter_command_injection(value):
    with pytest.raises(ValueError):
        render_cfile('save keyword "{{file}}"', dict(file=value))


def test_cfile_string_must_be_quoted_and_parameters_must_match():
    with pytest.raises(ValueError):
        render_cfile('save keyword {{file}}', dict(file="name.k"))
    with pytest.raises(ValueError):
        render_cfile('top', dict(extra=1))
    for source in ('save keyword prefix"{{file}}"', 'save keyword "{{file}}"suffix'):
        with pytest.raises(ValueError):
            render_cfile(source, dict(file="name.k"))


def test_cfile_error_lines_follow_repeated_commands_and_keep_native_text():
    source = 'top\ninvalid_test\ntop\ninvalid_test\n'
    log = 'openc command job.cfile\ntop\ninvalid_test\nInvalid command invalid_test!\ntop\ninvalid_test\nInvalid command invalid_test!\n'
    assert cfile_diagnostics(source, log) == [dict(line=2, message="Invalid command invalid_test!"),
                                            dict(line=4, message="Invalid command invalid_test!")]
    assert cfile_diagnostics(source, 'Invalid command unknown!') == [dict(line=None, message="Invalid command unknown!")]
