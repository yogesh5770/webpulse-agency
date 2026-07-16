"""SELF_REVIEW — after the gates and critic have run, the system writes an
honest reflection on the site it just built: what works, what's weak, why it
made the design decisions it did, and what it would improve next.

Why this exists: the critic scores; the gates measure; but neither explains the
*reasoning*. A self-review captures the "why" in the system's own words and
stores it alongside the record, so future builds (and humans auditing the
pipeline) can see not just what scored well but the thinking behind it. It is
grounded in the objective gate results and the critic's verdict, NOT invented —
the prompt hands it the facts and asks it to reflect, so it can't just
self-congratulate past what the gates actually found.
"""
from __future__ import annotations

import json
import logging

from ai_web_builder import chat_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the lead designer doing an honest post-mortem on a website you just built.
You are given the design brief, the objective quality-gate results, and the critic's verdict.
Reflect truthfully — do NOT inflate. If a gate flagged something, own it in Weaknesses.
Ground every point in the facts you were given; do not invent strengths the evidence doesn't support.

Return ONLY valid JSON matching exactly:
{
  "strengths": ["specific things that genuinely work, tied to evidence"],
  "weaknesses": ["honest gaps — include anything the gates or critic flagged"],
  "design_decisions": ["a decision AND the reason behind it (brand/audience/constraint)"],
  "future_improvements": ["concrete next steps to push this from good to exceptional"]
}
Be specific and concise. 2-5 items per list. No prose outside the JSON."""


def _facts(brief: dict, gates: dict, review: dict) -> str:
    return json.dumps({
        "positioning": brief.get("positioning"),
        "audience": brief.get("audience"),
        "art_direction": brief.get("art_direction"),
        "design_tokens": brief.get("design_tokens"),
        "gate_health": gates.get("health"),
        "gate_summary": gates.get("summary"),
        "critical_failed": gates.get("critical_failed"),
        "critic_overall": review.get("overall_score"),
        "critic_weak_sections": review.get("weak_sections"),
        "critic_strengths": review.get("strengths"),
    }, ensure_ascii=False)[:3000]


def generate(brief: dict, gates: dict, review: dict) -> dict:
    """Produce the structured self-review. Fails soft: on any error returns a
    minimal review derived from the facts we already have, so the pipeline never
    breaks just because the reflection step hiccuped."""
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content":
            "Reflect on this build. FACTS:\n" + _facts(brief, gates, review)
            + "\n\nReturn the JSON reflection now."},
    ]
    try:
        raw = chat_text(prompt, temperature=0.4, max_tokens=700)
        text = (raw or "").strip()
        if text.startswith("```"):
            import re
            text = re.sub(r"^```[a-zA-Z]*\n", "", text)
            text = re.sub(r"\n```$", "", text).strip()
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        logger.warning("self_review fell back: %s", e)
        return _fallback(gates, review)

    return {
        "strengths": data.get("strengths") or [],
        "weaknesses": data.get("weaknesses") or [],
        "design_decisions": data.get("design_decisions") or [],
        "future_improvements": data.get("future_improvements") or [],
    }


def _fallback(gates: dict, review: dict) -> dict:
    """Deterministic reflection from facts, used if the LLM step fails."""
    weak = [w.get("problem", "") if isinstance(w, dict) else str(w)
            for w in (review.get("weak_sections") or [])]
    crit = gates.get("critical_failed") or []
    return {
        "strengths": review.get("strengths") or [],
        "weaknesses": ([f"Critical gate failed: {', '.join(crit)}"] if crit else []) + weak,
        "design_decisions": [],
        "future_improvements": ["Re-run the improvement loop on the flagged sections."] if (weak or crit) else [],
    }


def to_markdown(sr: dict, site_name: str = "") -> str:
    """Render the self-review as the SELF_REVIEW.md the user sketched."""
    def block(title, items):
        if not items:
            return ""
        return f"## {title}\n\n" + "\n".join(f"- {i}" for i in items) + "\n\n"
    head = f"# SELF_REVIEW{': ' + site_name if site_name else ''}\n\n"
    return (head
            + block("Strengths", sr.get("strengths"))
            + block("Weaknesses", sr.get("weaknesses"))
            + block("Design Decisions", sr.get("design_decisions"))
            + block("Future Improvements", sr.get("future_improvements"))).strip() + "\n"
