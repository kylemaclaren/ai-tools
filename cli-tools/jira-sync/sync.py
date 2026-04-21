#!/usr/bin/env python3
"""Sync Jira Cloud tickets for a project to local Markdown files."""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

_VERSION_FILE = Path(__file__).parent / "VERSION"
_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
_VERSION_URL = (
    "https://raw.githubusercontent.com/kylemaclaren/ai-tools/main"
    "/cli-tools/jira-sync/VERSION"
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
                f"[jira-sync v{_VERSION}] Update available: latest is v{latest}. "
                f"Run 'git pull' to update.",
                file=sys.stderr,
            )
    except Exception:
        pass


STATE_FILE = Path(__file__).parent / "state.json"
ENV_FILE = Path(__file__).parent / ".env"

PAGE_SIZE = 50
REQUEST_DELAY = 0.15
RATE_LIMIT_BACKOFF = 10.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _read_env() -> dict[str, str]:
    """Parse key=value pairs from .env, falling back to environment variables."""
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _cfg(key: str, env: dict[str, str] | None = None) -> str:
    """Return a config value from .env or os.environ, or exit with an error."""
    if env is None:
        env = _read_env()
    val = env.get(key) or os.environ.get(key, "")
    if not val:
        print(f"Error: {key} not set in .env or environment.", file=sys.stderr)
        sys.exit(1)
    return val


def load_output_dir(env: dict[str, str] | None = None) -> Path:
    if env is None:
        env = _read_env()
    raw = env.get("OUTPUT_DIR") or os.environ.get("OUTPUT_DIR", "")
    if raw:
        return Path(raw).expanduser()
    default = Path.home() / "AI" / "jira"
    print(f"[info] OUTPUT_DIR not set — using default: {default}", file=sys.stderr)
    return default


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _auth_header(email: str, token: str) -> str:
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return f"Basic {creds}"


TOKEN_URL = "https://id.atlassian.com/manage-profile/security/api-tokens"


def _handle_auth_error(http_code: int) -> None:
    """Print a helpful token-expired message and exit.

    Points the user (or their LLM) at the bundled auth.py helper, which
    captures the new token via getpass so it never enters chat or model
    context.
    """
    auth_script = Path(__file__).parent / "auth.py"
    print(
        f"\nAuthentication failed (HTTP {http_code}) — your Atlassian API "
        f"token has likely expired.",
        file=sys.stderr,
    )
    print("\nAsk your AI editor to rotate the token by running:", file=sys.stderr)
    print(f"  python3 {auth_script}", file=sys.stderr)
    print(
        f"\nThe helper opens {TOKEN_URL} in your browser, captures the new "
        f"token in the terminal (input is hidden — the token never enters "
        f"chat or the model context), and writes it directly to .env.",
        file=sys.stderr,
    )
    sys.exit(1)


def _api_get(url: str, auth: str, *, retries: int = 3) -> dict | list:
    """GET a Jira REST endpoint and return parsed JSON."""
    headers = {
        "Authorization": auth,
        "Accept": "application/json",
    }
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        time.sleep(REQUEST_DELAY)
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                _handle_auth_error(exc.code)
            if exc.code == 429 and attempt < retries:
                time.sleep(RATE_LIMIT_BACKOFF)
                last_exc = exc
                continue
            if exc.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(1.0 * (2 ** attempt))
                last_exc = exc
                continue
            raise
        except OSError as exc:
            if attempt < retries:
                time.sleep(1.0 * (2 ** attempt))
                last_exc = exc
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _api_request(url: str, auth: str, *, method: str = "GET",
                  body: dict | None = None, retries: int = 3) -> dict | None:
    """Send an HTTP request to a Jira REST endpoint and return parsed JSON.

    Returns None for 204 No Content responses (e.g. successful PUT).
    """
    headers: dict[str, str] = {
        "Authorization": auth,
        "Accept": "application/json",
    }
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        time.sleep(REQUEST_DELAY)
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.status == 204 or not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                _handle_auth_error(exc.code)
            if exc.code == 429 and attempt < retries:
                time.sleep(RATE_LIMIT_BACKOFF)
                last_exc = exc
                continue
            if exc.code in (500, 502, 503, 504) and attempt < retries:
                time.sleep(1.0 * (2 ** attempt))
                last_exc = exc
                continue
            raise
        except OSError as exc:
            if attempt < retries:
                time.sleep(1.0 * (2 ** attempt))
                last_exc = exc
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _api_post(url: str, body: dict, auth: str, *, retries: int = 3) -> dict:
    """POST JSON to a Jira REST endpoint and return parsed JSON."""
    result = _api_request(url, auth, method="POST", body=body, retries=retries)
    return result or {}


