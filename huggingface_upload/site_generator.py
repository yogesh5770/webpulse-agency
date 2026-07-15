"""Generate a premium single-file website for a business using Opus 4.x, and
store its files in the DATABASE (the source of truth) so IDE edits persist
across restarts.

Design goal: TOP-LEVEL UI/UX with the FEWEST tokens -- a compact, opinionated
design system in the system prompt, one self-contained index.html per site.
"""
import json

from agent_router import chat_text
from leads_places import photo_url
import site_store

_SYSTEM = """You are a senior web designer. Output ONE complete, valid,
self-contained index.html (inline CSS + vanilla JS, no external build).
Design system (always apply):
- Modern, elegant, conversion-focused landing page.
- Google Fonts via <link>; tasteful type scale; generous whitespace.
- A cohesive color palette derived from the business type.
- Sections: sticky nav, hero (headline + CTA), about, services,
  gallery (use provided image URLs), testimonials-style trust, contact
  with phone + address + map link, footer.
- Subtle scroll-reveal animations (IntersectionObserver) and smooth
  hover states. Fully responsive (mobile-first). Accessible: semantic
  tags, alt text, good contrast, keyboard focus. SEO: <title>, meta
  description, one <h1>.
Return ONLY the HTML document. No markdown fences, no commentary."""


def _strip_fences(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def generate_site(lead: dict) -> str:
    """Generate the site and store its files in the DB. Returns a marker
    string ("db://<place_id>") used as the lead's site_dir."""
    details = json.loads(lead.get("details_json") or "{}")
    photo_refs = json.loads(lead.get("photos_json") or "[]")
    images = [photo_url(ref) for ref in photo_refs]

    facts = {
        "name": lead.get("name"),
        "category": lead.get("category"),
        "phone": lead.get("phone"),
        "address": lead.get("address"),
        "hours": details.get("hours", []),
        "rating": details.get("rating"),
        "images": images,
    }
    user_prompt = (
        "Build the website for this business. Use ONLY these facts; "
        "invent nothing false. Use the image URLs as-is in the gallery.\n"
        + json.dumps(facts, ensure_ascii=False)
    )

    html = _strip_fences(
        chat_text(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=16000,
        )
    )
    if "<html" not in html.lower():
        raise RuntimeError("Model did not return an HTML document.")

    place_id = lead["place_id"]
    lead_json = json.dumps(
        {
            "place_id": place_id,
            "name": lead.get("name"),
            "category": lead.get("category"),
            "phone": lead.get("phone"),
            "address": lead.get("address"),
            "images": images,
            "details": details,
        },
        ensure_ascii=False,
        indent=2,
    )

    # Store the whole "folder" in the DB.
    site_store.create_site(place_id, {"index.html": html, "lead.json": lead_json})
    return f"db://{place_id}"
