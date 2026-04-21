"""
Dropbox Sign MCP Server

Exposes tools for drafting contracts as PDFs and sending them
for e-signature via the Dropbox Sign API.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
import urllib.request
import webbrowser
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from mcp.server.fastmcp import FastMCP

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
VERSION_URL = (
    "https://raw.githubusercontent.com/kylemaclaren/ai-tools/main"
    "/mcps/dropbox-sign-mcp/VERSION"
)

_version_cache: dict = {}
_VERSION_CACHE_TTL = 3600


def _version_warning() -> str:
    if VERSION == "unknown":
        return ""
    now = time.time()
    if _version_cache.get("latest") and now - _version_cache.get("checked_at", 0) < _VERSION_CACHE_TTL:
        latest = _version_cache["latest"]
    else:
        try:
            req = urllib.request.Request(VERSION_URL, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                latest = resp.read().decode().strip()
            _version_cache["latest"] = latest
            _version_cache["checked_at"] = now
        except Exception:
            return ""
    if latest != VERSION:
        return (
            f"\n\n---\n"
            f"_dropbox-sign-mcp update available: you're on **v{VERSION}**, latest is **v{latest}**. "
            f"Run `git pull` in your dropbox-sign-mcp directory to update._"
        )
    return ""


mcp = FastMCP(
    "Dropbox Sign",
    instructions=(
        "Use this server to draft legal contracts as PDFs and send them for "
        "electronic signature via Dropbox Sign.\n\n"

        "== WORKFLOW A: Draft a new contract ==\n"
        "1) Present the proposed contract terms to the user IN CHAT first -- "
        "include the title, parties, all clauses, and governing law so the user "
        "can review and request changes to the content.\n"
        "2) Once the user approves the terms, call draft_contract to generate "
        "the PDF.\n"
        "3) Call analyze_document on the generated PDF to detect fields.\n"
        "4) Call review_contract to run a completeness check. Present the "
        "results as a 'Dropbox Sign Assistant Review' — include the structural "
        "check results alongside your own substantive legal analysis. Flag any "
        "missing standard clauses, unusual language, or imbalanced obligations.\n"
        "5) Present the detected fields to the user -- list each field's label, "
        "type, and signer assignment. Ask if they want to pre-fill any values.\n"
        "6) Call preview_contract WITH form_fields to show the visual overlay "
        "(colored rectangles with type labels). Ask the user to confirm "
        "placement looks correct.\n"
        "7) Only after the user confirms, call send_for_signature.\n\n"

        "== WORKFLOW B: Send an existing document (file or URL) ==\n"
        "1) Call analyze_document to extract text and auto-detect fields.\n"
        "2) Call review_contract with the detected form_fields to run a "
        "completeness check. Present the results as a 'Dropbox Sign Assistant "
        "Review' — include the structural check results alongside your own "
        "substantive legal analysis. Flag any missing clauses, unusual "
        "language, or concerns.\n"
        "3) Present the detected fields to the user -- list each field's label, "
        "type, and signer assignment.\n"
        "4) Ask if they want to pre-fill any fields (use type 'text-merge' with "
        "a 'name' key and pass values via custom_fields) or leave them "
        "interactive for the signer (use type 'text').\n"
        "5) Call preview_contract WITH form_fields to show the visual overlay. "
        "Ask the user to confirm placement looks correct.\n"
        "6) Only after the user confirms, call send_for_signature.\n\n"

        "== WORKFLOW C: Send using a template ==\n"
        "1) Call list_templates to show available templates and roles.\n"
        "2) Collect signer details (name, email, role) from the user.\n"
        "3) Call send_with_template. No field placement preview is needed "
        "because template fields are already precisely placed.\n\n"

        "== RULES ==\n"
        "- The visual field preview (preview_contract with form_fields) is "
        "MANDATORY before every send_for_signature call. Never skip it.\n"
        "- The ONLY exception is send_with_template, where fields are already "
        "placed in the template.\n"
        "- Always wait for explicit user confirmation after the preview before "
        "calling send_for_signature.\n"
        "- To undo a mistake after sending: cancel_signature_request.\n"
        "- Use check_signature_status to poll progress on sent requests.\n\n"

        "== FIELD ATTRIBUTION ==\n"
        "- analyze_document marks body fields (before signature blocks) as "
        "'text-merge'. These are filled by the SENDER before sending, not "
        "by signers. Pass their values via custom_fields on send_for_signature.\n"
        "- Only fields in or near signature blocks (signature, date, initials, "
        "and adjacent text like 'Printed Name') are interactive signer fields.\n"
        "- Each field has a fill_rule: 'required' (sender must pre-fill), "
        "'optional' (sender may pre-fill or leave for signer), or 'signer' "
        "(only the signer can complete — e.g. signature, date).\n"
        "- When presenting fields, group them by fill_rule. List required "
        "fields first and ask the user for values. Note optional fields the "
        "user may want to pre-fill. List signer fields for confirmation only.\n"
        "- Each field has a descriptive label (e.g. 'Client Name', 'Legal "
        "Matter', 'Attorney Signature'). Use these labels when presenting "
        "fields to the user."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "dropbox-sign-mcp")


def _ensure_output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


def _get_api_key() -> str:
    key = os.environ.get("DROPBOX_SIGN_API_KEY")
    if not key:
        raise RuntimeError(
            "DROPBOX_SIGN_API_KEY is not set in this MCP server's environment.\n\n"
            "Ask your AI to run this MCP's bundled auth helper to set it:\n"
            "  python3 <dropbox-sign-mcp-dir>/src/auth.py "
            "--config <your-mcp-config-path> --server-name dropbox-sign --first-time\n\n"
            "The helper opens https://app.hellosign.com/home/myAccount#api in "
            "your browser, prompts for the key in the terminal (input is "
            "hidden — the key never enters chat or the model context), and "
            "writes it directly to your MCP config. Then restart the MCP "
            "server (Cursor → MCP panel → restart, Claude Code → /mcp restart)."
        )
    return key


def _get_client_id(explicit: str | None) -> str | None:
    """Resolve client_id from explicit param or env var.

    Returns None for empty/placeholder values so they don't reach the API.
    """
    cid = explicit or os.environ.get("DROPBOX_SIGN_CLIENT_ID") or None
    if cid and len(cid) != 32:
        return None
    return cid


def _fix_dropbox_url(url: str) -> str:
    """Rewrite Dropbox shared links so they return the raw file."""
    parsed = urlparse(url)
    if "dropbox.com" not in parsed.hostname:
        return url
    params = parse_qs(parsed.query)
    params["dl"] = ["1"]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


_FIELD_TYPE_MAP = {
    "signature": "SubFormFieldsPerDocumentSignature",
    "text": "SubFormFieldsPerDocumentText",
    "text-merge": "SubFormFieldsPerDocumentTextMerge",
    "date_signed": "SubFormFieldsPerDocumentDateSigned",
    "initials": "SubFormFieldsPerDocumentInitials",
}


def _build_form_fields(
    fields: list[dict], models
) -> tuple[list, str | None]:
    """Convert user-supplied field dicts to SDK form-field objects.

    Returns (field_objects, error_string). error_string is None on success.
    """
    base_keys = {"type", "x", "y", "width", "height", "page"}
    result = []

    for idx, field in enumerate(fields):
        field_type = field.get("type", "")
        required_keys = base_keys | (set() if field_type == "text-merge" else {"signer"})
        missing = required_keys - set(field.keys())
        if missing:
            return [], f"Error: form_fields[{idx}] is missing keys: {missing}"
        cls_name = _FIELD_TYPE_MAP.get(field_type)
        if not cls_name:
            return [], (
                f"Error: form_fields[{idx}] has unknown type '{field_type}'. "
                f"Valid types: {', '.join(_FIELD_TYPE_MAP.keys())}"
            )

        cls = getattr(models, cls_name)
        common_kwargs = dict(
            document_index=field.get("document_index", 0),
            api_id=field.get("api_id", f"field_{idx}"),
            type=field_type,
            x=int(field["x"]),
            y=int(field["y"]),
            width=int(field["width"]),
            height=int(field["height"]),
            page=int(field["page"]),
            required=field.get("required", True),
        )

        if field_type == "text-merge":
            common_kwargs["signer"] = "sender"
            common_kwargs["name"] = field.get("name", f"merge_{idx}")
        else:
            common_kwargs["signer"] = str(field["signer"])

        obj = cls(**common_kwargs)
        result.append(obj)

    return result, None


def _format_api_error(exc) -> str:
    """Extract a clean error message from a Dropbox Sign ApiException.

    For auth failures (401/403), returns a directive pointing the LLM at the
    bundled auth helper instead of a raw API error so token rotation stays
    secure (key never enters chat).
    """
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return (
            f"Dropbox Sign authentication failed (HTTP {status}). Your API key "
            f"may be expired or revoked.\n\n"
            f"Ask your AI to rotate the key by running this MCP's bundled auth helper:\n"
            f"  python3 <dropbox-sign-mcp-dir>/src/auth.py "
            f"--config <your-mcp-config-path> --server-name dropbox-sign\n\n"
            f"The helper opens https://app.hellosign.com/home/myAccount#api in "
            f"your browser, prompts for the new key in the terminal (input is "
            f"hidden — the key never enters chat or the model context), and "
            f"writes it directly to your MCP config. Then restart the MCP "
            f"server (Cursor → MCP panel → restart, Claude Code → /mcp restart)."
        )
    if hasattr(exc, "data") and exc.data:
        err = getattr(exc.data, "error", None)
        if err:
            msg = getattr(err, "error_msg", None)
            path = getattr(err, "error_path", None)
            if msg:
                detail = f" (field: {path})" if path else ""
                return f"Error from Dropbox Sign: {msg}{detail}"
    if hasattr(exc, "body") and exc.body:
        return f"Error from Dropbox Sign: {exc.body}"
    return f"Error from Dropbox Sign ({exc.status}): {exc.reason}"


def _format_response(sr) -> str:
    """Build a human-readable summary from a SignatureRequestResponse."""
    mode_label = " (TEST MODE)" if sr.test_mode else ""
    signer_summary = ", ".join(
        f"{sig.signer_name} <{sig.signer_email_address}> ({sig.status_code})"
        for sig in sr.signatures
    )
    return (
        f"Signature request sent successfully{mode_label}!\n"
        f"  Request ID: {sr.signature_request_id}\n"
        f"  Title: {sr.title}\n"
        f"  Signers: {signer_summary}\n"
        f"  Details: {sr.details_url}"
    )


_SIGNER_COLORS = [
    ((0.68, 0.85, 0.95), (0.0, 0.45, 0.7)),    # light blue / blue
    ((1.0, 0.85, 0.65), (0.9, 0.55, 0.0)),      # light orange / orange
    ((0.7, 0.95, 0.7), (0.0, 0.6, 0.0)),        # light green / green
    ((0.9, 0.75, 0.95), (0.55, 0.0, 0.7)),      # light purple / purple
]

_DISPLAY_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["signature", "sign here", "sign below"], "Signature"),
    (["initial"], "Initials"),
    (["date"], "Date"),
    (["printed name", "typed name", "full name"], "Name"),
    (["name"], "Name"),
    (["mailing address", "street address"], "Address"),
    (["address"], "Address"),
    (["city"], "City"),
    (["state"], "State"),
    (["zip", "postal"], "ZIP"),
    (["phone", "telephone", "fax"], "Phone"),
    (["email", "e-mail"], "Email"),
    (["company", "organization", "employer"], "Company"),
    (["title", "position", "department"], "Title"),
]


def _infer_display_type(field_type: str, label: str) -> str:
    """Map a field's API type and label to a concise display name for overlays."""
    if field_type == "signature":
        return "Signature"
    if field_type == "date_signed":
        return "Date"
    if field_type == "initials":
        return "Initials"
    if field_type == "text-merge":
        return "Pre-filled"

    label_lower = label.lower()
    for keywords, display in _DISPLAY_TYPE_KEYWORDS:
        if any(kw in label_lower for kw in keywords):
            return display
    return "Text"


