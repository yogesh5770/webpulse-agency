"""AI Web Designer — Stage 1 of the free-form builder.

This is the "design before you build" step. Instead of picking from a fixed
menu of components/themes, Claude acts as a senior product designer and INVENTS
a bespoke design brief for THIS specific business: brand personality, a real
color system, type pairing, layout strategy, section flow, one signature visual
idea, and a motion concept.

The output is a structured brief (JSON) that Stage 2 (ai_web_builder) turns into
real code. Keeping design and build separate mirrors how a real studio works and
gives the critic loop a spec to check the build against.
"""
import json
import logging
import re

from agent_router import chat_text
import design_tokens

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a world-class Creative Director and Senior Product Designer whose sites win Awwwards.
You are briefing a build for ONE specific small business. You are NOT choosing from templates — you are inventing a visual identity that could only belong to this business.

Rules — make REAL design decisions, never defaults:
- AVOID the template tells: Bootstrap-blue, plain Inter everywhere, a centered hero, "hero -> 3 boxes -> footer". Also avoid the AI-generated cliches: warm cream (#F4F1EA) + serif + terracotta (#D97757); near-black bg + single acid-green accent; hairline-rule broadsheet. If your instinct lands on one of these, change it.
- Color: choose a distinct palette tied to THIS industry and vibe (not just blue/white). 4-6 named hex values with intent.
- Typography: pair a characterful DISPLAY face for headlines with a clean body face — real hierarchy through weight/width/spacing, not just bigger font-size. The type treatment is itself part of the design.
- Content IS the design driver: their real photos become the hero background / gallery / about imagery (with gradient overlays for legibility, never a plain stock block); real name, real reviews, real rating count, real address baked in so it never looks like a mockup.
- Layout must not look stock: mix asymmetric grids, overlapping image/text blocks, a testimonials treatment using their actual rating, a floating stats bar (rating / years / jobs done). Structure should encode something true, not decorate.
- The design must fit the business's audience, price point, and personality (a budget street barber and a luxury spa should look nothing alike).
- Spend boldness in ONE place: one memorable signature element, everything else quiet and disciplined.
- Mobile-first (most local searches are on phones), real accessibility, and clear conversion (the visitor must know what to do).

Return ONLY valid JSON, no prose, matching exactly this schema:
{
  "brand_personality": "3-6 adjectives capturing the vibe",
  "audience": "who visits this site and what they want",
  "positioning": "premium | mid-market | budget",
  "art_direction": "2-3 sentences describing the overall look & feel and the ONE signature visual idea",
  "color_system": {
    "background": "#hex",
    "surface": "#hex",
    "text": "#hex",
    "muted_text": "#hex",
    "primary": "#hex",
    "accent": "#hex",
    "gradient": "css gradient string or empty",
    "mode": "light | dark",
    "rationale": "why these colors fit this business"
  },
  "typography": {
    "heading_font": "Google Font name",
    "body_font": "Google Font name",
    "scale": "e.g. bold display headings, generous body",
    "rationale": "why this pairing"
  },
  "layout_strategy": "how the page should flow and why (what builds trust, where the eye lands first)",
  "sections": [
    { "name": "hero", "goal": "what this section must achieve", "treatment": "concrete visual/interaction description" }
  ],
  "signature_element": "the one thing that makes this site memorable (e.g. a diagonal split hero, floating product cards, an animated hand-drawn underline)",
  "motion_concept": "the motion personality (e.g. slow & elegant reveals for luxury; snappy & energetic for a gym) and specific animations to use",
  "conversion_strategy": "primary CTA, where it appears, sticky/floating behaviour, WhatsApp usage",
  "imagery_direction": "how to use the provided photos (crops, treatments, where)",
  "style_genome": {
    "visual_style": "Editorial Luxury | Brutalist Tech | Warm Organic | Minimal Clean | Industrial Bold",
    "layout_family": "Asymmetric Split Hero | Grid Masonry | Minimal Centered | Overlapping Split",
    "motion_family": "Staggered Elegant Fade | Spring Snap | Clean Static | Fluid Parallax",
    "typography_family": "Contrast Serif + Sans | Mono Space | Soft Round | Classic Editorial Serif",
    "brand_feeling": "Premium & Warm | Bold & Energetic | Calm & Trustworthy | Creative & Artistic"
  },
  "design_tokens": __TOKENS_SCHEMA__
}
Design 5-7 sections. Make choices a real designer would defend.

CRITICAL — design_tokens is the site's structured visual system. Pick ONE value per token from the allowed lists. Every component the builder makes will follow these tokens, so choose a combination that expresses this specific business and is internally coherent (e.g. luxury spa: airy spacing, soft-xl radius, luxury motion, glass cards; energetic gym: tight spacing, sharp radius, energetic motion, solid cards)."""

# Inject the token vocabulary into the schema placeholder at import time.
SYSTEM_PROMPT = SYSTEM_PROMPT.replace("__TOKENS_SCHEMA__", design_tokens.schema_hint())


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def design_brief(business: dict, avoid_hint: str = "") -> dict:
    """Produce a bespoke design brief for this business.

    business: {name, category, phone, address, images[], details{}, reviews[]}
    avoid_hint: optional instruction to diverge from recent designs (dedup).
    """
    user_payload = {
        "business": business,
        "instruction": (
            "Create the design brief. Make it unmistakably tailored to this business. "
            + (f"IMPORTANT — diverge strongly from past work: {avoid_hint}" if avoid_hint else "")
        ),
    }
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
    ]
    try:
        raw = chat_text(prompt, temperature=0.9, max_tokens=1600)
        brief = _extract_json(raw)
        if not brief.get("sections"):
            raise ValueError("brief missing sections")
        # Normalize the design tokens to the controlled vocabulary so the
        # builder and similarity engine always see valid, complete values.
        brief["design_tokens"] = design_tokens.normalize(brief.get("design_tokens"))
        return brief
    except Exception as e:  # noqa: BLE001
        logger.warning("Design brief generation failed (%s); using neutral fallback.", e)
        return _fallback_brief(business)


