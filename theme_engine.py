"""Theme Engine for website presets: colors, fonts, spacing, and design tokens."""

THEMES = {
    "apple": {
        "name": "Apple",
        "primary_hsl": "220 91% 54%",
        "secondary_hsl": "210 90% 70%",
        "bg_hsl": "0 0% 100%",
        "text_hsl": "0 0% 0%",
        "accent_hsl": "220 91% 54%",
        "radius": "12px",
        "fonts": ["SF Pro Text", "Inter"],
        "fonts_import": "Inter:wght@400;500;600;700",
        "font_family": "'Inter', sans-serif",
        "description": "Clean, minimal, premium aesthetic like Apple.com"
    },
    "stripe": {
        "name": "Stripe",
        "primary_hsl": "212 100% 47%",
        "secondary_hsl": "204 90% 55%",
        "bg_hsl": "210 40% 98%",
        "text_hsl": "210 20% 15%",
        "accent_hsl": "340 82% 52%",
        "radius": "8px",
        "fonts": ["Inter"],
        "fonts_import": "Inter:wght@400;500;600;700",
        "font_family": "'Inter', sans-serif",
        "description": "Modern, trusted, enterprise feel like Stripe.com"
    },
    "linear": {
        "name": "Linear",
        "primary_hsl": "245 63% 55%",
        "secondary_hsl": "220 70% 60%",
        "bg_hsl": "222 47% 11%",
        "text_hsl": "220 13% 91%",
        "accent_hsl": "245 63% 55%",
        "radius": "8px",
        "fonts": ["Inter"],
        "fonts_import": "Inter:wght@400;500;600;700",
        "font_family": "'Inter', sans-serif",
        "description": "Dark mode, productivity-focused like Linear.app"
    },
    "notion": {
        "name": "Notion",
        "primary_hsl": "220 9% 46%",
        "secondary_hsl": "220 9% 46%",
        "bg_hsl": "0 0% 100%",
        "text_hsl": "220 9% 20%",
        "accent_hsl": "220 9% 46%",
        "radius": "4px",
        "fonts": ["Inter"],
        "fonts_import": "Inter:wght@400;500;600;700",
        "font_family": "'Inter', sans-serif",
        "description": "Clean, content-first like Notion.so"
    },
    "luxury": {
        "name": "Luxury",
        "primary_hsl": "0 0% 0%",
        "secondary_hsl": "45 93% 47%",
        "bg_hsl": "0 0% 100%",
        "text_hsl": "0 0% 0%",
        "accent_hsl": "45 93% 47%",
        "radius": "0px",
        "fonts": ["Playfair Display", "Lato"],
        "fonts_import": "Playfair+Display:wght@400;700;900&family=Lato:wght@300;400;700",
        "font_family": "'Playfair Display', serif",
        "description": "Elegant, high-end luxury aesthetic"
    },
    "restaurant": {
        "name": "Restaurant",
        "primary_hsl": "14 85% 58%",
        "secondary_hsl": "34 95% 57%",
        "bg_hsl": "30 15% 96%",
        "text_hsl": "24 10% 10%",
        "accent_hsl": "14 85% 58%",
        "radius": "16px",
        "fonts": ["Poppins", "Playfair Display"],
        "fonts_import": "Poppins:wght@400;500;600;700&family=Playfair+Display:wght@400;700",
        "font_family": "'Poppins', sans-serif",
        "description": "Warm, inviting restaurant vibe"
    },
    "corporate": {
        "name": "Corporate",
        "primary_hsl": "212 85% 47%",
        "secondary_hsl": "200 80% 60%",
        "bg_hsl": "0 0% 100%",
        "text_hsl": "210 20% 15%",
        "accent_hsl": "212 85% 47%",
        "radius": "6px",
        "fonts": ["Roboto"],
        "fonts_import": "Roboto:wght@400;500;700",
        "font_family": "'Roboto', sans-serif",
        "description": "Professional, trustworthy corporate look"
    },
    "creative": {
        "name": "Creative",
        "primary_hsl": "280 70% 55%",
        "secondary_hsl": "340 80% 60%",
        "bg_hsl": "250 30% 98%",
        "text_hsl": "250 20% 15%",
        "accent_hsl": "280 70% 55%",
        "radius": "24px",
        "fonts": ["Space Grotesk", "Inter"],
        "fonts_import": "Space+Grotesk:wght@400;500;700&family=Inter:wght@400;500;700",
        "font_family": "'Space Grotesk', sans-serif",
        "description": "Bold, playful creative agency style"
    },
    "dark": {
        "name": "Dark",
        "primary_hsl": "215 90% 50%",
        "secondary_hsl": "185 85% 45%",
        "bg_hsl": "225 25% 9%",
        "text_hsl": "0 0% 95%",
        "accent_hsl": "215 90% 50%",
        "radius": "12px",
        "fonts": ["Outfit", "Inter"],
        "fonts_import": "Outfit:wght@400;600;800&family=Inter:wght@400;500;700",
        "font_family": "'Outfit', sans-serif",
        "description": "Sleek, premium dark mode theme"
    },
    "glass": {
        "name": "Glass",
        "primary_hsl": "215 90% 50%",
        "secondary_hsl": "185 85% 45%",
        "bg_hsl": "225 25% 12%",
        "text_hsl": "0 0% 95%",
        "accent_hsl": "215 90% 50%",
        "radius": "24px",
        "fonts": ["Inter"],
        "fonts_import": "Inter:wght@400;500;600;700",
        "font_family": "'Inter', sans-serif",
        "description": "Glassmorphic, translucent aesthetic"
    },
    "medical": {
        "name": "Medical",
        "primary_hsl": "210 100% 45%",
        "secondary_hsl": "180 70% 50%",
        "bg_hsl": "0 0% 100%",
        "text_hsl": "210 20% 15%",
        "accent_hsl": "210 100% 45%",
        "radius": "8px",
        "fonts": ["Roboto"],
        "fonts_import": "Roboto:wght@400;500;700",
        "font_family": "'Roboto', sans-serif",
        "description": "Clean, trustworthy medical/healthcare vibe"
    },
    "startup": {
        "name": "Startup",
        "primary_hsl": "265 89% 58%",
        "secondary_hsl": "330 81% 60%",
        "bg_hsl": "250 30% 98%",
        "text_hsl": "250 20% 15%",
        "accent_hsl": "265 89% 58%",
        "radius": "16px",
        "fonts": ["Poppins"],
        "fonts_import": "Poppins:wght@400;500;600;700",
        "font_family": "'Poppins', sans-serif",
        "description": "Modern, energetic startup style"
    }
}

