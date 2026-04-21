# Slack Feedback-to-PR

Scan your Slack channels for customer feedback, triage it with the AI, and ship the chosen fixes as PRs — without leaving your editor.

## Who is this for?

PMs, designers, and engineers who collect product feedback in Slack (design-partner channels, beta channels, internal `#bugs` channels, support escalations) and want a tighter loop between "user reported it" and "fix is in review." Useful when:

- You have multiple channels' worth of feedback and need help finding the high-signal items.
- You want to skim a triaged list once a week instead of scrolling each channel by hand.
- You ship from a small repo where the AI can plausibly draft the fix end-to-end.

You stay in the loop on what gets built — the skill always pauses after triage and lets you multi-select what to ship before it touches code.

## What does it do?

1. **Pre-flight checks** — confirms `gh` is authenticated, the Slack MCP is reachable, you're in a git repo, and your working tree is clean (or asks before proceeding if it isn't).
2. **Reads channel registry** — uses a `channels.yaml` file you maintain (or asks once and saves it). Just channel names, one per line.
3. **Loads triage state** — reads `.feedback-triage-state.json` (per-user state, gitignored) so successive runs only surface new feedback. Default scan window per channel is "since the last successful scan" rather than a fixed 7 days.
4. **Pulls messages** — calls the Slack MCP across all channels in parallel, including replies on threaded messages, with an optional time window ("last 24h", "since Friday").
5. **Classifies, ranks, and respects reactions** — sorts each substantive message into `BUG`, `FEATURE_REQUEST`, or `SKIP`. Reads team reaction conventions from `reactions.yaml` (defaults shipped): `:white_check_mark:` skips items already handled, `:thumbsup:` promotes them, `:eyes:` deprioritizes them, `:bug:` confirms a borderline classification. Ranks the rest by signal (reactions + replies + cross-channel recurrence + reaction weights).
6. **Asks you what to ship** — presents the ranked list as a multi-select. You pick which items become PRs (or stop here for a triage-only run).
7. **Checks for existing issues/PRs** — before implementing each item, searches your repo's open issues and PRs for likely duplicates. If it finds one, you can comment on the existing item with the new Slack context instead of opening a duplicate PR.
8. **Implements + opens PRs** — for each remaining item: creates a branch, reads the project's contributor docs, makes the change, runs the linter, commits, pushes, and opens a PR with the original Slack context in the body. The PR's Test Plan leads with the customer's verbatim repro quote, so the reviewer sees the actual wording, not an AI summary.
9. **Drafts close-the-loop replies** — for each shipped item, drafts a short PR-agnostic reply ("Thanks for flagging — this is now live!") and presents them all together as copy/paste material with the original thread links. The skill never posts to Slack itself — you send the replies manually after the PRs merge, so the "now live" claim stays honest.
10. **Persists state** — writes back `.feedback-triage-state.json` so the next run picks up where this one left off.

If a fix is too ambiguous to write end-to-end, the skill opens a **draft** PR with a detailed TODO so you can take it from there.

## Install

Open your AI editor (Cursor, Claude Code, or Codex) and paste this prompt:

> Install the **slack-feedback-to-pr** skill from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `skills/slack-feedback-to-pr`) and symlink it into my editor's skills directory. Then make sure I have everything the skill needs: install the `gh` CLI via Homebrew if it's missing and prompt me to run `gh auth login` if I'm not authenticated; check whether a Slack MCP server is configured in my editor's MCP config — if not, walk me through installing the public Slack MCP and authenticating it; and finally, in the repo I'll be shipping fixes from, append `.feedback-triage-state.json` to the `.gitignore` (creating it if needed) so my per-user triage state never gets committed.

The AI handles the clone, the symlink, the `gh` install + auth, the Slack MCP wiring, and the `.gitignore` entry.

