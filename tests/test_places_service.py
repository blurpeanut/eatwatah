"""Unit tests for classify_cuisine() and reverse_geocode_area()."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.places_service import classify_cuisine, reverse_geocode_area


# ── classify_cuisine ──────────────────────────────────────────────────────────

def test_classify_cuisine_japanese():
    assert classify_cuisine(["japanese_restaurant", "restaurant", "food"]) == "Japanese"


def test_classify_cuisine_cafe():
    assert classify_cuisine(["cafe", "food", "establishment"]) == "Café"


def test_classify_cuisine_western_pizza():
    # pizza_restaurant maps to Western; italian_restaurant also maps to Western —
    # priority order means pizza_restaurant fires first in _CUISINE_PRIORITY,
    # but both map to the same label so either way the result is Western.
    assert classify_cuisine(["pizza_restaurant", "italian_restaurant", "food"]) == "Western"


def test_classify_cuisine_unknown():
    assert classify_cuisine(["restaurant", "food", "point_of_interest"]) == "Other"


# ── reverse_geocode_area ──────────────────────────────────────────────────────

def _make_geocode_response(sublocality: str | None = None, postal: str | None = None) -> dict:
    """Build a minimal Geocoding API response."""
    components = []
    if sublocality:
        components.append({
            "long_name": sublocality,
            "types": ["sublocality_level_1", "sublocality", "political"],
        })
    formatted = f"Some St, Singapore {postal}" if postal else "Some St, Singapore"
    return {
        "results": [
            {
                "address_components": components,
                "formatted_address": formatted,
            }
        ],
        "status": "OK",
    }


@pytest.mark.asyncio
async def test_reverse_geocode_area_sublocality_match():
    """Sublocality 'Orchard' normalises to URA area 'Orchard'."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_geocode_response(sublocality="Orchard")

    with patch("services.places_service.PLACES_API_KEY", "fake-key"), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await reverse_geocode_area(1.3048, 103.8318)

    assert result == "Orchard"


@pytest.mark.asyncio
async def test_reverse_geocode_area_postal_fallback():
    """No sublocality returned — falls back to postal district '09' → 'Orchard'."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_geocode_response(sublocality=None, postal="098765")

    with patch("services.places_service.PLACES_API_KEY", "fake-key"), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await reverse_geocode_area(1.3048, 103.8318)

    assert result == "Orchard"


@pytest.mark.asyncio
async def test_reverse_geocode_area_no_results():
    """API returns empty results list — should return 'Others'."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": [], "status": "ZERO_RESULTS"}

    with patch("services.places_service.PLACES_API_KEY", "fake-key"), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await reverse_geocode_area(0.0, 0.0)

    assert result == "Others"
