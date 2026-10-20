# OpenCode review

AI review for pull requests, and answers to questions in issues and PRs, run by
[OpenCode](https://opencode.ai) inside your own GitHub Actions with your own model key.

- **Reviews every PR.** One comment with only the defects the change introduces, each checked by a
  second pass that tries to prove it wrong. Edited in place on every push.
- **Answers `/oc` questions** on any issue or PR, with `file:line` references.
- **Read-only.** The model can read the checkout and nothing else: no edits, no shell, no web, no
  files outside the repo.
- **Any model OpenCode supports.** OpenRouter by default.

Not affiliated with OpenCode or its authors.

## Quick start

1. Add a secret `OPENROUTER_API_KEY` to the repo.
2. Copy [`templates/workflow.yml`](templates/workflow.yml) to `.github/workflows/opencode-review.yml`.
3. Optional: copy [`templates/guide.md`](templates/guide.md) to `.github/opencode-review/guide.md` and
   describe your repo in a few lines. Reviews get faster and catch rule breaks.

```yaml
steps:
  - uses: aloki-alok/opencode-review@COMMIT_SHA # vX.Y.Z
    with:
      model: openrouter/deepseek/deepseek-v4.1-flash
      api-key: ${{ secrets.OPENROUTER_API_KEY }}
```

Pin the action to a commit SHA. Dependabot's `github-actions` updates move the pin for you.

## What it posts

A review comment looks like this:

> Changes needed: 1 thing.
>
> 1. add() subtracts instead of adding (`app/calc.py:2`). Restore `return a + b`.
>
> <sub>OpenCode review of c22bd6e6f, advisory. Reply if a finding is wrong.</sub>

At most 5 findings, under 150 words, no praise. If the review could not finish, the comment says
so and why. It never says "Nothing blocking" for a run that failed.

## Commands

Comment on an issue or a PR:

| Comment | Does |
|---|---|
| `/oc <question>` | Answers in the thread. On a PR it reads the PR's code and diff. |
| `/oc review` | On a PR, runs the review again and updates the review comment. |

Only repo owners, members and collaborators can use commands. Bots and fork PRs are ignored.

## Inputs

| Input | Default | What it does |
|---|---|---|
| `model` | required | OpenCode model as `provider/model`. |
| `api-key` | required | Key for the model's provider. |
| `github-token` | `github.token` | Reads the PR and posts comments. |
| `trigger` | `/oc` | Command word. Change the `if:` in the workflow too. |
| `guide-path` | `.github/opencode-review/guide.md` | Repo guide added to every prompt, read from the base branch. |
| `max-findings` | `5` | Most findings in the comment. |
| `review-budget` | `auto` | `auto` sizes the review to the change: 90 s up to 20 changed code lines, 180 s up to 300, else 240 s. Or `turns:seconds`. |
| `ask-budget` | `16:240` | `turns:seconds` for an answer. |
| `turn-p90` | `18` | Seconds per model turn at p90. Turns are set so they fit the time. Raise it for a slower model. |
| `allowed-associations` | `OWNER,MEMBER,COLLABORATOR` | Who may use commands. |
| `allow-public-self-hosted` | `false` | See [SECURITY.md](SECURITY.md). |
| `opencode-version` | `1.19.3` | OpenCode version to install. |
| `opencode-path` | | Use an installed `opencode` instead. |

## Runners

Needs `python3` (3.9 or later), `git` and, unless you set `opencode-path`, `npm`. GitHub-hosted
Ubuntu runners have all three. No `gh` CLI is needed.

On a self-hosted runner, give reviews their own label so they don't queue behind builds. All
OpenCode state goes to a fresh folder per job, so jobs can run side by side and a read-only home
directory is fine.

## When a review runs out of time

Each pass has a time limit. At the limit OpenCode is stopped and asked, in the same session, for
the findings it has so far. The comment then says it stopped at the time limit. Work is not lost.

## Measuring changes

[`bench/`](bench) replays real bug-introducing PRs from a repo's history, several times each, and
reports the catch rate, false alarms, time p50 and p90, and the spread across runs. Use it before
changing a prompt, a budget or a model. See [bench/README.md](bench/README.md).

## Security

See [SECURITY.md](SECURITY.md). In short: the model only reads, the action's code and prompts never
come from the PR, and fork PRs never get your key.

## License

MIT
