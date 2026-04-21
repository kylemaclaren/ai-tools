# Customer Journey

Turn a running prototype into an exec-ready customer journey presentation — automatically.

## Who is this for?

PMs and designers who have a working prototype and need to present the user experience to stakeholders — for stakeholder reviews, design partner previews, or team share-outs. Instead of manually screenshotting and assembling slides, you describe the persona and the AI walks through your prototype, captures the screens, and builds the presentation for you.

## What you get

A single `journey.html` file — open it locally, share it on Slack, email it, or publish it to a stable URL with the included [`publish.sh`](#sharing-with-a-stable-url) helper. Each journey includes:

- Dark title slides with persona and JTBD framing — the persona slide can carry an avatar from the bundled 62-face set, so the persona feels like a person (not a template)
- Optional narrative slides — a "thesis" that frames the deck and a "recap" that closes it
- Optional per-section "Part 1 / Part 2 / ..." eyebrows on journey titles
- Horizontal-scroll screenshot rows grouped by journey
- Click any screenshot to zoom in, with prev/next navigation
- Narrative captions in third-person ("Alex opens her project folder...")
- **Click indicators** — a pink dot on each screen showing where the user clicks to reach the next one (can be toggled off)
- Everything driven from a single YAML file you can edit and re-run
- Self-contained: all images are embedded as inline JPEG (typically 5-10 MB total)

### Example

For a contract-signing prototype, the journey doc generates slides like:

> **"Acme E-Sign"** — title slide with project name and date
>
> **"Alex is an Owner at Moonhelm Marketing."** — persona slide with her face in a round frame, her description, and what she's accountable for
>
> **Jobs to be done** — send contracts in under five minutes, let AI handle field placement, track who's signed
>
> **Discovery** — 5 screenshots showing Alex finding signing features inside her project folder
>
> **Sending** — 6 screenshots of AI-powered field placement and one-click sending
>
> **Receiving** — 5 screenshots of a client signing without needing to create an account

All 16 screens are real screenshots captured from the running prototype.

You describe who your user is and what they're trying to do. The AI walks through your prototype in a real browser, captures screenshots at each step, and generates a polished, self-contained HTML walkthrough with persona framing, jobs-to-be-done, and click-to-zoom screenshots.

## Click indicators

Every screenshot shows where the user is about to click next — a small pink dot on the element that will advance to the following frame. This lets viewers follow the causal flow at a glance: "click here → this happened → click here → this happened."

**How it works:**
- The dot appears only on frames where the next step advances via a click in the same view. Frames that end in a navigation, or that are purely informational, get no dot.
- If the click target is below the fold (e.g. in a sidebar or long form), the capture scrolls it into view first so the dot is always visible alongside its target.
- Filled form state renders on the same frame as the dot — when a step fills fields and then clicks submit, the screenshot shows the filled form with the dot on the submit button.

**Turning them off:** Add `click_indicators: false` to the top of your `journey.yaml` to suppress the dots entirely. Useful for decks whose flow isn't driven by discrete clicks (marketing tours, state galleries, data dashboards).

## Install

Open your AI editor (Cursor, Claude Code, or Codex) and paste this prompt:

> Install the **customer-journey** skill from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `skills/customer-journey`). Symlink it into my editor's skills directory and install its dependencies.

The AI will clone the repo, set up the skill, install the Chromium browser used for screenshots, and configure your editor automatically.

## Using it

### First time — create a journey doc

Open your prototype's project in Cursor or Claude Code and say:

> "Create a customer journey for this project"

The AI will:

1. Read your project docs to understand the product
2. Workshop a persona with you — who's the user, what do they care about?
3. Propose 3-5 key workflows and ask for your feedback
4. Start your dev server, walk through each workflow in a real browser, and capture screenshots
5. Generate the HTML presentation

### Re-running after changes

If you've updated the prototype or edited captions in the YAML:

> "Re-run the customer journey"

### Iterating

> "Add a fourth journey showing the admin dashboard"

> "Update the captions in journey 2 to be more specific about the AI features"

