#!/usr/bin/env node
import { chromium } from "playwright";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { resolve, dirname, extname, isAbsolute } from "path";
import { fileURLToPath } from "url";
import { parse } from "yaml";

const SKILL_DIR = dirname(fileURLToPath(import.meta.url));

async function main() {
  const args = process.argv.slice(2);
  const flags = new Set(args.filter((a) => a.startsWith("--")));
  const positional = args.filter((a) => !a.startsWith("--"));
  const manifestPath = positional[0];
  const reuse = flags.has("--no-capture") || flags.has("--reuse");
  const skipAssets = flags.has("--no-assets");

  if (!manifestPath) {
    console.error("Usage: node journey.mjs <path-to-journey.yaml> [--no-capture] [--no-assets]");
    console.error("  --no-capture    Reuse screenshots from existing journey.html (for copy/link edits)");
    console.error("  --no-assets     Skip writing standalone JPEGs to <manifest-dir>/assets/");
    process.exit(1);
  }

  const manifest = expandStepRecipes(parse(readFileSync(resolve(manifestPath), "utf8")));
  const outputDir = dirname(resolve(manifestPath));
  const outputPath = resolve(outputDir, "journey.html");
  const assetsDir = resolve(outputDir, "assets");

  resolvePersonaAvatar(manifest.persona, outputDir);

  const expectedCount = countCaptionedSteps(manifest);
  let screenshots;

  if (reuse) {
    if (!existsSync(outputPath)) {
      console.error(`--no-capture requires an existing ${outputPath} to extract screenshots from.`);
      console.error("Run once without --no-capture to generate it first.");
      process.exit(1);
    }
    screenshots = extractScreenshots(outputPath, manifest);
    if (screenshots.length !== expectedCount) {
      console.error(
        `Screenshot count mismatch: found ${screenshots.length} in existing HTML but manifest expects ${expectedCount}.`
      );
      console.error("The YAML structure changed (steps added/removed). Re-run without --no-capture.");
      process.exit(1);
    }
    console.log(`Reusing ${screenshots.length} screenshots from ${outputPath}`);
  } else {
    screenshots = await capture(manifest);
  }

  const html = buildHTML(manifest, screenshots);
  writeFileSync(outputPath, html, "utf8");
  const sizeMB = (Buffer.byteLength(html, "utf8") / 1024 / 1024).toFixed(1);
  console.log(`Generated: ${outputPath} (${sizeMB} MB)`);

  if (!skipAssets) {
    writeAssets(screenshots, assetsDir);
  }
}

// Writes each screenshot as a standalone JPEG under <assetsDir>/<NN-caption-slug>.jpg
// so individual frames are easy to share without opening the HTML deck. The HTML
// itself stays self-contained (it still embeds the images as data URIs); assets
// are additive.
function writeAssets(screenshots, assetsDir) {
  if (!screenshots.length) return;
  mkdirSync(assetsDir, { recursive: true });
  const width = String(screenshots.length).length;
  let written = 0;
  for (const ss of screenshots) {
    if (!ss.dataUri) continue;
    const m = ss.dataUri.match(/^data:image\/jpeg;base64,(.*)$/);
    if (!m) continue;
    const buffer = Buffer.from(m[1], "base64");
    const prefix = String(ss.index).padStart(width, "0");
    const slug = slugify(ss.caption ?? "", 60);
    const filename = slug ? `${prefix}-${slug}.jpg` : `${prefix}.jpg`;
    writeFileSync(resolve(assetsDir, filename), buffer);
    written++;
  }
  console.log(`Exported ${written} screenshot${written === 1 ? "" : "s"} to ${assetsDir}/`);
}

// Lowercase, ASCII-only slug. Collapses runs of non-alphanumerics to a single
// dash, trims leading/trailing dashes, and caps the length so filenames stay
// readable on all filesystems. We intentionally keep it boring — no unicode
// transliteration, just strip anything that isn't [a-z0-9].
function slugify(text, maxLen = 60) {
  const base = text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (base.length <= maxLen) return base;
  return base.slice(0, maxLen).replace(/-+$/g, "");
}

// Expands `do:` step shortcuts against the manifest's `step_library:`. Each
// step in a journey can be written either fully inline (legacy / one-off) or
// as `{ do: <recipe-name>, caption: "..." }`, where the recipe is defined
// once at the bottom of the manifest under `step_library:`. Frame-level keys
// (caption, wait, screenshot, url, …) override recipe defaults so a single
// recipe can serve multiple frames with slightly different pacing or copy.
//
// Mutates `manifest` in place and returns it. If `step_library:` is absent,
// this is a no-op — fully inline manifests keep working.
// Resolves `persona.avatar` to an inlined JPEG data URI on
// `persona._avatarDataUri`, so personaSlide() can render it without any
// async work. The avatar reference is one of:
//   - A full name ("Sara Letzinger") — looked up in the skill's bundled
//     avatars/index.json (see avatars/.download.mjs for provenance).
//   - A relative path (./alex.jpg, avatars/custom/alex.png) — resolved
//     against the manifest's directory, so project authors can drop
//     project-specific avatars next to their journey.yaml.
//   - An absolute path — used as-is.
// Unknown references log a warning and leave the slide avatar-less rather
// than failing the whole build.
function resolvePersonaAvatar(persona, manifestDir) {
  if (!persona || !persona.avatar) return;
  const ref = String(persona.avatar).trim();
  const candidate = avatarFilePath(ref, manifestDir);
  if (!candidate) {
    console.warn(`[persona.avatar] Unknown avatar reference "${ref}". See ${SKILL_DIR}/avatars/index.html for the bundled set.`);
    return;
  }
  if (!existsSync(candidate)) {
    console.warn(`[persona.avatar] File not found: ${candidate}`);
    return;
  }
  const mime = extname(candidate).toLowerCase() === ".png" ? "image/png" : "image/jpeg";
  const buffer = readFileSync(candidate);
  persona._avatarDataUri = `data:${mime};base64,${buffer.toString("base64")}`;
}

