"""Original A05 compiler regression; does not certify native Macro/Exec transport."""

import hashlib
import json
from pathlib import Path

import pytest

from tests.test_engine_native import native_case  # noqa: F401


@pytest.mark.native
def test_compiled_macro_string_and_numeric_arguments(native_case):  # noqa: F811
    service, fixture = native_case
    source = '''$ Original regression, not a course/tutorial sample
*macro begin unused
save keyword "wrong-block.k"
*macro end
*macro begin export
parameter file "default result.k"
parameter fallback "literal default.k"
parameter node 11
genselect clear
genselect target node
genselect node add node &node(n)
save keyword &file
save keyword "&{fallback}"
*macro end
'''
    source_file = service.settings.workspace / 'original.mac'
    source_file.write_text(source, encoding='utf8')
    prepared = service.prepare_native_program('macro', path=str(source_file), macro_name='export',
        parameters={'file': 'bound result.k', 'node': 79}, expected_counts={'nodes': 8},
        outputs=[{'name': name, 'kind': 'keyword'} for name in ('bound result.k', 'literal default.k')])
    result = service.execute_native_program(prepared['job_id'], prepared['data']['sha256'],
        model=str(fixture / 'input.k'), inspect_selection=True)
    directory = Path(result['job_directory'])
    (directory / 'a05-result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    assert result['status'] == 'succeeded', result
    assert source_file.read_text(encoding='utf8') == source
    assert not (directory / 'wrong-block.k').exists()
    # Independent readback checks actual keyword contents, not merely exit status.
    for name in ('bound result.k', 'literal default.k'):
        text = (directory / name).read_text()
        assert '*NODE' in text and '*ELEMENT_SHELL' in text
        assert '*END' in text
    selected = (directory / 'selection.txt').read_text().splitlines()
    assert selected == ['1', '79'], selected
    assert result['process']['configuration']['source_modified'] is False
    assert '-nographics' in result['process']['argv']
    assert prepared['data']['native_macro']['source_text_sha256'] == hashlib.sha256(source.encode()).hexdigest()
