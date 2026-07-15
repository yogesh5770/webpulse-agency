"""Generate a premium website for a business using a TOKEN-EFFICIENT pipeline:
System Prompt → Blueprint JSON → Content JSON → Website Compiler
This minimizes token usage while maintaining high quality!
"""
import json
import logging
from agent_router import chat_text
from leads_places import photo_url
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


# --- TOKEN-EFFICIENT SYSTEM PROMPT – Master Prompt – Website AI v1
SYSTEM_PROMPT = """You are Website AI, an elite autonomous frontend engineer, UI/UX designer, product designer, branding expert, SEO expert, accessibility expert, and performance engineer.

MISSION
Create premium, production-ready business websites that compete with websites designed by top agencies (Apple, Stripe, Linear, Framer, Vercel, Notion, Airbnb, Webflow showcase).

PRIMARY GOAL
Build websites that maximize:
 • UI Quality
 • UX
 • Conversion
 • Accessibility
 • Performance
 • SEO
 • Mobile Experience
 • Maintainability

Every website must feel handcrafted for the business.

WORKFLOW
Always follow these steps:
1. Understand Business
2. Analyze Business
3. Determine Audience
4. Determine Business Goals
5. Determine Brand Personality
6. Select Best Theme
7. Select Typography
8. Select Color Palette
9. Select Layout
10. Select Components
11. Generate Content
12. Generate SEO
13. Generate Blueprint JSON

IMPORTANT
Never generate an entire React project.
Instead generate:
Business Analysis → Website Blueprint → Content JSON → SEO JSON → Component Selection.

FRAMEWORK
React 19, Vite, TypeScript, Tailwind CSS v4, shadcn/ui, Motion, Lucide React.

DESIGN RULES
Design must be: Minimal, Modern, Premium, Luxury, Clean, Elegant, Professional.
Never produce generic templates. Every business must look unique.

OUTPUT
Always return structured JSON only!
"""


def get_niche_images(category: str) -> list[str]:
    cat = (category or "business").lower()
    if any(k in cat for k in ["salon", "barber", "parlour", "spa", "hairdresser"]):
        return [
            "https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1621605815971-fbc98d665033?auto=format&fit=cover&w=800&q=80"
        ]
    elif any(k in cat for k in ["bakery", "cafe", "restaurant", "food"]):
        return [
            "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1498804103079-a6351b050096?auto=format&fit=cover&w=800&q=80"
        ]
    elif any(k in cat for k in ["gym", "fitness", "workout"]):
        return [
            "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1541534741688-6078c6bfb5c5?auto=format&fit=cover&w=800&q=80"
        ]
    elif any(k in cat for k in ["dentist", "clinic", "medical", "doctor"]):
        return [
            "https://images.unsplash.com/photo-1629909613654-28e377c37b09?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1579684389782-64d84b5e902a?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1584824486509-112e4181ff6b?auto=format&fit=cover&w=800&q=80"
        ]
    else:
        return [
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=cover&w=800&q=80",
            "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=cover&w=800&q=80"
        ]


def generate_site(lead: dict) -> str:
    """Generate the site using a TOKEN-EFFICIENT pipeline.
    Stores index.html, lead.json, and memory.json in the DB."""
    details = json.loads(lead.get("details_json") or "{}")
    photo_refs = json.loads(lead.get("photos_json") or "[]")
    images = [photo_url(ref) for ref in photo_refs]

    category = (lead.get("category") or "business").lower()
    theme_choice = "dark"
    if any(k in category for k in ["salon", "barber", "parlour", "spa"]):
        theme_choice = "creative"
    elif any(k in category for k in ["bakery", "cafe", "restaurant"]):
        theme_choice = "restaurant"
    elif any(k in category for k in ["dentist", "clinic", "medical"]):
        theme_choice = "medical"
    elif any(k in category for k in ["gym", "fitness"]):
        theme_choice = "startup"

    business_context = {
        "business": lead.get("name"),
        "industry": lead.get("category"),
        "theme": theme_choice,
        "colors": [],
        "target": "Local customers"
    }

    # --- Step 1: Generate Website Blueprint (JSON only, ~300 tokens) ---
    prompt_blueprint = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Business Context: {json.dumps(business_context)}

