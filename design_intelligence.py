"""Design Intelligence — the memory that LEARNS, not just remembers.

Every finished site is recorded as three linked DNAs:
  * Business DNA — industry, positioning, city, audience, goal.
  * Design DNA   — the design tokens (the visual choices actually made).
  * Website DNA  — the outcome scores (ui/ux/seo/perf/a11y/overall) plus the
                   critic feedback and the edits the Refiner/user made.

Over many sites this lets us ask, per industry, "which token choices tend to
score well?" and softly bias new designs toward them.

TWO honest guardrails baked in, because this is the dangerous part:
  1. SIGNAL HONESTY. Today the only score we have is our own Critic (an LLM).
     Learning from self-assigned labels can amplify the critic's biases. So the
     learned prior is a SOFT nudge, requires a MIN_SAMPLES floor before it
     trusts anything, and every record carries `signal_source` so real
     conversion/analytics data can replace critic scores later as ground truth.
  2. IT NEVER OVERRIDES DIVERSITY. The prior only reports what has worked; the
     Diversity Engine still gets the final say on divergence. A prior is a hint,
     never a law — otherwise every bakery converges to one look.

Deliberately ONE module, not a ten-file package: the dataset starts at zero rows
and premature abstraction would just rot. Split when it earns the complexity.
"""
from __future__ import annotations

import json
import logging
import time

import design_tokens

logger = logging.getLogger(__name__)

STORE_PATH = "design_intelligence.jsonl"

# Don't trust a learned preference until we've seen at least this many sites for
# an industry. Below this, the prior stays silent rather than overfitting to one
# or two lucky (or biased) samples.
MIN_SAMPLES = 8

# The tokens worth learning a per-industry preference over (the visible ones).
LEARNABLE = ["hero", "grid", "cards", "motion", "radius", "image_style", "type_scale"]


def record(business: dict, brief: dict, artifacts: dict,
           signal_source: str = "critic") -> dict:
    """Build and persist one intelligence record for a finished site.

    signal_source: where the scores came from — "critic" (LLM, biased) today,
    "analytics" (real user data) once that's wired. Kept explicit so we can
    later learn only from trustworthy signal."""
    review = artifacts.get("review", {}) or {}
    scores = review.get("scores", {}) or {}

    rec = {
        "id": f"{(business.get('category') or 'site').lower().replace(' ', '_')}_{int(time.time()*1000)}",
        "ts": int(time.time()),
        "signal_source": signal_source,
        "business_dna": {
            "industry": (business.get("category") or "").lower(),
            "positioning": brief.get("positioning", ""),
            "city": business.get("city", ""),
            "audience": brief.get("audience", ""),
        },
        "design_dna": design_tokens.normalize(brief.get("design_tokens")),
        "website_dna": {
            "overall": artifacts.get("final_score", review.get("overall_score", 0)),
            "scores": scores,
            "published_ready": artifacts.get("published_ready", False),
        },
        "critic_feedback": review.get("weak_sections", []),
        "score_history": artifacts.get("score_history", []),
        "diversity": artifacts.get("diversity", {}),
        "quality_gates": artifacts.get("quality_gates", {}),
        "self_review": artifacts.get("self_review", {}),
    }
    _append(rec)
    return rec


def _append(rec: dict) -> None:
    try:
        with open(STORE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not persist design intelligence record: %s", e)


def _load() -> list[dict]:
    out = []
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read design intelligence store: %s", e)
    return out


def recent_fingerprints(industry: str = "", limit: int = 12) -> list[dict]:
    """Recent design token dicts (newest first), optionally filtered by industry.
    Feeds directly into the Diversity Engine's `recent_designs`."""
    rows = _load()
    if industry:
        rows = [r for r in rows if r.get("business_dna", {}).get("industry") == industry.lower()]
    rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return [{"design_tokens": r.get("design_dna", {})} for r in rows[:limit]]


def learned_prior(industry: str, trusted_only: bool = False) -> dict:
    """A SOFT prior: per learnable token, the value that has scored best on
    average for this industry — but only once we have MIN_SAMPLES sites.

    Returns {} when there isn't enough trustworthy data yet, which is the
    correct, honest answer early on. `trusted_only` restricts learning to
    records whose signal_source is real analytics (use once that exists).

    The result is advisory. The caller (and the Diversity Engine) decides how
    much weight to give it; it never forces a choice."""
    rows = [r for r in _load()
            if r.get("business_dna", {}).get("industry") == (industry or "").lower()]
    if trusted_only:
        rows = [r for r in rows if r.get("signal_source") == "analytics"]

    if len(rows) < MIN_SAMPLES:
        return {}  # not enough signal — stay silent rather than overfit

    prior: dict[str, dict] = {}
    for tok in LEARNABLE:
        agg: dict[str, list[float]] = {}
        for r in rows:
            val = r.get("design_dna", {}).get(tok)
            score = r.get("website_dna", {}).get("overall", 0) or 0
            if val:
                agg.setdefault(val, []).append(score)
        # Best average value, but require >=2 samples for that value too.
        best = None
        best_avg = -1.0
        for val, ss in agg.items():
            if len(ss) >= 2:
                avg = sum(ss) / len(ss)
                if avg > best_avg:
                    best_avg, best = avg, val
        if best is not None:
            prior[tok] = {"value": best, "avg_score": round(best_avg, 1), "n": len(agg[best])}
    return prior


def prior_hint(industry: str) -> str:
    """Render the learned prior as a gentle, clearly-labelled suggestion for the
    Designer. Empty string when there's not enough data — no hollow advice."""
    prior = learned_prior(industry)
    if not prior:
        return ""
    bits = [f"{tok}={p['value']} (avg {p['avg_score']}, n={p['n']})" for tok, p in prior.items()]
    joined = "; ".join(bits)
    return (
        f"LEARNED PRIOR for {industry} (soft guidance from past sites, NOT a rule — "
        f"the diversity push below overrides it): token choices that have scored "
        f"well on average are {joined}. Treat as a gentle nudge, not a template."
    )
