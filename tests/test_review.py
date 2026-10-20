from helpers import src  # noqa: F401  (puts src/ on the path)

# isort: split

import os
import tempfile
import unittest
from pathlib import Path

from review import sanitize


class SanitizeTest(unittest.TestCase):
    def test_links_out_of_the_checkout_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            code = tmp / 'code'
            (code / 'app').mkdir(parents=True)
            (tmp / 'secret.txt').write_text('s')
            (code / 'app' / 'real.py').write_text('x = 1\n')
            os.symlink(tmp / 'secret.txt', code / 'abs')
            os.symlink('../secret.txt', code / 'rel')
            os.symlink('../..', code / 'app' / 'updir')
            os.symlink('/proc/self/environ', code / 'environ')
            os.symlink('real.py', code / 'app' / 'alias.py')  # stays inside: harmless
            sanitize(code, None)
            left = sorted(str(p.relative_to(code)) for p in code.rglob('*'))
            self.assertEqual(left, ['app', 'app/alias.py', 'app/real.py'])


if __name__ == '__main__':
    unittest.main()