def _render_field_overlays(pdf_path: str, form_fields: list[dict]) -> str:
    """Draw colored rectangles with type labels onto a copy of the PDF.

    Returns the path to the annotated PDF. Each signer gets a distinct
    color (blue, orange, green, purple) cycling through the palette.
    """
    import fitz

    doc = fitz.open(pdf_path)

    for idx, field in enumerate(form_fields):
        page_num = int(field.get("page", 1)) - 1
        if page_num < 0 or page_num >= len(doc):
            continue

        page = doc[page_num]
        x = float(field.get("x", 0))
        y = float(field.get("y", 0))
        w = float(field.get("width", 100))
        h = float(field.get("height", 16))

        y_top = y - h + 6
        rect = fitz.Rect(x, y_top, x + w, y_top + h)

        signer = field.get("signer", 0)
        signer_int = int(signer) if str(signer).isdigit() else 0
        fill_rgb, stroke_rgb = _SIGNER_COLORS[signer_int % len(_SIGNER_COLORS)]

        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(
            color=stroke_rgb,
            fill=fill_rgb,
            fill_opacity=0.35,
            stroke_opacity=0.8,
            width=1.5,
        )
        shape.commit()

        field_type = field.get("type", "text")
        label = field.get("label", "")
        display_type = _infer_display_type(field_type, label)

        fontsize = min(9, h * 0.7)
        text_point = fitz.Point(x + 3, y_top + h - 3)
        page.insert_text(
            text_point,
            display_type,
            fontsize=fontsize,
            color=stroke_rgb,
            fontname="helv",
        )

    out_dir = _ensure_output_dir()
    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    preview_path = os.path.join(out_dir, f"preview_{basename}.pdf")
    doc.save(preview_path)
    doc.close()

    return preview_path


# ---------------------------------------------------------------------------
# Tool: draft_contract
# ---------------------------------------------------------------------------


