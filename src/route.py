"""Decide what one GitHub event asks for: a PR review, an answer to a question, or nothing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    trigger: str = '/oc'
    associations: tuple = ('OWNER', 'MEMBER', 'COLLABORATOR')
    allow_public_self_hosted: bool = False


@dataclass(frozen=True)
class Job:
    mode: str  # review | ask | skip
    reason: str = ''
    number: int = 0
    is_pr: bool = False
    comment_id: int = 0
    comment_kind: str = ''  # issue | review
    question: str = ''


PR_ACTIONS = ('opened', 'synchronize', 'reopened', 'ready_for_review')
COMMENT_EVENTS = {'issue_comment': 'issue', 'pull_request_review_comment': 'review'}


def route(event_name, event, pr, settings, runner_environment):
    """`pr` is the pull request the event is about (fetched for issue comments), or None.
    Every refusal is a skip with a reason, so the job log says why nothing ran."""
    repo = event.get('repository') or {}
    if runner_environment == 'self-hosted' and not repo.get('private', True) and not settings.allow_public_self_hosted:
        return Job('skip', 'public repo on a self-hosted runner (set allow-public-self-hosted to override)')
    if event_name == 'pull_request':
        return _pull_request(event, pr, repo)
    if event_name in COMMENT_EVENTS:
        return _comment(event, pr, repo, settings, COMMENT_EVENTS[event_name])
    return Job('skip', f'event {event_name} is not handled')


def _pull_request(event, pr, repo):
    if event.get('action') not in PR_ACTIONS:
        return Job('skip', f'pull_request action {event.get("action")} is not reviewed')
    if pr.get('draft'):
        return Job('skip', 'draft PR')
    if pr['user']['login'] == 'dependabot[bot]':
        return Job('skip', 'Dependabot PR (no secrets)')
    if not _same_repo(pr, repo):
        return Job('skip', 'PR from a fork')
    return Job('review', number=pr['number'], is_pr=True)


def _comment(event, pr, repo, settings, kind):
    c = event['comment']
    words = c['body'].strip().split(None, 1)
    if not words or words[0] != settings.trigger:
        return Job('skip', f'comment does not start with {settings.trigger}')
    question = words[1].strip() if len(words) > 1 else ''
    if not question:
        return Job('skip', 'empty question')
    if c['user'].get('type') == 'Bot':
        return Job('skip', 'comment by a bot')
    if c.get('author_association') not in settings.associations:
        return Job('skip', f'commenter is {c.get("author_association")}, not in {",".join(settings.associations)}')
    if pr is not None and not _same_repo(pr, repo):
        return Job('skip', 'PR from a fork')
    number = pr['number'] if pr is not None else event['issue']['number']
    is_pr = pr is not None
    base = dict(number=number, is_pr=is_pr, comment_id=c['id'], comment_kind=kind)
    if is_pr and question.split(None, 1)[0] == 'review':
        return Job('review', **base)
    return Job('ask', question=question, **base)


def _same_repo(pr, repo):
    head = pr['head'].get('repo')
    return bool(head) and head.get('full_name') == repo.get('full_name')
