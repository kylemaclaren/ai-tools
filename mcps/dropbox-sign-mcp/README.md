# dropbox-sign-mcp

Draft contracts, analyze documents, and send them for e-signature via [Dropbox Sign](https://sign.dropbox.com/) — all from your AI editor's chat.

An MCP server (a plugin that gives your AI editor new capabilities) for working with the Dropbox Sign API. Describe the contract you need in plain English, review the terms in chat, and send for signature without leaving your editor. You can also upload an existing PDF and the tool will auto-detect signature and fill-in fields.

## Who is this for?

PMs, founders, ops folks, or anyone who sends contracts, NDAs, or offer letters through Dropbox Sign and wants to do it faster — without switching to the Sign web app, manually placing fields, or re-typing signer details.

You'll need:
- A [Dropbox Sign](https://sign.dropbox.com/) account (free tier works for testing)
- A [Sign API key](https://app.hellosign.com/home/myAccount#api)
- An AI editor (Cursor, Claude Code, or Codex) that supports MCP

## Install

Open your AI editor (Cursor, Claude Code, or Codex) and paste this prompt:

> Install the **dropbox-sign-mcp** MCP server from `git@github.com:kylemaclaren/ai-tools.git` (sparse checkout `mcps/dropbox-sign-mcp`). Install its Python dependencies and add it to my editor's MCP config with the right `command` and `args` (leave the `env` block empty for now). Then run the bundled auth helper to capture my Dropbox Sign API key securely:
>
> ```
> python3 <mcp-dir>/src/auth.py --config <path-to-my-mcp-config> --server-name dropbox-sign --first-time
> ```
>
> The helper opens the [Dropbox Sign API key page](https://app.hellosign.com/home/myAccount#api) in my browser, prompts for the key in the terminal (input is hidden — it never enters chat or the model context), optionally collects a `DROPBOX_SIGN_CLIENT_ID` for branded signing, and writes everything into the MCP config's `env` block. After it finishes, restart the MCP server.

### Why the auth helper

The helper exists to keep your API key out of the LLM transcript. Pasting a key directly into chat sends it to your model provider's logs and leaves it in screenshots, exports, and shared sessions. Running the helper from a terminal pane lets you type the key via `getpass` (no echo, no tool output) — only the on-disk MCP config and the MCP server process ever see the value.

The same helper handles **rotation** too — when your key is revoked or expires, the MCP returns an error message that points your AI at the helper. Same flow, same security properties; just omit `--first-time`.

### A note on interactive setup across editors

- **Cursor (agent mode):** your AI runs the auth helper directly in a terminal pane you can click into and type the key.
- **Claude Code / Codex:** your AI may instead show you the exact `python3 src/auth.py ...` command and ask you to run it yourself in a terminal — same security properties, one extra step. The key is still captured locally via `getpass` and never enters chat.

JSON-based MCP config hosts (Cursor, Claude Code) work out of the box. For TOML-based hosts (e.g. Codex), update the config by hand.

## Tools

| Tool | Description |
|------|-------------|
| `draft_contract` | Generate a PDF contract from structured terms (N parties, embedded signature fields) |
| `preview_contract` | Open a PDF in the browser with colored field overlays showing placement, types, and signer assignments |
| `analyze_document` | Extract text with coordinates and auto-detect blank fields with inferred types and signer assignments |
| `send_for_signature` | Send a local file or URL for signature with field placement and optional pre-filled values |
| `send_with_template` | Send a signature request using a pre-built Dropbox Sign template |
| `list_templates` | List available templates and their signer roles |
| `check_signature_status` | Check the signing status of a sent request |
| `review_contract` | Run a completeness check — scans for standard clauses, field coverage, and document length, then the LLM adds substantive analysis |
| `cancel_signature_request` | Cancel an incomplete signature request |

## Example prompts

### Draft a new contract

> "Draft an NDA between Acme Corp and Moonhelm Studios. Use standard NDA language and California governing law."

> "Draft a freelance consulting agreement between Acme Corp and Jane Doe for $5,000/month, then send it to jane@example.com for signature."

The LLM will present the full contract terms in chat for you to review and iterate on. Once you approve, it generates the PDF, runs a completeness check (flagging any missing standard clauses or concerns), shows a visual preview with colored field overlays, and sends after your confirmation.

### Send an existing document

> "Send this NDA for signature: https://example.com/contracts/nda.pdf"

> "I need to send this contract to jane@acme.com. Pre-fill the company name as 'Acme Corp' and the effective date as 'March 12, 2026', but leave the signature and address fields for the signer."

The server downloads the document, analyzes it to auto-detect all fill-in fields (underscore blanks, colon-labeled fields like `Name:` and `Date:`), infers field types from labels and surrounding text, assigns signers from section headings, runs a completeness check for missing clauses or red flags, and shows a visual preview with colored overlays before sending.

### Use a template

> "What templates do I have in Sign?"

> "Use the NDA template and send it to new-hire@acme.com as the Receiving Party."

Templates already have fields precisely placed, so no field preview is needed — just provide signer details and send.

### Other actions

> "What's the signing status on that NDA I sent earlier?"

> "Cancel that signature request I just sent — I need to fix a typo."

## How it works

Every signature request follows a human-in-the-loop flow to prevent accidental sends:

```
Draft or upload a document
        ↓
  Analyze & detect fields
        ↓
  Completeness check (standard clauses, red flags)
        ↓
  Review fields in chat (types, signers, pre-fills)
        ↓
  Visual preview with colored overlays
        ↓
  User confirms → Send for signature
```

The only exception is templates, where fields are already placed and confirmed — the LLM collects signer details and sends directly.

## Features

- **Human-in-the-loop**: Contract terms are presented in chat first, a completeness check flags missing clauses, fields are reviewed, and a visual preview is mandatory before sending — no accidental dispatches
- **Completeness check**: Every contract is scanned for standard clauses (governing law, termination, indemnification, severability, etc.) with pass/fail results, then the LLM adds substantive analysis — flagging unusual language, missing protections, or imbalanced obligations
- **Visual field overlays**: Colored rectangles with type labels are drawn directly on the PDF — blue for signer 0, orange for signer 1 — so you can verify placement at a glance
- **Smart field detection**: Both underscore blanks (`___`) and colon-labeled fields (`Name:`, `Phone:`) are auto-detected with precise coordinates, types inferred from labels and surrounding context (e.g., "entered into on the date of ___" is detected as a Date field)
- **Pre-fill support**: Choose which fields to pre-fill with specific values (read-only) vs. which to leave interactive for the signer
- **Flexible parties**: Draft contracts with 1, 2, or N signing parties with parallel or sequential signing order
- **File URL support**: Send documents by URL — shared links are auto-converted to direct downloads where possible
- **Templates**: Discover and use pre-built Dropbox Sign templates with role-based signer mapping
- **Custom branding**: Apply your branded signing experience via API App `client_id`
- **Cancel & status**: Cancel incomplete requests or check signing progress at any time
- **Test mode**: Enabled by default — documents are watermarked and not legally binding until you flip a flag

---

Built by [Kyle Miller](https://www.linkedin.com/in/kylemaclaren/).