@mcp.tool()
def draft_contract(
    title: Annotated[str, "Contract title, e.g. 'Freelance Consulting Agreement'"],
    parties: Annotated[
        list[dict],
        (
            "List of party objects, each with 'name' and 'role' keys. "
            "Order matters: signer1 = first party, signer2 = second, etc. "
            "Example: [{'name': 'Acme Corp', 'role': 'Client'}, "
            "{'name': 'Jane Doe', 'role': 'Contractor'}]"
        ),
    ],
    effective_date: Annotated[str, "Effective date in YYYY-MM-DD format"],
    clauses: Annotated[
        list[str],
        "List of contract clauses/terms. Each string is one clause.",
    ],
    governing_law: Annotated[
        str, "Jurisdiction for governing law, e.g. 'State of California'"
    ] = "State of Delaware",
) -> str:
    """Generate a PDF contract from structured terms.

    Returns the absolute file path of the generated PDF so it can be
    passed to send_for_signature. Signature and date fields are embedded
    as invisible text tags for each party.
    """
    from fpdf import FPDF

    if not parties:
        return "Error: at least one party is required."

    for i, p in enumerate(parties):
        if not p.get("name") or not p.get("role"):
            return f"Error: party at index {i} is missing 'name' or 'role'. Got: {p}"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Effective Date: {effective_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Parties preamble
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Parties", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)

    party_fragments = []
    for p in parties:
        party_fragments.append(f'{p["name"]} ("{p["role"]}")')
    if len(party_fragments) == 1:
        parties_text = party_fragments[0]
    elif len(party_fragments) == 2:
        parties_text = f"{party_fragments[0]} and {party_fragments[1]}"
    else:
        parties_text = (
            ", ".join(party_fragments[:-1]) + f", and {party_fragments[-1]}"
        )

    pdf.multi_cell(
        0, 7,
        f'This agreement ("Agreement") is entered into as of {effective_date} '
        f"by and between {parties_text}.",
    )
    pdf.ln(4)

    # Clauses
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Terms and Conditions", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)

    for idx, clause in enumerate(clauses, start=1):
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"Section {idx}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 7, clause)
        pdf.ln(3)

    # Governing law
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Governing Law", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0, 7,
        f"This Agreement shall be governed by and construed in accordance "
        f"with the laws of the {governing_law}, without regard to its "
        f"conflict of laws principles.",
    )
    pdf.ln(6)

    # Signature blocks with Dropbox Sign text tags (white, invisible text).
    # signer1 = parties[0], signer2 = parties[1], etc.
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Signatures", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    num_signers = len(parties)

    for signer_idx, party in enumerate(parties, start=1):
        name, role = party["name"], party["role"]

        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 7, f"{role}:", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Signature text tag (white text)
        pdf.set_font("Courier", "", 12)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, f"[sig|req|signer{signer_idx}]", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "", 11)
        pdf.cell(90, 0, "", border="T")
        pdf.ln(2)
        pdf.cell(0, 7, name, new_x="LMARGIN", new_y="NEXT")

        # Date text tag (white text)
        pdf.set_font("Courier", "", 12)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(35, 7, "Date: ", new_x="RIGHT", new_y="LAST")
        pdf.cell(0, 7, f"[date|req|signer{signer_idx}]", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(8)

    # Footer
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(
        0, 6,
        f"Generated on {date.today().isoformat()}",
        new_x="LMARGIN", new_y="NEXT", align="C",
    )

    out_dir = _ensure_output_dir()
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    filename = f"{safe_title}_{date.today().isoformat()}.pdf"
    filepath = os.path.join(out_dir, filename)
    pdf.output(filepath)

    signer_map = ", ".join(
        f"signer{i}={p['name']}" for i, p in enumerate(parties, start=1)
    )
    return (
        f"Contract PDF saved to: {filepath}\n"
        f"Signature fields embedded for {num_signers} signer(s) ({signer_map}). "
        f"Pass signers to send_for_signature in the same order."
        + _version_warning()
    )


# ---------------------------------------------------------------------------
# Tool: preview_contract
# ---------------------------------------------------------------------------


@mcp.tool()
def preview_contract(
    file_path: Annotated[str, "Absolute path to the PDF file to preview (from draft_contract)"],
    form_fields: Annotated[
        list[dict] | None,
        (
            "Optional list of form field dicts (same format as send_for_signature). "
            "When provided, the preview renders colored overlays on the PDF showing "
            "each field's position, type, and signer assignment — blue for signer 0, "
            "orange for signer 1, etc. Use this after analyze_document to visually "
            "verify field placement before sending."
        ),
    ] = None,
) -> str:
    """Open a contract PDF in the default browser for review before sending.

    When form_fields are provided, generates an annotated copy with colored
    overlays showing field placement, types, and signer assignments.
    """
    if not os.path.isfile(file_path):
        return f"Error: file not found at {file_path}"

    if form_fields:
        try:
            preview_path = _render_field_overlays(file_path, form_fields)
        except Exception as exc:
            return f"Error rendering field overlays: {exc}"
        url = "file://" + os.path.abspath(preview_path)
        webbrowser.open(url)
        field_count = len(form_fields)
        signer_ids = sorted(set(
            int(f.get("signer", 0)) for f in form_fields
            if str(f.get("signer", "0")).isdigit()
        ))
        color_legend = ", ".join(
            f"signer {s} = {['blue', 'orange', 'green', 'purple'][s % 4]}"
            for s in signer_ids
        )
        return (
            f"Opened annotated preview with {field_count} field(s) highlighted.\n"
            f"Color legend: {color_legend}\n"
            f"Each field shows its type and label. Review the placement, then "
            f"confirm to send or request adjustments."
        )

    url = "file://" + os.path.abspath(file_path)
    webbrowser.open(url)
    return (
        f"Opened {file_path} in your default browser/PDF viewer.\n"
        "Please review the document. When you're ready, confirm and I'll send it for signature."
    )


# ---------------------------------------------------------------------------
# Tool: send_for_signature
# ---------------------------------------------------------------------------


@mcp.tool()
def send_for_signature(
    signers: Annotated[
        list[dict],
        (
            "List of signer objects. Order must match the contract parties "
            "(signer1=first party, signer2=second, etc.). Each must have "
            "'name' and 'email' keys. "
            "Example: [{'name': 'Acme Corp', 'email': 'ceo@acme.com'}, "
            "{'name': 'Jane Doe', 'email': 'jane@example.com'}]"
        ),
    ],
    subject: Annotated[str, "Email subject line for the signature request"],
    message: Annotated[str, "Message body included in the signature email"],
    file_path: Annotated[
        str | None,
        "Absolute path to a local PDF file to send. Provide either file_path or file_urls, not both.",
    ] = None,
    file_urls: Annotated[
        list[str] | None,
        (
            "List of publicly accessible URLs to documents to send. "
            "Dropbox shared links are auto-converted to direct download URLs. "
            "Provide either file_urls or file_path, not both."
        ),
    ] = None,
    title: Annotated[str, "Title for the signature request"] = "Contract",
    signing_order: Annotated[
        str,
        "Signing order: 'sequential' (one after another) or 'parallel' (all at once). Defaults to 'parallel'.",
    ] = "parallel",
    client_id: Annotated[
        str | None,
        "API App client_id for custom branding. Falls back to DROPBOX_SIGN_CLIENT_ID env var if not set.",
    ] = None,
    form_fields: Annotated[
        list[dict] | None,
        (
            "Optional list of form field objects for explicit field placement. "
            "Each must have: 'type' (signature/text/text-merge/date_signed/initials), "
            "'x', 'y', 'width', 'height', 'page' (1-indexed), 'signer' (0-indexed int). "
            "For 'text-merge' fields (pre-filled by sender), also include 'name' "
            "(a unique key) and provide the value via custom_fields. "
            "Use with analyze_document to determine coordinates. "
            "When provided, text tags are disabled."
        ),
    ] = None,
    custom_fields: Annotated[
        list[dict] | None,
        (
            "Optional list of pre-fill values for text-merge fields. "
            "Each must have 'name' (matching a text-merge field name) and 'value'. "
            "Example: [{'name': 'party_name', 'value': 'Acme Corp'}]"
        ),
    ] = None,
    test_mode: Annotated[
        bool,
        "If true, the request is not legally binding (watermarked). Defaults to true.",
    ] = True,
) -> str:
    """Send a document for electronic signature via Dropbox Sign.

    Accepts either a local file path or publicly accessible URL(s).
    For existing documents, use analyze_document first to get coordinates,
    then pass form_fields for precise field placement. Use 'text-merge'
    fields with custom_fields to pre-fill values (read-only to signer),
    or 'text' fields to leave them interactive for the signer.
    Returns the signature request ID and a link to view its status.
    """
    from dropbox_sign import ApiClient, ApiException, Configuration, api, models

    if not file_path and not file_urls:
        return "Error: provide either file_path or file_urls."
    if file_path and file_urls:
        return "Error: provide either file_path or file_urls, not both."
    if file_path and not os.path.isfile(file_path):
        return f"Error: file not found at {file_path}"

    api_key = _get_api_key()
    configuration = Configuration(username=api_key)

    signer_objects = []
    for idx, s in enumerate(signers):
        name = s.get("name")
        email = s.get("email")
        if not name or not email:
            return (
                f"Error: signer at index {idx} is missing 'name' or 'email'. "
                f"Got: {s}"
            )
        order = idx if signing_order == "sequential" else 0
        signer_objects.append(
            models.SubSignatureRequestSigner(
                name=name,
                email_address=email,
                order=order,
            )
        )

    signing_options = models.SubSigningOptions(
        default_type="draw",
        draw=True,
        type=True,
        upload=True,
        phone=False,
    )

    resolved_client_id = _get_client_id(client_id)

    use_text_tags = form_fields is None
    request_kwargs: dict = dict(
        title=title,
        subject=subject,
        message=message,
        signers=signer_objects,
        signing_options=signing_options,
        test_mode=test_mode,
        use_text_tags=use_text_tags,
        hide_text_tags=use_text_tags,
    )

    if form_fields:
        ff_objects, err = _build_form_fields(form_fields, models)
        if err:
            return err
        request_kwargs["form_fields_per_document"] = ff_objects

    if custom_fields:
        cf_objects = []
        for cf in custom_fields:
            name = cf.get("name")
            value = cf.get("value", "")
            if not name:
                return "Error: each custom_field must have a 'name' key."
            cf_objects.append(
                models.SubCustomField(name=name, value=str(value))
            )
        request_kwargs["custom_fields"] = cf_objects

    if file_path:
        request_kwargs["files"] = [open(file_path, "rb")]
    else:
        request_kwargs["file_urls"] = [_fix_dropbox_url(u) for u in file_urls]

    if resolved_client_id:
        request_kwargs["client_id"] = resolved_client_id

    send_request = models.SignatureRequestSendRequest(**request_kwargs)

    try:
        with ApiClient(configuration) as api_client:
            sig_api = api.SignatureRequestApi(api_client)
            response = sig_api.signature_request_send(
                signature_request_send_request=send_request,
            )
    except ApiException as exc:
        return _format_api_error(exc)

    return _format_response(response.signature_request) + _version_warning()


# ---------------------------------------------------------------------------
# Tool: list_templates
# ---------------------------------------------------------------------------


@mcp.tool()
def list_templates(
    query: Annotated[
        str | None,
        "Optional search query to filter templates by name or other fields.",
    ] = None,
) -> str:
    """List available Dropbox Sign templates in your account.

    Returns template IDs, titles, and signer roles so you can use them
    with send_with_template.
    """
    from dropbox_sign import ApiClient, ApiException, Configuration, api

    api_key = _get_api_key()
    configuration = Configuration(username=api_key)

    try:
        with ApiClient(configuration) as api_client:
            template_api = api.TemplateApi(api_client)
            kwargs: dict = dict(page=1, page_size=20)
            if query:
                kwargs["query"] = query
            response = template_api.template_list(**kwargs)
    except ApiException as exc:
        return _format_api_error(exc)

    templates = response.templates
    if not templates:
        return "No templates found."

    lines = [f"Found {len(templates)} template(s):\n"]
    for tmpl in templates:
        lines.append(f"  Title: {tmpl.title}")
        lines.append(f"  Template ID: {tmpl.template_id}")
        if tmpl.signer_roles:
            roles = ", ".join(r.name for r in tmpl.signer_roles)
            lines.append(f"  Signer roles: {roles}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: send_with_template
# ---------------------------------------------------------------------------


@mcp.tool()
def send_with_template(
    template_id: Annotated[str, "The template ID from list_templates"],
    signers: Annotated[
        list[dict],
        (
            "List of signer objects mapped to template roles. Each must have "
            "'role', 'name', and 'email' keys. "
            "Example: [{'role': 'Client', 'name': 'Jane Doe', 'email': 'jane@example.com'}]"
        ),
    ],
    subject: Annotated[str, "Email subject line for the signature request"],
    message: Annotated[str, "Message body included in the signature email"],
    title: Annotated[str, "Title for the signature request"] = "Contract",
    client_id: Annotated[
        str | None,
        "API App client_id for custom branding. Falls back to DROPBOX_SIGN_CLIENT_ID env var if not set.",
    ] = None,
    test_mode: Annotated[
        bool,
        "If true, the request is not legally binding (watermarked). Defaults to true.",
    ] = True,
) -> str:
    """Send a signature request using a pre-built Dropbox Sign template.

    Use list_templates first to discover available templates and their
    signer roles.
    """
    from dropbox_sign import ApiClient, ApiException, Configuration, api, models

    api_key = _get_api_key()
    configuration = Configuration(username=api_key)

    signer_objects = []
    for idx, s in enumerate(signers):
        role = s.get("role")
        name = s.get("name")
        email = s.get("email")
        if not role or not name or not email:
            return (
                f"Error: signer at index {idx} is missing 'role', 'name', or 'email'. "
                f"Got: {s}"
            )
        signer_objects.append(
            models.SubSignatureRequestTemplateSigner(
                role=role,
                name=name,
                email_address=email,
            )
        )

    resolved_client_id = _get_client_id(client_id)

    request_kwargs: dict = dict(
        template_ids=[template_id],
        title=title,
        subject=subject,
        message=message,
        signers=signer_objects,
        test_mode=test_mode,
    )

    if resolved_client_id:
        request_kwargs["client_id"] = resolved_client_id

    send_request = models.SignatureRequestSendWithTemplateRequest(**request_kwargs)

    try:
        with ApiClient(configuration) as api_client:
            sig_api = api.SignatureRequestApi(api_client)
            response = sig_api.signature_request_send_with_template(
                signature_request_send_with_template_request=send_request,
            )
    except ApiException as exc:
        return _format_api_error(exc)

    return _format_response(response.signature_request)


# ---------------------------------------------------------------------------
# Tool: check_signature_status
# ---------------------------------------------------------------------------


@mcp.tool()
def check_signature_status(
    signature_request_id: Annotated[
        str, "The signature request ID returned by send_for_signature or send_with_template"
    ],
) -> str:
    """Check the current signing status of a Dropbox Sign signature request."""
    from dropbox_sign import ApiClient, ApiException, Configuration, api

    api_key = _get_api_key()
    configuration = Configuration(username=api_key)

    try:
        with ApiClient(configuration) as api_client:
            sig_api = api.SignatureRequestApi(api_client)
            response = sig_api.signature_request_get(
                signature_request_id=signature_request_id,
            )
    except ApiException as exc:
        return _format_api_error(exc)

    sr = response.signature_request
    lines = [
        f"Signature Request: {sr.title}",
        f"  ID: {sr.signature_request_id}",
        f"  Complete: {sr.is_complete}",
        f"  Declined: {sr.is_declined}",
        f"  Has Error: {sr.has_error}",
        f"  Details: {sr.details_url}",
        "",
        "Signers:",
    ]

    for sig in sr.signatures:
        viewed = (
            f"last viewed at {sig.last_viewed_at}"
            if sig.last_viewed_at
            else "not yet viewed"
        )
        signed = (
            f"signed at {sig.signed_at}" if sig.signed_at else "not yet signed"
        )
        lines.append(
            f"  - {sig.signer_name} <{sig.signer_email_address}>: "
            f"{sig.status_code} ({viewed}, {signed})"
        )
        if sig.decline_reason:
            lines.append(f"    Decline reason: {sig.decline_reason}")

    return "\n".join(lines) + _version_warning()


# ---------------------------------------------------------------------------
# Tool: review_contract
# ---------------------------------------------------------------------------

_CLAUSE_CHECKS: list[tuple[str, list[str]]] = [
    ("Governing law", ["governing law", "governed by", "jurisdiction"]),
    ("Termination", ["termination", "terminate", "term of this"]),
    ("Confidentiality", ["confidential", "nondisclosure", "non-disclosure"]),
    ("Indemnification", ["indemnif", "hold harmless"]),
    ("Limitation of liability", ["limitation of liability", "consequential damages", "liable for"]),
    ("Entire agreement / integration", ["entire agreement", "integration", "supersedes all prior"]),
    ("Severability", ["severab", "invalid or unenforceable"]),
    ("Assignment", ["assign", "transfer of rights"]),
    ("Dispute resolution", ["arbitration", "mediation", "dispute resolution"]),
    ("Notices", ["notice shall be", "notices to", "written notice"]),
]

_PARTY_PATTERNS = [
    "party a", "party b", "disclosing party", "receiving party",
    "client", "contractor", "employer", "employee",
    "company", "consultant", "licensor", "licensee",
    "seller", "buyer", "landlord", "tenant",
    "the \"", "the '", "(\"",
]


def _check_clause_present(
    full_text_lower: str, keywords: list[str],
) -> tuple[bool, str]:
    """Scan text for any of the given keywords.

    Returns (found, snippet) where snippet is the surrounding context
    of the first match, or an empty string if not found.
    """
    for kw in keywords:
        idx = full_text_lower.find(kw)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(full_text_lower), idx + len(kw) + 60)
            snippet = full_text_lower[start:end].replace("\n", " ").strip()
            return True, f"...{snippet}..."
    return False, ""


def _count_parties(full_text_lower: str) -> int:
    """Estimate the number of distinct parties mentioned in the document."""
    found = set()
    for pattern in _PARTY_PATTERNS:
        if pattern in full_text_lower:
            found.add(pattern)
    return min(len(found), 6)


@mcp.tool()
def review_contract(
    file_path: Annotated[str, "Absolute path to the PDF file to review"],
    form_fields: Annotated[
        list[dict] | None,
        (
            "Optional list of detected form fields (from analyze_document). "
            "Used to verify signature and date field coverage."
        ),
    ] = None,
    contract_type: Annotated[
        str | None,
        (
            "Optional contract type hint (e.g., 'nda', 'consulting', "
            "'employment', 'sales'). Helps the LLM tailor its analysis."
        ),
    ] = None,
) -> str:
    """Review a contract PDF for completeness and standard clause coverage.

    Performs programmatic structural checks (clause detection, field
    coverage, document length) and returns the full document text for
    the LLM to provide substantive legal analysis.
    """
    import pdfplumber

    if not os.path.isfile(file_path):
        return f"Error: file not found at {file_path}"

    pages_text: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

    full_text = "\n".join(pages_text)
    full_text_lower = full_text.lower()
    word_count = len(full_text.split())

    report: list[str] = ["== DROPBOX SIGN ASSISTANT: COMPLETENESS REVIEW ==", ""]

    # --- Structural checks ---
    report.append("STRUCTURAL CHECKS:")
    passed = 0
    total = 0

    party_count = _count_parties(full_text_lower)
    total += 1
    if party_count >= 2:
        report.append(f"  [PASS] Parties identified ({party_count} party indicators detected)")
        passed += 1
    elif party_count == 1:
        report.append("  [WARN] Only 1 party indicator detected -- verify all parties are named")
    else:
        report.append("  [MISS] No standard party indicators found")

    if form_fields:
        sig_signers = sorted(set(
            f.get("signer", -1) for f in form_fields if f.get("type") == "signature"
        ))
        date_fields = [f for f in form_fields if f.get("type") == "date_signed"]

        total += 1
        if len(sig_signers) >= 2:
            report.append(f"  [PASS] Signature fields ({len(sig_signers)} signers covered)")
            passed += 1
        elif len(sig_signers) == 1:
            report.append("  [WARN] Signature field for only 1 signer -- verify this is intentional")
        else:
            report.append("  [MISS] No signature fields detected")

        total += 1
        if date_fields:
            report.append(f"  [PASS] Date fields present ({len(date_fields)} found)")
            passed += 1
        else:
            report.append("  [MISS] No date fields detected")
    else:
        report.append("  [SKIP] Signature/date field check (no form_fields provided)")

    for clause_name, keywords in _CLAUSE_CHECKS:
        total += 1
        found, snippet = _check_clause_present(full_text_lower, keywords)
        if found:
            report.append(f"  [PASS] {clause_name} clause found")
            passed += 1
        else:
            report.append(f"  [MISS] {clause_name} clause not found")

    total += 1
    if word_count >= 500:
        report.append(f"  [PASS] Document length: {word_count:,} words")
        passed += 1
    elif word_count >= 200:
        report.append(f"  [WARN] Document is short ({word_count} words) -- verify this is complete")
    else:
        report.append(f"  [MISS] Document appears very short ({word_count} words)")

    report.append("")
    missed = total - passed
    if missed > 0:
        report.append(
            f"DROPBOX SIGN ASSISTANT flagged {missed} item(s) for review "
            f"({passed} of {total} checks passed)."
        )
    else:
        report.append(
            f"DROPBOX SIGN ASSISTANT: all {total} structural checks passed."
        )

    report.append("")
    report.append("== FULL DOCUMENT TEXT ==")
    report.append(full_text)

    report.append("")
    type_hint = f" (detected or stated contract type: {contract_type})" if contract_type else ""
    report.append(
        "== INSTRUCTIONS FOR LLM ==\n"
        "You are acting as the Dropbox Sign Assistant — a senior legal "
        "reviewer. Analyze the document text above and present your findings "
        f"to the user under the heading 'Dropbox Sign Assistant Review'{type_hint}.\n\n"
        "First, identify the document type (NDA, consulting agreement, "
        "employment contract, lease, sales agreement, IP license, loan "
        "agreement, partnership agreement, terms of service, or other). "
        "Then provide:\n\n"
        "1. WHAT LOOKS GOOD — clauses and protections that are standard "
        "and well-drafted for this type of document\n"
        "2. WHAT'S MISSING — clauses that are standard for this document "
        "type but absent (e.g., indemnification in a services agreement, "
        "security deposit terms in a lease, IP assignment in a work-for-hire "
        "contract, payment terms in a sales agreement)\n"
        "3. UNUSUAL LANGUAGE — any nonstandard, one-sided, or potentially "
        "problematic clauses the signer should review carefully (e.g., "
        "unlimited liability, broad non-compete scope, automatic renewal "
        "without notice, unilateral amendment rights)\n"
        "4. BALANCE OF OBLIGATIONS — whether rights and obligations are "
        "reasonably balanced between parties, or if one side bears "
        "disproportionate risk\n"
        "5. KEY TERMS TO VERIFY — specific values the user should "
        "double-check (dates, dollar amounts, notice periods, term length, "
        "geographic scope)\n\n"
        "Keep the tone professional but accessible. Use the structural check "
        "results above as a starting point, then add your substantive analysis. "
        "End with a one-line recommendation: ready to send, or needs changes."
    )

    return "\n".join(report)


# ---------------------------------------------------------------------------
# Tool: cancel_signature_request
# ---------------------------------------------------------------------------


@mcp.tool()
def cancel_signature_request(
    signature_request_id: Annotated[str, "The signature request ID to cancel"],
) -> str:
    """Cancel an incomplete signature request. Only works if no signer has completed signing."""
    from dropbox_sign import ApiClient, ApiException, Configuration, api

    api_key = _get_api_key()
    configuration = Configuration(username=api_key)

    try:
        with ApiClient(configuration) as api_client:
            sig_api = api.SignatureRequestApi(api_client)
            sig_api.signature_request_cancel(
                signature_request_id=signature_request_id,
            )
    except ApiException as exc:
        return _format_api_error(exc)

    return (
        f"Signature request {signature_request_id} has been cancelled.\n"
        "Note: cancelled requests still count against your signature quota."
    )


# ---------------------------------------------------------------------------
# Tool: analyze_document
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_document(
    file_path: Annotated[str, "Absolute path to the PDF file to analyze"],
) -> str:
    """Extract text with coordinates from a PDF for intelligent field placement.

    Returns two sections:
    1. Text layout -- lines of text with page, x, y positions
    2. Suggested form fields -- auto-detected blanks with inferred types,
       ready to pass to send_for_signature's form_fields parameter

    The LLM should review the suggested fields and adjust signer assignments
    or types before sending.
    """
    import json

    import pdfplumber

    if not os.path.isfile(file_path):
        return f"Error: file not found at {file_path}"

    output_lines: list[str] = []
    all_suggested_fields: list[dict] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            width = round(page.width, 1)
            height = round(page.height, 1)
            output_lines.append(
                f"=== Page {page_num} (width={width}, height={height}) ==="
            )

            words = page.extract_words(
                keep_blank_chars=True,
                x_tolerance=3,
                y_tolerance=3,
            )

            if not words:
                output_lines.append("  (no text found on this page)")
                output_lines.append("")
                continue

            lines: list[dict] = []
            current_line_top: float | None = None
            current_line_words: list[dict] = []
            tolerance = 3

            for word in words:
                if current_line_top is None or abs(word["top"] - current_line_top) > tolerance:
                    if current_line_words:
                        lines.append(_build_line(current_line_words))
                    current_line_words = [word]
                    current_line_top = word["top"]
                else:
                    current_line_words.append(word)

            if current_line_words:
                lines.append(_build_line(current_line_words))

            for line in lines:
                output_lines.append(
                    f"  y={line['y']:6.1f}  x={line['x']:6.1f}..{line['x_end']:6.1f}  "
                    f'"{line["text"]}"'
                )

            output_lines.append("")

            detected = _detect_blank_fields(page, page_num, lines)
            all_suggested_fields.extend(detected)

    all_suggested_fields = _post_process_fields(all_suggested_fields)

    output_lines.append(
        "Use these coordinates with the form_fields parameter on send_for_signature. "
        "Field types: 'signature', 'date_signed', 'text', 'text-merge', 'initials'. "
        "Coordinates use 72 DPI; US Letter = 612x792."
    )

    if all_suggested_fields:
        output_lines.append("")
        output_lines.append("--- SUGGESTED FORM FIELDS ---")
        output_lines.append(
            "Each field has a fill_rule:\n"
            "  - 'required': sender MUST pre-fill before sending (via custom_fields)\n"
            "  - 'optional': sender MAY pre-fill, or leave for the signer\n"
            "  - 'signer': interactive field the signer completes (cannot be pre-filled)\n"
            "Fields marked 'text-merge' are body fields the sender fills. "
            "Review names, types, and signer assignments, then pass to "
            "send_for_signature."
        )
        output_lines.append("")
        output_lines.append(json.dumps(all_suggested_fields, indent=2))

    return "\n".join(output_lines) + _version_warning()


def _build_line(words: list[dict]) -> dict:
    """Combine a list of word dicts from pdfplumber into a single line record."""
    text = " ".join(w["text"] for w in words)
    x0 = min(w["x0"] for w in words)
    x1 = max(w["x1"] for w in words)
    top = min(w["top"] for w in words)
    return {"text": text, "x": round(x0, 1), "x_end": round(x1, 1), "y": round(top, 1)}


# ---------------------------------------------------------------------------
# Field detection helpers
# ---------------------------------------------------------------------------

_FIELD_HEIGHT = {
    "signature": 30,
    "date_signed": 16,
    "text": 16,
    "initials": 20,
}

_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["signature", "sign here", "sign below"], "signature"),
    (["date"], "date_signed"),
    (["initial"], "initials"),
]