def _api_put(url: str, body: dict, auth: str, *, retries: int = 3) -> None:
    """PUT JSON to a Jira REST endpoint (returns 204 No Content on success)."""
    _api_request(url, auth, method="PUT", body=body, retries=retries)


# ---------------------------------------------------------------------------
# Jira API
# ---------------------------------------------------------------------------

def search_issues(base_url: str, auth: str, jql: str) -> list[dict]:
    """Paginate through /rest/api/3/search/jql and return all matching issues."""
    issues: list[dict] = []
    next_token: str | None = None
    while True:
        query: dict[str, str | int] = {
            "jql": jql,
            "maxResults": PAGE_SIZE,
            "fields": "summary,status,priority,issuetype,assignee,reporter,"
                       "created,updated,labels,description,comment",
            "expand": "renderedFields",
        }
        if next_token:
            query["nextPageToken"] = next_token
        params = urllib.parse.urlencode(query)
        url = f"{base_url}/rest/api/3/search/jql?{params}"
        data = _api_get(url, auth)
        batch = data.get("issues", [])
        issues.extend(batch)
        next_token = data.get("nextPageToken")
        if not next_token or not batch:
            break
    return issues


def list_projects(base_url: str, auth: str) -> list[dict]:
    """Return all projects visible to the authenticated user."""
    url = f"{base_url}/rest/api/3/project/search?maxResults=100&orderBy=key"
    data = _api_get(url, auth)
    return data.get("values", [])


def create_issue(base_url: str, auth: str, fields: dict) -> dict:
    """Create a Jira issue via POST /rest/api/3/issue. Returns the response."""
    url = f"{base_url}/rest/api/3/issue"
    return _api_post(url, {"fields": fields}, auth)


def update_issue(base_url: str, auth: str, key: str, fields: dict) -> None:
    """Update a Jira issue via PUT /rest/api/3/issue/{key}."""
    url = f"{base_url}/rest/api/3/issue/{key}"
    _api_put(url, {"fields": fields}, auth)


def add_comment(base_url: str, auth: str, key: str, body_adf: dict) -> dict:
    """Add a comment to a Jira issue via POST /rest/api/3/issue/{key}/comment."""
    url = f"{base_url}/rest/api/3/issue/{key}/comment"
    return _api_post(url, {"body": body_adf}, auth)


def find_board(base_url: str, auth: str, project_key: str) -> int | None:
    """Find the first Scrum/Kanban board for a project via the Agile API."""
    params = urllib.parse.urlencode({"projectKeyOrId": project_key, "maxResults": 10})
    url = f"{base_url}/rest/agile/1.0/board?{params}"
    data = _api_get(url, auth)
    boards = data.get("values", [])
    return boards[0]["id"] if boards else None


def find_sprint(base_url: str, auth: str, board_id: int,
                name: str | None = None) -> dict | None:
    """Find a sprint on a board. If name is None/empty, return the active sprint."""
    if name:
        url = f"{base_url}/rest/agile/1.0/board/{board_id}/sprint?maxResults=100"
        data = _api_get(url, auth)
        needle = name.lower()
        for s in data.get("values", []):
            if needle in s.get("name", "").lower():
                return s
        return None
    else:
        url = f"{base_url}/rest/agile/1.0/board/{board_id}/sprint?state=active&maxResults=1"
        data = _api_get(url, auth)
        sprints = data.get("values", [])
        return sprints[0] if sprints else None


# ---------------------------------------------------------------------------
# Markdown → ADF conversion (for ticket creation)
# ---------------------------------------------------------------------------

_RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
_RE_BULLET = re.compile(r"^(\s*)[-*]\s+(.*)")
_RE_ORDERED = re.compile(r"^(\s*)\d+\.\s+(.*)")
_RE_CODE_FENCE = re.compile(r"^```(\w*)")
_RE_RULE = re.compile(r"^---+\s*$")

# Inline patterns — order matters (links before bold to avoid conflicts)
_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_BOLD_ITALIC = re.compile(r"\*\*\*(.+?)\*\*\*")
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_ITALIC = re.compile(r"\*(.+?)\*")
_RE_INLINE_CODE = re.compile(r"`([^`]+)`")


