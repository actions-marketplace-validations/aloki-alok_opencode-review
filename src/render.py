"""Turn the outcome of a review into the one PR comment."""
from __future__ import annotations

from dataclasses import dataclass

MARKER = '<!-- opencode-review -->'


@dataclass
class Outcome:
    sha: str
    find: str  # done | timeout | failed
    findings: list | None  # None: the find pass gave no JSON
    verify: str  # done | timeout | failed | skipped
    verdicts: list | None
    max_findings: int = 5
    reason: str = ''


ITEM_WORDS = 11  # per title and per fix: 5 items stay under 150 words


def render(o):
    sha = o.sha[:9]
    lines = [MARKER]
    if o.findings is None:
        if o.find == 'failed':
            lines.append(f'Review failed for {sha}: {o.reason or "the model gave no answer"}.')
        else:
            lines.append(f'Review did not finish for {sha}. It runs again on the next push, '
                         'or comment `/oc review`.')
        return '\n'.join(lines)

    checked = o.verify == 'done'
    by_index = {v.get('index'): v.get('verdict') for v in (o.verdicts or [])}
    kept = [f for i, f in enumerate(o.findings) if not checked or by_index.get(i) == 'real']
    kept = kept[:o.max_findings]
    notes = []
    if o.find == 'timeout':
        notes.append('Stopped at the time limit, so it may have missed things.')
    if kept and o.verify in ('timeout', 'failed'):
        notes.append('Second check did not finish.')

    if kept:
        n = len(kept)
        lines += [f"Changes needed: {n} thing{'s' if n > 1 else ''}.", '']
        for i, f in enumerate(kept, 1):
            where = ':'.join(str(x) for x in (f.get('file'), f.get('line')) if x) or '?'
            fix = _clip(f.get('fix'))
            lines.append(f"{i}. {_clip(f.get('title')).rstrip('.')} (`{where}`).{' ' + fix if fix else ''}")
    elif o.find == 'done':
        lines.append('Nothing blocking found.')
    else:
        lines.append('No findings before the time limit.')
        notes = [n for n in notes if 'time limit' not in n] + ['Comment `/oc review` to run it again.']
    lines += ['', f"<sub>OpenCode review of {sha}, advisory.{''.join(' ' + n for n in notes)} "
                  'Reply if a finding is wrong.</sub>']
    return '\n'.join(lines)


def _clip(text):
    words = str(text or '').split()
    return ' '.join(words[:ITEM_WORDS]) + ('...' if len(words) > ITEM_WORDS else '')
