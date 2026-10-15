# Instagram Close Friends — Playwright helper

A local, user-approved browser helper for comparing a follower CSV with Instagram's
Close Friends interface, making **limited additions**, and recording what was actually
observed. Uses your manually authenticated Chrome session. No passwords in code.

**Release:** `0.1.0b1` / `v0.1.0-beta` · **Python:** 3.12+ · **Platforms:** macOS and Linux

> Experimental and not affiliated with Instagram or Meta. Offline tests do not establish
> live compatibility. The website can change or reject automation. Stop on account
> restrictions, CAPTCHA, verification prompts, or page errors. There is no guaranteed
> safe action rate. This tool does not bypass those restrictions.

## The important distinction

**A checkmark changing on screen is not proof that Instagram saved the change.**

The workflow is: **preview → approve a limited addition → pending → manual refresh →
read-only verification**. The script never automatically reloads the page, switches its
theme, signs in, exports cookies, or deliberately retries a failed selection. There is
no removal mode. It only attempts a click when the exact row is currently unselected.

## Features

- First-column CSV import with optional `username` header, normalization and deduplication.
- Offline import of a complete official follower-export ZIP (JSON or HTML), with a preview,
  typed confirmation, an old-snapshot backup, and new/absent username reports.
- Existing three-column progress logs remain readable and append-only.
- Exact username matching and recognition of the two checkbox icons observed during development.
- Unknown/ambiguous states stop or require review; uncertain clicks are not blindly retried.
- Manual-refresh audits and separate selected, pending and awaiting-verification reports.
- Private data directory, local account-history binding, per-workspace and per-CDP-port locks.
- Loopback-only CDP connection, sanitized error categories and a manifest-based publication check.

## Install

