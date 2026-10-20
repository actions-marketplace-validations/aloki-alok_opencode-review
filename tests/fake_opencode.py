#!/usr/bin/env python3
"""Stand-in for `opencode run --format json`. The plan file (OPENCODE_FAKE_PLAN) says what each call prints:
{"run": [[delay_seconds, event], ...], "resume": [[...]], "ignore_int": false}
A call with --session uses "resume". Each call's argv and env are appended to OPENCODE_FAKE_CALLS."""
import json
import os
import signal
import sys
import time

plan = json.load(open(os.environ['OPENCODE_FAKE_PLAN']))
argv = sys.argv[1:]
resume = '--session' in argv
data = os.environ.get('XDG_DATA_HOME', '')
with open(os.environ['OPENCODE_FAKE_CALLS'], 'a') as f:
    f.write(json.dumps({'argv': argv, 'env': dict(os.environ), 'cwd': os.getcwd()}) + '\n')
if data:
    # Like OpenCode's own database: a second job sharing this dir would see the first one's runs.
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, 'runs.log'), 'a') as f:
        f.write(f'{os.getpid()}\n')
if plan.get('ignore_int'):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
for delay, event in plan['resume' if resume else 'run']:
    time.sleep(delay)
    print(json.dumps({'sessionID': 'ses_fake', **event}), flush=True)
sys.exit(plan.get('exit', 0))
