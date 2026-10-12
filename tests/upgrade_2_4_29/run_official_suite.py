"""Run immutable official 2.4.29 tests against an already-running isolated stack.
Only lifecycle is replaced: official Iris.start writes .env and targets primary
compose, so it is forbidden here. No official test bodies are edited.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
import unittest
from urllib.parse import urlparse

p = argparse.ArgumentParser()
p.add_argument('--url', required=True)
p.add_argument('--tests', type=Path, default=Path('D:/Diplom/iris-upstream-2.4.29/tests'))
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
u = urlparse(a.url)
if u.hostname not in {'localhost', '127.0.0.1'} or u.port not in {18082, 18083}:
    p.error('Only newly isolated acceptance ports 18082 and 18083 are allowed')
sys.path.insert(0, str(a.tests.resolve()))
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
import iris
iris.API_URL = a.url.rstrip('/')
class ForbiddenLifecycle:
    def __getattr__(self, name):
        raise RuntimeError('Official Docker lifecycle forbidden in isolated runner: ' + name)
def isolated_init(self):
    self._docker_compose = ForbiddenLifecycle()
    self._api = iris.RestApi(iris.API_URL, iris._API_KEY)
iris.Iris.__init__ = isolated_init
iris.Iris.start = lambda self: self._wait_until_api_is_ready()
iris.Iris.stop = lambda self: None
suite = unittest.defaultTestLoader.discover(str(a.tests), pattern='tests*.py')
a.output.parent.mkdir(parents=True, exist_ok=True)
with a.output.with_suffix('.log').open('w', encoding='utf-8') as log:
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        r = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
summary = {'url': a.url, 'official_tests': str(a.tests.resolve()), 'tests_run': r.testsRun,
           'failures': [{'test': str(t), 'traceback': v} for t,v in r.failures],
           'errors': [{'test': str(t), 'traceback': v} for t,v in r.errors],
           'skipped': [{'test': str(t), 'reason': v} for t,v in r.skipped]}
a.output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
print(f'{r.testsRun} tests: {len(r.failures)} failures, {len(r.errors)} errors, {len(r.skipped)} skipped')
sys.exit(not r.wasSuccessful())
