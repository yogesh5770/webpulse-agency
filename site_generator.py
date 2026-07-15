"""Generate a premium website for a business using a TOKEN-EFFICIENT pipeline:
Business DNA → Design DNA → Content → Website Compiler
This minimizes token usage while maintaining high quality and uniqueness!
"""
import json
import logging
import random
from agent_router import chat_text
from leads_places import photo_url, get_unsplash_images
import site_store
import site_assembler
import theme_engine

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


# --- TOKEN-EFFICIENT SYSTEM PROMPTS ---
SYSTEM_PROMPT_BUSINESS_DNA = """You are an elite business analyst and branding strategist. Your job is to deeply understand a business and create a "Business DNA" profile that captures its unique identity.

Return only valid JSON with no extra text.

Generate Business DNA with these fields:
- industry: The business industry/category
- personality: Brand personality (e.g., "Modern Luxury", "Warm & Friendly", "Professional & Trusted", "Creative & Bold")
- audience: Target audience (e.g., "Families and young professionals", "Luxury shoppers", "Health-conscious individuals")
- price_range: Price positioning (e.g., "Budget", "Mid-range", "Premium", "Luxury")
- strengths: Array of 3-5 business strengths
- brand_style: Visual brand style (e.g., "Warm Elegant", "Minimal Clean", "Bold & Vibrant", "Dark & Sophisticated")
- primary_goal: Primary business goal (e.g., "Increase walk-in customers", "Boost online bookings", "Build brand awareness")
- tone_of_voice: Content tone (e.g., "Friendly & Approachable", "Professional & Authoritative", "Luxurious & Exclusive")
"""

SYSTEM_PROMPT_DESIGN_DNA = """You are an award-winning senior product designer. Your job is to create a "Design DNA" profile that defines the visual and structural identity for the website based on the Business DNA.

Return only valid JSON with no extra text.

Available options:
- themes: apple, stripe, linear, notion, luxury, restaurant, corporate, creative, dark, glass, medical, startup
- animation_packs: luxury, corporate, modern, minimal, creative, medical, startup
- hero_components: hero_01, hero_02, hero_03
- about_components: about_01, about_02
- services_components: services_01, services_02
- gallery_components: gallery_01, gallery_02
- reviews_components: reviews_01, reviews_02
- contact_components: contact_01, contact_02
- section_orders (choose one or create your own array):
  - ["hero", "about", "services", "gallery", "reviews", "contact"]
  - ["hero", "services", "about", "gallery", "reviews", "contact"]
  - ["hero", "gallery", "about", "services", "reviews", "contact"]
  - ["hero", "reviews", "about", "services", "gallery", "contact"]

Generate Design DNA with these fields:
- theme: One theme from available options
- animation_pack: One animation pack from available options
- hero_component: Hero component variant
- about_component: About component variant
- services_component: Services component variant
- gallery_component: Gallery component variant
- reviews_component: Reviews component variant
- contact_component: Contact component variant
- section_order: Array defining the order of sections
- design_rationale: Brief explanation of design choices
"""

SYSTEM_PROMPT_CONTENT = """You are an elite copywriter and content strategist. Your job is to write unique, business-specific website content based on the Business DNA and Design DNA.

Return only valid JSON with no extra text.

Generate content with these fields:
- hero_title: Catchy, premium title tailored to the business (3-10 words)
- hero_subtitle: Brief, engaging description (15-30 words)
- hero_cta_primary: Clear call-to-action (e.g., "Book Now", "Contact Us", "Get Started")
- about_title: "About [Business Name]"
- about_description: Detailed, authentic description (150-250 words)
- about_xp_years: Number of years experience (integer, use 5 if unknown)
- services_title: "Our Services" or similar
- services_subtitle: Brief intro to services
- services: Array of 3-5 objects with title, description, price
- reviews: Array of 2-3 realistic reviews with author, text, rating (1-5)
- seo_title: "[Business Name] | [Category] in [Location]"
- seo_description: 150-160 character SEO description
- seo_keywords: Comma-separated keywords
"""


