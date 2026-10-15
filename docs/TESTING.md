# Tests and validation scope

## Local build result — 2026-10-15

**82 tests passed**, including two local Chromium DOM-fixture cases. Environment:

- Linux x86_64 build container; Python 3.13.5.
- Playwright 1.57.0; pytest 9.0.2.
- Locally installed `/usr/bin/chromium`, used only for synthetic DOM fixtures.

The actual result was produced with:

```bash
CF_RUN_BROWSER_TESTS=1 CF_TEST_CHROMIUM=/usr/bin/chromium python -m pytest -q
```

These tests exercise offline data import, legacy progress compatibility, pending/verified
state separation, account binding, confirmation gates, interrupted clicks, error stops,
locks, endpoint validation, CSV report escaping and publication checks. Browser cases
model the supplied interface with different nesting depths, duplicate exact usernames,
the search field and icon state transition. Browser page requests are intercepted or
aborted; no real Instagram authentication, followers, or account changes are used by the
public test suite.

**Not established by these tests:** live Instagram compatibility, successful additions
for every account, an approved action rate, permanent saved membership, absence of all
possible security issues, or successful execution of this project's CI on GitHub.

The configured CI matrix targets Python 3.12/3.13 on macOS/Linux, with a separate local
DOM job. Those GitHub-hosted jobs will run after publication; the matrix was not run on
GitHub during packaging. Dependencies/browser installation involves downloads, whereas
the test cases themselves use synthetic/local data.

## Run the unit suite

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q -m 'not browser'
```

This currently runs 80 tests without launching Chrome or accessing Instagram. Running
`pytest -q` without the browser-test environment variable skips the two DOM cases.

## Optional browser fixture tests

Install test Chromium once (not necessary for using CDP with your existing Chrome):

```bash
.venv/bin/python -m playwright install chromium
CF_RUN_BROWSER_TESTS=1 .venv/bin/python -m pytest -q -m browser
```

Or provide an explicitly chosen local Chromium executable with `CF_TEST_CHROMIUM`.
Only the fixture test launches a new headless browser; the application attaches to the
user-managed visible dedicated Chrome instance and never launches/authenticates it itself.

## Publication check

Before Git initialization, inspect the public working files:

```bash
.venv/bin/python scripts/check_publish.py
```

After initialization, `--stage` stages only the manifest paths and inspects the Git index;
`--staged`/`--tracked` inspect the existing index. Tests verify that this reads staged bytes,
not changed working-tree substitutes. It is a limited check and cannot replace human
review or remove a secret from Git history.

## Live validation before a public reliability claim

Use only an account you are authorized to manage and a currently healthy interface.
Record the actual environment and date, then manually validate a preview, one approved
addition, a separate manual-refresh audit, already-selected behavior, and a normal stop /
resume. Stop on any challenge/restriction. Do not claim a test succeeded merely because
an exit message says the run ended. Do not publish private usernames or logs as test evidence.
