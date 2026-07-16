"""Design Token System — the structured visual language every site is built from.

Instead of asking Claude to invent everything freehand each time, the designer
now commits to a compact set of DISCRETE design tokens (spacing, radius, shadow,
grid, hero style, nav, cards, buttons, motion, image style). The builder is then
FORCED to follow those tokens, so every component speaks one visual language —
this is how senior frontend teams work, and it's what makes a site feel cohesive
rather than assembled.

Discrete tokens have a second payoff: they give each site a comparable
"fingerprint", which the Similarity Engine uses to force divergence from recent
designs. That is why the vocabulary here is a fixed enum, not free text.
"""
from __future__ import annotations

# Controlled vocabulary. Each token maps to a small set of allowed values so the
# design space is combinatorial (thousands of combinations) yet every value is
# something the builder knows how to render consistently.
VOCAB: dict[str, list[str]] = {
    "spacing":     ["tight", "comfortable", "airy"],
    "radius":      ["sharp", "rounded", "pill", "soft-xl"],
    "shadow":      ["none", "flat", "soft", "soft-xl", "dramatic"],
    "grid":        ["editorial", "symmetric", "asymmetric", "broken", "magazine"],
    "hero":        ["split", "full-bleed", "centered", "diagonal", "overlap", "gallery-led"],
    "navigation":  ["floating", "sticky-bar", "minimal", "sidebar", "centered"],
    "cards":       ["glass", "solid", "outline", "elevated", "flat"],
    "buttons":     ["pill", "square", "rounded", "ghost", "underline"],
    "motion":      ["luxury", "energetic", "subtle", "playful", "editorial"],
    "image_style": ["rounded", "sharp", "circle", "duotone", "framed", "full-bleed"],
    "density":     ["minimal", "balanced", "rich"],
    "type_scale":  ["restrained", "bold-display", "oversized", "condensed"],
}

# Sensible defaults when the model omits or invalid-fills a token.
DEFAULTS: dict[str, str] = {
    "spacing": "comfortable", "radius": "rounded", "shadow": "soft",
    "grid": "editorial", "hero": "split", "navigation": "floating",
    "cards": "solid", "buttons": "pill", "motion": "subtle",
    "image_style": "rounded", "density": "balanced", "type_scale": "bold-display",
}


def schema_hint() -> str:
    """A compact, human-readable description of the allowed token values,
    injected into the designer prompt so Claude picks from the vocabulary."""
    lines = [f'  "{k}": one of {v}' for k, v in VOCAB.items()]
    return "{\n" + ",\n".join(lines) + "\n}"


def normalize(tokens: dict | None) -> dict:
    """Coerce a raw token dict to valid vocabulary values, filling defaults.
    Guarantees every key is present with a legal value, so the builder and the
    fingerprint never see a surprise."""
    tokens = tokens or {}
    clean: dict[str, str] = {}
    for key, allowed in VOCAB.items():
        val = str(tokens.get(key, "")).strip().lower()
        clean[key] = val if val in allowed else DEFAULTS[key]
    return clean


def fingerprint(tokens: dict) -> dict:
    """The comparable identity of a design — just the normalized tokens.
    Kept as its own function so the Similarity Engine has one obvious call site."""
    return normalize(tokens)


def similarity(a: dict, b: dict) -> float:
    """Fraction of tokens two designs share, 0.0–1.0. Used by the Similarity
    Engine to reject a new design that's too close to a recent one."""
    fa, fb = normalize(a), normalize(b)
    if not fa:
        return 0.0
    same = sum(1 for k in VOCAB if fa.get(k) == fb.get(k))
    return round(same / len(VOCAB), 3)


def build_directives(tokens: dict) -> str:
    """Turn tokens into explicit, imperative build instructions. The builder
    must obey these exactly so the whole page shares one visual language."""
    t = normalize(tokens)
    return (
        "DESIGN TOKENS — follow these EXACTLY for every component; they define "
        "the site's single visual language:\n"
        f"- spacing: {t['spacing']} — apply consistent rhythm, no ad-hoc padding.\n"
        f"- corner radius: {t['radius']} — use on ALL cards, buttons, images, inputs.\n"
        f"- shadow: {t['shadow']} — one elevation style throughout.\n"
        f"- grid: {t['grid']} — the layout system for every section.\n"
        f"- hero: {t['hero']} — the hero layout archetype.\n"
        f"- navigation: {t['navigation']} — the nav treatment.\n"
        f"- cards: {t['cards']} — every card uses this style.\n"
        f"- buttons: {t['buttons']} — every button/CTA uses this shape.\n"
        f"- motion: {t['motion']} — the personality of all animation.\n"
        f"- image style: {t['image_style']} — treat all photos this way.\n"
        f"- density: {t['density']} — overall information density.\n"
        f"- type scale: {t['type_scale']} — the headline/body scale character.\n"
        "Derive CSS variables from these tokens and reuse them everywhere — "
        "do not introduce one-off values that contradict the tokens."
    )
