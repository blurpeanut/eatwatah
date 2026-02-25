import html
import logging
from collections import defaultdict

from telegram import Update
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import ensure_user_and_chat, get_visits_for_chat, log_error, reactivate_if_needed

logger = logging.getLogger(__name__)

STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}
OCCASION_EMOJI = {
    "Casual": "🍽", "Special": "🎉", "Work": "💼", "Spontaneous": "⚡",
}


def _fmt_date(dt) -> str:
    return f"{dt.day} {dt.strftime('%b %Y')}"


async def view_visited_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/viewvisited called by user %s in chat %s", user.id, chat.id)

    try:
        await ensure_user_and_chat(
            telegram_id=user.id,
            display_name=user.full_name or user.username or "Friend",
            chat_id=chat.id,
            chat_type=chat.type,
            chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
        )
        await reactivate_if_needed(user.id, chat.id, context.bot)

        rows = await get_visits_for_chat(chat.id)

        if not rows:
            await update.message.reply_text(
                "Nothing logged yet! Use /visit after your next meal 🍽"
            )
            return

        # Group by place, preserving most-recently-visited order
        # Use an ordered dict: place_id → list of visit rows
        seen_order: list[str] = []
        by_place: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            pid = row["visit"].google_place_id
            if pid not in by_place:
                seen_order.append(pid)
            by_place[pid].append(row)

        lines = [f"✅ <b>Visited Places</b> — {len(seen_order)} spot{'s' if len(seen_order) != 1 else ''}\n"]

        for pid in seen_order:
            place_rows = by_place[pid]
            place_name = place_rows[0]["place_name"]

            lines.append(f"\n📍 <b>{html.escape(place_name)}</b>")

            # Deduplicate to most recent visit per user
            latest_by_user: dict[str, dict] = {}
            for r in place_rows:
                uid = r["visit"].logged_by
                if uid not in latest_by_user:
                    latest_by_user[uid] = r

            # Ratings line
            rating_parts = []
            for uid, r in latest_by_user.items():
                v = r["visit"]
                name_label = "You" if uid == str(user.id) else html.escape(r["user_name"])
                stars = STARS.get(v.rating, "—") if v.rating else "—"
                rating_parts.append(f"{name_label}: {stars}")
            lines.append("   " + "  |  ".join(rating_parts))

            # Occasion + date (from most recent overall visit)
            latest = place_rows[0]["visit"]
            occ = latest.occasion or ""
            occ_emoji = OCCASION_EMOJI.get(occ, "🍽")
            lines.append(f"   {occ_emoji} {occ or 'Casual'} · {_fmt_date(latest.visited_at)}")

            # Review snippet (most recent review that has text)
            for r in place_rows:
                if r["visit"].review:
                    snippet = r["visit"].review[:80]
                    if len(r["visit"].review) > 80:
                        snippet += "…"
                    lines.append(f'   <i>"{html.escape(snippet)}"</i>')
                    break

        # Telegram messages cap at 4096 chars — split if needed
        full_text = "\n".join(lines)
        if len(full_text) <= 4096:
            await update.message.reply_html(full_text)
        else:
            # Send in chunks of ~4000 chars, splitting on double newlines
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) + 1 > 4000:
                    await update.message.reply_html(chunk)
                    chunk = line
                else:
                    chunk += "\n" + line
            if chunk:
                await update.message.reply_html(chunk)

    except Exception as e:
        logger.error("/viewvisited error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/viewvisited", type(e).__name__, str(e))
        await update.message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )
