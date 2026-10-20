"""Run one OpenCode pass with a time cap, and salvage its work if the cap is hit."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from extract import error_message, find_json, last_text, session_id, turns

KILL_GRACE = 5  # seconds between SIGINT and SIGKILL
KEY_VAR = 'OPENCODE_REVIEW_API_KEY'
# Proxy and CA settings so self-hosted runners behind a proxy still reach the provider.
PASS_ENV = ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy',
            'https_proxy', 'no_proxy', 'SSL_CERT_FILE', 'NODE_EXTRA_CA_CERTS')
WRAP = {
    True: 'Time is up. Do not call any tools. Print the JSON now, in the format you were given, '
          'from what you already read. If you found nothing, print it with an empty list.',
    False: 'Time is up. Do not call any tools. Answer now from what you already read. If you could '
           'not find out, say what you checked and what is still unknown.',
}


@dataclass
class Pass:
    opencode: str
    cwd: str
    work: str  # this job's own dir: OpenCode's home, config and database live here
    model: str  # provider/model
    api_key: str
    agent: str
    prompt: str
    budget: object
    json_key: str | None  # findings | verdicts, or None for a free-text answer
    wrap_seconds: int = 30


@dataclass
class Result:
    status: str  # done | timeout | failed
    result: dict | None = None
    answer: str = ''
    turns: int = 0
    seconds: float = 0
    error: str = ''


def config(p):
    # Passed as OPENCODE_CONFIG_CONTENT, which overrides a project opencode.json in the PR.
    read_only = {'*': 'deny', 'read': {'*': 'allow', '*.env': 'deny', '*.env.*': 'deny'},
                 'glob': 'allow', 'grep': 'allow', 'list': 'allow'}
    for tool in ('edit', 'bash', 'webfetch', 'websearch', 'task', 'skill', 'external_directory',
                 'question', 'doom_loop'):
        read_only[tool] = 'deny'
    return {
        '$schema': 'https://opencode.ai/config.json',
        'share': 'disabled',
        'autoupdate': False,
        'permission': read_only,
        'agent': {p.agent: {'mode': 'primary', 'steps': p.budget.turns},
                  'wrap': {'mode': 'primary', 'steps': 1, 'permission': {'*': 'deny'}}},
        'provider': {p.model.split('/', 1)[0]: {'options': {'apiKey': '{env:%s}' % KEY_VAR}}},
    }


def env(p):
    home = Path(p.work)
    e = {k: os.environ[k] for k in PASS_ENV if k in os.environ}
    e.update(HOME=str(home / 'home'), XDG_CONFIG_HOME=str(home / 'config'), XDG_DATA_HOME=str(home / 'data'),
             XDG_CACHE_HOME=str(home / 'cache'), XDG_STATE_HOME=str(home / 'state'),
             OPENCODE_DISABLE_CLAUDE_CODE='1', OPENCODE_DISABLE_AUTOUPDATE='1',
             OPENCODE_CONFIG_CONTENT=json.dumps(config(p)))
    e[KEY_VAR] = p.api_key
    for k, v in os.environ.items():
        if k.startswith('OPENCODE_FAKE_'):  # test double controls
            e[k] = v
    for d in ('home', 'config', 'data', 'cache', 'state'):
        (home / d).mkdir(parents=True, exist_ok=True)
    return e


def _run(p, args, seconds, log_path):
    """Run until done or `seconds`, then SIGINT (OpenCode saves the session), then SIGKILL."""
    with open(log_path, 'ab') as out:
        proc = subprocess.Popen([p.opencode, 'run', '--pure', '--format', 'json', '-m', p.model, *args],
                                cwd=p.cwd, env=env(p), stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.wait(timeout=seconds)
            return False
        except subprocess.TimeoutExpired:
            _signal(proc, signal.SIGINT)
            try:
                proc.wait(timeout=KILL_GRACE)
            except subprocess.TimeoutExpired:
                _signal(proc, signal.SIGKILL)
                proc.wait()
            return True


def _signal(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def run_pass(p):
    start = time.monotonic()
    Path(p.work).mkdir(parents=True, exist_ok=True)
    log_path = Path(p.work) / f'{p.agent}.log'
    timed_out = _run(p, ['--agent', p.agent, p.prompt], p.budget.seconds, log_path)
    log = log_path.read_text(errors='replace')
    sid, n = session_id(log), turns(log)

    def done():
        return find_json(log, p.json_key) is not None if p.json_key else bool(last_text(log))

    # Out of time, or the step cap ended it with prose: ask the same session for the answer.
    if sid and (timed_out or not done()):
        wrap_path = Path(p.work) / f'{p.agent}-wrap.log'
        _run(p, ['--session', sid, '--agent', 'wrap', WRAP[bool(p.json_key)]], p.wrap_seconds, wrap_path)
        log += '\n' + wrap_path.read_text(errors='replace')

    status = 'timeout' if timed_out else 'done' if sid else 'failed'
    r = Result(status, turns=n, seconds=round(time.monotonic() - start, 1))
    if p.json_key:
        r.result = find_json(log, p.json_key)
    else:
        r.answer = last_text(log)
    if r.result is None and not r.answer:
        r.error = error_message(log)
        if status == 'done' and r.error:
            r.status = 'failed'
    return r