def _fallback_brief(business: dict) -> dict:
    name = business.get("name", "This Business")
    cat = (business.get("category") or "local business").lower()
    return {
        "brand_personality": "friendly, trustworthy, local, clean",
        "audience": f"nearby customers looking for a reliable {cat}",
        "positioning": "mid-market",
        "art_direction": f"A clean, modern single-page site for {name} that feels credible and approachable.",
        "color_system": {
            "background": "#0f1115", "surface": "#171a21", "text": "#f5f7fa",
            "muted_text": "#9aa4b2", "primary": "#4f8cff", "accent": "#22d3ee",
            "gradient": "linear-gradient(135deg,#4f8cff,#22d3ee)", "mode": "dark",
            "rationale": "Neutral, professional palette that reads as trustworthy.",
        },
        "typography": {
            "heading_font": "Sora", "body_font": "Inter",
            "scale": "bold display headings, comfortable body",
            "rationale": "Modern, legible pairing.",
        },
        "layout_strategy": "Lead with a strong hero and clear CTA, then build trust with services, gallery, reviews, and contact.",
        "sections": [
            {"name": "hero", "goal": "grab attention and state the offer", "treatment": "full-width hero with headline, subtext, primary CTA and a hero image with gradient overlay"},
            {"name": "services", "goal": "show what they offer", "treatment": "card grid with real items and prices"},
            {"name": "gallery", "goal": "show real work", "treatment": "responsive masonry of provided photos"},
            {"name": "reviews", "goal": "build trust", "treatment": "testimonial cards using real rating"},
            {"name": "contact", "goal": "drive the visit/booking", "treatment": "address, hours, map, WhatsApp button"},
        ],
        "signature_element": "a soft animated gradient glow behind the hero headline",
        "motion_concept": "subtle fade-and-rise reveals on scroll; gentle hover lifts on cards",
        "conversion_strategy": "primary CTA in hero + floating WhatsApp/Call button always visible",
        "imagery_direction": "use provided photos in the hero and gallery with rounded corners, gradient overlays, and subtle shadows",
        "design_tokens": design_tokens.normalize(None),
    }
