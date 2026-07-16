"""AI Web Builder — Stage 2 of the free-form builder.

Given the design brief (from ai_web_designer) and the real scraped business
data + images, Claude writes the ACTUAL complete website as a single self-
contained HTML file: Tailwind (CDN) for styling, Google Fonts, and vanilla JS
for animation. No template slots — this is real, bespoke code per business.

Why single-file HTML+Tailwind: it deploys to Cloudflare Pages with no build
step (matches the current pipeline), stays ~50KB, and lets the model express
any layout it wants instead of filling a fixed skeleton.

The builder can also do TARGETED edits: given critic feedback, it rewrites only
the weak sections instead of regenerating the whole page.
"""
import json
import logging
import re

from agent_router import chat_text
import design_tokens
import build_constraints

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a Senior Frontend Architect at an award-winning studio. You hand-code beautiful, original marketing sites.
You are given a DESIGN BRIEF and real BUSINESS DATA. Build the complete website exactly as the brief specifies — do not fall back to a generic template.

Hard requirements:
- Output ONE complete, self-contained HTML5 document. No explanation, no markdown fences — just the HTML starting with <!DOCTYPE html>.
- Styling: Tailwind via <script src="https://cdn.tailwindcss.com"></script>, configured inline (tailwind.config) to use the brief's colors and fonts. You MAY add a <style> block for custom animations, gradients, and effects Tailwind can't express.
- Fonts: load the brief's Google Fonts via <link>.
- Motion (purposeful, never gimmicky) — vanilla JS + CSS only, no external JS libraries:
  * A hero entrance animation on load so the first impression feels alive.
  * Scroll-triggered fade/slide-in reveals per section via IntersectionObserver.
  * Hover states that feel responsive on buttons and cards: scale, shadow lift, color shift.
  * Smooth anchor-link scrolling for the nav.
  * PERFORMANCE: animate ONLY CSS transform and opacity (GPU-friendly). No layout-thrashing properties, no heavy libraries. Respect prefers-reduced-motion.
- Use their content AS the design: use provided image URLs directly (hotlink, don't invent files) as hero background / gallery / about imagery, with gradient overlays so text stays legible — never a plain stock block. Bake in exact name, phone, address, real reviews and rating count. Write believable, specific copy for this business and category (real service names and prices; realistic reviews if none provided).
- Layout must not look stock: avoid "hero -> 3 boxes -> footer". Use asymmetric grids, overlapping image/text blocks, and a floating stats bar (rating / years / jobs done) where it fits.
- Accessibility: semantic tags (header/nav/main/section/footer), alt text on every image, sufficient contrast, visible keyboard focus states, aria labels where needed.
- Conversion (local business): implement the brief's CTA strategy. Include a floating, always-visible "Call Now" (tel:) and WhatsApp (https://wa.me/<digits-only-phone>, prefilled message) button — high-converting for local searches. A sticky action bar that appears on scroll works well.
- Mobile-FIRST: design for phones first (tap targets >=44px, phone-tuned spacing and animations), then scale up. No horizontal scroll.
- SEO: proper <title>, meta description, meta keywords, and Open Graph tags; one <h1>; logical heading order.

Quality bar: this must look like a real designer built it for THIS business — memorable, polished, and original. Deliver the signature element and motion concept from the brief. Return ONLY the HTML."""


def _clean_html(text: str) -> str:
    """Strip stray fences/prose and return from <!DOCTYPE or <html onward."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()
    # Cut anything before the doctype/html tag.
    m = re.search(r"(<!DOCTYPE html>|<html)", text, re.IGNORECASE)
    if m:
        text = text[m.start():]
    return text.strip()


def build_site(brief: dict, business: dict) -> str:
    """Write the full single-file website from the brief + business data."""
    payload = {
        "design_brief": brief,
        "business_data": business,
    }
    directives = design_tokens.build_directives(brief.get("design_tokens"))
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "Build the complete website now, following the brief precisely.\n\n"
            + directives + "\n\n"
            + build_constraints.constraints_block() + "\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    # Big token budget — a full page is large.
    raw = chat_text(prompt, temperature=0.6, max_tokens=8000)
    html = _clean_html(raw)
    if "<html" not in html.lower() or len(html) < 500:
        raise ValueError("Builder did not return a valid HTML document")
    return html


def revise_sections(html: str, brief: dict, business: dict, weak_sections: list) -> str:
    """Targeted improvement pass: rewrite ONLY the weak sections the critic
    flagged, preserving everything else. Mirrors how a dev fixes review notes."""
    fixes = "\n".join(
        f"- [{w.get('section','global')}] {w.get('problem','')} → FIX: {w.get('fix','')}"
        for w in (weak_sections or [])
    )
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nYou are now in REVISION mode. You are given the current full HTML and a list of specific problems. Return the COMPLETE improved HTML document. Change ONLY what the notes call for (and anything needed to make those fixes cohere). Keep the rest intact. Return ONLY the HTML."},
        {"role": "user", "content":
            "DESIGN BRIEF:\n" + json.dumps(brief, ensure_ascii=False)[:2500]
            + "\n\n" + design_tokens.build_directives(brief.get("design_tokens"))
            + "\n\nBUSINESS DATA:\n" + json.dumps(business, ensure_ascii=False)[:1500]
            + "\n\nCRITIC NOTES TO FIX:\n" + fixes
            + "\n\n--- CURRENT HTML START ---\n" + html
            + "\n--- CURRENT HTML END ---\n\nReturn the full revised HTML now."},
    ]
    raw = chat_text(prompt, temperature=0.5, max_tokens=8000)
    revised = _clean_html(raw)
    # If the revision came back broken, keep the previous version.
    if "<html" not in revised.lower() or len(revised) < 500:
        logger.warning("Revision returned invalid HTML; keeping previous version.")
        return html
    return revised
