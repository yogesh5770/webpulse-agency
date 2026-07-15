"""Generate a premium website for a business using a multi-agent pipeline
and store its files in the DATABASE (the source of truth) so IDE edits persist.

Uses specialized agents to perform:
1. Business Analysis (Business Analyzer Agent)
2. Brand & Theme Planning (Brand Designer Agent)
3. Copywriting & Section Planning (UI/UX Writer Agent)
4. Frontend Coding (Frontend Builder Agent)
5. SEO & HTML Quality Check (SEO & QA Expert Agent)
"""
import json
import logging
from agent_router import chat_text
from leads_places import photo_url
import site_store

logger = logging.getLogger(__name__)


def _strip_fences(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def generate_site(lead: dict) -> str:
    """Generate the site using a multi-agent workflow.
    Stores index.html, lead.json, and memory.json in the DB."""
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
        "reviews": details.get("reviews", []),
        "maps_url": details.get("maps_url", ""),
        "images": images,
    }

    facts_str = json.dumps(facts, ensure_ascii=False, indent=2)

    # --- Agent 1: Business Analyzer Agent ---
    prompt_analyzer = (
        "You are an elite Business Analyzer Agent.\n"
        "Analyze this business's details and reviews to understand its USP, key audience, "
        "and specific layout requirements based on its vertical (e.g. salons need price lists/services, "
        "restaurants need menu sections, clinics need practitioners/services/FAQs).\n\n"
        f"Business Details:\n{facts_str}\n\n"
        "Provide a concise JSON analysis describing:\n"
        "1. target_audience\n"
        "2. key_value_proposition\n"
        "3. vertical (salon, restaurant, clinic, or other)\n"
        "4. recommended_features (e.g., Booking Button, Structured Menu, Testimonials)\n"
        "Return ONLY the raw JSON object."
    )
    analysis_raw = _strip_fences(chat_text([{"role": "user", "content": prompt_analyzer}], temperature=0.2))
    try:
        analysis = json.loads(analysis_raw)
    except Exception:
        analysis = {
            "target_audience": "Local customers",
            "key_value_proposition": f"Premium service at {lead.get('name')}",
            "vertical": "other",
            "recommended_features": ["Services", "Gallery", "Reviews", "Map"]
        }

    # --- Agent 2: Brand Designer Agent ---
    prompt_brand = (
        "You are an elite Brand Designer Agent.\n"
        "Based on the business facts and analysis, choose a premium visual identity.\n"
        "Avoid generic basic colors (red/blue). Pick rich, harmonious HSL or Hex values (e.g. slate, gold, emerald, cream).\n"
        "Choose elegant Google Fonts (e.g., Playfair Display + Inter, or Outfit + Plus Jakarta Sans).\n\n"
        f"Business Details:\n{facts_str}\n"
        f"Business Analysis:\n{json.dumps(analysis, indent=2)}\n\n"
        "Provide a concise JSON output describing:\n"
        "1. colors (array of primary, secondary, background, text hex colors)\n"
        "2. fonts (array of Google Font names to load)\n"
        "3. theme (modern-dark, luxury-light, minimalist, vibrant-emerald, warm-amber, etc.)\n"
        "Return ONLY the raw JSON object."
    )
    brand_raw = _strip_fences(chat_text([{"role": "user", "content": prompt_brand}], temperature=0.2))
    try:
        brand = json.loads(brand_raw)
    except Exception:
        brand = {
            "colors": ["#0f172a", "#38bdf8", "#f8fafc", "#0f172a"],
            "fonts": ["Inter", "Outfit"],
            "theme": "modern"
        }

    # --- Agent 3: UI/UX Writer Agent ---
    prompt_writer = (
        "You are an elite UI/UX Copywriter Agent.\n"
        "Write engaging, conversion-focused copywriting content for the landing page.\n"
        "Use actual customer reviews to write testimonials and trust-builders.\n"
        "Structure the sections properly. For salons, write service lists. For restaurants, write a detailed culinary menu. For clinics, write treatment descriptions.\n\n"
        f"Business Facts:\n{facts_str}\n"
        f"Business Analysis:\n{json.dumps(analysis, indent=2)}\n"
        f"Brand Settings:\n{json.dumps(brand, indent=2)}\n\n"
        "Provide a JSON description of all copy sections, including headlines, subheadings, lists, and call-to-actions. Keep it structured. Return ONLY raw JSON."
    )
    copy_raw = _strip_fences(chat_text([{"role": "user", "content": prompt_writer}], temperature=0.5))

    # --- Agent 4: Frontend Builder Agent ---
    prompt_builder = (
        "You are a World-Class Frontend Architect & Product Designer. Output ONE complete, valid, self-contained index.html.\n"
        "Implement an ultra-premium visual design system (valued at 1 Lakh+ INR) using custom CSS variables (HSL structure) and vanilla JS.\n\n"
        "Strict Visual Design & UX Guidelines:\n"
        "1. Modern Layout & Spacing: Fluid typography using `clamp()`, generous and deliberate breathing room (vertical padding 8rem-10rem for sections), desktop max-width 1280px with side paddings.\n"
        "2. Luxury Aesthetics: Glassmorphism headers (backdrop-filter: blur(20px) border-bottom 1px solid rgba(255,255,255,0.08)), cards with ultra-soft double-layered box shadows, thin subtle borders, and smooth gradients.\n"
        "3. High-End Animations: CSS transitions with custom cubic-bezier timing (`all 0.5s cubic-bezier(0.16, 1, 0.3, 1)`) for hovers. Implement scroll-triggered reveal animations on sections using a performance-optimized IntersectionObserver.\n"
        "4. SVGs Only: Do NOT use broken emojis or FontAwesome/image-based icons. Code clean, inline styled SVGs with customized stroke widths for all visual elements (stars, phone, location, checkmarks).\n"
        "5. Conversion Focus: Eye-catching Hero with high-contrast dual buttons, sticky navigation containing active-link states, interactive Accordion/Faq or Tabs, structured Menu/Services grid, clean reviews carousel, and tap-to-call mobile links.\n\n"
        f"Business Facts:\n{facts_str}\n"
        f"Brand Settings:\n{json.dumps(brand, indent=2)}\n"
        f"Copy Content Structure:\n{copy_raw}\n\n"
        "Return ONLY the raw HTML document content. Do NOT wrap in markdown code blocks or add any commentary."
    )
    html = _strip_fences(chat_text([{"role": "user", "content": prompt_builder}], temperature=0.7, max_tokens=16000))

    if "<html" not in html.lower():
        raise RuntimeError("Frontend Builder did not produce a valid HTML document.")

    # --- Agent 5: SEO & QA Expert Agent ---
    prompt_qa = (
        "You are an elite SEO & QA Expert Agent.\n"
        "Examine this HTML file. Perform the following tasks:\n"
        "1. Check that it has a descriptive <title> matching the business and category.\n"
        "2. Ensure there is a meta description for search engines.\n"
        "3. Embed a JSON-LD LocalBusiness schema script inside the <head>.\n"
        "4. Validate accessibility: ensure color contrast is high, inputs have labels, images have meaningful alt attributes.\n"
        "5. Repair any formatting issues or unclosed HTML tags without altering the page layout or visual elements.\n\n"
        f"HTML Content:\n{html}\n\n"
        "Return ONLY the corrected, complete, valid HTML document. No markdown fences, no commentary."
    )
    final_html = _strip_fences(chat_text([{"role": "user", "content": prompt_qa}], temperature=0.3, max_tokens=16000))
    if "<html" not in final_html.lower():
        final_html = html

    # Build the Long-Term Memory (memory.json)
    memory = {
        "businessName": lead.get("name"),
        "industry": analysis.get("vertical", "other"),
        "theme": brand.get("theme", "modern"),
        "colors": brand.get("colors", []),
        "fonts": brand.get("fonts", []),
        "deployment": "Cloudflare Pages",
        "liveUrl": "",
        "framework": "HTML5 / Vanilla JS",
        "lastVersion": 1,
        "features": analysis.get("recommended_features", ["Gallery", "Services", "Map", "WhatsApp Button"])
    }

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

    # Store files in database (source of truth)
    site_store.create_site(
        place_id,
        {
            "index.html": final_html,
            "lead.json": lead_json,
            "memory.json": json.dumps(memory, indent=2, ensure_ascii=False)
        }
    )

    return f"db://{place_id}"
