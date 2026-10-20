import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import src  # noqa: F401
from diff import build


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True, text=True).stdout.strip()


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, 'init', '-q', '-b', 'main')
        git(self.repo, 'config', 'user.email', 't@t')
        git(self.repo, 'config', 'user.name', 't')
        self.write('app/calc.py', 'def add(a, b):\n    x = 1\n    y = 2\n    z = 3\n    return a + b\n')
        self.write('README.md', 'hello\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'base')
        self.base = git(self.repo, 'rev-parse', 'HEAD')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        p = Path(self.repo, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self):
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'change')
        return git(self.repo, 'rev-parse', 'HEAD')

    def test_code_shows_whole_function(self):
        self.write('app/calc.py', 'def add(a, b):\n    x = 1\n    y = 2\n    z = 3\n    return a - b\n')
        patch, changed = build(self.repo, self.base, self.commit())
        self.assertIn(' def add(a, b):', patch)  # 4 lines above the change: outside default context
        self.assertIn('+    return a - b', patch)
        self.assertEqual(changed, 2)

    def test_lockfiles_and_translations_are_skipped(self):
        self.write('app/calc.py', 'def add(a, b):\n    x = 1\n    y = 2\n    z = 3\n    return a - b\n')
        for name in ('package-lock.json', 'web/package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
                     'uv.lock', 'Cargo.lock', 'go.sum', 'i18n/fr.po', 'i18n/app.pot', 'static/app.min.js'):
            self.write(name, 'generated\n' * 50)
        patch, changed = build(self.repo, self.base, self.commit())
        self.assertNotIn('generated', patch)
        self.assertIn('app/calc.py', patch)
        self.assertEqual(changed, 2)

    def test_code_at_the_repo_root_counts(self):
        self.write('setup.py', 'x = 1\n')
        patch, changed = build(self.repo, self.base, self.commit())
        self.assertIn('+x = 1', patch)
        self.assertEqual(changed, 1)

    def test_non_code_is_in_the_patch_but_not_counted(self):
        self.write('README.md', 'hello\nworld\n')
        patch, changed = build(self.repo, self.base, self.commit())
        self.assertIn('+world', patch)
        self.assertEqual(changed, 0)


if __name__ == '__main__':
    unittest.main()
