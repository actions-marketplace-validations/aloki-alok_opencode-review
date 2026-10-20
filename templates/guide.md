# Repo guide

Copy to `.github/opencode-review/guide.md` and fill in each part in a few lines. The reviewer reads it
before every review and every answer, so it does not spend turns finding its way. Keep it under
60 lines. Edits take effect once merged: a PR can't change the guide its own review uses.

## What this is

One or two sentences: what the product does and who uses it.

## Layout

- `path/`: what lives there.
- `path/`: what lives there.

## Rules a reviewer should check

- A rule that, when broken, causes a real bug. Example: "Every query filters by `org_id`."
- Another. Skip style rules: the reviewer is told not to report style.

## Words

- `Term`: what it means here, if it differs from the usual meaning.