def _parse_inline(text: str) -> list[dict]:
    """Convert inline markdown (bold, italic, code, links) to ADF text nodes."""
    nodes: list[dict] = []
    # Tokenise by splitting on inline patterns. We process left-to-right
    # using a single combined regex to handle nesting order correctly.
    combined = re.compile(
        r"(\[([^\]]+)\]\(([^)]+)\))"   # links
        r"|(\*\*\*(.+?)\*\*\*)"        # bold+italic
        r"|(\*\*(.+?)\*\*)"            # bold
        r"|(\*(.+?)\*)"                # italic
        r"|(`([^`]+)`)"                # inline code
    )
    pos = 0
    for m in combined.finditer(text):
        # Plain text before this match
        if m.start() > pos:
            plain = text[pos:m.start()]
            if plain:
                nodes.append({"type": "text", "text": plain})
        if m.group(2) is not None:  # link
            nodes.append({
                "type": "text",
                "text": m.group(2),
                "marks": [{"type": "link", "attrs": {"href": m.group(3)}}],
            })
        elif m.group(5) is not None:  # bold+italic
            nodes.append({
                "type": "text",
                "text": m.group(5),
                "marks": [{"type": "strong"}, {"type": "em"}],
            })
        elif m.group(7) is not None:  # bold
            nodes.append({
                "type": "text",
                "text": m.group(7),
                "marks": [{"type": "strong"}],
            })
        elif m.group(9) is not None:  # italic
            nodes.append({
                "type": "text",
                "text": m.group(9),
                "marks": [{"type": "em"}],
            })
        elif m.group(11) is not None:  # inline code
            nodes.append({
                "type": "text",
                "text": m.group(11),
                "marks": [{"type": "code"}],
            })
        pos = m.end()
    # Trailing plain text
    if pos < len(text):
        tail = text[pos:]
        if tail:
            nodes.append({"type": "text", "text": tail})
    if not nodes:
        nodes.append({"type": "text", "text": text})
    return nodes


def _collect_list_items(lines: list[str], start: int, pattern: re.Pattern,
                        base_indent: int) -> tuple[list[dict], int]:
    """Consume consecutive list items at the same indent level, return (items, next_index)."""
    items: list[dict] = []
    i = start
    while i < len(lines):
        m = pattern.match(lines[i])
        if not m:
            break
        indent = len(m.group(1))
        if indent < base_indent:
            break
        if indent > base_indent:
            break
        item_text = m.group(2)
        items.append({
            "type": "listItem",
            "content": [{"type": "paragraph", "content": _parse_inline(item_text)}],
        })
        i += 1
    return items, i


def markdown_to_adf(md: str) -> dict:
    """Convert a markdown string to an Atlassian Document Format (ADF) document."""
    doc: dict = {"type": "doc", "version": 1, "content": []}
    lines = md.split("\n")
    i = 0
    para_lines: list[str] = []

    def _flush_para() -> None:
        text = " ".join(para_lines).strip()
        if text:
            doc["content"].append({
                "type": "paragraph",
                "content": _parse_inline(text),
            })
        para_lines.clear()

    while i < len(lines):
        line = lines[i]

        # Code fence
        m_fence = _RE_CODE_FENCE.match(line)
        if m_fence:
            _flush_para()
            lang = m_fence.group(1) or None
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            node: dict = {
                "type": "codeBlock",
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            }
            if lang:
                node["attrs"] = {"language": lang}
            doc["content"].append(node)
            continue

        # Horizontal rule
        if _RE_RULE.match(line):
            _flush_para()
            doc["content"].append({"type": "rule"})
            i += 1
            continue

        # Heading
        m_head = _RE_HEADING.match(line)
        if m_head:
            _flush_para()
            level = len(m_head.group(1))
            doc["content"].append({
                "type": "heading",
                "attrs": {"level": level},
                "content": _parse_inline(m_head.group(2)),
            })
            i += 1
            continue

        # Bullet list
        m_bullet = _RE_BULLET.match(line)
        if m_bullet:
            _flush_para()
            indent = len(m_bullet.group(1))
            items, i = _collect_list_items(lines, i, _RE_BULLET, indent)
            doc["content"].append({"type": "bulletList", "content": items})
            continue

        # Ordered list
        m_ordered = _RE_ORDERED.match(line)
        if m_ordered:
            _flush_para()
            indent = len(m_ordered.group(1))
            items, i = _collect_list_items(lines, i, _RE_ORDERED, indent)
            doc["content"].append({"type": "orderedList", "content": items})
            continue

        # Blank line — flush paragraph
        if not line.strip():
            _flush_para()
            i += 1
            continue

        # Regular text — accumulate into paragraph
        para_lines.append(line)
        i += 1

    _flush_para()
    return doc


