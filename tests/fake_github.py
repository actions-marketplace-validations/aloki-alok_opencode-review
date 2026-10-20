"""In-memory GitHub REST API: just the routes the action uses, plus the OpenRouter key check."""
import json
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeGitHub:
    def __init__(self, repo, good_key, git_dir=None):
        self.git_dir = git_dir
        self.repo = repo
        self.good_key = good_key
        self.pulls = {}
        self.issues = {}
        self.comments = []  # issue comments: {'id', 'issue', 'body', 'user'}
        self.replies = []  # review comment replies
        self.reactions = []
        self.writes = []  # (method, path) of every write
        self.lock = threading.Lock()
        self.next_id = 1000
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()

    def comments_on(self, number):
        return [c for c in self.comments if c['issue'] == number]

    def _handler(gh):
        prefix = f'/repos/{gh.repo}'

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, body=None):
                data = json.dumps(body).encode() if body is not None else b''
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def body(self):
                n = int(self.headers.get('Content-Length') or 0)
                return json.loads(self.rfile.read(n) or b'{}')

            def do_GET(self):
                u = urlparse(self.path)
                if u.path == '/openrouter/key':
                    ok = self.headers.get('Authorization') == f'Bearer {gh.good_key}'
                    return self.send(200 if ok else 401, {'data': {}} if ok else {'error': {'message': 'User not found'}})
                if self.headers.get('Authorization') != 'Bearer ghs_token':
                    return self.send(401, {'message': 'Bad credentials'})
                p = u.path[len(prefix):]
                if m := re.fullmatch(r'/pulls/(\d+)', p):
                    return self.send(200, gh.pulls[int(m[1])])
                if m := re.fullmatch(r'/compare/([0-9a-f]+)\.\.\.([0-9a-f]+)', p):
                    mb = subprocess.run(['git', '-C', gh.git_dir, 'merge-base', m[1], m[2]],
                                        capture_output=True, text=True, check=True).stdout.strip()
                    return self.send(200, {'merge_base_commit': {'sha': mb}})
                if m := re.fullmatch(r'/issues/(\d+)', p):
                    return self.send(200, gh.issues[int(m[1])])
                if m := re.fullmatch(r'/issues/(\d+)/comments', p):
                    q = parse_qs(u.query)
                    per, page = int(q.get('per_page', ['30'])[0]), int(q.get('page', ['1'])[0])
                    rows = gh.comments_on(int(m[1]))[(page - 1) * per:page * per]
                    return self.send(200, [{k: c[k] for k in ('id', 'body', 'user')} for c in rows])
                self.send(404, {'message': 'Not Found'})

            def write(self, method):
                p = urlparse(self.path).path[len(prefix):]
                body = self.body()
                with gh.lock:
                    gh.writes.append((method, p))
                    gh.next_id += 1
                    new_id = gh.next_id
                bot = {'login': 'github-actions[bot]', 'type': 'Bot'}
                if method == 'POST' and (m := re.fullmatch(r'/issues/(\d+)/comments', p)):
                    gh.comments.append({'id': new_id, 'issue': int(m[1]), 'body': body['body'], 'user': bot})
                    return self.send(201, {'id': new_id})
                if method == 'PATCH' and (m := re.fullmatch(r'/issues/comments/(\d+)', p)):
                    c = next(c for c in gh.comments if c['id'] == int(m[1]))
                    c['body'] = body['body']
                    return self.send(200, {'id': c['id']})
                if method == 'POST' and (m := re.fullmatch(r'/(issues|pulls)/comments/(\d+)/reactions', p)):
                    gh.reactions.append((m[1], int(m[2]), body['content']))
                    return self.send(201, {})
                if method == 'POST' and (m := re.fullmatch(r'/pulls/(\d+)/comments/(\d+)/replies', p)):
                    gh.replies.append({'pr': int(m[1]), 'to': int(m[2]), 'body': body['body']})
                    return self.send(201, {'id': new_id})
                self.send(404, {'message': 'Not Found'})

            def do_POST(self):
                self.write('POST')

            def do_PATCH(self):
                self.write('PATCH')

        return H
