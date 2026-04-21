# Atlassian Internal

Work with Jira tickets and Confluence pages directly from your AI editor's chat — no browser tab required.

An MCP server (a plugin that gives your AI editor new capabilities) for Jira Cloud and Confluence Cloud. Search issues, read tickets, create and update tickets, transition statuses, comment, and link — plus fetch Confluence pages, reply to comments, and create or update content. All data comes from the Atlassian API in real-time.

## Who is this for?

PMs and anyone who works in Jira and Confluence and wants to interact with tickets and pages without leaving their editor. Ask your AI "what's in the current sprint?" or "create a bug for the broken upload button" and it handles the Jira API calls for you.

## How is this different from Atlassian's official Rovo MCP?

Atlassian also ships a first-party MCP server — the [Atlassian Rovo MCP Server](https://support.atlassian.com/rovo/docs/getting-started-with-the-atlassian-remote-mcp-server/) — hosted at `https://mcp.atlassian.com/v1/mcp`. If you want broad coverage with vendor support and don't need anything custom, **start with Rovo**. It's free, hosted by Atlassian, uses OAuth 2.1, respects your Atlassian permissions, and writes audit logs your admin can review.

This MCP is a small, opinionated, self-hosted alternative for cases where Rovo's surface area or behavior doesn't match how I want my agent to work:

| | Atlassian Rovo MCP | This MCP |
|---|---|---|
| Hosted by | Atlassian (cloud) | You (local Python) |
| Auth | OAuth 2.1 (preferred) or API token | API token (set via `auth.py` helper, never pasted into chat) |
| Setup | Just-in-time install via 3LO consent | `pip install` + `auth.py --first-time` |
| Coverage | Jira, Confluence, Compass | Jira, Confluence (no Compass) |
| Compass | Yes | No |
| Sprint awareness | General Jira tools | Dedicated `get_sprint_issues` (active sprint shortcut) |
| Confluence comment replies | General page tools | Dedicated `reply_to_comment` + threaded `get_page_comments` workflow |
| Write safety | Up to the client/user | Server-side `instructions` enforce a draft-confirm-send loop for writes and one-at-a-time comment replies |
| Admin controls | IP allowlist, audit log, domain controls | None — runs on your machine |
| Best fit | Most users; orgs with admin governance needs | PMs who want a focused, customizable workflow and are OK self-hosting |

If you're undecided, start with Rovo. Pick this one if you want sprint-first ergonomics, the human-in-the-loop comment-reply workflow, or you just want something small you can fork and bend to your specific habits.

## Install

Open your AI editor (Cursor, Claude Code, or Codex) and paste this prompt:

> Install the **atlassian-internal-mcp** MCP server from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `mcps/atlassian-internal-mcp`). Install its Python dependencies and add it to my editor's MCP config with the right `command` and `args` (leave the `env` block empty for now). Then run the bundled auth helper to capture my Atlassian credentials securely:
>
> ```
> python3 <mcp-dir>/src/auth.py --config <path-to-my-mcp-config> --server-name atlassian-internal --first-time
> ```
>
> The helper opens the [Atlassian API token page](https://id.atlassian.com/manage-profile/security/api-tokens) in my browser, prompts for my base URL, email, and token in the terminal (token input is hidden — it never enters chat or the model context), and writes everything into the MCP config's `env` block. After it finishes, restart the MCP server.

### Why the auth helper

The helper exists to keep your API token out of the LLM transcript. Pasting a token directly into chat sends it to your model provider's logs and leaves it in screenshots, exports, and shared sessions. Running the helper from a terminal pane lets you type the token via `getpass` (no echo, no tool output) — only the on-disk MCP config and the MCP server process ever see the value.

The same helper handles **rotation** too — when your token expires, the MCP returns an error message that points your AI at the helper. Same flow, same security properties; just omit `--first-time`.

### A note on interactive setup across editors

- **Cursor (agent mode):** your AI runs the auth helper directly in a terminal pane you can click into and type the token.
- **Claude Code / Codex:** your AI may instead show you the exact `python3 src/auth.py ...` command and ask you to run it yourself in a terminal — same security properties, one extra step. The token is still captured locally via `getpass` and never enters chat.

JSON-based MCP config hosts (Cursor, Claude Code) work out of the box. For TOML-based hosts (e.g. Codex), update the config by hand.

## Jira Tools

| Tool | Description |
|------|-------------|
| `search_issues` | Run any JQL query, get a compact summary list |
| `get_issue` | Full details for one issue (description, comments, metadata) |
| `list_projects` | List all accessible Jira projects |
| `get_sprint_issues` | Get issues in the active (or named) sprint for a project |
| `get_issue_types` | List valid issue types for a project |
| `create_issue` | Create a new issue with summary, description, type, priority, labels, epic |
| `update_issue` | Update an issue's summary, description, priority, or labels |
| `add_comment` | Add a markdown comment to an issue |
| `transition_issue` | Move an issue to a new status (e.g. In Progress, Done) |
| `assign_issue` | Assign an issue by email or display name, or unassign |
| `link_issues` | Link two issues (Blocks, Relates to, Duplicate, etc.) |

## Confluence Tools

| Tool | Description |
|------|-------------|
| `get_confluence_page` | Fetch a page by URL or page ID, returned as markdown |
| `get_page_comments` | All comments on a page, threaded, with comment IDs for replying |
| `search_confluence` | Search pages using CQL (Confluence Query Language) |
| `list_spaces` | List all accessible Confluence spaces |
| `create_confluence_page` | Create a new page in a space (with optional parent page) |
| `update_confluence_page` | Update a page's title or body (auto-increments version) |
| `reply_to_comment` | Post a reply to a specific comment, or add a new top-level comment |

## Example Prompts

### Jira — Reading

> "What tickets are in the current sprint for REPLAY?"

> "Show me REPLAY-42 with all its comments"

> "Find all open bugs assigned to me in REPLAY"

> "What are the children of epic REPLAY-100?"

### Jira — Writing

> "Create a bug in REPLAY: the upload button is broken on mobile -- priority High"

> "Move REPLAY-42 to In Review"

> "Assign REPLAY-55 to Sarah"

### Confluence — Reading

> "Fetch this Confluence page: https://acme.atlassian.net/wiki/spaces/DEV/pages/12345"

> "Show me all comments on that page"

> "Search Confluence for pages about deployment in the DEV space"

> "What Confluence spaces do I have access to?"

### Confluence — Writing

> "Create a new Confluence page in REPLAY titled 'Sprint 12 Retrospective' with these notes..."

> "Update that page with the revised acceptance criteria"

### Confluence — Comment Reply Workflow

> "Pull the comments from this Confluence page and summarize them"

> "Draft a reply to Alice's comment about the migration timeline"

> "Make it shorter and mention we're targeting Q3"

> "Post it"

> "Now draft a reply to Bob's question about the API changes"

## Safety

All write operations follow a human-in-the-loop pattern:

1. The LLM gathers the details from conversation
2. Presents the full planned action in chat (what it will create/update/comment)
3. Waits for explicit user confirmation
4. Only then calls the write tool

For comment replies, the LLM drafts one reply at a time in chat and never batch-posts without individual confirmation. This is enforced by the server's `instructions` string.

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
