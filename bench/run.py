"""Replay each case K times through the same review code the action runs, a few at a time.

usage: OPENCODE_REVIEW_API_KEY=... python3 bench/run.py cases.jsonl --repo PATH --out results/NAME \
         --model openrouter/deepseek/deepseek-v4.1-flash [--k 3] [--parallel 4] [--guide-file F | --guide-path P]
         [--budget auto] [--turn-p90 14] [--opencode PATH] [--only ID,ID]
Writes results/NAME/<case>/<run>/result.json. Finished runs are skipped, so a stopped bench resumes.
Score with: python3 bench/score.py cases.jsonl results/NAME
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

import review  # noqa: E402

worktree_lock = threading.Lock()  # git worktree add/remove on one repo must not overlap


def run_one(a, model, case, run):
    out = Path(a.out, case['id'], str(run))
    if (out / 'result.json').exists():
        return
    tmp = Path(tempfile.mkdtemp(prefix='oc-bench-'))
    code = tmp / 'code'
    try:
        with worktree_lock:
            review.git(a.repo, 'worktree', 'add', '-q', '--detach', str(code), case['head'])
        review.sanitize(code, case['base'])
        if a.guide_file:
            guide = Path(a.guide_file).read_text()
        elif a.guide_path:
            guide = review.guide_at(code, case['base'], a.guide_path)
        else:
            guide = ''
        lines = []
        r = review.review(
            model,
            code,
            tmp / 'work',
            case['base'],
            case['head'],
            f'# {case["title"]}\n\n{case.get("body") or ""}\n',
            guide,
            a.budget,
            5,
            lines.append,
        )
        out.mkdir(parents=True, exist_ok=True)
        for log in (tmp / 'work').rglob('*.log'):
            shutil.copy(log, out / log.name)
        o = r.outcome
        result = {
            'case': case['id'],
            'run': run,
            'find': o.find,
            'verify': o.verify,
            'findings': o.findings,
            'verdicts': o.verdicts,
            'seconds': round(r.find.seconds + (r.verify.seconds if r.verify else 0), 1),
            'turns': r.find.turns,
            'changed': r.changed,
            'budget': list(r.budget),
            'log': lines,
        }
        (out / 'result.json').write_text(json.dumps(result, indent=1))
        print(
            f'#{case["id"]} run {run}: {o.find}, {result["seconds"]} s, '
            f'{"no JSON" if o.findings is None else len(o.findings)} findings',
            flush=True,
        )
    finally:
        with worktree_lock:
            review.git(a.repo, 'worktree', 'remove', '--force', str(code))
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cases')
    ap.add_argument('--repo', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--k', type=int, default=3)
    ap.add_argument('--parallel', type=int, default=4)
    ap.add_argument('--guide-file')
    ap.add_argument('--guide-path')
    ap.add_argument('--budget', default='auto')
    ap.add_argument('--turn-p90', type=float, default=14)
    ap.add_argument('--opencode', default='opencode')
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    model = review.Model(a.opencode, a.model, os.environ['OPENCODE_REVIEW_API_KEY'], a.turn_p90)
    cases = [json.loads(ln) for ln in Path(a.cases).read_text().splitlines() if ln.strip()]
    if a.only:
        cases = [c for c in cases if c['id'] in a.only.split(',')]
    jobs = [(c, k) for k in range(a.k) for c in cases]
    with ThreadPoolExecutor(a.parallel) as pool:
        for f in [pool.submit(run_one, a, model, c, k) for c, k in jobs]:
            f.result()


if __name__ == '__main__':
    main()
