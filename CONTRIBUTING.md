# Contributing

Start with a small reproducible change and a synthetic fixture. Do not reproduce against
a live restricted account simply to collect logs. Do not attach real usernames or account
state to a pull request.

Run the offline tests before submitting:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q -m 'not browser'
.venv/bin/python scripts/check_publish.py
```

Run the optional local DOM integration tests as described in docs/TESTING.md when changing
selectors or browser logic. Keep the single-module entry point for compatibility unless
a deliberate migration is documented. Public functions should have useful type annotations
and errors that do not expose raw authentication/network data.

Changes must preserve these invariants: preview does not click; no forced/ambiguous toggle;
intent persists before clicking; a new on-screen selection is not confirmed saved; a failed
or uncertain mutation is not blindly retried; account histories remain separate; no login,
CAPTCHA, proxy or rate-limit bypass features; no automatic reloads or theme changes.

Update the changelog and relevant docs, then add new public paths deliberately to
`PUBLIC_FILES.txt`. The manifest is not a place for fixtures copied from real accounts.
Review the staged diff and applicable licensing. Contributions are proposed under the
repository's GPL-3.0-only license; do not add third-party material with incompatible terms.
