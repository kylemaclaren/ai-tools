# Example AGENTS.md

A starter template for the `AGENTS.md` file that tells your AI editor (Cursor, Claude Code, Codex, etc.) who you are, what you work on, and how you want it to behave. Drop a customized copy at `~/AI/AGENTS.md` (or your project root) and your editor will load it automatically at the start of every session.

**This is not a fill-in-the-blanks form.** You can absolutely edit the placeholders by hand — but the easier path is to paste this whole file at your LLM and let it interview you.

---

## How to use this file

Open this file in Cursor, Claude Code, or Codex and paste the prompt below into the chat. The AI will read the template, ask you a handful of questions about your role and preferences, and write a customized `~/AI/AGENTS.md` based on your answers.

> Read this entire `example-agents-md.md` file. Then walk me through customizing it into my own `~/AI/AGENTS.md`:
>
> 1. Ask me one section at a time (About me, My workspace, How I want you to work, Tools I have wired up, Where to find things, Don't). For each section, ask the minimum questions you need to fill in the placeholders — 2-4 questions per section max.
> 2. Offer sensible defaults based on what's already installed in `~/AI/` (check for `docs/`, `drafts/`, `meetings/`, `tasks/`, `repos/`; check for tools in `~/AI/repos/ai-tools/` or similar; check `.cursor/mcp.json` / `~/.claude/mcp.json` / `~/.codex/config.toml` for wired-up MCPs).
> 3. After I answer each section, show me the filled-in version and ask if I want to tweak anything before moving on.
> 4. When all sections are done, write the result to `~/AI/AGENTS.md`. Don't overwrite an existing file without confirming.
> 5. If I already have an `~/AI/AGENTS.md`, read it first and treat this as an update — only ask about fields that are missing or look stale.

You can also just edit the template by hand — every placeholder is in `{curly braces}` and there's a real example under each section showing what "good" looks like.

---

## The template

Copy everything below this line into `~/AI/AGENTS.md`, then replace the `{placeholders}` with your own details. The example blocks (in `> blockquotes`) are illustrative — delete them once you've filled in the real version.

---

# AGENTS.md

Instructions for AI editors working in this workspace.

## About me

- **Name:** {your name}
- **Role:** {your role, e.g. "Senior PM" / "Designer" / "Solutions Engineer"}
- **Team / focus area:** {what you work on day-to-day}
- **Stakeholders I serve:** {engineering partners, design partners, customers, execs — whoever you produce work for}

> Example:
> - Name: Jordan Rivera
> - Role: Senior PM
> - Team / focus area: Checkout experience on the Payments org
> - Stakeholders: Eng lead (Priya), Design lead (Sam), and two design-partner customers piloting v2

## My workspace

I work out of `~/AI/`. Subdirectories:

- `docs/` — {what lives here}
- `drafts/` — {what lives here}
- `meetings/` — {what lives here}
- `tasks/` — {what lives here}
- `repos/` — {what lives here}

> Example:
> - `docs/` — synced Paper and Confluence docs I reference (read-only, refreshed daily)
> - `drafts/` — working copies of PRDs, strategy docs, and narrative memos I'm actively editing
> - `meetings/` — Granola transcripts, synced daily by `granola-sync`
> - `tasks/` — Jira tickets I'm tracking, synced by `jira-sync`. One file per ticket.
> - `repos/` — cloned git repos. The `ai-tools/` toolbox lives here.

## How I want you to work

- {preference 1}
- {preference 2}
- {preference 3}

> Example:
> - Commit incrementally as you work, but don't push to a remote without asking.
> - When summarizing meetings, pull the raw transcript — never rely on the AI-generated summary.
> - Prefer plain markdown over rich-text formatting.
> - If a task needs more than 3-4 steps, show me the plan first and wait for confirmation.
> - When you're uncertain, say so and ask. Don't guess at file paths, API shapes, or my intent.

## Tools I have wired up

Pointers, not an exhaustive list — discover tools via the editor's native mechanisms (MCP config, skills directory, rules directory).

- **MCPs:** {list the MCPs you use, one line each}
- **CLI tools:** {list any custom CLI scripts you've installed}
- **Skills:** {list skills you rely on}

> Example:
> - **MCPs:** `atlassian` (Jira + Confluence), `slack`, `figma`, `granola`, `paper`, `dropbox-sign`
> - **CLI tools:** `granola-sync` (pulls meeting transcripts), `jira-sync` (pulls tickets)
> - **Skills:** `customer-journey` (builds HTML customer journey decks from a running prototype), `slack-feedback-to-pr` (triages Slack feedback and ships fixes as PRs)

## Where to find things

Concrete pointers so you don't have to guess or grep.

- {pointer 1}
- {pointer 2}

> Example:
> - My active workstreams are in `drafts/active/` — one folder per workstream.
> - Tickets I own: `tasks/*.md` where the `assignee` frontmatter matches my email.
> - Customer interview notes: `meetings/` — search by customer name or date.
> - Strategy docs I reference often: `docs/strategy/`.
> - When I say "the design partner call", I mean the weekly 45-min sync with customers X and Y; transcripts are in `meetings/design-partner-*.md`.

## Don't

- {guardrail 1}
- {guardrail 2}

> Example:
> - Don't post to Slack without showing me the draft first.
> - Don't push to `main` on any repo — always work on a feature branch and open a PR.
> - Don't commit anything under `drafts/` — that's scratch space.
> - Don't paste API tokens or credentials into chat. If a tool needs auth, run its `auth.py` setup helper in a terminal pane instead.
> - Don't reply to Confluence or Jira comments in my voice without letting me review the draft.

---

## Related guides

- **[getting-started.md](./getting-started.md)** — if you don't have an `~/AI/` workspace yet, start here. It bootstraps the whole setup in one paste.
- **[agentic-tools-for-non-engineers.md](./agentic-tools-for-non-engineers.md)** — the longer "why and how" behind this style of workflow, written for PMs, designers, and other non-engineers.

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
