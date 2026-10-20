"""Entry point of the action: route the event, fetch the code, run OpenCode, post the result.
Advisory: it always exits 0, and says in the log and the comment why when it could not finish."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I does not add the script dir

from budget import Budget, find_budget, parse_budget  # noqa: E402
from diff import build  # noqa: E402
from github import GitHub, key_status  # noqa: E402
import install  # noqa: E402
from render import MARKER, Outcome, render  # noqa: E402
from route import Settings, route  # noqa: E402
from runner import Pass, run_pass  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OPENCODE = '1.19.3'  # the version the bench numbers were measured on
ANSWER_MARKER = '<!-- opencode-review:answer -->'
OPENROUTER_KEY_URL = 'https://openrouter.ai/api/v1/key'
VERIFY_SECONDS = 120
# Files in a PR that would change how OpenCode itself runs: config, agents, plugins (code).
OPENCODE_FILES = ('opencode.json', 'opencode.jsonc', '.opencode')
# Instruction files OpenCode loads on its own: taken from the base, so a PR can't rewrite its review.
RULE_FILES = ('AGENTS.md', 'CLAUDE.md')


class Log:
    def __init__(self, secrets):
        self.secrets = [s for s in secrets if s]

    def mask(self, text):
        for s in self.secrets:
            text = text.replace(s, '***')
        return re.sub(r'sk-[A-Za-z0-9_-]{8,}', 'sk-***', text)

    def __call__(self, text):
        print(self.mask(str(text)), flush=True)


def main(env):
    log = Log([env.get('OC_API_KEY'), env.get('OC_GITHUB_TOKEN')])
    try:
        _main(env, log)
    except Exception:  # advisory: a crash must not fail the PR's checks
        log(traceback.format_exc())
    return 0


def _main(env, log):
    key = env.get('OC_API_KEY', '')
    if key:
        print(f'::add-mask::{key}', flush=True)
    else:
        return _skip(env, log, 'no API key (Dependabot and fork PRs get no secrets)')
    event_name = env['GITHUB_EVENT_NAME']
    event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())
    settings = Settings(trigger=env.get('OC_TRIGGER') or '/oc',
                        associations=tuple(a.strip() for a in env.get('OC_ASSOCIATIONS', '').split(',') if a.strip())
                        or Settings.associations,
                        allow_public_self_hosted=env.get('OC_ALLOW_PUBLIC_SELF_HOSTED') == 'true')
    gh = GitHub(env.get('GITHUB_API_URL', 'https://api.github.com'), env['GITHUB_REPOSITORY'], env['OC_GITHUB_TOKEN'])

    pr = event.get('pull_request')
    if event_name == 'issue_comment' and 'pull_request' in event.get('issue', {}):
        words = event['comment']['body'].split(None, 1)
        pr = gh.pull(event['issue']['number']) if words and words[0] == settings.trigger else None
    job = route(event_name, event, pr, settings, env.get('RUNNER_ENVIRONMENT', ''))
    if job.mode == 'skip':
        return _skip(env, log, job.reason)
    log(f'mode: {job.mode}, #{job.number}')
    if job.comment_id:
        gh.react(job.comment_id, job.comment_kind)
    if job.is_pr and event_name != 'pull_request':
        pr = gh.pull(job.number)  # a comment reviews the PR as it is now

    work = Path(tempfile.mkdtemp(prefix='opencode-review-', dir=env.get('RUNNER_TEMP')))
    code = work / 'code'
    try:
        if job.is_pr:
            head, base = pr['head']['sha'], pr['base']['sha']
            merge_base = gh.call('GET', f'/compare/{base}...{head}')['merge_base_commit']['sha']
            _fetch(env, code, [head, base, merge_base], head)
            _sanitize(code, base)
        else:
            head = merge_base = ''
            _fetch(env, code, [f"refs/heads/{event['repository']['default_branch']}"], 'FETCH_HEAD')
            _sanitize(code, None)
        (code / '.review').mkdir()

        failure = ''
        try:
            opencode = env.get('OC_OPENCODE') or install.install(
                env.get('OC_OPENCODE_VERSION') or DEFAULT_OPENCODE, Path(env['RUNNER_TEMP'], 'opencode-review-bin'))
            log(f'opencode: {opencode} ({_version(opencode, work)})')
        except install.InstallError as e:
            failure = f'could not install OpenCode ({e})'
            log(failure)
        failure = failure or _key_failure(env, log, key)
        ctx = dict(env=env, log=log, gh=gh, job=job, code=code, work=work, key=key, opencode=opencode if not failure else '')
        if job.mode == 'review':
            _review(ctx, pr, head, base, merge_base, failure)
        else:
            _ask(ctx, pr, merge_base, head, failure)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _skip(env, log, reason):
    log(f'skip: {reason}')
    _summary(env, f'opencode-review: skipped ({reason})')


def _git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout


def _fetch(env, code, refs, checkout):
    """Depth-1 fetch of exactly the commits needed. The token goes in per command, never into
    .git/config, because the model can read every file in the checkout."""
    url = f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/{env['GITHUB_REPOSITORY']}.git"
    auth = base64.b64encode(f"x-access-token:{env['OC_GITHUB_TOKEN']}".encode()).decode()
    code.mkdir(parents=True)
    _git(code, 'init', '-q')
    subprocess.run(['git', '-C', str(code), '-c', f'http.extraheader=AUTHORIZATION: basic {auth}',
                    'fetch', '-q', '--no-tags', '--depth=1', url, *dict.fromkeys(refs)],
                   check=True, capture_output=True, text=True)
    _git(code, 'checkout', '-q', '--detach', checkout)


def _sanitize(code, base):
    for name in OPENCODE_FILES:
        p = code / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    if base:
        for name in RULE_FILES:
            p = code / name
            try:
                p.write_text(_git(code, 'show', f'{base}:{name}'))
            except subprocess.CalledProcessError:
                p.unlink(missing_ok=True)  # not in the base: the PR added it


def _version(opencode, work):
    home = work / 'version-home'  # OpenCode writes to ~/.config even for --version
    home.mkdir(exist_ok=True)
    try:
        r = subprocess.run([opencode, '--version'], capture_output=True, text=True, timeout=30,
                           env={'PATH': os.environ.get('PATH', ''), 'HOME': str(home)})
        return r.stdout.strip() or 'version unknown'
    except (OSError, subprocess.TimeoutExpired):
        return 'version unknown'


def _key_failure(env, log, key):
    """A reason string if the provider rejects the key, else ''. Only OpenRouter has a key endpoint."""
    if not env['OC_MODEL'].startswith('openrouter/'):
        return ''
    status = key_status(env.get('OC_KEY_CHECK_URL') or OPENROUTER_KEY_URL, key)
    log(f'key check: HTTP {status}')
    return f'the model API key was rejected (HTTP {status})' if status in (401, 403) else ''


def _prompt(name, turns, guide=''):
    text = (ROOT / 'prompts' / name).read_text().replace('{TURNS}', str(turns))
    return text + (f'\n\n# Repo guide\n\n{guide}' if guide.strip() else '')


def _pass(ctx, agent, prompt, budget, json_key):
    env = ctx['env']
    return run_pass(Pass(opencode=ctx['opencode'], cwd=str(ctx['code']),
                         work=str(ctx['work'] / agent), model=env['OC_MODEL'], api_key=ctx['key'],
                         agent=agent, prompt=prompt, budget=budget, json_key=json_key,
                         wrap_seconds=int(env.get('OC_WRAP_SECONDS') or 30)))


def _review(ctx, pr, head, base, merge_base, failure):
    env, log, gh, job, code = ctx['env'], ctx['log'], ctx['gh'], ctx['job'], ctx['code']
    max_findings = int(env.get('OC_MAX_FINDINGS') or 5)
    if failure:
        outcome = Outcome(head, 'failed', None, 'skipped', None, max_findings, failure)
    else:
        patch, changed = build(code, merge_base, head)
        (code / '.review/diff.patch').write_text(patch)
        (code / '.review/pr.md').write_text(f"# {pr['title']}\n\n{pr.get('body') or ''}\n")
        p90 = float(env.get('OC_TURN_P90') or 14)
        budget = parse_budget(env.get('OC_REVIEW_BUDGET') or 'auto') or find_budget(changed, p90)
        log(f'changed code lines: {changed}, find pass: {budget.turns} turns, {budget.seconds} s')
        guide_path = env.get('OC_GUIDE_PATH') or '.github/opencode-review/guide.md'
        try:
            guide = _git(code, 'show', f'{base}:{guide_path}')
        except subprocess.CalledProcessError:
            guide = ''
        log(f"guide: {guide_path} from the base branch ({len(guide)} chars)" if guide else 'guide: none')

        found = _pass(ctx, 'review', _prompt('review.md', budget.turns, guide), budget, 'findings')
        findings = found.result['findings'] if found.result else None
        log(f'find pass: {found.status}, {found.turns} turns, {found.seconds} s, '
            f"{'no JSON' if findings is None else len(findings)} findings")
        find = 'failed' if found.status == 'failed' else found.status
        verify, verdicts = 'skipped', None
        if findings:
            (code / '.review/findings.json').write_text(json.dumps({'findings': findings}, indent=1))
            vb = Budget(max(3, int(VERIFY_SECONDS // p90)), VERIFY_SECONDS)
            checked = _pass(ctx, 'verify', _prompt('verify.md', vb.turns, guide), vb, 'verdicts')
            verdicts = checked.result['verdicts'] if checked.result else None
            verify = 'done' if verdicts is not None else 'failed' if checked.status == 'failed' else 'timeout'
            log(f'verify pass: {verify}, {checked.turns} turns, {checked.seconds} s')
        outcome = Outcome(head, find, findings, verify, verdicts, max_findings, log.mask(found.error))
    body = render(outcome)
    log(body)
    if gh.pull(job.number)['head']['sha'] != head:
        log('not posting: the PR has a newer commit, whose run posts instead')
        return
    gh.upsert_comment(job.number, MARKER, body)
    _summary(env, f'opencode-review: review of {head[:9]}, find {outcome.find}, verify {outcome.verify}, '
                  f"model {env['OC_MODEL']}\n\n{body}")


def _ask(ctx, pr, merge_base, head, failure):
    env, log, gh, job, code = ctx['env'], ctx['log'], ctx['gh'], ctx['job'], ctx['code']
    if failure:
        answer = f'I could not answer: {failure}.'
    else:
        issue = gh.issue(job.number)
        thread = [f"# {issue['title']}\n\n{issue.get('body') or ''}\n\n## Recent comments"]
        recent = [c for c in gh.comments(job.number) if not c['body'].startswith('<!-- opencode-review')][-20:]
        thread += [f"\n**{c['user']['login']}:** {c['body'][:2000]}" for c in recent]
        (code / '.review/thread.md').write_text('\n'.join(thread) + '\n')
        (code / '.review/question.md').write_text(job.question + '\n')
        if job.is_pr:
            (code / '.review/diff.patch').write_text(build(code, merge_base, head)[0])
        budget = parse_budget(env.get('OC_ASK_BUDGET') or '16:240')
        r = _pass(ctx, 'ask', _prompt('ask.md', budget.turns), budget, None)
        log(f'ask pass: {r.status}, {r.turns} turns, {r.seconds} s')
        answer = r.answer or 'I could not finish an answer in time. Try a narrower question.'
    body = f'{ANSWER_MARKER}\n{log.mask(answer)}\n\n<sub>OpenCode answer, read-only, advisory.</sub>'
    gh.reply(job.number, job.comment_id, job.comment_kind, body)
    _summary(env, f"opencode-review: answered on #{job.number}, model {env['OC_MODEL']}")


def _summary(env, text):
    path = env.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    sys.exit(main(os.environ))
