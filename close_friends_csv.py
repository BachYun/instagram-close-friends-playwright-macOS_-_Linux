#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# See NOTICE.md for provenance; this distribution modifies the supplied no-reload helper.
"""Instagram Close Friends helper (beta).

Local CSV tracking and limited, user-approved browser actions. Connects only to
loopback Chrome DevTools Protocol. Login/2FA remain manual. No automatic page
reloads, theme changes, API calls outside the website, or restriction retries.
Selections remain pending until a separate audit after a manual full refresh.

Run --help for commands. See README.md, docs/SAFETY.md and NOTICE.md.
"""

from __future__ import annotations

import argparse
import os
import math
import tempfile
from contextlib import contextmanager
import csv
import json
import re
import shutil
import sys
import time
import zipfile
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Response

VERSION = "0.1.0b1"
PROJECT_NAME = "instagram-close-friends-playwright"
BASE_DIR = Path.home() / ".local" / "share" / PROJECT_NAME
ACCOUNT_PATH = BASE_DIR / ".close_friends_account.json"
CSV_PATH = BASE_DIR / "followers.csv"
PROGRESS_PATH = BASE_DIR / "close_friends_progress.csv"
REPORT_PATH = BASE_DIR / "close_friends_status.csv"
PENDING_PATH = BASE_DIR / "close_friends_pending.csv"
NEW_PATH = BASE_DIR / "close_friends_new_since_export.csv"
REMOVED_PATH = BASE_DIR / "close_friends_no_longer_following.csv"
ERROR_PATH = BASE_DIR / "close_friends_errors.csv"
SELECTED_PATH = BASE_DIR / "close_friends_selected.csv"
AWAITING_PATH = BASE_DIR / "close_friends_awaiting_verification.csv"
LOCK_PATH = BASE_DIR / ".close_friends_run.lock"
PAGE_URL = "https://www.instagram.com/accounts/close_friends/"
CDP_URL = "http://127.0.0.1:9222"

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
FOLLOWER_FILE_RE = re.compile(r"^followers(?:_\d+)?\.(?:json|html)$", re.I)
CONFIRMED_RESULTS = {"confirmed_selected", "already_selected", "live_selected", "verified_selected"}
AWAITING_RESULTS = {
    "selection_attempted_pending_verification", "selected_pending_verification",
    "stopped_after_click", "verification_failed", "verification_unresolved", "stopped",
}
IGNORABLE_RESULTS = {"preview_only", "preview_not_found_or_ambiguous", "preview_error"}
ADDABLE_RESULTS = {None, "live_unselected", "not_found_or_ambiguous", "stopped_before_click"}
MAX_SCAN = 100
MAX_AUDIT = 20
SEARCH_SELECTOR = 'input[placeholder="Search"][class~="wbloks_1"]:visible'
TOGGLE_SELECTOR = '[role="button"][aria-label="Toggle checkbox"]'
ERROR_PAGE_MARKERS = (
    "something went wrong",
    "there's an issue and the page could not be loaded",
    "there’s an issue and the page could not be loaded",
    "couldn't load this page",
)
RESTRICTION_MARKERS = (
    "rate_limited",
    "try again later",
    "too many requests",
    "we restrict certain activity",
    "please wait a few minutes",
    "temporarily blocked",
)


class InstagramUnavailable(RuntimeError):
    """A page or HTTP response is inconsistent with a healthy Instagram session."""


class FollowerHTMLParser(HTMLParser):
    """Extract only usernames from followers_N.html profile links."""

    def __init__(self):
        super().__init__()
        self.usernames = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        username = username_from_href(href)
        if username:
            self.usernames.append(username)


