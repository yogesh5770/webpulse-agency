"""Central configuration loaded from environment variables.

Secrets are NEVER hardcoded. Locally they come from a .env file;
on Hugging Face they come from Space "Repository secrets".
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# AgentRouter / Opus
AGENTROUTER_BASE_URL = _get("AGENTROUTER_BASE_URL")
AGENTROUTER_API_KEY = _get("AGENTROUTER_API_KEY")
AGENTROUTER_API_KEYS = [k.strip() for k in AGENTROUTER_API_KEY.split(",") if k.strip()] if AGENTROUTER_API_KEY else []
AGENTROUTER_MODEL = _get("AGENTROUTER_MODEL", "glm-5-2")

# Google Places
GOOGLE_PLACES_API_KEY = _get("GOOGLE_PLACES_API_KEY")
LEAD_SEARCH_QUERY = _get("LEAD_SEARCH_QUERY", "salon in Chennai")
LEAD_MAX_RESULTS = int(_get("LEAD_MAX_RESULTS", "10") or "10")
# Region hint used by the AI query generator so auto-generated searches stay
# relevant (e.g. "Tamil Nadu, India" -> queries across its cities/niches).
LEAD_REGION = _get("LEAD_REGION", "Chennai, Tamil Nadu, India")
# When true, the worker asks Opus for a fresh search query each cycle instead
# of reusing the single fixed LEAD_SEARCH_QUERY.
LEAD_AI_QUERIES = _get("LEAD_AI_QUERIES", "true").lower() not in ("false", "0", "no", "")

# --- Publishing ---
# Generated client sites are always published to Cloudflare Pages (unlimited
# free, no per-project caps).
# Cloudflare Pages. Every business is deployed to ONE project on its own
# branch, so it gets a stable URL like https://<branch>.<project>.pages.dev
# with no per-project limit.
CLOUDFLARE_API_TOKEN = _get("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = _get("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_PAGES_PROJECT = _get("CLOUDFLARE_PAGES_PROJECT", "lead-sites")

# WhatsApp
WHATSAPP_FROM_NUMBER = _get("WHATSAPP_FROM_NUMBER")
WHATSAPP_ACCESS_TOKEN = _get("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _get("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = _get("WHATSAPP_VERIFY_TOKEN")

# Worker
WORKER_INTERVAL_SECONDS = int(_get("WORKER_INTERVAL_SECONDS", "30") or "30")

# Database. When DATABASE_URL is set (a postgres:// URL), leads are stored in
# Postgres instead of the local SQLite file -- needed for persistence on
# ephemeral hosts like Hugging Face free Spaces (their disk resets on rebuild).
DATABASE_URL = _get("DATABASE_URL")

# Local paths
DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")
SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")


# Backups / Additional Providers
GEMINI_API_KEY = _get("GEMINI_API_KEY")
GEMINI_API_KEYS = [k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()] if GEMINI_API_KEY else []
DEEPSEEK_API_KEY = _get("DEEPSEEK_API_KEY")
DEEPSEEK_API_KEYS = [k.strip() for k in DEEPSEEK_API_KEY.split(",") if k.strip()] if DEEPSEEK_API_KEY else []
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get("OPENAI_API_KEY")


def missing_keys() -> list[str]:
    """Return the list of required secrets that are not set, so the UI
    can tell the user exactly what to configure before running. The publishing
    keys required depend on the selected DEPLOY_PROVIDER."""
    # We require AT LEAST ONE AI API KEY.
    ai_keys = [
        AGENTROUTER_API_KEY,
        GEMINI_API_KEY,
        DEEPSEEK_API_KEY,
        ANTHROPIC_API_KEY,
        OPENAI_API_KEY
    ]
    has_ai = any(ai_keys)
    required = {
        "GOOGLE_PLACES_API_KEY": GOOGLE_PLACES_API_KEY,
        "CLOUDFLARE_API_TOKEN": CLOUDFLARE_API_TOKEN,
        "CLOUDFLARE_ACCOUNT_ID": CLOUDFLARE_ACCOUNT_ID,
    }
    missing = [k for k, v in required.items() if not v]
    if not has_ai:
        missing.append("ANY_AI_API_KEY (AGENTROUTER_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY)")
    return missing