def _infer_field_type(label: str, context: str = "") -> str:
    """Infer a Dropbox Sign field type from the label and surrounding text.

    The immediate label (e.g., "Date:") is checked first. Surrounding
    context (e.g., "entered into on the date of ___") is only used as a
    fallback when the label alone gives no specific type.
    """
    label_lower = label.lower()
    for keywords, field_type in _TYPE_KEYWORDS:
        if any(kw in label_lower for kw in keywords):
            return field_type

    if context:
        context_lower = context.lower()
        for keywords, field_type in _TYPE_KEYWORDS:
            if any(kw in context_lower for kw in keywords):
                return field_type

    return "text"


_SIGNER_PATTERNS: list[tuple[list[str], int]] = [
    (["disclosing party", "party disclosing", "party a", "sender", "company", "employer"], 0),
    (["receiving party", "party receiving", "party b", "recipient", "contractor", "employee"], 1),
]


def _assign_signer(current_signer: int, line_text: str) -> int:
    """Update signer index if the line contains a signer-section heading."""
    text_lower = line_text.lower()
    for patterns, signer_idx in _SIGNER_PATTERNS:
        if any(p in text_lower for p in patterns):
            return signer_idx
    return current_signer


def _get_label_for_run(
    run_x0: float, run_y: float, page_chars: list[dict], tolerance: float = 3,
) -> str:
    """Return the label text immediately to the LEFT of an underscore run.

    Uses character-level data so that multiple blanks on the same line
    each get the correct preceding label (e.g. "Name: ___ Date: ___").
    """
    left_chars = sorted(
        [
            c for c in page_chars
            if abs(c["top"] - run_y) <= tolerance
            and c["x1"] <= run_x0 + 2
            and c["text"] != "_"
        ],
        key=lambda c: c["x0"],
    )
    if not left_chars:
        return ""

    label_chars: list[dict] = []
    for i in range(len(left_chars) - 1, -1, -1):
        if label_chars and label_chars[0]["x0"] - left_chars[i]["x1"] > 30:
            break
        label_chars.insert(0, left_chars[i])

    return "".join(c["text"] for c in label_chars).strip()


