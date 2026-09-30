from pathlib import Path

import pytest

pytest.importorskip('ansys.dyna.core')

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.deck_backend import material_values
from ls_prepost_mcp.model_deck import complete_tensile_plate, validate_references
from ls_prepost_mcp.service import Service


def mesh(path):
    path.write_text('*KEYWORD\n*NODE\n10,0,0,0\n20,2,0,0\n30,2,1,0\n40,0,1,0\n'
                    '*ELEMENT_SHELL\n100,1,10,20,30,40\n*END\n')


def test_complete_plate_controls_and_links(tmp_path):
    from ansys.dyna.core import Deck
    from ansys.dyna.core import keywords as kw
    source, output = tmp_path/'mesh.k', tmp_path/'analysis.k'
    mesh(source)
    result = complete_tensile_plate(source, output, .1, material_values(1,100,.3),.2,10,.1)
    assert result['references']['valid_within_scope']
    deck = Deck()
    deck.import_file(str(output))
    curve = next(c for c in deck.keywords if isinstance(c,kw.DefineCurve))
    assert curve.curves.iloc[-1]['a1'] == 10
    assert curve.curves.iloc[-1]['o1'] == pytest.approx(.2)
    motion = next(c for c in deck.keywords if isinstance(c,kw.BoundaryPrescribedMotionSet))
    assert motion.vad == 2 and motion.nsid == 2 and motion.lcid == curve.lcid
    assert not result['quasistatic_validated']


def test_box_set_preserves_input_and_uses_user_ids(tmp_path):
    source = tmp_path/'mesh.k'
    mesh(source)
    before = source.read_bytes()
    s = Service(Settings(tmp_path))
    r = s.create_node_set_by_box(str(source),55,[0,0,-1,0,1,1],'mm')
    assert r['status'] == 'succeeded', r
    assert r['data']['node_id_sample'] == [10,40]
    assert source.read_bytes() == before
    duplicate = s.create_node_set_by_box(r['artifacts'][0]['path'],55,[0,0,-1,2,1,1],'mm')
    assert duplicate['status'] == 'failed'
    assert Path(r['artifacts'][0]['path']).exists()


def test_reference_errors_and_includes_fail_closed(tmp_path):
    source = tmp_path/'mesh.k'
    mesh(source)
    r = validate_references(source)
    assert not r['valid_within_scope']
    assert any(e['target']=='part' for e in r['errors'])
    source.write_text('*KEYWORD\n*INCLUDE\nother.k\n*END\n')
    with pytest.raises(ValueError,match='standalone'):
        validate_references(source)
