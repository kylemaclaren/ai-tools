---
name: slack-feedback-to-pr
description: Scan Slack channels for customer feedback and bug reports, triage them with the user, and ship the chosen fixes/features as PRs.
suggest_when: User says "scan Slack", "check Slack feedback", "triage feedback", "run the feedback workflow", or asks to turn Slack feedback into PRs.
---

<!-- Auto-generated. Edit upstream and re-run the publish script; do not edit here. -->

# Slack Feedback-to-PR Workflow

Scan a configured set of Slack channels for customer feedback, classify and rank what's in them, present the ranked list for the user to multi-select, then implement and open PRs for the items they chose.

**Trigger when** the user says any of: "scan Slack", "check Slack feedback", "triage Slack feedback", "run the feedback workflow", or similar.

**Compatible with the public Slack MCP** — uses `slack_list_channels` (resolve names to IDs), `slack_read_channel`, and `slack_read_thread`. Also requires the [`gh` CLI](https://cli.github.com/) on the user's `PATH` for opening PRs. The skill never posts to Slack itself — close-the-loop replies are drafted as copy/paste text for the user to send manually after merge.

## Version Check

Before starting, check for updates:

1. Read the local `VERSION` file in this skill's directory.
2. Fetch the latest version from GitHub:
   ```
   curl -sf https://raw.githubusercontent.com/kylemaclaren/ai-tools/main/skills/slack-feedback-to-pr/VERSION
   ```
3. If the remote version is newer than the local version, warn the user:
   > **Update available:** You're on slack-feedback-to-pr **v{local}**, latest is **v{remote}**. Ask your agent to pull the latest from GitHub. Proceeding with your current version.
4. If the fetch fails (network error, timeout), skip silently and proceed.

---

## Phase 0a: Pre-flight Checks

Before doing any real work, run these four checks. Run them in parallel, then present any failures as a single consolidated error block — don't fail one at a time.

1. **`gh` is authenticated.** Run `gh auth status`. If it fails, the fix hint is `gh auth login`.
2. **Slack MCP is reachable.** Call `slack_list_channels` with `limit: 1`. If the call errors, the fix hint is "check that a Slack MCP server is configured and authenticated in your editor's MCP config."
3. **Working directory is a git repo.** Run `git rev-parse --is-inside-work-tree`. If it fails, **hard fail** — there's nowhere for PRs to land. Fix hint: `cd` into the repo you want fixes shipped from, then re-run the skill.
4. **No uncommitted changes.** Run `git status --porcelain`. If output is non-empty, **warn and ask** — don't auto-fail:
   > Your working tree has uncommitted changes. Phase 4 will switch branches, which may conflict. Stash, commit, or proceed anyway?

   Options: `Stash` (`git stash push -m "slack-feedback-to-pr WIP"` and remember to `git stash pop` at end of run) / `Commit` (let the user handle it manually, then re-run) / `Proceed anyway` / `Cancel`.

Also capture the **current branch name** via `git rev-parse --abbrev-ref HEAD` and the **default branch name** via `git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'`. Use these in Phase 4 instead of hardcoding `main` — return to whichever branch the user started on.

---

## Phase 0b: Resolve the Channel Registry

The skill needs a list of Slack channels to monitor.

### Load channel names

Look for a `channels.yaml` file, in this order:
1. The current working directory.
2. This skill's own directory (next to `SKILL.md`).
3. If neither exists, ask the user to paste their channel names (e.g. `#my-product-feedback, #design-partner-acme`). Offer to save the result to `./channels.yaml` so it persists for next time.

The file is a simple list of channel names (with or without a leading `#`):
```yaml
- my-product-feedback
- design-partner-acme
- beta-feedback
```

### Resolve names to IDs

The Slack MCP's read tools take channel **IDs**, not names — so resolve the names once at the start of each run:

1. Call the Slack MCP's channel-listing tool — typically `slack_list_channels` (the public Slack MCP) or equivalent. Request both public and private channels the bot is a member of, with a high enough `limit` to cover the workspace (paginate if needed).
2. Build a `name -> id` map from the response.
3. For each channel name in `channels.yaml`, look up its ID. Strip any leading `#` before matching.
4. If a name doesn't resolve, warn the user (e.g. "couldn't find `#beta-feedback` — make sure the Slack MCP's bot user is invited to it") and skip that channel for this run. Don't fail the whole workflow.

Hold the resolved IDs in memory for the rest of this run — don't write them back to `channels.yaml`.

### Optional one-run scoping

If the user wants to scope a single run to a subset of channels (e.g. "just scan #my-product-feedback"), filter the registry to that subset for this run only — don't modify the saved file.

---

## Phase 0c: Load Triage State

The skill keeps a state file so successive runs only surface new feedback — no re-classifying yesterday's backlog.

### State file location

Look for `.feedback-triage-state.json` in the working directory. If it doesn't exist, create it on first run with the empty shape:

```json
{ "version": 1, "channels": {}, "items": [], "scans": [] }
```

The skill writes back to this file at end-of-run. Tell the user once that they should add `.feedback-triage-state.json` to their `.gitignore` — it's per-user runtime state, not committed config.

### Full state shape

```json
{
  "version": 1,
  "channels": {
    "C012345": { "name": "design-partner-acme", "last_scanned_ts": "1772561075" }
  },
  "items": [
    {
      "permalink": "https://yourworkspace.slack.com/archives/.../p...",
      "ts": "1772493603.389949",
      "channel_id": "C012345",
      "classification": "BUG",
      "summary": "Video playback freezes on seek",
      "first_seen_ts": "1772561075",
      "last_seen_ts": "1772561075",
      "pr_url": "https://github.com/.../pull/123",
      "pr_status": "open",
      "shipped": true
    }
  ],
  "scans": [
    { "ts": "1772561075", "items_collected": 27, "items_new": 5, "items_shipped": 2 }
  ]
}
```

Hold the parsed state in memory for the rest of the run. It informs Phases 1, 2, 4, and 5, and is rewritten at the very end.

### Escape hatch

If the user said "ignore triage state", "rescan everything", or "fresh scan", load the state file (so we can still write back to it) but **don't use it as a filter** — every message gets re-classified from scratch. State is still updated at end-of-run as normal.

---

## Phase 1: Collect Messages

For each channel in the registry:

1. Call `slack_read_channel` with:
   - `channel_id`: the ID from the registry
   - `limit`: 100
   - `response_format`: "detailed"
   - `oldest`: pick in this priority order:
     1. **Explicit user window** (e.g. "last 24 hours", "since Friday") — compute and use that timestamp.
     2. **State's `last_scanned_ts` for this channel** — if present, default to scanning only since the last successful scan.
     3. **Fallback: 7 days ago** — for first-ever runs (no state for this channel).
2. For any message that has a thread (reply count > 0), call `slack_read_thread` with the `channel_id` and `message_ts` to get the full conversation.
3. Skip bot messages and system/join/leave notifications.

Use parallel MCP calls where possible (batch channels in groups of 4–6).

---

## Phase 2: Analyze and Classify

Review all collected messages and classify each substantive message (or thread).

### 2a. Apply state filter

For each message, check whether its `permalink` is already in the state file's `items[]`:

- **Already shipped** (`shipped: true`) → skip silently. Don't re-surface.
- **Already triaged but not shipped** → carry the prior classification forward, update `last_seen_ts`, and label as **"carry-over from prior scan"** in the Phase 3 display so the user knows it's been hanging around.
- **Not in state** → fall through to fresh classification below.

(If the user invoked the "ignore triage state" escape hatch, skip this filter — every message gets fresh classification.)

### 2b. Apply reaction filter

Load the reaction config (see [reactions.example.yaml](reactions.example.yaml)) — from `./reactions.yaml`, then `<skill-dir>/reactions.yaml`, then baked-in defaults:

```yaml
skip:         [white_check_mark, done]
promote:      [thumbsup, heavy_plus_sign]
deprioritize: [eyes]
confirms_bug: [bug]
```

For each remaining message:

- If it has any reaction in `skip`, drop it (someone on the team has already marked it handled).
- Note any `promote`, `deprioritize`, and `confirms_bug` reactions for use in 2d (ranking) and 2c (classification).

### 2c. Classify

For each remaining message, classify into one of:

- **BUG** — Something is broken, erroring, or behaving unexpectedly. Tilt borderline cases here if the message has any `confirms_bug` reaction.
- **FEATURE_REQUEST** — A user is asking for new functionality or an improvement.
- **SKIP** — General chatter, status updates, greetings, or anything not actionable.

For each BUG or FEATURE_REQUEST, extract:

| Field | Description |
|-------|-------------|
| type | BUG or FEATURE_REQUEST |
| summary | One-sentence description of the issue or request |
| source_channel | Which channel it came from |
| reporter | Who said it (display name) |
| message_link | Slack permalink or channel/ts reference |
| severity | For bugs: critical / major / minor. For features: high / medium / low priority |
| details | AI-summarized repro steps (bugs) or user need / proposed solution (features) |
| verbatim_quote | The most relevant sentence(s) from the original message, copied **exactly as written**. Used in the PR Test Plan in Phase 4f. |
| signal_strength | See 2d. |

### 2d. Score signal_strength

Compute `signal_strength` per item as:

```
base   = reactions_count + (thread_replies * 1.5) + (cross_channel_recurrence * 3)
weight = 5  for each `promote` reaction present
       - 3  for each `deprioritize` reaction present
signal_strength = base + weight
```

Then:
- Deduplicate items that describe the same issue across channels.
- Rank by `signal_strength` descending.

---

## Phase 3: Present to User

Use your editor's structured multi-select prompt:
- **Cursor**: call `AskQuestion` with `allow_multiple: true`.
- **Claude Code / Codex / other**: present a numbered list and parse the user's reply (e.g. "1, 3, 5" or "all bugs").

Format each option label as:
```
[BUG|FEAT] <summary> (from #<channel>, <N> reactions, <M> replies)
```

Ask the user: "Which of these should I fix/build? Select all that apply."

If there are more than 10 items, split into two questions: bugs first, then feature requests.

If the user only wants the triage (no PRs), stop here and present the ranked list as a markdown table.

---

## Phase 4: Fix Code and Create PRs

For each item the user selected:

### 4a. Prepare the repo

From the root of the target git repo (the current working directory unless the user specifies otherwise). Use the **default branch name captured in Phase 0a** (don't hardcode `main`):

```bash
git fetch origin
git checkout <default-branch>
git pull origin <default-branch>
```

### 4b. Create a branch

- Bugs: `fix/<slugified-summary>` (e.g., `fix/video-playback-freezes-on-seek`)
- Features: `feat/<slugified-summary>` (e.g., `feat/add-bulk-export-option`)

```bash
git checkout -b <branch-name>
```

### 4b.5. Check for existing issues/PRs

Before implementing, check whether someone already filed (or started fixing) this exact thing. Pick 3–5 keywords from the item's `summary` and run:

```bash
gh issue list --search "<keywords>" --state open --json number,title,url --limit 5
gh pr list   --search "<keywords>" --state open --json number,title,url --limit 5
```

If matches come back, present them to the user with the editor's structured prompt:

```
Possible duplicates for "Video playback freezes on seek":
- Issue #234: "Video player freezes during scrubbing" (https://.../issues/234)
- PR    #501: "Fix seek bar event handling" (open) (https://.../pull/501)

What do you want to do?
```

Options:
- **Comment on existing #N** (one option per match) — run `gh issue comment <N> --body "<Slack reporter context, signal, message_link>"` for issues, or `gh pr comment <N>` for PRs. Skip Phase 4c–4f for this item; record `pr_url` in state as the existing one and mark `shipped: true`.
- **Open new PR anyway** — proceed to Phase 4c.
- **Skip this item** — drop it from the run; don't write to state.

If no matches, proceed silently to Phase 4c.

### 4c. Understand the codebase

Read the project's `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, and `README.md` for stack conventions and follow them strictly. If the project has a `CONTRIBUTING.md` or contributor guide, read that too. Don't edit auto-generated files (typically generated clients, lockfiles, `.env`).

### 4d. Implement the fix/feature

1. Search the codebase to find relevant files (use Grep, Glob, semantic search).
2. Make targeted changes following existing patterns and conventions.
3. Run the project's linter on all modified files and fix any introduced errors.
4. If the project has a fast test suite, run the relevant tests.

### 4e. Commit and push

```bash
git add -A
git commit -m "<type>: <summary>

<details from the Slack feedback>"
git push -u origin HEAD
```

### 4f. Create a PR

Use `gh pr create` with:
- **Title**: `<type>: <summary>` (e.g. `fix: video playback freezes on seek`)
- **Body** (HEREDOC format):
  ```
  ## Summary
  <1-2 sentence description>

  ## Source
  - Channel: #<channel-name>
  - Reporter: <who reported it>
  - Signal: <N> reactions, <M> thread replies
  - Slack: <message_link>

  ## Changes
  <bullet list of what was changed and why>

  ## Test Plan
  - [ ] <Lead item, see below>
  - [ ] <additional manual checks specific to the change>
  ```

  **Lead Test Plan item — use the `verbatim_quote` captured in Phase 2c.**

  For bugs:
  ```
  Reproduce the original report:
  > <verbatim_quote from Slack>
  Confirm the steps above no longer trigger the bug.
  ```

  For feature requests:
  ```
  Verify the change matches the original ask:
  > <verbatim_quote from Slack>
  Confirm the implementation covers what was requested.
  ```

  Quoting verbatim (rather than paraphrasing) gives the reviewer the customer's actual wording, which is often more specific than any AI summary.

### 4g. Return to the starting branch before the next item

Use the **starting branch captured in Phase 0a** (the branch the user was on when they kicked off the skill — not necessarily the default branch):

```bash
git checkout <starting-branch>
```

If Phase 0a stashed the user's WIP, leave the stash alone for now — it gets popped at end-of-run after Phase 5.

---

## Phase 5: Draft Close-the-Loop Replies

For each item that successfully became a PR **in this run** (regular, draft, or "comment on existing #N"), draft a short Slack reply the user can post back to the original reporter once the change is live.

Don't draft replies for items that were carried over from a prior scan and already had `pr_url` set — those replies were drafted in a previous run.

Skip this phase if the user has already said they don't want it (e.g. "skip the Slack replies" or "I'll close the loop manually").

**The skill never posts these itself.** It hands them to the user as copy/paste text, with a reminder to wait until the PR is merged before sending. This keeps the messages honest — they say "this is now live", which is only true after merge.

### 5a. Draft

Draft one reply per shipped item. The drafts are PR-agnostic — no PR links, no commit details, just an acknowledgement to the reporter. Pick the variant that matches the item:

| Item type | Draft |
|-----------|---|
| Regular PR fixing a bug | `Thanks for flagging — this is now live!` |
| Regular PR for a feature request | `Thanks for the suggestion — this is now live!` |
| Draft PR (AI couldn't fully ship) | `Thanks for flagging — taking a look at this.` |

Keep each draft to one short sentence. No "Hi!", no "Our AI assistant", no emoji. Match the reporter's tone if their original message was casual.

### 5b. Present in batch

Present all the drafts at once, grouped by reporter, in a single block the user can scan and copy from. Each entry should give them everything they need to find the original thread and paste the reply:

```
Reply to @alex in #design-partner-acme (thread: https://yourworkspace.slack.com/archives/C.../p...):
> Thanks for flagging — this is now live!

Reply to @sam in #beta-feedback (thread: https://yourworkspace.slack.com/archives/C.../p...):
> Thanks for the suggestion — this is now live!
```

Close with a one-liner reminder:

> Post these as thread replies once the PRs above are merged so the "now live" claim is accurate.

That's it for Phase 5 — the skill does not call any Slack write tools.

---

## Phase 6: Persist State

Write the updated triage state back to `.feedback-triage-state.json`:

1. **Update `channels[<id>].last_scanned_ts`** to the current Unix timestamp for every channel that was successfully scanned this run (skipped channels keep their old timestamp).
2. **Upsert each item** into `items[]` keyed by `permalink`:
   - New items get `first_seen_ts` and `last_seen_ts` set to now, with their classification recorded.
   - Carry-over items get `last_seen_ts` bumped to now.
   - Items that became PRs (in this run or via "comment on existing") get `pr_url`, `pr_status`, and `shipped: true`.
3. **Append a `scans[]` entry** with the run timestamp, total items collected, items new this run, and items shipped this run.
4. **Write atomically** — write to `.feedback-triage-state.json.tmp` and `mv` over the original, so a crashed write doesn't corrupt state.
5. **If Phase 0a stashed user WIP**, run `git stash pop` now to restore it.

Briefly tell the user what was written ("State updated: 5 new items recorded, 2 marked shipped").

---

## Error Handling

- If a channel returns `channel_not_found` or `not_in_channel`, skip it and note the error to the user — they probably need to invite the Slack MCP's bot user to that channel.
- If `gh pr create` fails, show the error and ask the user how to proceed.
- If the codebase fix is too complex or ambiguous, create the branch with a detailed `TODO` comment explaining the issue and what's known, push it, and open a **draft** PR (`gh pr create --draft`) so the user can take it from there.

---

## Output

After completing all selected items, present a summary table:

| # | Type | Summary | Branch | PR Link | Status | Slack draft |
|---|------|---------|--------|---------|--------|-------------|

Include links to all created PRs. The `Slack draft` column inlines the drafted reply (or `skipped` if the user skipped Phase 5) so the user has everything in one place when they come back to post replies after merge.
