"""Website Critic AI — the strict, Awwwards-style judge at the heart of the
generate → critique → improve loop.

Two design rules that the OLD reviewer got wrong:
  1. The critic MUST see the actual rendered HTML, not just the brief. You
     cannot judge a website you never looked at.
  2. The critic MUST fail CLOSED. If the model errors or returns garbage, we
     return needs_improvement=True with a low score — never a silent pass.

It returns per-axis scores AND a list of weak sections with concrete fixes,
so the improvement pass can regenerate ONLY what's broken instead of redoing
the whole site.
"""
import json
import logging
import re

from agent_router import chat_text

logger = logging.getLogger(__name__)

# A site must clear this overall score (0-100) to be publishable.
PUBLISH_THRESHOLD = 88

AXES = [
    "originality", "visual_hierarchy", "typography", "spacing",
    "responsiveness", "animation", "accessibility", "conversion",
    "trust", "branding", "seo", "mobile_ux",
]

SYSTEM_PROMPT = """You are a jury member for the Awwwards Site of the Day. You are famously harsh.
You are reviewing the FULL HTML source of a small-business website that an AI just generated.

Judge the ACTUAL code and markup you are given — layout, hierarchy, copy, semantics, responsiveness signals, motion. Do not be generous. A generic template that "looks fine" is a 6/10, not a 9. Reserve 9-10 for work you would genuinely feature.

Score each axis from 0 to 100:
- originality: does this look designed for THIS business, or like a reused template? Penalize template tells (Bootstrap-blue, plain Inter, centered "hero -> 3 boxes -> footer") and AI cliches (cream+serif+terracotta, black+acid-green). Reward content-as-design: their real photos used as hero/gallery with overlays, real reviews/rating baked in, asymmetric or overlapping layout.
- visual_hierarchy: does the eye land in the right order?
- typography: type scale, pairing, rhythm, line length
- spacing: whitespace, grid discipline, breathing room
- responsiveness: are there real responsive patterns (clamp, grid, media/container queries, fluid units)?
- animation: is motion purposeful and tasteful (hero entrance, scroll reveals, responsive hover lifts, smooth anchor scroll) using GPU-friendly transform/opacity — or absent/gratuitous or performance-heavy? Penalize missing prefers-reduced-motion.
- accessibility: semantic tags, alt text, contrast, focus states, aria where needed
- conversion: is the primary CTA obvious and well-placed? is there a clear next step?
- trust: does it feel credible (reviews, real detail, polish)?
- branding: coherent identity — color, voice, imagery all agree
- seo: title, meta description, headings, structured data
- mobile_ux: tap targets, sticky/floating CTA, no horizontal scroll

Return ONLY valid JSON, no prose, matching exactly:
{
  "scores": { "originality": 0, "visual_hierarchy": 0, "typography": 0, "spacing": 0, "responsiveness": 0, "animation": 0, "accessibility": 0, "conversion": 0, "trust": 0, "branding": 0, "seo": 0, "mobile_ux": 0 },
  "overall_score": 0,
  "would_publish": false,
  "weak_sections": [
    { "section": "hero|about|services|gallery|reviews|contact|global", "problem": "what is wrong, specifically", "fix": "the concrete change to make" }
  ],
  "strengths": ["what genuinely works"]
}
overall_score is the mean of the twelve axis scores, rounded to an int.
weak_sections must be empty ONLY if every axis is strong. Be specific: name the section and the exact fix."""


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    """Be forgiving: models sometimes wrap JSON in stray text."""
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _fail_closed(reason: str) -> dict:
    """When we cannot trust the critic, we do NOT let the site pass."""
    logger.warning("Critic failing closed: %s", reason)
    return {
        "scores": {a: 0 for a in AXES},
        "overall_score": 0,
        "would_publish": False,
        "weak_sections": [{
            "section": "global",
            "problem": f"Critic could not evaluate the site ({reason}).",
            "fix": "Regenerate the site and re-run the critic.",
        }],
        "strengths": [],
        "needs_improvement": True,
        "critic_error": reason,
    }


def critique(html: str, business_dna: dict | None = None,
             design_dna: dict | None = None, gate_summary: str = "") -> dict:
    """Score the actual HTML. Returns a normalized critique dict that always
    contains overall_score, needs_improvement, weak_sections, and suggestions.

    gate_summary: one-line results from the deterministic quality gates
    (HTML/SEO/a11y/perf/mobile/motion/tokens). When provided, the critic treats
    the objective facts as settled and focuses its budget on subjective quality
    — emotion, hierarchy, storytelling, brand, conversion — instead of guessing
    at things the gates already measured."""
    if not html or len(html) < 200:
        return _fail_closed("empty or too-short HTML")

    # Token economy: the critic doesn't need every gallery <img> tag to judge
    # quality. Cap the HTML we send (structure lives near the top) to keep the
    # input small. ~14K chars is plenty to assess layout, hierarchy, and copy.
    snippet = html if len(html) <= 14000 else html[:14000] + "\n<!-- …truncated for review… -->"

    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "BUSINESS CONTEXT (for judging originality/branding fit):\n"
            + json.dumps({"business_dna": business_dna or {},
                          "design_dna": design_dna or {}}, ensure_ascii=False)[:2000]
            + (("\n\nOBJECTIVE QUALITY GATES (already measured deterministically — "
                "treat these as settled facts; do NOT re-litigate them. Spend your "
                "judgment on subjective quality: emotional impact, visual hierarchy, "
                "storytelling, brand expression, conversion flow):\n" + gate_summary)
               if gate_summary else "")
            + "\n\n--- WEBSITE HTML START ---\n" + snippet
            + "\n--- WEBSITE HTML END ---\n\nReturn the JSON verdict now."},
    ]

    try:
        raw = chat_text(prompt, temperature=0.2, max_tokens=900)
        data = _extract_json(raw)
    except Exception as e:  # noqa: BLE001 - we deliberately fail closed
        return _fail_closed(f"{type(e).__name__}: {e}")

    scores = data.get("scores") or {}
    # Recompute overall from axes so the model can't inflate it.
    valid = [int(scores[a]) for a in AXES if isinstance(scores.get(a), (int, float))]
    if not valid:
        return _fail_closed("critic returned no usable axis scores")
    overall = round(sum(valid) / len(valid))

    weak = data.get("weak_sections") or []
    # Normalize weak_sections to a list of dicts with the expected keys.
    norm_weak = []
    for w in weak:
        if isinstance(w, dict):
            norm_weak.append({
                "section": w.get("section", "global"),
                "problem": w.get("problem", ""),
                "fix": w.get("fix", ""),
            })
    needs_improvement = overall < PUBLISH_THRESHOLD or bool(norm_weak)

    return {
        "scores": {a: int(scores.get(a, 0)) for a in AXES},
        "overall_score": overall,
        "would_publish": bool(data.get("would_publish")) and not needs_improvement,
        "weak_sections": norm_weak,
        "strengths": data.get("strengths") or [],
        "needs_improvement": needs_improvement,
    }
