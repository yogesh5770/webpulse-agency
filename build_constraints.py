"""Build Constraints — the hard, numeric rules every site is built inside.

Professional frontend developers don't design in a vacuum; they work inside a
spec: max widths, a spacing scale, motion durations, contrast and tap-target
minimums, image and performance budgets. This module makes those explicit and
injects them into the Builder and Refiner.

Deliberately NOT a "Constraint AI". Asking a model to police numeric rules is
unreliable and costs a round-trip. These are static rules stated up front (which
the model is good at following) and later checked by the deterministic quality
gates (which is where enforcement actually belongs). One source of truth.
"""

# The house rules. Tuned for fast, accessible, single-file marketing sites.
CONSTRAINTS: dict[str, str] = {
    "max_content_width": "1440px (content); full-bleed sections may exceed this",
    "hero_height": "min 80vh, max 100vh",
    "spacing_scale": "8px base scale (8/16/24/32/48/64/96) — no arbitrary values",
    "motion_duration": "150–600ms; ease-out for entrances, respect prefers-reduced-motion",
    "motion_props": "animate transform & opacity only (GPU); never animate layout properties",
    "contrast": "WCAG AA minimum (4.5:1 body text, 3:1 large text)",
    "tap_targets": "interactive elements >= 48x48px on mobile",
    "images": "use loading=\"lazy\" + width/height attributes to protect CLS; prefer WebP sources when available",
    "performance": "target LCP < 2.5s and CLS < 0.1 — keep the hero image lean, no blocking scripts",
    "fonts": "max 2 font families; preconnect to the font host",
    "responsiveness": "use fluid units (clamp/%, min/max) and CSS grid; no fixed pixel layouts that break < 380px",
}


def constraints_block() -> str:
    """Render the constraints as an imperative block for a build/refine prompt."""
    lines = [f"- {k.replace('_', ' ')}: {v}" for k, v in CONSTRAINTS.items()]
    return (
        "BUILD CONSTRAINTS — the site MUST be built inside these hard rules "
        "(they are checked automatically before publish):\n" + "\n".join(lines)
    )
