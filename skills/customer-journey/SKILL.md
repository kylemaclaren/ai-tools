---
name: customer-journey
description: Generate a self-contained HTML customer journey presentation from a running prototype. Captures real screenshots via Playwright and combines them with persona/JTBD narrative.
suggest_when: User asks to create a journey doc, UX walkthrough, customer journey presentation, design review deck, prototype walkthrough, or says "document this prototype", "show the user flow", "create a demo deck".
---

<!-- Auto-generated. Edit upstream and re-run the publish script; do not edit here. -->

# Customer Journey

Generate a self-contained HTML presentation from a running prototype. Captures real screenshots via Playwright and combines them with persona/JTBD narrative from a single YAML manifest. Output is one `.html` file with inline JPEG images — no external dependencies, no hosting required.

**Trigger when**: the user asks to create a journey doc, UX walkthrough, customer journey presentation, design review deck, or prototype walkthrough for a web project.

## Version Check

Before starting, check for updates:

1. Read the local `VERSION` file in this skill's directory.
2. Fetch the latest version from GitHub:
   ```
   curl -sf https://raw.githubusercontent.com/kylemaclaren/ai-tools/main/skills/customer-journey/VERSION
   ```
3. If the remote version is newer than the local version, warn the user:
   > **Update available:** You're on customer-journey **v{local}**, latest is **v{remote}**. Ask your agent to pull the latest from GitHub. Proceeding with your current version.
4. If the fetch fails (network error, timeout), skip silently and proceed.

## Prerequisites

Install dependencies on first use:

```bash
cd <skill-dir> && npm install
npx playwright install chromium
```

## Workflow

### 1. Draft the manifest

Check if `journey.yaml` already exists in the project directory (look first in `<project>/customer-journey/journey.yaml`, then fall back to `<project>/journey.yaml` for older projects).

**If it exists:** Read it and use it as-is. Confirm with the user before making changes.

**If it does not exist:** Build it with the user. Do this as a real conversation, not a template fill-in. The deck is only as strong as the persona and JTBDs — spend time here.

1. **Ground the persona in evidence.** Read the prototype project's `AGENTS.md`, `README.md`, and any other docs to understand the product and its target user. If the workspace has an `org-context/` or `interviews/` folder, check for real customer/persona research to anchor on. If you find conflicting signals, surface them and ask the user which to prioritize. Never invent a persona from whole cloth when real user research is available.
2. **Workshop the persona.** Propose a name, role, and a short description. Present in chat and iterate. Aim for a persona that would be recognizable to anyone in the ICP — specific role + specific responsibilities + the kind of day they actually have. Avoid generic "tech-forward professional" framings. Skip a separate "accountabilities" list: the JTBDs cover that ground, and a dedicated slide just repeats the same content twice.

   Once the persona is locked, **pick an avatar**. The skill ships 62 bundled stock fake-user faces (`avatars/work/` + `avatars/personal/`, sourced from a design system tokens file). Open `<skill-dir>/avatars/index.html` in a browser to browse them, then set `persona.avatar:` in the manifest to the full name (e.g. `"Sara Letzinger"`). Real faces beat text-only persona slides — strangers retain a persona much better when it has a face attached. If none of the bundled options fit the persona (e.g. the product targets a specific demographic not represented in the set), drop a custom JPEG/PNG next to the manifest and reference it by relative path (e.g. `avatar: "./alex.jpg"`). Absolute paths also work.
3. **Workshop the JTBDs (this is the one to get right).** JTBDs are what the persona is trying to accomplish in their life or work, independent of our product. Apply this quality bar before moving on:

   **Good JTBDs** (what execs actually respond to):
   - "Get contracts signed without disrupting my creative flow."
   - "Know who's signed and who's still dragging their feet."
   - "Make it easy enough for the other side that they actually sign."

   **Anti-patterns to reject** — if the draft JTBDs read like any of these, push back and rework:
   - *Feature-discovery framing*: "Find out that Sign is available in Dropbox." The persona isn't trying to discover our product; they're trying to get their job done.
   - *Monetization framing*: "Upgrade to premium," "Convert to a paid plan." That's our job, not theirs.
   - *Onboarding/activation framing*: "Complete setup," "Finish my profile." Same problem — our funnel is not their job.
   - *Internal-product problems*: "Learn about new features," "Migrate from legacy." Again, not their job.
   - *Vague aspirations*: "Be more productive," "Collaborate better." Too abstract to design against.

   The litmus test: *would this persona describe this job in these words even if our product didn't exist?* If no, rewrite.

   Aim for **3–5 JTBDs**. Fewer is fine. More than 5 starts to dilute the narrative.