function avatarFilePath(ref, manifestDir) {
  // 1. Name lookup in the bundled index (case-insensitive).
  const indexPath = resolve(SKILL_DIR, "avatars", "index.json");
  if (existsSync(indexPath)) {
    try {
      const index = JSON.parse(readFileSync(indexPath, "utf8"));
      const needle = ref.toLowerCase();
      const hit = (index.avatars || []).find((a) => a.name.toLowerCase() === needle);
      if (hit) return resolve(SKILL_DIR, "avatars", hit.file);
    } catch (err) {
      console.warn(`[persona.avatar] Failed to read ${indexPath}: ${err.message}`);
    }
  }

  // 2. Path reference (relative or absolute) — only follow if it looks
  //    like a path (contains a separator or a file extension). Prevents
  //    bare names that happen not to match the index from being silently
  //    treated as filenames.
  const looksLikePath = ref.includes("/") || ref.includes("\\") || extname(ref);
  if (!looksLikePath) return null;
  return isAbsolute(ref) ? ref : resolve(manifestDir, ref);
}

function expandStepRecipes(manifest) {
  const library = manifest.step_library ?? {};
  const expand = (step) => {
    if (!step || typeof step !== "object" || !step.do) return step;
    const recipe = library[step.do];
    if (!recipe) {
      throw new Error(
        `Unknown step recipe "${step.do}". Define it under step_library: at the bottom of the manifest, or remove the do: reference.`
      );
    }
    const { do: _, ...overrides } = step;
    return { ...recipe, ...overrides };
  };
  for (const journey of manifest.journeys ?? []) {
    if (journey.extend) continue;
    if (Array.isArray(journey.steps)) journey.steps = journey.steps.map(expand);
    if (Array.isArray(journey.rows)) {
      for (const row of journey.rows) {
        if (Array.isArray(row.steps)) row.steps = row.steps.map(expand);
      }
    }
  }
  return manifest;
}

function countCaptionedSteps(manifest) {
  let n = 0;
  for (const journey of manifest.journeys ?? []) {
    if (journey.extend) continue;
    for (const row of iterCaptureRows(journey)) {
      for (const step of row.steps ?? []) {
        if (step.screenshot === false) continue;
        if (!step.caption) continue;
        n++;
      }
    }
  }
  return n;
}

// Normalizes a journey into an iterable of capture-producing rows. A journey
// either has `rows: [{ sub_label, steps | extend }, ...]` (multi-row) or a
// top-level `steps: [...]` (single-row). Extend rows produce no screenshots
// and are filtered out here.
function iterCaptureRows(journey) {
  if (Array.isArray(journey.rows)) {
    return journey.rows.filter((r) => !r.extend && r.steps);
  }
  if (journey.steps) return [{ steps: journey.steps }];
  return [];
}

function extractScreenshots(htmlPath, manifest) {
  const html = readFileSync(htmlPath, "utf8");
  // Match only screenshot <img> tags inside ss-card containers so we don't
  // accidentally pull in unrelated images or the lightbox target.
  const re = /<div class="ss-card">\s*<img src="(data:image\/jpeg;base64,[^"]+)"/g;
  const uris = [];
  let m;
  while ((m = re.exec(html)) !== null) {
    uris.push(m[1]);
  }

  const screenshots = [];
  let idx = 0;
  for (const journey of manifest.journeys ?? []) {
    if (journey.extend) continue;
    for (const row of iterCaptureRows(journey)) {
      for (const step of row.steps ?? []) {
        if (step.screenshot === false) continue;
        if (!step.caption) continue;
        idx++;
        screenshots.push({
          index: idx,
          caption: step.caption,
          dataUri: uris[idx - 1],
        });
      }
    }
  }
  return screenshots;
}

