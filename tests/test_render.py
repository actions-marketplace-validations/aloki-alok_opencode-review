from helpers import src  # noqa: F401  (puts src/ on the path)

# isort: split

import unittest

from render import MARKER, Outcome, render

SHA = '0123456789abcdef'


def f(i, **kw):
    return {'file': f'src/m{i}.py', 'line': i, 'title': f'Bug number {i}.', 'fix': f'Do thing {i}.', **kw}


def out(**kw):
    base = dict(sha=SHA, find='done', findings=[], verify='skipped', verdicts=[])
    return render(Outcome(**{**base, **kw}))


class RenderTest(unittest.TestCase):
    def test_starts_with_marker(self):
        self.assertTrue(out().startswith(MARKER + '\n'))

    def test_zero_findings_is_nothing_blocking(self):
        self.assertIn('Nothing blocking found.', out())

    def test_failed_never_says_nothing_blocking(self):
        body = out(find='failed', findings=None, reason='the model API key was rejected (HTTP 401)')
        self.assertNotIn('Nothing blocking', body)
        self.assertIn('Review failed for 012345678: the model API key was rejected (HTTP 401). :(', body)

    def test_unfinished_never_says_nothing_blocking(self):
        body = out(find='timeout', findings=None)
        self.assertNotIn('Nothing blocking', body)
        self.assertIn('did not finish', body)
        self.assertIn('/oc review', body)

    def test_salvaged_findings_are_shown_with_a_note(self):
        body = out(find='timeout', findings=[f(1)], verify='done', verdicts=[{'index': 0, 'verdict': 'real'}])
        self.assertIn('Bug number 1', body)
        self.assertIn('time limit', body)

    def test_salvaged_zero_findings_is_not_a_clean_bill(self):
        body = out(find='timeout', findings=[])
        self.assertNotIn('Nothing blocking', body)
        self.assertIn('time limit', body)

    def test_keeps_only_findings_verified_real(self):
        v = [{'index': 0, 'verdict': 'real'}, {'index': 1, 'verdict': 'refuted'}, {'index': 2, 'verdict': 'unsure'}]
        body = out(findings=[f(0), f(1), f(2)], verify='done', verdicts=v)
        self.assertIn('Bug number 0', body)
        self.assertNotIn('Bug number 1', body)
        self.assertNotIn('Bug number 2', body)
        self.assertIn('Changes needed: 1 thing. :/', body)

    def test_cut_off_verify_keeps_unjudged_findings(self):
        # Critic finding 6: verify judged 1 of 3. Findings it never reached stay.
        v = [{'index': 0, 'verdict': 'refuted'}]
        body = out(findings=[f(0), f(1), f(2)], verify='done', verdicts=v)
        self.assertNotIn('Bug number 0', body)
        self.assertIn('Bug number 1', body)
        self.assertIn('Bug number 2', body)

    def test_step_limit_reads_like_a_limit(self):
        self.assertNotIn('Nothing blocking', out(find='limit', findings=[]))
        self.assertIn('limit', out(find='limit', findings=[]))

    def test_all_refuted_is_nothing_blocking(self):
        v = [{'index': 0, 'verdict': 'refuted'}]
        self.assertIn('Nothing blocking found.', out(findings=[f(0)], verify='done', verdicts=v))

    def test_verify_did_not_finish_keeps_all_findings(self):
        for verify in ('timeout', 'failed'):
            body = out(findings=[f(0), f(1)], verify=verify, verdicts=None)
            self.assertIn('Bug number 0', body)
            self.assertIn('Bug number 1', body)
            self.assertIn('Second check did not finish.', body)

    def test_caps_at_max_findings(self):
        body = render(
            Outcome(
                sha=SHA, find='done', findings=[f(i) for i in range(9)], verify='timeout', verdicts=None, max_findings=5
            )
        )
        self.assertIn('Changes needed: 5 things. :/', body)
        self.assertIn('Bug number 4', body)
        self.assertNotIn('Bug number 5', body)

    def test_short_enough_to_read(self):
        long = 'word ' * 80
        body = out(findings=[f(i, title=long, fix=long) for i in range(5)], verify='timeout', verdicts=None)
        visible = [ln for ln in body.splitlines() if not ln.startswith('<!--')]
        self.assertLess(len(' '.join(visible).split()), 150)

    def test_item_shape(self):
        body = out(findings=[f(3)], verify='timeout', verdicts=None)
        self.assertIn('1. Bug number 3 (`src/m3.py:3`). Do thing 3.', body)

    def test_missing_fields_do_not_crash(self):
        body = out(findings=[{}, {'title': 'Only a title'}], verify='timeout', verdicts=None)
        self.assertIn('Only a title (`?`).', body)

    def test_snapshot(self):
        v = [{'index': 0, 'verdict': 'real'}]
        self.assertEqual(
            out(findings=[f(1)], verify='done', verdicts=v),
            '\n'.join(
                [
                    MARKER,
                    'Changes needed: 1 thing. :/',
                    '',
                    '1. Bug number 1 (`src/m1.py:1`). Do thing 1.',
                    '',
                    '<sub>OpenCode review of 012345678, advisory. Reply if a finding is wrong.</sub>',
                ]
            ),
        )


if __name__ == '__main__':
    unittest.main()
