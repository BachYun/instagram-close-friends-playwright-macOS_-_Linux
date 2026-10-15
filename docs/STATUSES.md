# Data, statuses and queues

`followers.csv` is a snapshot, not a live follower service. The parser reads its first
column, accepts an optional `username` or `usernames` header, strips an initial `@`,
lowercases and deduplicates. Invalid nonempty usernames cause an error. Keep separate
snapshots and history for separate accounts.

`close_friends_progress.csv` retains the original exact columns:

```text
timestamp,username,result
```

New timestamps include a local UTC offset. Existing naive timestamps remain unchanged.
Events are interpreted in **file order**, not sorted by timestamp. A later meaningful
negative/uncertain observation supersedes an old selected result. Preview events do not
supersede meaningful evidence. Never manually count log rows as distinct people.

| Result in history | Meaning | Addition behavior |
|---|---|---|
| `confirmed_selected` | Legacy script reported selected after its automatic refresh | Skip; historical only |
| `already_selected`, `live_selected` | Legacy on-screen selected observation | Skip; weaker evidence |
| `verified_selected` | Current audit saw selected after a user-performed new document load | Skip; observation at that time |
| `live_unselected` | Audit saw unselected after manual refresh | Eligible for an explicitly approved addition |
| `selection_attempted_pending_verification` | Intent persisted before a click | Held for audit, even after a crash |
| `selected_pending_verification` | Selected on screen, not verified saved | Held for audit |
| `stopped_after_click`, `verification_failed` | A potentially changed state needs review | Held for audit |
| `verification_unresolved` | Audit could not resolve the exact row/state | Held for review |
| `stopped` | Old log did not record whether a click happened | Conservatively held for audit |
| `stopped_before_click` | New run stopped before a mutation | No new selection claimed; inspect error before any later run |
| `not_found_or_ambiguous` | No unique matching row; not proof of deletion or unselected status | Can be checked later; do not guess similar names |
| `preview_only`, `preview_not_found_or_ambiguous`, `preview_error` | Preview diagnostics | Do not change meaningful selection evidence |
| Unrecognized future result | Unknown semantics | Requires explicit review; not clicked |

A `never_checked` report means no meaningful non-preview record exists. It does not mean
a live Instagram request has never been made for that username.

Pending includes never-checked names, unresolved searches, negative observations and
uncertain selections. Awaiting verification is a subset; the two counts must not be added
together. Selected reports mix historical evidence categories and retain their timestamps.

## Positions and pagination

For preview, `--apply`, and ordinary `--verify-live`, `--start` is the 1-based position in
the **current source CSV**, and `--limit` is the number of source positions to scan.
Previously selected or pending users still consume positions in an addition range, but
not the click budget. `--username` chooses one exact name from that CSV instead.

`--verify-pending` has a filtered queue of uncertain/pending entries. Its `--start` and
`--limit` refer to this queue. After a successful audit, resolved entries leave the queue;
start at 1 again to process the next pending entries. If the first entries stay unresolved,
use `--start` to inspect later queue positions, or `--verify-live --username` for one name.

This command lists the current pending queue without making website requests:

```bash
.venv/bin/python close_friends_csv.py --status
```

Open `close_friends_awaiting_verification.csv` in the private data folder to see its order.
Do not delete or change statuses just to force re-clicks.

## Snapshot replacement

Only complete follower exports for the same account should replace a snapshot. Import
shows added/absent counts and requires confirmation. Old history is kept even when an
account is absent from the newer export; reports only cover names in the current snapshot.
Changing usernames/reassignment cannot be reliably reconciled without stable identifiers.
The helper does not attempt that reconciliation and does not remove Close Friends.
