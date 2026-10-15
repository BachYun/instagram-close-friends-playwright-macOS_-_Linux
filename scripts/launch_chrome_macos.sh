#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then
  printf '%s\n' 'This launcher is for macOS only. See README.md for Linux.' >&2
  exit 1
fi
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE="${1:-$HOME/.local/share/instagram-close-friends-playwright/chrome-profile}"
if [[ "$PROFILE" != /* ]]; then
  printf '%s\n' 'Supply an absolute path for the dedicated Chrome profile.' >&2
  exit 1
fi
case "$PROFILE" in
  "$HOME/Library/Application Support/Google/Chrome"*)
    printf '%s\n' 'Refusing the default Chrome profile. Use a dedicated profile.' >&2
    exit 1
    ;;
esac
if [[ ! -x "$CHROME" ]]; then
  printf '%s\n' 'Google Chrome was not found in /Applications.' >&2
  exit 1
fi
if /usr/sbin/lsof -nP -iTCP:9222 -sTCP:LISTEN >/dev/null 2>&1; then
  printf '%s\n' 'Port 9222 is already in use. Keep your existing dedicated Chrome window; do not start another.' >&2
  exit 1
fi
umask 077
mkdir -p "$PROFILE"
printf '%s\n' 'Keep this browser and its profile private. Never expose port 9222 on your network.'
exec "$CHROME" \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  'https://www.instagram.com/accounts/close_friends/'
