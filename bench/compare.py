"""Compare two bench summaries (from score.py). A catch-rate change smaller than the run-to-run spread
is "within noise". A change ships only if catches don't get worse and timeouts don't rise.

usage: python3 bench/compare.py before.json after.json
"""

from __future__ import annotations

import json
import sys


def compare(a, b):
    noise = max(a['spread'], b['spread'])
    delta = b['catch_rate'] - a['catch_rate']
    rate = 'within noise' if abs(delta) <= noise else 'better' if delta > 0 else 'worse'
    timeouts = 'same' if b['timeouts'] == a['timeouts'] else 'worse' if b['timeouts'] > a['timeouts'] else 'better'
    return {
        'catch_rate': rate,
        'catch_rate_change': round(delta, 3),
        'noise': round(noise, 3),
        'timeouts': timeouts,
        'false_alarms_change': b['false_alarms'] - a['false_alarms'],
        'p90_seconds_change': round(b['p90_seconds'] - a['p90_seconds'], 1),
        'ship': rate != 'worse' and timeouts != 'worse',
    }


if __name__ == '__main__':
    before, after = (json.load(open(p)) for p in sys.argv[1:3])
    print(json.dumps(compare(before, after), indent=1))
