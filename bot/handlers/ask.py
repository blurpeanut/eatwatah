import asyncio
import html
import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import ensure_user_and_chat, log_error, reactivate_if_needed
from services.recommendation_service import get_recommendations

logger = logging.getLogger(__name__)

_AI_TIMEOUT = 25.0  # seconds — budget covers 3 API calls (parse → Places → AI reasoning)

_FOOD_KEYWORDS = {
    "eat", "food", "restaurant", "cafe", "bar", "hawker", "supper",
    "lunch", "dinner", "breakfast", "ramen", "sushi", "pizza", "burger",
    "chicken", "coffee", "brunch", "dessert", "boba", "noodle", "rice",
    "steak", "seafood", "dim sum", "bbq", "buffet", "recommend", "place",
    "where", "near", "cheap", "budget", "atas", "good", "best", "try",
    "drink", "cuisine", "western", "chinese", "japanese", "korean", "indian",
    "thai", "malay", "halal", "vegetarian", "vegan",
    # vibe / atmosphere words
    "cosy", "cozy", "chill", "romantic", "aesthetic", "lively", "quiet",
    "casual", "fancy", "vibey", "instagrammable", "noisy",
    # discovery intent
    "spot", "spots", "something", "anywhere", "area", "vibes",
}

# Matches "in Bugis", "in the East", "in town" — strong signal for place-seeking
_LOCATION_PATTERN = re.compile(r"\bin\s+\w", re.IGNORECASE)


def _is_food_query(text: str) -> bool:
    lower = text.lower()
    if any(kw in lower for kw in _FOOD_KEYWORDS):
        return True
    # "... in Bugis", "... in Tanjong Pagar" etc. are clearly place-seeking
    if _LOCATION_PATTERN.search(text):
        return True
    return False


# ── /ask command ──────────────────────────────────────────────────────────────

async def ask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/ask called by user %s in chat %s", user.id, chat.id)

    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )
    await reactivate_if_needed(user.id, chat.id, context.bot)

    query_text = " ".join(context.args).strip() if context.args else ""
    if not query_text:
        await update.message.reply_text(
            "What are you in the mood for? 🍜\n\n"
            "Try: /ask something cosy in Bugis\n"
            "Or: /ask birthday dinner, not too formal 🎉"
        )
        return

    if not _is_food_query(query_text):
        await update.message.reply_text(
            "I'm only able to help with food and restaurant recommendations! "
            "Try asking me something like 'good ramen near Orchard' or 'cheap eats in the East' 🍜"
        )
        return

    # Holding message — shown immediately while AI works
    hold = await update.message.reply_text("Hmm let me think... 🤔")

    try:
        results, source_labels, _ = await asyncio.wait_for(
            get_recommendations(query_text, chat.id, user.id),
            timeout=_AI_TIMEOUT,
        )

    except asyncio.TimeoutError:
        logger.warning("/ask timeout for user %s, query=%r", user.id, query_text)
        await log_error(user.id, chat.id, "/ask", "TimeoutError", f"query={query_text!r}")
        await hold.edit_text(
            "Taking too long — try asking again in a moment? 😅"
        )
        return

    except Exception as e:
        logger.error("/ask error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/ask", type(e).__name__, str(e))
        await hold.edit_text(
            "My brain is taking a break right now 🤯 Can't give recs at the moment — "
            "but you can browse your wishlist with /viewwishlist while I recover!"
        )
        return

    if not results:
        await hold.edit_text(
            "Hmm, couldn't find anything matching that 😅\n\n"
            "Try rephrasing — add more detail like the area, vibe, or cuisine type?"
        )
        return

    # ── Format results ────────────────────────────────────────────────────────
    count = len(results)
    lines = [f"Found {count} spot{'s' if count != 1 else ''} for you 👇\n"]

    for i, rec in enumerate(results):
        label = source_labels[i] if i < len(source_labels) else "you might like"
        name = html.escape(rec.get("name", "Unknown"))
        address = html.escape(rec.get("address", ""))
        reason = html.escape(rec.get("reason", ""))
        maps_url = rec.get("maps_url", "")

        maps_link = f' · <a href="{maps_url}">📍 Maps</a>' if maps_url else ""
        lines.append(
            f"<b>{i + 1}. {name}</b> · <i>{html.escape(label)}</i>\n"
            f"{address}{maps_link}"
            + (f"\n{reason}" if reason else "")
        )

    await hold.edit_text(
        "\n\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
