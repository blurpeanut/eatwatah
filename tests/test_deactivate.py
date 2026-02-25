"""
Tests for /deactivate feature.

Unit tests: reactivate_if_needed (4 cases)
Handler tests: deactivate_handler (2 cases)

All DB and bot interactions are mocked — no real DB or Telegram connection needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(
    telegram_id: str = "111",
    is_deactivated: bool = False,
    is_deleted: bool = False,
) -> MagicMock:
    user = MagicMock()
    user.telegram_id = telegram_id
    user.is_deactivated = is_deactivated
    user.is_deleted = is_deleted
    return user


def _make_session(db_user):
    """Return a mock async session whose scalar() resolves to db_user."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=db_user)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # Support async context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _make_session_factory(db_user):
    """Return a mock AsyncSessionLocal context manager backed by _make_session."""
    session = _make_session(db_user)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


# ── reactivate_if_needed ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reactivate_deactivated_user():
    """Deactivated user: flag cleared, welcome-back message sent, returns True."""
    from db.helpers import reactivate_if_needed

    db_user = _make_user(is_deactivated=True)
    factory, session = _make_session_factory(db_user)
    bot = AsyncMock()

    with patch("db.helpers.AsyncSessionLocal", factory):
        result = await reactivate_if_needed("111", "999", bot)

    assert result is True
    assert db_user.is_deactivated is False
    session.commit.assert_awaited_once()
    bot.send_message.assert_awaited_once()
    sent_text = bot.send_message.call_args.kwargs["text"]
    assert "Welcome back" in sent_text


@pytest.mark.asyncio
async def test_reactivate_active_user():
    """Active user: no DB write, no message, returns False."""
    from db.helpers import reactivate_if_needed

    db_user = _make_user(is_deactivated=False, is_deleted=False)
    factory, session = _make_session_factory(db_user)
    bot = AsyncMock()

    with patch("db.helpers.AsyncSessionLocal", factory):
        result = await reactivate_if_needed("111", "999", bot)

    assert result is False
    session.commit.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reactivate_deleted_user():
    """is_deleted user: no DB write, no message, returns False."""
    from db.helpers import reactivate_if_needed

    db_user = _make_user(is_deleted=True)
    factory, session = _make_session_factory(db_user)
    bot = AsyncMock()

    with patch("db.helpers.AsyncSessionLocal", factory):
        result = await reactivate_if_needed("111", "999", bot)

    assert result is False
    session.commit.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reactivate_nonexistent_user():
    """User not in DB: returns False without error."""
    from db.helpers import reactivate_if_needed

    factory, session = _make_session_factory(None)
    bot = AsyncMock()

    with patch("db.helpers.AsyncSessionLocal", factory):
        result = await reactivate_if_needed("999", "999", bot)

    assert result is False
    session.commit.assert_not_awaited()
    bot.send_message.assert_not_awaited()


# ── deactivate_handler ────────────────────────────────────────────────────────

def _make_update(user_id: int = 111, chat_id: int = 111):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.full_name = "Test User"
    update.effective_user.username = "testuser"
    update.effective_chat.id = chat_id
    update.effective_chat.type = "private"
    update.effective_chat.title = None
    update.message.reply_text = AsyncMock()
    return update


def _make_context(bot=None):
    context = MagicMock()
    context.bot = bot or AsyncMock()
    return context


@pytest.mark.asyncio
async def test_deactivate_active_user():
    """Active user calling /deactivate: flag set True, confirmation message sent."""
    from bot.handlers.deactivate import deactivate_handler

    db_user = _make_user(is_deactivated=False)
    factory, session = _make_session_factory(db_user)
    update = _make_update()
    context = _make_context()

    with (
        patch("db.helpers.AsyncSessionLocal", factory),
        patch("bot.handlers.deactivate.AsyncSessionLocal", factory),
        patch("bot.handlers.deactivate.ensure_user_and_chat", AsyncMock()),
        patch("bot.handlers.deactivate.reactivate_if_needed", AsyncMock(return_value=False)),
    ):
        await deactivate_handler(update, context)

    assert db_user.is_deactivated is True
    session.commit.assert_awaited_once()
    update.message.reply_text.assert_awaited_once()
    sent_text = update.message.reply_text.call_args.args[0]
    assert "deactivated" in sent_text.lower()
    assert "/deleteaccount" in sent_text


@pytest.mark.asyncio
async def test_deactivate_already_deactivated_user():
    """User already deactivated: guard fires, no DB write, no reply sent."""
    from bot.handlers.deactivate import deactivate_handler

    # After reactivate_if_needed runs (and doesn't reactivate because the mock
    # returns False), the scalar query finds the user still deactivated.
    db_user = _make_user(is_deactivated=True)
    factory, session = _make_session_factory(db_user)
    update = _make_update()
    context = _make_context()

    with (
        patch("db.helpers.AsyncSessionLocal", factory),
        patch("bot.handlers.deactivate.AsyncSessionLocal", factory),
        patch("bot.handlers.deactivate.ensure_user_and_chat", AsyncMock()),
        patch("bot.handlers.deactivate.reactivate_if_needed", AsyncMock(return_value=False)),
    ):
        await deactivate_handler(update, context)

    session.commit.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()