def _get_right_context(
    run_x_end: float, run_y: float, page_chars: list[dict], tolerance: float = 3,
) -> str:
    """Return text immediately to the RIGHT of an underscore run."""
    right_chars = sorted(
        [
            c for c in page_chars
            if abs(c["top"] - run_y) <= tolerance
            and c["x0"] >= run_x_end - 2
            and c["text"] != "_"
        ],
        key=lambda c: c["x0"],
    )
    if not right_chars:
        return ""

    text_chars: list[dict] = []
    for c in right_chars:
        if text_chars and c["x0"] - text_chars[-1]["x1"] > 30:
            break
        text_chars.append(c)

    return "".join(c["text"] for c in text_chars).strip()


def _detect_blank_fields(
    page, page_num: int, text_lines: list[dict],
) -> list[dict]:
    """Scan a PDF page for fill-in fields and return detected field dicts.

    Detects two patterns:
    1. Underscore runs (______) with precise bounding boxes
    2. 'Label:' patterns (Name:, Phone:) with empty space after the colon
    """
    fields: list[dict] = []

    underscore_chars = [c for c in page.chars if c["text"] == "_"]
    if underscore_chars:
        underscore_chars.sort(key=lambda c: (c["top"], c["x0"]))

        y_groups: list[list[dict]] = []
        current_group: list[dict] = [underscore_chars[0]]
        for c in underscore_chars[1:]:
            if abs(c["top"] - current_group[0]["top"]) <= 3:
                current_group.append(c)
            else:
                y_groups.append(current_group)
                current_group = [c]
        y_groups.append(current_group)

        runs: list[dict] = []
        for group in y_groups:
            group.sort(key=lambda c: c["x0"])
            current_run = [group[0]]
            for c in group[1:]:
                if c["x0"] - current_run[-1]["x1"] > 10:
                    runs.append(_run_to_dict(current_run, page_num))
                    current_run = [c]
                else:
                    current_run.append(c)
            runs.append(_run_to_dict(current_run, page_num))

        current_signer = 0
        all_lines_sorted = sorted(text_lines, key=lambda l: l["y"])
        page_chars = page.chars

        for run in sorted(runs, key=lambda r: (r["page"], r["y"])):
            for line in all_lines_sorted:
                if line["y"] > run["y"] + 3:
                    break
                current_signer = _assign_signer(current_signer, line["text"])

            label = _get_label_for_run(run["x"], run["y"], page_chars)
            right_ctx = _get_right_context(
                run["x"] + run["width"], run["y"], page_chars,
            )

            current_line_text = ""
            next_line_text = ""
            prev_line_text = ""
            for li, line in enumerate(all_lines_sorted):
                if abs(line["y"] - run["y"]) <= 5:
                    current_line_text = line["text"]
                    if li + 1 < len(all_lines_sorted):
                        next_line_text = all_lines_sorted[li + 1]["text"]
                    if li > 0:
                        prev_line_text = all_lines_sorted[li - 1]["text"]
                    break

            context = ""
            if not label:
                context = " ".join(
                    p for p in [current_line_text, prev_line_text] if p
                )

            field_type = _infer_field_type(label, context)
            height = _FIELD_HEIGHT.get(field_type, 16)

            fields.append({
                "type": field_type,
                "x": run["x"],
                "y": run["y"],
                "width": run["width"],
                "height": height,
                "page": run["page"],
                "signer": current_signer,
                "label": label or "(unlabeled)",
                "_right_context": right_ctx,
                "_line_text": current_line_text,
                "_next_line_text": next_line_text,
                "_prev_line_text": prev_line_text,
            })

    existing_ys = {f["y"] for f in fields}
    colon_fields = _detect_colon_fields(page, page_num, text_lines, existing_ys)
    fields.extend(colon_fields)

    fields.sort(key=lambda f: (f["page"], f["y"], f["x"]))
    return fields


