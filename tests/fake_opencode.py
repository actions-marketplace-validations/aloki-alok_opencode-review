#!/usr/bin/env python3
"""Stand-in for `opencode run --format json`. The plan file (OPENCODE_FAKE_PLAN) says what each call prints:
{"run": [[delay_seconds, event], ...], "resume": [[...]], "ignore_int": false, "exit": 0}
or the same keyed by agent: {"review": {...}, "verify": {...}}. A call with --session uses "resume"
of the agent that started the session. Each call's argv, env, cwd and top-level files go to
OPENCODE_FAKE_CALLS."""

import json
import os
import signal
import sys
import time


def tree():
    # What the model would see, snapshot at call time: the action deletes its work dir afterwards.
    out = {}
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in files:
            path = os.path.relpath(os.path.join(root, name))
            out[path] = open(path, errors='replace').read()[:20000]
    return out


plan = json.load(open(os.environ['OPENCODE_FAKE_PLAN']))
argv = sys.argv[1:]
agent = argv[argv.index('--agent') + 1]
resume = '--session' in argv
if resume:
    agent = argv[argv.index('--session') + 1].removeprefix('ses_')
step = plan.get(agent, plan)
with open(os.environ['OPENCODE_FAKE_CALLS'], 'a') as f:
    f.write(
        json.dumps(
            {
                'argv': argv,
                'env': dict(os.environ),
                'cwd': os.getcwd(),
                'files': sorted(os.listdir('.')),
                'tree': tree(),
                'gitconfig': open('.git/config').read() if os.path.exists('.git/config') else '',
            }
        )
        + '\n'
    )
data = os.environ.get('XDG_DATA_HOME', '')
if data:
    # Like OpenCode's own database: a second job sharing this dir would see the first one's runs.
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, 'runs.log'), 'a') as f:
        f.write(f'{os.getpid()}\n')
if step.get('ignore_int'):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
for delay, event in step['resume' if resume else 'run']:
    time.sleep(delay)
    print(json.dumps({'sessionID': f'ses_{agent}', **event}), flush=True)
sys.exit(step.get('exit', 0))