From the repository folder:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python close_friends_csv.py --help
```

Google Chrome must already be installed. You do **not** need to download Playwright's
Chromium to attach to Chrome via CDP. The optional DOM integration tests need Chromium.

An optional package installation exposes the same CLI as `close-friends`:

```bash
.venv/bin/python -m pip install .
.venv/bin/close-friends --version
```

## Keep code and account data separate

The default data folder is `~/.local/share/instagram-close-friends-playwright`, not the
repository. Override it with `--data-dir` or `CLOSE_FRIENDS_DATA_DIR`. Use a separate data
folder for every account. Do not commit any actual account data, even to a private repo.

For a new workspace, place your own CSV at `<data folder>/followers.csv`. The only CSV
shipped here is `examples/followers.example.csv`, which is **synthetic** and must not be
used for live additions. The first column contains usernames without profile URLs.

For an existing installation, keep the original CSV and progress log in their original
folder. Point this version at them rather than copying the old project into this repo:

```bash
.venv/bin/python close_friends_csv.py --data-dir "$HOME/your-existing-data-folder" --status
```

See [migration notes](docs/MIGRATION.md) before replacing older scripts. Stop old processes
first; versions predating the locking feature do not coordinate with this helper.

## Open a dedicated Chrome profile

On macOS:

```bash
bash scripts/launch_chrome_macos.sh
```

An existing dedicated profile can be passed as an absolute path:

```bash
bash scripts/launch_chrome_macos.sh "$HOME/your-existing-data-folder/chrome-profile"
```

Do not run the launcher when your existing dedicated Chrome is already listening on
port 9222; keep that window. Do not point it at your ordinary Chrome profile. Chrome
requires a separate data directory for remote debugging of current releases
([Chrome documentation](https://developer.chrome.com/blog/remote-debugging-port)).

Log in manually on the genuine Instagram website and complete any legitimate 2FA.
Do not share the password or code with this tool. Keep exactly **one** Close Friends tab
open in this Chrome instance. Stop if normal manual use also fails.

On Linux, launch installed Chrome yourself with a dedicated profile and loopback port:

```bash
google-chrome --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="$HOME/.local/share/instagram-close-friends-playwright/chrome-profile" 'https://www.instagram.com/accounts/close_friends/'
```

The Linux executable name may differ. Native Windows is not supported by this release's
locking implementation. Never forward, tunnel, or expose the debugging port to a network.
CDP grants browser control, not just read access.

## Use the helper

The following examples use `your_username`: replace it with your own account username.
Use your private data folder consistently in every command. To avoid repeating the path:

```bash
export CLOSE_FRIENDS_DATA_DIR="$HOME/your-existing-data-folder"
```

### 1. Offline status

```bash
.venv/bin/python close_friends_csv.py --status
```

This reads the local follower snapshot and log, then writes derived reports. It does not
contact Instagram. Counts are historical observations, not a fresh whole-account audit.

### 2. Preview without clicks

```bash
.venv/bin/python close_friends_csv.py --account your_username --start 1 --limit 5
```

Preview searches the website and reads rows; it makes website requests but never clicks
selection controls. Its log entries do not overwrite meaningful prior selection evidence.
The first browser run stores a local account declaration in the data folder. Later use
of a different account name with that same folder is refused.

**Account binding is not automatic login detection.** You must visually confirm the
account in the connected Chrome tab before every run. Do not switch accounts mid-run.

### 3. Approve one test addition

```bash
.venv/bin/python close_friends_csv.py --account your_username --apply --start 1 --limit 20 --max-adds 1
```

After checking the connected account, type `ADD 1 TO your_username` at the prompt.
Recorded selections and unresolved previous clicks are skipped. At most one click is
attempted, and its intent is flushed to disk **before** the click. A successful visual
change is recorded as `selected_pending_verification`, not confirmed saved.

### 4. Verify pending/uncertain selections

```bash
.venv/bin/python close_friends_csv.py --account your_username --verify-pending --limit 20
```

When prompted, refresh the **connected tab once**, wait for a healthy Close Friends page,
and type `REFRESHED your_username`. The script checks that the document changed before
reading selection states. Do not change any selection circles during the audit.

A selected row is recorded as `verified_selected`; an unselected row as `live_unselected`.
An unavailable/ambiguous row remains unresolved. This is still a UI observation at that
moment, not a permanent membership guarantee or an independent server-side API audit.

To inspect one known username instead:

```bash
.venv/bin/python close_friends_csv.py --account your_username --verify-live --username exact_username_from_your_csv
```

### 5. Further limited additions

After reviewing the last batch and ensuring normal Instagram use still works:

```bash
.venv/bin/python close_friends_csv.py --account your_username --apply --start 21 --limit 20 --max-adds 3
```

Use the report's `position` column to choose a range; do not assume the next unconfirmed
user is the next sequential row. `--limit` is the number of source positions scanned,
including skipped rows, **not** the number of additions. `--max-adds` caps click attempts
at 10, and defaults to 3. The maximum scan is 100 names; audits are capped at 20.

`--delay-seconds` defaults to 30, with a minimum of 10. These are software guardrails,
not Instagram-approved limits. No unattended batch loop, automatic retries or schedules
are provided. To stop, use Control+C. Review pending clicks before another run.

### New followers

A higher profile count cannot tell the tool the new usernames. Import a **new complete,
all-time export for the same account**, not just recently added followers:

```bash
.venv/bin/python close_friends_csv.py --import-export "$HOME/Downloads/your-actual-export.zip" --status
```

Review the counts and type the `IMPORT N` phrase displayed. The import reads follower
files only, never extracts arbitrary archive members, preserves the log, and backs up
the old snapshot. It does not identify the owner of an archive for you. Names absent from
an export may reflect renames or export differences, not necessarily unfollows. It does
not remove anyone from Close Friends. Positions may change after import; use `--username`
when checking one specific person.

## Local reports

| File | Meaning |
|---|---|
| `close_friends_progress.csv` | Append-only history; preserve it |
| `close_friends_status.csv` | All snapshot usernames, source positions and latest meaningful status |
| `close_friends_selected.csv` | Historically recorded selected, with time/evidence category |
| `close_friends_pending.csv` | Not currently confirmed in the log |
| `close_friends_awaiting_verification.csv` | Uncertain clicks and errors needing a fresh audit |
| `close_friends_errors.csv` | Error type/category and processing phase |
| `close_friends_new_since_export.csv` | Usernames not in the previous snapshot |
| `close_friends_no_longer_following.csv` | Legacy filename: **absent from the newer export**, not proof of unfollowing |

Full status definitions and queue pagination are in [data and status semantics](docs/STATUSES.md).

## Troubleshooting and limits

A successful run may finish without completing the follower snapshot. Missing users,
previous selections, limits and pending verification all affect what remains. **An exit
code of 0 is not proof all followers were added.** See [troubleshooting](docs/TROUBLESHOOTING.md).

This build supports the observed English-language Close Friends layout, including the
Bloks Search field and `Toggle checkbox` mask icons. Other layouts/locales are not
validated. Username snapshots can go stale or be reassigned. Verify the intended people.

## Development and publication

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q -m 'not browser'
.venv/bin/python scripts/check_publish.py
```

Tests use synthetic data. The optional browser tests use an in-memory page with intercepted
requests, never an Instagram login. GitHub Actions is configured for offline tests only;
do not add Instagram credentials or profiles to CI. See [testing](docs/TESTING.md).

[Publish to GitHub](docs/PUBLISHING.md) describes first upload, privacy review and beta
releases. The manifest checker is limited defense in depth; it is not a complete security
audit and does not inspect Git history. `.gitignore` is not a retroactive eraser.

## License and provenance

GPL-3.0-only. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). This project's development
began by evaluating `tuliosousapro/Instagram-Close-Friends-BOT`; this distribution refines
the supplied no-reload Playwright helper rather than bundling that project's API client.
No endorsement by that author, Instagram, Meta or Playwright is implied.
