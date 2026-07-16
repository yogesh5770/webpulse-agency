"""Diversity Engine — make each new site MEANINGFULLY different from recent ones,
BEFORE it is designed.

A Similarity Engine asks "are these the same?" after the fact and rejects
duplicates. That's reactive and wasteful — you can burn a whole design pass only
to throw it away. The Diversity Engine flips it: it looks at what the last few
sites in this category actually did (their token fingerprints), summarizes the
patterns to avoid, and hands the Designer an explicit "don't repeat this, invent
another suitable approach" instruction up front.

It leans on machinery that already exists: the Designer's `avoid_hint` parameter
and `design_tokens.similarity()`. This module just turns recent history into a
sharp divergence instruction, and can still flag a fresh design as too close as
a backstop.
"""
import logging

import design_tokens

logger = logging.getLogger(__name__)

# Tokens whose repetition is most visible to a human eye — worth calling out
# explicitly when recent sites clustered on the same value.
SALIENT = ["hero", "grid", "cards", "motion", "radius", "image_style", "type_scale"]

# If a fresh design shares more than this fraction of tokens with any recent
# one, treat it as too close and worth a redesign nudge.
TOO_SIMILAR = 0.75


def _recent_fingerprints(recent_designs: list[dict]) -> list[dict]:
    """Pull normalized token fingerprints out of stored design records.
    Records may store tokens under 'design_tokens' or be a token dict directly."""
    out = []
    for d in recent_designs or []:
        tokens = d.get("design_tokens") if isinstance(d, dict) else None
        if not tokens and isinstance(d, dict):
            # A record that IS the token dict (has known token keys).
            if any(k in d for k in design_tokens.VOCAB):
                tokens = d
        if tokens:
            out.append(design_tokens.normalize(tokens))
    return out


def divergence_hint(recent_designs: list[dict], category: str = "") -> str:
    """Build an instruction telling the Designer how to diverge from recent work.
    Returns "" when there's no meaningful history to diverge from."""
    fps = _recent_fingerprints(recent_designs)
    if not fps:
        return ""

    # Find, per salient token, the values that recent sites clustered on.
    overused: list[str] = []
    for tok in SALIENT:
        seen = [f.get(tok) for f in fps if f.get(tok)]
        for val in set(seen):
            if seen.count(val) >= max(2, len(fps) // 2):  # a real cluster
                overused.append(f"{tok}={val}")

    cat = f" {category}" if category else ""
    if overused:
        return (
            f"Recent{cat} sites clustered on: {', '.join(overused)}. "
            "Do NOT repeat those choices. Invent a different but equally suitable "
            "premium approach — change the hero archetype, grid, and motion "
            "personality so this site reads as its own design."
        )
    return (
        f"Several recent{cat} sites exist. Make deliberately different token "
        "choices (hero, grid, cards, motion) so this one stands apart."
    )


def genome_similarity(g1: dict, g2: dict) -> float:
    """Compare two Style Genomes and return a similarity score between 0.0 and 1.0."""
    if not g1 or not g2:
        return 0.0
    keys = ["visual_style", "layout_family", "motion_family", "typography_family", "brand_feeling"]
    matches = sum(1 for k in keys if g1.get(k) == g2.get(k))
    return matches / len(keys)


def is_too_similar(new_tokens: dict, recent_designs: list[dict], new_brief: dict = None) -> tuple[bool, float]:
    """Backstop check AFTER a design is made: is it too close to any recent site?
    Returns (too_similar, worst_similarity_score)."""
    fps = _recent_fingerprints(recent_designs)
    worst = 0.0
    for fp in fps:
        s = design_tokens.similarity(new_tokens, fp)
        worst = max(worst, s)
        
    # Check Style Genome similarity
    if new_brief and "style_genome" in new_brief:
        new_genome = new_brief["style_genome"]
        for past in recent_designs or []:
            past_genome = None
            if isinstance(past, dict):
                past_genome = past.get("style_genome") or past.get("design_brief", {}).get("style_genome")
            if past_genome:
                sim = genome_similarity(new_genome, past_genome)
                if sim >= 0.8:
                    return True, sim
                    
    return worst > TOO_SIMILAR, round(worst, 3)