def _run_to_dict(chars: list[dict], page_num: int) -> dict:
    """Convert a list of contiguous underscore chars to a position dict."""
    x0 = chars[0]["x0"]
    x1 = chars[-1]["x1"]
    top = min(c["top"] for c in chars)
    return {
        "x": int(round(x0)),
        "y": int(round(top)),
        "width": int(round(x1 - x0)),
        "page": page_num,
    }


_COLON_FIELD_KEYWORDS = {
    "name", "title", "address", "city", "state", "zip", "zip code",
    "phone", "telephone", "fax", "email", "e-mail",
    "date", "company", "organization", "position", "department",
    "printed name", "typed name", "employer", "employee",
    "representative", "witness", "county", "country",
    "ssn", "social security", "ein", "tax id",
}

_MIN_EMPTY_SPACE = 100


def _detect_colon_fields(
    page, page_num: int, text_lines: list[dict], existing_field_ys: set[float],
) -> list[dict]:
    """Detect fill-in fields marked by 'Label:' with empty space (no underscores).

    Looks for short labels ending with ':' that match known fill-in keywords
    and have significant blank space to the right.
    """
    page_width = page.width
    right_margin = page_width - 40
    page_chars = page.chars
    fields: list[dict] = []

    current_signer = 0

    for line in sorted(text_lines, key=lambda l: l["y"]):
        current_signer = _assign_signer(current_signer, line["text"])
        text = line["text"].strip()

        if ":" not in text:
            continue

        colon_segments = _find_colon_labels(text, line, page_chars, right_margin)

        sorted_lines = sorted(text_lines, key=lambda l: l["y"])
        for label, field_x, field_y in colon_segments:
            if any(abs(field_y - y) <= 5 for y in existing_field_ys):
                continue

            field_type = _infer_field_type(label)
            height = _FIELD_HEIGHT.get(field_type, 16)
            field_width = int(right_margin - field_x)
            if field_width < _MIN_EMPTY_SPACE:
                continue

            next_line_text = ""
            for li, ln in enumerate(sorted_lines):
                if abs(ln["y"] - field_y) <= 5 and li + 1 < len(sorted_lines):
                    next_line_text = sorted_lines[li + 1]["text"]
                    break

            fields.append({
                "type": field_type,
                "x": int(round(field_x)),
                "y": int(round(field_y)),
                "width": min(field_width, 250),
                "height": height,
                "page": page_num,
                "signer": current_signer,
                "label": label,
                "_right_context": "",
                "_line_text": line["text"],
                "_next_line_text": next_line_text,
                "_prev_line_text": "",
            })

    return fields


