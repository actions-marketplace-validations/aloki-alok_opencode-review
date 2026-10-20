"""Install the pinned OpenCode build for this runner."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

SYSTEMS = {'Linux': 'linux', 'Darwin': 'darwin'}
MACHINES = {'x86_64': 'x64', 'amd64': 'x64', 'AMD64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}


class InstallError(Exception):
    pass


def package(system, machine, musl):
    """The npm package holding the OpenCode binary for this platform. Installing it directly skips
    the `opencode-ai` wrapper, whose install script picked the musl build on glibc and failed."""
    if system not in SYSTEMS or machine not in MACHINES:
        raise InstallError(f'no OpenCode build for {system} {machine}. Install OpenCode yourself and '
                           'set the opencode-path input.')
    name = f'opencode-{SYSTEMS[system]}-{MACHINES[machine]}'
    return name + '-musl' if musl and system == 'Linux' else name


def _is_musl():
    if Path('/etc/alpine-release').exists():
        return True
    try:
        r = subprocess.run(['ldd', '--version'], capture_output=True, text=True)
    except OSError:
        return False
    return 'musl' in (r.stdout + r.stderr).lower()  # musl's ldd prints its banner to stderr


def install(version, dest):
    """npm-installs the binary under `dest` (no global install, no root) and returns its path."""
    name = package(platform.system(), platform.machine(), _is_musl())
    binary = Path(dest, 'node_modules', name, 'bin', 'opencode')
    if binary.exists():
        return str(binary)
    r = subprocess.run(['npm', 'install', '--prefix', str(dest), '--no-audit', '--no-fund',
                        '--loglevel=error', f'{name}@{version}'],
                       capture_output=True, text=True, env={**os.environ, 'npm_config_update_notifier': 'false'})
    if r.returncode != 0 or not binary.exists():
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        raise InstallError(f'npm could not install {name}@{version}: {" ".join(tail)}. '
                           'Install OpenCode yourself and set the opencode-path input.')
    return str(binary)
