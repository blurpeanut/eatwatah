import logging
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
PLACES_V1_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"

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


# ── Cuisine classification ─────────────────────────────────────────────────

# Ordered: first matching type wins. Each entry is (google_places_type, label).
_CUISINE_PRIORITY: list[tuple[str, str]] = [
    ("japanese_restaurant",     "Japanese"),
    ("chinese_restaurant",      "Chinese"),
    ("korean_restaurant",       "Korean"),
    ("thai_restaurant",         "Southeast Asian"),
    ("vietnamese_restaurant",   "Southeast Asian"),
    ("indonesian_restaurant",   "Southeast Asian"),
    ("indian_restaurant",       "Indian"),
    ("american_restaurant",     "Western"),
    ("western_restaurant",      "Western"),
    ("steak_house",             "Western"),
    ("pizza_restaurant",        "Western"),
    ("italian_restaurant",      "Western"),
    ("french_restaurant",       "Western"),
    ("mediterranean_restaurant","Western"),
    ("seafood_restaurant",      "Seafood"),
    ("cafe",                    "Café"),
    ("coffee_shop",             "Café"),
    ("bakery",                  "Café"),
    ("breakfast_restaurant",    "Café"),
    ("bar",                     "Bar"),
    ("night_club",              "Bar"),
]

# Flat lookup for O(1) per-type check — built from the ordered list above
CUISINE_MAP: dict[str, str] = dict(_CUISINE_PRIORITY)


def classify_cuisine(types: list[str]) -> str:
    """Return a normalised cuisine label given a Google Places types array.

    Iterates _CUISINE_PRIORITY in order; first match wins.
    Returns "Other" when no cuisine-relevant type is present.
    """
    types_set = set(types)
    for gtype, label in _CUISINE_PRIORITY:
        if gtype in types_set:
            return label
    return "Other"


# ── Area reverse geocoding ─────────────────────────────────────────────────

# Maps lowercase Google Maps sublocality/neighborhood names → URA planning area
_URA_NORMALISE: dict[str, str] = {
    # Downtown Core / CBD
    "raffles place":        "Downtown Core",
    "marina bay":           "Downtown Core",
    "marina centre":        "Downtown Core",
    "tanjong pagar":        "Downtown Core",
    "anson":                "Downtown Core",
    "telok ayer":           "Downtown Core",
    "cecil":                "Downtown Core",
    "downtown core":        "Downtown Core",
    # Outram
    "chinatown":            "Outram",
    "outram":               "Outram",
    # Museum / Bras Basah
    "bras basah":           "Museum",
    "city hall":            "Museum",
    "dhoby ghaut":          "Museum",
    "museum":               "Museum",
    # Rochor
    "bugis":                "Rochor",
    "middle road":          "Rochor",
    "golden mile":          "Rochor",
    "little india":         "Rochor",
    "kampong glam":         "Rochor",
    "rochor":               "Rochor",
    # Singapore River
    "clarke quay":          "Singapore River",
    "robertson quay":       "Singapore River",
    "boat quay":            "Singapore River",
    "riverside":            "Singapore River",
    "singapore river":      "Singapore River",
    # River Valley
    "river valley":         "River Valley",
    # Orchard
    "orchard":              "Orchard",
    "cairnhill":            "Orchard",
    # Newton
    "newton":               "Newton",
    # Novena / Thomson
    "novena":               "Novena",
    "thomson":              "Thomson",
    "upper thomson":        "Thomson",
    # Central
    "toa payoh":            "Toa Payoh",
    "bishan":               "Bishan",
    "ang mo kio":           "Ang Mo Kio",
    "serangoon":            "Serangoon",
    # Tanglin
    "tanglin":              "Tanglin",
    "dempsey":              "Tanglin",
    # Bukit Timah
    "bukit timah":          "Bukit Timah",
    "holland village":      "Bukit Timah",
    "holland":              "Bukit Timah",
    # Queenstown / Buona Vista
    "queenstown":           "Queenstown",
    "buona vista":          "Queenstown",
    "dover":                "Queenstown",
    # Bukit Merah
    "tiong bahru":          "Bukit Merah",
    "bukit merah":          "Bukit Merah",
    "harbourfront":         "Bukit Merah",
    "telok blangah":        "Bukit Merah",
    "alexandra":            "Bukit Merah",
    # Kallang
    "kallang":              "Kallang",
    "lavender":             "Kallang",
    "bendemeer":            "Kallang",
    "boon keng":            "Kallang",
    # East
    "geylang":              "Geylang",
    "eunos":                "Geylang",
    "aljunied":             "Geylang",
    "macpherson":           "Geylang",
    "paya lebar":           "Paya Lebar",
    "katong":               "Marine Parade",
    "joo chiat":            "Marine Parade",
    "marine parade":        "Marine Parade",
    "east coast":           "Marine Parade",
    "bedok":                "Bedok",
    "upper east coast":     "Bedok",
    "changi":               "Changi",
    "loyang":               "Changi",
    "tampines":             "Tampines",
    "pasir ris":            "Pasir Ris",
    # North-East
    "hougang":              "Hougang",
    "sengkang":             "Sengkang",
    "punggol":              "Punggol",
    # West
    "clementi":             "Clementi",
    "west coast":           "Clementi",
    "jurong east":          "Jurong East",
    "jurong west":          "Jurong West",
    "jurong":               "Jurong East",
    "bukit batok":          "Bukit Batok",
    "bukit panjang":        "Bukit Panjang",
    "choa chu kang":        "Choa Chu Kang",
    "boon lay":             "Boon Lay",
    # North
    "woodlands":            "Woodlands",
    "yishun":               "Yishun",
    "sembawang":            "Sembawang",
    "mandai":               "Mandai",
    "seletar":              "Seletar",
    "lim chu kang":         "Lim Chu Kang",
}

