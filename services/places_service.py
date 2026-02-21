import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
PLACES_V1_URL = "https://places.googleapis.com/v1/places:searchText"

# Fields to request — new API returns nothing without an explicit field mask
FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.addressComponents,"
    "places.rating,"
    "places.types,"
    "places.googleMapsUri,"
    "places.location"
)

# Singapore geographic centre + radius covering the whole island
SG_LAT = 1.3521
SG_LNG = 103.8198
SG_RADIUS_M = 40000

# Known Singapore districts for area extraction
SINGAPORE_AREAS = [
    "Orchard", "Bugis", "Clarke Quay", "Chinatown", "Tanjong Pagar",
    "Marina Bay", "Raffles Place", "Newton", "Tiong Bahru", "Katong",
    "Tanjong Katong", "Bedok", "Tampines", "Pasir Ris", "Hougang",
    "Sengkang", "Punggol", "Jurong", "Clementi", "Buona Vista",
    "Holland Village", "Dempsey", "Novena", "Bishan", "Ang Mo Kio",
    "Yishun", "Woodlands", "Sembawang", "Choa Chu Kang", "Bukit Timah",
    "Changi", "Tanah Merah", "Paya Lebar", "Geylang", "Lavender",
    "Toa Payoh", "Little India", "Rochor", "Kallang", "Marine Parade",
    "Siglap", "East Coast", "Dhoby Ghaut", "Harbourfront", "Sentosa",
    "Robertson Quay", "Boat Quay", "Outram", "Queenstown", "Redhill",
    "River Valley", "Joo Chiat", "Serangoon", "Braddell",
]


def extract_area(address: str) -> str | None:
    """Try to extract a Singapore district name from a formatted address string."""
    for area in SINGAPORE_AREAS:
        if area.lower() in address.lower():
            return area
    return None


def _area_from_components(components: list[dict]) -> str | None:
    """Try to extract a known Singapore area from addressComponents."""
    for component in components:
        types = component.get("types", [])
        if any(t in types for t in ("sublocality_level_1", "neighborhood")):
            text = component.get("longText") or component.get("shortText") or ""
            for area in SINGAPORE_AREAS:
                if area.lower() in text.lower():
                    return area
    return None


async def search_places(query: str, max_results: int = 3) -> list[dict]:
    """Search using the Google Places API v1 (new).

    Returns list of up to max_results place dicts.
    Returns [] when no results are found.
    Raises RuntimeError on API or network errors.
    """
    if not PLACES_API_KEY:
        raise RuntimeError("GOOGLE_PLACES_API_KEY not set")

    # Bias toward Singapore results
    text_query = query if "singapore" in query.lower() else f"{query} Singapore"

    payload = {
        "textQuery": text_query,
        "maxResultCount": max(1, min(max_results, 20)),  # API caps at 20
        "locationBias": {
            "circle": {
                "center": {"latitude": SG_LAT, "longitude": SG_LNG},
                "radius": SG_RADIUS_M,
            }
        },
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": PLACES_API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(PLACES_V1_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        raise RuntimeError("Places API timeout")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Places API HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        raise RuntimeError(f"Places API request failed: {e}")

    places = data.get("places", [])
    if not places:
        return []

    results = []
    for place in places:
        location = place.get("location", {})
        address = place.get("formattedAddress", "")
        place_id = place.get("id", "")
        area = _area_from_components(place.get("addressComponents", [])) or extract_area(address)
        results.append({
            "place_id": place_id,
            "name": place.get("displayName", {}).get("text", ""),
            "address": address,
            "area": area,
            "lat": location.get("latitude"),
            "lng": location.get("longitude"),
            "rating": place.get("rating"),
            "maps_url": place.get("googleMapsUri", f"https://www.google.com/maps/place/?q=place_id:{place_id}"),
        })

    return results