async function capture(manifest) {
  const vp = manifest.viewport ?? { width: 1440, height: 900 };
  const vars = {};
  const screenshots = [];
  let globalIndex = 0;

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: 2,
    colorScheme: "light",
  });
  const page = await context.newPage();

  // Project-wide toggle. Default on. Set `click_indicators: false` at the
  // top of journey.yaml to suppress pink dots entirely (useful for decks
  // where the visual flow isn't driven by discrete user clicks).
  const clickIndicatorsEnabled = manifest.click_indicators !== false;

  // Flatten into a linear sequence of captioned steps so we can look ahead
  // to the NEXT step when deciding where to paint the click indicator.
  // The dot shows where the user is ABOUT to click to get to the next
  // frame — so it's painted on screenshot N, pointing at the element that
  // step N+1 will click. The final screenshot in any run has no dot.
  const sequence = [];
  for (const journey of manifest.journeys) {
    if (journey.extend) continue;
    for (const row of iterCaptureRows(journey)) {
      for (const step of row.steps) {
        sequence.push({ journey, row, step });
      }
    }
  }

  let lastJourneyHeader = null;
  let lastRowHeader = null;

  for (let i = 0; i < sequence.length; i++) {
    const { journey, row, step } = sequence[i];

    if (lastJourneyHeader !== journey) {
      const label = journey.headline ?? journey.title ?? `Journey ${journey.number}`;
      console.log(`\n── Journey ${journey.number}: ${label}`);
      lastJourneyHeader = journey;
      lastRowHeader = null;
    }
    if (lastRowHeader !== row && row.sub_label) {
      console.log(`   ── Row: ${row.sub_label}`);
      lastRowHeader = row;
    }

    if (step.url) {
      const url = interpolate(step.url, vars);
      console.log(`   [nav] ${url}`);
      await page.goto(url, { waitUntil: "networkidle" });
    }

    if (step.actions) {
      for (const action of step.actions) {
        await runAction(page, action, vars);
      }
    }

    if (step.waitFor) {
      console.log(`   [waitFor] ${step.waitFor}`);
      await page.waitForSelector(step.waitFor, { timeout: 10000 });
    }

    await page.waitForTimeout(step.wait ?? 800);

    if (step.screenshot === false) {
      console.log(`   [skip screenshot] ${step.caption ?? "(utility step)"}`);
      continue;
    }

    if (!step.caption) continue;

    // Look ahead to the next captioned step: if its first action is a
    // click that resolves in the current DOM (no intervening nav), paint
    // the dot on that element before screenshotting. This makes the dot
    // read as "the user is about to click here" against the current state.
    const nextClick = clickIndicatorsEnabled ? findNextClickTarget(sequence, i) : null;
    const indicatorShown = await showClickIndicatorOnElement(page, nextClick);

    globalIndex++;
    const buffer = await page.screenshot({
      type: "jpeg",
      quality: 85,
      fullPage: false,
    });
    const dataUri = `data:image/jpeg;base64,${buffer.toString("base64")}`;
    screenshots.push({ index: globalIndex, caption: step.caption, dataUri });
    const sizeKB = Math.round(buffer.length / 1024);
    console.log(`   ✓ screenshot ${globalIndex} (${sizeKB} KB)`);

    if (indicatorShown) await hideClickIndicator(page);
  }

  await browser.close();
  console.log(`\nCaptured ${globalIndex} screenshots`);
  return screenshots;
}

// Finds the click that step i is DIRECTLY followed by (the click whose
// result lands the viewer in the next new layout), so the current frame
// can paint a dot on it. Returns the action object or null.
//
// The dot lands on the LAST frame before a click — so if dwell frames
// sit between the current step and the click, the current step gets no
// dot (those dwell frames are the same underlying layout, just multiple
// captions). Only the frame immediately preceding the click wins.
//
// Rules:
//   - If the NEXT captioned step itself has a dwell (no click), return
//     null here — that frame, not this one, will own the dot.
//   - If the next captioned step starts with a `url:` nav, return null
//     (the clicked element lives on a different page).
//   - If the next captioned step's first meaningful action is a click,
//     return it.
function findNextClickTarget(sequence, i) {
  for (let j = i + 1; j < sequence.length; j++) {
    const next = sequence[j];
    const isUtility = next.step.screenshot === false || !next.step.caption;
    if (isUtility) continue;
    // Found the next captioned frame. The dot lives on whichever frame
    // IMMEDIATELY precedes the click, so if this next frame is itself
    // a dwell/informational frame (no click), we surrender the dot to it.
    if (next.step.url) return null;
    if (!next.step.actions || next.step.actions.length === 0) return null;
    const firstMeaningful = next.step.actions.find((a) => a.type !== "store" && a.type !== "eval");
    if (!firstMeaningful || firstMeaningful.type !== "click") return null;
    return firstMeaningful;
  }
  return null;
}

// Resolves the click target in the current DOM, scrolls it into the
// viewport if needed (so the dot is always visible on state-changing
// frames), and paints the pink dot at the center (or at action.position).
// Returns true if a dot was drawn so the caller knows whether to clean up.
async function showClickIndicatorOnElement(page, action) {
  if (!action) return false;
  let coords = null;
  try {
    const loc = resolveLocator(page, action);
    // Scroll first — if the target is in a sidebar below the fold,
    // the reader needs to see it under the dot. scrollIntoViewIfNeeded
    // walks up ancestor scroll containers, so it works for nested
    // sidebar scrolls (not just the main window).
    await loc.scrollIntoViewIfNeeded({ timeout: 3000 });
    const box = await loc.boundingBox({ timeout: 3000 });
    if (box) {
      if (action.position) {
        coords = { x: box.x + action.position.x, y: box.y + action.position.y };
      } else {
        coords = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
      }
    }
  } catch {
    // Target not yet in DOM / not resolvable — skip the dot for this frame
    // rather than blocking the capture.
  }
  if (!coords) return false;

  // Clamp to the viewport rather than suppressing — by this point we've
  // already scrolled, so if the element is still logically off-viewport
  // (e.g. an overflow container couldn't be scrolled far enough) we'd
  // rather show the dot at the nearest edge than nothing. In practice
  // scrollIntoViewIfNeeded handles the common case.
  const vp = page.viewportSize();
  if (vp) {
    coords.x = Math.max(0, Math.min(vp.width, coords.x));
    coords.y = Math.max(0, Math.min(vp.height, coords.y));
  }

  await page.evaluate(({ x, y }) => {
    const id = "__cj-click-indicator";
    document.getElementById(id)?.remove();
    const el = document.createElement("div");
    el.id = id;
    el.style.cssText = [
      "position:fixed",
      `left:${x}px`,
      `top:${y}px`,
      "width:32px",
      "height:32px",
      "margin-left:-16px",
      "margin-top:-16px",
      "border-radius:50%",
      "background:rgba(236,72,153,0.55)",
      "pointer-events:none",
      "z-index:2147483647",
    ].join(";");
    document.body.appendChild(el);
  }, coords);
  return true;
}

