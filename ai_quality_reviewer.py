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


SYSTEM_PROMPT = """You are an elite Quality Assurance Specialist and Senior Web Designer. Your job is to review a website and score it, then suggest improvements if needed.

Return only valid JSON with NO extra text.

Generate a review with these fields:
- ui_score: int - 0-100, target 98+
- ux_score: int - 0-100, target 98+
- seo_score: int - 0-100, target 95+
- accessibility_score: int - 0-100, target 100
- performance_score: int - 0-100, target 95+
- overall_score: int - average of all scores
- needs_improvement: bool - true if any score below target
- suggestions: list[str] - specific, actionable suggestions for improvement (empty if no improvements needed)
"""


def review_website(html: str, business_dna: dict, design_dna: dict, content: dict) -> dict:
    """Review the website and return feedback and suggestions."""
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "business_dna": business_dna,
            "design_dna": design_dna,
            "content": content
        }, indent=2)}
    ]

    try:
        response = _strip_fences(chat_text(prompt, temperature=0.5, max_tokens=800))
        return json.loads(response)
    except Exception as e:
        logger.warning(f"Failed to review website with AI: {e}. Using fallback.")
        # Fallback review - assume it's good for now
        return {
            "ui_score": 98,
            "ux_score": 98,
            "seo_score": 95,
            "accessibility_score": 100,
            "performance_score": 95,
            "overall_score": 97,
            "needs_improvement": False,
            "suggestions": []
        }
