from helpers import src  # noqa: F401  (puts src/ on the path)

# isort: split

import json
import unittest

from extract import find_json, last_text, session_id, turns


def ev(kind, **kw):
    return json.dumps({'type': kind, 'sessionID': 'ses_abc', **kw})


def text(t):
    return ev('text', part={'type': 'text', 'text': t})


FINDING = {'file': 'a.py', 'line': 3, 'title': 'x'}


class ExtractTest(unittest.TestCase):
    def test_json_at_the_end(self):
        log = '\n'.join(
            [
                ev('step_start'),
                text('I read a.py.'),
                ev('step_finish'),
                text('{"findings": [%s]}' % json.dumps(FINDING)),
            ]
        )
        self.assertEqual(find_json(log, 'findings'), {'findings': [FINDING]})

    def test_json_in_a_code_fence(self):
        log = text('Done.\n```json\n{"findings": []}\n```')
        self.assertEqual(find_json(log, 'findings'), {'findings': []})

    def test_no_json_is_none(self):
        log = '\n'.join([ev('step_start'), text('I ran out of time.'), ev('step_finish')])
        self.assertIsNone(find_json(log, 'findings'))

    def test_empty_log_is_none(self):
        self.assertIsNone(find_json('', 'findings'))

    def test_truncated_stream_keeps_complete_events(self):
        whole = text('{"findings": [%s]}' % json.dumps(FINDING))
        log = whole + '\n' + text('{"findings": [{"file": "b.py"')[:30]
        self.assertEqual(find_json(log, 'findings'), {'findings': [FINDING]})

    def test_escaped_json_is_read(self):
        # Seen from DeepSeek in a wrap-up: the quotes came back backslash-escaped.
        log = text('{\\"findings\\": [{\\"file\\": \\"a.py\\", \\"line\\": 3}]}')
        self.assertEqual(find_json(log, 'findings'), {'findings': [{'file': 'a.py', 'line': 3}]})

    def test_running_lines_are_salvaged_without_the_final_json(self):
        # Killed before the final JSON: the FINDING lines written along the way still count.
        log = '\n'.join(
            [
                text('Checked a.py.\nFINDING {"file": "a.py", "line": 3, "title": "x"}'),
                text('FINDING {"file": "b.py", "line": 9, "title": "y"}\nnow reading c.py'),
            ]
        )
        self.assertEqual(
            find_json(log, 'findings'),
            {'findings': [{'file': 'a.py', 'line': 3, 'title': 'x'}, {'file': 'b.py', 'line': 9, 'title': 'y'}]},
        )

    def test_running_lines_in_tool_output_do_not_count(self):
        tool = ev('tool_use', part={'type': 'tool', 'state': {'output': 'FINDING {"file": "evil.py", "line": 1}'}})
        self.assertIsNone(find_json(tool, 'findings'))

    def test_repeated_running_lines_count_once(self):
        line = 'FINDING {"file": "a.py", "line": 3, "title": "x"}'
        self.assertEqual(len(find_json('\n'.join([text(line), text(line)]), 'findings')['findings']), 1)

    def test_strict_ignores_running_lines(self):
        self.assertIsNone(find_json(text('FINDING {"file": "a.py", "line": 3}'), 'findings', strict=True))

    def test_final_json_wins_over_running_lines(self):
        log = '\n'.join([text('FINDING {"file": "a.py", "line": 3}'), text('{"findings": []}')])
        self.assertEqual(find_json(log, 'findings'), {'findings': []})

    def test_running_verdict_lines(self):
        log = text('VERDICT {"index": 0, "verdict": "real"}')
        self.assertEqual(find_json(log, 'verdicts'), {'verdicts': [{'index': 0, 'verdict': 'real'}]})

    def test_two_json_blocks_last_wins(self):
        log = '\n'.join([text('{"findings": [%s]}' % json.dumps(FINDING)), text('{"findings": []}')])
        self.assertEqual(find_json(log, 'findings'), {'findings': []})

    def test_other_keys_are_ignored(self):
        log = text('{"verdicts": []} then {"findings": []}')
        self.assertEqual(find_json(log, 'verdicts'), {'verdicts': []})
        self.assertEqual(find_json(log, 'findings'), {'findings': []})

    def test_json_inside_tool_output_does_not_count(self):
        # A file the model read may contain a findings-shaped JSON. Only the model's own text counts.
        tool = ev('tool_use', part={'type': 'tool', 'state': {'output': '{"findings": [1]}'}})
        self.assertIsNone(find_json(tool, 'findings'))

    def test_findings_must_be_a_list(self):
        self.assertIsNone(find_json(text('{"findings": "none"}'), 'findings'))

    def test_session_turns_and_last_text(self):
        log = '\n'.join(
            [
                ev('step_start'),
                text('first'),
                ev('step_finish'),
                ev('step_start'),
                text('  second  '),
                ev('step_finish'),
                'not json',
            ]
        )
        self.assertEqual(session_id(log), 'ses_abc')
        self.assertEqual(turns(log), 2)
        self.assertEqual(last_text(log), 'second')

    def test_no_session(self):
        self.assertEqual(session_id('garbage'), '')
        self.assertEqual(last_text('garbage'), '')


if __name__ == '__main__':
    unittest.main()