def normalize_username(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip().lstrip("@").lower()
    return name if USERNAME_RE.fullmatch(name) else None


def username_from_href(href: Any) -> str | None:
    if not isinstance(href, str):
        return None
    url = urlsplit(href)
    if url.scheme != "https" or url.netloc.lower() not in {"www.instagram.com", "instagram.com"}:
        return None
    parts = url.path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "_u":
        parts = parts[1:]
    return normalize_username(parts[0]) if len(parts) == 1 else None


def unique_names(values: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(name for raw in values if (name := normalize_username(raw))))


def read_username_csv(path: Path) -> list[str]:
    """Read the first CSV column; reject bad rows instead of silently dropping them."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}. Copy a follower CSV to this data folder, or import an export ZIP.")
    values: list[str] = []
    first_nonempty = True
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for line_number, row in enumerate(csv.reader(fh), 1):
            if not row or not row[0].strip():
                continue
            value = row[0].strip()
            if first_nonempty and value.lower() in {"username", "usernames"}:
                first_nonempty = False
                continue
            first_nonempty = False
            name = normalize_username(value)
            if not name:
                raise ValueError(f"Invalid username at line {line_number} in {path.name}.")
            values.append(name)
    return list(dict.fromkeys(values))


def write_csv(path: Path, columns: Iterable[str] | None, rows: Iterable[Iterable[Any]]) -> None:
    """Atomic replacement of a derived report or explicitly imported snapshot."""
    path = Path(path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8",
                                         dir=path.parent, prefix=".close-friends-", delete=False) as fh:
            temp_path = Path(fh.name)
            writer = csv.writer(fh)
            if columns:
                writer.writerow(columns)
            # Spreadsheet programs must not interpret a free-text report cell as a formula.
            writer.writerows(
                ["'" + cell if isinstance(cell, str) and cell.startswith(("=", "+", "-", "@", "\t", "\r")) else cell
                 for cell in row]
                for row in rows
            )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def read_progress() -> list[dict[str, str]]:
    """Read the existing append-only three-column log; refuse malformed history."""
    if not PROGRESS_PATH.exists() or PROGRESS_PATH.stat().st_size == 0:
        return []
    records: list[dict[str, str]] = []
    with PROGRESS_PATH.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != ["timestamp", "username", "result"]:
            raise ValueError("Progress CSV must have timestamp,username,result headers. Back up and inspect it; do not delete history.")
        for number, row in enumerate(reader, 2):
            name = normalize_username(row.get("username"))
            result = (row.get("result") or "").strip()
            timestamp = (row.get("timestamp") or "").strip()
            if None in row or not name or not result or not timestamp:
                raise ValueError(f"Malformed progress row {number}. No browser actions will run.")
            records.append({"username": name, "result": result, "timestamp": timestamp})
    return records


def latest_results(progress: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    latest = {}
    last_event = {}
    for row in progress:
        name = row["username"]
        last_event[name] = row
        if row["result"] not in IGNORABLE_RESULTS:
            latest[name] = row
    return latest, last_event


def status_for(event: dict[str, str] | None) -> str:
    if not event:
        return "never_checked"
    result = event["result"]
    if result == "confirmed_selected":
        return "confirmed_after_refresh_in_log"
    if result == "verified_selected":
        return "selected_after_manual_refresh_in_log"
    if result in {"already_selected", "live_selected"}:
        return "selected_at_last_check_in_log"
    if result == "live_unselected":
        return "unselected_at_last_check"
    if result in {"selection_attempted_pending_verification", "selected_pending_verification"}:
        return "awaiting_manual_refresh_verification"
    if result == "stopped_before_click":
        return "stopped_before_click"
    if result == "not_found_or_ambiguous":
        return "not_found_or_ambiguous"
    if result in AWAITING_RESULTS:
        return "needs_review_after_error"
    return "needs_review"


def create_reports(names: list[str]) -> dict[str, Any]:
    progress = read_progress()
    latest, last_event = latest_results(progress)
    selected = []
    pending = []
    awaiting = []
    report = []
    counts = Counter()
    for pos, name in enumerate(names, 1):
        row = latest.get(name)
        most_recent = last_event.get(name)
        status = status_for(row)
        verified_in_log = row is not None and row["result"] in CONFIRMED_RESULTS
        counts[status] += 1
        entry = [
            name, pos, status,
            row["result"] if row else "",
            row["timestamp"] if row else "",
            most_recent["result"] if most_recent else "",
        ]
        report.append(entry)
        if row is not None and row["result"] in AWAITING_RESULTS:
            awaiting.append([name, status, row["timestamp"]])
        if verified_in_log:
            selected.append([name, status, row["timestamp"]])
        else:
            pending.append([name, status, row["timestamp"] if row else ""])

    write_csv(REPORT_PATH,
              ["username", "position", "status", "last_meaningful_result", "recorded_at", "last_log_event"],
              report)
    write_csv(PENDING_PATH, ["username", "status", "last_check_time"], pending)
    write_csv(SELECTED_PATH, ["username", "status", "recorded_at"], selected)
    write_csv(AWAITING_PATH, ["username", "status", "recorded_at"], awaiting)

    print("\nCLOSE FRIENDS — TRACKING SNAPSHOT")
    print("-" * 48)
    print(f"Followers in current CSV: {len(names)}")
    print(f"Historically marked selected: {len(selected)}")
    print(f"Not confirmed in the log: {len(pending)}")
    print(f"Awaiting verification/review (included above): {len(awaiting)}")
    for status in ["confirmed_after_refresh_in_log", "selected_after_manual_refresh_in_log", "selected_at_last_check_in_log",
                   "awaiting_manual_refresh_verification",
                   "never_checked", "unselected_at_last_check", "not_found_or_ambiguous",
                   "needs_review_after_error", "stopped_before_click", "needs_review"]:
        if counts[status]:
            print(f"  {status}: {counts[status]}")
    print(f"\nFull tracking file: {REPORT_PATH.resolve()}")
    print(f"Unconfirmed usernames: {PENDING_PATH.resolve()}")
    print(f"Recorded selected usernames: {SELECTED_PATH.resolve()}")
    print(f"Awaiting verification: {AWAITING_PATH.resolve()}")
    print("These are historical script observations, not a guaranteed live Instagram snapshot.")
    return {"selected": set(selected_row[0] for selected_row in selected),
            "pending": set(pending_row[0] for pending_row in pending),
            "counts": counts, "awaiting": set(row[0] for row in awaiting)}


def json_usernames(value: Any) -> list[str]:
    collected = []

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            if "string_list_data" in obj and isinstance(obj["string_list_data"], list):
                for item in obj["string_list_data"]:
                    if isinstance(item, dict):
                        name = normalize_username(item.get("value")) or username_from_href(item.get("href"))
                        if name:
                            collected.append(name)
            for key, nested in obj.items():
                if key != "string_list_data" and isinstance(nested, (dict, list)):
                    walk(nested)

    walk(value)
    return collected


def import_export(archive: str | Path) -> list[str]:
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise FileNotFoundError(f"Instagram export ZIP not found: {archive}")
    previous = read_username_csv(CSV_PATH) if CSV_PATH.exists() else []
    with zipfile.ZipFile(archive) as zf:
        entries = [entry for entry in zf.infolist()
                   if FOLLOWER_FILE_RE.fullmatch(Path(entry.filename).name)
                   and "followers_and_following/" in entry.filename.replace("\\", "/")
                   and not entry.is_dir()]
        if not entries:
            raise ValueError("No followers_N.html or followers_N.json found in this ZIP. Export 'Followers and following'.")
        if len(entries) > 1000:
            raise ValueError("Too many follower files. No data changed.")
        combined = []
        total_size = 0
        for entry in sorted(entries, key=lambda item: item.filename):
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Refusing symlinked follower archive member.")
            if entry.file_size > 25_000_000:
                raise ValueError("Follower file is unexpectedly large; stopping for safety.")
            total_size += entry.file_size
            if total_size > 60_000_000:
                raise ValueError("Too much follower data in ZIP; stopping for safety.")
            data = zf.read(entry)
            if entry.filename.lower().endswith(".html"):
                parser = FollowerHTMLParser()
                parser.feed(data.decode("utf-8-sig", errors="replace"))
                combined.extend(parser.usernames)
            else:
                combined.extend(json_usernames(json.loads(data.decode("utf-8-sig"))))
    updated = unique_names(combined)
    if not updated:
        raise ValueError("No valid usernames parsed. Existing followers.csv has NOT been changed.")
    before = set(previous)
    after = set(updated)
    new_names = [u for u in updated if u not in before]
    no_longer = [u for u in previous if u not in after]
    print(f"\nIMPORT PREVIEW: {len(updated)} usernames; {len(new_names)} new; {len(no_longer)} absent.")
    print("Only import a complete, all-time follower snapshot for this same account.")
    print("Absent does not prove an unfollow. Account renames/export differences may be involved.")
    if terminal_prompt(f"Type IMPORT {len(updated)} to replace the snapshot: ") != f"IMPORT {len(updated)}":
        raise ValueError("Import cancelled. Existing follower list and history were not changed.")
    if CSV_PATH.exists():
        backup = BASE_DIR / Path(f"followers.before-import-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.csv")
        shutil.copy2(CSV_PATH, backup)
        print(f"Old follower CSV backed up: {backup}")
    write_csv(CSV_PATH, None, [[u] for u in updated])
    write_csv(NEW_PATH, ["username"], [[u] for u in new_names])
    write_csv(REMOVED_PATH, ["username"], [[u] for u in no_longer])
    print(f"Imported follower snapshot: {len(updated)} names")
    print(f"New since previous CSV: {len(new_names)} names -> {NEW_PATH}")
    print(f"Absent from updated snapshot: {len(no_longer)} names -> {REMOVED_PATH}")
    print("Existing Close Friends progress log was NOT modified.")
    return updated


def log_result(username: str, result: str) -> None:
    is_new = not PROGRESS_PATH.exists() or PROGRESS_PATH.stat().st_size == 0
    with PROGRESS_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(["timestamp", "username", "result"])
        writer.writerow([datetime.now().astimezone().isoformat(), username, result])
        fh.flush()
        os.fsync(fh.fileno())


def error_summary(exc: BaseException) -> str:
    """Only our controlled page errors are recorded verbatim; never dump API payloads."""
    if isinstance(exc, InstagramUnavailable):
        text = str(exc).splitlines()[0] if str(exc) else "Page unavailable."
        text = re.sub(r"https?://\S+", "[URL omitted]", text)
        return f"{type(exc).__name__}: {text[:180]}"
    if isinstance(exc, KeyboardInterrupt):
        return "KeyboardInterrupt: stopped by user."
    return f"{type(exc).__name__}: operation did not complete; inspect the browser manually."


def log_error(username: str, phase: str, exc: BaseException) -> str:
    is_new = not ERROR_PATH.exists() or ERROR_PATH.stat().st_size == 0
    summary = error_summary(exc)
    with ERROR_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(["timestamp", "username", "phase", "error"])
        writer.writerow([datetime.now().astimezone().isoformat(), username, phase, summary])
        fh.flush()
        os.fsync(fh.fileno())
    return summary


def is_close_friends_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname == "www.instagram.com"
                and url.port in (None, 443) and url.username is None and url.password is None
                and url.path.rstrip("/") == "/accounts/close_friends")
    except ValueError:
        return False


def current_page_health(page: Page, rejected: list[str]) -> None:
    if rejected:
        raise InstagramUnavailable("Instagram refused an HTTP request: " + rejected[-1])
    if page.is_closed():
        raise InstagramUnavailable("Chrome tab was closed.")
    if not is_close_friends_url(page.url):
        raise InstagramUnavailable("Instagram left Close Friends. Check the account/page manually; no login retries.")
    try:
        text = page.locator("body").inner_text(timeout=4000).lower()
    except Exception as exc:
        raise InstagramUnavailable(f"Could not inspect Instagram page: {type(exc).__name__}") from exc
    if any(marker in text for marker in ERROR_PAGE_MARKERS):
        raise InstagramUnavailable("Instagram displayed 'Something went wrong'. Stopping; no automatic reload.")
    if any(marker in text for marker in RESTRICTION_MARKERS):
        raise InstagramUnavailable("Instagram displayed an activity restriction. Stopping without retrying.")


def find_row(page: Page, username: str, rejected: list[str]) -> Locator | None:
    """Use the observed Bloks search, then the nearest exact, clickable account row.

    DOM-specific and fail-closed: a changed layout or ambiguous match is not clicked.
    Search still makes normal website requests and is not an offline operation.
    """
    from playwright.sync_api import TimeoutError as PWTimeout

    current_page_health(page, rejected)
    searches = page.locator(SEARCH_SELECTOR)
    try:
        searches.first.wait_for(state="visible", timeout=12000)
    except PWTimeout as exc:
        current_page_health(page, rejected)
        raise InstagramUnavailable("Close Friends search did not load or the known layout changed.") from exc
    if searches.count() != 1:
        raise InstagramUnavailable("Cannot uniquely identify the Close Friends search. No guessing.")
    search = searches.first
    search.fill(username)
    guarded_wait(page, rejected, 1)
    matches = page.get_by_text(username, exact=True)
    try:
        matches.first.wait_for(state="visible", timeout=10000)
    except PWTimeout:
        current_page_health(page, rejected)
        return None
    current_page_health(page, rejected)
    if search.input_value().strip().lower() != username:
        raise InstagramUnavailable("Search text changed during the run. Stop other interactions.")
    if matches.count() > 15:
        return None
    rows: list[Locator] = []
    keys: set[int] = set()
    for i in range(matches.count()):
        match = matches.nth(i)
        if not match.is_visible():
            continue
        details = match.evaluate(r"""el => {
            let node = el;
            for (let depth = 0; node && depth < 12; depth++, node = node.parentElement) {
                const toggles = node.querySelectorAll('[role="button"][aria-label="Toggle checkbox"]');
                const style = getComputedStyle(node);
                if (toggles.length === 1 && style.pointerEvents === "auto" && style.cursor === "pointer") {
                    return {depth, key: Array.from(document.querySelectorAll('*')).indexOf(node)};
                }
                if (toggles.length > 1) break;
            }
            return null;
        }""")
        if details is None:
            continue
        row = match.locator("xpath=" + "/".join([".."] * details["depth"])) if details["depth"] else match
        lines = row.inner_text().splitlines()
        if (row.is_visible() and lines and lines[0].strip().lower() == username
                and row.locator(TOGGLE_SELECTOR).count() == 1 and details["key"] not in keys):
            rows.append(row)
            keys.add(details["key"])
    return rows[0] if len(rows) == 1 else None


def selection_state(row: Locator) -> str:
    return row.evaluate('''el => {
        const button = el.querySelector('[role="button"][aria-label="Toggle checkbox"]');
        const icon = button?.querySelector('[style*="mask-image"]');
        if (!icon) return "UNKNOWN";
        const style = getComputedStyle(icon);
        const mask = style.maskImage || style.webkitMaskImage || "";
        if (mask.includes("circle-check__filled__")) return "SELECTED";
        if (mask.includes("circle__outline__")) return "NOT_SELECTED";
        return "UNKNOWN";
    }''')


@contextmanager
def run_lock() -> Iterator[None]:
    """Lock this data folder on macOS/Linux; old scripts may not use this lock."""
    import fcntl
    with LOCK_PATH.open("a+") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another run is using this data folder. Stop it before continuing.") from exc
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def terminal_prompt(message: str) -> str:
    try:
        return input(message).strip()
    except EOFError as exc:
        raise ValueError("Run this saved .py file in Terminal, not through a heredoc or pipe.") from exc


def guarded_wait(page: Page, rejected: list[str], seconds: float) -> None:
    """Only service events/read the UI while waiting; never retry requests."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current_page_health(page, rejected)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            page.wait_for_timeout(min(500, max(1, remaining * 1000)))
    current_page_health(page, rejected)


def confirm_manual_refresh(page: Page, rejected: list[str], account: str) -> None:
    """Require a new document, not just a changed checkbox, before an audit."""
    current_page_health(page, rejected)
    before = page.evaluate("() => performance.timeOrigin")
    print("\nREAD-ONLY AUDIT: refresh this connected tab ONCE (Command+R on Mac, Ctrl+R on Linux).")
    print(f"Wait for Close Friends to load normally. Manually confirm you are logged into @{account}.")
    print("Do not click selection circles. Cancel on a page error or security challenge.")
    if terminal_prompt(f"Then type REFRESHED {account}: ") != f"REFRESHED {account}":
        raise InstagramUnavailable("Verification cancelled. No membership changes were made.")
    current_page_health(page, rejected)
    after = page.evaluate("() => performance.timeOrigin")
    if before == after:
        raise InstagramUnavailable("No full refresh detected in the connected tab. No verification recorded.")
    print("New document detected. Reading displayed selection states, without clicking.")


def observe_selected_after_click(page: Page, row: Locator, rejected: list[str]) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current_page_health(page, rejected)
        state = selection_state(row)
        if state == "SELECTED":
            guarded_wait(page, rejected, 5)
            if selection_state(row) != "SELECTED":
                raise InstagramUnavailable("Selection did not remain selected on screen. Manual review needed.")
            return
        if state == "UNKNOWN":
            raise InstagramUnavailable("Checkbox icon changed unexpectedly. No second click will be attempted.")
        page.wait_for_timeout(250)
    raise InstagramUnavailable("Checkbox did not become selected. No second click will be attempted.")


def get_targets(names: list[str], args: argparse.Namespace, latest: dict[str, dict[str, str]]) -> list[str]:
    if args.username:
        name = normalize_username(args.username)
        if name not in names:
            raise ValueError("Requested username is not in followers.csv; import the correct follower snapshot first.")
        return [name]
    if args.verify_pending:
        queue = [name for name in names if latest.get(name, {}).get("result") in AWAITING_RESULTS]
        return queue[args.start - 1:args.start - 1 + args.limit]
    return names[args.start - 1:args.start - 1 + args.limit]


def make_response_watcher(rejected: list[str]):
    def watch_response(response: Response) -> None:
        host = (urlsplit(response.url).hostname or "").lower()
        if not (host == "instagram.com" or host.endswith(".instagram.com")):
            return
        status = response.status
        request = response.request
        if (status in (401, 403, 429) or
            (status == 400 and request.method in ("POST", "PUT", "PATCH", "DELETE")) or
            (status >= 500 and request.resource_type in ("document", "xhr", "fetch"))):
            # Do not record full URLs, request payloads, cookies or authentication tokens.
            if len(rejected) < 5:
                rejected.append(f"HTTP {status} {request.method} ({request.resource_type})")
    return watch_response


def browser_check(names: list[str], args: argparse.Namespace) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError("Playwright is missing. Install requirements.txt in this Python environment first.") from exc

    latest, _ = latest_results(read_progress())
    targets = get_targets(names, args, latest)
    if not targets:
        print("Nothing in this queue/range to process. No browser connection was made.")
        return 0
    is_audit = args.verify_live or args.verify_pending
    if args.apply:
        eligible = [name for name in targets
                    if latest.get(name, {}).get("result") in ADDABLE_RESULTS]
        if not eligible:
            print("No eligible additions in this range. Recorded selections and pending verification are skipped.")
            print("Use --verify-pending to review uncertain previous clicks.")
            return 0
        print(f"Up to {args.max_adds} clicks. Selections will remain PENDING until a separate verification.")
        print(f"Manually confirm the connected account is @{args.account}. Do not use other automation.")
        if terminal_prompt(f"Type ADD {args.max_adds} TO {args.account}: ") != f"ADD {args.max_adds} TO {args.account}":
            print("Cancelled. No changes made.")
            return 0

    ensure_account_binding(args.account, bind=True)
    clicked_count = 0
    stopped = False
    current = ""
    phase = "connecting"
    click_started = False
    with endpoint_lock(), sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except Exception as exc:
            raise ValueError("Could not attach to the loopback Chrome debugging port. Keep your dedicated Chrome open and check the port; no automatic retry.") from exc
        pages = [pg for ctx in browser.contexts for pg in ctx.pages if is_close_friends_url(pg.url)]
        if len(pages) != 1:
            raise ValueError(f"Keep exactly ONE Close Friends tab open in Chrome on port {urlsplit(CDP_URL).port}.")
        page = pages[0]
        rejected = []
        watch_response = make_response_watcher(rejected)
        page.on("response", watch_response)
        print("Connected to Instagram Close Friends. No automatic reloads; theme is not changed.")
        if args.no_dark:
            print("--no-dark accepted for compatibility; this version never changes the theme.")
        last_search_started = None
        try:
            current_page_health(page, rejected)
            if is_audit:
                phase = "manual_refresh_checkpoint"
                confirm_manual_refresh(page, rejected, args.account)
            for current in targets:
                click_started = False
                old_result = latest.get(current, {}).get("result")
                if args.apply and old_result in CONFIRMED_RESULTS:
                    print(f"SKIP @{current}: historically recorded selected.")
                    continue
                if args.apply and old_result not in ADDABLE_RESULTS:
                    print(f"REVIEW @{current}: unresolved prior state; audit it before any new click.")
                    continue
                phase = "pacing"
                if last_search_started is not None:
                    elapsed = time.monotonic() - last_search_started
                    guarded_wait(page, rejected, max(0, args.delay_seconds - elapsed))
                phase = "search"
                last_search_started = time.monotonic()
                print(f"\n@{current} — searching")
                row = find_row(page, current, rejected)
                current_page_health(page, rejected)
                if row is None:
                    if is_audit:
                        result = "verification_unresolved"
                    elif not args.apply:
                        result = "preview_not_found_or_ambiguous"
                    else:
                        result = "not_found_or_ambiguous"
                    log_result(current, result)
                    print("UNRESOLVED: No unique exact match. This does not establish a deleted account or an empty list.")
                    continue
                state = selection_state(row)
                print("Instagram displayed:", state)
                if state == "UNKNOWN":
                    raise InstagramUnavailable("Unknown checkbox icon; stopping instead of guessing.")
                if is_audit:
                    result = "verified_selected" if state == "SELECTED" else "live_unselected"
                    log_result(current, result)
                    print("VERIFIED SELECTED AFTER MANUAL REFRESH" if state == "SELECTED" else
                          "VERIFIED NOT SELECTED AFTER MANUAL REFRESH")
                    continue
                if not args.apply:
                    log_result(current, "preview_only")
                    print("PREVIEW ONLY: no clicks and no saved-state confirmation.")
                    continue
                if state == "SELECTED":
                    # Existing visible selections are also not freshly verified without a reload.
                    log_result(current, "selected_pending_verification")
                    print("Already selected on screen. No click; queued for separate verification.")
                    continue
                phase = "before_click"
                current_page_health(page, rejected)
                if (selection_state(row) != "NOT_SELECTED" or
                    row.inner_text().splitlines()[0].strip().lower() != current):
                    raise InstagramUnavailable("Account row/state changed before click. Stopping.")
                # Write intent BEFORE the click so an interruption cannot hide an uncertain mutation.
                log_result(current, "selection_attempted_pending_verification")
                phase = "click"
                click_started = True
                clicked_count += 1
                row.click(timeout=5000)
                phase = "observing_selection"
                observe_selected_after_click(page, row, rejected)
                log_result(current, "selected_pending_verification")
                latest[current] = {"result": "selected_pending_verification"}
                print(f"SELECTED ON SCREEN — NOT YET VERIFIED ({clicked_count}/{args.max_adds} clicks).")
                click_started = False
                if clicked_count >= args.max_adds:
                    print("PAUSED: maximum clicks reached. Verify these selections before another addition batch.")
                    break
        except (Exception, KeyboardInterrupt) as exc:
            stopped = True
            if current:
                log_result(current, "stopped_after_click" if click_started else
                           ("verification_unresolved" if is_audit else ("stopped_before_click" if args.apply else "preview_error")))
            summary = log_error(current, phase, exc)
            print(f"STOPPED during {phase}: {summary}")
            if click_started:
                print("The last account may already be selected. No retry/removal will be attempted.")
        finally:
            page.remove_listener("response", watch_response)
            # Exiting Playwright disconnects; never close the user's browser/context/tab.

    create_reports(names)
    if stopped:
        print("STOPPED EARLY. Check Instagram manually. No automatic reload, retry or restriction workaround.")
        return 2
    if not is_audit:
        print("Run ended. Displayed selections are NOT confirmed saved until --verify-pending succeeds.")
    else:
        print("Read-only audit ended. These observations describe the accounts that were found, at this time.")
    return 0


def default_data_dir() -> Path:
    value = os.environ.get("CLOSE_FRIENDS_DATA_DIR")
    return Path(value).expanduser() if value else Path.home() / ".local" / "share" / PROJECT_NAME


def configure_paths(folder: Path) -> None:
    """One process operates on one workspace; library callers must not share threads."""
    global BASE_DIR, CSV_PATH, PROGRESS_PATH, REPORT_PATH, PENDING_PATH, NEW_PATH
    global REMOVED_PATH, ERROR_PATH, SELECTED_PATH, AWAITING_PATH, LOCK_PATH, ACCOUNT_PATH
    BASE_DIR = folder.expanduser().resolve()
    BASE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    for attr, name in {
        "CSV_PATH": "followers.csv", "PROGRESS_PATH": "close_friends_progress.csv",
        "REPORT_PATH": "close_friends_status.csv", "PENDING_PATH": "close_friends_pending.csv",
        "NEW_PATH": "close_friends_new_since_export.csv",
        "REMOVED_PATH": "close_friends_no_longer_following.csv",
        "ERROR_PATH": "close_friends_errors.csv", "SELECTED_PATH": "close_friends_selected.csv",
        "AWAITING_PATH": "close_friends_awaiting_verification.csv",
        "LOCK_PATH": ".close_friends_run.lock", "ACCOUNT_PATH": ".close_friends_account.json",
    }.items():
        path = BASE_DIR / name
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked workspace file: {name}")
        globals()[attr] = path


def validate_cdp_url(value: str) -> str:
    url = urlsplit(value)
    try:
        port = url.port
    except ValueError as exc:
        raise ValueError("CDP port is invalid.") from exc
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username is not None or url.password is not None or not port
            or url.path not in {"", "/"} or url.query or url.fragment):
        raise ValueError("CDP must be a loopback HTTP endpoint, e.g. http://127.0.0.1:9222. No tunnels or credentials.")
    return value.rstrip("/")