def _find_colon_labels(
    line_text: str, line: dict, page_chars: list[dict], right_margin: float,
) -> list[tuple[str, float, float]]:
    """Find 'Label:' patterns in a line that likely represent fill-in fields.

    Returns list of (label, field_x, field_y) tuples.
    """
    results: list[tuple[str, float, float]] = []
    line_y = line["y"]

    chars_on_line = sorted(
        [c for c in page_chars if abs(c["top"] - line_y) <= 3],
        key=lambda c: c["x0"],
    )
    if not chars_on_line:
        return results

    colon_positions: list[int] = []
    for i, c in enumerate(chars_on_line):
        if c["text"] == ":":
            colon_positions.append(i)

    for colon_idx in colon_positions:
        colon_char = chars_on_line[colon_idx]
        colon_x1 = colon_char["x1"]

        label_chars_before = chars_on_line[:colon_idx + 1]
        label_text = "".join(c["text"] for c in label_chars_before).strip()

        last_colon = label_text.rfind(":", 0, len(label_text) - 1)
        if last_colon >= 0:
            label_text = label_text[last_colon + 1:].strip() + ":"

        label_text = label_text.rstrip(":")

        if not _is_fill_in_label(label_text):
            continue

        text_after = [
            c for c in chars_on_line[colon_idx + 1:]
            if c["text"].strip() and c["text"] != "_"
        ]
        if text_after:
            next_text_x = text_after[0]["x0"]
            empty_gap = next_text_x - colon_x1
        else:
            empty_gap = right_margin - colon_x1

        if empty_gap >= _MIN_EMPTY_SPACE:
            results.append((label_text, colon_x1 + 5, line_y))

    return results


def _is_fill_in_label(label: str) -> bool:
    """Check if a label matches known fill-in field keywords.

    Only matches short labels (<=4 words) to avoid false positives on
    section headers like 'If to Company:' or 'With a copy to:'.
    """
    label_lower = label.lower().strip()
    words = label_lower.split()
    if len(words) > 4:
        return False
    if label_lower in _COLON_FIELD_KEYWORDS:
        return True
    for keyword in _COLON_FIELD_KEYWORDS:
        kw_words = keyword.split()
        if len(kw_words) == 1:
            if words and words[0] == keyword:
                return True
        elif keyword in label_lower:
            return True
    return False


_HEREINAFTER_RE = re.compile(
    r'hereinafter\s+["\u201c\']+(\w[\w\s]*?\w?)["\u201d\']+', re.IGNORECASE,
)

_PARTY_LABEL_RE = re.compile(
    r"\[("
    r"CLIENT|ATTORNEY|BUYER|SELLER|LANDLORD|TENANT|EMPLOYER|EMPLOYEE"
    r"|LICENSOR|LICENSEE|COMPANY|CONSULTANT|CONTRACTOR|VENDOR|PROVIDER"
    r"|LENDER|BORROWER|LESSOR|LESSEE|PARTY\s*[AB12]"
    r")\]",
    re.IGNORECASE,
)

