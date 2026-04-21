# Agentic Tools for Non-Engineers

A practical guide for product managers, designers, data scientists, and other non-engineering roles who want to use AI coding agents — tools like Cursor, Claude Code, and Codex — to get more done across the tools they already use.

**This is not a "learn to code" guide.** You don't need to become an engineer. You need to understand how these tools think, what they can see, and how to set up your workspace so the AI is genuinely useful for your actual work: synthesizing meetings, drafting strategy docs, pulling customer research together, keeping stakeholders updated.

**Time to get value:** You can be productive within a day. Most of the setup is just organizing files into a folder.

---

## The Core Idea

AI agents are most powerful when they can **see your work in context**. A chatbot can answer questions. An agent can read your meeting notes from last week, cross-reference them with your Jira or Linear tickets, draft a status update in the format your team expects, and post it to Slack — all in one conversation.

The catch: the agent can only work with what it can see. The rest of this guide is about how to make your work visible to the agent, how to get the agent's output back into your tools, and how to pick the right tool for different tasks.

---

## Choosing Your Tool

There are five categories of AI tools you'll encounter, roughly ordered from simplest to most powerful. You don't need to pick one — most people settle into two or three depending on the task.


| Category                    | Examples                      | What it feels like                                                            | Best for                                                                                                     |
| --------------------------- | ----------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Chatbot in your browser** | Claude, ChatGPT, Gemini       | A conversation partner you can paste things into                              | Brainstorming, one-off questions, drafting text when you don't need file access                              |
| **AI prototyping tool**     | Lovable, Replit               | A visual builder that turns your description into a working app               | Building functional prototypes and demos without touching code — you describe what you want, it builds it    |
| **AI code editor**          | Cursor, Windsurf              | A smart workspace where the AI can see and edit all the files in your project | Multi-file projects, connecting to external tools via MCP, iterating on prototypes with full control         |
| **AI desktop app**          | Claude Desktop, Codex Desktop | A chatbot with access to your local files and connected tools                 | Working with files on your computer, using MCP integrations, longer working sessions with persistent context |
| **AI in the terminal**      | Claude Code CLI, Codex CLI    | A conversation with an expert who can run commands on your computer           | Quick tasks, scripting, automation, running on a remote server                                               |


**How to decide**

**"I want to ask a quick question or brainstorm."** Use a chatbot in your browser. No setup, no files, just a conversation. Still the right tool for anything that doesn't need context beyond what you can paste in.

**"I want a working prototype I can show people."** Use an AI prototyping tool. Describe the app you want — "a dashboard that shows our team's sprint progress with a burndown chart" — and it builds a live, shareable version. You iterate by describing changes, not by editing code. Most prototypes start fully mocked — no database, no real APIs — which is fastest to build and perfect for demos and design partner sessions. When you need actual users doing actual work, both Lovable and Replit can wire in a real backend (Supabase, auth, etc.). Slower to set up, but it turns the demo into something a small pilot group can actually use.

**"I'm building something with multiple files and I want full control."** Use Cursor. You graduate here when your prototype outgrows a visual builder, or when you need to connect to external tools (Jira, Slack, Figma) via MCP servers. You see and edit every file; the AI works alongside you in the same workspace.

**"I want AI that can see my local files and connect to my tools, without managing a code project."** Use a desktop app like Claude Desktop. You get file access and MCP integrations (Slack, Jira, Figma, etc.) in a chat-style interface. The power of connected tools without the overhead of a code editor.

**"I need to automate something, run a script, or work from the command line."** Use Claude Code or another CLI agent. The most flexible option — you can pipe data, run commands, chain tasks together. It's also the only option that works well on remote servers or in CI/CD pipelines.

**They're complementary, not competing**

A common workflow: prototype an idea in Lovable, then pull it into Cursor when you need more control. Use Claude Desktop with Slack and Jira MCPs for your daily PM workflows. Drop into Claude Code in the terminal when you need to run a quick script or automate something.

You'll naturally gravitate toward 2-3 of these. The key insight is that they sit on a spectrum from "easy to start, limited context" (browser chatbot) to "more setup, maximum power" (terminal CLI). Move along that spectrum as your needs grow.

**Graduating a prototype from Lovable or Replit into Cursor or Claude Code**