> "Change the persona from Alex to Jordan — she's a media producer, not a business owner"

## Sharing with a stable URL

The generated `journey.html` is self-contained, so you can share it as a file attachment. If you'd rather paste a stable URL in Slack that stays the same across every regeneration, the skill ships a `publish.sh` helper that uploads your deck to a public GCS bucket.

### One-time setup

Create a public GCS bucket on a Google Cloud project you own (replace `<your-gcp-project>`):

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

If you use a different bucket name, edit the `BUCKET` and `HOST` constants at the top of `publish.sh` (or set `JOURNEY_BUCKET` / `JOURNEY_HOST` env vars if your `publish.sh` reads them).

### Publish a deck

From the root of your prototype repo (after generating `customer-journey/journey.html`), just ask your AI editor:

> "Re-publish my customer journey"

The skill knows where `publish.sh` lives, picks the prototype repo's directory name as the project slug, and prints the resulting `https://storage.googleapis.com/<your-bucket>/<project-name>/journey.html` URL back to you. Paste it in Slack — re-running keeps the same URL.

### Behavior

- Re-running overwrites the same object. The URL is stable, so paste it in Slack once and you're done.
- Upload sets `Cache-Control: no-cache` so viewers always see the latest push without needing a hard-refresh.
- The bucket is public read. Anyone with the URL can view the deck — safe for internal product review decks, not safe for NDA-sensitive content or real customer data in screenshots.

## Customizing the design with your company's style guide

The default template uses Space Grotesk + Inter with a dark/light theme and yellow accents. You can restyle it to match your company's brand using the Figma MCP to pull design tokens directly from your design system.

### Using Figma MCP to apply your brand

If you have the [Figma MCP](https://github.com/figma/figma-mcp) configured, ask the AI to pull your company's design tokens before generating:

> "Pull our design system from Figma and update the customer journey template to match our brand"

The AI will:

1. Call `search_design_system` to discover your colors, typography, and spacing tokens
2. Call `get_variable_defs` to pull exact color values, font families, and sizes
3. Update the CSS constants in `journey.mjs` to use your brand's:
   - **Colors** — background, text, accent, and eyebrow colors
   - **Typography** — font families, weights, and sizes for headlines, body, and captions
   - **Spacing** — padding, gaps, and border radius values

### Manual customization

If you don't have Figma MCP, you can edit the CSS directly in `journey.mjs`. The styles are in a single `CSS` constant near the bottom of the file. Key variables to change:

| Element | CSS class | What to update |
|---------|-----------|----------------|
| Dark slide background | `.slide.dark` | `background` color |
| Light slide background | `.slide.light` | `background` color |
| Accent color (eyebrow labels) | `.eyebrow` | `color` value |
| Dark accent (JTBD labels) | `.dark-eyebrow`, `.ss-section-label` | `color` value |
| Headline font | `.headline` | `font-family` |
| Body font | `body` | `font-family` |
| Screenshot card radius | `.ss-card img` | `border-radius` |
| Screenshot card shadow | `.ss-card img` | `box-shadow` |

### Example: applying a brand

```
# If you have a Figma file with your design system:
> "Pull the color tokens from [Figma URL] and restyle the customer journey template"

# Or just describe what you want:
> "Update the customer journey template to use our brand colors: 
>  primary blue #0061FF, dark background #1E1E1E, light background #FAFAFA,
>  font family 'Atlas Grotesk', accent color #FF6B35"
```

The Google Fonts link in the HTML template will also need updating if you switch to a different web font. The AI will handle this automatically when restyling.

## How it works

The AI creates a single `journey.yaml` file that defines the persona, their jobs-to-be-done, and step-by-step browser actions (click this button, fill this field, wait for this animation). One script does all the work: it walks through your prototype in a headless browser, captures JPEG screenshots, and assembles them with the narrative into a self-contained HTML presentation with embedded images.

You never need to run the script directly — the AI handles it. But if you want to, the YAML file and the script are simple and readable:

```bash
node journey.mjs path/to/journey.yaml
```

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
