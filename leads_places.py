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
        "name,formatted_phone_number,formatted_address,geometry,"
        "website,types,photos,opening_hours,rating,user_ratings_total"
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

        # Core filter: no website == a lead we can sell to.
        if d.get("website"):
            continue

        photos = [p.get("photo_reference") for p in d.get("photos", []) if p.get("photo_reference")]
        geo = d.get("geometry", {}).get("location", {})
        types = d.get("types", [])
        category = types[0].replace("_", " ") if types else "business"

        leads.append(
            {
                "place_id": place_id,
                "name": d.get("name", r.get("name", "")),
                "category": category,
                "phone": d.get("formatted_phone_number", ""),
                "address": d.get("formatted_address", ""),
                "lat": geo.get("lat"),
                "lng": geo.get("lng"),
                "photos_json": json.dumps(photos[:6]),
                "details_json": json.dumps(
                    {
                        "rating": d.get("rating"),
                        "reviews": d.get("user_ratings_total"),
                        "hours": d.get("opening_hours", {}).get("weekday_text", []),
                        "types": types,
                    }
                ),
            }
        )
    return leads
