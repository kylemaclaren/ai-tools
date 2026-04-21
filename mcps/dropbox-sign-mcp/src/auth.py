#!/usr/bin/env python3
"""Set up or rotate the Dropbox Sign API key for the dropbox-sign-mcp server.

Captures the API key in the terminal via getpass so it never appears in the
LLM chat, transcript, or model context. Writes DROPBOX_SIGN_API_KEY (and
optionally DROPBOX_SIGN_CLIENT_ID for custom branding) directly to your
editor's MCP config JSON, then asks you to restart the MCP server.

Usage (rotation — server entry already exists in your MCP config):
    python3 src/auth.py --config ~/.cursor/mcp.json --server-name dropbox-sign

Usage (first-time setup — also offers to set the optional CLIENT_ID and
creates the entry if it does not yet exist):
    python3 src/auth.py --config ~/.cursor/mcp.json --server-name dropbox-sign --first-time

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

API_KEY_URL = "https://app.hellosign.com/home/myAccount#api"


def _prompt_visible(label: str, current: str | None = None) -> str:
    suffix = f" [{current}]" if current else ""
    value = input(f"{label}{suffix}: ").strip()
    if not value and current:
        return current
    return value


def _prompt_secret(label: str) -> str:
    while True:
        value = getpass.getpass(f"{label} (input hidden, press Enter when done): ").strip()
        if value:
            return value
        print("  (empty input — please paste your API key)", file=sys.stderr)


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
            "Securely set up or rotate the Dropbox Sign API key for the "
            "dropbox-sign-mcp server. API key entry uses getpass so the "
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
        default="dropbox-sign",
        help="MCP server name in your config (default: dropbox-sign).",
    )
    parser.add_argument(
        "--first-time",
        action="store_true",
        help="Initial setup: also offer to set the optional "
             "DROPBOX_SIGN_CLIENT_ID, and create the server entry if it "
             "does not yet exist.",
    )
    args = parser.parse_args()

    config_path = Path(os.path.expanduser(args.config)).resolve()

    print("Dropbox Sign API Key Setup")
    print("=" * 40)
    print(f"Config file:     {config_path}")
    print(f"MCP server name: {args.server_name}")
    print(f"Mode:            {'First-time setup' if args.first_time else 'API key rotation'}")
    print()

    data = _load_config(config_path)
    entry = _get_or_create_server_entry(data, args.server_name, args.first_time)
    env = entry["env"]

    print(f"Opening {API_KEY_URL} in your browser...")
    _open_browser(API_KEY_URL)
    print()
    print("Create a new API key, copy it, then paste it below.")
    env["DROPBOX_SIGN_API_KEY"] = _prompt_secret("Paste API key")

    if args.first_time:
        print()
        print("Optional: DROPBOX_SIGN_CLIENT_ID enables your branded signing")
        print("experience (the 32-char client_id from a Dropbox Sign API App).")
        print("Press Enter to skip if you don't have one or don't need branding.")
        client_id = _prompt_visible("DROPBOX_SIGN_CLIENT_ID", env.get("DROPBOX_SIGN_CLIENT_ID") or None)
        if client_id:
            env["DROPBOX_SIGN_CLIENT_ID"] = client_id

    _save_config(config_path, data)

    print()
    print(f"  ✓  Updated {config_path} (permissions: 0600)")
    print()
    print("Done. Restart the MCP server in your editor to pick up the new key:")
    print("  • Cursor      → MCP panel → restart this server")
    print("  • Claude Code → /mcp restart")
    print("  • Other hosts → restart the editor session")


if __name__ == "__main__":
    main()
