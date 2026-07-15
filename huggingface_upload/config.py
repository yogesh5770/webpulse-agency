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
AGENTROUTER_MODEL = _get("AGENTROUTER_MODEL", "claude-opus-4-8")

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
# Which host to deploy generated sites to: "cloudflare" (default, unlimited
# free, no project caps) or "netlify".
DEPLOY_PROVIDER = _get("DEPLOY_PROVIDER", "cloudflare").lower()

# Netlify
NETLIFY_AUTH_TOKEN = _get("NETLIFY_AUTH_TOKEN")

# Cloudflare Pages. Every business is deployed to ONE project on its own
# branch, so it gets a stable URL like https://<branch>.<project>.pages.dev
# with no per-project limit.
CLOUDFLARE_API_TOKEN = _get("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = _get("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_PAGES_PROJECT = _get("CLOUDFLARE_PAGES_PROJECT", "lead-sites")

# WhatsApp
WHATSAPP_FROM_NUMBER = _get("WHATSAPP_FROM_NUMBER")

# Worker
WORKER_INTERVAL_SECONDS = int(_get("WORKER_INTERVAL_SECONDS", "30") or "30")

# Database. When DATABASE_URL is set (a postgres:// URL), leads are stored in
# Postgres instead of the local SQLite file -- needed for persistence on
# ephemeral hosts like Hugging Face free Spaces (their disk resets on rebuild).
DATABASE_URL = _get("DATABASE_URL")

# Local paths
DB_PATH = os.path.join(os.path.dirname(__file__), "leads.db")
SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")


def missing_keys() -> list[str]:
    """Return the list of required secrets that are not set, so the UI
    can tell the user exactly what to configure before running. The publishing
    keys required depend on the selected DEPLOY_PROVIDER."""
    required = {
        "AGENTROUTER_BASE_URL": AGENTROUTER_BASE_URL,
        "AGENTROUTER_API_KEY": AGENTROUTER_API_KEY,
        "GOOGLE_PLACES_API_KEY": GOOGLE_PLACES_API_KEY,
    }
    if DEPLOY_PROVIDER == "netlify":
        required["NETLIFY_AUTH_TOKEN"] = NETLIFY_AUTH_TOKEN
    else:  # cloudflare
        required["CLOUDFLARE_API_TOKEN"] = CLOUDFLARE_API_TOKEN
        required["CLOUDFLARE_ACCOUNT_ID"] = CLOUDFLARE_ACCOUNT_ID
    return [k for k, v in required.items() if not v]
