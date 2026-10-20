"""The few GitHub REST calls the action makes. Standard library only: runners may not have `gh`."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class GitHub:
    def __init__(self, api_url, repo, token):
        self.base = f'{api_url}/repos/{repo}'
        self.token = token

    def call(self, method, path, body=None):
        req = urllib.request.Request(
            self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None
        )
        req.add_header('Authorization', f'Bearer {self.token}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        return json.loads(data) if data else None

    def pull(self, number):
        return self.call('GET', f'/pulls/{number}')

    def issue(self, number):
        return self.call('GET', f'/issues/{number}')

    def comments(self, number):
        page = 1
        while True:
            rows = self.call('GET', f'/issues/{number}/comments?per_page=100&page={page}')
            yield from rows
            if len(rows) < 100:
                return
            page += 1

    def upsert_comment(self, number, marker, body):
        """One comment per PR, found by its marker and edited in place."""
        mine = next((c for c in self.comments(number) if c['body'].startswith(marker)), None)
        if mine:
            self.call('PATCH', f'/issues/comments/{mine["id"]}', {'body': body})
        else:
            self.call('POST', f'/issues/{number}/comments', {'body': body})

    def react(self, comment_id, kind, content='eyes'):
        self.call(
            'POST',
            f'/{"pulls" if kind == "review" else "issues"}/comments/{comment_id}/reactions',
            {'content': content},
        )

    def reply(self, number, comment_id, kind, body):
        if kind == 'review':
            self.call('POST', f'/pulls/{number}/comments/{comment_id}/replies', {'body': body})
        else:
            self.call('POST', f'/issues/{number}/comments', {'body': body})


def key_status(url, key):
    """HTTP status of the provider's key endpoint, so a dead key is named in the log and the comment."""
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {key}'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0  # unreachable: let OpenCode try and report its own error