# ---------------------------------------------------------------------------
# Draft file parsing (for --create)
# ---------------------------------------------------------------------------

def parse_draft_file(path: Path) -> dict:
    """Read a draft markdown file and return parsed frontmatter + description body.

    Returns a dict with keys: summary, type, priority, labels, epic,
    status, assignee, reporter, and description (as markdown string).
    """
    text = path.read_text(encoding="utf-8")
    result: dict = {"_path": str(path)}

    # Extract YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            fm_block = text[3:end].strip()
            body = text[end + 3:].strip()
            for line in fm_block.splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
        else:
            body = text
    else:
        body = text

    # Strip the leading H1 title (it duplicates the summary)
    body = re.sub(r"^#\s+.*\n*", "", body, count=1).strip()

    # Strip a leading "## Description" header if present
    body = re.sub(r"^##\s+Description\s*\n*", "", body, count=1).strip()

    result["description"] = body
    return result


# ---------------------------------------------------------------------------
# HTML → Markdown conversion
# ---------------------------------------------------------------------------

class _HtmlToMd(HTMLParser):
    """Lightweight HTML-to-Markdown converter for Jira rendered fields."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._list_stack: list[str] = []  # "ul" or "ol"
        self._ol_counter: list[int] = []
        self._href: str | None = None
        self._in_pre = False
        self._in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self._parts.append("\n" + "#" * level + " ")
        elif tag == "p":
            self._parts.append("\n\n")
        elif tag == "br":
            self._parts.append("\n")
        elif tag == "strong" or tag == "b":
            self._parts.append("**")
        elif tag == "em" or tag == "i":
            self._parts.append("*")
        elif tag == "code" and not self._in_pre:
            self._in_code = True
            self._parts.append("`")
        elif tag == "pre":
            self._in_pre = True
            self._parts.append("\n```\n")
        elif tag == "a":
            self._href = attr_map.get("href")
            self._parts.append("[")
        elif tag == "ul":
            self._list_stack.append("ul")
            self._parts.append("\n")
        elif tag == "ol":
            self._list_stack.append("ol")
            self._ol_counter.append(0)
            self._parts.append("\n")
        elif tag == "li":
            indent = "  " * max(0, len(self._list_stack) - 1)
            if self._list_stack and self._list_stack[-1] == "ol":
                self._ol_counter[-1] += 1
                self._parts.append(f"{indent}{self._ol_counter[-1]}. ")
            else:
                self._parts.append(f"{indent}- ")
        elif tag == "hr":
            self._parts.append("\n---\n")
        elif tag == "blockquote":
            self._parts.append("\n> ")
        elif tag == "img":
            alt = attr_map.get("alt", "")
            src = attr_map.get("src", "")
            if src:
                self._parts.append(f"![{alt}]({src})")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._parts.append("\n")
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")
        elif tag == "code" and not self._in_pre:
            self._in_code = False
            self._parts.append("`")
        elif tag == "pre":
            self._in_pre = False
            self._parts.append("\n```\n")
        elif tag == "a":
            if self._href:
                self._parts.append(f"]({self._href})")
            else:
                self._parts.append("]")
            self._href = None
        elif tag == "ul":
            if self._list_stack:
                self._list_stack.pop()
            self._parts.append("\n")
        elif tag == "ol":
            if self._list_stack:
                self._list_stack.pop()
            if self._ol_counter:
                self._ol_counter.pop()
            self._parts.append("\n")
        elif tag == "li":
            self._parts.append("\n")
        elif tag == "p":
            pass

    def handle_data(self, data: str) -> None:
        if self._in_pre:
            self._parts.append(data)
        else:
            self._parts.append(data)

    def get_markdown(self) -> str:
        raw = "".join(self._parts)
        # Collapse excessive blank lines
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def html_to_markdown(html: str | None) -> str:
    if not html:
        return ""
    parser = _HtmlToMd()
    parser.feed(html)
    return parser.get_markdown()


# ---------------------------------------------------------------------------
# ADF → plain text fallback (for non-rendered fields)
# ---------------------------------------------------------------------------

def _adf_to_text(node: dict | str | None) -> str:
    """Recursively extract plain text from an ADF document node."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [_adf_to_text(child) for child in node.get("content", [])]
    text = "".join(parts)
    if node.get("type") in ("paragraph", "heading", "bulletList", "orderedList",
                             "blockquote", "codeBlock", "rule"):
        text += "\n"
    return text


# ---------------------------------------------------------------------------
# Markdown composition
# ---------------------------------------------------------------------------

