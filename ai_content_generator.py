import json
import logging
from agent_router import chat_text

logger = logging.getLogger(__name__)


def _strip_fences(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


SYSTEM_PROMPT = """You are an elite Copywriter and Content Strategist. Your job is to write unique, business-specific website content based on Business DNA and Design DNA.

Return only valid JSON with NO extra text.

Generate content with these fields:
- hero_title: str - catchy, premium title tailored to the business (3-10 words)
- hero_subtitle: str - brief, engaging description (15-30 words)
- hero_cta_primary: str - clear call-to-action (e.g., "Book Now", "Contact Us", "Get Started")
- about_title: str - "About [Business Name]"
- about_description: str - detailed, authentic description (150-250 words)
- about_xp_years: int - number of years experience (use 5 if unknown)
- services_title: str - "Our Services" or similar
- services_subtitle: str - brief intro to services
- services: list[dict] - 3-5 services with title, description, price
- reviews: list[dict] - 2-3 realistic reviews with author, text, rating (1-5)
- seo_title: str - "[Business Name] | [Category] in [Location]"
- seo_description: str - 150-160 character SEO description
- seo_keywords: str - comma-separated keywords
"""


def generate_content(business_data: dict, business_dna: dict) -> dict:
    """Generate unique, business-specific content."""
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "business_data": business_data,
            "business_dna": business_dna
        }, indent=2)}
    ]

    try:
        response = _strip_fences(chat_text(prompt, temperature=0.7, max_tokens=1500))
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Failed to generate content with AI: {e}. Using fallback.")
        # Fallback content
        name = business_data.get("name", "Local Business")
        category = business_data.get("category", "services")
        return {
            "hero_title": f"Welcome to {name}",
            "hero_subtitle": f"Premium {category} services tailored for you.",
            "hero_cta_primary": "Book Now",
            "about_title": f"About {name}",
            "about_description": f"Serving our local community with premium quality {category} services and unmatched dedication for years.",
            "about_xp_years": 5,
            "services_title": "Our Services",
            "services_subtitle": "Explore our offerings.",
            "services": [
                {"title": "Signature Service", "description": "Our most popular offering.", "price": "Contact Us"},
                {"title": "Premium Package", "description": "Enhanced experience.", "price": "Contact Us"}
            ],
            "reviews": [
                {"author": "Happy Customer", "text": "Great service!", "rating": 5}
            ],
            "seo_title": f"{name} | {category}",
            "seo_description": f"Check out {name} for the best {category} in town.",
            "seo_keywords": f"{name}, {category}, services"
        }
