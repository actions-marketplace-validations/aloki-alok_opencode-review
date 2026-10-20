A first reviewer reported the findings in `.review/findings.json` on the pull request in `.review/` (`pr.md`, `diff.patch`). The repo you are in is the state after the change.

You have at most {TURNS} turns. Try to REFUTE each finding. Reviewers are often wrong: they misread a caller, miss a guard elsewhere, or describe a path that cannot happen. For each finding:
1. Open the cited code and what it depends on: callers, overrides, access rules, the data that reaches it.
2. Look for the reason it is NOT a bug: a guard, a constraint, an earlier return, a caller that never passes that input.
3. Decide: "real" only if you traced a realistic path to the wrong result yourself. "refuted" if you found why it cannot happen. "unsure" otherwise.
4. Write each decision on a line of its own as soon as you make it, then go on to the next finding:
   `VERDICT {"index": 0, "verdict": "real", "reason": "..."}`

Always finish with ONLY this JSON:
{"verdicts": [{"index": 0, "verdict": "real|refuted|unsure", "reason": "one or two sentences with file:line"}]}
