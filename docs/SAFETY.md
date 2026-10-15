# Safety boundaries

This is a local automation helper, not an official Instagram integration and not a way to
bypass restrictions. Review Instagram's applicable terms before use. Small batches and
pacing do not guarantee that a platform will permit automation.

## Browser control

CDP exposes control of the dedicated Chrome instance. Bind remote debugging to loopback,
never forward it, and keep unrelated accounts/tabs out of that profile. Other local
software may still reach a loopback port. Close the debugging browser when no longer
needed, keeping the private profile for a later manual launch. Do not copy browser cookies
or authentication state into source code, Git, issue reports or CI.

The helper uses a local account declaration to separate progress histories. It does not
read a private API or cookies to prove the active username. You must manually verify the
correct account before every run and must not switch it while the helper is running.

## What the helper will and will not do

- Default browser mode searches/reads but does not click selection controls.
- Adding requires `--apply` and an account-specific typed confirmation.
- Unknown or ambiguous state is not clicked. No remove operation is implemented.
- Intent is written and flushed before each click. A click is counted even if it fails.
- A changed checkbox stays pending until a separate user-refreshed audit observes it.
- UI health and selected HTTP errors stop the run. Detection is conservative and incomplete;
  a generic page error does not prove a rate limit, and absence of a detected error does not
  prove the account is unrestricted.
- No automatic reload, profile/IP rotation, CAPTCHA solving, automatic login, forced click,
  event-dispatch bypass, direct API request construction or automatic failed-action retry.
- The website itself can issue API requests as a consequence of normal UI interactions.
- A process lock coordinates this release and compatible older helpers. It does not stop
  unrelated tools, manually launched scripts lacking the lock, or your own browser clicks.

## Local storage

Data defaults outside the repository. New runtime files are created under a restrictive
umask; existing files and their history are preserved. Reports are replaced atomically.
Log appends are flushed and fsynced, but a power failure or filesystem error can still
leave a malformed file. Malformed history stops processing rather than silently discarding
records. Keep private backups; never erase the log to make the tool continue.

A report labelled selected is historical evidence, not a live whole-account list or a
permanent promise that a server retained that state.

## Publication

`PUBLIC_FILES.txt` is the intended source manifest. The publish checker stages only these
files and can inspect the actual Git index. It rejects other indexed paths, symlinks,
binaries, a modified synthetic CSV and several obvious credential patterns. It is not a
complete secret scanner, does not assess every possible personal detail, and does not
inspect or rewrite old Git history. Always inspect the staged diff yourself.

Primary references:
- https://playwright.dev/python/docs/auth
- https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp
- https://developer.chrome.com/blog/remote-debugging-port
- https://docs.github.com/en/get-started/git-basics/ignoring-files
