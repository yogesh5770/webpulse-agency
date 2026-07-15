"""Lead discovery + enrichment via Google Places API.

Strategy for finding businesses WITHOUT a website:
  1. Text Search for a category+location (e.g. "salon in Chennai").
  2. For each result, fetch Place Details.
  3. Keep only places whose `website` field is empty  -> that's a lead.
  4. Capture name, phone, address, geo, and photo references.
"""
import json

import requests

import config

_TEXT_SEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"
_PHOTO = "https://maps.googleapis.com/maps/api/place/photo"


def _details(place_id: str) -> dict:
    fields = (
        "name,formatted_phone_number,international_phone_number,formatted_address,"
        "geometry,website,url,types,photos,opening_hours,rating,user_ratings_total,"
        "business_status,editorial_summary,reviews,price_level"
    )
    resp = requests.get(
        _DETAILS,
        params={
            "place_id": place_id,
            "fields": fields,
            "key": config.GOOGLE_PLACES_API_KEY,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def photo_url(photo_ref: str, maxwidth: int = 1200) -> str:
    """Build a direct, usable image URL for a Google photo reference."""
    return (
        f"{_PHOTO}?maxwidth={maxwidth}"
        f"&photo_reference={photo_ref}&key={config.GOOGLE_PLACES_API_KEY}"
    )


def find_leads(query: str, max_results: int) -> list[dict]:
    """Return normalized lead dicts for businesses that have NO website."""
    resp = requests.get(
        _TEXT_SEARCH,
        params={"query": query, "key": config.GOOGLE_PLACES_API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])[:max_results]

    leads = []
    for r in results:
        place_id = r.get("place_id")
        if not place_id:
            continue
        d = _details(place_id)

        if not _qualifies(d):
            continue

        photos = [p.get("photo_reference") for p in d.get("photos", []) if p.get("photo_reference")]
        geo = d.get("geometry", {}).get("location", {})
        types = d.get("types", [])
        category = _readable_category(types)
        phone = d.get("formatted_phone_number") or d.get("international_phone_number") or ""

        # Top few reviews give the generator real, human wording for the copy.
        reviews = [
            {"author": rv.get("author_name"), "rating": rv.get("rating"), "text": (rv.get("text") or "")[:400]}
            for rv in (d.get("reviews") or [])[:4]
            if rv.get("text")
        ]

        leads.append(
            {
                "place_id": place_id,
                "name": d.get("name", r.get("name", "")),
                "category": category,
                "phone": phone,
                "address": d.get("formatted_address", ""),
                "lat": geo.get("lat"),
                "lng": geo.get("lng"),
                "photos_json": json.dumps(photos[:8]),
                "details_json": json.dumps(
                    {
                        "rating": d.get("rating"),
                        "reviews_count": d.get("user_ratings_total"),
                        "hours": d.get("opening_hours", {}).get("weekday_text", []),
                        "types": types,
                        "summary": (d.get("editorial_summary") or {}).get("overview", ""),
                        "price_level": d.get("price_level"),
                        "maps_url": d.get("url", ""),
                        "reviews": reviews,
                    }
                ),
            }
        )
    return leads


# ---- qualification: only businesses worth building a site for ---------

def _qualifies(d: dict) -> bool:
    """A lead is worth pursuing only if it (a) has no website, (b) is
    operational, and (c) has enough info to build a credible page."""
    if d.get("website"):
        return False                         # already has a site -> skip
    if d.get("business_status") not in (None, "OPERATIONAL"):
        return False                         # closed / temporarily closed -> skip
    if not d.get("name"):
        return False
    # Need at least a way to contact them AND some visual/social proof,
    # otherwise the generated site would be too thin to sell.
    has_contact = bool(d.get("formatted_phone_number") or d.get("international_phone_number"))
    has_material = bool(d.get("photos")) or bool(d.get("user_ratings_total"))
    return has_contact and has_material


def _readable_category(types: list) -> str:
    """Pick the most business-descriptive type, skipping generic ones."""
    generic = {"point_of_interest", "establishment", "store"}
    for t in types or []:
        if t not in generic:
            return t.replace("_", " ")
    return (types[0].replace("_", " ") if types else "business")