async function hideClickIndicator(page) {
  await page.evaluate(() => {
    document.getElementById("__cj-click-indicator")?.remove();
  });
}

// ── Browser automation ──────────────────────────────────────────────

async function runAction(page, action, vars) {
  switch (action.type) {
    case "click": {
      const loc = resolveLocator(page, action);
      const extras = [];
      if (action.button && action.button !== "left") extras.push(`button=${action.button}`);
      if (action.clickCount && action.clickCount > 1) extras.push(`x${action.clickCount}`);
      if (action.modifiers?.length) extras.push(`+${action.modifiers.join("+")}`);
      console.log(`   [click${extras.length ? " " + extras.join(" ") : ""}] ${describeLocator(action)}`);
      const opts = { timeout: 8000 };
      if (action.force) opts.force = true;
      if (action.position) opts.position = action.position;
      if (action.button) opts.button = action.button;
      if (action.clickCount) opts.clickCount = action.clickCount;
      if (action.modifiers) opts.modifiers = action.modifiers;

      await loc.click(opts);
      break;
    }
    case "fill": {
      const value = interpolate(action.text, vars);
      if (action.placeholder) {
        console.log(`   [fill] placeholder="${action.placeholder}"`);
        await page.getByPlaceholder(action.placeholder).fill(value);
      } else if (action.selector) {
        await page.locator(action.selector).fill(value);
      }
      break;
    }
    case "hover": {
      const loc = resolveLocator(page, action);
      await loc.hover();
      break;
    }
    case "key": {
      console.log(`   [key] ${action.key}`);
      await page.keyboard.press(action.key);
      break;
    }
    case "scroll": {
      if (action.selector) {
        await page.locator(action.selector).scrollIntoViewIfNeeded();
      }
      break;
    }
    case "store": {
      const result = await page.evaluate(action.eval);
      vars[action.name] = result;
      console.log(`   [store] ${action.name} = ${result}`);
      break;
    }
    case "eval": {
      console.log(`   [eval] running script`);
      await page.evaluate(action.script);
      break;
    }
    case "wait": {
      await page.waitForTimeout(action.ms ?? 1000);
      break;
    }
  }

  if (action.wait) {
    await page.waitForTimeout(action.wait);
  }
}

function resolveLocator(page, action) {
  let base = page;
  if (action.scope) base = page.locator(action.scope);

  if (action.role) {
    const opts = {};
    if (action.name) opts.name = new RegExp(action.name);
    return base.getByRole(action.role, opts);
  }
  if (action.text) {
    return base.getByText(action.text, { exact: action.exact ?? false });
  }
  if (action.selector) {
    return base.locator(action.selector);
  }
  throw new Error(`Cannot resolve locator: ${JSON.stringify(action)}`);
}

function describeLocator(action) {
  if (action.role) return `role=${action.role} name="${action.name ?? ""}"`;
  if (action.text) return `text="${action.text}"`;
  if (action.selector) return action.selector;
  return "?";
}

// ── HTML generation ─────────────────────────────────────────────────

