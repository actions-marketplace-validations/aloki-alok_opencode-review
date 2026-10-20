import re
import unittest

from helpers import ROOT


def code_only(yaml):
    lines = []
    for line in yaml.splitlines():
        line = re.sub(r'\s+#.*$', '', line) if not line.lstrip().startswith('#') else ''
        if line.strip():
            lines.append(line.rstrip())
    return lines


class DocsTest(unittest.TestCase):
    def test_readme_workflow_matches_the_template(self):
        # People copy the README's block, the CI lints the template: they must be the same file.
        readme = (ROOT / 'README.md').read_text()
        block = re.search(r'```yaml\n(name: OpenCode review\n.*?)```', readme, re.S)[1]
        self.assertEqual(code_only(block), code_only((ROOT / 'templates/workflow.yml').read_text()))


if __name__ == '__main__':
    unittest.main()
