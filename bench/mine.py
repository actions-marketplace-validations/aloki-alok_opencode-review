"""Find bug-introducing PRs in a repo's history (SZZ). For each merged fix PR, blame the lines it changed
in its parent, map the blamed commits to the PR that landed them, and keep the pair when one PR owns
most of those lines.

usage: python3 bench/mine.py <repo> [--branch main] [--since 2026-01-01] > cases.jsonl
Each line is one case: the introducing PR's head and base, and the lines its fix changed, for scoring.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess

MERGE = re.compile(r'Merge pull request #(\d+) from [^/\s]+/(\S+)')
SQUASH = re.compile(r'^(.*) \(#(\d+)\)$')
FIX = re.compile(r'^(fix|hotfix|bugfix|bug)\b|^fix(\(.*\))?:', re.I)
SKIP = re.compile(r'(^|/)(tests?|spec|__tests__)/|_test\.|\.test\.|\.spec\.|\.(md|rst|txt|lock|po|pot)$')
MIN_SHARE = 0.6


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, check=True).stdout


def landings(repo, branch):
    """Every PR that landed on `branch` by merge or squash: sha -> (id, title, body, from_branch, date)."""
    out = {}
    log = git(repo, 'log', branch, '--first-parent', '--format=%H%x00%cs%x00%s%x00%b%x1e')
    for rec in log.split('\x1e'):
        if not rec.strip():
            continue
        sha, date, subject, body = rec.strip('\n').split('\x00', 3)
        if m := MERGE.match(subject):
            lines = [ln for ln in body.splitlines() if ln.strip()]
            title = lines[0] if lines else subject
            out[sha] = (m[1], title, '\n'.join(lines[1:]), m[2], date)
        elif m := SQUASH.match(subject):
            out[sha] = (m[2], m[1], body.strip(), '', date)
    return out


def changed_lines(repo, base, head):
    """Old-side line ranges a commit changed, per file. An insertion counts as the line it follows."""
    lines, path = {}, None
    for ln in git(repo, 'diff', '-U0', '--no-renames', base, head).splitlines():
        if ln.startswith('--- '):
            path = ln[6:] if ln.startswith('--- a/') else None
        elif ln.startswith('@@') and path and not SKIP.search(path):
            start, count = re.match(r'@@ -(\d+)(?:,(\d+))?', ln).groups()
            start, count = int(start), int(count or 1)
            lines.setdefault(path, []).append([max(start, 1), max(start, 1) + max(count, 1) - 1, count])
    return lines


def mine(repo, branch='main', since='2000-01-01'):
    prs = landings(repo, branch)
    first_parent = set(prs) | set(git(repo, 'rev-list', '--first-parent', branch).split())
    landed_by = {}

    def landing(commit):
        if commit not in landed_by:
            if commit in first_parent:
                landed_by[commit] = commit
            else:
                path = git(repo, 'rev-list', '--first-parent', '--ancestry-path', f'{commit}..{branch}').split()
                landed_by[commit] = path[-1] if path else None
        return landed_by[commit]

    cases = {}
    for sha, (pr_id, title, _, from_branch, date) in prs.items():
        if date < since or not (FIX.search(title) or from_branch.startswith(('fix/', 'hotfix/', 'bugfix/'))):
            continue
        parent = f'{sha}^1'
        fixed = changed_lines(repo, parent, sha)
        blamed = collections.Counter()
        for path, ranges in fixed.items():
            for start, end, count in ranges:
                if count == 0:
                    continue  # a pure insertion has no old line to blame
                out = git(repo, 'blame', '-l', '-s', f'-L{start},{end}', parent, '--', path)
                blamed.update(m[1] for m in re.finditer(r'^\^?([0-9a-f]{40}) ', out, re.M))
        by_pr = collections.Counter()
        for commit, n in blamed.items():
            land = landing(commit)
            if land in prs and land != sha:
                by_pr[land] += n
        if not by_pr:
            continue
        top, n = by_pr.most_common(1)[0]
        if n / sum(blamed.values()) < MIN_SHARE:
            continue
        intro_id, intro_title, intro_body, _, _ = prs[top]
        case = cases.setdefault(
            top,
            {
                'id': intro_id,
                'kind': 'bug',
                'title': intro_title,
                'body': intro_body,
                'head': top,
                'base': git(repo, 'rev-parse', f'{top}^1').strip(),
                'fix_ids': [],
                'fix_lines': {},
            },
        )
        case['fix_ids'].append(pr_id)
        for path, ranges in fixed.items():
            case['fix_lines'].setdefault(path, []).extend([s, e] for s, e, _ in ranges)
    return list(cases.values())


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('repo')
    ap.add_argument('--branch', default='main')
    ap.add_argument('--since', default='2000-01-01')
    a = ap.parse_args()
    for c in mine(a.repo, a.branch, a.since):
        print(json.dumps(c))
