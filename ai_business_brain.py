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


SYSTEM_PROMPT = """You are an elite Business Analyst and Brand Strategist. Your job is to deeply understand a business and create a comprehensive Business DNA profile.

Return only valid JSON with NO extra text.

Generate Business DNA with these fields:
- industry: str - the business industry/category
- personality: str - brand personality (e.g., "Modern Luxury", "Warm & Friendly", "Professional & Trusted", "Creative & Bold")
- audience: str - target audience description
- price_range: str - price positioning (e.g., "Budget", "Mid-range", "Premium", "Luxury")
- strengths: list[str] - 3-5 business strengths
- brand_style: str - visual brand style (e.g., "Warm Elegant", "Minimal Clean", "Bold & Vibrant", "Dark & Sophisticated")
- primary_goal: str - primary business goal (e.g., "Increase walk-in customers", "Boost online bookings", "Build brand awareness")
- tone_of_voice: str - content tone (e.g., "Friendly & Approachable", "Professional & Authoritative", "Luxurious & Exclusive")
"""


def generate_business_dna(business_data: dict) -> dict:
    """Generate comprehensive Business DNA from business data."""
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(business_data, indent=2)}
    ]

    try:
        response = _strip_fences(chat_text(prompt, temperature=0.8, max_tokens=800))
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Failed to generate Business DNA with AI: {e}. Using fallback.")
        # Fallback Business DNA
        category = business_data.get("category", "business")
        return {
            "industry": category,
            "personality": "Modern & Professional",
            "audience": "Local customers and families",
            "price_range": "Mid-range",
            "strengths": ["Quality service", "Friendly staff", "Convenient location"],
            "brand_style": "Clean & Modern",
            "primary_goal": "Increase customer base",
            "tone_of_voice": "Friendly & Approachable"
        }
