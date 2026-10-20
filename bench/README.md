# Bench

Measures the reviewer on real bugs from a repo's own history, so a change to a prompt, a budget or a
model is judged by numbers instead of by one lucky run.

## How it works

1. `mine.py` finds merged fix PRs, blames the lines each fix changed, and maps them back to the PR
   that introduced them. Each pair becomes a case: the introducing PR, and the lines its fix touched.
2. `run.py` reviews each introducing PR K times (default 3) with the same code the action runs,
   a few at a time.
3. `score.py` counts a catch when a kept finding is within 15 lines of a line the fix changed, in
   the same file. It reports the catch rate, false alarms, time p50 and p90, timeouts, and the
   spread of the catch rate across the K runs.
4. `compare.py` puts two scores side by side. A catch-rate change smaller than the spread is
   "within noise". A change ships only if catches don't get worse and timeouts don't rise.

## Run it

```sh
python3 bench/mine.py path/to/repo --branch main --since 2026-01-01 > cases.jsonl
export OPENCODE_REVIEW_API_KEY=sk-...
python3 bench/run.py cases.jsonl --repo path/to/repo --out results/before \
  --model openrouter/deepseek/deepseek-v4.1-flash --k 3 --guide-path .github/opencode-review/guide.md
# change a prompt, then
python3 bench/run.py cases.jsonl --repo path/to/repo --out results/after ...
python3 bench/score.py cases.jsonl results/before > before.json
python3 bench/score.py cases.jsonl results/after > after.json
python3 bench/compare.py before.json after.json
```

`--only 123,456` limits the run to some cases. A stopped run resumes where it left off.

## Public cases

`cases/` holds 17 bug-introducing PRs from [httpx](https://github.com/encode/httpx),
[click](https://github.com/pallets/click) and [flask](https://github.com/pallets/flask), one file
per repo, mined with `mine.py` and picked by hand (renames, release bumps and docs reworks dropped).
Clone the repo with full history and pass it as `--repo`:

```sh
git clone https://github.com/encode/httpx /tmp/httpx
python3 bench/run.py bench/cases/httpx.jsonl --repo /tmp/httpx --out results/httpx --model ...
```

## Reading the numbers

- Lines move between the introducing PR and its fix, so a catch is approximate. Read the findings
  in `results/<name>/<case>/<run>/result.json` before trusting a small difference.
- A miss is not always the reviewer's fault: some bugs only show at runtime with production data.
- Cases with no later fix have no ground truth for catches. Add PRs you know are clean with
  `"kind": "clean"` and `"fix_lines": {}` to measure false alarms.
- Keep cases from private code out of public repos. Results hold findings that quote code.