_CONTEXT_NAME_PATTERNS: list[tuple[list[str], str]] = [
    (["concerning", "regarding", "relating to", "in the matter of", "re "], "Legal Matter"),
    (["fee of", "fee amount", "compensation amount", "salary of"], "Fee Amount"),
    (["paid as follows", "payment schedule", "payment terms"], "Payment Terms"),
    (["effective date", "commencement date", "start date"], "Effective Date"),
    (["expiration date", "end date", "termination date"], "End Date"),
    (["security deposit"], "Security Deposit"),
    (["monthly rent", "rent of", "rent amount"], "Rent Amount"),
]

_OPTIONAL_NAME_KEYWORDS = {"name", "address", "city", "state", "zip", "phone", "email", "title"}


def _find_party_from_context(line_text: str, next_line_text: str) -> str:
    """Find a party label from bracketed tags like [CLIENT] or [ATTORNEY]."""
    for text in [line_text, next_line_text]:
        m = _PARTY_LABEL_RE.search(text)
        if m:
            return m.group(1).strip().title()
    return ""


def _generate_field_name(
    field: dict, prev_name: str, field_idx: int,
) -> str:
    """Generate a descriptive, unique field name from field context."""
    field_type = field["type"]
    label = field.get("label", "")
    right_ctx = field.get("_right_context", "")
    line_text = field.get("_line_text", "")
    next_line = field.get("_next_line_text", "")
    prev_line = field.get("_prev_line_text", "")

    if field_type in ("signature", "date_signed", "initials"):
        party = _find_party_from_context(line_text, next_line)
        type_label = {
            "signature": "Signature",
            "date_signed": "Date Signed",
            "initials": "Initials",
        }[field_type]
        if party:
            return f"{party} {type_label}"
        return type_label

    m = _HEREINAFTER_RE.search(f"{right_ctx} {line_text}")
    if m:
        return f"{m.group(1).strip().title()} Name"

    if label and label != "(unlabeled)":
        label_lower = label.lower().strip()
        if "undersigned" in label_lower:
            m2 = _HEREINAFTER_RE.search(right_ctx)
            if m2:
                return f"{m2.group(1).strip().title()} Name"
            return "Signatory Name"
        if "$" in label or "($" in label:
            return "Fee Amount ($)"
        if label_lower.rstrip(":") == "date":
            party = _find_party_from_context(line_text, next_line)
            return f"{party} Date Signed" if party else "Date Signed"
        for patterns, name in _CONTEXT_NAME_PATTERNS:
            if any(kw in label_lower for kw in patterns):
                return name
        clean = label.rstrip(":").strip()
        if clean:
            return clean.title()

    right_lower = right_ctx.lower()
    if "$" in right_lower or "($" in right_lower:
        return "Fee Amount"

    if prev_line:
        prev_lower = prev_line.lower()
        for patterns, name in _CONTEXT_NAME_PATTERNS:
            if any(kw in prev_lower for kw in patterns):
                return name

    for patterns, name in _CONTEXT_NAME_PATTERNS:
        if any(kw in right_lower for kw in patterns):
            return name

    line_lower = line_text.lower()
    for patterns, name in _CONTEXT_NAME_PATTERNS:
        if any(kw in line_lower for kw in patterns):
            return name

    if prev_name:
        # Strip any existing ", Line N" suffix to get the base name
        base = re.sub(r",\s*Line\s+\d+$", "", prev_name).strip()
        return base

    return f"Field {field_idx + 1}"


def _classify_fill_rule(field: dict) -> str:
    """Classify how a field should be filled: required, optional, or signer."""
    if field["type"] in ("signature", "date_signed", "initials"):
        return "signer"
    if field["type"] != "text-merge":
        return "signer"
    name_lower = field.get("label", "").lower()
    if any(kw in name_lower for kw in _OPTIONAL_NAME_KEYWORDS):
        return "optional"
    return "required"


def _post_process_fields(fields: list[dict]) -> list[dict]:
    """Post-process detected fields: classify body vs sig block, fix types
    and signers, generate descriptive names, assign fill rules."""
    sig_types = {"signature", "date_signed", "initials"}
    sig_fields = [f for f in fields if f["type"] in sig_types]

    first_sig = None
    if sig_fields:
        first_sig = min(sig_fields, key=lambda f: (f["page"], f["y"]))

    # --- 1. Reclassify body text fields as text-merge ---
    if first_sig:
        for f in fields:
            if f["type"] != "text":
                continue
            is_before = (
                f["page"] < first_sig["page"]
                or (f["page"] == first_sig["page"]
                    and f["y"] < first_sig["y"] - 20)
            )
            if is_before:
                f["type"] = "text-merge"

    # --- 2. Fix wide unlabeled blanks in sig blocks → signature ---
    if first_sig:
        for f in fields:
            if f["type"] != "date_signed" or f["width"] <= 150:
                continue
            if f.get("label", "") not in ("(unlabeled)", ""):
                continue
            is_in_block = not (
                f["page"] < first_sig["page"]
                or (f["page"] == first_sig["page"]
                    and f["y"] < first_sig["y"] - 20)
            )
            if is_in_block:
                f["type"] = "signature"
                f["height"] = _FIELD_HEIGHT.get("signature", 30)

    # --- 3. Fix signer assignment in signature blocks ---
    block_fields = [f for f in fields if f["type"] in sig_types]
    party_order: list[str] = []
    for f in block_fields:
        party = _find_party_from_context(
            f.get("_line_text", ""), f.get("_next_line_text", ""),
        )
        if party and party not in party_order:
            party_order.append(party)
    party_to_signer = {p: i for i, p in enumerate(party_order)}
    for f in block_fields:
        party = _find_party_from_context(
            f.get("_line_text", ""), f.get("_next_line_text", ""),
        )
        if party in party_to_signer:
            f["signer"] = party_to_signer[party]

    # --- 4. Generate descriptive names with "Line N" for multi-line groups ---
    prev_name = ""
    base_name_counts: dict[str, int] = {}
    used_slugs: set[str] = set()
    for idx, f in enumerate(fields):
        base = _generate_field_name(f, prev_name, idx)
        base_name_counts[base] = base_name_counts.get(base, 0) + 1
        count = base_name_counts[base]
        if count == 1:
            display = base
        else:
            # Retroactively upgrade the first occurrence to "Line 1" on second hit
            if count == 2:
                for earlier in fields[:idx]:
                    if earlier.get("label") == base:
                        earlier["label"] = f"{base}, Line 1"
                        if earlier.get("name"):
                            slug1 = re.sub(r"[^a-z0-9]+", "_", f"{base}, Line 1".lower()).strip("_")
                            used_slugs.discard(earlier["name"])
                            earlier["name"] = slug1
                            used_slugs.add(slug1)
                        break
            display = f"{base}, Line {count}"

        f["label"] = display
        if f["type"] == "text-merge":
            slug = re.sub(r"[^a-z0-9]+", "_", display.lower()).strip("_")
            slug = slug or f"field_{idx}"
            orig_slug = slug
            scnt = 2
            while slug in used_slugs:
                slug = f"{orig_slug}_{scnt}"
                scnt += 1
            used_slugs.add(slug)
            f["name"] = slug
        prev_name = display

    # --- 5. Assign fill rules ---
    for f in fields:
        f["fill_rule"] = _classify_fill_rule(f)

    # --- 6. Strip internal context keys ---
    for f in fields:
        for key in ("_right_context", "_line_text", "_next_line_text", "_prev_line_text"):
            f.pop(key, None)

    return fields


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
