import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,  # 24 hours
) -> tuple[bool, dict]:
    """Validate Telegram WebApp initData HMAC-SHA256 signature.

    Returns (True, parsed_data) on success, (False, {}) on failure.
    parsed_data contains the decoded fields: user dict, auth_date, optional chat dict.

    Algorithm per Telegram docs:
        secret_key = HMAC-SHA256(b"WebAppData", bot_token)
        data_check_string = sorted key=value pairs (excluding hash) joined by \\n
        expected_hash = HMAC-SHA256(data_check_string, secret_key).hexdigest()
    """
    try:
        # Parse URL-encoded initData into an ordered key=value dict
        params = dict(parse_qsl(unquote(init_data), keep_blank_values=True))

        received_hash = params.pop("hash", None)
        if not received_hash:
            return False, {}

        # Build data_check_string: sorted key=value pairs joined by \n
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        # Derive secret key: HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256,
        ).digest()

        # Compute expected hash
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison
        if not hmac.compare_digest(expected_hash, received_hash):
            return False, {}

        # Check auth_date freshness (prevents replay attacks)
        auth_date = int(params.get("auth_date", 0))
        if time.time() - auth_date > max_age_seconds:
            return False, {}

        # Decode nested JSON fields (user, chat, receiver)
        decoded: dict = {}
        for k, v in params.items():
            try:
                decoded[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                decoded[k] = v

        return True, decoded

    except Exception:
        return False, {}