def generate_site(lead: dict) -> str:
    """Generate the site using a unique pipeline.
    Stores index.html, lead.json, and memory.json in the DB."""
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

    business_context = {
        "business": lead.get("name"),
        "industry": lead.get("category"),
        "address": lead.get("address"),
        "phone": lead.get("phone"),
        "details": details
    }

    # --- Step 1: Generate Business DNA ---
    prompt_business_dna = [
        {"role": "system", "content": SYSTEM_PROMPT_BUSINESS_DNA},
        {"role": "user", "content": f"Business Info: {json.dumps(business_context)}"}
    ]
    business_dna_raw = _strip_fences(chat_text(prompt_business_dna, temperature=0.7, max_tokens=600))
    try:
        business_dna = json.loads(business_dna_raw)
    except Exception:
        business_dna = {
            "industry": lead.get("category"),
            "personality": "Modern & Professional",
            "audience": "Local customers",
            "price_range": "Mid-range",
            "strengths": ["Quality service", "Friendly staff", "Convenient location"],
            "brand_style": "Clean & Modern",
            "primary_goal": "Increase customers",
            "tone_of_voice": "Friendly & Approachable"
        }

    # --- Step 2: Generate Design DNA ---
    prompt_design_dna = [
        {"role": "system", "content": SYSTEM_PROMPT_DESIGN_DNA},
        {"role": "user", "content": f"Business DNA: {json.dumps(business_dna)}"}
    ]
    design_dna_raw = _strip_fences(chat_text(prompt_design_dna, temperature=0.7, max_tokens=600))
    try:
        design_dna = json.loads(design_dna_raw)
    except Exception:
        # Randomize components for uniqueness if AI fails
        design_dna = {
            "theme": random.choice(["apple", "stripe", "luxury", "creative", "dark", "startup"]),
            "animation_pack": random.choice(["luxury", "corporate", "modern", "minimal", "creative"]),
            "hero_component": random.choice(["hero_01", "hero_02", "hero_03"]),
            "about_component": random.choice(["about_01", "about_02"]),
            "services_component": random.choice(["services_01", "services_02"]),
            "gallery_component": random.choice(["gallery_01", "gallery_02"]),
            "reviews_component": random.choice(["reviews_01", "reviews_02"]),
            "contact_component": random.choice(["contact_01", "contact_02"]),
            "section_order": random.choice([
                ["hero", "about", "services", "gallery", "reviews", "contact"],
                ["hero", "services", "about", "gallery", "reviews", "contact"],
                ["hero", "gallery", "about", "services", "reviews", "contact"]
            ]),
            "design_rationale": "Fallback design choices"
        }

    # --- Step 3: Generate Content ---
    prompt_content = [
        {"role": "system", "content": SYSTEM_PROMPT_CONTENT},
        {"role": "user", "content": f"Business Info: {json.dumps(business_context)}\nBusiness DNA: {json.dumps(business_dna)}"}
    ]
    content_raw = _strip_fences(chat_text(prompt_content, temperature=0.7, max_tokens=1500))
    try:
        content = json.loads(content_raw)
    except Exception:
        content = {
            "hero_title": f"Welcome to {lead.get('name')}",
            "hero_subtitle": f"Top-rated {lead.get('category')} experience.",
            "hero_cta_primary": "Book Now",
            "about_title": f"About {lead.get('name')}",
            "about_description": "Serving our local community with premium quality and unmatched dedication.",
            "about_xp_years": 5,
            "services_title": "Our Services",
            "services_subtitle": "Premium offerings tailored for you.",
            "services": [],
            "reviews": [],
            "seo_title": f"{lead.get('name')} | {lead.get('category')}",
            "seo_description": f"Check out {lead.get('name')} for the best {lead.get('category')} in town.",
            "seo_keywords": f"{lead.get('name')}, {lead.get('category')}, services, booking"
        }

    # --- Step 4: Website Compiler ---
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

    # Build memory
    memory = {
        "businessName": lead.get("name"),
        "industry": lead.get("category"),
        "businessDNA": business_dna,
        "designDNA": design_dna,
        "theme": theme_name,
        "colors": [],
        "fonts": [],
        "deployment": "Cloudflare Pages",
        "liveUrl": "",
        "framework": "HTML5 / Vanilla JS",
        "lastVersion": 1,
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
            "design_dna.json": json.dumps(design_dna, indent=2, ensure_ascii=False)
        }
    )

    return f"db://{place_id}"
