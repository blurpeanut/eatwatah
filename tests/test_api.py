"""
Tests for API auth and wishlist endpoint.

Unit tests cover validate_init_data() directly (the critical security logic).
Integration tests cover the /api/wishlist endpoint using FastAPI's TestClient
— they test auth rejection without needing a real DB connection.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from api.auth import validate_init_data

_BOT_TOKEN = "test_bot_token_abc123"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_init_data(
    user_id: int = 12345,
    chat_id: int | None = None,
    bot_token: str = _BOT_TOKEN,
    age_seconds: int = 0,
) -> str:
    """Build a valid Telegram WebApp initData string signed with bot_token."""
    params: dict[str, str] = {
        "user": json.dumps({"id": user_id, "first_name": "Tester"}),
        "auth_date": str(int(time.time()) - age_seconds),
    }
    if chat_id is not None:
        params["chat"] = json.dumps({"id": chat_id, "type": "group"})

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)


# ── Unit tests: validate_init_data ────────────────────────────────────────────

def test_valid_init_data_returns_true_and_user():
    init_data = _make_init_data(user_id=99)
    ok, data = validate_init_data(init_data, _BOT_TOKEN)

    assert ok is True
    assert isinstance(data, dict)
    assert data["user"]["id"] == 99


def test_valid_init_data_with_group_chat():
    init_data = _make_init_data(user_id=11, chat_id=-100987654)
    ok, data = validate_init_data(init_data, _BOT_TOKEN)

    assert ok is True
    assert data["chat"]["id"] == -100987654


def test_invalid_hash_is_rejected():
    ok, data = validate_init_data(
        "user=%7B%22id%22%3A1%7D&auth_date=9999999999&hash=deadbeef00",
        _BOT_TOKEN,
    )
    assert ok is False
    assert data == {}


def test_wrong_bot_token_is_rejected():
    init_data = _make_init_data(user_id=42, bot_token="correct_token")
    ok, data = validate_init_data(init_data, "wrong_token")

    assert ok is False
    assert data == {}


def test_expired_auth_date_is_rejected():
    # 25 hours ago — beyond the 24-hour window
    init_data = _make_init_data(user_id=1, age_seconds=25 * 3600)
    ok, data = validate_init_data(init_data, _BOT_TOKEN)

    assert ok is False
    assert data == {}


def test_missing_hash_is_rejected():
    ok, data = validate_init_data("user=%7B%22id%22%3A1%7D&auth_date=9999999999", _BOT_TOKEN)
    assert ok is False
    assert data == {}


def test_empty_string_is_rejected():
    ok, data = validate_init_data("", _BOT_TOKEN)
    assert ok is False
    assert data == {}


# ── Integration tests: /api/wishlist endpoint ─────────────────────────────────

def test_endpoint_returns_403_on_invalid_init_data(monkeypatch):
    """Endpoint rejects requests with a bad initData hash before hitting the DB."""
    import api.routes.wishlist as wl_module
    monkeypatch.setattr(wl_module, "_get_bot_token", lambda: _BOT_TOKEN)

    from api.main import app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/api/wishlist?chat_id=12345",
        headers={"X-Telegram-Init-Data": "user=%7B%7D&auth_date=0&hash=badhash"},
    )
    assert response.status_code == 403


def test_endpoint_returns_403_on_mismatched_chat_id(monkeypatch):
    """Endpoint rejects requests where chat_id doesn't match initData user/chat."""
    import api.routes.wishlist as wl_module
    monkeypatch.setattr(wl_module, "_get_bot_token", lambda: _BOT_TOKEN)

    from api.main import app
    client = TestClient(app, raise_server_exceptions=False)

    # Valid initData for user 99, but requesting chat_id=9999 (not their chat)
    init_data = _make_init_data(user_id=99)
    response = client.get(
        "/api/wishlist?chat_id=9999",
        headers={"X-Telegram-Init-Data": init_data},
    )
    assert response.status_code == 403