function buildHTML(manifest, screenshots) {
  const { project, persona, jtbds, journeys, thesis, recap } = manifest;

  let ssIndex = 0;
  const sections = [
    titleSlide(project),
    personaSlide(persona),
    narrativeSlide(thesis),
    jtbdSlide(jtbds, journeys),
    ...journeys.flatMap((j) => {
      if (j.extend) return [extendPlaceholder(j.extend)];
      const rendered = journeyRowsHTML(j, screenshots, ssIndex);
      ssIndex = rendered.nextIndex;
      return [journeyTitleSlide(j), ...rendered.rows];
    }),
    narrativeSlide(recap),
    demoSlide(manifest.demo_link),
  ].filter(Boolean).join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(project.name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>${CSS}</style>
</head>
<body>
${sections}
${LIGHTBOX_HTML}
${LIGHTBOX_JS}
</body>
</html>`;
}

function titleSlide(project) {
  return `<section class="slide dark">
  <div class="slide-inner">
    ${project.date ? `<p class="eyebrow">${esc(project.date)}</p>` : ""}
    <h1 class="headline xl">${esc(project.name)}</h1>
    <p class="subtitle">UX Walkthrough + Demo</p>
  </div>
</section>`;
}

function personaSlide(persona) {
  const avatar = persona._avatarDataUri
    ? `<div class="persona-avatar" aria-hidden="true"><img src="${persona._avatarDataUri}" alt=""></div>\n    `
    : "";
  return `<section class="slide dark">
  <div class="slide-inner">
    ${avatar}<p class="eyebrow">Primary Persona</p>
    <h2 class="headline">${esc(persona.name)} is ${/^[aeiou]/i.test(persona.role) ? "an" : "a"} ${esc(persona.role)}.</h2>
    <p class="body-large">${esc(persona.description)}</p>
  </div>
</section>`;
}

// Accepts three shapes:
//   1) a plain array of strings — renders with default titles.
//   2) an object { eyebrow, headline, items: [...] } — explicit items.
//   3) an object { eyebrow, headline } (no items) — items derived from
//      journeys[*].jtbd in declaration order. This keeps the JTBDs list and
//      the journeys themselves in a single source of truth in the manifest.
function jtbdSlide(jtbds, journeys = []) {
  if (!jtbds) return "";
  const isObject = !Array.isArray(jtbds) && typeof jtbds === "object";
  let items = isObject ? jtbds.items : jtbds;
  if (!items?.length && isObject) {
    items = deriveJtbdsFromJourneys(journeys);
  }
  if (!items?.length) return "";
  const eyebrow = isObject && jtbds.eyebrow ? jtbds.eyebrow : "Jobs to be done";
  const headline = isObject && jtbds.headline ? jtbds.headline : "Recurring workflows...";
  const rendered = items
    .map(
      (j, i) =>
        `<div class="jtbd-item"><span class="jtbd-num">${String(i + 1).padStart(2, "0")}</span><span class="jtbd-text">${esc(j)}</span></div>`
    )
    .join("\n      ");
  return `<section class="slide light">
  <div class="slide-inner">
    <p class="eyebrow dark-eyebrow">${esc(eyebrow)}</p>
    <h2 class="headline dark-text">${esc(headline)}</h2>
    <div class="jtbd-list">
      ${rendered}
    </div>
  </div>
</section>`;
}

function deriveJtbdsFromJourneys(journeys) {
  const items = [];
  for (const j of journeys ?? []) {
    if (j.jtbd) items.push(j.jtbd);
  }
  return items;
}

function journeyTitleSlide(journey) {
  const eyebrow = journey.part_label
    ? `<p class="eyebrow">${esc(journey.part_label)}</p>\n    `
    : "";
  const headline = journey.headline ?? journey.title ?? "";
  const subtitle = journey.jtbd
    ? `\n    <p class="body-large journey-jtbd">${esc(journey.jtbd)}</p>`
    : "";
  return `<section class="slide dark">
  <div class="slide-inner">
    ${eyebrow}<div class="journey-number">${journey.number}</div>
    <h2 class="headline">${esc(headline)}</h2>${subtitle}
  </div>
</section>`;
}

function narrativeSlide(slide) {
  if (!slide) return "";
  const parts = [];
  if (slide.eyebrow) parts.push(`<p class="eyebrow">${esc(slide.eyebrow)}</p>`);
  if (slide.headline) parts.push(`<h2 class="headline">${esc(slide.headline)}</h2>`);
  if (slide.subtitle) parts.push(`<p class="body-large">${esc(slide.subtitle)}</p>`);
  if (!parts.length) return "";
  return `<section class="slide dark">
  <div class="slide-inner">
    ${parts.join("\n    ")}
  </div>
</section>`;
}

// Emits an HTML comment as a stable anchor for a companion sidecar script.
// Use a journey entry like `- extend: mcp_journey` in the manifest to reserve
// a slot at that position in the deck; a sidecar can then find the comment
// and replace it with bespoke HTML (e.g., a faux-chat carousel for a CLI or
// MCP flow that has no screenshots).
function extendPlaceholder(key) {
  const safe = String(key).replace(/[^a-z0-9_\-]/gi, "");
  return `<!-- extend:${safe} -->`;
}

// Renders the row-level slides for a single journey. Handles three cases:
//   (a) `journey.rows` present → emit one <section> per row. Each row is
//       either a Playwright-captured step list OR an extend sub-row that
//       emits a placeholder comment for a sidecar to fill.
//   (b) `journey.steps` present → one unlabeled row (back-compat default).
//   (c) neither → nothing.
// Rows with a `sub_label` render it as the section eyebrow; otherwise the
// journey's headline/title is used.
function journeyRowsHTML(journey, screenshots, startIndex) {
  const rows = [];
  let idx = startIndex;
  const journeyLabel = journey.headline ?? journey.title ?? "";

  if (Array.isArray(journey.rows)) {
    for (const row of journey.rows) {
      if (row.extend) {
        rows.push(extendPlaceholder(row.extend));
        continue;
      }
      const rowHTML = renderScreenshotRow(row.steps ?? [], screenshots, idx, row.sub_label ?? journeyLabel);
      idx = rowHTML.nextIndex;
      if (rowHTML.html) rows.push(rowHTML.html);
    }
  } else if (journey.steps) {
    const rowHTML = renderScreenshotRow(journey.steps, screenshots, idx, journeyLabel);
    idx = rowHTML.nextIndex;
    if (rowHTML.html) rows.push(rowHTML.html);
  }

  return { rows, nextIndex: idx };
}

function renderScreenshotRow(steps, screenshots, startIndex, sectionLabel) {
  const cards = [];
  let idx = startIndex;

  for (const step of steps) {
    if (step.screenshot === false) continue;
    if (!step.caption) continue;

    const ss = screenshots[idx];
    if (!ss) { idx++; continue; }

    cards.push(`<div class="ss-card">
        <img src="${ss.dataUri}" alt="${esc(step.caption)}">
        <p class="ss-caption">${esc(step.caption)}</p>
      </div>`);
    idx++;
  }

  if (!cards.length) return { html: "", nextIndex: idx };

  return {
    html: `<section class="slide light screenshots-slide">
  <p class="ss-section-label">${esc(sectionLabel)}</p>
  <div class="ss-row">
      ${cards.join("\n      ")}
  </div>
</section>`,
    nextIndex: idx,
  };
}

function demoSlide(demoLink) {
  if (!demoLink) return "";
  const url = typeof demoLink === "string" ? demoLink : demoLink.url;
  if (!url) return "";
  const label = (typeof demoLink === "object" && demoLink.label) || "Try the live demo";
  const eyebrow = (typeof demoLink === "object" && demoLink.eyebrow) || "Interactive prototype";
  const host = safeHost(url);
  return `<section class="slide dark">
  <div class="slide-inner demo-cta">
    <p class="eyebrow">${esc(eyebrow)}</p>
    <h2 class="headline">${esc(label)}</h2>
    <a class="demo-button" href="${esc(url)}" target="_blank" rel="noopener noreferrer">
      <span class="demo-button-label">${esc(host)}</span>
      <span class="demo-button-arrow" aria-hidden="true">&rarr;</span>
    </a>
    <p class="demo-hint">Opens in a new tab. Poke around at your own pace.</p>
  </div>
</section>`;
}

function safeHost(url) {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// ── Utilities ───────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function interpolate(str, vars) {
  if (!str) return str;
  return str.replace(/\$\{(\w+)\}/g, (_, key) => vars[key] ?? `\${${key}}`);
}

// ── Styles + Lightbox ───────────────────────────────────────────────

const CSS = `
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}

html{
  scroll-snap-type:y mandatory;
  scroll-behavior:smooth;
  -webkit-font-smoothing:antialiased;
}

body{
  font-family:'Inter',system-ui,sans-serif;
  background:#0a0a0a;
  color:#fff;
  overflow-x:hidden;
}

.slide{
  min-height:100vh;
  scroll-snap-align:start;
  display:flex;
  align-items:center;
  position:relative;
}

.slide-inner{
  width:100%;
  max-width:1200px;
  margin:0 auto;
  padding:80px;
}

.slide.dark{background:#0a0a0a;color:#fff}
.slide.light{background:#f7f5f2;color:#1a1918}

.eyebrow{
  font-family:'Space Grotesk',sans-serif;
  font-size:15px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:0.08em;
  color:#fbbf24;
  margin-bottom:32px;
}

.dark-eyebrow{color:#92400e}

.persona-avatar{
  width:100px;
  height:100px;
  border-radius:50%;
  overflow:hidden;
  margin-bottom:32px;
  box-shadow:0 0 0 3px rgba(255,255,255,0.08),0 14px 28px rgba(0,0,0,0.35);
  background:#1a1918;
}
.persona-avatar img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}

.headline{
  font-family:'Space Grotesk',sans-serif;
  font-size:clamp(38px,4.5vw,60px);
  font-weight:500;
  line-height:1.35;
  max-width:1000px;
}

.headline.xl{
  font-size:clamp(56px,7vw,88px);
  font-weight:700;
  line-height:1.15;
}

.dark-text{color:#1a1918}

.subtitle{
  font-family:'Space Grotesk',sans-serif;
  font-size:clamp(20px,2.2vw,28px);
  font-weight:400;
  color:rgba(255,255,255,0.45);
  margin-top:24px;
}

.body-large{
  font-size:clamp(20px,2vw,26px);
  line-height:1.6;
  color:rgba(255,255,255,0.65);
  margin-top:32px;
  max-width:700px;
}

.headline-list{
  list-style:none;
  display:flex;
  flex-direction:column;
  gap:12px;
  margin-top:24px;
}

.headline-list li{
  font-family:'Space Grotesk',sans-serif;
  font-size:clamp(22px,2.5vw,32px);
  font-weight:500;
  line-height:1.5;
  padding-left:24px;
  position:relative;
  color:rgba(255,255,255,0.75);
}

.headline-list li::before{
  content:'';
  position:absolute;
  left:0;
  top:0.55em;
  width:8px;
  height:8px;
  border-radius:50%;
  background:#fbbf24;
}

.jtbd-list{margin-top:48px}

.jtbd-item{
  display:flex;
  align-items:center;
  gap:32px;
  padding:28px 0;
  border-top:1px solid rgba(0,0,0,0.1);
}

.jtbd-num{
  font-family:'Space Grotesk',sans-serif;
  font-size:28px;
  font-weight:400;
  color:rgba(0,0,0,0.25);
  flex-shrink:0;
  width:48px;
}

.jtbd-text{
  font-family:'Space Grotesk',sans-serif;
  font-size:clamp(20px,2.5vw,28px);
  font-weight:500;
  line-height:1.4;
  color:#1a1918;
}

.journey-number{
  font-family:'Space Grotesk',sans-serif;
  font-size:clamp(80px,12vw,160px);
  font-weight:700;
  color:rgba(255,255,255,0.06);
  line-height:1;
  margin-bottom:-20px;
}

.journey-jtbd{
  margin-top:24px;
  max-width:900px;
  color:rgba(255,255,255,0.55);
}

.screenshots-slide{
  min-height:100vh;
  padding:64px 0;
  scroll-snap-align:start;
}

.ss-section-label{
  font-family:'Space Grotesk',sans-serif;
  font-size:15px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:0.08em;
  color:#92400e;
  padding:0 80px;
  margin-bottom:24px;
}

.ss-row{
  display:flex;
  gap:32px;
  overflow-x:auto;
  padding:0 80px 24px;
  scroll-snap-type:x proximity;
  scroll-padding-inline:80px;
  scrollbar-width:thin;
  scrollbar-color:rgba(0,0,0,0.15) transparent;
}

.ss-row::-webkit-scrollbar{height:6px}
.ss-row::-webkit-scrollbar-track{background:transparent}
.ss-row::-webkit-scrollbar-thumb{background:rgba(0,0,0,0.15);border-radius:3px}

.ss-card{
  flex-shrink:0;
  width:min(580px,80vw);
  scroll-snap-align:start;
}

.ss-card img{
  width:100%;
  border-radius:12px;
  box-shadow:0 4px 24px rgba(0,0,0,0.08);
  margin-bottom:16px;
  cursor:pointer;
  transition:transform 0.2s ease, box-shadow 0.2s ease;
}

.ss-card img:hover{
  transform:scale(1.02);
  box-shadow:0 8px 40px rgba(0,0,0,0.15);
}

/* Generic hover for non-image cards that opt into the lightbox via
   data-lightbox="html". Sidecars can style the card body however they want;
   this just signals interactivity. */
.ss-card[data-lightbox="html"]>:first-child{
  cursor:pointer;
  transition:transform 0.2s ease, box-shadow 0.2s ease;
}
.ss-card[data-lightbox="html"]:hover>:first-child{
  transform:scale(1.01);
}

.ss-caption{
  font-size:16px;
  line-height:1.5;
  color:rgba(0,0,0,0.55);
  max-width:540px;
}

.lightbox-overlay{
  display:none;
  position:fixed;
  inset:0;
  z-index:9999;
  background:rgba(0,0,0,0.92);
  align-items:center;
  justify-content:center;
  cursor:zoom-out;
  padding:40px;
}

.lightbox-overlay.active{
  display:flex;
}

.lightbox-overlay img{
  image-rendering:auto;
  max-width:min(95vw,calc(100vw - 160px));
  max-height:85vh;
  border-radius:8px;
  box-shadow:0 8px 60px rgba(0,0,0,0.5);
  object-fit:contain;
  cursor:default;
}

/* Holds arbitrary HTML content when a non-image card opens the lightbox.
   Sidecars can target descendants with their own scoped styles. */
.lightbox-html{
  max-width:min(95vw,calc(100vw - 160px));
  max-height:85vh;
  overflow:auto;
  cursor:default;
  display:flex;
  align-items:center;
  justify-content:center;
}
.lightbox-html:empty{display:none}

.lightbox-caption{
  position:fixed;
  bottom:24px;
  left:50%;
  transform:translateX(-50%);
  font-family:'Inter',sans-serif;
  font-size:14px;
  color:rgba(255,255,255,0.6);
  max-width:600px;
  text-align:center;
  line-height:1.5;
}

.lightbox-close{
  position:fixed;
  top:24px;
  right:32px;
  font-size:32px;
  color:rgba(255,255,255,0.6);
  cursor:pointer;
  font-family:system-ui;
  line-height:1;
  z-index:10000;
  transition:color 0.2s;
}

.lightbox-close:hover{color:#fff}

.lightbox-nav{
  position:fixed;
  top:50%;
  transform:translateY(-50%);
  font-size:36px;
  color:rgba(255,255,255,0.5);
  cursor:pointer;
  font-family:system-ui;
  z-index:10000;
  width:56px;
  height:56px;
  display:flex;
  align-items:center;
  justify-content:center;
  border-radius:50%;
  transition:color 0.2s,background 0.2s;
  user-select:none;
  -webkit-user-select:none;
}

.lightbox-nav:hover{
  color:#fff;
  background:rgba(255,255,255,0.1);
}

.lightbox-nav.prev{left:24px}
.lightbox-nav.next{right:24px}

.lightbox-counter{
  position:fixed;
  top:28px;
  left:50%;
  transform:translateX(-50%);
  font-family:'Inter',sans-serif;
  font-size:13px;
  color:rgba(255,255,255,0.35);
  z-index:10000;
}

.demo-cta{
  display:flex;
  flex-direction:column;
  align-items:flex-start;
  gap:0;
}

.demo-button{
  display:inline-flex;
  align-items:center;
  gap:20px;
  margin-top:40px;
  padding:20px 28px;
  background:#fbbf24;
  color:#0a0a0a;
  border-radius:12px;
  font-family:'Space Grotesk',sans-serif;
  font-size:clamp(20px,2.2vw,26px);
  font-weight:600;
  text-decoration:none;
  transition:transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
  box-shadow:0 4px 24px rgba(251,191,36,0.25);
}

.demo-button:hover{
  transform:translateY(-2px);
  background:#fcd34d;
  box-shadow:0 8px 40px rgba(251,191,36,0.35);
}

.demo-button-arrow{
  font-size:1.1em;
  line-height:1;
  transition:transform 0.2s ease;
}

.demo-button:hover .demo-button-arrow{
  transform:translateX(4px);
}

.demo-hint{
  font-family:'Inter',sans-serif;
  font-size:15px;
  color:rgba(255,255,255,0.45);
  margin-top:20px;
}

@media(max-width:768px){
  .slide-inner{padding:48px 32px}
  .ss-row{padding:0 32px 24px;gap:16px;scroll-padding-inline:32px}
  .ss-section-label{padding:0 32px}
  .ss-card{width:min(400px,85vw)}
}
`;

const LIGHTBOX_HTML = `
<div class="lightbox-overlay" id="lightbox" onclick="closeLightbox()">
  <span class="lightbox-close" onclick="closeLightbox()">&times;</span>
  <span class="lightbox-nav prev" onclick="event.stopPropagation();navLightbox(-1)">&#8249;</span>
  <span class="lightbox-nav next" onclick="event.stopPropagation();navLightbox(1)">&#8250;</span>
  <img id="lightbox-img" src="" alt="" onclick="event.stopPropagation()">
  <div class="lightbox-html" id="lightbox-html" onclick="event.stopPropagation()"></div>
  <p class="lightbox-counter" id="lightbox-counter"></p>
  <p class="lightbox-caption" id="lightbox-caption"></p>
</div>`;

const LIGHTBOX_JS = `
<script>
var lbItems = [];
var lbIndex = 0;
(function() {
  // Build a unified list of lightbox-participating cards in DOM order.
  // An <img> inside .ss-card produces an image item; a .ss-card with
  // data-lightbox="html" produces an HTML item (rendered into a scrollable
  // panel in the overlay). Any other .ss-card is skipped.
  var cards = document.querySelectorAll('.ss-card');
  for (var i = 0; i < cards.length; i++) {
    var card = cards[i];
    var captionEl = card.querySelector('.ss-caption');
    var caption = captionEl ? captionEl.textContent.trim() : '';
    var img = card.querySelector('img');
    if (img) {
      var itemIndex = lbItems.length;
      lbItems.push({ type: 'img', src: img.src, alt: img.alt || caption });
      img.style.cursor = 'pointer';
      (function(idx) {
        img.addEventListener('click', function(e) {
          e.stopPropagation();
          openLightboxAt(idx);
        });
      })(itemIndex);
    } else if (card.getAttribute('data-lightbox') === 'html') {
      // Capture the card's content minus the caption, which the lightbox
      // renders separately in the footer.
      var clone = card.cloneNode(true);
      var clonedCaption = clone.querySelector('.ss-caption');
      if (clonedCaption) clonedCaption.remove();
      var itemIndex = lbItems.length;
      lbItems.push({ type: 'html', html: clone.innerHTML, caption: caption });
      (function(idx) {
        card.addEventListener('click', function(e) {
          openLightboxAt(idx);
        });
      })(itemIndex);
    }
  }
})();
function openLightboxAt(idx) {
  lbIndex = idx;
  showLightboxItem();
  document.getElementById('lightbox').classList.add('active');
}
// Kept for backward compatibility with any inline onclick="openLightbox(...)".
function openLightbox(src) {
  for (var i = 0; i < lbItems.length; i++) {
    if (lbItems[i].type === 'img' && lbItems[i].src === src) {
      openLightboxAt(i);
      return;
    }
  }
}
function showLightboxItem() {
  var item = lbItems[lbIndex];
  if (!item) return;
  var imgEl = document.getElementById('lightbox-img');
  var htmlEl = document.getElementById('lightbox-html');
  if (item.type === 'img') {
    imgEl.src = item.src;
    imgEl.style.display = '';
    htmlEl.style.display = 'none';
    htmlEl.innerHTML = '';
  } else {
    imgEl.src = '';
    imgEl.style.display = 'none';
    htmlEl.innerHTML = item.html;
    htmlEl.style.display = '';
  }
  var caption = item.type === 'img' ? (item.alt || '') : (item.caption || '');
  document.getElementById('lightbox-caption').textContent = caption;
  document.getElementById('lightbox-counter').textContent = (lbIndex + 1) + ' / ' + lbItems.length;
  document.querySelector('.lightbox-nav.prev').style.display = lbIndex === 0 ? 'none' : '';
  document.querySelector('.lightbox-nav.next').style.display = lbIndex === lbItems.length - 1 ? 'none' : '';
}
function navLightbox(dir) {
  var next = lbIndex + dir;
  if (next < 0 || next >= lbItems.length) return;
  lbIndex = next;
  showLightboxItem();
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('active');
}
document.addEventListener('keydown', function(e) {
  var lb = document.getElementById('lightbox');
  if (!lb.classList.contains('active')) return;
  if (e.key === 'Escape') closeLightbox();
  if (e.key === 'ArrowLeft') navLightbox(-1);
  if (e.key === 'ArrowRight') navLightbox(1);
});
<\/script>`;

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
