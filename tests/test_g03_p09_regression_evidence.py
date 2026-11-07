"""Portable identity checks for G03/P09 host captures and immutable prior contexts."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'docs/decisions/evidence/g03-p09-regressions'
INDEX=ROOT/'docs/decisions/evidence/contact-geometry-refresh/context.json'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def strings(value):
    if isinstance(value,dict):
        for key,item in value.items():
            yield key
            yield from strings(item)
    elif isinstance(value,list):
        for item in value:
            yield from strings(item)
    elif isinstance(value,str):
        yield value


def test_g03_p09_host_capture_binds_exact_current_sources_without_done_upgrade():
    data=read(FOLDER/'evidence.json')
    assert data['status']=='partial' and data['verification_level']=='L1' and data['native_executed'] is False
    assert data['working_tree_dirty'] is False and data['source_before_after_equal'] is True
    assert data['focused']['passed']==110 and data['focused']['skipped']==0
    assert data['sdk_absence']['passed']==11 and data['sdk_absence']['skipped']==45
    assert data['sdk_absence']['complete_minimal_environment'] is False
    assert data['sdk_absence']['observation']['loaded_ansys_dyna_core_modules']==[]
    identities=data['product_and_test_source_identity']
    assert len(identities)==len({row['path'] for row in identities})==6
    paths=[row['path'] for row in identities]
    current=subprocess.check_output(['git','hash-object','--',*paths],cwd=ROOT,text=True,timeout=30).splitlines()
    recorded=subprocess.check_output(['git','ls-tree','-r',data['actual_git_revision'],'--',*paths],cwd=ROOT,text=True,timeout=30).splitlines()
    blobs={row.split('\t',1)[1]:row.split('\t',1)[0].split()[2] for row in recorded}
    for item,blob in zip(identities,current,strict=True):
        assert blob==blobs[item['path']]==item['git_blob_id']
        assert hashlib.sha256((ROOT/item['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==item['sha256_lf']


def test_g03_p09_refresh_preserves_the_previous_seven_roles_and_mesh_archive():
    index=read(INDEX)
    previous=index['previous_current_before_G03_P09']
    assert len(previous)==7
    for task,row in previous.items():
        assert hashlib.sha256((ROOT/row['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==row['sha256_lf']
        assert row['path']!=index['current'][task]['path']
        assert row['actual_git_revision']!=index['current'][task]['actual_git_revision']
    mesh=index['previous_mesh_readback_before_G03_P09']
    assert mesh['path']!=index['current_mesh_readback']['path']
    for name,key in (('evidence.json','evidence_sha256_lf'),('report.md','report_sha256_lf')):
        assert hashlib.sha256((ROOT/mesh['path']/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==mesh[key]


def test_g03_p09_report_keeps_original_failed_contexts_and_privacy():
    data=read(FOLDER/'evidence.json')
    assert data['g03_original_main']['failed']==1 and data['g03_original_main']['passed']==1
    assert data['g03_legacy']['failed']==3 and data['g03_legacy']['passed']==1
    assert data['p09_original_main']['failed']==4
    assert data['p09_original_main']['working_tree_dirty'] is True
    assert data['p09_original_main']['original_test_recovered_and_capture_hash_verified'] is True
    assert data['p09_original_main']['new_red_execution_claimed'] is False
    assert data['p09_original_main']['missing_endpoint_public_ok_was_already_false_due_to_dangling_reference'] is True
    assert data['g03_legacy']['actual_git_revision']!=data['g03_original_main']['actual_git_revision']
    assert all(row['identical'] for row in data['legacy_quality_byte_equality']['checks'])
    assert hashlib.sha256((FOLDER/data['report']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==data['report_sha256_lf']
    assert (FOLDER/'evidence.json').stat().st_size<512*1024
    assert all(re.search(r'[A-Za-z]:[\\/]|\\\\[^\\]+\\',value) is None for value in strings(data))