def _safe_str(obj: dict | None, *keys: str) -> str:
    """Walk nested dicts by keys and return the leaf as a string, or ''."""
    current: dict | str | None = obj
    for k in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(k)
    return str(current) if current else ""


def _parse_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return iso


def _extract_comments(issue: dict) -> list[dict]:
    """Pull comments from the issue's fields.comment or renderedFields.comment."""
    rendered = (issue.get("renderedFields") or {}).get("comment", {})
    comments_list = rendered.get("comments", [])
    if comments_list:
        return comments_list
    raw = (issue.get("fields") or {}).get("comment", {})
    return raw.get("comments", [])


def compose_ticket_markdown(issue: dict) -> str:
    """Build a Markdown document for a single Jira issue."""
    fields = issue.get("fields", {})
    rendered = issue.get("renderedFields", {})
    key = issue.get("key", "")

    summary = fields.get("summary", "")
    status = _safe_str(fields.get("status"), "name")
    priority = _safe_str(fields.get("priority"), "name")
    issue_type = _safe_str(fields.get("issuetype"), "name")
    assignee = _safe_str(fields.get("assignee"), "displayName")
    reporter = _safe_str(fields.get("reporter"), "displayName")
    labels = ", ".join(fields.get("labels", []))
    created = _parse_date(fields.get("created", ""))
    updated = _parse_date(fields.get("updated", ""))

    # Description: prefer rendered HTML, fall back to ADF → plain text
    desc_html = rendered.get("description")
    if desc_html:
        description = html_to_markdown(desc_html)
    else:
        description = _adf_to_text(fields.get("description")).strip()

    # Frontmatter
    fm_lines = ["---"]
    fm_lines.append(f"key: {key}")
    fm_lines.append(f"summary: {summary}")
    fm_lines.append(f"status: {status}")
    if priority:
        fm_lines.append(f"priority: {priority}")
    if issue_type:
        fm_lines.append(f"type: {issue_type}")
    if assignee:
        fm_lines.append(f"assignee: {assignee}")
    if reporter:
        fm_lines.append(f"reporter: {reporter}")
    fm_lines.append(f"created: {created}")
    fm_lines.append(f"updated: {updated}")
    if labels:
        fm_lines.append(f"labels: {labels}")
    fm_lines.append("---")

    sections: list[str] = ["\n".join(fm_lines)]

    # Title + metadata line
    sections.append(f"# {key}: {summary}")

    meta_parts = []
    if status:
        meta_parts.append(f"**Status:** {status}")
    if priority:
        meta_parts.append(f"**Priority:** {priority}")
    if issue_type:
        meta_parts.append(f"**Type:** {issue_type}")
    if meta_parts:
        sections.append(" | ".join(meta_parts))

    detail_parts = []
    if assignee:
        detail_parts.append(f"**Assignee:** {assignee}")
    if reporter:
        detail_parts.append(f"**Reporter:** {reporter}")
    if detail_parts:
        sections.append(" | ".join(detail_parts))

    if labels:
        sections.append(f"**Labels:** {labels}")

    # Description
    if description:
        sections.append("## Description\n\n" + description)
    else:
        sections.append("## Description\n\n_No description._")

    # Comments
    comments = _extract_comments(issue)
    if comments:
        comment_parts = ["## Comments"]
        for c in comments:
            author = _safe_str(c.get("author"), "displayName") or "Unknown"
            date = _parse_date(c.get("created", ""))
            body_html = c.get("renderedBody") or c.get("body")
            if isinstance(body_html, str):
                body = html_to_markdown(body_html)
            elif isinstance(body_html, dict):
                body = _adf_to_text(body_html).strip()
            else:
                body = ""
            comment_parts.append(f"### {author} ({date})\n\n{body}")
        sections.append("\n\n".join(comment_parts))

    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_issue_fields(draft: dict, project_key: str) -> dict:
    """Map a parsed draft dict to a Jira issue creation payload."""
    fields: dict = {
        "project": {"key": project_key},
        "summary": draft.get("summary", "Untitled"),
        "issuetype": {"name": draft.get("type", "Task")},
    }

    if draft.get("priority"):
        fields["priority"] = {"name": draft["priority"]}

    if draft.get("labels"):
        fields["labels"] = [l.strip() for l in draft["labels"].split(",")]

    desc_md = draft.get("description", "")
    if desc_md:
        fields["description"] = markdown_to_adf(desc_md)

    # Link to parent epic via the "parent" field (next-gen / team-managed)
    # or via the "Epic Link" custom field (company-managed).
    # The "parent" approach works for both project types in current Jira Cloud.
    if draft.get("epic"):
        fields["parent"] = {"key": draft["epic"]}

    return fields


