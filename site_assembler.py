import os
import re
import theme_engine

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _read_tpl(name: str) -> str:
    path = os.path.join(TEMPLATES_DIR, name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def assemble_site(config: dict) -> str:
    """Assembles the modular component sections into a premium, consistent landing page."""
    # Load layout shell
    layout = _read_tpl("layout.html")
    if not layout:
        raise ValueError("layout.html template not found")

    # Get animation pack config
    anim_pack = theme_engine.get_animation_pack(config.get("animation_pack", "modern"))

    # Get about image
    about_img = config.get("about_image") or (
        config.get("gallery_images")[0] if config.get("gallery_images") else "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=cover&w=800&q=80")

    # Helper function to fill placeholders in any section
    def fill_section_placeholders(html: str) -> str:
        html = html.replace("{{HERO_TITLE}}", config.get("hero_title", f"Welcome to {config.get('business_name')}"))
        html = html.replace("{{HERO_SUBTITLE}}", config.get("hero_subtitle", "Premium Quality & Professional Service."))
        html = html.replace("{{HERO_CTA_PRIMARY}}", config.get("hero_cta_primary", "Book Now"))
        html = html.replace("{{ABOUT_TITLE}}", config.get("about_title", "About Us"))
        html = html.replace("{{ABOUT_DESCRIPTION}}", config.get("about_description", "We are dedicated to providing the absolute best service to our community."))
        html = html.replace("{{ABOUT_IMAGE}}", about_img)
        html = html.replace("{{ABOUT_XP_YEARS}}", str(config.get("about_xp_years", "5")))
        html = html.replace("{{SERVICES_TITLE}}", config.get("services_title", "Our Specialties"))
        html = html.replace("{{SERVICES_SUBTITLE}}", config.get("services_subtitle", "Explore our signature offerings and pricing below."))
        html = html.replace("{{BUSINESS_ADDRESS}}", config.get("business_address", "Address Not Available"))
        html = html.replace("{{BUSINESS_PHONE}}", config.get("business_phone", "N/A"))
        hours = config.get("business_hours", [])
        hours_str = "<br>".join(hours) if isinstance(hours, list) and hours else "Monday - Friday: 9 AM - 6 PM"
        html = html.replace("{{BUSINESS_HOURS}}", hours_str)
        map_html = config.get("maps_iframe", "")
        if not map_html:
            q = re.sub(r"\s+", "+", config.get("business_address", ""))
            map_html = f'<iframe width="100%" height="100%" frameborder="0" style="border:0; position:absolute; inset:0;" src="https://maps.google.com/maps?q={q}&t=&z=14&ie=UTF8&iwloc=&output=embed" allowfullscreen></iframe>'
        html = html.replace("{{MAPS_IFRAME}}", map_html)
        return html

    # Gather sections in custom order
    sections = []
    section_order = config.get("section_order", ["hero", "about", "services", "gallery", "reviews", "contact"])
    component_map = {
        "hero": config.get("hero_component", "hero_01"),
        "about": config.get("about_component", "about_01"),
        "services": config.get("services_component", "services_01"),
        "gallery": config.get("gallery_component", "gallery_01"),
        "reviews": config.get("reviews_component", "reviews_01"),
        "contact": config.get("contact_component", "contact_01")
    }

    for section_type in section_order:
        if section_type == "hero":
            tpl_name = f"components/{component_map['hero']}.html"
            hero_tpl = _read_tpl(tpl_name)
            if hero_tpl:
                hero_html = fill_section_placeholders(hero_tpl)
                sections.append(hero_html)
        elif section_type == "about":
            tpl_name = f"components/{component_map['about']}.html"
            about_tpl = _read_tpl(tpl_name)
            if about_tpl:
                about_html = fill_section_placeholders(about_tpl)
                sections.append(about_html)
        elif section_type == "services":
            tpl_name = f"components/{component_map['services']}.html"
            services_tpl = _read_tpl(tpl_name)
            if services_tpl:
                cards_html = ""
                services_list = config.get("services", [])
                if not services_list:
                    services_list = [
                        {"title": "Signature Service", "description": "Our most popular offering, crafted to perfection.", "price": "Contact Us"},
                        {"title": "Deluxe Treatment", "description": "An upgraded premium experience with extra detail.", "price": "Contact Us"}
                    ]
                for s in services_list:
                    if isinstance(s, str):
                        title = s
                        desc = "Professional quality service."
                        price = "Contact Us"
                    elif isinstance(s, dict):
                        title = s.get('title') or "Service Offer"
                        desc = s.get('description') or "Professional quality service."
                        price = s.get('price') or "Contact Us"
                    else:
                        continue
                        
                    cards_html += f"""
    <div class="card p-8 bg-[var(--card-bg)] backdrop-blur-md border border-[var(--border)] rounded-2xl hover:border-indigo-500/40 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-indigo-500/5">
      <h3 class="text-xl font-bold text-indigo-400 mb-3">{title}</h3>
      <p class="text-slate-400 text-sm mb-6 leading-relaxed min-h-[50px]">{desc}</p>
      <div class="flex justify-between items-center border-t border-[var(--border)] pt-4">
        <span class="font-extrabold text-lg text-white">{price}</span>
        <a href="https://wa.me/{config.get('whatsapp_number')}" target="_blank" class="text-sm font-semibold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1">Book Now <span class="text-xs">→</span></a>
      </div>
    </div>"""
                services_html = services_tpl.replace("{{SERVICES_CARDS}}", cards_html)
                services_html = fill_section_placeholders(services_html)
                sections.append(services_html)
        elif section_type == "gallery":
            tpl_name = f"components/{component_map['gallery']}.html"
            gallery_tpl = _read_tpl(tpl_name)
            if gallery_tpl:
                items_html = ""
                gallery_list = config.get("gallery_images", [])
                if not gallery_list:
                    gallery_list = [
                        "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?auto=format&fit=cover&w=400&q=80",
                        "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=cover&w=400&q=80",
                        "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=cover&w=400&q=80"
                    ]
                for img in gallery_list:
                    items_html += f"""
    <div style="aspect-ratio: 1; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border); transition: transform 0.2s;">
      <img src="{img}" alt="Gallery Item" style="width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s;" onmouseover="this.style.transform='scale({anim_pack['card_hover_scale']})'" onmouseout="this.style.transform='scale(1)'">
    </div>"""
                gallery_html = gallery_tpl.replace("{{GALLERY_ITEMS}}", items_html)
                gallery_html = fill_section_placeholders(gallery_html)
                sections.append(gallery_html)
        elif section_type == "reviews":
            tpl_name = f"components/{component_map['reviews']}.html"
            reviews_tpl = _read_tpl(tpl_name)
            if reviews_tpl:
                cards_html = ""
                reviews_list = config.get("reviews", [])
                if not reviews_list:
                    reviews_list = [
                        {"author": "Jane Doe", "text": "Absolutely fantastic experience! The quality and service was second to none.", "rating": 5},
                        {"author": "John Smith", "text": "Extremely satisfied with the prompt booking and responsive communication.", "rating": 5}
                    ]
                for r in reviews_list:
                    stars = "★" * int(r.get("rating") or 5)
                    cards_html += f"""
    <div class="card p-8 bg-[var(--card-bg)] backdrop-blur-md border border-[var(--border)] rounded-2xl hover:border-indigo-500/40 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-indigo-500/5">
      <div class="text-amber-400 text-lg mb-3">{stars}</div>
      <p class="text-slate-300 italic text-sm mb-6 leading-relaxed">"{r.get('text')}"</p>
      <div class="font-bold text-xs text-indigo-400 tracking-wider uppercase">— {r.get('author')}</div>
    </div>"""
                reviews_html = reviews_tpl.replace("{{REVIEWS_CARDS}}", cards_html)
                reviews_html = fill_section_placeholders(reviews_html)
                sections.append(reviews_html)
        elif section_type == "contact":
            tpl_name = f"components/{component_map['contact']}.html"
            contact_tpl = _read_tpl(tpl_name)
            if contact_tpl:
                contact_html = fill_section_placeholders(contact_tpl)
                sections.append(contact_html)

    # Stitch all sections
    compiled_sections = "\n\n".join(sections)
    
    # Process Layout placeholders
    html = layout
    default_title = f"{config.get('business_name', 'Local Business')} | {config.get('business_category', 'Specialty Services')}"
    html = html.replace("{{SEO_TITLE}}", config.get("seo_title", default_title))
    html = html.replace("{{BUSINESS_NAME}}", config.get("business_name", "Local Business"))
    html = html.replace("{{BUSINESS_CATEGORY}}", config.get("business_category", "Specialty Services"))
    html = html.replace("{{SEO_DESCRIPTION}}", config.get("seo_description", f"Premium services and highlights at {config.get('business_name')}."))
    html = html.replace("{{SEO_KEYWORDS}}", config.get("seo_keywords", f"{config.get('business_name')}, {config.get('business_category')}, local business"))
    
    # Load fonts
    html = html.replace("{{FONTS_IMPORT}}", config.get("fonts_import", "Inter:wght@400;600;800&family=Outfit:wght@400;700"))
    html = html.replace("{{FONT_FAMILY}}", config.get("font_family", "'Outfit', sans-serif"))
    
    # Design HSL theme tokens
    html = html.replace("{{PRIMARY_HSL}}", config.get("primary_hsl", "215 90% 50%"))
    html = html.replace("{{SECONDARY_HSL}}", config.get("secondary_hsl", "185 85% 45%"))
    html = html.replace("{{BG_HSL}}", config.get("bg_hsl", "225 25% 9%"))
    html = html.replace("{{TEXT_HSL}}", config.get("text_hsl", "0 0% 95%"))
    html = html.replace("{{ACCENT_HSL}}", config.get("accent_hsl", "215 90% 50%"))
    html = html.replace("{{RADIUS}}", config.get("radius", "12px"))
    
    # Animation Pack Config Placeholders
    html = html.replace("{{ANIM_HERO_DURATION}}", str(anim_pack["hero_duration"]))
    html = html.replace("{{ANIM_HERO_EASE}}", anim_pack["hero_ease"])
    html = html.replace("{{ANIM_SCROLL_EASE}}", anim_pack["scroll_ease"])
    html = html.replace("{{ANIM_SCROLL_DURATION}}", str(anim_pack["scroll_duration"]))
    
    # WhatsApp details
    html = html.replace("{{WHATSAPP_NUMBER}}", config.get("whatsapp_number", ""))
    
    # Stitched content block
    html = html.replace("{{COMPILER_SECTIONS}}", compiled_sections)
    
    return html