# Postal district (first 2 digits of 6-digit SG postal code) → URA area
_POSTAL_DISTRICT_AREA: dict[str, str] = {
    "01": "Downtown Core", "02": "Downtown Core",
    "03": "Bukit Merah",   "04": "Bukit Merah",
    "05": "Clementi",      "06": "Rochor",
    "07": "Rochor",        "08": "Rochor",
    "09": "Orchard",       "10": "Tanglin",
    "11": "Novena",        "12": "Toa Payoh",
    "13": "Toa Payoh",     "14": "Geylang",
    "15": "Marine Parade", "16": "Bedok",
    "17": "Changi",        "18": "Tampines",
    "19": "Hougang",       "20": "Bishan",
    "21": "Bukit Timah",   "22": "Jurong East",
    "23": "Bukit Panjang", "24": "Lim Chu Kang",
    "25": "Woodlands",     "26": "Mandai",
    "27": "Yishun",        "28": "Seletar",
    "29": "Toa Payoh",     "30": "Thomson",
    "31": "Toa Payoh",     "33": "Serangoon",
    "34": "Geylang",       "36": "Hougang",
    "37": "Hougang",       "38": "Hougang",
    "39": "Sengkang",      "40": "Punggol",
    "44": "Pasir Ris",     "45": "Pasir Ris",
    "46": "Tampines",      "47": "Tampines",
    "48": "Tampines",      "49": "Clementi",
    "53": "Queenstown",    "54": "Queenstown",
    "55": "Queenstown",    "56": "Queenstown",
    "59": "Bukit Timah",   "60": "Bukit Timah",
    "61": "Paya Lebar",    "62": "Geylang",
    "63": "Bedok",         "64": "Bedok",
    "65": "Bedok",         "68": "Choa Chu Kang",
    "69": "Choa Chu Kang", "70": "Choa Chu Kang",
    "71": "Bukit Panjang", "74": "Jurong West",
    "75": "Jurong West",   "76": "Jurong West",
}

_SG_POSTAL_RE = re.compile(r"Singapore\s+(\d{6})", re.IGNORECASE)


async def reverse_geocode_area(lat: float, lng: float) -> str:
    """Reverse geocode lat/lng to a URA planning area name.

    Calls the Google Maps Geocoding API, extracts the sublocality_level_1
    or neighborhood component, and normalises it against _URA_NORMALISE.
    Falls back to a postal district lookup if no sublocality is found.
    Returns "Others" if nothing resolves.
    """
    if not PLACES_API_KEY:
        return "Others"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                GEOCODING_URL,
                params={"latlng": f"{lat},{lng}", "key": PLACES_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("reverse_geocode_area failed for (%s, %s): %s", lat, lng, e)
        return "Others"

    results = data.get("results", [])
    if not results:
        return "Others"

    # Primary: sublocality_level_1 or neighborhood component
    for result in results:
        for component in result.get("address_components", []):
            comp_types = component.get("types", [])
            if "sublocality_level_1" in comp_types or "neighborhood" in comp_types:
                raw = component.get("long_name", "").lower().strip()
                if raw in _URA_NORMALISE:
                    return _URA_NORMALISE[raw]

    # Fallback: postal district from formatted_address
    for result in results:
        m = _SG_POSTAL_RE.search(result.get("formatted_address", ""))
        if m:
            district = m.group(1)[:2]
            if district in _POSTAL_DISTRICT_AREA:
                return _POSTAL_DISTRICT_AREA[district]

    return "Others"


# ── Legacy area helpers (kept for reference; replaced by reverse_geocode_area) ─

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
            "types": place.get("types", []),
        })

    return results
