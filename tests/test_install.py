from helpers import src  # noqa: F401  (puts src/ on the path)

# isort: split

import unittest

from install import InstallError, package


class PackageTest(unittest.TestCase):
    def test_platform_packages(self):
        self.assertEqual(package('Linux', 'x86_64', musl=False), 'opencode-linux-x64')
        self.assertEqual(package('Linux', 'aarch64', musl=False), 'opencode-linux-arm64')
        self.assertEqual(package('Linux', 'x86_64', musl=True), 'opencode-linux-x64-musl')
        self.assertEqual(package('Darwin', 'arm64', musl=False), 'opencode-darwin-arm64')
        self.assertEqual(package('Darwin', 'x86_64', musl=False), 'opencode-darwin-x64')

    def test_glibc_never_gets_the_musl_build(self):
        # The opencode-ai wrapper picked the musl build on glibc Ubuntu 24.04 and failed (EBADPLATFORM).
        self.assertNotIn('musl', package('Linux', 'x86_64', musl=False))

    def test_unsupported_platform_says_what_to_do(self):
        for system, machine in (('Windows', 'AMD64'), ('Linux', 'riscv64'), ('FreeBSD', 'x86_64')):
            with self.assertRaises(InstallError) as e:
                package(system, machine, musl=False)
            self.assertIn('opencode-path', str(e.exception))


if __name__ == '__main__':
    unittest.main()
