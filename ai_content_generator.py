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


SYSTEM_PROMPT = """You are an elite Copywriter and Content Strategist. Your job is to write unique, highly specific, premium website content tailored to the exact category of the business. 
Do not output placeholders or key names as list items. Write real items (e.g. if the category is bakery, output real bakery items like 'Croissant', 'Sourdough', etc.).

Return only valid JSON with NO extra text.

You MUST match this exact JSON schema:
{
  "hero_title": "Catchy business headline (3-10 words)",
  "hero_subtitle": "Engaging business details (15-30 words)",
  "hero_cta_primary": "Call to action text",
  "about_title": "About [Business Name]",
  "about_description": "A authentic company narrative (150-250 words)",
  "about_xp_years": 8,
  "services_title": "Our Specialties",
  "services_subtitle": "Short intro text explaining the services",
  "services": [
    {
      "title": "Real service/product title (e.g. 'Fresh Sourdough Bread')",
      "description": "Engaging description of this specific item",
      "price": "₹120"
    },
    {
      "title": "Another service/product title (e.g. 'Butter Croissant')",
      "description": "Engaging description of this specific item",
      "price": "₹80"
    }
  ],
  "reviews": [
    {
      "author": "Customer Name",
      "text": "Highly realistic review highlighting specific services",
      "rating": 5
    }
  ],
  "seo_title": "[Business Name] | [Category] in [Location]",
  "seo_description": "150-160 character description",
  "seo_keywords": "comma-separated keywords"
}
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


def generate_refinement(business_data: dict, business_dna: dict, old_content: dict, suggestions: list[str]) -> dict:
    """Run a second pass to refine content copy based on Quality Reviewer suggestions."""
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nCRITICAL: You are running a refinement pass. The previous content had issues. Please read the suggestions and return updated content JSON fixing the issues while keeping correct formatting."},
        {"role": "user", "content": json.dumps({
            "business_data": business_data,
            "business_dna": business_dna,
            "previous_content": old_content,
            "quality_feedback_suggestions": suggestions
        }, indent=2)}
    ]
    try:
        response = _strip_fences(chat_text(prompt, temperature=0.5, max_tokens=1500))
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Failed to refine content: {e}. Returning original.")
        return old_content
