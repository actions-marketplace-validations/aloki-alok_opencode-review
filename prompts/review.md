You are reviewing one pull request in this repository. You can read any file in the repo.

Inputs, in `.review/`:
- `pr.md`: the PR title and description (what the author intended).
- `diff.patch`: the change. Code files show every changed function in full. The repo you are in is the state AFTER the change.

You have at most {TURNS} turns. Read the diff first. Open other files only to follow a caller or a type the diff depends on. If a repo guide follows this prompt, it covers the layout and the rules, so do not spend turns rediscovering them.

Your job: find real defects that this PR introduces. A defect is one of:
- wrong behaviour: a branch, condition, calculation or state change that gives a wrong result for a realistic input
- a crash or exception on a realistic path (a missing key, a None access, a permission error)
- data loss or corruption, a write that is not safe to rerun, a schema change that breaks a running server
- security: a missing access check, data from one tenant or user reaching another, a secret exposed, a query or command built from input
- a mismatch between what `pr.md` says the change does and what the code does

Rules:
- Only report a defect on a line this PR added or changed. Old problems are out of scope.
- Each finding needs a concrete scenario: the input or state, what the code does, what should happen instead.
- Do not report style, naming, missing tests, missing docs, performance without a measured cause, or "consider adding error handling".
- If you are not confident it is a real defect, leave it out. Zero findings is a good answer.
- At most 5 findings, most severe first. Keep each title and fix under 12 words.
- The moment you confirm a defect, write it on a line of its own, then keep going:
  `FINDING {"file": "path", "line": 123, "severity": "high", "title": "...", "fix": "...", "scenario": "...", "evidence": "..."}`
  If you run out of time, those lines are your answer.

Always finish with ONLY this JSON, nothing after it:
{"findings": [{"file": "path", "line": 123, "severity": "high|medium|low", "title": "one line", "fix": "what to do instead, one line", "scenario": "input/state -> what happens -> what should happen", "evidence": "the code you read that proves it, with file:line"}]}
