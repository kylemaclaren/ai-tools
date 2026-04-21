#!/usr/bin/env node
// Sidecar for the customer-journey skill. Renders no-visual flows (CLI,
// MCP, chat, API exchanges, Figma embeds) into placeholders the skill
// reserved via `- extend: <key>` entries in journey.yaml.
//
// Copy this file into your prototype repo next to journey.yaml, rename it
// to journey-extend.mjs, and customize the `render*` functions + CSS for
// your project's bespoke flows.
//
// Run AFTER the skill:
//   node <skill>/journey.mjs customer-journey/journey.yaml
//   node customer-journey/journey-extend.mjs
//
// Why a sidecar (not part of the skill): these flows are bespoke to one
// project. The customer-journey skill renders real screenshots; this
// script lets a project overlay custom HTML without polluting the skill.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const htmlPath = resolve(here, "journey.html");
const extendPath = resolve(here, "extend.yaml");

// Resolve the `yaml` module. Tries (in order):
//   1. The project's own node_modules (if the project installs `yaml`).
//   2. The skill's node_modules, located via the JOURNEY_SKILL_DIR env var
//      or a common relative path.
// If neither works, instruct the user to install `yaml` in their project.
async function loadYamlParser() {
  try {
    return (await import("yaml")).parse;
  } catch {
    // fall through
  }
  const skillDir =
    process.env.JOURNEY_SKILL_DIR ??
    resolve(here, "/path/to/customer-journey-skill");
  const candidate = resolve(skillDir, "node_modules/yaml/dist/index.js");
  if (existsSync(candidate)) {
    const mod = await import(pathToFileURL(candidate).href);
    return mod.parse;
  }
  console.error(
    "Could not find the `yaml` module. Either run `npm i yaml` in your project, " +
      "or set JOURNEY_SKILL_DIR to the customer-journey skill directory."
  );
  process.exit(1);
}

const parse = await loadYamlParser();

if (!existsSync(htmlPath)) {
  console.error(`Not found: ${htmlPath}`);
  console.error("Run the skill first to generate journey.html.");
  process.exit(1);
}
if (!existsSync(extendPath)) {
  console.error(`Not found: ${extendPath}`);
  process.exit(1);
}

function main() {
  const extend = parse(readFileSync(extendPath, "utf8"));
  let html = readFileSync(htmlPath, "utf8");

  html = injectStyles(html);

  // ── Customize per project ────────────────────────────────────────
  // Add one call per `- extend: <key>` entry in journey.yaml. The
  // `render*` function receives the corresponding block from extend.yaml
  // and should return raw HTML that drops in where the placeholder was.
  //
  // Peer-journey slot (top-level `- extend: ...`): render a title slide
  // AND a row. Sub-row slot (`- extend: ...` inside `rows:`): render just
  // the row — the parent journey's title card is already placed.
  html = fillExtendPlaceholder(html, "example_flow", extend.example_flow, renderExampleFlow);
  // ─────────────────────────────────────────────────────────────────

  const unfilled = html.match(/<!--\s*extend:[a-z0-9_\-]+\s*-->/gi);
  if (unfilled) {
    console.error(`Unfilled extend placeholders in HTML: ${unfilled.join(", ")}`);
    process.exit(1);
  }

  writeFileSync(htmlPath, html, "utf8");
  const sizeMB = (Buffer.byteLength(html, "utf8") / 1024 / 1024).toFixed(1);
  console.log(`Extended: ${htmlPath} (${sizeMB} MB)`);
}

// ── HTML mutations ──────────────────────────────────────────────────

function injectStyles(html) {
  return html.replace("</style>", `${EXTEND_CSS}\n</style>`);
}

// Replaces `<!-- extend:<key> -->` with the HTML returned by `render(data)`.
// The placeholder is emitted by the customer-journey skill for any entry
// of the form `- extend: <key>` in journey.yaml (peer-journey or sub-row).
function fillExtendPlaceholder(html, key, data, render) {
  const placeholder = new RegExp(`<!--\\s*extend:${key}\\s*-->`);
  if (!placeholder.test(html)) {
    console.error(
      `No <!-- extend:${key} --> placeholder found in journey.html. ` +
        `Add \`- extend: ${key}\` to the journeys list in journey.yaml.`
    );
    process.exit(1);
  }
  if (!data) {
    console.error(`extend.yaml has no \`${key}\` entry to fill placeholder.`);
    process.exit(1);
  }
  return html.replace(placeholder, render(data));
}

// ── Example render function — replace with your own ─────────────────
//
// For a SUB-ROW slot (nested inside a journey's `rows:`), return just a
// <section class="slide light screenshots-slide"> with a `.ss-row` of
// `.ss-card` elements. The parent journey's title card is already placed
// by the skill; don't emit another one.
//
// For a PEER-JOURNEY slot (top-level `- extend: ...`), return both a
// <section class="slide dark"> title card AND the screenshots section.
//
// Reuse the skill's CSS classes (slide, slide-inner, headline, eyebrow,
// journey-number, ss-row, ss-card, ss-caption) so the sidecar slides
// match the rest of the deck. Add scoped CSS only for genuinely new UI.

function renderExampleFlow(block) {
  const cards = (block.steps ?? [])
    .map(
      (s) => `<div class="ss-card">
        <div class="example-frame">${esc(s.content ?? "")}</div>
        <p class="ss-caption">${esc(s.caption ?? "")}</p>
      </div>`
    )
    .join("\n      ");
  const label = block.sub_label ?? block.title ?? "";
  const eyebrow = label
    ? `<p class="ss-section-label">${esc(label)}</p>\n  `
    : "";
  return `<section class="slide light screenshots-slide">
  ${eyebrow}<div class="ss-row">
      ${cards}
  </div>
</section>`;
}

// ── Helpers ─────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Scoped styles for sidecar-rendered cards ────────────────────────
// Add CSS for any new UI introduced above (chat bubbles, terminal frames,
// API request/response panes, etc.). Everything else should reuse the
// skill's existing classes so the deck stays visually consistent.

const EXTEND_CSS = `
.example-frame{
  background:#111214;
  color:#e7e7ea;
  border-radius:12px;
  padding:24px;
  font-family:'Inter',system-ui,sans-serif;
  font-size:15px;
  line-height:1.55;
  min-height:320px;
}
`;

main();
