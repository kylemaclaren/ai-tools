# granola-sync

Sync your [Granola](https://www.granola.so/) meeting notes and transcripts into a local folder as Markdown files, so your AI editor can reference past conversations.

## Who is this for?

Anyone who uses Granola to record meetings and wants those transcripts available in Cursor, Claude Code, or Codex — for example, to ask "what did we decide about pricing in last week's standup?" and have the AI find the answer in the actual transcript instead of the AI summary.

## What does it do?

1. Reads your login from the Granola desktop app automatically — no token setup required
2. Downloads meeting transcripts (and optionally the AI-generated notes panel) as `.md` files
3. Saves one file per meeting to a local folder (default: `~/granola/`)
4. Tracks what's already been synced, so subsequent runs only fetch new meetings

Each file is named `YYYY-MM-DD_Meeting_Title.md` and includes metadata (attendees, date), the verbatim transcript, and optionally the notes panel.

## Install

Open your AI editor (Cursor, Claude Code, or Codex) and paste this prompt:

> Install **granola-sync** from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `cli-tools/granola-sync`). Set up a shell alias so I can run `granola-sync` from anywhere.

The AI will clone the repo and add a `granola-sync` alias to your shell. The only prerequisite is having the [Granola](https://www.granola.so/) desktop app installed and logged in — the script reads your credentials from the app automatically.

The first time you run `granola-sync`, it will ask where you'd like meeting transcripts saved (default: `~/granola`) and remember your answer for next time.

## How to use it

```bash
granola-sync
```

### List recent meetings

```bash
granola-sync --list-meetings
```

Shows your 25 most recent meetings. Already-synced ones are marked with a checkmark.

### Sync meetings by title

```bash
granola-sync --meeting "Weekly standup"
granola-sync --meeting "Weekly standup" --notes
```

If the title matches multiple meetings (e.g. a recurring standup), all of them are synced. Combine with `--date`, `--after`, or `--limit` to narrow results.

### Filter by date

Supports absolute dates (`MM/DD/YY`, `YYYY-MM-DD`) and relative descriptors:

```bash
granola-sync --date today
granola-sync --date "last week"
granola-sync --date "February 2026"
granola-sync --after 2026-02-01 --before 2026-03-01
```

### Sync by folder

```bash
granola-sync --folder "Sales calls"
granola-sync --list-folders
```

### Include AI notes

By default, only the raw transcript is synced. To also include the Granola notes panel (manual notes + AI-generated content):

```bash
granola-sync --notes
```

### Test run

```bash
granola-sync --limit 3      # process only 3 meetings
granola-sync --dry-run      # preview without writing
```

### Re-sync

```bash
granola-sync --force --date 2026-03-05
```

### Override output directory

```bash
granola-sync --meeting "Project Kick-off" --output ~/Desktop/meetings
```

## Run it automatically (macOS)

If you want `granola-sync` to run in the background every 30 minutes so your meetings are always up to date, paste this prompt into your AI editor:

> Set up **granola-sync** to run every 30 minutes in the background on macOS using launchd. Find the absolute path to my `sync.py`, generate a launchd plist at `~/Library/LaunchAgents/com.<my-username>.granola-sync.plist` that invokes it with `python3` on a 1800-second interval (with `RunAtLoad` true and stdout/stderr redirected to a log file in the same folder as the script), then load it with `launchctl` and confirm it's running. Tell me the commands to start, stop, and uninstall it later.

To uninstall later, just ask the same AI editor: *"Uninstall the granola-sync launchd job."*

## State and troubleshooting

`state.json` tracks which meeting IDs have already been synced. Delete it to re-sync from scratch.

`config.json` remembers your output directory choice. Delete it to be re-prompted on the next run.

Both files are gitignored.

| Symptom | Fix |
|---|---|
| "Could not load Granola credentials" | Open the Granola desktop app and confirm you're logged in |
| "Token refresh failed" / HTTP 401 | Re-open the Granola desktop app; it refreshes the token cache |
| Missing transcript | The meeting may not have been transcribed yet, or transcription was disabled in Granola |

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
