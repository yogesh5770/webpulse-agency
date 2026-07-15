"""Generate a premium website for a business using a 50% AI + 50% Template architecture!

Pipeline:
Business Data -> AI Business Brain -> AI Design Director -> AI Content Generator
-> Component Library -> Website Compiler -> AI Quality Reviewer -> Production Website
"""
import json
import logging
from agent_router import chat_text
from leads_places import photo_url, get_unsplash_images
import site_store
import site_assembler
import theme_engine
from ai_business_brain import generate_business_dna
from ai_design_director import generate_design_dna
from ai_content_generator import generate_content
from ai_quality_reviewer import review_website

logger = logging.getLogger(__name__)


def hex_to_hsl(hex_str: str) -> str:
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        return "215 90% 50%"  # Fallback HSL
    try:
        r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        r, g, b = r/255.0, g/255.0, b/255.0
        mx, mn = max(r, g, b), min(r, g, b)
        diff = mx - mn
        h = 0
        if mx == mn:
            h = 0
        elif mx == r:
            h = (60 * ((g - b) / diff) + 360) % 360
        elif mx == g:
            h = (60 * ((r - b) / diff) + 120) % 360
        elif mx == b:
            h = (60 * ((r - g) / diff) + 240) % 360
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
    """Generate the site using the complete pipeline. Stores all data in DB."""
    details = json.loads(lead.get("details_json") or "{}")
    photo_refs = json.loads(lead.get("photos_json") or "[]")
    # Load images - if they are already URLs, use them directly!
    images = []
    for ref in photo_refs:
        if ref.startswith("http"):
            images.append(ref)
        else:
            images.append(photo_url(ref))
    # Fallback if images are empty
    if not images:
        images = get_unsplash_images(lead.get("category"), 5)

    # Step 1: Business Data
    business_data = {
        "name": lead.get("name"),
        "category": lead.get("category"),
        "address": lead.get("address"),
        "phone": lead.get("phone"),
        "details": details
    }

    # Step 2: AI Business Brain -> Business DNA
    business_dna = generate_business_dna(business_data)

    # Step 3: AI Design Director -> Design DNA
    design_dna = generate_design_dna(business_dna)

    # Step 4: AI Content Generator -> Content
    content = generate_content(business_data, business_dna)

    # Step 5: Website Compiler -> HTML
    theme_name = design_dna.get("theme", "dark")
    theme = theme_engine.get_theme(theme_name)
    anim_pack_name = design_dna.get("animation_pack", "modern")

    config_dict = {
        "business_name": lead.get("name"),
        "business_category": lead.get("category"),
        "whatsapp_number": lead.get("phone") or "",
        "business_address": lead.get("address") or "N/A",
        "business_phone": lead.get("phone") or "N/A",
        "business_hours": details.get("hours", ["Monday - Friday: 9 AM - 6 PM"]),
        "gallery_images": images,
        # Theme tokens
        "primary_hsl": theme["primary_hsl"],
        "secondary_hsl": theme["secondary_hsl"],
        "bg_hsl": theme["bg_hsl"],
        "text_hsl": theme["text_hsl"],
        "accent_hsl": theme["accent_hsl"],
        "radius": theme["radius"],
        "fonts_import": theme["fonts_import"],
        "font_family": theme["font_family"],
        "theme": theme_name,
        "animation_pack": anim_pack_name,
        # Design DNA components and order
        "hero_component": design_dna.get("hero_component", "hero_01"),
        "about_component": design_dna.get("about_component", "about_01"),
        "services_component": design_dna.get("services_component", "services_01"),
        "gallery_component": design_dna.get("gallery_component", "gallery_01"),
        "reviews_component": design_dna.get("reviews_component", "reviews_01"),
        "contact_component": design_dna.get("contact_component", "contact_01"),
        "section_order": design_dna.get("section_order", ["hero", "about", "services", "gallery", "reviews", "contact"]),
        # SEO
        "seo_title": content.get("seo_title", f"{lead.get('name')} | {lead.get('category')}"),
        "seo_description": content.get("seo_description", f"Check out {lead.get('name')} for the best {lead.get('category')} in town."),
        "seo_keywords": content.get("seo_keywords", f"{lead.get('name')}, {lead.get('category')}, services, booking")
    }

    # Merge content data
    config_dict.update(content)

    # Run the Assembly Engine
    html = site_assembler.assemble_site(config_dict)

    # Step 6: AI Quality Reviewer
    review = review_website(html, business_dna, design_dna, content)

    # Build memory
    memory = {
        "business_name": lead.get("name"),
        "industry": lead.get("category"),
        "business_dna": business_dna,
        "design_dna": design_dna,
        "content": content,
        "review": review,
        "theme": theme_name,
        "colors": [],
        "fonts": [],
        "deployment": "Cloudflare Pages",
        "live_url": "",
        "framework": "HTML5 / Vanilla JS",
        "last_version": 1,
        "features": ["Gallery", "Services", "Map", "WhatsApp Button"]
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
            "index.html": html,
            "lead.json": lead_json,
            "memory.json": json.dumps(memory, indent=2, ensure_ascii=False),
            "business_dna.json": json.dumps(business_dna, indent=2, ensure_ascii=False),
            "design_dna.json": json.dumps(design_dna, indent=2, ensure_ascii=False),
            "content.json": json.dumps(content, indent=2, ensure_ascii=False),
            "review.json": json.dumps(review, indent=2, ensure_ascii=False)
        }
    )

    return f"db://{place_id}"
