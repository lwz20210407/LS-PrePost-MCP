from pathlib import Path

import pytest

pytest.importorskip('ansys.dyna.core')

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.keyword_tools import equal
from ls_prepost_mcp.service import Service


def specifications():
    return [
        {'class_name':'Mat003','fields':{'mid':1,'ro':1.0,'e':100.0,'pr':.3,'sigy':1.0,'etan':.1}},
        {'class_name':'SectionShell','fields':{'secid':1,'elform':16,'t1':1.0,'t2':1.0,'t3':1.0,'t4':1.0}},
        {'class_name':'Part','fields':{'parts':[{'pid':10,'mid':1,'secid':1,'heading':'synthetic'}]}},
        {'class_name':'Node','fields':{'nodes':[{'nid':7,'x':1.0,'y':2.0,'z':3.0},{'nid':9,'x':4.0,'y':5.0,'z':6.0}]}},
        {'class_name':'SetNodeList','fields':{'sid':8,'nodes':[7,9]}},
        {'class_name':'DefineCurve','fields':{'lcid':4,'curves':[{'a1':0.0,'o1':0.0},{'a1':1.0,'o1':2.0}]}},
        {'class_name':'BoundarySpcSet','fields':{'nsid':8,'dofx':1}},
        {'class_name':'ControlTermination','fields':{'endtim':1.0}},
    ]


def test_schema_uses_real_properties_and_rejects_upstream_example_typo(tmp_path):
    s = Service(Settings(tmp_path))
    schema = s.describe_pydyna_keyword('SectionShell')
    assert 'elform' in {f['name'] for f in schema['fields']}
    r = s.compose_keyword_deck([{'class_name':'SectionShell','fields':{'secid':1,'elfrom':16}}],'test')
    assert r['status']=='failed' and 'elfrom' in r['error']['message']
    r = s.compose_keyword_deck([{'class_name':'Include','fields':{'filename':'outside.k'}}],'test')
    assert r['status']=='failed'


def test_generic_scalar_table_series_roundtrip_and_edit(tmp_path):
    s = Service(Settings(tmp_path))
    r = s.compose_keyword_deck(specifications(),'synthetic-consistent')
    assert r['status']=='succeeded', r
    p = Path(r['artifacts'][0]['path'])
    before = p.read_bytes()
    edited = s.update_keyword_fields(str(p),'Mat003',{'mid':1},{'sigy':2.5},'synthetic-consistent')
    assert edited['status']=='succeeded', edited
    table = s.update_keyword_table_row(str(p),'Node','nodes',{'nid':9},{'x':8.0},'synthetic-consistent')
    assert table['status']=='succeeded', table
    assert p.read_bytes()==before
    bad = s.update_keyword_table_row(str(p),'Node','nodes',{'nid':500},{'x':8.0},'test')
    assert bad['status']=='failed'


def test_unknown_columns_and_keyword_injection_rejected(tmp_path):
    s = Service(Settings(tmp_path))
    for fields in ({'parts':[{'pid':1,'invented_column':2}]},{'parts':[{'heading':'title\n*INCLUDE\nsecret.k','pid':1}]}):
        r=s.compose_keyword_deck([{'class_name':'Part','fields':fields}],'test')
        assert r['status']=='failed'
    r=s.compose_keyword_deck([{'class_name':'Mat003','fields':{'deck':'wrong'}}],'test')
    assert r['status']=='failed'


def test_integer_identity_never_uses_float_tolerance():
    assert not equal(1000000,1000001)
    assert equal(1000000,1000000)