def _run_create(args: argparse.Namespace, env: dict[str, str],
                base_url: str, auth: str) -> None:
    """Handle the --create workflow: read drafts, confirm, push to Jira."""
    output_dir = load_output_dir(env)
    drafts_dir = Path(args.create_dir).expanduser() if args.create_dir else output_dir / "drafts"

    if not drafts_dir.exists():
        print(f"Drafts directory does not exist: {drafts_dir}", file=sys.stderr)
        print(f"Create it and add draft .md files, then re-run.", file=sys.stderr)
        sys.exit(1)

    draft_files = sorted(drafts_dir.glob("*.md"))
    if not draft_files:
        print(f"No .md files found in {drafts_dir}")
        return

    project_key = args.project or env.get("JIRA_PROJECT_KEY") or os.environ.get("JIRA_PROJECT_KEY", "")
    if not project_key:
        print("Error: No project specified. Use --project or set JIRA_PROJECT_KEY in .env.", file=sys.stderr)
        sys.exit(1)

    drafts = [parse_draft_file(f) for f in draft_files]

    # Show summary table
    print(f"\n{len(drafts)} ticket(s) to create in project {project_key}:\n")
    print(f"  {'#':<4} {'Type':<10} {'Priority':<10} {'Summary'}")
    print("  " + "-" * 70)
    for i, d in enumerate(drafts, 1):
        t = d.get("type", "Task")
        p = d.get("priority", "-")
        s = d.get("summary", "(no summary)")
        epic = d.get("epic", "")
        suffix = f"  [→ {epic}]" if epic else ""
        print(f"  {i:<4} {t:<10} {p:<10} {s}{suffix}")

    if args.dry_run:
        print("\nDry run — no changes made.")
        return

    print()
    answer = input("Create these tickets? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        return

    print()
    ok = failed = 0
    created_keys: list[str] = []

    for draft in drafts:
        summary = draft.get("summary", "(no summary)")
        draft_path = Path(draft["_path"])
        try:
            fields = _build_issue_fields(draft, project_key)
            resp = create_issue(base_url, auth, fields)
            new_key = resp.get("key", "???")
            created_keys.append(new_key)
            print(f"  ✓  {new_key}: {summary}")
            draft_path.unlink()
            ok += 1
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"  ✗  {summary}  →  HTTP {exc.code}: {body}", file=sys.stderr)
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗  {summary}  →  {exc}", file=sys.stderr)
            failed += 1

    print(f"\nCreated: {ok}, failed: {failed}.")

    # Sync newly-created tickets so they appear as KEY.md in the output dir
    if created_keys:
        keys_jql = ", ".join(created_keys)
        sync_jql = f"key in ({keys_jql})"
        print(f"\nSyncing created tickets ...")
        try:
            issues = search_issues(base_url, auth, sync_jql)
            output_dir.mkdir(parents=True, exist_ok=True)
            for issue in issues:
                key = issue.get("key", "unknown")
                md = compose_ticket_markdown(issue)
                (output_dir / f"{key}.md").write_text(md, encoding="utf-8")
                print(f"  ✓  Synced {key}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] Post-create sync failed: {exc}", file=sys.stderr)

    if failed:
        sys.exit(1)


