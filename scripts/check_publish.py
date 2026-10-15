#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check public files or the Git index; optional --stage stages only PUBLIC_FILES.txt.

This is defense in depth, NOT an exhaustive secret detector. It does not inspect
Git history and cannot erase a prior leak. Review the staged diff yourself.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
IGNORE_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.ruff_cache',
               '.mypy_cache', '.local', '.cache', 'build', 'dist', '.vscode', '.idea'}
PATTERNS = (
    ('GitHub token-like literal', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})')),
    ('private-key header', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('password assignment', re.compile(r'''(?im)^\s*(?:IG_PASSWORD|PASSWORD)\s*=\s*['"][^'"\r\n]+['"]''')),
    ('session-cookie literal', re.compile(r'''(?i)['"](?:sessionid|csrftoken)['"]\s*:\s*['"][^'"\s]{8,}['"]''')),
)
EXAMPLE = b'username\nexample_follower_one\nexample_follower_two\nexample_follower_three\n'


def public_files(root: Path) -> list[str]:
    entries = (root / 'PUBLIC_FILES.txt').read_text(encoding='utf-8').splitlines()
    if not entries or len(set(entries)) != len(entries):
        raise ValueError('Missing, empty or duplicate public-file manifest.')
    for name in entries:
        p = PurePosixPath(name)
        if not name or p.is_absolute() or '..' in p.parts or str(p) != name:
            raise ValueError('Invalid public-file manifest path.')
    return entries


def inspect_blob(name: str, data: bytes) -> list[str]:
    issues = []
    if len(data) > 1_000_000:
        return [f'{name}: unexpectedly large public file']
    if b'\0' in data:
        return [f'{name}: binary content is not allowed in this source package']
    text = data.decode('utf-8')
    if name.endswith('.csv') and (name != 'examples/followers.example.csv' or data != EXAMPLE):
        issues.append(f'{name}: only the exact synthetic follower example is allowed')
    for label, pattern in PATTERNS:
        if pattern.search(text):
            issues.append(f'{name}: {label} (value withheld)')
    return issues


def inspect_tree(root: Path, names: list[str]) -> list[str]:
    issues = []
    allowed = set(names)
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            issues.append(f'{name}: missing file or symlink')
            continue
        if any((root / Path(*Path(name).parts[:i])).is_symlink()
               for i in range(1, len(Path(name).parts))):
            issues.append(f'{name}: symlinked parent directory')
            continue
        issues.extend(inspect_blob(name, path.read_bytes()))
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if path.name == '.DS_Store' or any(p in IGNORE_DIRS or p.endswith('.egg-info') for p in relative.parts):
            continue
        if path.is_file() and relative.as_posix() not in allowed:
            issues.append(f'{relative}: not in public-file manifest; do not upload it')
    return issues


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def inspect_index(root: Path, names: list[str]) -> list[str]:
    allowed = set(names)
    issues = []
    indexed = set()
    entries = git(root, 'ls-files', '--stage', '-z').split(b'\0')
    for entry in entries:
        if not entry:
            continue
        meta, name_bytes = entry.split(b'\t', 1)
        mode, oid, stage = meta.decode('ascii').split()
        name = name_bytes.decode('utf-8')
        indexed.add(name)
        if name not in allowed:
            issues.append(f'{name}: non-public file in Git index')
            continue
        if mode not in {'100644', '100755'} or stage != '0':
            issues.append(f'{name}: symlink/submodule/conflict is not permitted')
            continue
        issues.extend(inspect_blob(name, git(root, 'cat-file', 'blob', oid)))
    for name in sorted(allowed - indexed):
        issues.append(f'{name}: public file not staged/tracked')
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stage', action='store_true', help='Validate tree, stage manifest files only, then inspect index.')
    mode.add_argument('--staged', action='store_true', help='Read actual staged/index bytes, not working-file copies.')
    mode.add_argument('--tracked', action='store_true', help='Inspect index after checkout, for CI.')
    args = parser.parse_args()
    try:
        names = public_files(ROOT)
        if args.staged or args.tracked:
            issues = inspect_index(ROOT, names)
        else:
            issues = inspect_tree(ROOT, names)
            if not issues and args.stage:
                git(ROOT, 'add', '--', *names)
                issues = inspect_index(ROOT, names)
        if issues:
            print('PUBLISH CHECK FAILED. Do not commit/push yet.')
            print('\n'.join(issues))
            return 1
        print(f'PUBLISH CHECK PASSED: {len(names)} public files checked.')
        print('This is a limited check, not proof of no secrets. Review git diff --cached before publishing.')
        return 0
    except (ValueError, UnicodeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'PUBLISH CHECK ERROR ({type(exc).__name__}). Verify the manifest and run inside the prepared Git repository.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
