"""District-by-district lead search queries.

Discovery systematically sweeps EVERY district in EVERY state (Tamil Nadu
first). A persistent cursor in the DB remembers how far we've walked, so the
24/7 worker keeps advancing across the country and resumes where it left off
after a restart.

For each (state, district) we iterate the business niches. When AI queries are
enabled, Opus is told the exact state+district to target so it varies the
neighbourhood/town within that district; otherwise we fall back to a plain
"<niche> in <district>, <state>, India" query. Every produced query is recorded
so it is never repeated.
"""
import json

import config
import db
from agent_router import chat_text
from india_districts import DISTRICTS

# Business types that commonly have NO website -> good targets.
_NICHES = [
    "salon", "barber shop", "beauty parlour", "spa", "gym", "fitness center",
    "tailor", "boutique", "bakery", "cafe", "restaurant", "sweet shop",
    "dentist clinic", "physiotherapy clinic", "pet grooming", "car wash",
    "car repair garage", "tattoo studio", "yoga studio", "dance studio",
    "florist", "photography studio", "event planner", "interior designer",
    "hardware store", "mobile repair shop", "coaching center", "play school",
]

_CUR_KEY = "district_cursor"  # stores "districtIndex:nicheIndex"


def _used_queries() -> set[str]:
    return {q.lower() for q in db.get_used_queries()}


def _read_cursor() -> tuple[int, int]:
    raw = db.get_state(_CUR_KEY, "0:0")
    try:
        d, n = raw.split(":")
        return int(d), int(n)
    except (ValueError, AttributeError):
        return 0, 0


def _write_cursor(d_idx: int, n_idx: int) -> None:
    db.set_state(_CUR_KEY, f"{d_idx}:{n_idx}")


def _advance(d_idx: int, n_idx: int) -> tuple[int, int]:
    """Move to the next niche; when a district's niches are exhausted, move to
    the next district. Wraps back to the start after the whole grid."""
    n_idx += 1
    if n_idx >= len(_NICHES):
        n_idx = 0
        d_idx += 1
        if d_idx >= len(DISTRICTS):
            d_idx = 0
    return d_idx, n_idx


def _plain_query(niche: str, state: str, district: str) -> str:
    return f"{niche} in {district}, {state}, India"


def _ai_query(niche: str, state: str, district: str, used: set[str]) -> str:
    """Ask Opus for one specific Places query inside this district, varying the
    town/neighbourhood. Falls back to the plain query on any problem."""
    prompt = (
        "You generate ONE Google Places text-search query to find LOCAL "
        f"'{niche}' businesses that usually have NO website, located inside "
        f"{district} district, {state}, India.\n"
        "Pick a specific town, locality or neighbourhood WITHIN that district "
        "so the query surfaces real local businesses. Format exactly: "
        "'<business type> in <specific area>, <district>'.\n"
        f"Do NOT reuse any of these already-used queries: {json.dumps(sorted(used)[:40])}.\n"
        "Return ONLY the query text, nothing else."
    )
    try:
        q = chat_text(
            [{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=40,
        ).strip().strip('"').splitlines()[0].strip()
    except Exception:
        q = ""
    if not q or q.lower() in used:
        return _plain_query(niche, state, district)
    return q


def next_query() -> str:
    """Return a fresh search query for the current district, then advance the
    cursor. The query is recorded so it won't be produced again."""
    used = _used_queries()
    d_idx, n_idx = _read_cursor()

    # Try up to a full grid sweep to find a niche/district that yields a new
    # query, so we never hand back a duplicate or get stuck.
    attempts = len(DISTRICTS) * len(_NICHES)
    for _ in range(attempts):
        state, district = DISTRICTS[d_idx]
        niche = _NICHES[n_idx]

        if config.LEAD_AI_QUERIES:
            q = _ai_query(niche, state, district, used)
        else:
            q = _plain_query(niche, state, district)

        # Advance the cursor for next time (persisted) BEFORE returning.
        d_idx, n_idx = _advance(d_idx, n_idx)
        _write_cursor(d_idx, n_idx)

        if q.lower() not in used:
            db.add_used_query(q)
            return q
        # else: this combo was already used -> loop to the next one.

    # Whole grid exhausted (every combo used at least once): reuse first slot.
    state, district = DISTRICTS[0]
    return _plain_query(_NICHES[0], state, district)
