# Getting Started

A one-paste prompt to bootstrap a complete AI-native workspace on macOS. The AI editor you paste this into will install Homebrew, your AI editor of choice, clone the toolbox, and wire up every MCP, CLI, skill, and rule in this repo.

**Time to finish:** about 15-20 minutes, most of which is automated. You'll be asked to approve a handful of steps (sudo password, browser auth windows for GitHub).

---

## Why this guide exists

Most people get stuck before they ever get value from an AI coding agent. The setup steps — install Homebrew, install the editor, create a workspace, wire up MCPs, drop in rules — are individually easy but collectively a wall if you haven't done it before.

This guide turns that wall into a single paste. The prompt below describes the end state you want; your AI editor does the work.

---

## What you'll have when this is done

- **One AI editor installed** (your pick of Cursor, Claude Desktop, or Codex Desktop — plus the matching CLI if you want it)
- **A `~/AI/` workspace** with folders for your docs, drafts, meetings, tasks, and cloned repos
- **The `ai-tools` toolbox** cloned into `~/AI/repos/ai-tools/`, with every MCP, CLI, skill, and rule from this repo wired into your editor
- **A customized `~/AI/AGENTS.md`** that tells your editor about your role, preferences, and workspace layout
- **Working shell aliases** (`jira-sync`, `granola-sync`) you can run from any terminal

---

## Before you paste

A few things to know before you hand this off to your editor:

- **macOS only for v1.** The prompt assumes macOS and Homebrew. Linux and Windows users will want to adapt it by hand for now.
- **sudo required.** Homebrew installation prompts for your macOS login password once. The AI cannot type your password — it will pause and ask you to do it in a terminal pane.
- **Browser windows will open.** `gh auth login` (GitHub) opens a browser tab. MCPs that use OAuth (like the Paper MCP) open browser tabs for auth. This is expected and safe.
- **Never paste tokens into chat.** Any MCP or CLI tool that needs an API key ships an `auth.py` helper that uses hidden terminal input. The install prompt tells the AI to run those helpers in a terminal pane, not to ask you for tokens in chat.
- **The AI will adapt.** If you already have Homebrew, Cursor, or a `~/AI/` workspace, it'll skip those steps. If a step fails (a Homebrew package was renamed, a download URL is dead), it'll tell you and ask before improvising.
- **You can stop at any time.** After each major step, the AI summarizes what was done. If something looks wrong, say so and the AI backs up.

---

## The install prompt

Copy everything in the block below and paste it into Cursor, Claude Code, or Codex.

