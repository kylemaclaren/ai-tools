"""
Atlassian Unofficial MCP Server

Exposes tools for Jira Cloud (search, read, create, update issues) and
Confluence Cloud (fetch pages, comments, search, create/update pages)
directly from the LLM via MCP -- no local files are created.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated

import markdown as _md_lib

from mcp.server.fastmcp import FastMCP

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
VERSION_URL = (
    "https://raw.githubusercontent.com/kylemaclaren/ai-tools/main"
    "/mcps/atlassian-unofficial-mcp/VERSION"
)

_version_cache: dict = {}
_VERSION_CACHE_TTL = 3600


def _version_warning() -> str:
    if VERSION == "unknown":
        return ""
    now = time.time()
    if _version_cache.get("latest") and now - _version_cache.get("checked_at", 0) < _VERSION_CACHE_TTL:
        latest = _version_cache["latest"]
    else:
        try:
            req = urllib.request.Request(VERSION_URL, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                latest = resp.read().decode().strip()
            _version_cache["latest"] = latest
            _version_cache["checked_at"] = now
        except Exception:
            return ""
    if latest != VERSION:
        return (
            f"\n\n---\n"
            f"_atlassian-unofficial-mcp update available: you're on **v{VERSION}**, latest is **v{latest}**. "
            f"Run `git pull` in your atlassian-unofficial-mcp directory to update._"
        )
    return ""


mcp = FastMCP(
    "Atlassian Unofficial",
    instructions=(
        "Use this server to work with Jira Cloud issues and Confluence Cloud "
        "pages directly. All data comes from the Atlassian API in real-time "
        "-- no local files are created.\n\n"

        "== JIRA READING ==\n"
        "- search_issues: Run any JQL query. Returns a compact summary.\n"
        "- get_issue: Full details for one issue (description + comments).\n"
        "- get_sprint_issues: Active-sprint shortcut (finds board + sprint).\n"
        "- list_projects: Discover available projects.\n"
        "- get_issue_types: Valid issue types for a project.\n\n"

        "== COMMON JQL PATTERNS ==\n"
        "- project = PROJ ORDER BY updated DESC\n"
        "- project = PROJ AND status = 'In Progress'\n"
        "- sprint in openSprints() AND project = PROJ\n"
        "- parent = PROJ-42 ORDER BY rank ASC  (epic children)\n"
        "- assignee = currentUser() AND resolution = Unresolved\n"
        "- project = PROJ AND updated >= -7d\n"
        "- labels = 'design-partner' AND status != Done\n\n"

        "== CONFLUENCE READING ==\n"
        "- get_confluence_page: Fetch a page by URL or page ID.\n"
        "- get_page_comments: All comments on a page, threaded, with IDs.\n"
        "- search_confluence: Run a CQL query against Confluence.\n"
        "- list_spaces: Discover available Confluence spaces.\n\n"

        "== COMMON CQL PATTERNS ==\n"
        "- space = SPACE AND type = page ORDER BY lastModified DESC\n"
        "- space = SPACE AND text ~ \"search term\"\n"
        "- ancestor = 12345 AND type = page  (children of a page)\n"
        "- label = \"api-docs\" AND space = SPACE\n"
        "- creator = currentUser() AND type = page\n"
        "- type = page AND lastModified >= now(\"-7d\")\n\n"

        "== COMMENT REPLY WORKFLOW ==\n"
        "When the user wants to review and reply to Confluence comments:\n"
        "1. Call get_page_comments to fetch all comments with IDs.\n"
        "2. Summarize the comments in chat (themes, questions, who said what).\n"
        "3. Draft ONE reply at a time in chat when the user asks.\n"
        "4. Let the user iterate on the draft in conversation.\n"
        "5. Only call reply_to_comment after the user confirms.\n"
        "6. NEVER batch-post multiple replies without individual confirmation.\n\n"

        "== WRITING ==\n"
        "Before calling ANY write tool (create_issue, update_issue, "
        "add_comment, transition_issue, assign_issue, link_issues, "
        "create_confluence_page, update_confluence_page, reply_to_comment), "
        "ALWAYS present the full details of what you plan to do in chat "
        "and wait for the user to confirm.\n"
        "For bulk operations (multiple creates or updates), list EVERY "
        "planned change and get explicit confirmation before proceeding.\n"
    ),
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PAGE_SIZE = 50
REQUEST_DELAY = 0.15
RATE_LIMIT_BACKOFF = 10.0

_config: dict[str, str] = {}

TOKEN_URL = "https://id.atlassian.com/manage-profile/security/api-tokens"


class JiraError(Exception):
    pass


def _handle_auth_error(http_code: int) -> None:
    """Raise a JiraError with instructions for the LLM to drive a secure rotation."""
    raise JiraError(
        f"Your Atlassian API token has expired (HTTP {http_code}).\n\n"
        f"Ask your AI to rotate the token by running this MCP's bundled auth helper:\n"
        f"  python3 <atlassian-unofficial-mcp-dir>/src/auth.py "
        f"--config <your-mcp-config-path> --server-name atlassian-unofficial\n\n"
        f"The helper opens {TOKEN_URL} in your browser, prompts for the new "
        f"token in the terminal (input is hidden — the token never enters "
        f"chat or the model context), and writes it directly to your MCP "
        f"config. Then restart the MCP server (Cursor → MCP panel → restart, "
        f"Claude Code → /mcp restart)."
    )


def _cfg() -> dict[str, str]:
    if not _config:
        base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
        email = os.environ.get("JIRA_EMAIL", "")
        token = os.environ.get("JIRA_API_TOKEN", "")
        if not base_url or not email or not token:
            raise JiraError(
                "JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN must be set."
            )
        creds = base64.b64encode(f"{email}:{token}".encode()).decode()
        _config.update({
            "base_url": base_url,
            "confluence_base": base_url + "/wiki",
            "auth": f"Basic {creds}",
            "project": os.environ.get("JIRA_PROJECT_KEY", ""),
            "confluence_space": os.environ.get("CONFLUENCE_SPACE_KEY", ""),
        })
    return _config


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _api_get(url: str, *, retries: int = 3) -> dict | list:
    cfg = _cfg()
    headers = {"Authorization": cfg["auth"], "Accept": "application/json"}
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


def _api_request(
    url: str, *, method: str = "GET", body: dict | None = None, retries: int = 3,
) -> dict | None:
    cfg = _cfg()
    headers: dict[str, str] = {
        "Authorization": cfg["auth"],
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


def _api_post(url: str, body: dict) -> dict:
    return _api_request(url, method="POST", body=body) or {}


def _api_put(url: str, body: dict) -> None:
    _api_request(url, method="PUT", body=body)


def _format_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode(errors="replace")
    except Exception:
        body = str(exc)
    return f"Atlassian API error (HTTP {exc.code}): {body}"


# ---------------------------------------------------------------------------
# Jira API wrappers
# ---------------------------------------------------------------------------

def _search(jql: str, max_results: int = PAGE_SIZE) -> list[dict]:
    base = _cfg()["base_url"]
    issues: list[dict] = []
    next_token: str | None = None
    while len(issues) < max_results:
        query: dict[str, str | int] = {
            "jql": jql,
            "maxResults": min(PAGE_SIZE, max_results - len(issues)),
            "fields": "summary,status,priority,issuetype,assignee,reporter,"
                       "created,updated,labels,description,comment",
            "expand": "renderedFields",
        }
        if next_token:
            query["nextPageToken"] = next_token
        params = urllib.parse.urlencode(query)
        url = f"{base}/rest/api/3/search/jql?{params}"
        data = _api_get(url)
        batch = data.get("issues", [])
        issues.extend(batch)
        next_token = data.get("nextPageToken")
        if not next_token or not batch:
            break
    return issues


def _get_single_issue(key: str) -> dict:
    base = _cfg()["base_url"]
    fields = ("summary,status,priority,issuetype,assignee,reporter,"
              "created,updated,labels,description,comment")
    url = f"{base}/rest/api/3/issue/{key}?fields={fields}&expand=renderedFields"
    return _api_get(url)


def _list_projects() -> list[dict]:
    base = _cfg()["base_url"]
    url = f"{base}/rest/api/3/project/search?maxResults=100&orderBy=key"
    data = _api_get(url)
    return data.get("values", [])


def _create(fields: dict) -> dict:
    base = _cfg()["base_url"]
    return _api_post(f"{base}/rest/api/3/issue", {"fields": fields})


def _update(key: str, fields: dict) -> None:
    base = _cfg()["base_url"]
    _api_put(f"{base}/rest/api/3/issue/{key}", {"fields": fields})


def _comment(key: str, body_adf: dict) -> dict:
    base = _cfg()["base_url"]
    return _api_post(f"{base}/rest/api/3/issue/{key}/comment", {"body": body_adf})


def _find_board(project_key: str) -> int | None:
    base = _cfg()["base_url"]
    params = urllib.parse.urlencode({"projectKeyOrId": project_key, "maxResults": 10})
    data = _api_get(f"{base}/rest/agile/1.0/board?{params}")
    boards = data.get("values", [])
    return boards[0]["id"] if boards else None


def _find_sprint(board_id: int, name: str | None = None) -> dict | None:
    base = _cfg()["base_url"]
    if name:
        url = f"{base}/rest/agile/1.0/board/{board_id}/sprint?maxResults=100"
        data = _api_get(url)
        needle = name.lower()
        for s in data.get("values", []):
            if needle in s.get("name", "").lower():
                return s
        return None
    url = f"{base}/rest/agile/1.0/board/{board_id}/sprint?state=active&maxResults=1"
    data = _api_get(url)
    sprints = data.get("values", [])
    return sprints[0] if sprints else None


def _get_transitions(key: str) -> list[dict]:
    base = _cfg()["base_url"]
    data = _api_get(f"{base}/rest/api/3/issue/{key}/transitions")
    return data.get("transitions", [])


def _do_transition(key: str, transition_id: str) -> None:
    base = _cfg()["base_url"]
    _api_post(f"{base}/rest/api/3/issue/{key}/transitions", {"transition": {"id": transition_id}})


def _search_users(query: str) -> list[dict]:
    base = _cfg()["base_url"]
    params = urllib.parse.urlencode({"query": query, "maxResults": 10})
    return _api_get(f"{base}/rest/api/3/user/search?{params}")


def _set_assignee(key: str, account_id: str | None) -> None:
    base = _cfg()["base_url"]
    _api_put(f"{base}/rest/api/3/issue/{key}/assignee", {"accountId": account_id})


def _create_link(from_key: str, to_key: str, link_type: str) -> None:
    base = _cfg()["base_url"]
    _api_post(f"{base}/rest/api/3/issueLink", {
        "type": {"name": link_type},
        "inwardIssue": {"key": from_key},
        "outwardIssue": {"key": to_key},
    })


def _resolve_project(project_key: str) -> str:
    key = project_key.strip() or _cfg()["project"]
    if not key:
        raise JiraError(
            "No project specified and JIRA_PROJECT_KEY is not set. "
            "Pass a project_key or set the environment variable."
        )
    return key


def _get_project_issue_types(project_key: str) -> list[dict]:
    base = _cfg()["base_url"]
    try:
        data = _api_get(f"{base}/rest/api/3/issue/createmeta/{project_key}/issuetypes")
        return data.get("issueTypes", data.get("values", []))
    except urllib.error.HTTPError:
        data = _api_get(f"{base}/rest/api/3/project/{project_key}")
        return data.get("issueTypes", [])


# ---------------------------------------------------------------------------
# Markdown → ADF conversion
# ---------------------------------------------------------------------------

_RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
_RE_BULLET = re.compile(r"^(\s*)[-*]\s+(.*)")
_RE_ORDERED = re.compile(r"^(\s*)\d+\.\s+(.*)")
_RE_CODE_FENCE = re.compile(r"^```(\w*)")
_RE_RULE = re.compile(r"^---+\s*$")


def _parse_inline(text: str) -> list[dict]:
    nodes: list[dict] = []
    combined = re.compile(
        r"(\[([^\]]+)\]\(([^)]+)\))"
        r"|(\*\*\*(.+?)\*\*\*)"
        r"|(\*\*(.+?)\*\*)"
        r"|(\*(.+?)\*)"
        r"|(`([^`]+)`)"
    )
    pos = 0
    for m in combined.finditer(text):
        if m.start() > pos:
            plain = text[pos:m.start()]
            if plain:
                nodes.append({"type": "text", "text": plain})
        if m.group(2) is not None:
            nodes.append({
                "type": "text", "text": m.group(2),
                "marks": [{"type": "link", "attrs": {"href": m.group(3)}}],
            })
        elif m.group(5) is not None:
            nodes.append({
                "type": "text", "text": m.group(5),
                "marks": [{"type": "strong"}, {"type": "em"}],
            })
        elif m.group(7) is not None:
            nodes.append({
                "type": "text", "text": m.group(7),
                "marks": [{"type": "strong"}],
            })
        elif m.group(9) is not None:
            nodes.append({
                "type": "text", "text": m.group(9),
                "marks": [{"type": "em"}],
            })
        elif m.group(11) is not None:
            nodes.append({
                "type": "text", "text": m.group(11),
                "marks": [{"type": "code"}],
            })
        pos = m.end()
    if pos < len(text):
        tail = text[pos:]
        if tail:
            nodes.append({"type": "text", "text": tail})
    if not nodes:
        nodes.append({"type": "text", "text": text})
    return nodes


def _collect_list_items(
    lines: list[str], start: int, pattern: re.Pattern, base_indent: int,
) -> tuple[list[dict], int]:
    items: list[dict] = []
    i = start
    while i < len(lines):
        m = pattern.match(lines[i])
        if not m:
            break
        indent = len(m.group(1))
        if indent != base_indent:
            break
        items.append({
            "type": "listItem",
            "content": [{"type": "paragraph", "content": _parse_inline(m.group(2))}],
        })
        i += 1
    return items, i


def _markdown_to_adf(md: str) -> dict:
    doc: dict = {"type": "doc", "version": 1, "content": []}
    lines = md.split("\n")
    i = 0
    para_lines: list[str] = []

    def _flush():
        text = " ".join(para_lines).strip()
        if text:
            doc["content"].append({"type": "paragraph", "content": _parse_inline(text)})
        para_lines.clear()

    while i < len(lines):
        line = lines[i]

        m_fence = _RE_CODE_FENCE.match(line)
        if m_fence:
            _flush()
            lang = m_fence.group(1) or None
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            node: dict = {
                "type": "codeBlock",
                "content": [{"type": "text", "text": "\n".join(code_lines)}],
            }
            if lang:
                node["attrs"] = {"language": lang}
            doc["content"].append(node)
            continue

        if _RE_RULE.match(line):
            _flush()
            doc["content"].append({"type": "rule"})
            i += 1
            continue

        m_head = _RE_HEADING.match(line)
        if m_head:
            _flush()
            level = len(m_head.group(1))
            doc["content"].append({
                "type": "heading",
                "attrs": {"level": level},
                "content": _parse_inline(m_head.group(2)),
            })
            i += 1
            continue

        m_bullet = _RE_BULLET.match(line)
        if m_bullet:
            _flush()
            indent = len(m_bullet.group(1))
            items, i = _collect_list_items(lines, i, _RE_BULLET, indent)
            doc["content"].append({"type": "bulletList", "content": items})
            continue

        m_ordered = _RE_ORDERED.match(line)
        if m_ordered:
            _flush()
            indent = len(m_ordered.group(1))
            items, i = _collect_list_items(lines, i, _RE_ORDERED, indent)
            doc["content"].append({"type": "orderedList", "content": items})
            continue

        if not line.strip():
            _flush()
            i += 1
            continue

        para_lines.append(line)
        i += 1

    _flush()
    return doc


# ---------------------------------------------------------------------------
# HTML → Markdown conversion
# ---------------------------------------------------------------------------

class _HtmlToMd(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._list_stack: list[str] = []
        self._ol_counter: list[int] = []
        self._href: str | None = None
        self._in_pre = False
        self._in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._parts.append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self._parts.append("\n\n")
        elif tag == "br":
            self._parts.append("\n")
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
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

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_markdown(self) -> str:
        raw = "".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _html_to_md(html: str | None) -> str:
    if not html:
        return ""
    parser = _HtmlToMd()
    parser.feed(html)
    return parser.get_markdown()


# ---------------------------------------------------------------------------
# ADF → plain text fallback
# ---------------------------------------------------------------------------

def _adf_to_text(node: dict | str | None) -> str:
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
# Issue formatting
# ---------------------------------------------------------------------------

def _safe(obj: dict | None, *keys: str) -> str:
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


def _format_issue_full(issue: dict) -> str:
    """Format a single issue with full details (description + comments)."""
    fields = issue.get("fields", {})
    rendered = issue.get("renderedFields", {})
    key = issue.get("key", "")
    base_url = _cfg()["base_url"]

    summary = fields.get("summary", "")
    status = _safe(fields.get("status"), "name")
    priority = _safe(fields.get("priority"), "name")
    issue_type = _safe(fields.get("issuetype"), "name")
    assignee = _safe(fields.get("assignee"), "displayName")
    reporter = _safe(fields.get("reporter"), "displayName")
    labels = ", ".join(fields.get("labels", []))
    created = _parse_date(fields.get("created", ""))
    updated = _parse_date(fields.get("updated", ""))

    desc_html = rendered.get("description")
    description = _html_to_md(desc_html) if desc_html else _adf_to_text(fields.get("description")).strip()

    sections: list[str] = []

    fm = ["---", f"key: {key}", f"summary: {summary}", f"status: {status}"]
    if priority:
        fm.append(f"priority: {priority}")
    if issue_type:
        fm.append(f"type: {issue_type}")
    if assignee:
        fm.append(f"assignee: {assignee}")
    if reporter:
        fm.append(f"reporter: {reporter}")
    fm.extend([f"created: {created}", f"updated: {updated}"])
    if labels:
        fm.append(f"labels: {labels}")
    fm.append(f"url: {base_url}/browse/{key}")
    fm.append("---")
    sections.append("\n".join(fm))

    sections.append(f"# {key}: {summary}")

    meta = []
    if status:
        meta.append(f"**Status:** {status}")
    if priority:
        meta.append(f"**Priority:** {priority}")
    if issue_type:
        meta.append(f"**Type:** {issue_type}")
    if meta:
        sections.append(" | ".join(meta))

    detail = []
    if assignee:
        detail.append(f"**Assignee:** {assignee}")
    if reporter:
        detail.append(f"**Reporter:** {reporter}")
    if detail:
        sections.append(" | ".join(detail))

    if labels:
        sections.append(f"**Labels:** {labels}")

    sections.append("## Description\n\n" + (description or "_No description._"))

    raw_comments = (rendered.get("comment", {}) or {}).get("comments", [])
    if not raw_comments:
        raw_comments = (fields.get("comment", {}) or {}).get("comments", [])

    if raw_comments:
        comment_parts = ["## Comments"]
        for c in raw_comments:
            author = _safe(c.get("author"), "displayName") or "Unknown"
            date = _parse_date(c.get("created", ""))
            body_html = c.get("renderedBody") or c.get("body")
            if isinstance(body_html, str):
                body = _html_to_md(body_html)
            elif isinstance(body_html, dict):
                body = _adf_to_text(body_html).strip()
            else:
                body = ""
            comment_parts.append(f"### {author} ({date})\n\n{body}")
        sections.append("\n\n".join(comment_parts))

    return "\n\n".join(sections) + "\n"


def _format_issue_row(issue: dict) -> str:
    """One-line summary for search results."""
    fields = issue.get("fields", {})
    key = issue.get("key", "")
    summary = fields.get("summary", "")
    status = _safe(fields.get("status"), "name")
    priority = _safe(fields.get("priority"), "name")
    issue_type = _safe(fields.get("issuetype"), "name")
    assignee = _safe(fields.get("assignee"), "displayName") or "Unassigned"

    parts = []
    if issue_type:
        parts.append(issue_type)
    if priority:
        parts.append(priority)
    tag = ", ".join(parts)

    return f"- **{key}** [{tag}] {summary} — *{status}, {assignee}*"


# ---------------------------------------------------------------------------
# MCP Tools — Reading
# ---------------------------------------------------------------------------

@mcp.tool()
def search_issues(
    jql: Annotated[str, "JQL query to search for issues"],
    max_results: Annotated[int, "Maximum issues to return (default 20, max 50)"] = 20,
) -> str:
    """Search Jira issues using JQL. Returns a compact summary list."""
    try:
        max_results = min(max(1, max_results), 50)
        issues = _search(jql, max_results)
        if not issues:
            return f"No issues found for: {jql}"
        lines = [f"Found {len(issues)} issue(s) for: `{jql}`\n"]
        for issue in issues:
            lines.append(_format_issue_row(issue))
        return "\n".join(lines) + _version_warning()
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def get_issue(
    issue_key: Annotated[str, "Jira issue key (e.g. PROJ-123)"],
) -> str:
    """Get a single Jira issue with full description, comments, and metadata."""
    try:
        issue = _get_single_issue(issue_key)
        return _format_issue_full(issue) + _version_warning()
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def list_projects() -> str:
    """List all Jira projects accessible to the authenticated user."""
    try:
        projects = _list_projects()
        if not projects:
            return "No projects found."
        lines = ["| Key | Name |", "|-----|------|"]
        for p in projects:
            lines.append(f"| {p.get('key', '')} | {p.get('name', '')} |")
        return "\n".join(lines)
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def get_sprint_issues(
    project_key: Annotated[str, "Project key (e.g. REPLAY). Leave empty to use default."] = "",
    sprint_name: Annotated[str, "Sprint name to search for; leave empty for active sprint"] = "",
) -> str:
    """Get all issues in a sprint. Defaults to the active sprint."""
    try:
        project_key = _resolve_project(project_key)
        board_id = _find_board(project_key)
        if not board_id:
            return f"No board found for project {project_key}."
        sprint = _find_sprint(board_id, sprint_name or None)
        if not sprint:
            label = f'matching "{sprint_name}"' if sprint_name else "active"
            return f"No {label} sprint found for project {project_key}."

        sprint_display = sprint.get("name", "?")
        jql = f'sprint = {sprint["id"]} ORDER BY rank ASC'
        issues = _search(jql)
        if not issues:
            return f"No issues in sprint '{sprint_display}'."

        lines = [f"**Sprint: {sprint_display}** ({len(issues)} issues)\n"]
        for issue in issues:
            lines.append(_format_issue_row(issue))
        return "\n".join(lines)
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def get_issue_types(
    project_key: Annotated[str, "Project key (e.g. REPLAY). Leave empty to use default."] = "",
) -> str:
    """List available issue types for a project."""
    try:
        project_key = _resolve_project(project_key)
        types = _get_project_issue_types(project_key)
        if not types:
            return f"No issue types found for project {project_key}."
        lines = [f"Issue types for **{project_key}**:\n"]
        for t in types:
            name = t.get("name", "")
            desc = t.get("description", "")
            subtask = " *(subtask)*" if t.get("subtask") else ""
            lines.append(f"- **{name}**{subtask}" + (f" — {desc}" if desc else ""))
        return "\n".join(lines)
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


# ---------------------------------------------------------------------------
# MCP Tools — Writing (LLM must confirm with user before calling)
# ---------------------------------------------------------------------------

@mcp.tool()
def create_issue(
    project_key: Annotated[str, "Project key (e.g. REPLAY). Leave empty to use default."] = "",
    summary: Annotated[str, "Issue title/summary"] = "",
    description: Annotated[str, "Description in markdown"] = "",
    issue_type: Annotated[str, "Issue type (e.g. Bug, Task, Story)"] = "Task",
    priority: Annotated[str, "Priority (e.g. High, Medium, Low)"] = "",
    labels: Annotated[str, "Comma-separated labels (e.g. 'bug, frontend')"] = "",
    epic_key: Annotated[str, "Parent epic key (e.g. PROJ-42)"] = "",
) -> str:
    """Create a new Jira issue. Present details to user and confirm before calling."""
    try:
        project_key = _resolve_project(project_key)
        if not summary:
            return "Error: summary is required."
        fields: dict = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
        if description:
            fields["description"] = _markdown_to_adf(description)
        if epic_key:
            fields["parent"] = {"key": epic_key}

        resp = _create(fields)
        new_key = resp.get("key", "???")
        base_url = _cfg()["base_url"]
        return f"Created **{new_key}**: {summary}\n{base_url}/browse/{new_key}"
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def update_issue(
    issue_key: Annotated[str, "Jira issue key (e.g. PROJ-123)"],
    summary: Annotated[str, "New summary (empty to keep current)"] = "",
    description: Annotated[str, "New description in markdown (empty to keep current)"] = "",
    priority: Annotated[str, "New priority (empty to keep current)"] = "",
    labels: Annotated[str, "Comma-separated labels; use 'CLEAR' to remove all; empty to keep current"] = "",
) -> str:
    """Update a Jira issue. Present changes to user and confirm before calling."""
    try:
        fields: dict = {}
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = _markdown_to_adf(description)
        if priority:
            fields["priority"] = {"name": priority}
        if labels == "CLEAR":
            fields["labels"] = []
        elif labels:
            fields["labels"] = [l.strip() for l in labels.split(",") if l.strip()]

        if not fields:
            return "Nothing to update — all fields were empty."

        _update(issue_key, fields)
        updated = ", ".join(fields.keys())
        return f"Updated **{issue_key}** (fields: {updated})."
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def add_comment(
    issue_key: Annotated[str, "Jira issue key (e.g. PROJ-123)"],
    comment: Annotated[str, "Comment text in markdown"],
) -> str:
    """Add a comment to a Jira issue. Show the comment to user and confirm first."""
    try:
        body_adf = _markdown_to_adf(comment)
        _comment(issue_key, body_adf)
        return f"Comment added to **{issue_key}**."
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def transition_issue(
    issue_key: Annotated[str, "Jira issue key (e.g. PROJ-123)"],
    status_name: Annotated[str, "Target status name (e.g. 'In Progress', 'Done')"],
) -> str:
    """Move a Jira issue to a new status. Confirm with user before calling."""
    try:
        transitions = _get_transitions(issue_key)
        needle = status_name.lower()
        match = None
        for t in transitions:
            if needle == t.get("name", "").lower() or needle == _safe(t.get("to"), "name").lower():
                match = t
                break

        if not match:
            available = ", ".join(
                t.get("name", "") or _safe(t.get("to"), "name")
                for t in transitions
            )
            return (
                f"Cannot transition {issue_key} to '{status_name}'. "
                f"Available transitions: {available}"
            )

        _do_transition(issue_key, match["id"])
        target = _safe(match.get("to"), "name") or match.get("name", status_name)
        return f"**{issue_key}** moved to **{target}**."
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def assign_issue(
    issue_key: Annotated[str, "Jira issue key (e.g. PROJ-123)"],
    assignee: Annotated[str, "Email or display name; leave empty or 'unassigned' to clear"] = "",
) -> str:
    """Assign or unassign a Jira issue. Confirm with user before calling."""
    try:
        if not assignee or assignee.lower() == "unassigned":
            _set_assignee(issue_key, None)
            return f"**{issue_key}** unassigned."

        users = _search_users(assignee)
        if not users:
            return f"No Jira user found matching '{assignee}'."
        if len(users) > 1:
            lines = [f"Multiple users match '{assignee}'. Please be more specific:\n"]
            for u in users:
                name = u.get("displayName", "")
                email = u.get("emailAddress", "")
                lines.append(f"- {name} ({email})")
            return "\n".join(lines)

        user = users[0]
        _set_assignee(issue_key, user["accountId"])
        return f"**{issue_key}** assigned to **{user.get('displayName', assignee)}**."
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def link_issues(
    from_key: Annotated[str, "Source issue key (e.g. PROJ-1)"],
    to_key: Annotated[str, "Target issue key (e.g. PROJ-2)"],
    link_type: Annotated[str, "Link type: 'Blocks', 'Relates to', 'Duplicate', etc."] = "Relates to",
) -> str:
    """Create a link between two Jira issues. Confirm with user before calling."""
    try:
        _create_link(from_key, to_key, link_type)
        return f"Linked **{from_key}** → *{link_type}* → **{to_key}**."
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


# ---------------------------------------------------------------------------
# Confluence — URL parsing
# ---------------------------------------------------------------------------

_RE_CONFLUENCE_PAGE_URL = re.compile(r"/wiki/spaces/[^/]+/pages/(\d+)")
_RE_CONFLUENCE_TINY_URL = re.compile(r"/wiki/x/([A-Za-z0-9_-]+)")


def _parse_confluence_url(url_or_id: str) -> str:
    """Extract a Confluence page ID from a URL, or return a bare numeric ID."""
    url_or_id = url_or_id.strip()
    if url_or_id.isdigit():
        return url_or_id
    m = _RE_CONFLUENCE_PAGE_URL.search(url_or_id)
    if m:
        return m.group(1)
    m = _RE_CONFLUENCE_TINY_URL.search(url_or_id)
    if m:
        cfg = _cfg()
        req = urllib.request.Request(
            url_or_id,
            headers={"Authorization": cfg["auth"]},
            method="HEAD",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                m2 = _RE_CONFLUENCE_PAGE_URL.search(resp.url)
                if m2:
                    return m2.group(1)
        except Exception:
            pass
        raise JiraError(f"Could not resolve Confluence tiny URL: {url_or_id}")
    raise JiraError(f"Could not parse Confluence page ID from: {url_or_id}")


# ---------------------------------------------------------------------------
# Confluence — Storage-format XHTML ↔ Markdown
# ---------------------------------------------------------------------------

def _esc_html(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _normalize_list_indent(md: str) -> str:
    """Convert 2-space list indentation to 4-space for the markdown library.

    The ``markdown`` library requires 4-space indentation for nested lists,
    but many documents use 2-space.  This pre-processes the text so nesting
    is preserved.  Fenced code blocks are skipped.
    """
    lines = md.split("\n")
    in_code_block = False

    # Detect the smallest list-item indentation in the document.
    # If it's ≤ 2 we treat the whole file as 2-space and double all indents.
    indent_sizes: list[int] = []
    for line in lines:
        if re.match(r"^\s*```", line):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        m = re.match(r"^( +)([-*]|\d+[.)]) ", line)
        if m:
            indent_sizes.append(len(m.group(1)))

    needs_conversion = bool(indent_sizes) and min(indent_sizes) <= 2

    in_code_block = False
    result: list[str] = []
    for line in lines:
        if re.match(r"^\s*```", line):
            in_code_block = not in_code_block
            result.append(line)
            continue
        if in_code_block:
            result.append(line)
            continue
        if needs_conversion:
            m = re.match(r"^( +)([-*]|\d+[.)]) ", line)
            if m:
                n = len(m.group(1))
                indent_level = n // 2
                remainder = line[n:]
                result.append("    " * indent_level + remainder)
                continue
        result.append(line)
    return "\n".join(result)


def _markdown_to_confluence(md: str) -> str:
    """Convert markdown to Confluence XHTML storage format.

    Uses the ``markdown`` library for full CommonMark + tables support, then
    post-processes the HTML to convert fenced code blocks into Confluence
    ``ac:structured-macro`` elements.
    """
    md = _normalize_list_indent(md)
    html = _md_lib.markdown(
        md,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="xhtml",
    )
    # Convert <pre><code class="language-X">...</code></pre> to Confluence code macro
    def _code_block_to_macro(m: re.Match) -> str:
        lang_attr = m.group(1) or ""
        lang_m = re.search(r'language-(\w+)', lang_attr)
        lang = lang_m.group(1) if lang_m else ""
        code = m.group(2)
        # Unescape HTML entities inside code blocks — CDATA doesn't need them
        code = (
            code
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
        )
        parts = ['<ac:structured-macro ac:name="code" ac:schema-version="1">']
        if lang:
            parts.append(
                f'<ac:parameter ac:name="language">{_esc_html(lang)}</ac:parameter>'
            )
        parts.append(
            f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
        )
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    html = re.sub(
        r"<pre><code([^>]*)>(.*?)</code></pre>",
        _code_block_to_macro,
        html,
        flags=re.DOTALL,
    )
    return html


def _confluence_storage_to_md(html: str) -> str:
    """Convert Confluence XHTML storage format to markdown."""
    if not html:
        return ""
    # Extract code blocks from ac:structured-macro
    def _replace_code_macro(m: re.Match) -> str:
        body = m.group(0)
        lang_m = re.search(r'ac:name="language"[^>]*>([^<]+)', body)
        lang = lang_m.group(1) if lang_m else ""
        code_m = re.search(r'<!\[CDATA\[(.*?)\]\]>', body, re.DOTALL)
        if not code_m:
            code_m = re.search(
                r'<ac:plain-text-body>(.*?)</ac:plain-text-body>', body, re.DOTALL,
            )
        code = code_m.group(1) if code_m else ""
        return f"\n```{lang}\n{code}\n```\n"

    html = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?</ac:structured-macro>',
        _replace_code_macro,
        html,
        flags=re.DOTALL,
    )
    # Info/note/warning/tip panels → blockquotes
    html = re.sub(
        r'<ac:structured-macro[^>]*ac:name="(info|note|warning|tip)"[^>]*>'
        r'.*?<ac:rich-text-body>(.*?)</ac:rich-text-body>.*?</ac:structured-macro>',
        lambda m: f"\n> **{m.group(1).title()}:** {m.group(2)}\n",
        html,
        flags=re.DOTALL,
    )
    # Strip remaining Confluence-specific XML tags, keep inner content
    html = re.sub(r"</?ac:[^>]*>", "", html)
    html = re.sub(r"</?ri:[^>]*>", "", html)
    return _html_to_md(html)


# ---------------------------------------------------------------------------
# Confluence — API wrappers
# ---------------------------------------------------------------------------

def _confluence_get_page_data(page_id: str) -> dict:
    base = _cfg()["confluence_base"]
    url = f"{base}/rest/api/content/{page_id}?expand=body.storage,version,space,ancestors"
    return _api_get(url)


def _confluence_search_pages(cql: str, max_results: int = 25) -> list[dict]:
    base = _cfg()["confluence_base"]
    params = urllib.parse.urlencode({
        "cql": cql,
        "limit": min(max_results, 50),
        "expand": "version,space",
    })
    return _api_get(f"{base}/rest/api/content/search?{params}").get("results", [])


def _confluence_get_all_comments(
    page_id: str,
) -> tuple[list[dict], dict[str, list[dict]]]:
    """Fetch top-level comments and one level of replies for a page."""
    base = _cfg()["confluence_base"]

    def _fetch_comments(parent_id: str) -> list[dict]:
        results: list[dict] = []
        start = 0
        while True:
            url = (
                f"{base}/rest/api/content/{parent_id}/child/comment"
                f"?expand=body.storage,version&start={start}&limit=50"
            )
            data = _api_get(url)
            batch = data.get("results", [])
            results.extend(batch)
            if len(batch) < 50:
                break
            start += 50
        return results

    top_level = _fetch_comments(page_id)
    replies: dict[str, list[dict]] = {}
    for c in top_level:
        cid = c.get("id", "")
        if cid:
            try:
                child_comments = _fetch_comments(cid)
                if child_comments:
                    replies[cid] = child_comments
            except urllib.error.HTTPError:
                pass
    return top_level, replies


def _confluence_create_content(body: dict) -> dict:
    base = _cfg()["confluence_base"]
    return _api_post(f"{base}/rest/api/content", body)


def _confluence_update_content(content_id: str, body: dict) -> None:
    base = _cfg()["confluence_base"]
    _api_put(f"{base}/rest/api/content/{content_id}", body)


def _confluence_list_spaces(max_results: int = 100) -> list[dict]:
    base = _cfg()["confluence_base"]
    url = f"{base}/rest/api/space?limit={min(max_results, 100)}&type=global"
    return _api_get(url).get("results", [])


def _resolve_confluence_space(space_key: str) -> str:
    key = space_key.strip() or _cfg()["confluence_space"]
    if not key:
        raise JiraError(
            "No Confluence space specified and CONFLUENCE_SPACE_KEY is not set. "
            "Pass a space_key or set the environment variable."
        )
    return key


# ---------------------------------------------------------------------------
# Confluence — Formatting helpers
# ---------------------------------------------------------------------------

def _format_confluence_comment(
    comment: dict,
    replies: dict[str, list[dict]],
    depth: int = 0,
) -> str:
    cid = comment.get("id", "")
    version = comment.get("version", {})
    author = _safe(version.get("by"), "displayName") or "Unknown"
    date = _parse_date(version.get("when", ""))
    body_html = comment.get("body", {}).get("storage", {}).get("value", "")
    body = _confluence_storage_to_md(body_html)

    level = "###" if depth == 0 else "####"
    parts = [f"{level} {author} ({date}) [comment_id: {cid}]", "", body]

    for reply in replies.get(cid, []):
        parts.append("")
        parts.append(_format_confluence_comment(reply, {}, depth + 1))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# MCP Tools — Confluence Reading
# ---------------------------------------------------------------------------

@mcp.tool()
def get_confluence_page(
    url_or_id: Annotated[str, "Confluence page URL or numeric page ID"],
) -> str:
    """Fetch a Confluence page by URL or page ID. Returns content as markdown."""
    try:
        page_id = _parse_confluence_url(url_or_id)
        data = _confluence_get_page_data(page_id)

        title = data.get("title", "")
        space_key = _safe(data.get("space"), "key")
        space_name = _safe(data.get("space"), "name")
        version = data.get("version", {}).get("number", "?")
        storage_html = data.get("body", {}).get("storage", {}).get("value", "")
        base = _cfg()["confluence_base"]

        content = _confluence_storage_to_md(storage_html)
        return "\n".join([
            "---",
            f"page_id: {page_id}",
            f"title: {title}",
            f"space: {space_key} ({space_name})",
            f"version: {version}",
            f"url: {base}/spaces/{space_key}/pages/{page_id}",
            "---",
            "",
            f"# {title}",
            "",
            content,
        ]) + _version_warning()
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def get_page_comments(
    url_or_id: Annotated[str, "Confluence page URL or numeric page ID"],
) -> str:
    """Fetch all comments on a Confluence page, threaded with comment IDs for replying."""
    try:
        page_id = _parse_confluence_url(url_or_id)
        top_level, replies = _confluence_get_all_comments(page_id)

        total = len(top_level) + sum(len(v) for v in replies.values())
        if total == 0:
            return "No comments found on this page."

        lines = [f"**{total} comment(s)** on page {page_id}\n"]
        for c in top_level:
            lines.append(_format_confluence_comment(c, replies))
            lines.append("")
        return "\n".join(lines)
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def search_confluence(
    cql: Annotated[str, "CQL query (e.g. 'space = DEV AND text ~ \"deployment\"')"],
    max_results: Annotated[int, "Maximum results (default 20, max 50)"] = 20,
) -> str:
    """Search Confluence pages using CQL. Returns matching page summaries."""
    try:
        max_results = min(max(1, max_results), 50)
        results = _confluence_search_pages(cql, max_results)
        if not results:
            return f"No pages found for: {cql}"

        base = _cfg()["confluence_base"]
        lines = [f"Found {len(results)} page(s) for: `{cql}`\n"]
        for r in results:
            title = r.get("title", "")
            page_id = r.get("id", "")
            space_key = _safe(r.get("space"), "key")
            content_type = r.get("type", "page")
            url = f"{base}/spaces/{space_key}/pages/{page_id}"
            lines.append(f"- **{title}** [{space_key}, {content_type}] — {url}")
        return "\n".join(lines) + _version_warning()
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def list_spaces() -> str:
    """List all Confluence spaces accessible to the authenticated user."""
    try:
        spaces = _confluence_list_spaces()
        if not spaces:
            return "No spaces found."
        lines = ["| Key | Name | Type |", "|-----|------|------|"]
        for s in spaces:
            lines.append(f"| {s.get('key', '')} | {s.get('name', '')} | {s.get('type', '')} |")
        return "\n".join(lines)
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


# ---------------------------------------------------------------------------
# MCP Tools — Confluence Writing (LLM must confirm with user before calling)
# ---------------------------------------------------------------------------

@mcp.tool()
def create_confluence_page(
    title: Annotated[str, "Page title"],
    body: Annotated[str, "Page content in markdown"],
    space_key: Annotated[str, "Space key (e.g. DEV). Leave empty to use default."] = "",
    parent_id: Annotated[str, "Parent page ID to nest under (optional)"] = "",
) -> str:
    """Create a new Confluence page. Present details to user and confirm before calling."""
    try:
        space_key = _resolve_confluence_space(space_key)
        if not title:
            return "Error: title is required."
        if not body:
            return "Error: body is required."

        storage = _markdown_to_confluence(body)
        payload: dict = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": storage, "representation": "storage"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]

        resp = _confluence_create_content(payload)
        page_id = resp.get("id", "???")
        base = _cfg()["confluence_base"]
        return f"Created page **{title}** (ID: {page_id})\n{base}/spaces/{space_key}/pages/{page_id}"
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def update_confluence_page(
    url_or_id: Annotated[str, "Confluence page URL or numeric page ID"],
    title: Annotated[str, "New title (empty to keep current)"] = "",
    body: Annotated[str, "New content in markdown (empty to keep current)"] = "",
) -> str:
    """Update a Confluence page. Auto-increments version. Confirm with user first."""
    try:
        page_id = _parse_confluence_url(url_or_id)
        current = _confluence_get_page_data(page_id)
        current_version = current.get("version", {}).get("number", 0)
        current_title = current.get("title", "")

        new_title = title or current_title
        if body:
            storage = _markdown_to_confluence(body)
        else:
            storage = current.get("body", {}).get("storage", {}).get("value", "")

        if not title and not body:
            return "Nothing to update — both title and body were empty."

        payload = {
            "type": "page",
            "title": new_title,
            "body": {"storage": {"value": storage, "representation": "storage"}},
            "version": {"number": current_version + 1},
        }
        _confluence_update_content(page_id, payload)

        base = _cfg()["confluence_base"]
        space_key = _safe(current.get("space"), "key")
        updated_fields = []
        if title:
            updated_fields.append("title")
        if body:
            updated_fields.append("body")
        return (
            f"Updated page **{new_title}** v{current_version + 1} "
            f"({', '.join(updated_fields)})\n"
            f"{base}/spaces/{space_key}/pages/{page_id}"
        )
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


@mcp.tool()
def reply_to_comment(
    url_or_id: Annotated[str, "Confluence page URL or numeric page ID"],
    body: Annotated[str, "Reply content in markdown"],
    parent_comment_id: Annotated[str, "Comment ID to reply to (empty for new top-level comment)"] = "",
) -> str:
    """Post a comment or reply on a Confluence page. Confirm with user before calling."""
    try:
        page_id = _parse_confluence_url(url_or_id)
        if not body:
            return "Error: body is required."

        storage = _markdown_to_confluence(body)
        payload: dict = {
            "type": "comment",
            "container": {"id": page_id, "type": "page"},
            "body": {"storage": {"value": storage, "representation": "storage"}},
        }
        if parent_comment_id:
            payload["ancestors"] = [{"id": parent_comment_id}]

        resp = _confluence_create_content(payload)
        comment_id = resp.get("id", "???")

        if parent_comment_id:
            return f"Reply posted (comment_id: {comment_id}) to comment {parent_comment_id}."
        return f"Comment posted (comment_id: {comment_id}) on page {page_id}."
    except JiraError as exc:
        return f"Error: {exc}"
    except urllib.error.HTTPError as exc:
        return _format_http_error(exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
