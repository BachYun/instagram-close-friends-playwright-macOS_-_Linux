# Troubleshooting

## `No such file or directory` after copying an update

Check the actual download name and folder first. Do not continue with later commands when
copy/extraction failed: the old script will still be installed. Run `--version` and `--help`
on the exact file you intend to execute. This package reports `Close Friends Helper 0.1.0b1`.

## `unrecognized arguments`

Usually the wrong/old file or environment is running. From this repository use the explicit
`.venv/bin/python close_friends_csv.py --help` command. The old bulk scan length is also no
longer accepted; see MIGRATION.md.

## `zsh: command not found: #`

Some interactive zsh configurations do not treat pasted comment lines as comments. Copy
only command lines, not prose, code fences or the Terminal prompt. Commands in the main
setup instructions do not require pasted `#` comments.

## `EOFError` or a missing confirmation prompt

Execute the saved Python file from an interactive Terminal. Do not feed the program through
`python - <<'PY'`, a pipe, a notebook, or unattended CI: the confirmation needs terminal input.

## Cannot connect to CDP / wrong tab

Keep the dedicated debugging Chrome instance open. Use the same debugging port as the
launcher. Keep exactly one Close Friends tab in it. A normal Chrome window not launched
with remote debugging cannot be taken over by this tool. Do not expose CDP externally.
The helper never automatically reconnects or creates a logged-in browser for you.

## `Something went wrong`, `rate_limited`, HTTP errors or CAPTCHA

The helper stops. Check Instagram manually in the same dedicated browser and in the
normal app. Do not repeatedly restart, switch proxies, discard profiles, or retry a failed
selection to bypass a restriction. No exact waiting time is guaranteed. A generic page
error alone does not identify its cause. If an earlier click may have happened, keep its
pending record and resolve it in a later legitimate audit, not by clicking again.

## The theme changes or a white loading screen appears

This helper never calls `emulate_media` or reloads. Instagram/Chrome may still change their
own loading appearance when you manually refresh or navigate. Old processes or earlier
media overrides may still be active in a shared tab. Stop other tools. Do not change flags
or delete your profile just to conceal automation.

## Search layout changed / no unique exact row

The supported layout has one visible Bloks input with placeholder `Search` and controls
labelled `Toggle checkbox`. The known icons are `circle__outline__24-4x.png` and
`circle-check__filled__24-4x.png`. Other layouts/locales are unverified. Do not replace an
exact match with the first result or force a click. A username can be renamed, unavailable,
missing from search results or ambiguous. None of those cases proves deletion or unselected
membership. Use a current export and review the intended person.

## A run ended but the pending count is not zero

`--limit` counts scanned positions, including skips. `--max-adds` counts attempted clicks,
not verified saved additions. New selections remain in the pending count until a separate
manual-refresh audit records them as selected. Reports also retain unresolved accounts.

## Account folder belongs to a different account

Use a different data folder for the other account. Do not delete the binding or mix logs.
The binding is a user declaration, not automated Chrome login detection. Old unbound logs
must be matched to the correct account manually.

## Malformed progress history

Back up the file privately and inspect the reported row. Never delete it or discard unknown
records to force the script onward. A truncated log may follow an interrupted disk write.
No automated repair that might discard evidence is included.

## Exit codes

- `0`: requested range/report completed or user cancelled additions; not all followers confirmed.
- `1`: configuration, file or connection/setup problem.
- `2`: argument-validation failure, or an early browser/verification stop.
- `130`: user interruption outside the main browser loop. Inside the loop interruption is logged
  conservatively and returns `2`.