4. Ask whether the deck needs a **thesis slide** — a narrative frame between the persona and the JTBDs. Good for an "Our bet" / "The opportunity" / "Why now" framing. Optional.
5. **Map JTBDs to journeys 1:1, and keep each journey to 3–7 captured frames.** Each JTBD becomes one numbered journey that *delivers* on that promise through real prototype screens. Give each journey a `jtbd` (the full sentence from step 3) and a short `headline` (the punchy title-card version). When every journey carries a `jtbd`, the JTBDs list slide auto-derives from them — single source of truth, no risk of drift. **If a journey would run longer than 7 captured frames, split it** into two journeys (each with its own JTBD) rather than letting one journey become a 10-frame slog. Cognitive load matters: execs stop tracking a story past ~7 beats. If a journey shows the same JTBD across two surfaces (e.g., in-app + CLI + chat), use the `rows:` field to stack multiple rows under one journey number with `sub_label`s like `"1a — In the app"` / `"1b — In the CLI"`. If the deck has natural sections, ask if any journey should carry a **part label** (e.g., "Part 1 — Discovery") — renders as an eyebrow above the journey number.
6. For the JTBDs slide `headline`, default to **"How this shows up for {persona.name}."** (e.g., "How this shows up for Alex.") unless the user has a stronger framing. This phrase ties the list directly to the persona just introduced on the previous slide and reads as a natural bridge into the journeys.
7. Ask if the deck needs a **recap slide** before the demo CTA. Optional.
8. Ask if there's a **live demo URL** (Lovable, Vercel, staging) for the final CTA slide. Optional.
9. Save the result as `<project>/customer-journey/journey.yaml` (see [Project layout](#project-layout) below).

The manifest is the single source file. It defines everything:

- **project**: name, date
- **persona**: name, role, description, `avatar` (optional — a name from the bundled set, a relative path, or an absolute path; see [Persona avatars](#persona-avatars))
- **thesis** (optional): narrative bridge slide between persona and JTBDs. Object with `eyebrow`, `headline`, `subtitle`.
- **jtbds**: numbered jobs-to-be-done. Three shapes supported:
  - Plain array of strings — uses default slide titles.
  - Object `{ eyebrow, headline, items: [...] }` — explicit items with custom titles.
  - Object `{ eyebrow, headline }` (no `items`) — items are **derived from `journeys[*].jtbd`** in declaration order. This is the recommended shape: keeps the list promise and the journey delivery in one place.
- **dev_server**: command and port to start the app
- **viewport**: width and height for screenshots (default 1440x900)
- **click_indicators** (optional): `true` (default) or `false`. When `true`, every captured frame gets a pink dot on the element the user is about to click to reach the next frame — see [Click indicator](#click-indicator). Set `false` for decks whose flow isn't driven by discrete user clicks.
- **journeys**: numbered sections. Each journey supports:
  - `number` — journey number for the title card.
  - `jtbd` (optional but recommended) — the full JTBD sentence. Renders as a subtitle under the journey headline and flows into the derived JTBDs list.
  - `headline` (optional) — short punchy title (e.g., `"Drafting a contract."`). Falls back to `title` for back-compat.
  - `title` — back-compat alias for `headline` when no `headline` is set.
  - `part_label` (optional) — eyebrow above the journey number (e.g., "Part 1 — In Dropbox").
  - `steps` — Playwright step list (single-row journey).
  - `rows` (alternative to `steps`) — array of row objects, each with `sub_label` + either `steps` or `extend: <key>`. Use this for multi-surface journeys where one JTBD is demonstrated across two or more surfaces (e.g., in-app and CLI).
  - Use a sentinel top-level entry of the form `- extend: <key>` to reserve a whole-journey slot for a companion sidecar script. Sub-row extend entries work the same way inside `rows:` (see [Extension slots](#extension-slots) below).
- **recap** (optional): closing narrative slide rendered just before the demo CTA. Same shape as `thesis`.
- **demo_link** (optional): URL to a live demo (e.g., Lovable, Vercel, staging). If set, generates a final CTA slide with a clickable button so viewers can jump into the prototype. Can be a string (just the URL) or an object with `url`, `label`, and `eyebrow`.

Each step can have:
- `url` — navigate to this URL (supports `${varName}` interpolation)
- `actions` — array of browser actions to perform before screenshot
- `wait` — milliseconds to wait before screenshot (default 800)
- `waitFor` — CSS selector to wait for before screenshot
- `caption` — narrative text describing what the user is doing (third-person present tense)
- `screenshot: false` — skip the screenshot for this step (utility steps)

**Action types:**
- `click` — by `text`, `role`+`name`, or `selector` (optional `scope` to narrow, `exact` for text matching). See [Click action options](#click-action-options) for `button`, `clickCount`, `modifiers`, `force`, and `position`.
- `fill` — by `placeholder` or `selector`, with `text` value
- `hover` — by `text`, `role`+`name`, or `selector`
- `key` — press a keyboard key (e.g., `Escape`, `Enter`)
- `scroll` — scroll element into view by `selector`
- `store` — evaluate JS (`eval`) and store result under `name` for later URL interpolation
- `eval` — run arbitrary JS in page (`script`)
- `wait` — explicit pause (`ms`)

**Keep the manifest readable.** For anything beyond a one-or-two-journey throwaway, use the [step recipe pattern](#step-recipes-keeping-the-manifest-readable): write each step's actions once under a `step_library:` block at the bottom of the file, then reference them from the journey body with `do: <recipe-name>`. The journey body becomes a scannable list of `do:` + `caption:` pairs that a non-engineer reader can follow and edit. Reach for inline `actions:` only for genuinely one-off sequences in tiny manifests.

### 2. Review with user

Present a structured summary of the manifest in chat — not the raw YAML. Include:

- **Project name and date**
- **Persona**: name, role, and description in one short paragraph
- **Jobs to be done**: numbered list (the `jtbd` from each journey if derived)
- **Each journey**: headline, followed by a numbered list of step captions only (omit selectors, actions, wait times, and other technical details)

Before asking for generation approval, run the **JTBD sanity check** out loud:

> "These JTBDs read as things [Persona] would describe even if our product didn't exist. None of them are 'discover feature X' or 'convert to paid'. Each one maps 1:1 to a journey that delivers it. Anything to tighten before we generate?"

If you can't say that truthfully, revise before proceeding. Then end with: "Ready to generate? Or would you like to edit anything first?"

If the user requests changes (persona, JTBDs, journey flow, captions, or step order), apply them to the YAML and re-present the updated summary. Only proceed to step 3 after the user confirms.

### 3. Start the dev server

Start the prototype project's dev server and confirm it's running:

```bash
cd <prototype-project> && npm run dev
```

Wait for the server to be ready before proceeding.

### 4. Generate the journey

Run a single command that captures screenshots and generates the HTML:

```bash
node <skill-dir>/journey.mjs <project>/customer-journey/journey.yaml
```

This launches Playwright headless, walks through each journey step, captures JPEG screenshots, and writes:

- `<project>/customer-journey/journey.html` — self-contained deck with all images embedded as data URIs (shareable as a single file).
- `<project>/customer-journey/assets/NN-<caption-slug>.jpg` — one standalone JPEG per captioned step for easy individual-frame sharing. Pass `--no-assets` to skip.

**Fast regeneration (copy/link edits only):** If the user changes text content — captions, persona, JTBDs, `demo_link`, project name — but has not changed the step structure, skip Playwright and reuse the existing screenshots:

```bash
node <skill-dir>/journey.mjs <project>/customer-journey/journey.yaml --no-capture
```

Use this whenever:
- The user edits a caption, persona, JTBD item, journey `jtbd`, journey `headline`/`title`, thesis, recap, part label, sub-row label, JTBDs slide eyebrow/headline, or demo link
- The step count and order are unchanged (including the order of rows within a multi-row journey)
- `journey.html` already exists from a prior capture

Do **not** use `--no-capture` if:
- A step was added or removed
- A step's `url`, `actions`, `wait`, or `screenshot: false` changed (the screenshots would be stale)
- `click_indicators` was toggled at the top level (dots are baked into the JPEGs at capture time)
- The prototype UI itself changed

If the step count in the manifest doesn't match the existing HTML, the script will abort with a clear error message and you should fall back to a full capture.

If the project uses a sidecar (`journey-extend.mjs` — see [Extension slots](#extension-slots)), run it immediately after the skill to fill any `<!-- extend:* -->` placeholders:

```bash
node <project>/customer-journey/journey-extend.mjs
```

`--no-capture` is safe to combine with a sidecar: the placeholder comments are re-emitted on every build.

### 5. Caption review pass (do this every full capture)

Captions are drafted *before* the screenshots exist, so they're best-guess descriptions of what the UI will show. Once the JPEGs are on disk, walk back through them and reconcile every caption against what's actually rendered. This is mandatory after every full capture (and after any prototype UI change), and it's the highest-leverage step for keeping the deck credible.

For each captioned frame, open the corresponding `customer-journey/assets/NN-*.jpg` and verify the caption against what's actually visible:

1. **Read the image.** Don't trust the captured text alone — actually inspect the rendered UI for column names, badge colors, button labels, copy in headers, presence/absence of icons, and any toast or modal state.
2. **Check every concrete claim** the caption makes:
   - Specific UI labels ("Access column" vs. what the prototype really calls it)
   - Badge colors and shapes ("amber badge" vs. blue, "Users icon" vs. inbound arrow)
   - Counts and names ("3 shares inside" vs. "Contains shared")
   - Icons referenced ("blue arrow" — is there actually one?)
   - State claims ("permission flips from view to edit" — does the screenshot show the new state, or just the toast?)
3. **Rewrite anything that doesn't match the screenshot**, while preserving the narrative beat for that frame. The goal is "what an exec sees in the screenshot supports the words underneath," not "rewrite the story."
4. **Soften unverifiable claims.** If a caption asserts a color or icon that's hard to read in the JPEG, swap to a description of the *behavior* or *position* (e.g., "the small inbound arrow next to the filename" vs. "the purple arrow"). If a tool/feature isn't visible in the dock or canvas, frame it as context rather than as something the viewer can spot.
5. **Apply the edits to `journey.yaml`**, then run with `--no-capture` to regenerate the HTML. The screenshots stay; only the captions change.

A useful litmus test before declaring done: *if a stranger looked at this frame with the caption hidden, would they recognize the elements the caption calls out?* If not, the caption is over-claiming.

### 6. Review output

## Project layout

All generated artifacts live in a single `customer-journey/` folder inside the prototype repo:

```
<project>/
└── customer-journey/
    ├── journey.yaml           # single source file — edit this
    ├── journey.html           # generated deck (self-contained, shareable)
    ├── assets/                # generated — one standalone JPEG per step
    │   ├── 01-alex-opens-dropbox.jpg
    │   ├── 02-clicks-new.jpg
    │   └── ...
    ├── extend.yaml            # optional — bespoke sidecar data
    └── journey-extend.mjs     # optional — project-specific sidecar renderer
```

The HTML stays self-contained (inline data URIs), so sending just that one file to stakeholders still works. The `assets/` folder is additive: use it when you need to drop an individual screenshot into a Slack thread, Paper doc, or slide.

## Output

| File | Source |
|------|--------|
| `customer-journey/journey.yaml` | Single source file — edit this |
| `customer-journey/journey.html` | Generated presentation (self-contained, inline images) |
| `customer-journey/assets/*.jpg` | Generated standalone JPEGs, one per captioned step |

The HTML uses a presentation aesthetic: dark title/persona slides, light screenshot rows, Space Grotesk + Inter typography, yellow accents, horizontal scroll with snap, and click-to-zoom lightbox with prev/next navigation.

## Publishing

The generated `journey.html` is self-contained (inline images), so sharing it is as simple as sending the file. If you'd rather paste a stable URL in Slack, the skill ships a `publish.sh` helper that uploads the deck to a public GCS bucket.

**One-time bucket setup** (create one in any GCP project you own and swap the bucket name below):

```bash
gcloud storage buckets create gs://YOUR-BUCKET-NAME \
  --project=<your-gcp-project> \
  --location=us-central1 \
  --uniform-bucket-level-access \
  --no-public-access-prevention

gcloud storage buckets add-iam-policy-binding gs://YOUR-BUCKET-NAME \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

**Publish a deck.** When the user says something like *"re-publish my journey,"* *"publish the journey,"* or *"push the latest deck,"* run the bundled `publish.sh` helper from the root of the prototype repo (the directory that contains `customer-journey/journey.html`):

- Resolve `<skill-dir>` from where this skill is installed (e.g. `~/.cursor/skills/customer-journey/` or wherever the user symlinked it). Do **not** ask the user to type the path.
- Use the prototype repo's directory name as `<project-name>` unless the user specifies a different one.
- Then invoke: `bash <skill-dir>/publish.sh <project-name>`

Expected output line: `Published: https://storage.googleapis.com/YOUR-BUCKET-NAME/<project-name>/journey.html` — paste that URL back to the user.

**Behavior**:
- Re-running overwrites the same object — the URL stays stable across every publish, so you only paste it in Slack once.
- Uploads with `Cache-Control: no-cache` so viewers always see the latest push without a hard-refresh.
- The bucket is public read. Anyone with the URL can view the deck — safe for internal product review decks, not safe for NDA-sensitive content or screenshots with real customer data.
- If you're forking this skill with your own bucket, edit the `BUCKET` and `HOST` constants at the top of `publish.sh`.

## Click indicator

Every screenshot is analyzed against the next captioned frame, and a small pink dot is painted on the element that the next click will target — so viewers can follow "the user clicked here → this happened" as they read through the deck.

**Which frames get a dot:**
- A frame gets a dot only when the **immediately next captioned frame** advances via a click in the same page (no intervening navigation, no intervening dwell).
- Dwell/informational frames (pure captions with no actions) get no dot — and the frame right before them also gets no dot, because a dwell frame is the same underlying layout and it will own the dot itself if a click follows.
- Frames where the next step navigates to a new URL get no dot (the clicked element lives on a different page).
- The final frame of each run gets no dot.

**Scroll-into-view on dot frames:** If the click target is off-viewport (e.g. in a sidebar below the fold), the script scrolls it in before screenshotting so the dot is always visible. This means authoring YAML rarely needs a manual `scroll` action — previewing the next click handles it automatically.

**Frame state vs. caption:** The dot lives on the frame immediately before a click, so if a step needs to set up visible state before the click (e.g. filling a form), put those `fill` actions on that earlier step, not bundled with the click. The screenshot then shows the filled form with the dot on the submit button — matching what the viewer expects.

**Project-wide toggle:** Set `click_indicators: false` at the top of the manifest to suppress dots entirely. Useful for decks whose visual flow isn't driven by discrete user clicks (marketing tours, state galleries, data dashboards). Default is `true`.

```yaml
click_indicators: false  # disable pink dots for the whole deck
```

## Click action options

The `type: click` action accepts a few Playwright-style modifiers for desktop/native flows where a plain left-click isn't enough. Combine these with any locator (`text:`, `role:`, `selector:`, `scope:`).

| Option | Values | Use it for |
|--------|--------|-----------|
| `button` | `"right"` (default `"left"`) | Right-click context menus — e.g. native Finder/Explorer-style menus inside a prototype. |
| `clickCount` | `2` | Double-click — e.g. opening a folder in a Finder window where single-click only selects. |
| `modifiers` | `["Meta"]`, `["Shift"]`, `["Control"]`, `["Alt"]` (or any combination) | Modifier-key clicks — e.g. ⌘-click to multi-select, Shift-click to range-select. Use `"Meta"` for ⌘ on macOS prototypes; `"Control"` for the Windows equivalent. |
| `force` | `true` | Bypass actionability checks (clicks even if the target is "covered" — useful for shadcn checkboxes that sit under a hover overlay). |
| `position` | `{ x: number, y: number }` | Click at a specific offset inside the target. |

```yaml
# Right-click a Finder row to open a context menu.
- type: click
  selector: "[data-app='finder'] span:text-is('Logo-Suite-Verdant.zip')"
  button: "right"

# Double-click a folder to navigate into it.
- type: click
  selector: "[data-app='finder'] span:text-is('Clients')"
  clickCount: 2

# ⌘-click a second row to add it to the selection.
- type: click
  selector: "[data-app='finder'] span:text-is('Logo-Suite-Verdant.zip')"
  modifiers: ["Meta"]
```

The click indicator (pink dot) follows the locator regardless of modifiers — so the dot for a right-click sits on the target row, and the next frame naturally shows the context menu.

## Persona avatars

A face on the persona slide makes the persona feel like a person, not a template. The skill ships 62 bundled stock fake-user avatars — the same kind of stock faces product designers use — so every deck can have one without anyone having to dig through Figma.

**What's bundled** (256×256 JPEGs, ~1.5 MB total):

- `avatars/work/` — 39 professional headshots (studio backdrops, office settings)
- `avatars/personal/` — 23 casual portraits (home, outdoors, natural light)
- `avatars/index.json` — machine-readable manifest mapping each name to its file
- `avatars/index.html` — open this in a browser to browse and pick. Names render under each round thumbnail so you can copy one straight into the manifest.

**Usage** — set one of these in the manifest:

```yaml
persona:
  name: "Alex"
  role: "Owner at Moonhelm Marketing"
  avatar: "Sara Letzinger"       # name from the bundled set (case-insensitive)
  # avatar: "./alex.jpg"         # relative path — looked up next to journey.yaml
  # avatar: "/Users/me/alex.jpg" # absolute path
  description: "..."
```

The resolver tries each in order:

1. **Name lookup** in `avatars/index.json` — works for any of the 62 bundled names.
2. **Path reference** — anything containing a `/` or a file extension is treated as a path and resolved against the manifest's directory (for project-specific custom avatars), or used as-is if absolute.
3. **Unknown** — logs a warning and renders the slide without an avatar (never fails the build).

The image is read at capture time, base64-encoded, and inlined into `journey.html` — the final deck stays self-contained. Published HTML files are still one-file shareable.

**Adding a custom avatar**: drop a JPEG or PNG next to `journey.yaml` (e.g. `customer-journey/alex.jpg`), then reference it as `avatar: "./alex.jpg"`. Square crops look best (it renders in a 160px circle); anything off-square will be object-fit cropped to center.

**Re-pulling the bundled set from Figma**: the asset URLs from the Figma MCP expire after 7 days, so the download script embeds fresh URLs only at the time it's run. If the avatars folder ever disappears or needs refreshing, open `avatars/.download.mjs` — the URLs at the top of that file are a snapshot; fetch new ones from the DIG Global/Tokens file (node `789:0`, frames `People/Work` at `38239:10386` and `People/Personal` at `38239:10511`) and re-run `node avatars/.download.mjs`. The script is idempotent and overwrites in place.

**Handoff avatars in journey frames** (future): the same resolver will eventually power per-frame avatars — showing a different face when the persona hands work off to a client or teammate. Not wired yet; the avatar is currently persona-slide-only.

## Step recipes (keeping the manifest readable)

For anything beyond the smallest demo, write step actions once in a `step_library:` section at the bottom of the manifest, then reference each one from the journey body with a `do:` shortcut. The journey body shrinks to a scannable list of `do:` + `caption:` pairs — what the user is doing and what the reader will see — and all the Playwright-flavored selectors stay below a clear "do not edit" boundary.

**Why this matters**: the human reading or editing the manifest (the PM, the design partner, the exec) cares about the captions, the JTBDs, and the order of beats — not whether a checkbox needs `force: true`. Burying the technical bits keeps the script credible and editable without specialized knowledge.

**How it works**: a step written as `{ do: <recipe-name>, ...overrides }` is expanded at load time to `{ ...recipe, ...overrides }`. Frame-level keys (`caption`, `wait`, `screenshot`, `url`, …) override the recipe's defaults, so one recipe can serve many frames with different copy or pacing.

**Authoring rules**:
- **Every row in the journey body should produce a captured frame.** That means every `do:` row gets a `caption:`, and they line up 1:1 with the screenshots in the rendered deck. A reader scanning the body sees the deck.
- **3–7 captured frames per journey.** A journey longer than that taxes the reader and usually means it's really two JTBDs stuck together — split it. Aggressively collapse "she opens folder X, then folder Y" hops: bake the intermediate navigation clicks into the recipe of the next *valuable* captured frame. The click-dot rule is not "show the literal screen-to-screen path" — it's "make it clear how the viewer got from A to B." A dot on `Clients` followed by a Verdant-contents frame is a legible jump; the reader fills in the intermediate step. Reserve captured frames for beats that *show something new* (new UI, new state, new value), not for tour-guide navigation.
- **No orphan utility rows.** If a step needs setup actions that don't deserve their own screenshot (e.g. an intermediate selection or folder navigation), bake those actions into the recipe of the *captured* step that follows. `select_brief_hero_and_carousel` belongs in one recipe, not split into a silent `select_brief` plus a captioned `select_hero_and_carousel`. The single tolerated exception is a one-time `bootstrap_welcome` at the very top of the deck — modal dismissals or other session priming that has no captured step to attach to. Mark it with a `# one-time setup` end-of-line comment so its captionless presence reads as deliberate, not as a bug.
- **No `wait:` overrides in the body.** Bake the right wait into the recipe (`wait: 2000` is a fine default for dwell frames; click-driven recipes usually need `wait: 1000–2500` to let animations settle). If two frames really need different pacing for the *same* action, that's a sign you want two recipes with different intent in their names — keep tuning out of the script.
- **No runner config in the body's reading path.** Move `dev_server`, `viewport`, `click_indicators`, and `step_library` itself below the same "do not edit" banner so the human reading the file from the top hits persona → JTBDs → journey beats → recap, in that order, with no plumbing in between.
- **Name recipes after the user action they encode** (`select_brief`, `nav_clients`, `enable_branded_share`), not after their selector. Reading the journey body should still tell the story.
- **Reuse recipes across journeys** whenever the same action repeats. If two beats only differ in caption, that's one recipe.
- **A recipe with no `actions:`** (just `url:` + `wait:`) is a valid "dwell" frame — useful for the opening shot of a journey.
- Inline steps still work. A one-off action sequence in a tiny manifest can stay inline if pulling it out would actually hurt readability.

```yaml
journeys:
  - number: 1
    jtbd: "..."
    headline: "..."
    steps:
      - do: bootstrap_welcome   # one-time setup — dismisses the welcome modal
      - do: at_moonhelm_root
        caption: "Alex starts her day in Moonhelm Marketing…"
      - do: nav_clients
        caption: "She drills into Clients to grab the brief."

recap: { … }


# ╔══════════════════════════════════════════════════════════════════╗
# ║                ⚠  DO NOT EDIT BELOW THIS LINE  ⚠                 ║
# ╚══════════════════════════════════════════════════════════════════╝

dev_server: { command: "npm run dev", port: 8080 }
viewport:   { width: 1440, height: 1000 }
click_indicators: true

step_library:
  bootstrap_welcome:
    url: "http://localhost:8080/"
    actions:
      - { type: click, role: button, name: "Next" }
      - { type: click, role: button, name: "Get started" }
    wait: 800
    screenshot: false

  at_moonhelm_root:
    url: "http://localhost:8080/"
    wait: 2000

  nav_clients:
    actions:
      - { type: click, text: "Clients", scope: "main", exact: true }
    wait: 1200
```

If a `do:` reference doesn't match a recipe name, the runner fails fast with a clear error pointing at the offending step.

## Manifest Example

```yaml
project:
  name: "My Product"
  date: "2026-03-31"

persona:
  name: "Jordan"
  role: "Media Producer"
  avatar: "Becca Fiore"       # optional — name from the bundled set, or a relative/absolute path
  description: "Runs client-facing video projects at a mid-size agency."

# Optional: narrative bridge slide between persona and JTBDs.
thesis:
  eyebrow: "Our bet"
  headline: "Review meets Jordan wherever she works."
  subtitle: "Feedback shouldn't live in six places. We put it where the work already is."

# Recommended shape: items are derived from journeys[*].jtbd (single source
# of truth). Just set the slide's titles here.
jtbds:
  eyebrow: "Key workflows"
  headline: "Jordan's day, in three moves."

dev_server:
  command: "npm run dev"
  port: 3000

viewport:
  width: 1440
  height: 900

# Optional: pink dot on each frame showing where the user is about to
# click. Default true. Set false to suppress dots for decks whose flow
# isn't driven by discrete clicks (marketing tours, data dashboards).
click_indicators: true

# Optional: adds a final "Try the live demo" CTA slide.
# Shorthand: demo_link: "https://my-app.lovable.app"
demo_link:
  url: "https://my-app.lovable.app"
  label: "Try it yourself"
  eyebrow: "Interactive prototype"

journeys:
  # Single-row journey. The `jtbd` feeds the JTBDs list slide and renders as
  # a subtitle under the `headline` on this journey's title card.
  - number: 1
    jtbd: "Get a draft into review without friction."
    headline: "Sharing a draft."
    steps:
      - url: "http://localhost:3000/"
        wait: 2000
        caption: "Jordan opens the project dashboard and sees her latest uploads."
      - actions:
          - type: click
            text: "Share for review"
        wait: 1500
        caption: "She clicks Share and selects reviewers from the team."

  # Multi-row journey: one JTBD, demonstrated across two surfaces.
  - number: 2
    jtbd: "Consolidate feedback into a clear action plan, wherever it lives."
    headline: "Consolidating feedback."
    rows:
      - sub_label: "2a — In the app"
        steps:
          - url: "http://localhost:3000/reviews/42"
            caption: "Jordan opens the review view and sees every comment in context."
      # A sub-row filled by a sidecar script (no screenshots).
      - sub_label: "2b — In her editor"
        extend: editor_integration

# Optional: closing narrative slide rendered just before the demo CTA.
recap:
  eyebrow: "Recap"
  headline: "One review flow. Every surface."
  subtitle: "Whether Jordan starts in the dashboard or her editor, feedback lands in the same place."
```

## Extension slots

Sometimes a deck needs to include a flow that has no screenshots — a CLI walkthrough, an MCP/agent interaction, an API exchange, a Figma embed. The skill can't capture those, but it can reserve a slot for a companion sidecar script to fill.

**Bootstrap a sidecar in a new project:**

```bash
cp <skill-dir>/templates/journey-extend.template.mjs <project>/customer-journey/journey-extend.mjs
cp <skill-dir>/templates/extend.template.yaml        <project>/customer-journey/extend.yaml
```

Then customize the render functions in `journey-extend.mjs` and the data in `extend.yaml` for your project's bespoke flows. The template ships with one example flow showing the minimum shape; add one render function per `- extend: <key>` entry you introduce in `journey.yaml`.

Extension slots come in two flavors:

**Peer-journey slot** — a whole journey rendered by the sidecar (title card + row). Add a sentinel entry in the top-level `journeys` list:

```yaml
journeys:
  - number: 1
    jtbd: "..."
    headline: "..."
    steps: [...]

  # Reserved slot — rendered by a companion sidecar script. The sidecar
  # emits its own title slide for this journey.
  - extend: mcp_journey

  - number: 3                # numbering skips 2 because the sidecar owns it
    jtbd: "..."
    headline: "..."
    steps: [...]
```

**Sub-row slot** — a single row inside a multi-row journey, where the skill-rendered title card already carries the journey-level JTBD. Add the sentinel inside `rows:`:

```yaml
journeys:
  - number: 1
    jtbd: "Draft a contract, wherever I'm working."
    headline: "Drafting a contract."
    rows:
      - sub_label: "1a — In the app"
        steps: [...]
      - sub_label: "1b — In her LLM"
        extend: mcp_journey     # sidecar fills just this row, no title slide
```

At either position the skill emits `<!-- extend:<key> -->` in the HTML. A sidecar script in the project directory (e.g., `journey-extend.mjs`) finds the comment and replaces it with whatever HTML it wants to render. For a peer-journey slot that's typically a `<section class="slide dark">` title + a `<section class="slide light screenshots-slide">` carousel. For a sub-row slot, skip the title slide and just return the carousel — the skill already rendered the shared title card.

**Guidelines for sidecars:**
- Keep sidecar code in the project directory, not in the skill. The skill stays generic.
- Read bespoke content from a small `extend.yaml` next to `journey.yaml` so the sidecar stays data-driven.
- Reuse the skill's existing CSS classes (`slide`, `slide-inner`, `headline`, `eyebrow`, `journey-number`, `ss-row`, `ss-card`, `ss-caption`) so extension slides match the rest of the deck. Add a scoped `<style>` block only for genuinely new UI (chat bubbles, terminal frames).
- To make non-image cards zoomable, put `data-lightbox="html"` on the `.ss-card` element. The skill's lightbox picks those up automatically and includes them in the shared prev/next nav alongside real screenshots. The card's `.ss-caption` is used as the lightbox caption.
- For peer-journey slots, number extension journeys manually — reserve the slot in `journey.yaml` by skipping a number (see example above). For sub-row slots, the parent journey owns the number and the sub-row's `sub_label` carries the label (e.g., `"1b — In her LLM"`).
- `--no-capture` is safe to use with extension slots: the placeholder comment is re-emitted on every build, so the sidecar can re-fill it.

## Tips

- Keep captions in third-person present tense: "Alex opens Dropbox..." not "The user opens..."
- Use `screenshot: false` for setup steps (like storing variables) that shouldn't appear in the output
- Add generous `wait` times for animations (2000-3000ms for modals, field placement, etc.)
- The `store` action is useful for capturing dynamic values (like sign codes) between journeys
- Journeys run sequentially in the same browser context, so localStorage persists between them
- Output file size is typically 5-10 MB for a 16-step journey (JPEG at quality 85, 2x retina)

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
