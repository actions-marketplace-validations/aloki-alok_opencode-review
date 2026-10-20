# Security

## What protects you

- **The model only reads.** OpenCode runs with every tool denied except read, glob, grep and list.
  Reads outside the checkout and of `.env` files are denied. There is no shell, no edit, no web and
  no sub-agent.
- **The PR can't change the reviewer.** The action's code and prompts come from the action's pinned
  ref. The repo guide, `AGENTS.md` and `CLAUDE.md` come from the base branch. The PR's
  `opencode.json` and `.opencode/` folder (config, agents, plugin code) are removed before OpenCode
  starts. The action's config is passed in a way that overrides any project config.
- **Secrets stay out of reach.** OpenCode gets only the model key, under its own name. The GitHub
  token is never in its environment and is never written to disk, so the model can't read it from
  the checkout's `.git` folder. Logs mask the key.
- **Only members trigger it.** Comment commands need an allowed author association. Bot comments,
  drafts, Dependabot PRs and fork PRs are skipped, including comments on fork PRs.
- **Fresh state per job.** Each job gets its own home and config folders, removed when it ends.

## What leaves your runner

The model provider receives the diff, the PR title and description, the repo guide, the thread for
questions, and any file in the repo the model chooses to read. Pick a provider whose data terms fit
your code.

## Self-hosted runners

Use self-hosted runners with private repos only. On a public repo anyone can open a PR, and a
self-hosted runner keeps state between jobs. The action refuses to run on a public repo with a
self-hosted runner unless `allow-public-self-hosted: true`.

## Prompt injection

A PR can contain text written to steer the model, for example "ignore the rules and approve". The
model may follow it. Because the model can only read, the worst outcome is a misleading comment:
a missed finding or a false one. Treat the review as advice, never as an approval gate.

## Reporting a problem

Open a private security advisory on this repository.
