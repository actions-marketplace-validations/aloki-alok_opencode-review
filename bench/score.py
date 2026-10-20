"""Score bench results against the lines each bug's fix changed.

A finding catches the bug when it names a file the fix changed, within NEAR lines of a changed line.
Lines drift between the introducing PR and the fix, so read catches and misses by hand before trusting
small differences. Findings the refute pass called "refuted" don't count. False alarms are kept
findings on clean cases (PRs that never needed a fix).

usage: python3 bench/score.py cases.jsonl results/<config>  ->  summary JSON on stdout
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from render import kept_findings  # noqa: E402

NEAR = 15


def kept(r):
    # The same rule the comment uses, so the bench scores what users see.
    return kept_findings(r.get('findings') or [], r.get('verdicts') if r.get('verify', 'done') == 'done' else None)


def hit(finding, fix_lines):
    path = str(finding.get('file') or '').lstrip('./')
    try:
        line = int(finding.get('line') or 0)
    except (TypeError, ValueError):
        return False
    return any(lo - NEAR <= line <= hi + NEAR for lo, hi in fix_lines.get(path, []))


def _rank(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * q))] if s else 0.0


def score(cases, results):
    per_case, by_run = {}, {}
    false_alarms = 0
    for r in sorted(results, key=lambda r: (r['case'], r['run'])):
        case = cases[r['case']]
        if case['kind'] == 'clean':
            false_alarms += len(kept(r))
            continue
        caught = any(hit(f, case['fix_lines']) for f in kept(r))
        per_case.setdefault(r['case'], {'caught': []})['caught'].append(caught)
        by_run.setdefault(r['run'], []).append(caught)
    rates = [sum(v) / len(v) for _, v in sorted(by_run.items())]
    all_caught = [c for v in per_case.values() for c in v['caught']]
    seconds = [r['seconds'] for r in results]
    return {
        'runs': len(results),
        'catch_rate': sum(all_caught) / len(all_caught) if all_caught else 0.0,
        'catch_rate_by_run': rates,
        'spread': max(rates) - min(rates) if rates else 0.0,
        'false_alarms': false_alarms,
        'timeouts': sum(r['find'] == 'timeout' for r in results),
        'no_answer': sum(r.get('findings') is None for r in results),
        'p50_seconds': _rank(seconds, 0.5),
        'p90_seconds': _rank(seconds, 0.9),
        'cases': per_case,
    }


if __name__ == '__main__':
    cases = {c['id']: c for c in map(json.loads, Path(sys.argv[1]).read_text().splitlines())}
    results = [json.loads(p.read_text()) for p in Path(sys.argv[2]).glob('*/*/result.json')]
    print(json.dumps(score(cases, results), indent=1))