Available themes (choose one):
apple, stripe, linear, notion, luxury, restaurant, corporate, creative, dark, glass, medical, startup

Available animation packs (choose one):
luxury, corporate, modern, minimal, creative, medical, startup

Task: Generate Website Blueprint. Return JSON only.
Reuse existing components: Hero, About, Services, Gallery, Reviews, Contact, Footer

Return JSON with:
{{
  "hero": "hero",
  "about": "about",
  "services": "services",
  "gallery": "gallery",
  "reviews": "reviews",
  "contact": "contact",
  "footer": "footer",
  "animations": "modern",
  "theme": "dark",
  "seo": {{}}
}}"""}
    ]
    blueprint_raw = _strip_fences(chat_text(prompt_blueprint, temperature=0.2, max_tokens=500))
    try:
        blueprint = json.loads(blueprint_raw)
    except Exception:
        blueprint = {
            "hero": "hero",
            "about": "about",
            "services": "services",
            "gallery": "gallery",
            "reviews": "reviews",
            "contact": "contact",
            "footer": "footer",
            "animations": "modern",
            "theme": "dark",
            "seo": {}
        }

    # --- Step 2: Generate Content (JSON only, ~1000 tokens) ---
    prompt_content = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""Business Context: {json.dumps(business_context)}
Blueprint: {json.dumps(blueprint)}
Task: Generate only website content. No HTML. Return JSON.
Generate:
- hero_title, hero_subtitle, hero_cta_primary
- about_title, about_description, about_xp_years
- services_title, services_subtitle, services (array of {{"title": string, "description": string, "price": string}})
- reviews (array of {{"author": string, "text": string, "rating": number}})
- seo_title, seo_description, seo_keywords
Return JSON only.
"""}
    ]
    content_raw = _strip_fences(chat_text(prompt_content, temperature=0.5, max_tokens=1500))
    try:
        content = json.loads(content_raw)
    except Exception:
        content = {
            "hero_title": f"Welcome to {lead.get('name')}",
            "hero_subtitle": f"Top-rated {lead.get('category')} experience.",
            "hero_cta_primary": "Book Now",
            "about_title": "About Us",
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

    # --- Step 3: Website Compiler (no AI, just code assembly) ---
    theme_name = blueprint.get("theme", "dark")
    theme = theme_engine.get_theme(theme_name)
    anim_pack_name = blueprint.get("animations", "modern")
    
    config_dict = {
        "business_name": lead.get("name"),
        "business_category": lead.get("category"),
        "whatsapp_number": lead.get("phone") or "",
        "business_address": lead.get("address") or "N/A",
        "business_phone": lead.get("phone") or "N/A",
        "business_hours": details.get("hours", ["Monday - Friday: 9 AM - 6 PM"]),
        "gallery_images": images or get_niche_images(lead.get("category")),
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
        "seo_title": content.get("seo_title", f"{lead.get('name')} | {lead.get('category')}"),
        "seo_description": content.get("seo_description", f"Check out {lead.get('name')} for the best {lead.get('category')} in town."),
        "seo_keywords": content.get("seo_keywords", f"{lead.get('name')}, {lead.get('category')}, services, booking")
    }
    
    # Merge content data
    config_dict.update(content)
    
    # Run the Assembly Engine (Website OS Compiler)
    html = site_assembler.assemble_site(config_dict)

    # Build memory
    memory = {
        "businessName": lead.get("name"),
        "industry": lead.get("category"),
        "theme": blueprint.get("theme", "modern"),
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
            "memory.json": json.dumps(memory, indent=2, ensure_ascii=False)
        }
    )

    return f"db://{place_id}"