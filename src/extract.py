"""Read an `opencode run --format json` log: the model's text, its final JSON, the session and turn count."""

from __future__ import annotations

import json
import re


def _events(log):
    for line in log.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue  # a line cut off by a kill, or plain stderr
        if isinstance(e, dict):
            yield e


def _texts(log):
    # Only the model's own text parts: a file it read may hold JSON of the same shape.
    for e in _events(log):
        part = e.get('part') or {}
        if e.get('type') == 'text' and isinstance(part.get('text'), str):
            yield part['text']


def find_json(log, key, strict=False):
    """The last JSON object in the model's text whose `key` is a list, or None. Unless `strict`,
    falls back to the FINDING/VERDICT lines streamed along the way."""
    found = None
    for t in _texts(log):
        # A model sometimes prints the JSON with its quotes escaped: {\"findings\": []}.
        found = _last_json(t, key) or _last_json(t.replace('\\"', '"'), key) or found
    return found or (None if strict else _running_lines(log, key))


# Written one at a time as the model goes, so a run killed before its final JSON keeps them.
RUNNING = {'findings': 'FINDING', 'verdicts': 'VERDICT'}


def _running_lines(log, key):
    items = []
    for t in _texts(log):
        for m in re.finditer(r'^\s*%s\s+(\{.*\})\s*$' % RUNNING.get(key, '-'), t, re.M):
            try:
                obj = json.loads(m[1])
            except ValueError:
                continue
            if isinstance(obj, dict) and obj not in items:  # a wrap-up may repeat a line
                items.append(obj)
    return {key: items} if items else None


def _last_json(text, key):
    found = None
    decoder = json.JSONDecoder()
    for m in re.finditer(r'\{', text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get(key), list):
            found = obj
    return found


def session_id(log):
    return next((e['sessionID'] for e in _events(log) if e.get('sessionID')), '')


def turns(log):
    return sum(e.get('type') == 'step_finish' for e in _events(log))


def error_message(log):
    """The last error OpenCode reported, for the job log and the failure comment."""
    msg = ''
    for e in _events(log):
        if e.get('type') == 'error':
            err = e.get('error') or {}
            msg = str((err.get('data') or {}).get('message') or err.get('name') or 'unknown error')
    return msg


def last_text(log):
    texts = [t.strip() for t in _texts(log) if t.strip()]
    return texts[-1] if texts else ''
