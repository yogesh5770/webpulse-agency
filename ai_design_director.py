import json
import logging
import random
from agent_router import chat_text

logger = logging.getLogger(__name__)


def _strip_fences(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


SYSTEM_PROMPT = """You are an award-winning Senior Product Designer (AI Design Director). Your job is to create a comprehensive Design DNA profile based on the Business DNA.

Return only valid JSON with NO extra text.

Available options:
- themes: apple, stripe, linear, notion, luxury, restaurant, corporate, creative, dark, glass, medical, startup
- animation_packs: luxury, corporate, modern, minimal, creative, medical, startup
- hero_components: hero_01, hero_02, hero_03
- about_components: about_01, about_02
- services_components: services_01, services_02
- gallery_components: gallery_01, gallery_02
- reviews_components: reviews_01, reviews_02
- contact_components: contact_01, contact_02
- section_orders (choose one):
  - ["hero", "about", "services", "gallery", "reviews", "contact"]
  - ["hero", "services", "about", "gallery", "reviews", "contact"]
  - ["hero", "gallery", "about", "services", "reviews", "contact"]
  - ["hero", "reviews", "about", "services", "gallery", "contact"]

Generate Design DNA with these fields:
- theme: str - one theme from available options
- animation_pack: str - one animation pack from available options
- hero_component: str - hero component variant
- about_component: str - about component variant
- services_component: str - services component variant
- gallery_component: str - gallery component variant
- reviews_component: str - reviews component variant
- contact_component: str - contact component variant
- section_order: list[str] - array defining the order of sections
- design_rationale: str - brief explanation of design choices
"""


def generate_design_dna(business_dna: dict) -> dict:
    """Generate comprehensive Design DNA from Business DNA."""
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(business_dna, indent=2)}
    ]

    try:
        response = _strip_fences(chat_text(prompt, temperature=0.7, max_tokens=800))
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Failed to generate Design DNA with AI: {e}. Using fallback.")
        # Fallback Design DNA with randomization for uniqueness
        return {
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
            "design_rationale": "Fallback design based on randomization for uniqueness."
        }