def ensure_account_binding(account: str | None, *, bind: bool = False) -> str | None:
    """Guard against reusing the same history for different accounts.

    This is a local user declaration, NOT proof of which account is open in Chrome.
    """
    bound = None
    if ACCOUNT_PATH.exists():
        data = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
        bound = normalize_username(data.get("account")) if isinstance(data, dict) else None
        if not bound:
            raise ValueError("Invalid workspace account binding. Inspect the local account metadata.")
    if account and bound and account != bound:
        raise ValueError("This data folder belongs to a different account. Use a separate data folder; do not reuse its history.")
    resolved = account or bound
    if bind and not resolved:
        raise ValueError("Pass --account YOUR_USERNAME for browser commands.")
    if bind and not bound:
        # Exclusively create; never replace an existing account binding.
        with ACCOUNT_PATH.open("x", encoding="utf-8") as fh:
            json.dump({"account": resolved, "schema": 1}, fh)
            fh.write("\n")
    return resolved


@contextmanager
def endpoint_lock() -> Iterator[None]:
    """Coordinate our processes on one debugging port, even with different data folders."""
    import fcntl
    port = urlsplit(CDP_URL).port
    folder = Path.home() / ".cache" / PROJECT_NAME / "locks"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / f"cdp-{port}.lock"
    if path.is_symlink():
        raise ValueError("Refusing symlinked browser lock.")
    with path.open("a+") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another helper is using this Chrome debugging port. Stop it first.") from exc
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    global CDP_URL
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"Close Friends Helper {VERSION}")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="Private workspace; default ~/.local/share/instagram-close-friends-playwright or CLOSE_FRIENDS_DATA_DIR.")
    parser.add_argument("--account", help="Instagram username for this workspace; required on its first browser run. Not a password.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Loopback Chrome debugging endpoint only.")
    parser.add_argument("--status", action="store_true", help="Offline reports; no browser needed.")
    parser.add_argument("--import-export", metavar="ZIP", help="Import a follower export after preview/confirmation, preserving progress.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--verify-live", action="store_true", help="Read-only audit after a manual refresh (max 20).")
    modes.add_argument("--verify-pending", action="store_true", help="Audit the pending/uncertain queue after a manual refresh (max 20).")
    modes.add_argument("--apply", action="store_true", help="Limited additions; new selections remain PENDING.")
    parser.add_argument("--username", help="One exact username in followers.csv; overrides positional range.")
    parser.add_argument("--start", type=int, default=1, help="1-based CSV position; for --verify-pending, position in its queue.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum names scanned, default 5; maximum 100, or 20 for audits.")
    parser.add_argument("--max-adds", type=int, default=3, help="Maximum click attempts (1 to 10); not an Instagram limit.")
    parser.add_argument("--delay-seconds", type=float, default=30, help="Minimum seconds between searches, 10 to 3600. Not a safe-rate guarantee.")
    parser.add_argument("--no-dark", action="store_true", help="Compatibility flag; theme is NEVER changed.")
    args = parser.parse_args(argv)
    if args.start < 1 or not 1 <= args.limit <= MAX_SCAN:
        parser.error(f"--start must be positive and --limit must be 1 to {MAX_SCAN}.")
    if not 1 <= args.max_adds <= 10:
        parser.error("--max-adds must be 1 to 10.")
    if not math.isfinite(args.delay_seconds) or not 10 <= args.delay_seconds <= 3600:
        parser.error("--delay-seconds must be a finite number from 10 to 3600.")
    if (args.verify_live or args.verify_pending) and args.limit > MAX_AUDIT and not args.username:
        parser.error(f"Live audits are limited to {MAX_AUDIT} usernames per run.")
    if args.verify_pending and args.username:
        parser.error("Use --verify-live with --username, not --verify-pending.")
    if (args.status or args.import_export) and (args.apply or args.verify_live or args.verify_pending):
        parser.error("Offline import/status cannot be combined with browser modes.")
    if args.account:
        account = normalize_username(args.account)
        if not account:
            parser.error("--account must be a valid username, not a URL or email.")
        args.account = account
    if sys.platform == "win32":
        parser.error("This release supports macOS/Linux locking. Native Windows has not been implemented.")
    CDP_URL = validate_cdp_url(args.cdp_url)
    old_umask = os.umask(0o077)
    try:
        configure_paths(args.data_dir)
        with run_lock():
            args.account = ensure_account_binding(args.account)
            print(f"Close Friends Helper {VERSION}")
            print(f"Data folder: {BASE_DIR}")
            if args.import_export:
                # Validate history before making changes to a follower snapshot.
                read_progress()
                names = import_export(args.import_export)
                create_reports(names)
                return 0
            names = read_username_csv(CSV_PATH)
            if not names:
                raise ValueError("followers.csv is empty.")
            create_reports(names)
            if args.status:
                return 0
            if not args.account:
                raise ValueError("Pass --account YOUR_USERNAME for the first browser run in this data folder.")
            return browser_check(names, args)
    finally:
        os.umask(old_umask)


def entrypoint() -> None:
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Stopped by user. Review pending selections before another run.", file=sys.stderr)
        sys.exit(130)
    except (ValueError, FileNotFoundError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {error_summary(exc)} No automatic retry.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    entrypoint()
