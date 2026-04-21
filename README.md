# ai-tools

A small public toolbox of AI-native utilities I use day-to-day: CLI scripts, reusable skills, guides, and rules that plug into Cursor, Claude Code, and Codex.

Each tool is **editor-agnostic** (works in any AI editor that supports skills or MCP) and **install-by-prompt** — you paste a single prompt into your editor and the AI handles the git clone, dependencies, and config wiring.

## Read this first

**[Agentic Tools for Non-Engineers](./guides/agentic-tools-for-non-engineers.md)** — a practical guide for product managers, designers, data scientists, and other non-engineering roles who want to use AI coding agents to get more done across the tools they already use. The tools below are concrete examples of the patterns it describes (sync your work into a workspace, give the AI persistent context, save your repeatable workflows as skills, build small personal scripts when you spot a copy-paste pattern).

## Tools

### CLI tools — [`cli-tools/`](./cli-tools/)

| Tool | What it does |
|------|---|
| [`granola-sync`](./cli-tools/granola-sync) | Sync [Granola](https://www.granola.so/) meeting transcripts into a local folder as Markdown, so your AI editor can reference past conversations verbatim |
| [`jira-sync`](./cli-tools/jira-sync) | Pull Jira Cloud tickets into local Markdown files, draft new tickets locally and push in batch, add comments from the terminal |

### Skills — [`skills/`](./skills/)

| Tool | What it does |
|------|---|
| [`customer-journey`](./skills/customer-journey) | Turn a running prototype into an exec-ready customer journey presentation. The AI workshops a persona with you, walks through your prototype in a real browser, captures screenshots, and assembles a self-contained HTML deck |
| [`slack-feedback-to-pr`](./skills/slack-feedback-to-pr) | Scan your Slack channels for customer feedback and bug reports, triage them with the AI, and ship the fixes as PRs. The AI ranks items by signal (reactions + replies + cross-channel recurrence), you pick what to ship, the AI does the implementation and opens the PRs |

### MCP servers — [`mcps/`](./mcps/)

| Tool | What it does |
|------|---|
| [`dropbox-sign-mcp`](./mcps/dropbox-sign-mcp) | Draft contracts, analyze documents, and send for e-signature via [Dropbox Sign](https://www.dropbox.com/sign) — all from your AI editor's chat. Auto-detects signature fields, runs completeness checks, and shows visual previews before sending |
| [`atlassian-unofficial-mcp`](./mcps/atlassian-unofficial-mcp) | Read and write Jira tickets and Confluence pages from your AI editor's chat. An opinionated alternative to Atlassian's official Rovo MCP — adds sprint-aware tools, batched comment-reply workflows, and human-in-the-loop write safety |

### Rules — [`rules/`](./rules/)

| Rule | What it does |
|------|---|
| [`granola-raw-transcript`](./rules/granola-raw-transcript.mdc) | Tells your AI editor to use the raw [Granola](https://www.granola.so/) meeting transcript — whether pulled from the [Granola MCP](https://granola.ai/mcp) or read from local files synced by [`granola-sync`](./cli-tools/granola-sync) — instead of the AI-generated summary, so recaps and post-backs are grounded in what was literally said |
| [`git-best-practices`](./rules/git-best-practices.mdc) | Tells your AI editor to commit incrementally but never push without asking, always work on a feature branch, never amend pushed commits, never commit secrets, and other defensive git hygiene that protects you from common AI overreach |

## Concepts (quick refresher)

- **CLI tools** are scripts you run from the terminal (`granola-sync`, `jira-sync some-flags`). Useful for syncing external data into local Markdown your AI editor can read.
- **Skills** are structured instruction packs your AI editor loads on demand. They teach the AI a multi-step workflow ("create a customer journey for this project") and give it the helper scripts to do the work.
- **MCP servers** are persistent plugins that give your AI editor new capabilities — typically API access to a third-party tool (Dropbox Sign, Jira, Confluence). Once configured, the AI can call them like any other tool in its toolbox.
- **Rules** are persistent instructions your AI editor reads at the start of every session. Drop one in your workspace and the AI follows it automatically — useful for team conventions, formatting preferences, or telling the AI which tools to prefer.

## How to install

Each tool's README has a copy/paste install prompt. The prompts all follow the same shape:

> Install **{tool-name}** from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `<path>`). [Editor-specific setup the AI should handle.]

Open the tool's directory, copy its install prompt, paste it into Cursor / Claude Code / Codex, and the AI handles the rest. Guides and rules are even simpler — open the file, read it (for guides) or copy it into `.cursor/rules/` or `CLAUDE.md` (for rules).

## License

[MIT](./LICENSE).

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
