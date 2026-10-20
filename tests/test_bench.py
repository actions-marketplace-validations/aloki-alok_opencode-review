from helpers import ROOT, src  # noqa: F401  (puts src/ on the path)

# isort: split

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(ROOT / 'bench'))

from compare import compare  # noqa: E402
from mine import mine  # noqa: E402
from score import score  # noqa: E402


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True, text=True).stdout.strip()


class MineTest(unittest.TestCase):
    """A history with one bug-introducing PR and the PR that fixes it, merged the GitHub way."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = r = self.tmp.name
        git(r, 'init', '-q', '-b', 'main')
        git(r, 'config', 'user.email', 't@t')
        git(r, 'config', 'user.name', 't')
        self.write('app/calc.py', ''.join(f'x{i} = {i}\n' for i in range(30)) + 'def add(a, b):\n    return a + b\n')
        git(r, 'add', '-A')
        git(r, 'commit', '-qm', 'init')
        self.merge_pr(11, 'feature/speed', 'Make add faster', 'app/calc.py',
                      ''.join(f'x{i} = {i}\n' for i in range(30)) + 'def add(a, b):\n    return a - b\n')
        self.merge_pr(12, 'feature/docs', 'Add docs', 'README.md', 'docs\n')
        self.merge_pr(13, 'fix/add-sign', 'Fix add sign', 'app/calc.py',
                      ''.join(f'x{i} = {i}\n' for i in range(30)) + 'def add(a, b):\n    return a + b\n')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        p = Path(self.repo, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def merge_pr(self, number, branch, title, path, text):
        git(self.repo, 'checkout', '-qb', branch)
        self.write(path, text)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', title)
        git(self.repo, 'checkout', '-q', 'main')
        git(self.repo, 'merge', '-q', '--no-ff', branch, '-m',
            f'Merge pull request #{number} from acme/{branch}\n\n{title}')

    def test_finds_the_introducing_pr(self):
        [case] = mine(self.repo, 'main', since='2000-01-01')
        self.assertEqual((case['id'], case['fix_ids']), ('11', ['13']))
        self.assertEqual(case['title'], 'Make add faster')
        self.assertEqual(case['head'], git(self.repo, 'rev-parse', 'HEAD~2'))
        self.assertEqual(case['base'], git(self.repo, 'rev-parse', 'HEAD~2^1'))
        # The fix changed line 32 of app/calc.py (old side).
        self.assertEqual(case['fix_lines'], {'app/calc.py': [[32, 32]]})


def result(case, run, findings, verdicts=None, seconds=100.0, find='done'):
    return {'case': case, 'run': run, 'find': find, 'findings': findings, 'verdicts': verdicts,
            'seconds': seconds, 'turns': 5}


CASES = {
    '11': {'id': '11', 'kind': 'bug', 'fix_lines': {'app/calc.py': [[32, 32]]}},
    '20': {'id': '20', 'kind': 'clean', 'fix_lines': {}},
}
HIT = {'file': 'app/calc.py', 'line': 40, 'title': 'sign'}  # within 15 lines of 32
FAR = {'file': 'app/calc.py', 'line': 60, 'title': 'other'}


class ScoreTest(unittest.TestCase):
    def test_catch_needs_the_right_file_and_a_near_line(self):
        s = score(CASES, [result('11', 0, [HIT]), result('11', 1, [FAR]),
                          result('11', 2, [dict(HIT, file='app/other.py')])])
        self.assertEqual(s['cases']['11']['caught'], [True, False, False])
        self.assertAlmostEqual(s['catch_rate'], 1 / 3)

    def test_refuted_finding_does_not_count(self):
        s = score(CASES, [result('11', 0, [HIT], [{'index': 0, 'verdict': 'refuted'}])])
        self.assertEqual(s['cases']['11']['caught'], [False])

    def test_false_alarms_are_kept_findings_on_clean_cases(self):
        s = score(CASES, [result('20', 0, [FAR, FAR], [{'index': 0, 'verdict': 'refuted'}]),
                          result('20', 1, [])])
        self.assertEqual(s['false_alarms'], 1)

    def test_spread_is_across_runs(self):
        rs = [result('11', 0, [HIT]), result('11', 1, []), result('11', 2, [HIT])]
        s = score(CASES, rs)
        # Run-level catch rates over bug cases: run 0 = 1, run 1 = 0, run 2 = 1.
        self.assertEqual(s['catch_rate_by_run'], [1.0, 0.0, 1.0])
        self.assertEqual(s['spread'], 1.0)

    def test_time_and_timeouts(self):
        rs = [result('11', i, [], seconds=float(s)) for i, s in enumerate(range(10, 110, 10))]
        rs[3]['find'] = 'timeout'
        s = score(CASES, rs)
        self.assertEqual(s['p50_seconds'], 60.0)
        self.assertEqual(s['p90_seconds'], 100.0)
        self.assertEqual(s['timeouts'], 1)

    def test_no_json_counts_as_failed_not_clean(self):
        s = score(CASES, [result('11', 0, None, find='timeout')])
        self.assertEqual(s['no_answer'], 1)


class CompareTest(unittest.TestCase):
    def summary(self, rate, spread, timeouts=0, p90=100.0):
        return {'catch_rate': rate, 'spread': spread, 'timeouts': timeouts, 'p90_seconds': p90,
                'false_alarms': 0, 'runs': 9}

    def test_within_noise(self):
        self.assertEqual(compare(self.summary(0.5, 0.3), self.summary(0.6, 0.2))['catch_rate'], 'within noise')

    def test_clear_change(self):
        self.assertEqual(compare(self.summary(0.3, 0.1), self.summary(0.8, 0.1))['catch_rate'], 'better')
        self.assertEqual(compare(self.summary(0.8, 0.1), self.summary(0.3, 0.1))['catch_rate'], 'worse')

    def test_more_timeouts_is_worse(self):
        self.assertEqual(compare(self.summary(0.5, 0.1, 0), self.summary(0.5, 0.1, 3))['timeouts'], 'worse')

    def test_ship_verdict(self):
        self.assertTrue(compare(self.summary(0.5, 0.3), self.summary(0.6, 0.2))['ship'])
        self.assertFalse(compare(self.summary(0.8, 0.1), self.summary(0.3, 0.1))['ship'])


if __name__ == '__main__':
    unittest.main()