Visual builders are great for the first version of an idea, but you'll hit a ceiling: you want to wire up a real API, add an MCP integration, or just see the whole codebase at once. The good news is the handoff is built in — you don't have to start over.

- **Push to GitHub from inside the prototyping tool, then clone the repo locally.** Lovable, Replit, v0, and Bolt all have a one-click "Connect to GitHub" / "Export to GitHub" option. Once the repo exists, ask your AI editor to clone it and open the folder — the AI walks you through any auth step.
- **The connection stays live in both directions.** Most prototyping tools keep watching the GitHub repo — push a commit from Cursor and Lovable picks it up, so you keep the visual preview and shareable URL while doing heavier work in your editor. (Some tools require flipping into "GitHub-synced" mode first; check the docs.)
- **Move back and forth as friction dictates.** You don't have to "graduate" all at once. Plenty of people prototype the next feature in Lovable, pull it down to Cursor for cleanup, then push back up — depending on what's easier for the task at hand.

---

## Getting Content In: Live Connections vs. Local Files

The most important decision you'll make is how to get your existing content — docs, tickets, meeting notes, designs — into a place where the AI can see it.

There are two approaches, and you'll probably use both.

**Option A: Live connection (MCP servers)**

An MCP server is a plugin that lets the AI talk directly to a SaaS tool. Instead of downloading your Jira tickets, the AI queries Jira in real time during your conversation.

**Examples of what this looks like:**

- "What's the status of PROJ-142?" — the AI fetches the ticket live from Jira or Linear
- "Find the Slack thread where design shared the new onboarding mocks" — the AI searches Slack directly
- "Pull up the PRD on the Confluence page Sarah shared yesterday" — the AI fetches the page by URL

**When to use live connections:**

- You need the **latest version** right now (a ticket that's being actively updated, a Slack thread still in progress)
- It's a **one-off lookup** — you need one specific thing, not a corpus
- The content **changes frequently** and a local copy would go stale

**The tradeoff:** MCP servers can be slow, they can't search across large datasets efficiently, and the AI forgets the content after your session ends. If you find yourself fetching the same doc every session, that's a sign you should sync it locally instead.

**Vendor-shipped MCPs vs. custom ones**

Most major SaaS tools now ship their own MCP server (Atlassian, Slack, GitHub, Linear, Notion). Use those as your default — they're maintained by the vendor, scoped sensibly, and free to use on the standard product tier in most cases. (Don't confuse the free MCP with the paid AI assistant some vendors also sell — those are separate products.)

You'd build (or use someone else's) **custom** MCP server when you want one of three things the vendor's default doesn't give you:

- **Guardrails** — only let the AI touch certain projects, channels, or doc spaces
- **Opinionated tools** — e.g. a `pull_doc` tool that fetches a single doc by URL and tracks it for sync, instead of a generic `search` you have to drive yourself
- **Workflows your vendor doesn't ship** — pulling raw meeting transcripts instead of AI summaries, posting to a custom internal canvas, etc.

Start with the official MCP. Move to a custom one only when you've felt the limitation enough times to know what you actually want.

**Option B: Local files (sync to your workspace)**

Download content as files — usually Markdown — into a folder on your computer. The AI can see everything in your workspace's file tree: searching across files, referencing them in conversation, even editing them.

**Examples of what this looks like:**

- A `meetings/` folder with one Markdown file per meeting, auto-synced from your meeting tool
- A `jira/` folder with your sprint's tickets pulled down as Markdown files
- A `docs/` folder with key strategy docs, PRDs, and research summaries

**When to use local files:**

- You **reference this content across many sessions** — your roadmap, your team's OKRs, your research corpus
- You want to **search across a collection** — "find every meeting where we discussed the enterprise pricing model"
- You want to **annotate or edit** before sharing — revise a doc locally, then push the updated version back

**The tradeoff:** Local files can go stale. You need a way to keep them updated — either manually re-downloading, or with a sync script (more on this later).

**The Decision Cheat Sheet**


| Situation                                                           | Approach                                       |
| ------------------------------------------------------------------- | ---------------------------------------------- |
| "What's the current status of this ticket?"                         | Live connection                                |
| "Pull up the doc Sarah shared in Slack"                             | Live connection                                |
| "Summarize what we've discussed about X across the last 5 meetings" | Local files                                    |
| "Draft a status update using my roadmap and this sprint's tickets"  | Local files (roadmap + tickets synced locally) |
| "Find every mention of 'churn' in our research notes"               | Local files                                    |