def get_theme(theme_name: str) -> dict:
    """Get theme preset by name (case-insensitive). Falls back to 'dark'."""
    theme_name = theme_name.lower().strip()
    if theme_name not in THEMES:
        return THEMES["dark"]
    return THEMES[theme_name]


ANIMATION_PACKS = {
    "luxury": {
        "name": "Luxury",
        "description": "Elegant, subtle fade-ins with slow ease",
        "hero_duration": 1.5,
        "hero_ease": "power2.out",
        "scroll_ease": "cubic-bezier(0.25, 0.46, 0.45, 0.94)",
        "scroll_duration": 1,
        "card_hover_scale": 1.02
    },
    "corporate": {
        "name": "Corporate",
        "description": "Professional, minimal animations",
        "hero_duration": 0.8,
        "hero_ease": "power1.out",
        "scroll_ease": "ease-out",
        "scroll_duration": 0.6,
        "card_hover_scale": 1.01
    },
    "modern": {
        "name": "Modern",
        "description": "Clean, modern animation style",
        "hero_duration": 1.2,
        "hero_ease": "power4.out",
        "scroll_ease": "cubic-bezier(0.16, 1, 0.3, 1)",
        "scroll_duration": 0.8,
        "card_hover_scale": 1.03
    },
    "minimal": {
        "name": "Minimal",
        "description": "Super subtle, almost no animations",
        "hero_duration": 0.4,
        "hero_ease": "none",
        "scroll_ease": "ease-out",
        "scroll_duration": 0.4,
        "card_hover_scale": 1.0
    },
    "creative": {
        "name": "Creative",
        "description": "Playful, bouncy animations",
        "hero_duration": 1.3,
        "hero_ease": "back.out(1.7)",
        "scroll_ease": "elastic.out(1, 0.5)",
        "scroll_duration": 1,
        "card_hover_scale": 1.05
    },
    "medical": {
        "name": "Medical",
        "description": "Calm, reassuring animations",
        "hero_duration": 1,
        "hero_ease": "power1.out",
        "scroll_ease": "ease-out",
        "scroll_duration": 0.7,
        "card_hover_scale": 1.01
    },
    "startup": {
        "name": "Startup",
        "description": "Energetic, fast-paced animations",
        "hero_duration": 0.9,
        "hero_ease": "power3.out",
        "scroll_ease": "cubic-bezier(0.16, 1, 0.3, 1)",
        "scroll_duration": 0.6,
        "card_hover_scale": 1.04
    }
}

def get_animation_pack(pack_name: str) -> dict:
    """Get animation pack by name (case-insensitive). Falls back to 'modern'."""
    pack_name = pack_name.lower().strip()
    if pack_name not in ANIMATION_PACKS:
        return ANIMATION_PACKS["modern"]
    return ANIMATION_PACKS[pack_name]
