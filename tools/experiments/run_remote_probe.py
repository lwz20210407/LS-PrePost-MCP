"""I10/E5 UU remote-disconnect probe; operator starts disconnection window."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2])
p.add_argument('--executable-413', type=Path, required=True)
p.add_argument('--executable-410', type=Path, required=True)
p.add_argument('--engine-repository', type=Path, help='Optional I01 checkout with tests/test_engine_native.py')
p.add_argument('--operator-ready', action='store_true', required=True,
               help='Operator agreed to disconnect UU during this run; reconnect confirmation remains required')
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--delay', type=int, default=30)
p.add_argument('--remaining-matrix', action='store_true', help='Run the 13 runc/macro cells omitted by the default-route probe')
a = p.parse_args()
sys.path.insert(0, str(a.repository / 'tools' / 'experiments'))
sys.path.insert(0, str(a.repository / 'src'))
from prepare import prepare  # noqa: E402
from run_matrix import client_protocol_type, desktop_state, run  # noqa: E402

root = a.output.resolve()
root.mkdir(exist_ok=False)
prepare(root / 'matrix', a.fixture / 'd3plot')
report = dict(task_id='I10/E5', environment='UU remote',
              condition_evidence='operator confirms disconnect/reconnect interval; WTS is recorded separately',
              armed_at=time.time(), protocol=client_protocol_type(), lanes=[])
(root / 'uu-result.json').write_text(json.dumps(report, indent=2), encoding='utf8')
print('ARMED: delay before disconnected probes:', a.delay, flush=True)
time.sleep(a.delay)
report['started_at'] = time.time()
ordinary = ('command', 'cfile', 'scl', 'python')
lanes = [
    ('4.13', str(a.executable_413), 'nographics', ordinary),
    ('4.10', str(a.executable_410), 'nographics', ordinary),
    ('4.13', str(a.executable_413), 'session', ordinary),
]
if a.remaining_matrix:
    lanes = [
        ('4.13', str(a.executable_413), 'runc', ordinary + ('macro',)),
        ('4.10', str(a.executable_410), 'runc', ordinary + ('macro',)),
        ('4.13', str(a.executable_413), 'nographics', ('macro',)),
        ('4.10', str(a.executable_410), 'nographics', ('macro',)),
        ('4.13', str(a.executable_413), 'session', ('macro',)),
    ]
for version, executable, mode, languages in lanes:
    for language in languages:
        args = argparse.Namespace(directory=root/'matrix', executable=Path(executable), version=version,
                                  desktop='unlocked', mode=mode, language=language)
        before = time.time()
        try:
            run(args)
            report['lanes'].append(dict(version=version, mode=mode, language=language, started_at=before, finished_at=time.time()))
        except Exception as exc:
            report['lanes'].append(dict(version=version, mode=mode, language=language, error=str(exc), started_at=before, finished_at=time.time()))
        (root/'uu-result.json').write_text(json.dumps(report, indent=2), encoding='utf8')
if a.engine_repository is not None:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(a.engine_repository/'src')+os.pathsep+str(a.engine_repository),
               LSPP_ENGINE_EXECUTABLE=str(a.executable_413), LSPP_ENGINE_FIXTURE=str(a.fixture))
    with (root/'engine-native.log').open('w', encoding='utf8') as stream:
        test = subprocess.run([sys.executable,'-B','-m','pytest','tests/test_engine_native.py','-q',
                               '--basetemp='+str(root/'engine-native'), '-o','cache_dir='+str(root/'pytest-cache')],
                              cwd=a.engine_repository, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
    report['engine_test_exit'] = test.returncode
report.update(finished_at=time.time(), desktop_after=desktop_state(), operator_reconnection_confirmed=False)
(root/'uu-result.json').write_text(json.dumps(report, indent=2), encoding='utf8')
print('COMPLETE; waiting for operator confirmation that UU remained disconnected during tests',flush=True)
