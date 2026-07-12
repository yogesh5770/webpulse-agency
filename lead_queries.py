"""AI-driven lead search queries.

Instead of one fixed search string, ask Opus to generate fresh, varied
Google Places queries (business niche x location) so the 24/7 worker keeps
finding NEW leads instead of re-scanning the same area. Used queries are
persisted so we never repeat one, and there's an offline fallback rotation
if the model is unavailable.
"""
import json

import config
import db
from agent_router import chat_text

# Businesses that commonly have NO website -> good targets. Used only by the
# offline fallback; the AI path invents its own, wider variety.
_FALLBACK_NICHES = [
    "salon", "barber shop", "gym", "spa", "beauty parlour", "tailor",
    "bakery", "cafe", "dentist clinic", "pet grooming", "car wash",
    "tattoo studio", "yoga studio", "florist", "photography studio",
]

# Major cities/towns across India, so the offline fallback (and the AI hint)
# spread lead discovery nationwide instead of one city. Kept broad on purpose.
# --- Tamil Nadu, comprehensively (home market -> cover it FULLY) ---
_TN_CITIES = [
    "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem",
    "Tirunelveli", "Tiruppur", "Erode", "Vellore", "Thoothukudi",
    "Dindigul", "Thanjavur", "Ranipet", "Sivakasi", "Karur", "Hosur",
    "Nagercoil", "Kanchipuram", "Kumbakonam", "Cuddalore", "Tiruvannamalai",
    "Pollachi", "Rajapalayam", "Pudukkottai", "Neyveli", "Nagapattinam",
    "Viluppuram", "Tiruchengode", "Vaniyambadi", "Theni", "Namakkal",
    "Krishnagiri", "Dharmapuri", "Virudhunagar", "Ramanathapuram",
    "Sivaganga", "Ooty", "Kovilpatti", "Arakkonam", "Gudiyatham",
]

# --- The rest of India (metros + tier-2) -> cover the country too ---
_REST_INDIA_CITIES = [
    "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Kolkata", "Pune",
    "Ahmedabad", "Jaipur", "Surat", "Lucknow", "Kanpur", "Nagpur", "Indore",
    "Bhopal", "Kochi", "Visakhapatnam", "Patna", "Vadodara", "Ludhiana",
    "Agra", "Nashik", "Varanasi", "Rajkot", "Amritsar", "Chandigarh",
    "Guwahati", "Thiruvananthapuram", "Mysuru", "Mangaluru", "Vijayawada",
    "Bhubaneswar", "Dehradun", "Jodhpur", "Raipur", "Ranchi", "Gwalior",
    "Jabalpur", "Aurangabad", "Noida", "Gurugram", "Faridabad", "Ghaziabad",
    "Meerut", "Kozhikode", "Warangal", "Guntur", "Jalandhar", "Udaipur",
]

# Tamil Nadu first (priority), then the rest of India.
_INDIA_CITIES = _TN_CITIES + _REST_INDIA_CITIES


def _used_queries() -> set[str]:
    return {q.lower() for q in db.get_used_queries()}


def _fallback_query(used: set[str]) -> str:
    """Deterministic rotation of (niche x city) ACROSS INDIA, so discovery
    keeps finding new businesses nationwide even without the AI generator.
    Iterates city-major so we spread across the country quickly."""
    for niche in _FALLBACK_NICHES:
        for city in _INDIA_CITIES:
            q = f"{niche} in {city}"
            if q.lower() not in used:
                return q
    # Everything used at least once -> allow reuse (whole grid exhausted).
    return f"{_FALLBACK_NICHES[0]} in {_INDIA_CITIES[0]}"


def next_query() -> str:
    """Return a fresh search query. Uses Opus when enabled, else the rotation.
    The returned query is recorded so it won't be produced again."""
    used = _used_queries()

    if not config.LEAD_AI_QUERIES:
        q = _fallback_query(used)
        db.add_used_query(q)
        return q

    prompt = (
        "You generate Google Places text-search queries to find LOCAL "
        "businesses that typically have NO website (salons, gyms, small "
        f"shops, clinics, etc.) in and around: {config.LEAD_REGION}.\n"
        "Vary the business type AND the specific town/neighbourhood so each "
        "query surfaces different businesses. Return ONE query only, format "
        "'<business type> in <specific area>'. Do NOT reuse any of these "
        f"already-used queries: {json.dumps(sorted(used)[:60])}.\n"
        "Return ONLY the query text, nothing else."
    )
    try:
        q = chat_text(
            [{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=40,
        ).strip().strip('"').splitlines()[0]
    except Exception:
        q = ""

    if not q or q.lower() in used:
        q = _fallback_query(used)
    db.add_used_query(q)
    return q
