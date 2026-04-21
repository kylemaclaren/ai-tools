#!/usr/bin/env python3
"""Sync new Granola meeting transcripts to the configured output directory."""

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_VERSION_FILE = Path(__file__).parent / "VERSION"
_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
_VERSION_URL = (
    "https://raw.githubusercontent.com/kylemaclaren/ai-tools/main"
    "/cli-tools/granola-sync/VERSION"
)


def _check_version() -> None:
    if _VERSION == "unknown":
        return
    try:
        req = urllib.request.Request(_VERSION_URL, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            latest = resp.read().decode().strip()
        if latest != _VERSION:
            print(
                f"[granola-sync v{_VERSION}] Update available: latest is v{latest}. "
                f"Run 'git pull' to update.",
                file=sys.stderr,
            )
    except Exception:
        pass


BASE_URL = "https://api.granola.ai"
APP_VERSION = "7.0.0"
WORKOS_AUTH_URL = "https://api.workos.com/user_management/authenticate"
SUPABASE_JSON = Path.home() / "Library" / "Application Support" / "Granola" / "supabase.json"
STATE_FILE = Path(__file__).parent / "state.json"
CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_OUTPUT_DIR = Path.home() / "granola"

# Rate limiting (Granola API: 5 req/s sustained, 25 req / 5s burst)
REQUEST_DELAY = 0.25       # seconds between every API call (≤4 req/s sustained)
RATE_LIMIT_BACKOFF = 10.0  # seconds to sleep after a 429 before retrying
BATCH_SIZE = 10            # meetings processed per batch during initial sync
BATCH_PAUSE = 2.0          # seconds to pause between batches


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _read_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[warn] Could not save config to {CONFIG_FILE}: {exc}", file=sys.stderr)


def load_output_dir() -> Path:
    """Return the configured output directory.

    On first run, prompts interactively (default: ~/granola) and remembers
    the choice in config.json. Non-interactive runs (e.g. launchd) silently
    use the default. The OUTPUT_DIR environment variable still wins if set.
    """
    env_override = os.environ.get("OUTPUT_DIR", "").strip()
    if env_override:
        return Path(env_override).expanduser()

    saved = _read_config().get("output_dir")
    if saved:
        return Path(saved).expanduser()

    if sys.stdin.isatty():
        print(f"\nWhere should meeting transcripts be saved? [{DEFAULT_OUTPUT_DIR}]")
        try:
            answer = input("> ").strip()
        except EOFError:
            answer = ""
        chosen = Path(answer).expanduser() if answer else DEFAULT_OUTPUT_DIR
    else:
        chosen = DEFAULT_OUTPUT_DIR
        print(
            f"[granola-sync] No output directory configured; using default: {chosen}",
            file=sys.stderr,
        )

    _write_config({"output_dir": str(chosen)})
    print(f"[granola-sync] Saved output directory to {CONFIG_FILE.name}.", file=sys.stderr)
    return chosen


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _parse_supabase_json(raw: str) -> dict | None:
    """Extract access_token, refresh_token, and client_id from supabase.json."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    # WorkOS tokens (newer desktop app versions)
    if isinstance(data.get("workos_tokens"), str):
        try:
            wt = json.loads(data["workos_tokens"])
            if wt.get("access_token"):
                return {
                    "access_token": wt["access_token"],
                    "refresh_token": wt.get("refresh_token", ""),
                    "client_id": wt.get("client_id", "client_GranolaMac"),
                }
        except json.JSONDecodeError:
            pass

    # Cognito tokens (older desktop app versions)
    if isinstance(data.get("cognito_tokens"), str):
        try:
            ct = json.loads(data["cognito_tokens"])
            if ct.get("refresh_token"):
                return {
                    "access_token": ct.get("access_token", ""),
                    "refresh_token": ct["refresh_token"],
                    "client_id": ct.get("client_id", "client_GranolaMac"),
                }
        except json.JSONDecodeError:
            pass

    # Legacy root-level tokens
    if data.get("refresh_token"):
        return {
            "access_token": data.get("access_token", ""),
            "refresh_token": data["refresh_token"],
            "client_id": data.get("client_id", "client_GranolaMac"),
        }

    return None


def _refresh_workos_token(refresh_token: str, client_id: str) -> dict | None:
    """Exchange a WorkOS refresh token for new credentials."""
    payload = json.dumps({
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        WORKOS_AUTH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "client_id": client_id,
        }
    except Exception as exc:
        print(f"  [warn] Token refresh failed: {exc}", file=sys.stderr)
        return None


def load_token(state: dict) -> tuple[str, str, str]:
    """Return (access_token, refresh_token, client_id).

    Precedence:
    1. Granola desktop app's live supabase.json
    2. Locally cached credentials in state.json (written after a successful refresh)
    """
    if SUPABASE_JSON.exists():
        creds = _parse_supabase_json(SUPABASE_JSON.read_text(encoding="utf-8"))
        if creds and creds.get("access_token"):
            return creds["access_token"], creds["refresh_token"], creds["client_id"]

    cached = state.get("credentials", {})
    if cached.get("access_token"):
        return cached["access_token"], cached.get("refresh_token", ""), cached.get("client_id", "client_GranolaMac")

    print(
        "Error: Could not load Granola credentials from supabase.json or state.json.\n"
        "Make sure the Granola desktop app is installed and you are logged in.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Load persisted sync state (synced meeting IDs, cached credentials)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

_CLIENT_HEADERS = {
    "X-App-Version": APP_VERSION,
    "X-Client-Version": APP_VERSION,
    "X-Client-Type": "cli",
    "X-Client-Platform": "darwin",
    "Accept-Encoding": "identity",  # disable gzip so we can decode the body directly
}


def _api_post(endpoint: str, body: dict, token: str, *, retries: int = 3) -> dict | list:
    """POST to the Granola API and return parsed JSON, retrying on transient errors."""
    url = BASE_URL + endpoint
    payload = json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        **_CLIENT_HEADERS,
    }
    server_error_delay = 0.25
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        # Throttle every request to stay within the sustained rate limit.
        time.sleep(REQUEST_DELAY)
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise  # caller handles re-auth
            if exc.code == 429 and attempt < retries:
                # Wait for the full burst window to reset before retrying.
                time.sleep(RATE_LIMIT_BACKOFF)
                last_exc = exc
                continue
            if exc.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(server_error_delay * (2 ** attempt))
                last_exc = exc
                continue
            raise
        except OSError as exc:
            if attempt < retries:
                time.sleep(server_error_delay * (2 ** attempt))
                last_exc = exc
                continue
            raise
    raise last_exc  # type: ignore[misc]


def api_post(endpoint: str, body: dict, token: str, state: dict) -> tuple[dict | list, str]:
    """Call _api_post; on 401 attempt token refresh and retry once.

    Returns (response_data, current_token) so the caller can update state.
    """
    try:
        return _api_post(endpoint, body, token), token
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise

    # Try to refresh the token
    _, refresh_token, client_id = load_token(state)
    if not refresh_token:
        print("Error: Access token expired and no refresh token available.", file=sys.stderr)
        sys.exit(1)

    new_creds = _refresh_workos_token(refresh_token, client_id)
    if not new_creds:
        print("Error: Token refresh failed. Try logging in to the Granola desktop app.", file=sys.stderr)
        sys.exit(1)

    # Persist refreshed credentials for future runs
    state["credentials"] = new_creds
    save_state(state)

    new_token = new_creds["access_token"]
    return _api_post(endpoint, body, new_token), new_token


# ---------------------------------------------------------------------------
# Granola API
# ---------------------------------------------------------------------------

def list_meetings(token: str, state: dict, limit: int = 100) -> tuple[list[dict], str]:
    """Fetch the most recent meetings from the API."""
    meetings: list[dict] = []
    cursor: str | None = None

    while True:
        body: dict = {"limit": limit, "include_last_viewed_panel": False}
        if cursor:
            body["cursor"] = cursor

        data, token = api_post("/v2/get-documents", body, token, state)
        batch = data.get("docs", []) if isinstance(data, dict) else []
        meetings.extend(batch)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if not cursor:
            break

    return meetings, token


def get_full_meeting(meeting_id: str, token: str, state: dict) -> tuple[dict, str]:
    """Fetch the full meeting document including notes and AI-enhanced panel.

    Uses /v1/get-documents-batch with include_last_viewed_panel=True, which is
    the reliable source for notes and AI summaries. The /v1/get-document-metadata
    endpoint does not consistently return these fields.
    """
    data, token = api_post(
        "/v1/get-documents-batch",
        {"document_ids": [meeting_id], "include_last_viewed_panel": True},
        token,
        state,
    )
    if isinstance(data, dict):
        docs = data.get("documents") or data.get("docs") or []
        if docs:
            return docs[0], token
    return {}, token


def get_transcript(meeting_id: str, token: str, state: dict) -> tuple[list[dict], str]:
    """Fetch raw transcript utterances."""
    data, token = api_post(
        "/v1/get-document-transcript",
        {"document_id": meeting_id},
        token,
        state,
    )
    return data if isinstance(data, list) else [], token


def list_folders(token: str, state: dict) -> tuple[list[dict], str]:
    """Fetch all document lists (folders) from the Granola API.

    Tries the v2 endpoint first, falling back to v1. Each folder dict contains
    at minimum an ``id`` and a name (``title`` in v2, ``name`` in v1), plus the
    documents belonging to it (``documents`` list in v2, ``document_ids`` in v1).
    """
    for endpoint in ("/v2/get-document-lists", "/v1/get-document-lists"):
        try:
            data, token = api_post(endpoint, {}, token, state)
            if isinstance(data, list):
                return data, token
            if isinstance(data, dict):
                folders = data.get("document_lists") or data.get("lists") or []
                if folders:
                    return folders, token
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and endpoint.startswith("/v2"):
                continue
            raise
    return [], token


def _folder_name(folder: dict) -> str:
    """Return the display name for a folder (v2 uses ``title``, v1 uses ``name``)."""
    return folder.get("title") or folder.get("name") or "(unnamed)"


def _folder_doc_ids(folder: dict) -> list[str]:
    """Extract document IDs from a folder response (handles v1 and v2 shapes)."""
    docs = folder.get("documents")
    if isinstance(docs, list):
        return [d["id"] if isinstance(d, dict) else d for d in docs]
    ids = folder.get("document_ids")
    if isinstance(ids, list):
        return ids
    return []


# ---------------------------------------------------------------------------
# ProseMirror → Markdown (port of granola-cli/src/lib/prosemirror.ts)
# ---------------------------------------------------------------------------

def _inline_to_md(nodes: list | None) -> str:
    if not nodes:
        return ""
    return "".join(_node_to_md(n) for n in nodes)


def _apply_marks(text: str, marks: list | None) -> str:
    if not marks:
        return text
    for mark in marks:
        t = mark.get("type", "")
        if t in ("bold", "strong"):
            text = f"**{text}**"
        elif t in ("italic", "em"):
            text = f"*{text}*"
        elif t == "code":
            text = f"`{text}`"
        elif t == "strike":
            text = f"~~{text}~~"
    return text


def _node_to_md(node: dict | str) -> str:
    if isinstance(node, str):
        return node  # bare string node — return as-is
    ntype = node.get("type", "")
    content = node.get("content", [])
    attrs = node.get("attrs", {})

    if ntype == "heading":
        level = attrs.get("level", 1)
        return "#" * level + " " + _inline_to_md(content)
    if ntype == "paragraph":
        return _inline_to_md(content)
    if ntype == "bulletList":
        return "\n".join(_node_to_md(li) for li in content)
    if ntype == "orderedList":
        lines = []
        for i, li in enumerate(content, 1):
            item = _node_to_md(li)
            lines.append(re.sub(r"^- ", f"{i}. ", item))
        return "\n".join(lines)
    if ntype == "listItem":
        inner = "\n  ".join(_node_to_md(c) for c in content)
        return f"- {inner}"
    if ntype == "blockquote":
        return "\n".join(f"> {_node_to_md(c)}" for c in content)
    if ntype == "codeBlock":
        lang = attrs.get("language", "")
        return f"```{lang}\n{_inline_to_md(content)}\n```"
    if ntype == "horizontalRule":
        return "---"
    if ntype == "text":
        return _apply_marks(node.get("text", ""), node.get("marks"))
    # Fallback: recurse into children
    return "".join(_node_to_md(c) for c in content)


def prosemirror_to_markdown(doc: dict | str | None) -> str:
    """Convert a ProseMirror doc object to a Markdown string.

    Some API responses encode the doc as a JSON string rather than a parsed
    object; this function handles both forms.
    """
    if not doc:
        return ""
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except (json.JSONDecodeError, ValueError):
            return doc  # plain text fallback
    if not isinstance(doc, dict) or not doc.get("content"):
        return ""
    parts = [_node_to_md(n) for n in doc["content"]]
    # Filter blanks, join with double newline
    return "\n\n".join(p for p in parts if p.strip())


# ---------------------------------------------------------------------------
# Transcript formatting
# ---------------------------------------------------------------------------

def format_transcript(utterances: list[dict]) -> str:
    """Format raw transcript utterances as readable Markdown."""
    if not utterances:
        return "_No transcript available._"

    lines: list[str] = []
    for u in utterances:
        speaker = "**You**" if u.get("source") == "microphone" else "**Participant**"
        text = u.get("text", "").strip()
        if text:
            lines.append(f"{speaker}: {text}")

    return "\n".join(lines) if lines else "_No transcript available._"


# ---------------------------------------------------------------------------
# Filename + Markdown composition
# ---------------------------------------------------------------------------

def sanitize_filename(title: str, date_str: str) -> str:
    """Build a date-prefixed, cross-platform-safe filename."""
    # Parse the ISO date and format as YYYY-MM-DD
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        prefix = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        prefix = "0000-00-00"

    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title)
    safe = re.sub(r"\s+", "_", safe.strip())
    safe = safe[:180] or "untitled"
    return f"{prefix}_{safe}.md"


def _format_attendees(meeting: dict, metadata: dict) -> str:
    """Build a comma-separated attendee string from available data."""
    people: list[str] = []

    attendees = (
        metadata.get("attendees")
        or meeting.get("attendees")
        or (meeting.get("people") or {}).get("attendees")
        or []
    )
    for person in attendees:
        if isinstance(person, str):
            people.append(person)
            continue
        name = person.get("name", "")
        email = person.get("email", "")
        if name and email:
            people.append(f"{name} ({email})")
        elif name:
            people.append(name)
        elif email:
            people.append(email)

    return ", ".join(people) if people else ""


def compose_markdown(meeting: dict, full_meeting: dict, transcript: list[dict]) -> str:
    """Assemble the full Markdown document for a meeting."""
    title = meeting.get("title") or "Untitled Meeting"
    date_str = meeting.get("created_at", "")
    meeting_id = meeting.get("id", "")
    attendees_str = _format_attendees(meeting, full_meeting)

    # Parse display date
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        display_date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        display_date = date_str

    # Use the full notes panel (last_viewed_panel), which contains both manual
    # notes and Granola's AI-generated content. The API does not expose these
    # separately, so both are included under a single "Notes" section.
    notes_doc = (full_meeting.get("last_viewed_panel") or {}).get("content")
    notes_md = prosemirror_to_markdown(notes_doc)
    transcript_md = format_transcript(transcript)

    # YAML frontmatter
    frontmatter_lines = ["---"]
    frontmatter_lines.append(f"id: {meeting_id}")
    frontmatter_lines.append(f"title: {title}")
    frontmatter_lines.append(f"date: {display_date}")
    if attendees_str:
        frontmatter_lines.append(f"attendees: {attendees_str}")
    frontmatter_lines.append("---")
    frontmatter = "\n".join(frontmatter_lines)

    sections: list[str] = [frontmatter, f"# {title}"]

    if notes_md:
        sections.append("## Notes\n\n" + notes_md)

    sections.append("## Transcript\n\n" + transcript_md)

    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_DATE_FORMATS = ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%y", "%m-%d-%Y")

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}



def _meeting_date(meeting: dict) -> datetime:
    """Return the meeting's created_at as a timezone-aware UTC datetime, or epoch on failure."""
    raw = meeting.get("created_at", "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _parse_date_range(value: str) -> tuple[datetime, datetime]:
    """Parse a date string into a (start, end) UTC range (start inclusive, end exclusive).

    Supports absolute dates (MM/DD/YY, YYYY-MM-DD, etc.) and relative
    descriptors: today, yesterday, this/last week, this/last month,
    this/last year, or 'Month YYYY' (e.g. 'February 2026').
    """
    val = value.strip().lower()
    today = date.today()
    start_d: date | None = None
    end_d: date | None = None

    if val == "today":
        start_d = today
        end_d = today + timedelta(days=1)
    elif val == "yesterday":
        start_d = today - timedelta(days=1)
        end_d = today
    elif val == "this week":
        start_d = today - timedelta(days=today.weekday())
        end_d = start_d + timedelta(days=7)
    elif val == "last week":
        this_monday = today - timedelta(days=today.weekday())
        start_d = this_monday - timedelta(days=7)
        end_d = this_monday
    elif val == "this month":
        start_d = today.replace(day=1)
        end_d = (start_d + timedelta(days=32)).replace(day=1)
    elif val == "last month":
        first_this = today.replace(day=1)
        end_d = first_this
        start_d = (first_this - timedelta(days=1)).replace(day=1)
    elif val == "this year":
        start_d = today.replace(month=1, day=1)
        end_d = today.replace(year=today.year + 1, month=1, day=1)
    elif val == "last year":
        start_d = today.replace(year=today.year - 1, month=1, day=1)
        end_d = today.replace(month=1, day=1)
    else:
        m = re.match(r"^([a-z]+)\s+(\d{4})$", val)
        if m:
            month_num = _MONTH_NAMES.get(m.group(1))
            if month_num:
                year = int(m.group(2))
                start_d = date(year, month_num, 1)
                end_d = (start_d + timedelta(days=32)).replace(day=1)

    if start_d is not None and end_d is not None:
        return (
            datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc),
            datetime(end_d.year, end_d.month, end_d.day, tzinfo=timezone.utc),
        )

    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            d = dt.date()
            start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            return start, start + timedelta(days=1)
        except ValueError:
            continue

    raise argparse.ArgumentTypeError(
        f"Unrecognized date: '{value}'. "
        "Try YYYY-MM-DD, MM/DD/YY, 'today', 'yesterday', 'this week', "
        "'last month', 'February 2026', etc."
    )


def _parse_date_point(value: str) -> datetime:
    """Parse a date string into a single UTC datetime (start of the resolved range)."""
    return _parse_date_range(value)[0]


def _fmt_date_range(r: tuple[datetime, datetime]) -> str:
    """Format a date range for display."""
    start, end = r
    if end - start <= timedelta(days=1):
        return start.strftime("%Y-%m-%d")
    end_display = (end - timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{start.strftime('%Y-%m-%d')} to {end_display}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync new Granola meetings to markdown files.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only sync the N most recent new meetings (useful for a test run).",
    )
    parser.add_argument(
        "--after",
        type=_parse_date_point,
        default=None,
        metavar="DATE",
        help=(
            "Only sync meetings on or after this date. "
            "Accepts MM/DD/YY, MM/DD/YYYY, YYYY-MM-DD, or relative "
            "descriptors like 'today', 'last week', 'February 2026', etc."
        ),
    )
    parser.add_argument(
        "--notes",
        action="store_true",
        default=False,
        help="Include the Granola notes panel (manual + AI-generated) in addition to the transcript.",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        metavar="NAME",
        help="Only sync meetings from the named Granola folder (case-insensitive substring match).",
    )
    parser.add_argument(
        "--list-folders",
        action="store_true",
        default=False,
        help="List available Granola folders and exit.",
    )
    parser.add_argument(
        "--list-meetings",
        action="store_true",
        default=False,
        help="List the 25 most recent meetings and exit.",
    )
    parser.add_argument(
        "--meeting",
        type=str,
        default=None,
        metavar="NAME",
        help="Sync all meetings matching the title (case-insensitive substring match). Combine with --date, --after, or --limit to narrow results.",
    )
    parser.add_argument(
        "--date",
        type=_parse_date_range,
        default=None,
        metavar="DATE",
        help=(
            "Only sync meetings from this date or period. "
            "Accepts MM/DD/YY, MM/DD/YYYY, YYYY-MM-DD, or relative descriptors: "
            "'today', 'yesterday', 'this week', 'last week', 'this month', "
            "'last month', 'this year', 'last year', 'February 2026', etc."
        ),
    )
    parser.add_argument(
        "--before",
        type=_parse_date_point,
        default=None,
        metavar="DATE",
        help=(
            "Only sync meetings before this date (exclusive). "
            "Accepts MM/DD/YY, MM/DD/YYYY, YYYY-MM-DD, or relative "
            "descriptors like 'today', 'this month', 'February 2026', etc. "
            "Combine with --after for a date range."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-sync meetings even if they were already synced (overwrites existing files).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List meetings that would be synced without actually downloading or writing anything.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="DIR",
        help="Override the output directory for this run (instead of the saved value in config.json).",
    )
    args = parser.parse_args()

    _check_version()
    state = load_state()
    access_token, _, _ = load_token(state)

    # --list-folders: print available folders and exit (no output dir needed).
    if args.list_folders:
        print("Fetching folders ...")
        try:
            folders, access_token = list_folders(access_token, state)
        except Exception as exc:
            print(f"Error fetching folders: {exc}", file=sys.stderr)
            sys.exit(1)
        if not folders:
            print("No folders found.")
            return
        print(f"\n{'#':<4} {'Folder':<40} {'Docs':>5}")
        print("-" * 51)
        for i, f in enumerate(folders, 1):
            name = _folder_name(f)
            count = len(_folder_doc_ids(f))
            print(f"{i:<4} {name:<40} {count:>5}")
        return

    # --list-meetings: print recent meetings and exit (no output dir needed).
    if args.list_meetings:
        print("Fetching meetings ...")
        try:
            meetings, access_token = list_meetings(access_token, state)
        except Exception as exc:
            print(f"Error fetching meetings: {exc}", file=sys.stderr)
            sys.exit(1)
        if not meetings:
            print("No meetings found.")
            return
        recent = meetings[:25]
        print(f"\n{'#':<4} {'Date':<12} {'Title'}")
        print("-" * 70)
        for i, m in enumerate(recent, 1):
            title = m.get("title") or "(untitled)"
            raw = m.get("created_at", "")
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                date = "?"
            synced_marker = " ✓" if m.get("id") in state.get("synced", {}) else ""
            print(f"{i:<4} {date:<12} {title}{synced_marker}")
        return

    # --meeting: sync all meetings matching the title search.
    if args.meeting:
        print("Fetching meetings ...")
        try:
            meetings, access_token = list_meetings(access_token, state)
        except Exception as exc:
            print(f"Error fetching meetings: {exc}", file=sys.stderr)
            sys.exit(1)

        needle = args.meeting.lower()
        matches = [m for m in meetings if needle in (m.get("title") or "").lower()]
        if not matches:
            print(f"No meeting matching \"{args.meeting}\".", file=sys.stderr)
            sys.exit(1)

        if args.date is not None:
            range_start, range_end = args.date
            matches = [m for m in matches if range_start <= _meeting_date(m) < range_end]
            if not matches:
                print(f"No meeting matching \"{args.meeting}\" on {_fmt_date_range(args.date)}.", file=sys.stderr)
                sys.exit(1)

        if args.after is not None:
            matches = [m for m in matches if _meeting_date(m) >= args.after]
            print(f"--after {args.after.strftime('%Y-%m-%d')}: {len(matches)} meeting(s) qualify.")

        if args.before is not None:
            matches = [m for m in matches if _meeting_date(m) < args.before]
            print(f"--before {args.before.strftime('%Y-%m-%d')}: {len(matches)} meeting(s) qualify.")

        if args.limit is not None:
            matches = matches[: args.limit]
            print(f"--limit {args.limit}: capped to {len(matches)} meeting(s).")

        if not matches:
            print("No meetings to sync after applying filters.")
            return

        if args.dry_run:
            print(f"[dry-run] Would sync {len(matches)} meeting(s):")
            for m in matches:
                title = m.get("title") or "(untitled)"
                dt = _meeting_date(m).strftime("%Y-%m-%d")
                print(f"  {dt}  {title}")
            return

        output_dir = Path(args.output).expanduser() if args.output else load_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        synced_state: dict[str, str] = state.get("synced", {})

        print(f"Syncing {len(matches)} meeting(s) matching \"{args.meeting}\" ...")
        ok = failed = 0

        for meeting in matches:
            meeting_id = meeting["id"]
            title = meeting.get("title") or "Untitled Meeting"

            try:
                full_meeting: dict = {}
                if args.notes:
                    full_meeting, access_token = get_full_meeting(meeting_id, access_token, state)
                transcript, access_token = get_transcript(meeting_id, access_token, state)
                content = compose_markdown(meeting, full_meeting, transcript)
                date_str = meeting.get("created_at", "")
                filename = sanitize_filename(title, date_str)
                (output_dir / filename).write_text(content, encoding="utf-8")

                synced_state[meeting_id] = filename
                print(f"  ✓  {title}  →  {filename}")
                ok += 1
            except Exception as exc:
                print(f"  ✗  {title}  →  {exc}", file=sys.stderr)
                failed += 1

        state["synced"] = synced_state
        save_state(state)

        print(f"\nDone: {ok} synced, {failed} failed.")
        if failed:
            sys.exit(1)
        return

    output_dir = Path(args.output).expanduser() if args.output else load_output_dir()
    synced: dict[str, str] = state.get("synced", {})
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve the meeting list — either from a specific folder or all recent.
    if args.folder:
        print("Fetching folders ...")
        try:
            folders, access_token = list_folders(access_token, state)
        except Exception as exc:
            print(f"Error fetching folders: {exc}", file=sys.stderr)
            sys.exit(1)

        needle = args.folder.lower()
        matches = [f for f in folders if needle == _folder_name(f).lower()]
        if not matches:
            matches = [f for f in folders if needle in _folder_name(f).lower()]
        if not matches:
            available = ", ".join(_folder_name(f) for f in folders) or "(none)"
            print(f"Error: No folder matching \"{args.folder}\". Available: {available}", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            names = ", ".join(_folder_name(f) for f in matches)
            print(f"Error: \"{args.folder}\" matches multiple folders: {names}. Be more specific.", file=sys.stderr)
            sys.exit(1)

        matched_folder = matches[0]
        doc_ids = _folder_doc_ids(matched_folder)
        print(f"Folder \"{_folder_name(matched_folder)}\": {len(doc_ids)} document(s).")

        # The v2 folder response embeds document objects with metadata we need.
        docs_by_id: dict[str, dict] = {}
        folder_docs = matched_folder.get("documents")
        if isinstance(folder_docs, list):
            for d in folder_docs:
                if isinstance(d, dict) and d.get("id"):
                    docs_by_id[d["id"]] = d

        # Build meeting dicts — use embedded objects when available, else stubs.
        meetings = [docs_by_id.get(did, {"id": did}) for did in doc_ids if did]
    else:
        print("Fetching meeting list ...")
        try:
            meetings, access_token = list_meetings(access_token, state)
        except Exception as exc:
            print(f"Error fetching meetings: {exc}", file=sys.stderr)
            sys.exit(1)

    if args.force:
        new_meetings = [m for m in meetings if m.get("id")]
    else:
        new_meetings = [m for m in meetings if m.get("id") and m["id"] not in synced]

    if args.date is not None:
        range_start, range_end = args.date
        count_before = len(new_meetings)
        new_meetings = [m for m in new_meetings if range_start <= _meeting_date(m) < range_end]
        print(f"--date {_fmt_date_range(args.date)}: {len(new_meetings)} of {count_before} new meeting(s) match.")

    if args.after is not None:
        count_before = len(new_meetings)
        new_meetings = [m for m in new_meetings if _meeting_date(m) >= args.after]
        print(f"--after {args.after.strftime('%Y-%m-%d')}: {len(new_meetings)} of {count_before} new meeting(s) qualify.")

    if args.before is not None:
        count_before = len(new_meetings)
        new_meetings = [m for m in new_meetings if _meeting_date(m) < args.before]
        print(f"--before {args.before.strftime('%Y-%m-%d')}: {len(new_meetings)} of {count_before} new meeting(s) qualify.")

    if args.limit is not None:
        new_meetings = new_meetings[: args.limit]
        print(f"--limit {args.limit}: capped to {len(new_meetings)} meeting(s).")

    if not new_meetings:
        print(f"No new meetings to sync (checked {len(meetings)} total).")
        return

    if args.dry_run:
        print(f"[dry-run] Would sync {len(new_meetings)} meeting(s):")
        for m in new_meetings:
            title = m.get("title") or "(untitled)"
            dt = _meeting_date(m).strftime("%Y-%m-%d")
            print(f"  {dt}  {title}")
        return

    total = len(new_meetings)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Syncing {total} new meeting(s) in {num_batches} batch(es) of up to {BATCH_SIZE} to {output_dir} ...")
    ok = failed = 0

    for batch_idx in range(num_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch = new_meetings[batch_start : batch_start + BATCH_SIZE]
        batch_end = batch_start + len(batch)

        print(f"\nBatch {batch_idx + 1}/{num_batches} (meetings {batch_start + 1}–{batch_end} of {total})")

        for meeting in batch:
            meeting_id = meeting["id"]
            title = meeting.get("title") or "Untitled Meeting"

            try:
                full_meeting: dict = {}
                if args.notes:
                    full_meeting, access_token = get_full_meeting(meeting_id, access_token, state)
                transcript, access_token = get_transcript(meeting_id, access_token, state)

                content = compose_markdown(meeting, full_meeting, transcript)

                date_str = meeting.get("created_at", "")
                filename = sanitize_filename(title, date_str)
                (output_dir / filename).write_text(content, encoding="utf-8")

                synced[meeting_id] = filename
                print(f"  ✓  {title}  →  {filename}")
                ok += 1

            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                print(f"  ✗  {title}  →  HTTP {exc.code}: {body}", file=sys.stderr)
                failed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  ✗  {title}  →  {exc}", file=sys.stderr)
                failed += 1

        # Save state after every batch so a partial run is resumable.
        state["synced"] = synced
        save_state(state)

        # Pause between batches (skip after the last one).
        if batch_idx < num_batches - 1:
            print(f"  [rate limit] pausing {BATCH_PAUSE}s before next batch ...")
            time.sleep(BATCH_PAUSE)

    print(f"\nDone: {ok} synced, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
