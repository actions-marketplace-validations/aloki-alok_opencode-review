import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from helpers import ROOT, src  # noqa: F401
from budget import Budget
from runner import Pass, run_pass

FAKE = str(ROOT / 'tests' / 'fake_opencode.py')
KEY = 'sk-or-v1-secretsecretsecret'
FINDINGS = '{"findings": [{"file": "a.py", "line": 1, "title": "t"}]}'


def text(t):
    return {'type': 'text', 'part': {'type': 'text', 'text': t}}


STEP = {'type': 'step_finish'}


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name).resolve()
        self.code = self.dir / 'code'
        self.code.mkdir()
        self.calls = self.dir / 'calls.jsonl'
        os.environ['OPENCODE_FAKE_CALLS'] = str(self.calls)
        os.environ['GITHUB_TOKEN'] = 'ghs_should_not_leak'

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, **plan):
        p = self.dir / f'plan-{len(list(self.dir.glob("plan-*")))}.json'
        p.write_text(json.dumps(plan))
        os.environ['OPENCODE_FAKE_PLAN'] = str(p)

    def run_it(self, budget=Budget(5, 2), key='findings', work=None):
        return run_pass(Pass(opencode=FAKE, cwd=str(self.code), work=str(work or self.dir / 'work'),
                             model='openrouter/some/model', api_key=KEY, agent='review', prompt='go',
                             budget=budget, json_key=key, wrap_seconds=3))

    def calls_made(self):
        return [json.loads(ln) for ln in self.calls.read_text().splitlines()]

    def test_finished_run(self):
        self.plan(run=[[0, STEP], [0, text(FINDINGS)]])
        r = self.run_it()
        self.assertEqual((r.status, r.turns), ('done', 1))
        self.assertEqual(r.result['findings'][0]['file'], 'a.py')
        self.assertEqual(len(self.calls_made()), 1)

    def test_killed_mid_stream_is_resumed_for_the_json(self):
        self.plan(run=[[0, STEP], [0, text('reading')], [30, text(FINDINGS)]],
                  resume=[[0, text('Out of time. ' + FINDINGS)]])
        t = time.monotonic()
        r = self.run_it(Budget(5, 1))
        self.assertLess(time.monotonic() - t, 1 + 3 + 2)
        self.assertEqual(r.status, 'timeout')
        self.assertEqual(r.result['findings'][0]['title'], 't')
        resume = self.calls_made()[1]['argv']
        self.assertIn('--session', resume)
        self.assertEqual(resume[resume.index('--session') + 1], 'ses_review')
        self.assertEqual(resume[resume.index('--agent') + 1], 'wrap')

    def test_killed_and_resume_also_fails_gives_none(self):
        self.plan(run=[[0, STEP], [30, text(FINDINGS)]], resume=[[30, text(FINDINGS)]])
        r = self.run_it(Budget(5, 1))
        self.assertEqual(r.status, 'timeout')
        self.assertIsNone(r.result)

    def test_process_that_ignores_sigint_is_killed(self):
        self.plan(run=[[0, STEP], [60, text(FINDINGS)]], resume=[[60, text(FINDINGS)]], ignore_int=True)
        t = time.monotonic()
        r = self.run_it(Budget(5, 1))
        self.assertLess(time.monotonic() - t, 1 + 3 + 2 * 5 + 2)
        self.assertIsNone(r.result)

    def test_finished_without_json_is_asked_for_it(self):
        # The step cap makes OpenCode stop with a text summary and no JSON.
        self.plan(run=[[0, STEP], [0, text('I looked at a.py and found an issue.')]],
                  resume=[[0, text(FINDINGS)]])
        r = self.run_it()
        self.assertEqual(r.status, 'done')
        self.assertEqual(len(r.result['findings']), 1)

    def test_error_with_no_session_fails(self):
        self.plan(run=[[0, {'type': 'error', 'error': {'name': 'APIError', 'data': {'message': 'User not found'}}}]],
                  exit=1)
        r = self.run_it()
        self.assertEqual(r.status, 'failed')
        self.assertIsNone(r.result)
        self.assertIn('User not found', r.error)

    def test_ask_mode_takes_the_last_text(self):
        self.plan(run=[[0, text('thinking')], [0, STEP], [0, text('It is in a.py:3.')]])
        r = self.run_it(key=None)
        self.assertEqual((r.status, r.answer), ('done', 'It is in a.py:3.'))

    def test_state_is_isolated_and_secrets_stay_out_of_the_env(self):
        self.plan(run=[[0, text(FINDINGS)]])
        self.run_it()
        call = self.calls_made()[0]
        env, argv = call['env'], call['argv']
        work = str(self.dir / 'work')
        for var in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME'):
            self.assertTrue(env[var].startswith(work), var)
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertEqual(env['OPENCODE_DISABLE_CLAUDE_CODE'], '1')
        self.assertEqual(call['cwd'], str(self.code))
        self.assertNotIn(KEY, ' '.join(argv))
        self.assertNotIn(KEY, env['OPENCODE_CONFIG_CONTENT'])
        cfg = json.loads(env['OPENCODE_CONFIG_CONTENT'])
        for tool in ('edit', 'bash', 'webfetch', 'websearch', 'task', 'external_directory', 'skill'):
            self.assertEqual(cfg['permission'][tool], 'deny', tool)
        self.assertEqual(cfg['permission']['*'], 'deny')
        self.assertEqual(cfg['agent']['review']['steps'], 5)
        self.assertEqual(cfg['provider']['openrouter']['options']['apiKey'], '{env:OPENCODE_REVIEW_API_KEY}')
        self.assertEqual(env['OPENCODE_REVIEW_API_KEY'], KEY)

    def test_two_jobs_at_once_keep_their_own_state(self):
        self.plan(run=[[0.5, STEP], [0, text(FINDINGS)]])
        results = {}

        def job(name):
            results[name] = self.run_it(work=self.dir / name)

        threads = [threading.Thread(target=job, args=(n,)) for n in ('job1', 'job2')]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual({r.status for r in results.values()}, {'done'})
        for name in ('job1', 'job2'):
            runs = list((self.dir / name).rglob('runs.log'))
            self.assertEqual(len(runs), 1, name)
            self.assertEqual(len(runs[0].read_text().split()), 1, name)


if __name__ == '__main__':
    unittest.main()
