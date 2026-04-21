# jira-sync

Pull Jira Cloud tickets into local Markdown files, so your AI editor can reference sprint backlogs, epic breakdowns, and ticket details without you copy-pasting from the browser.

## Who is this for?

PMs and engineers who work out of Jira and want their tickets available locally as persistent context for Cursor, Claude Code, or Codex. Also useful for drafting tickets in Markdown locally and pushing them to Jira in batch.

## What does it do?

1. **Pull** — downloads Jira tickets as `.md` files into a local folder (e.g. `~/AI/jira/`)
2. **Create** — drafts tickets as local `.md` files, reviews them, then pushes to Jira
3. **Update** — edits a synced ticket locally and pushes changes back to Jira
4. **Comment** — adds a comment to a ticket from the terminal
5. **Scheduled sync** — optionally runs every 30 minutes to keep your local folder current

Each file is named `KEY.md` (e.g. `PROJ-123.md`) with YAML frontmatter, description, and comments — designed for LLM context.

## Install

Open your AI editor (Cursor, Claude Code, or Codex) and paste this prompt:

> Install **jira-sync** from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `cli-tools/jira-sync`). Set up a shell alias so I can run `jira-sync` from anywhere. Then run the bundled auth helper to capture my Atlassian credentials securely:
>
> ```
> python3 <jira-sync-dir>/auth.py --first-time
> ```
>
> The helper opens the [Atlassian API token page](https://id.atlassian.com/manage-profile/security/api-tokens) in my browser, prompts for my base URL, email, project key, output directory, and token in the terminal (token input is hidden — it never enters chat or the model context), and writes them all to `<jira-sync-dir>/.env` with `0600` permissions.

### Why the auth helper

The helper exists to keep your API token out of the LLM transcript. Pasting a token directly into chat sends it to your model provider's logs and leaves it in screenshots, exports, and shared sessions. Running the helper from a terminal pane lets you type the token via `getpass` (no echo, no tool output) — only the on-disk `.env` file and `jira-sync` itself ever see the value.

### A note on interactive setup across editors

- **Cursor (agent mode):** your AI runs the auth helper directly in a terminal pane you can click into and type the token.
- **Claude Code / Codex:** your AI may instead show you the exact `python3 auth.py --first-time` command and ask you to run it yourself in a terminal — same security properties, one extra step. The token is still captured locally via `getpass` and never enters chat.

## Usage

```bash
# Sync all tickets for the configured project
jira-sync

# Sync a different project (overrides .env)
jira-sync --project PROJ

# Use a custom JQL query
jira-sync --jql "project = PROJ AND status != Done"

# Sync specific issues by key
jira-sync --issue PROJ-3 PROJ-5 PROJ-9

# Sync all children of an epic
jira-sync --epic PROJ-42

# Sync the active sprint
jira-sync --sprint

# Force re-sync everything (ignores state.json)
jira-sync --force

# List accessible projects
jira-sync --list-projects
```

## Creating tickets from markdown

Useful for having an LLM spec out tickets from a PRD, reviewing them locally, then pushing in batch.

### 1. Write draft files

Create `.md` files in `~/AI/jira/drafts/`. Use the same frontmatter format as synced tickets, with `key: NEW`:

```markdown
---
key: NEW
summary: Implement SSO for enterprise accounts
type: Story
priority: P1
labels: auth, enterprise
epic: PROJ-42
---

# Implement SSO for enterprise accounts

## Description

As an enterprise admin, I want to configure SSO so that...

### Acceptance criteria

- SAML 2.0 support
- Auto-provisioning of users
```

### 2. Push to Jira

```bash
jira-sync --create
jira-sync --create --create-dir ~/path/to/drafts
jira-sync --create --project PROJ
```

The script shows a summary table and asks for confirmation before creating. After creation, drafts are deleted and the new tickets are synced back as `KEY.md` files.

## Updating tickets from local edits

Edit a synced `KEY.md` locally (summary, description, priority, or labels), then push changes back:

```bash
jira-sync --update PROJ-1
jira-sync --update PROJ-1 PROJ-2 PROJ-3
```

The script shows what will be updated and asks for confirmation. After pushing, it re-syncs to get the canonical version.

Status and assignee changes are not currently supported (would require the transitions API).

## Adding comments

```bash
jira-sync --comment PROJ-1 "Reviewed -- looks good. Ship it."

# Markdown is supported
jira-sync --comment PROJ-1 "## Notes\n\n- Checked **staging** -- works\n- Ready for prod"
```

## Dry run

Append `--dry-run` to any command to preview without writing files or making API calls:

```bash
jira-sync --dry-run
jira-sync --epic PROJ-42 --dry-run
jira-sync --create --dry-run
jira-sync --comment PROJ-1 "Ship it" --dry-run
```

## Incremental sync

After the first run, subsequent syncs only fetch tickets updated since the last run (tracked via `state.json`). Use `--force` to re-sync everything.

## Run it automatically (macOS)

If you want `jira-sync` to run in the background every 30 minutes so your local Jira folder stays current, paste this prompt into your AI editor:

> Set up **jira-sync** to run every 30 minutes in the background on macOS using launchd. Find the absolute path to my `sync.py`, generate a launchd plist at `~/Library/LaunchAgents/com.<my-username>.jira-sync.plist` that invokes it with `python3` on a 1800-second interval (with `RunAtLoad` true and stdout/stderr redirected to a log file in the same folder as the script), then load it with `launchctl` and confirm it's running. Tell me the commands to start, stop, and uninstall it later.

To uninstall later, just ask the same AI editor: *"Uninstall the jira-sync launchd job."*

## Token rotation

When your Atlassian token expires, ask your AI editor:

> "Rotate my jira-sync Atlassian token"

The same `auth.py` helper handles rotation — it opens the token page, captures the new token via `getpass`, and updates `.env` in place. The token never enters chat, the same way first-time setup works.

If you also use the [atlassian-unofficial-mcp](../../mcps/atlassian-unofficial-mcp/) (or `atlassian-internal-mcp` privately) with the same token, run that MCP's bundled `auth.py` separately — it writes to your editor's MCP config, not to `.env`.

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