> Set me up with an AI-native workspace for AI coding agents on macOS. Work through the steps below in order. After each major step, summarize what was done and ask before any destructive action.
>
> 1. **Interview me first.** Ask me these two questions (one at a time) and use the answers to tailor step 2:
>    a. Which LLM does my company use — **Anthropic**, **OpenAI**, **both**, or **not sure**?
>    b. How comfortable am I in the terminal — **not at all**, **somewhat**, or **very**?
>
> 2. **Install AI editors based on my answers.** Every editor below is a Homebrew cask. Skip anything I already have installed (check `/Applications/` and `which` before installing).
>    - **Always install Cursor desktop app:** `brew install --cask cursor` (macOS 12+). Fallback URL: https://cursor.com/download
>    - **Anthropic + GUI comfort** → install **Claude Desktop**: `brew install --cask claude`. On macOS this bundles Claude Code, so no separate CLI needed. Fallback URL: https://claude.ai/download
>    - **Anthropic + terminal comfort** → also install standalone **Claude Code CLI**: `brew install --cask claude-code` (cask, not formula).
>    - **OpenAI + GUI comfort** → install **Codex Desktop**: `brew install --cask codex-app`. **Apple Silicon only** — on an Intel Mac, skip the cask and download the Intel `.dmg` from https://developers.openai.com/codex/app instead.
>    - **OpenAI + terminal comfort** → also install **Codex CLI**: `brew install --cask codex` (cask, not formula — distinct from `codex-app`).
>    - **Both vendors** → install from both rows above.
>    - **"Not sure"** → install Cursor only; we can add more later.
>    - **Important:** `codex` and `codex-app` are two separate Homebrew casks. Don't conflate them. Same with `claude` (desktop + Claude Code bundled) vs. `claude-code` (standalone CLI only).
>
> 3. **Homebrew + base tools.** Install Homebrew if missing (https://brew.sh), then `git`, `gh`, and `python@3.11`. Don't install anything else on spec — individual tools (like `node` for the `customer-journey` skill) will pull in their own dependencies when I opt in.
>
> 4. **GitHub auth.** Run `gh auth login`. Use SSH if I have an SSH key set up (`ls ~/.ssh/id_*.pub` returns any files), otherwise HTTPS.
>
> 5. **Workspace.** Create `~/AI/` with subdirectories `docs/`, `drafts/`, `meetings/`, `tasks/`, and `repos/`.
>
> 6. **Clone the toolbox.** Sparse-clone `git@github.com:kylemaclaren/ai-tools.git` into `~/AI/repos/ai-tools/`. (If I authed with HTTPS in step 4, use `https://github.com/kylemaclaren/ai-tools.git` instead.)
>
> 7. **MCPs.** For each MCP under `~/AI/repos/ai-tools/mcps/`, follow that MCP's README install prompt and wire it into whichever editors I installed. Config paths by editor:
>    - Cursor → `~/.cursor/mcp.json`
>    - Claude Desktop → `~/Library/Application Support/Claude/claude_desktop_config.json`
>    - Claude Code CLI → `~/.claude/mcp.json`
>    - Codex Desktop → `~/Library/Application Support/Codex/config.toml`
>    - Codex CLI → `~/.codex/config.toml`
>
>    For MCPs that need API tokens (e.g. `atlassian-internal-mcp`, `dropbox-sign-mcp`), run the MCP's bundled `src/auth.py --first-time` in a terminal pane. **Never ask me to paste tokens into chat** — the auth helpers use hidden terminal input.
>
> 8. **CLI tools.** For each CLI tool under `~/AI/repos/ai-tools/cli-tools/`, follow its README install prompt. These set up shell aliases (`jira-sync`, `granola-sync`) and config files.
>
> 9. **Skills.** Symlink each skill from `~/AI/repos/ai-tools/skills/` into each installed editor's skills directory where skills are supported:
>    - Cursor → `~/.cursor/skills/`
>    - Claude Code / Claude Desktop → `~/.claude/skills/`
>    - Codex → `~/.codex/skills/`
>
>    Skip editors that don't support skills.
>
> 10. **Rules.** Copy each `.mdc` from `~/AI/repos/ai-tools/rules/` into `~/.cursor/rules/` (for Cursor), and reference them from the equivalent instruction files for any other editors I installed (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`).
>
> 11. **Starter AGENTS.md.** Read `~/AI/repos/ai-tools/guides/example-agents-md.md` and follow its embedded "How to use this" prompt: interview me briefly (role, what I work on, preferences), then write the customized result to `~/AI/AGENTS.md`. If the file already exists, diff against it before overwriting.
>
> 12. **Summary.** When everything is done, show me:
>     - What was installed
>     - Where MCPs, skills, and rules landed (by path)
>     - What shell aliases I can now run
>     - Suggested first prompts to try (2-3 examples that exercise the tools I just installed)

---

## Workspace layout reference

Once the prompt finishes, your `~/AI/` directory will look like this:

```
~/AI/
├── AGENTS.md         # your instructions to AI editors opened here
├── docs/             # longer-form docs synced from your knowledge sources
├── drafts/           # your working docs (PRDs, strategy memos, etc.)
├── meetings/         # transcripts (e.g. synced by granola-sync)
├── tasks/            # tickets (e.g. synced by jira-sync)
└── repos/            # cloned git repos
    └── ai-tools/     # the toolbox itself
```

Open `~/AI/` as a workspace in your AI editor. The editor will load `~/AI/AGENTS.md` automatically at the start of every session.

---

## What to do next

Once setup finishes, try one of these starter prompts in your editor to confirm everything's wired up:

- **"Pull my Jira tickets from the last 7 days into `tasks/` and summarize what changed."** Exercises `jira-sync` + your editor's ability to read local markdown.
- **"Read `meetings/` for this week and draft a status update in the format I use."** Exercises `granola-sync` + your `AGENTS.md` preferences.
- **"What MCPs and skills do I have installed? Show me a short description of each."** A sanity check on the tool wiring.

If the AI stumbles on any of these, it's usually because an MCP or skill didn't wire up correctly — paste the error back at the AI and it'll walk you through the fix.

---

## Editor-specific notes

| Editor | Config location | Skills directory | Restart to reload MCPs |
|---|---|---|---|
| Cursor | `~/.cursor/mcp.json` | `~/.cursor/skills/` | Cmd+Shift+P → "Reload Window" |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | `~/.claude/skills/` | Quit & reopen the app |
| Claude Code CLI | `~/.claude/mcp.json` | `~/.claude/skills/` | Restart the `claude` session |
| Codex Desktop | `~/Library/Application Support/Codex/config.toml` | `~/.codex/skills/` | Quit & reopen the app |
| Codex CLI | `~/.codex/config.toml` | `~/.codex/skills/` | Restart the `codex` session |

## Troubleshooting

- **"MCP not showing up."** Restart the editor. If still missing, ask the AI to re-read the MCP's README install prompt and re-run the wiring step.
- **"Auth failed for MCP X."** Re-run that MCP's `src/auth.py` (or `auth.py` for CLI tools) in a terminal pane. Never paste tokens into chat.
- **"Homebrew package not found."** Package names occasionally change. The install prompt has fallback vendor URLs for each editor — tell the AI to use those.
- **"I'm on an Intel Mac and Codex Desktop's cask doesn't install."** The `codex-app` cask is Apple Silicon only. Download the Intel `.dmg` from https://developers.openai.com/codex/app.
- **"I want Claude Code to auto-update instead of `brew upgrade`-ing manually."** Anthropic publishes a vendor-maintained installer at `https://claude.ai/install.sh` that handles auto-updates. Ask the AI to uninstall the Homebrew cask first (`brew uninstall --cask claude-code`), then run Anthropic's installer. OpenAI doesn't publish an equivalent for Codex.

---

## Related guides

- **[example-agents-md.md](./example-agents-md.md)** — a customizable `AGENTS.md` template with an embedded prompt that walks you through personalizing it.
- **[agentic-tools-for-non-engineers.md](./agentic-tools-for-non-engineers.md)** — the longer "why and how" behind this style of workflow, for PMs, designers, and other non-engineers.

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
