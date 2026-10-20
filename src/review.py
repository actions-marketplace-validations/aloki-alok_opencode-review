"""The review itself, on a local checkout and with no GitHub calls: the action and the bench both run this."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from budget import Budget, find_budget, parse_budget
from diff import build
from render import Outcome
from runner import Pass, Result, run_pass

PROMPTS = Path(__file__).resolve().parent.parent / 'prompts'
VERIFY_SECONDS = 120
# Files in a PR that would change how OpenCode itself runs: config, agents, plugins (code).
OPENCODE_FILES = ('opencode.json', 'opencode.jsonc', '.opencode')
# Instruction files OpenCode loads on its own: taken from the base, so a PR can't rewrite its review.
RULE_FILES = ('AGENTS.md', 'CLAUDE.md')


@dataclass
class Model:
    opencode: str
    model: str  # provider/model
    api_key: str
    turn_p90: float = 14
    wrap_seconds: int = 30


@dataclass
class Review:
    outcome: Outcome
    find: Result
    verify: Result | None
    changed: int
    budget: Budget


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout


def sanitize(code, base):
    """Make the checkout safe to hand to OpenCode. `base` is None when the checkout is trusted."""
    for name in OPENCODE_FILES:
        p = Path(code, name)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    if base:
        for name in RULE_FILES:
            p = Path(code, name)
            try:
                p.write_text(git(code, 'show', f'{base}:{name}'))
            except subprocess.CalledProcessError:
                p.unlink(missing_ok=True)  # not in the base: the PR added it


def guide_at(code, ref, path):
    try:
        return git(code, 'show', f'{ref}:{path}')
    except subprocess.CalledProcessError:
        return ''


def prompt(name, turns, guide=''):
    text = (PROMPTS / name).read_text().replace('{TURNS}', str(turns))
    return text + (f'\n\n# Repo guide\n\n{guide}' if guide.strip() else '')


def one_pass(m, code, work, agent, text, budget, json_key):
    return run_pass(
        Pass(
            opencode=m.opencode,
            cwd=str(code),
            work=str(Path(work, agent)),
            model=m.model,
            api_key=m.api_key,
            agent=agent,
            prompt=text,
            budget=budget,
            json_key=json_key,
            wrap_seconds=m.wrap_seconds,
        )
    )


def review(m, code, work, merge_base, head, pr_text, guide, budget_text='auto', max_findings=5, log=print):
    """Find pass, then a refute pass if anything was found. Writes the inputs to `code/.review/`."""
    review_dir = Path(code, '.review')
    review_dir.mkdir(exist_ok=True)
    patch, changed = build(code, merge_base, head)
    (review_dir / 'diff.patch').write_text(patch)
    (review_dir / 'pr.md').write_text(pr_text)
    budget = parse_budget(budget_text) or find_budget(changed, m.turn_p90)
    log(f'changed code lines: {changed}, find pass: {budget.turns} turns, {budget.seconds} s')

    found = one_pass(m, code, work, 'review', prompt('review.md', budget.turns, guide), budget, 'findings')
    findings = found.result['findings'] if found.result else None
    log(
        f'find pass: {found.status}, {found.turns} turns, {found.seconds} s, '
        f'{"no JSON" if findings is None else len(findings)} findings'
    )
    verify, verdicts, checked = 'skipped', None, None
    if findings:
        (review_dir / 'findings.json').write_text(json.dumps({'findings': findings}, indent=1))
        vb = Budget(max(3, int(VERIFY_SECONDS // m.turn_p90)), VERIFY_SECONDS)
        checked = one_pass(m, code, work, 'verify', prompt('verify.md', vb.turns, guide), vb, 'verdicts')
        verdicts = checked.result['verdicts'] if checked.result else None
        verify = 'done' if verdicts is not None else 'failed' if checked.status == 'failed' else 'timeout'
        log(f'verify pass: {verify}, {checked.turns} turns, {checked.seconds} s')
    outcome = Outcome(head, found.status, findings, verify, verdicts, max_findings, found.error)
    return Review(outcome, found, checked, changed, budget)