**The practical pattern most people land on**

Sync the stuff you reference constantly — meeting notes, sprint tickets, key docs. Use live connections for everything else. You'll figure out which is which within a week: if you keep asking the AI to fetch the same Confluence page, just download it.

**A worked example: meetings**

Meetings are the cleanest case for using both approaches at once. You probably want:

- A **live MCP** for "what did Sarah say in the meeting yesterday?" (fresh, one-off, you don't need it next week)
- A **local sync** for "find every meeting where we discussed enterprise pricing" (cross-corpus search, persistent reference)
- A **rule** that tells the AI to always pull the verbatim transcript instead of the meeting tool's auto-generated summary, regardless of which path it came from — so a recap is grounded in what was literally said, not in the AI summarizing an AI summary

That's the full pattern in one workflow: live + local + rule, all reinforcing each other. (See `[granola-sync](https://github.com/kylemaclaren/ai-tools/tree/main/cli-tools/granola-sync)` and the `[granola-raw-transcript](https://github.com/kylemaclaren/ai-tools/tree/main/rules/granola-raw-transcript.mdc)` rule for a worked example built around the [Granola](https://www.granola.so/) meeting tool.)

---

## Pushing Content Out

The AI is great at drafting, synthesizing, and structuring. But the output needs to get back into the tools your team actually uses. Three common destinations:

**Back to a collaboration tool (Confluence, Google Docs, Notion)**

The typical workflow:

1. Draft or revise content locally in Markdown (the AI helps you write it)
2. Push it to your collaboration tool via MCP server or a sync script
3. Share the link with your team

**Watch for conflicts.** If someone else edited the remote version while you were working locally, pushing will overwrite their changes. Most sync tools will warn you — pay attention to the warning.

**When to push:** When the content is ready for other people to see. Don't push drafts-in-progress to a shared doc — keep those local until you're happy with them.

**To a project tracker (Jira, Linear, Asana)**

Common patterns:

- Draft a ticket locally, including description, acceptance criteria, and context — then have the AI create it via MCP
- Update a batch of tickets at once: "move all the tickets in this sprint that are marked 'blocked' to 'needs triage' and add a comment explaining why"
- Generate a set of tickets from a spec or meeting notes

The AI is especially good at the tedious parts: writing clear descriptions, formatting acceptance criteria consistently, linking related tickets.

**To GitHub (sharing a tool or prototype)**

When your project is useful enough that other people want to run it:

1. The AI helps you write a README explaining what it does and how to use it
2. You create a GitHub repo and push your project folder up
3. Others can clone it and run it themselves

This is most relevant for prototypes, internal tools, and shared scripts. You don't need to understand git deeply — the AI can walk you through the commands.

**To Slack or email (status updates, summaries)**

Two approaches:

- **Via MCP:** The AI posts directly to a Slack channel. Good for routine updates you want to automate.
- **Via copy/paste:** The AI drafts the message, you review it, you paste it. Good for anything sensitive or high-visibility where you want a human checkpoint.

---

## When to Build a Personal Tool

This is the part that surprises most non-engineers: **you can have the AI build you tools.** Not apps. Not products. Just small scripts that automate a task you do repeatedly.

**Signs you should build one**

- You **copy-paste between two tools** on a regular schedule (pulling data from one place, reformatting it, putting it somewhere else)
- You do a **manual conversion step** every time (exporting a doc as PDF, reformatting meeting notes, cleaning up a spreadsheet export)
- You have a **recurring ritual** that follows the same steps every time (weekly status update, Monday sprint prep, quarterly OKR refresh)

**What these tools actually look like**

Not what you might imagine. A typical personal tool is:

- A single Python script, 50-200 lines
- Takes a command like `python3 sync-meetings.py --today`
- Talks to one or two APIs (your meeting tool, your docs tool, your project tracker)
- Outputs Markdown files into a folder, or posts to Slack, or creates tickets
- No UI. No deployment. No infrastructure. Just a script in a folder on your computer.

Optionally, you can set it to run on a schedule — every 30 minutes, every morning at 8am — so the data is always fresh without you thinking about it.

**A few conventions worth stealing**

After building a few of these you'll converge on a small set of patterns. Steal them from day one and skip the rediscovery:

- `**config.json` for preferences** — paths, defaults, channel lists, whatever the user might want to change. Have the script ask interactively on first run and save the answers.
- `**.env` for secrets only** — API tokens, signing keys. Keep these out of `config.json` so you don't accidentally commit them. Different file, different treatment.
- **Don't ship boilerplate the AI can write at install time** — no per-OS launchd templates, no scaffolded cron jobs, no "fill in your username here" YAML files. Ship the smallest possible artifact and let the user's AI generate the per-machine bits during install. It scales infinitely better than maintaining templates.

A worked example of all three: `[granola-sync](https://github.com/kylemaclaren/ai-tools/tree/main/cli-tools/granola-sync)`.

**How to build one**

1. Open Cursor or Claude Code
2. Describe what you want in plain English: "I want a script that pulls my meeting notes from today and saves them as Markdown files in a folder called meetings/"
3. The AI writes it
4. You run it and check the output
5. If the format isn't right, tell the AI: "Actually, put the date in the filename" or "Include the attendee list at the top"
6. Done. Save the script. Run it whenever you need it.

You don't need to understand every line of code. You need to understand what the script does, what inputs it takes, and how to run it. That's it.

**Example tools worth building**


| Task you do manually                                                              | Tool the AI can build for you                                                                |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Open your meeting tool, copy notes, paste into a doc, clean up formatting         | A sync script that pulls notes as Markdown on a schedule                                     |
| Go to Jira/Linear every morning, scan the sprint board, write a summary in Slack  | A script that pulls active sprint tickets and drafts a summary                               |
| Copy customer feedback from support channels, group by theme, share with the team | A script that reads a channel and categorizes messages                                       |
| Write the same style of weekly status update every Friday                         | A script that pulls your calendar, completed tickets, and recent docs, then drafts an update |


Each of these takes 15-30 minutes to build with an AI agent. You'll spend more time explaining the output format you want than anything else.

---

## Tips and Common Mistakes

**Start with one folder.** Don't try to connect everything at once. Pick one project or one workflow, get comfortable, then expand. A single folder with your meeting notes is a great starting point.

**Commit to Markdown.** It's the universal format that every AI tool reads, searches, and edits well. If you can get your content into Markdown, you're 80% of the way there. Most tools export to it, and the AI can convert almost anything.

**Name your files well.** The AI reads filenames. `2024-03-15-product-review-standup.md` is infinitely more useful than `notes.md` or `doc1.md`. Dates in filenames (`YYYY-MM-DD`) make chronological searching easy.

**Don't over-organize.** A flat folder with 50 Markdown files is totally fine. The AI can search them instantly. You don't need nested subfolders, tagging systems, or taxonomies to be productive.

**Live connections aren't magic.** MCP servers add latency, can be flaky, and can't efficiently search across large datasets. For anything you reference more than twice a week, sync it locally.

**Save your best prompts.** When you figure out a prompt that produces great output — a status update format, a feedback template, a doc structure — save it as a file in your workspace. Next time, you can just say "use the format in templates/weekly-update.md" and the AI will follow it exactly.

**Use Plan mode for anything bigger than a small change.** Most AI editors now ship a read-only "Plan mode" (Cursor, Claude Code) or "Ask mode" — the AI investigates your codebase and proposes a step-by-step plan without actually editing anything. You read the plan, push back on the parts that look wrong, and only then flip into the regular agent mode to execute.

- **Use it when:** the task touches multiple files, you're unsure of the approach, or you're doing anything you'd hate to undo (refactors, migrations, deletes, anything in a shared repo).
- **Skip it when:** the change is small and obvious — a typo fix, a renamed variable, a one-line tweak.
- **A good starter prompt:** "Switch to Plan mode and propose how you'd add a CSV export button to the dashboard. Don't change anything yet — walk me through what you'd touch and why." Reading the plan takes five minutes; reverting wrong changes across twelve files takes an hour.

**You will feel slow at first.** That's normal. The payoff comes after a week, when your workspace is set up and the AI already has context on your projects, your team's conventions, and your preferred formats. The first session is setup. Every session after that is leverage.

---

## Power User: Leveling Up Your Setup

Once you're comfortable with the basics — files in a folder, conversations with the AI, maybe a sync script or two — there are three things that separate a casual user from someone who's genuinely fast.

**Teach your workspace with rules**

Every time you correct the AI — "no, use bullet points not numbered lists," "we call those 'workstreams' not 'initiatives'," "always include the Jira ticket link" — that's a preference you could save permanently.

**Rules** are small text files you drop into your workspace that the AI reads at the start of every session. They're like onboarding notes for the AI: your team's terminology, your preferred formats, which tools to use and which to avoid.

**What a rule looks like in practice:**

A file called something like `status-update-conventions.md` that says:

> When drafting a weekly status update, use this format: one section per workstream, each with a 1-2 sentence summary, a list of completed items, and a list of blockers. Use the workstream names from our OKRs doc. Always link Jira tickets as `PROJ-###`.

That's it. No code. Just a text file that tells the AI how you work. The AI reads it automatically every time you open a conversation in that workspace.

**When it's worth doing:**

- You've corrected the AI on the same thing 3+ times
- You have a team convention that's not obvious (naming, formatting, terminology)
- You want consistent output across sessions without re-explaining your preferences

Different tools call these different things — Cursor uses `.cursor/rules/`, Claude Code uses `CLAUDE.md`, Claude Desktop uses project instructions — but the concept is the same everywhere: persistent instructions the AI follows automatically.

**Give each project a context doc**

Rules are small and single-purpose. For any project that'll outlive a single session — a prototype, a personal tool, a folder you'll keep working in — graduate to a single **`AGENTS.md`** at the project root. It's the first file the AI reads, so it stops re-deriving things you've already decided.

What goes in it:

- **What this is and why** — one paragraph. The thesis, the audience, what's mocked vs. real.
- **Architecture in broad strokes** — the main pieces, where they live, how they connect.
- **Common pitfalls** — specific things the AI keeps getting wrong. After you correct the same mistake 3+ times, write it down here. Next session it stops happening.

Two conventions worth stealing from day one:

- **Use the name `AGENTS.md`, not editor-specific files.** It's the cross-editor standard — Cursor, Claude Code, and Codex all read it. Editor-specific files (`CLAUDE.md`, `.cursor/rules/`) can be one-line redirects: a `CLAUDE.md` whose only content is "Read AGENTS.md before making any changes."
- **Split when it gets long.** Past ~200 lines, keep `AGENTS.md` as the quick reference and link out to a deeper doc (`app-overview.md` or similar) for the full briefing. Open the short doc with "Read the full overview before making changes" so the AI doesn't try to work from the summary alone.

A useful side effect: by the time you hand the prototype to engineering, your `AGENTS.md` *is* the spec. The prototype shows the behavior; the doc captures the why. There's no separate PRD to keep in sync.

**Save workflows as skills**

Rules tell the AI *how* you work. Skills tell the AI *what to do* — they're saved multi-step procedures for workflows you repeat.

Think of a skill as a recipe. Instead of saying "pull up the meeting notes from this week, find the action items, cross-reference with open Jira tickets, draft a status update in our team format, and post it to the #team-updates channel" every time, you save that entire workflow once. Then you just say "run the weekly update skill."

Skills come in two flavors. Most of yours will be the first kind. The second kind is where AI tooling starts to feel less like a chatbot and more like having a small team.

**Text-workflow skills** — synthesize, classify, draft, review. Inputs are docs and conversations; outputs are docs and messages. 80% of what you'll write.


| Workflow                   | What the skill encodes                                                                                                                              |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Customer feedback triage   | Scan a Slack channel for recent messages, classify each as bug/feature request/question, present a summary for your review                          |
| Sprint retrospective prep  | Pull completed tickets, meeting notes from the sprint, and any blockers — draft a retro doc with what went well, what didn't, and discussion topics |
| Competitive research brief | Given a competitor name, search your docs and notes for prior mentions, structure a brief with what you know and what gaps remain                   |


**Automation skills** — drive a browser, generate artifacts, call APIs, open PRs. The skill doesn't just *think*, it *does*. These take more effort to build but unlock workflows that aren't possible with a text-only loop.


| Workflow                                        | What the skill encodes                                                                                                                                                                                                                                                    |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Customer journey from a running prototype       | Workshop a persona with you, walk a real browser through your prototype, capture screenshots at each step, assemble a self-contained HTML deck (anchor: `[customer-journey](https://github.com/kylemaclaren/ai-tools/tree/main/skills/customer-journey)`)                 |
| Slack feedback → triage → PR (the agentic loop) | Scan your Slack channels, classify and rank items by signal, you pick what to ship, the AI does the implementation and opens the PRs against your repo (anchor: `[slack-feedback-to-pr](https://github.com/kylemaclaren/ai-tools/tree/main/skills/slack-feedback-to-pr)`) |


**When it's worth doing:**

- The workflow has 3+ steps that always happen in the same order
- You do it on a regular cadence (weekly, per-sprint, per-candidate)
- Someone else on your team would benefit from doing it the same way

**Share your setup with your team**

This is the multiplier. Once you've built scripts, written rules, and saved skills, other people on your team can use them too.

**What's shareable:**

- **Sync scripts** — "Here's how to pull our sprint tickets into a local folder." Others clone the script, plug in their own API token, and they're running.
- **Rules files** — "Here are our team's conventions for the AI." Drop them into a shared repo and everyone's AI follows the same guidelines.
- **Skills** — "Here's the weekly status update workflow." Others add it to their workspace and use it immediately.
- **Workspace templates** — "Here's a starter folder structure with our key docs, rules, and skills pre-configured." New team members clone it and start from a working setup instead of from scratch.

**The bar is install-by-prompt, not "here's a README"**

The lazy way to share is "here's a GitHub repo, follow the README." That's a 10-step setup most people will bounce off of. The good way is **install-by-prompt**: a single paragraph the user pastes into their AI editor, and the AI handles the clone, the dependencies, the auth, the config wiring, the launchd setup. No manual steps.

It looks like this:

> Install **{tool-name}** from `git@github.com:{you}/{repo}.git` (sparse checkout `<path>`). Set up the auth flow, install dependencies, then add it to my editor's MCP config and create a shell alias.

The user pastes that into Cursor, Claude Code, or Codex. Two minutes later they're running. Three benefits fall out:

- **Editor-agnostic** — same prompt works in any AI editor that can run a shell, so you stop having to maintain three sets of instructions
- **Self-updating** — the prompt describes intent, not specific commands, so it survives launchd changes, repo restructures, and per-OS quirks
- **Low-effort install** — closer to "install an app" than "set up a dev environment," which is what determines whether non-engineers actually adopt your tool

A worked example you can copy the pattern from: `[ai-tools](https://github.com/kylemaclaren/ai-tools)` — every tool's README has its own install-by-prompt block.

You don't need to be an engineer to maintain a shared repo. You need to be the person who figured out a good workflow and wants others to benefit from it. The AI handles the packaging.

---

## Quick-Start Checklist

If you want to get going today, pick your entry point based on what you want to do:

**If you want to prototype an app or demo:**

1. Sign up for Lovable and/or Replit
2. Describe what you want to build in plain English
3. Iterate by describing changes — "add a sidebar," "make the chart show weekly instead of monthly"
4. Share the live link with your team

**If you want AI that works with your files and tools:**

1. Install Cursor (or Claude Desktop if you don't want a code editor)
2. Create a project folder — something like `~/AI/` or `~/workspace/`
3. Put some files in it — download a few key docs as Markdown, or just create a notes file
4. Open the folder in Cursor (File > Open Folder)
5. Start a conversation — ask the AI to summarize a doc, draft a status update, or search across your files

**If you just want to start a conversation:**

1. Open Claude.ai or ChatGPT in your browser
2. Ask your question or paste in content you want help with
3. When you hit limits — "I wish it could see my other docs" or "I wish it could check Jira" — that's when you move to a tool with file access and MCP integrations

**If you've built something you want others to use:**

1. Put your scripts, rules, or skills in a GitHub repo (the AI helps you set it up)
2. Write an **install-by-prompt** block in the README — a single paragraph the user pastes into their AI editor that handles clone, deps, auth, and config
3. Send the prompt to a teammate. Two minutes later they're running.

Everything else — MCP servers, sync scripts, scheduled automation — is an optimization you add when the basic workflow clicks.