def _run_update(args: argparse.Namespace, env: dict[str, str],
                base_url: str, auth: str) -> None:
    """Handle the --update workflow: parse local .md, push changes to Jira."""
    output_dir = load_output_dir(env)
    keys = [k.replace(".md", "") for k in args.update]

    parsed: list[tuple[str, dict]] = []
    for key in keys:
        filepath = output_dir / f"{key}.md"
        if not filepath.exists():
            print(f"Error: {filepath} not found.", file=sys.stderr)
            sys.exit(1)
        draft = parse_draft_file(filepath)
        fm_key = draft.get("key", "")
        if fm_key and fm_key != "NEW" and fm_key != key:
            print(f"Warning: frontmatter key '{fm_key}' differs from filename '{key}', using '{key}'.",
                  file=sys.stderr)
        parsed.append((key, draft))

    # Show what will be updated
    print(f"\n{len(parsed)} ticket(s) to update:\n")
    print(f"  {'Key':<14} {'Summary'}")
    print("  " + "-" * 60)
    for key, draft in parsed:
        s = draft.get("summary", "(no summary)")
        print(f"  {key:<14} {s}")

    if args.dry_run:
        print("\nDry run — no changes made.")
        return

    print()
    answer = input("Push these updates to Jira? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("Aborted.")
        return

    print()
    ok = failed = 0

    for key, draft in parsed:
        summary = draft.get("summary", "(no summary)")
        try:
            fields: dict = {"summary": draft.get("summary", "")}

            desc_md = draft.get("description", "")
            if desc_md:
                fields["description"] = markdown_to_adf(desc_md)

            if draft.get("priority"):
                fields["priority"] = {"name": draft["priority"]}

            if draft.get("labels"):
                fields["labels"] = [l.strip() for l in draft["labels"].split(",")]
            elif "labels" in draft:
                fields["labels"] = []

            update_issue(base_url, auth, key, fields)
            print(f"  ✓  {key}: {summary}")
            ok += 1
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"  ✗  {key}: {summary}  →  HTTP {exc.code}: {body}", file=sys.stderr)
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗  {key}: {summary}  →  {exc}", file=sys.stderr)
            failed += 1

    # Re-sync updated tickets to get the canonical version from Jira
    if ok > 0:
        updated_keys = [key for key, _ in parsed]
        keys_jql = ", ".join(updated_keys[:ok])
        sync_jql = f"key in ({keys_jql})"
        print(f"\nRe-syncing updated tickets ...")
        try:
            issues = search_issues(base_url, auth, sync_jql)
            for issue in issues:
                k = issue.get("key", "unknown")
                md = compose_ticket_markdown(issue)
                (output_dir / f"{k}.md").write_text(md, encoding="utf-8")
                print(f"  ✓  Synced {k}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] Post-update sync failed: {exc}", file=sys.stderr)

    print(f"\nUpdated: {ok}, failed: {failed}.")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Jira Cloud tickets to local Markdown files."
    )
    parser.add_argument(
        "--project", type=str, default=None, metavar="KEY",
        help="Project key to sync (overrides JIRA_PROJECT_KEY in .env).",
    )
    parser.add_argument(
        "--jql", type=str, default=None,
        help="Custom JQL query (overrides --project and .env project key).",
    )
    parser.add_argument(
        "--force", action="store_true", default=False,
        help="Re-sync all tickets, ignoring state.json.",
    )
    parser.add_argument(
        "--list-projects", action="store_true", default=False,
        help="List accessible Jira projects and exit.",
    )
    parser.add_argument(
        "--create", action="store_true", default=False,
        help="Create Jira tickets from draft markdown files in the drafts directory.",
    )
    parser.add_argument(
        "--create-dir", type=str, default=None, metavar="DIR",
        help="Directory containing draft .md files (defaults to OUTPUT_DIR/drafts/).",
    )
    parser.add_argument(
        "--update", nargs="+", type=str, default=None, metavar="KEY",
        help="Push local edits for one or more tickets back to Jira (e.g. --update PROJ-1 PROJ-2).",
    )
    parser.add_argument(
        "--issue", nargs="+", type=str, default=None, metavar="KEY",
        help="Sync specific issue(s) by key (e.g. --issue PROJ-3 PROJ-5 PROJ-9).",
    )
    parser.add_argument(
        "--epic", type=str, default=None, metavar="KEY",
        help="Sync all children of an epic (e.g. --epic PROJ-42).",
    )
    parser.add_argument(
        "--comment", nargs=2, type=str, default=None, metavar=("KEY", "TEXT"),
        help='Add a comment to a ticket (e.g. --comment PROJ-1 "Looks good!").',
    )
    parser.add_argument(
        "--sprint", nargs="?", type=str, default=False, const="",
        help="Sync tickets in a sprint. No arg = active sprint; or pass a name.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Preview what --create or --update would do without making changes.",
    )
    args = parser.parse_args()

    _check_version()

    env = _read_env()
    base_url = _cfg("JIRA_BASE_URL", env).rstrip("/")
    email = _cfg("JIRA_EMAIL", env)
    token = _cfg("JIRA_API_TOKEN", env)
    auth = _auth_header(email, token)

    # --list-projects
    if args.list_projects:
        print("Fetching projects ...")
        try:
            projects = list_projects(base_url, auth)
        except urllib.error.HTTPError as exc:
            print(f"Error: HTTP {exc.code} — {exc.read().decode(errors='replace')}", file=sys.stderr)
            sys.exit(1)
        if not projects:
            print("No projects found.")
            return
        print(f"\n{'Key':<12} {'Name'}")
        print("-" * 50)
        for p in projects:
            print(f"{p.get('key', ''):<12} {p.get('name', '')}")
        return

    # --create
    if args.create:
        _run_create(args, env, base_url, auth)
        return

    # --update
    if args.update:
        _run_update(args, env, base_url, auth)
        return

    # --comment
    if args.comment:
        key, text = args.comment
        if args.dry_run:
            print(f"Would add comment to {key}:\n")
            print(f"  {text}")
            print("\nDry run — no changes made.")
            return
        print(f"Adding comment to {key} ...")
        try:
            body_adf = markdown_to_adf(text)
            add_comment(base_url, auth, key, body_adf)
            print(f"  ✓  Comment added to {key}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"Error: HTTP {exc.code} — {body}", file=sys.stderr)
            sys.exit(1)
        return

    # Determine JQL
    skip_incremental = False
    if args.issue:
        keys_csv = ", ".join(args.issue)
        jql = f"key in ({keys_csv})"
        skip_incremental = True
    elif args.epic:
        jql = f'"Epic Link" = {args.epic} OR parent = {args.epic} ORDER BY rank ASC'
        skip_incremental = True
    elif args.sprint is not False:
        project_key = args.project or env.get("JIRA_PROJECT_KEY") or os.environ.get("JIRA_PROJECT_KEY", "")
        if not project_key:
            print("Error: No project specified. Use --project or set JIRA_PROJECT_KEY in .env.", file=sys.stderr)
            sys.exit(1)
        print("Finding board ...")
        board_id = find_board(base_url, auth, project_key)
        if not board_id:
            print(f"Error: No board found for project {project_key}.", file=sys.stderr)
            sys.exit(1)
        sprint_name = args.sprint or None
        if sprint_name:
            print(f'Finding sprint matching "{sprint_name}" ...')
        else:
            print("Finding active sprint ...")
        sprint = find_sprint(base_url, auth, board_id, sprint_name)
        if not sprint:
            label = f'matching "{sprint_name}"' if sprint_name else "active"
            print(f"Error: No {label} sprint found.", file=sys.stderr)
            sys.exit(1)
        print(f'Sprint: {sprint.get("name", "?")} (id={sprint["id"]}, state={sprint.get("state", "?")})')
        jql = f'sprint = {sprint["id"]} ORDER BY rank ASC'
        skip_incremental = True
    elif args.jql:
        jql = args.jql
    else:
        project_key = args.project or env.get("JIRA_PROJECT_KEY") or os.environ.get("JIRA_PROJECT_KEY", "")
        if not project_key:
            print("Error: No project specified. Use --project, --jql, or set JIRA_PROJECT_KEY in .env.", file=sys.stderr)
            sys.exit(1)
        jql = f"project = {project_key} ORDER BY updated DESC"

    state = load_state()
    synced: dict[str, str] = state.get("synced", {})  # key → updated timestamp
    output_dir = load_output_dir(env)
    output_dir.mkdir(parents=True, exist_ok=True)

    # For incremental sync, narrow the JQL to only recently-updated tickets
    if not skip_incremental and not args.force and synced:
        last_sync = state.get("last_sync")
        if last_sync:
            incremental_jql = f"({jql}) AND updated > \"{last_sync}\""
            print(f"Incremental sync: tickets updated since {last_sync}")
            jql = incremental_jql

    print(f"JQL: {jql}")
    print("Searching ...")

    try:
        issues = search_issues(base_url, auth, jql)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"Error: HTTP {exc.code} — {body}", file=sys.stderr)
        sys.exit(1)

    if not issues:
        print("No tickets found.")
        return

    if args.dry_run:
        print(f"Found {len(issues)} ticket(s) that would be synced to {output_dir}:\n")
        for issue in issues:
            key = issue.get("key", "unknown")
            summary = (issue.get("fields") or {}).get("summary", "")
            status = _safe_str((issue.get("fields") or {}).get("status"), "name")
            print(f"  {key}: {summary}  [{status}]")
        print("\nDry run — no files written.")
        return

    print(f"Found {len(issues)} ticket(s). Writing to {output_dir} ...")
    ok = failed = 0

    for issue in issues:
        key = issue.get("key", "unknown")
        summary = (issue.get("fields") or {}).get("summary", "")
        updated = (issue.get("fields") or {}).get("updated", "")

        try:
            md = compose_ticket_markdown(issue)
            filepath = output_dir / f"{key}.md"
            filepath.write_text(md, encoding="utf-8")
            synced[key] = updated
            print(f"  ✓  {key}: {summary}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗  {key}: {summary}  →  {exc}", file=sys.stderr)
            failed += 1

    # Update state
    state["synced"] = synced
    state["last_sync"] = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M")
    save_state(state)

    print(f"\nDone: {ok} synced, {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
