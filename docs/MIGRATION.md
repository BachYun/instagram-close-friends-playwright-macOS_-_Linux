# Migration from the development helpers

This repository release is `0.1.0b1` (Git tag `v0.1.0-beta`). Its version sequence is
separate from the earlier development helper labelled `3.0-no-reload`.

## Preserve your working installation

Stop older processes. Extract this repository into a NEW folder. Leave the older Chrome
profile, follower CSV and progress CSV where they are. Do not initialize Git in that old
folder, and do not copy the whole folder into this repository.

The new CLI can read the original three-column progress file directly:

```bash
.venv/bin/python close_friends_csv.py --data-dir "$HOME/your-old-project" --status
```

The status operation writes derived reports in that data folder but does not rewrite the
follower CSV or source progress log. Browser modes append new observations. There is no
mandatory migration of those files and no need to re-add historically selected accounts.

Use the same data directory on every run. For convenience:

```bash
export CLOSE_FRIENDS_DATA_DIR="$HOME/your-old-project"
.venv/bin/python close_friends_csv.py --account your_username --limit 1
```

The first browser run binds that data folder to the declared account in a small local JSON
file. This does not determine the actual Chrome account: visually check it yourself.

## Behavioral changes

1. No automatic refresh or theme override. `--no-dark` remains a compatibility no-op.
2. New selections are always pending until a read-only manual-refresh audit succeeds.
3. Uncertain old `stopped` records are held for review, rather than automatically re-clicked.
4. Unknown future log states are also held. Use `--verify-live --username` for one account.
5. Confirmation phrases include the declared account: `ADD 1 TO your_username` and
   `REFRESHED your_username`.
6. Maximum scan is 100 names (20 for audits), maximum attempted additions is 10. An older
   `--limit 685` command is deliberately not accepted. Choose a smaller source range using
   the report's `position` column; completed and held entries may be interspersed.
7. Import previews changes and asks for `IMPORT N` before replacing a follower snapshot.
8. Account data defaults outside the code folder. Running the new script without the right
   `--data-dir` will not find your old CSV automatically; this is deliberate isolation.

## First live check

Start with a known uncertain username from your own CSV:

```bash
.venv/bin/python close_friends_csv.py --account your_username --verify-live --username exact_username
```

Follow the one-refresh checkpoint, then try a single addition only after normal manual
operations and the preview work. New DOM matching removes the fixed five-parent assumption,
but still depends on the observed English-language Bloks controls and needs live validation.
