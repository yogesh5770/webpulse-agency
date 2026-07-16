"""Design Reasoning — emit a human-readable DESIGN.md explaining WHY the site
looks the way it does.

Not shown to end users. It's the equivalent of a design team documenting its
decisions: invaluable for debugging, future edits, and making the system behave
like an accountable studio rather than a black box. It's nearly free because all
the reasoning already lives in the brief and tokens — we just render it.
"""
import json


def build_reasoning(brief: dict, business: dict, tokens: dict | None = None) -> str:
    """Render a DESIGN.md-style reasoning document from the brief + tokens."""
    b = brief or {}
    tokens = tokens or b.get("design_tokens") or {}
    name = business.get("name", "This business")
    cat = business.get("category", "local business")
    cs = b.get("color_system", {}) or {}
    tp = b.get("typography", {}) or {}

    def line(label: str, value) -> str:
        return f"## {label}\n\n{value}\n" if value else ""

    parts = [
        f"# Design Decisions — {name}\n",
        f"_Category: {cat}. This document explains the reasoning behind the design; it is internal, not shown to visitors._\n",
        line("Brand", f"{b.get('brand_personality','—')} — positioned as {b.get('positioning','—')}."),
        line("Audience", b.get("audience")),
        line("Art direction", b.get("art_direction")),
        line("Signature element", b.get("signature_element")),
        line("Color", f"{cs.get('rationale','')} (mode: {cs.get('mode','—')}, primary {cs.get('primary','—')}, accent {cs.get('accent','—')})."),
        line("Typography", f"{tp.get('heading_font','—')} for headings + {tp.get('body_font','—')} for body. {tp.get('rationale','')}"),
        line("Layout strategy", b.get("layout_strategy")),
        line("Motion", b.get("motion_concept")),
        line("Conversion", b.get("conversion_strategy")),
        line("Imagery", b.get("imagery_direction")),
    ]

    if tokens:
        tok_lines = "\n".join(f"- **{k}**: {v}" for k, v in tokens.items())
        parts.append(f"## Design tokens (the visual system)\n\n{tok_lines}\n")

    sections = b.get("sections") or []
    if sections:
        sec_lines = "\n".join(
            f"- **{s.get('name','?')}** — {s.get('goal','')} ({s.get('treatment','')})"
            for s in sections
        )
        parts.append(f"## Section flow & why\n\n{sec_lines}\n")

    return "\n".join(p for p in parts if p).strip() + "\n"
