#!/usr/bin/env python3
"""Set up or rotate the Atlassian API token for the atlassian-internal MCP server.

Captures the token in the terminal via getpass so it never appears in the LLM
chat, transcript, or model context. Writes JIRA_BASE_URL, JIRA_EMAIL, and
JIRA_API_TOKEN directly to your editor's MCP config JSON, then asks you to
restart the MCP server.

Usage (rotation — token already known to the MCP server entry):
    python3 src/auth.py --config ~/.cursor/mcp.json --server-name atlassian-internal

Usage (first-time setup — also collects base URL + email and creates the entry
if it does not already exist):
    python3 src/auth.py --config ~/.cursor/mcp.json --server-name atlassian-internal --first-time

The --config path must point at an MCP config file in the standard
{"mcpServers": {<name>: {"env": {...}, ...}}} JSON shape (Cursor, Claude
Code, and other JSON-based MCP hosts). Editors that use a different config
format (e.g. Codex's TOML) are not supported by this helper — for those,
update the config file by hand.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import webbrowser
from pathlib import Path

TOKEN_URL = "https://id.atlassian.com/manage-profile/security/api-tokens"


def _prompt_visible(label: str, current: str | None = None) -> str:
    suffix = f" [{current}]" if current else ""
    value = input(f"{label}{suffix}: ").strip()
    if not value and current:
        return current
    return value


def _normalize_base_url(url: str) -> str:
    """Ensure the Jira base URL has an https:// scheme and no trailing slash."""
    url = url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _prompt_secret(label: str) -> str:
    while True:
        value = getpass.getpass(f"{label} (input hidden, press Enter when done): ").strip()
        if value:
            return value
        print("  (empty input — please paste your token)", file=sys.stderr)


def _load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {"mcpServers": {}}
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"Error: {config_path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"Error: {config_path} top-level value must be a JSON object.", file=sys.stderr)
        sys.exit(1)
    return data


def _save_config(config_path: Path, data: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    # Restrict permissions: owner read/write only, since this file holds secrets.
    # Best-effort — silently ignore on filesystems that don't support chmod.
    try:
        os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _get_or_create_server_entry(data: dict, server_name: str, first_time: bool) -> dict:
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        print(
            "Error: 'mcpServers' in your config is not a JSON object.",
            file=sys.stderr,
        )
        sys.exit(1)
    if server_name not in servers:
        if not first_time:
            print(
                f"Error: no MCP server named '{server_name}' in {list(servers) or '<empty>'}.\n"
                f"Re-run with --first-time to create it, or correct --server-name.",
                file=sys.stderr,
            )
            sys.exit(1)
        servers[server_name] = {"env": {}}
    entry = servers[server_name]
    if not isinstance(entry, dict):
        print(f"Error: server entry '{server_name}' is not a JSON object.", file=sys.stderr)
        sys.exit(1)
    env = entry.setdefault("env", {})
    if not isinstance(env, dict):
        print(f"Error: 'env' for '{server_name}' is not a JSON object.", file=sys.stderr)
        sys.exit(1)
    return entry


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        print(f"  (couldn't open browser automatically — visit {url} manually)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Securely set up or rotate the Atlassian API token for the "
            "atlassian-internal MCP server. Token entry uses getpass so the "
            "value never enters the LLM chat or context."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to your editor's MCP config JSON (e.g. ~/.cursor/mcp.json).",
    )
    parser.add_argument(
        "--server-name",
        default="atlassian-internal",
        help="MCP server name in your config (default: atlassian-internal).",
    )
    parser.add_argument(
        "--first-time",
        action="store_true",
        help="Initial setup: also prompt for JIRA_BASE_URL and JIRA_EMAIL, "
             "and create the server entry if it does not yet exist.",
    )
    args = parser.parse_args()

    config_path = Path(os.path.expanduser(args.config)).resolve()

    print("Atlassian API Token Setup")
    print("=" * 40)
    print(f"Config file:     {config_path}")
    print(f"MCP server name: {args.server_name}")
    print(f"Mode:            {'First-time setup' if args.first_time else 'Token rotation'}")
    print()

    data = _load_config(config_path)
    entry = _get_or_create_server_entry(data, args.server_name, args.first_time)
    env = entry["env"]

    if args.first_time:
        print("Step 1 of 2 — Jira instance details")
        print("  JIRA_BASE_URL looks like https://acme.atlassian.net")
        print("  JIRA_EMAIL is the address you use to sign in to Atlassian.")
        print()
        env["JIRA_BASE_URL"] = _normalize_base_url(
            _prompt_visible("JIRA_BASE_URL", env.get("JIRA_BASE_URL") or None)
        )
        env["JIRA_EMAIL"] = _prompt_visible("JIRA_EMAIL", env.get("JIRA_EMAIL") or None)
        print()
        print("Step 2 of 2 — API token")
    else:
        if not env.get("JIRA_BASE_URL") or not env.get("JIRA_EMAIL"):
            print(
                "Warning: JIRA_BASE_URL or JIRA_EMAIL is missing from this server entry.\n"
                "Re-run with --first-time to set those alongside the token.",
                file=sys.stderr,
            )
        print("API token rotation")

    print()
    print(f"Opening {TOKEN_URL} in your browser...")
    _open_browser(TOKEN_URL)
    print()
    print("Create a new token, copy it, then paste it below.")
    env["JIRA_API_TOKEN"] = _prompt_secret("Paste new token")

    _save_config(config_path, data)

    print()
    print(f"  ✓  Updated {config_path} (permissions: 0600)")
    print()
    print("Done. Restart the MCP server in your editor to pick up the new token:")
    print("  • Cursor      → MCP panel → restart this server")
    print("  • Claude Code → /mcp restart")
    print("  • Other hosts → restart the editor session")


if __name__ == "__main__":
    main()
