"""Visual Editor AI — the elevation pass that turns a GOOD site into an
EXCEPTIONAL one.

This is the piece that makes WebPulse behave like a senior design lead rather
than a code generator. The Builder produces a solid, on-brief site. The Visual
Editor then does what an experienced designer does before shipping: it looks at
the real rendered markup and asks, section by section, "can this be better?" —
then edits ONLY what it can genuinely improve, leaving the rest intact.

Design decisions:
  * ONE coherent pass, not many. A single reviewer holding the whole checklist
    (hero, spacing, cards, type, overlap, motion, mobile, conversion, UX
    friction) makes cohesive edits. Five separate AIs editing in isolation would
    undo each other and cost far more tokens. This is the deliberate collapse of
    the "UX AI / Motion AI / Layout AI" ideas into one intelligent pass.
  * It stays ON-SYSTEM. The elevation must obey the same design tokens, so the
    site keeps one visual language instead of drifting during polish.
  * It fails SAFE. If the edit comes back broken or shorter-than-plausible, we
    keep the original build — elevation must never make a site worse.
"""
import json
import logging

from agent_router import chat_text
from ai_web_builder import _clean_html
import design_tokens
import build_constraints

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a Senior Design Lead doing a final ELEVATION pass on a website that is already good. Your job is not to fix defects — it is to raise the ceiling, the way an experienced designer polishes work before it ships.

You are given the full HTML, the design tokens (the site's visual system), and the business context. Go through this checklist and make a change ONLY where you can genuinely improve the result:
- Hero: is it as striking as it could be? Stronger focal point, better use of the business's real imagery, more confident headline?
- Spacing & rhythm: is the whitespace intentional and consistent, or cramped/uneven anywhere?
- Cards & surfaces: right size, right elevation, right hierarchy?
- Typography: bolder/clearer hierarchy where it earns attention; better line-length and rhythm?
- Layout richness: would an overlap, an asymmetric break, or a floating stats element make a flat section more alive? (only where it serves the content)
- Motion: do interactions feel smooth and intentional (transform/opacity, 60fps, reduced-motion respected)? Remove anything decorative.
- Mobile: is the phone experience truly first-class (tap targets, spacing, one-column flow)?
- Conversion & UX friction: is the primary action always obvious? Any confusing flow, weak CTA, or trust gap to close?

Hard rules:
- Obey the design tokens exactly. Elevation must not break the site's single visual language.
- Edit surgically. Keep everything that already works; change only what you're improving.
- Never remove real business content (name, phone, address, reviews, images).
- Return the COMPLETE, valid HTML document. Return ONLY the HTML, no commentary."""


def elevate(html: str, brief: dict, business: dict) -> str:
    """Run one elevation pass. Returns improved HTML, or the original if the
    edit came back invalid (fail-safe — never ship something worse)."""
    if not html or len(html) < 500:
        return html

    directives = design_tokens.build_directives(brief.get("design_tokens"))
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "ELEVATE this website. Same tokens, same content — just make it better.\n\n"
            + directives
            + "\n\n" + build_constraints.constraints_block()
            + "\n\nDESIGN BRIEF (intent):\n" + json.dumps(brief, ensure_ascii=False)[:2000]
            + "\n\nBUSINESS DATA:\n" + json.dumps(business, ensure_ascii=False)[:1500]
            + "\n\n--- CURRENT HTML START ---\n" + html
            + "\n--- CURRENT HTML END ---\n\nReturn the full elevated HTML now."},
    ]
    try:
        raw = chat_text(prompt, temperature=0.5, max_tokens=8000)
    except Exception as e:  # noqa: BLE001
        logger.warning("Visual Editor call failed (%s); keeping original build.", e)
        return html

    elevated = _clean_html(raw)
    # Fail safe: an elevation that returns broken or implausibly short HTML is
    # discarded. We also guard against the model dropping most of the page.
    if "<html" not in elevated.lower() or len(elevated) < max(500, int(len(html) * 0.6)):
        logger.warning("Elevation returned invalid/short HTML; keeping original build.")
        return html
    logger.info("Visual Editor elevation applied (%d -> %d chars).", len(html), len(elevated))
    return elevated