The skill itself will offer to create a [`channels.yaml`](#channelsyaml-format) for you on first run.

## How to use

Run from the root of the repo where you want the fixes shipped. Example prompts:

> "Scan Slack for new feedback from the last 24 hours."

> "Triage Slack feedback — but just give me the ranked list, don't open any PRs."

> "Run the feedback workflow against just `#my-product-feedback` and `#design-partner-acme` since Friday."

> "Scan Slack and prioritize bugs over feature requests — I only want to ship the top 3 bugs this sprint."

> "Run the feedback workflow but skip the Slack replies at the end — I'll close the loop manually."

> "Rescan everything from the last 30 days — ignore my triage state file."

The skill always pauses after triage to confirm what you want to ship, asks again before opening a PR if it finds a possible duplicate issue/PR, and pauses one more time before drafting close-the-loop replies. You can also stop it after the triage phase if you just want a ranked report.

### Expected output

After Phase 3, you'll see a multi-select list like:

```
[ ] [BUG]  Video playback freezes on seek (from #design-partner-acme, 4 reactions, 6 replies)
[ ] [BUG]  Export button doesn't trigger download in Safari (from #beta-feedback, 2 reactions, 3 replies)
[ ] [FEAT] Add bulk-export option to project list (from #design-partner-acme, 5 reactions, 1 reply)
...
```

After Phase 4 the skill drafts a short, PR-agnostic Slack reply for each shipped item and presents them all together as copy/paste material — with a reminder to wait until merge before posting:

```
Reply to @alex in #design-partner-acme (thread: https://yourworkspace.slack.com/archives/C.../p...):
> Thanks for flagging — this is now live!

Reply to @sam in #beta-feedback (thread: https://yourworkspace.slack.com/archives/C.../p...):
> Thanks for the suggestion — this is now live!

Post these as thread replies once the PRs above are merged so the "now live" claim is accurate.
```

The skill never posts to Slack itself — you copy/paste the drafts into the original threads after the PRs merge. This keeps the messages honest and keeps you in control of the customer-facing comms.

After everything wraps, you'll see a summary table:


| #   | Type | Summary                        | Branch                               | PR Link                                                            | Status | Slack draft                                    |
| --- | ---- | ------------------------------ | ------------------------------------ | ------------------------------------------------------------------ | ------ | ---------------------------------------------- |
| 1   | fix  | Video playback freezes on seek | `fix/video-playback-freezes-on-seek` | [https://github.com/.../pull/123](https://github.com/.../pull/123) | open   | `Thanks for flagging — this is now live!`      |
| 2   | feat | Add bulk-export option         | `feat/add-bulk-export-option`        | [https://github.com/.../pull/124](https://github.com/.../pull/124) | draft  | `Thanks for flagging — taking a look at this.` |


## Reference

### `channels.yaml` format

Place this in the working directory (the repo where you want fixes shipped) or alongside `SKILL.md` in the skill's own directory. Just the channel names, one per line — the leading `#` is optional:

```yaml
- my-product-feedback
- design-partner-acme
- beta-feedback
```

The skill resolves names to channel IDs at the start of each run via the Slack MCP. The bot user attached to your Slack MCP must be a member of every channel listed here — invite it once with `/invite @your-mcp-bot` in each channel. If a name doesn't resolve, the skill warns you and skips that channel for the run.

### `reactions.yaml` format (optional)

Customize how the skill interprets Slack reaction emoji. If this file is missing, sensible defaults are used — copy [`reactions.example.yaml`](./reactions.example.yaml) to `reactions.yaml` only if you want to override.

```yaml
skip:         [white_check_mark, done]       # already handled — drop from triage
promote:      [thumbsup, heavy_plus_sign]    # boost in ranking
deprioritize: [eyes]                         # someone's on it — downrank
confirms_bug: [bug]                          # tilt borderline cases toward BUG
```

Reaction names are bare (no surrounding colons) and custom workspace emoji are supported. The four sections are independent — omit any you don't want, and the skill falls back to defaults for that section. Particularly handy if your team already uses reactions to triage manually: the skill picks up where you left off instead of asking you to start a new convention.

### `.feedback-triage-state.json`

The skill writes per-user state to `.feedback-triage-state.json` in the working directory. It tracks last-scanned timestamps per channel, every item ever triaged (with classification + PR link if shipped), and a per-run scan summary. This is what lets each subsequent run skip what you've already seen and only surface new feedback.

The install prompt above already adds this file to your `.gitignore`. If you didn't run that prompt, add it manually — it's per-user runtime state, not committed config.

To start over (e.g. after a major release), delete the file and re-run, or use one of the escape-hatch prompts above ("rescan everything", "ignore triage state").

### Classification taxonomy


| Type              | What it covers                                                         |
| ----------------- | ---------------------------------------------------------------------- |
| `BUG`             | Something is broken, erroring, or behaving unexpectedly                |
| `FEATURE_REQUEST` | A user is asking for new functionality or an improvement               |
| `SKIP`            | General chatter, status updates, greetings, or anything not actionable |


### Fields extracted per item


| Field             | Description                                                                                                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `type`            | `BUG` or `FEATURE_REQUEST`                                                                                                                                         |
| `summary`         | One-sentence description                                                                                                                                           |
| `source_channel`  | Where it came from                                                                                                                                                 |
| `reporter`        | Who said it                                                                                                                                                        |
| `message_link`    | Slack permalink                                                                                                                                                    |
| `severity`        | `critical`/`major`/`minor` (bugs) or `high`/`medium`/`low` (features)                                                                                              |
| `details`         | AI-summarized repro steps (bugs) or user need / proposed solution (features)                                                                                       |
| `verbatim_quote`  | The most relevant sentence(s) from the original Slack message, copied exactly. Lifted into the PR's Test Plan so reviewers see the customer's actual wording       |
| `signal_strength` | `reactions + (replies × 1.5) + (cross_channel_recurrence × 3)`, plus weights from `reactions.yaml` (`+5` per `promote` reaction, `-3` per `deprioritize` reaction) |


### What stops a PR from being shipped end-to-end?

The skill opens a **draft** PR with a TODO instead of a regular PR when:

- The repo's contributor docs (`AGENTS.md` / `CLAUDE.md` / `CONTRIBUTING.md`) describe a process the AI can't fully follow autonomously (e.g. requires running an integration test the AI can't run).
- The fix touches auto-generated files (lockfiles, generated clients) that the project guides flag as "do not edit".
- The change is large enough that the AI's confidence is low and it would rather hand off than guess.

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).