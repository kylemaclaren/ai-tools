#!/usr/bin/env python3
"""Set up or rotate the Atlassian API token in jira-sync's .env file.

Captures the token in the terminal via getpass so it never appears in the
LLM chat, transcript, or model context. Writes JIRA_API_TOKEN (and on first
run, JIRA_BASE_URL, JIRA_EMAIL, JIRA_PROJECT_KEY, and OUTPUT_DIR) directly
to the jira-sync .env file.

Usage (rotation — .env already exists, just need a fresh token):
    python3 auth.py

Usage (first-time setup — also collects the other config values and creates
the .env file if it does not yet exist):
    python3 auth.py --first-time

Optional flags:
    --env PATH       Path to the .env file (default: <script-dir>/.env).
    --first-time     Run the full first-time prompt sequence.

This helper is intentionally separate from any MCP server's token rotation.
If you also use the atlassian-unofficial-mcp (or atlassian-internal-mcp)
and want a single token across both, run that MCP's bundled auth.py
afterwards — it writes to your editor's MCP config, not to .env.
"""

from __future__ import annotations

import argparse
import getpass
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


def _parse_env(env_path: Path) -> dict[str, str]:
    """Parse a .env file into an ordered dict, preserving existing keys.

    Lines that are blank or comments are not returned (we re-emit fresh
    formatting on save). Quoted values are stripped of surrounding quotes.
    """
    if not env_path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _save_env(env_path: Path, values: dict[str, str]) -> None:
    """Write values to .env in a stable, well-commented order."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [
        "JIRA_BASE_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "JIRA_PROJECT_KEY",
        "OUTPUT_DIR",
    ]
    seen = set()
    lines = [
        "# jira-sync configuration",
        f"# Generate or rotate API tokens at: {TOKEN_URL}",
        "",
    ]
    for key in ordered_keys:
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)
    extras = [k for k in values if k not in seen]
    if extras:
        lines.append("")
        for key in extras:
            lines.append(f"{key}={values[key]}")
    env_path.write_text("\n".join(lines) + "\n")
    # Restrict permissions: owner read/write only, since this file holds a token.
    # Best-effort — silently ignore on filesystems that don't support chmod.
    try:
        os.chmod(env_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        print(f"  (couldn't open browser automatically — visit {url} manually)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Securely set up or rotate the Atlassian API token in jira-sync's "
            ".env file. Token entry uses getpass so the value never enters "
            "the LLM chat or context."
        )
    )
    parser.add_argument(
        "--env",
        default=str(Path(__file__).resolve().parent / ".env"),
        help="Path to the .env file (default: <jira-sync-dir>/.env).",
    )
    parser.add_argument(
        "--first-time",
        action="store_true",
        help="Initial setup: also prompt for JIRA_BASE_URL, JIRA_EMAIL, "
             "JIRA_PROJECT_KEY, and OUTPUT_DIR.",
    )
    args = parser.parse_args()

    env_path = Path(os.path.expanduser(args.env)).resolve()

    print("jira-sync API Token Setup")
    print("=" * 40)
    print(f"Env file: {env_path}")
    print(f"Mode:     {'First-time setup' if args.first_time else 'Token rotation'}")
    print()

    values = _parse_env(env_path)

    if args.first_time:
        print("Step 1 of 2 — Jira instance details")
        print("  JIRA_BASE_URL looks like https://acme.atlassian.net")
        print("  JIRA_EMAIL is the address you use to sign in to Atlassian.")
        print("  JIRA_PROJECT_KEY is the default project to sync (e.g. PROJ).")
        print("  OUTPUT_DIR is where ticket markdown files get written.")
        print()
        values["JIRA_BASE_URL"] = _normalize_base_url(
            _prompt_visible("JIRA_BASE_URL", values.get("JIRA_BASE_URL"))
        )
        values["JIRA_EMAIL"] = _prompt_visible(
            "JIRA_EMAIL", values.get("JIRA_EMAIL")
        )
        values["JIRA_PROJECT_KEY"] = _prompt_visible(
            "JIRA_PROJECT_KEY", values.get("JIRA_PROJECT_KEY") or "PROJ"
        )
        values["OUTPUT_DIR"] = _prompt_visible(
            "OUTPUT_DIR", values.get("OUTPUT_DIR") or "~/jira/"
        )
        print()
        print("Step 2 of 2 — API token")
    else:
        if not values.get("JIRA_BASE_URL") or not values.get("JIRA_EMAIL"):
            print(
                "Warning: JIRA_BASE_URL or JIRA_EMAIL is missing from .env.\n"
                "Re-run with --first-time to set those alongside the token.",
                file=sys.stderr,
            )
        print("API token rotation")

    print()
    print(f"Opening {TOKEN_URL} in your browser...")
    _open_browser(TOKEN_URL)
    print()
    print("Create a new token, copy it, then paste it below.")
    values["JIRA_API_TOKEN"] = _prompt_secret("Paste new token")

    _save_env(env_path, values)

    print()
    print(f"  ✓  Updated {env_path} (permissions: 0600)")
    print()
    print("Done. The next jira-sync invocation will use the new token.")
    print()
    print("If you also use the atlassian-unofficial-mcp (or atlassian-internal-mcp)")
    print("with the same Atlassian token, run that MCP's bundled auth.py too —")
    print("it writes to your editor's MCP config, which is separate from .env.")


if __name__ == "__main__":
    main()
