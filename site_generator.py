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
import site_assembler

logger = logging.getLogger(__name__)


def hex_to_hsl(hex_str: str) -> str:
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        return "215 90% 50%" # Fallback HSL
    try:
        r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        r, g, b = r/255.0, g/255.0, b/255.0
        mx, mn = max(r, g, b), min(r, g, b)
        diff = mx - mn
        h = 0
        if mx == mn: h = 0
        elif mx == r: h = (60 * ((g - b) / diff) + 360) % 360
        elif mx == g: h = (60 * ((r - b) / diff) + 120) % 360
        elif mx == b: h = (60 * ((r - g) / diff) + 240) % 360
        l = (mx + mn) / 2
        s = 0 if l == 0 or l == 1 else (mx - l) / min(l, 1 - l)
        return f"{int(h)} {int(s*100)}% {int(l*100)}%"
    except Exception:
        return "215 90% 50%"


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
        "Provide a JSON description of all copy sections. Return ONLY raw JSON matching this format:\n"
        "{\n"
        '  "hero_title": "Headline targeting the USP of the business",\n'
        '  "hero_subtitle": "Sub-headline emphasizing benefits",\n'
        '  "hero_cta_primary": "E.g. Book Now, Order Now",\n'
        '  "about_title": "About Us Title",\n'
        '  "about_description": "Engaging story about the business",\n'
        '  "about_xp_years": 5,\n'
        '  "services_title": "Our Offerings Title",\n'
        '  "services_subtitle": "Subtitle describing pricing/choices",\n'
        '  "services": [\n'
        '    {"title": "Service name", "description": "Short service description", "price": "$15"}\n'
        '  ],\n'
        '  "reviews": [\n'
        '    {"author": "Customer name", "text": "Customer review text", "rating": 5}\n'
        '  ]\n'
        "}"
    )
    copy_raw = _strip_fences(chat_text([{"role": "user", "content": prompt_writer}], temperature=0.5))
    try:
        copy_data = json.loads(copy_raw)
    except Exception:
        copy_data = {
            "hero_title": f"Welcome to {lead.get('name')}",
            "hero_subtitle": f"Top-rated {lead.get('category')} experience.",
            "hero_cta_primary": "Book Now",
            "about_title": "About Us",
            "about_description": "Serving our local community with premium quality and unmatched dedication.",
            "about_xp_years": 5,
            "services_title": "Our Services",
            "services_subtitle": "Premium offerings tailored for you.",
            "services": [],
            "reviews": []
        }

    # Map brand colors & fonts to HSL
    colors = brand.get("colors") or ["#0f172a", "#38bdf8", "#f8fafc", "#0f172a"]
    primary_hex = colors[1] if len(colors) > 1 else "#38bdf8"
    secondary_hex = colors[2] if len(colors) > 2 else "#f8fafc"
    
    config_dict = {
        "business_name": lead.get("name"),
        "business_category": lead.get("category"),
        "whatsapp_number": lead.get("phone") or "",
        "business_address": lead.get("address") or "N/A",
        "business_phone": lead.get("phone") or "N/A",
        "business_hours": details.get("hours", ["Monday - Friday: 9 AM - 6 PM"]),
        "gallery_images": images or [
            "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=cover&w=400&q=80"
        ],
        "primary_hsl": hex_to_hsl(primary_hex),
        "secondary_hsl": hex_to_hsl(secondary_hex),
        "bg_hsl": "225 25% 9%", # Premium dark background HSL
        "text_hsl": "0 0% 95%", # HSL light text
        "accent_hsl": hex_to_hsl(primary_hex),
        "radius": "12px",
        "fonts_import": "|".join(brand.get("fonts", ["Inter", "Outfit"])),
        "font_family": f"'{brand.get('fonts', ['Inter'])[0]}', sans-serif",
        "seo_description": f"Check out {lead.get('name')} for the best {lead.get('category')} in town.",
        "seo_keywords": f"{lead.get('name')}, {lead.get('category')}, services, booking",
    }
    
    # Merge copy data
    config_dict.update(copy_data)
    
    # Run the Assembly Engine (Website OS Compiler)
    html = site_assembler.assemble_site(config_dict)

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
