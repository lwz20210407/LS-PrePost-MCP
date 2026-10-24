import hashlib
import json
import subprocess
from pathlib import Path

import pytest


def test_sae_fix_preserves_strict_native_comparisons_and_revision(pytestconfig):
    root=Path(pytestconfig.rootpath)
    folder=root/'docs/decisions/evidence/q07-sae-fix'
    evidence=json.loads((folder/'evidence.json').read_text(encoding='utf8'))
    assert sum(r['passed'] for r in evidence['runs']) == 8
    for run in evidence['runs']:
        assert not run['working_tree_dirty']
        assert run['git_diff_sha256'] == hashlib.sha256(b'').hexdigest()
        assert hashlib.sha256((folder/run['report']).read_text(encoding='utf8').encode()).hexdigest() == run['report_sha256']
        for c in run['cases']:
            v=c['comparisons']['lsprepost']
            assert v['agrees'] and v['rtol'] == 2e-5
            assert v['atol'] < .000021
            assert c['verdict'] == 'agrees' and c['samples'] == 4001
    p=subprocess.run(['git','rev-parse','--is-shallow-repository'],cwd=root,capture_output=True,text=True)
    if p.returncode or p.stdout.strip() == 'true':
        pytest.skip('Historical product blobs require complete Git checkout')
    for run in evidence['runs']:
        for s in run['source_identity']:
            assert subprocess.check_output(['git','rev-parse',run['actual_git_revision']+':'+s['path']],cwd=root,text=True).strip() == s['git_blob_id']
