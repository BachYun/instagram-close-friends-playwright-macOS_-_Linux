# Changelog

## 0.1.0b1 — Initial repository beta, 2026-10-15

First repository-ready distribution, derived from the supplied no-reload development
helper. This is not a claim that the release was tested live against Instagram.

### Preserved

- User-managed login and loopback CDP attachment.
- No automatic reloads/theme changes or retries of failed selections.
- CSV snapshot import, append-only progress history and historical status reports.
- Pending selection intent before clicking and separate manual-refresh audits.

### Refined

- Configurable private data directory outside the repository by default.
- Generic account name with workspace binding and explicit account-specific prompts.
- Nearest supported clickable-row discovery instead of fixed five-parent XPath depth.
- Strict malformed-history handling, unknown-state hold and non-destructive preview errors.
- Loopback endpoint validation, file symlink refusal, per-data-folder and per-port locks.
- Bounded scans and click attempts, finite pacing validation and filtered audit pagination.
- Import preview/confirmation, archive size/member limits and newer profile-link support.
- Synthetic tests, local DOM fixture tests, CI configuration and public-file/secret checks.
- Migration, security, troubleshooting and GitHub publication documentation.

### Known limits

English-language observed DOM only; username-based snapshots can become stale. Manual
account confirmation is not automatic identity detection. A manual-refresh audit observes
UI state at a point in time, not permanent membership. Platform restrictions remain possible.
