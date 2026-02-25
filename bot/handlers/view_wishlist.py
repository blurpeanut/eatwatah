import html
import io
import logging
import math
import os

import httpx
from PIL import Image, ImageDraw, ImageFont

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Chat, Update, WebAppInfo
from telegram.ext import ContextTypes

from db.context import is_private_chat
from db.helpers import (
    ensure_user_and_chat,
    get_user_display_names,
    get_wishlist_entries,
    log_error,
    reactivate_if_needed,
)

logger = logging.getLogger(__name__)

# Singapore region grouping
AREA_TO_REGION: dict[str, str] = {
    # Central
    "Orchard": "Central", "Newton": "Central", "Novena": "Central",
    "Toa Payoh": "Central", "Bishan": "Central", "Braddell": "Central",
    "Chinatown": "Central", "Tanjong Pagar": "Central",
    "Clarke Quay": "Central", "Raffles Place": "Central",
    "Marina Bay": "Central", "Bugis": "Central", "Rochor": "Central",
    "Little India": "Central", "Dhoby Ghaut": "Central",
    "River Valley": "Central", "Robertson Quay": "Central",
    "Boat Quay": "Central", "Outram": "Central", "Tiong Bahru": "Central",
    "Queenstown": "Central", "Redhill": "Central", "Lavender": "Central",
    "Harbourfront": "Central", "Sentosa": "Central",
    "Holland Village": "Central", "Dempsey": "Central", "Buona Vista": "Central",
    # East
    "East Coast": "East", "Bedok": "East", "Tampines": "East",
    "Pasir Ris": "East", "Changi": "East", "Tanah Merah": "East",
    "Paya Lebar": "East", "Marine Parade": "East", "Siglap": "East",
    "Katong": "East", "Tanjong Katong": "East", "Joo Chiat": "East",
    "Geylang": "East", "Kallang": "East",
    # North
    "Woodlands": "North", "Sembawang": "North",
    "Yishun": "North", "Ang Mo Kio": "North",
    # North-East
    "Hougang": "North-East", "Sengkang": "North-East",
    "Punggol": "North-East", "Serangoon": "North-East",
    # West
    "Jurong": "West", "Clementi": "West",
    "Bukit Timah": "West", "Choa Chu Kang": "West",
}
REGION_ORDER = ["Central", "East", "North", "North-East", "West", "Other"]


# ── Static map helpers ────────────────────────────────────────────────────────

_TILE = 256  # Google Maps tile size in pixels


def _project(lat: float, lng: float) -> tuple[float, float]:
    """Lat/lng → Web Mercator world coordinates in the [0, 1] range."""
    x = (lng + 180) / 360
    sin_lat = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    return x, y


def _fit_zoom(entries, img_w: int, img_h: int, max_zoom: int = 16) -> tuple[float, float, int]:
    """Return (center_lat, center_lng, zoom) that fits all entries in the image."""
    lats = [e.lat for e in entries]
    lngs = [e.lng for e in entries]
    center_lat = (min(lats) + max(lats)) / 2
    center_lng = (min(lngs) + max(lngs)) / 2

    if len(entries) == 1:
        return center_lat, center_lng, 15

    wx_vals = [_project(e.lat, e.lng)[0] for e in entries]
    wy_vals = [_project(e.lat, e.lng)[1] for e in entries]
    dx = max(wx_vals) - min(wx_vals)
    dy = max(wy_vals) - min(wy_vals)

    pad = 0.20  # 20% padding on each axis
    for zoom in range(max_zoom, 8, -1):
        scale = _TILE * (2 ** zoom)
        if dx * scale <= img_w * (1 - pad) and dy * scale <= img_h * (1 - pad):
            return center_lat, center_lng, zoom

    return center_lat, center_lng, 9


def _to_pixel(lat: float, lng: float, c_lat: float, c_lng: float,
              zoom: int, pix_w: int, pix_h: int) -> tuple[int, int]:
    """Convert lat/lng to pixel position in the rendered static map image."""
    scale = _TILE * (2 ** zoom)
    cx, cy = _project(c_lat, c_lng)
    wx, wy = _project(lat, lng)
    px = int((wx - cx) * scale + pix_w / 2)
    py = int((wy - cy) * scale + pix_h / 2)
    return px, py


def _pil_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


async def _build_static_map_image(entries) -> bytes | None:
    """Fetch a Google Static Map and draw dot + semi-transparent name labels on it.

    Returns JPEG bytes, or None if the map can't be generated.
    Falls back to the unlabelled map bytes if PIL drawing fails.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        return None

    with_coords = [e for e in entries if e.lat is not None and e.lng is not None]
    if not with_coords:
        return None

    IMG_W, IMG_H, SCALE = 600, 300, 2
    PIX_W, PIX_H = IMG_W * SCALE, IMG_H * SCALE

    center_lat, center_lng, zoom = _fit_zoom(with_coords, IMG_W, IMG_H)

    # Plain base map — no markers in the URL, PIL draws everything
    url = (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?size={IMG_W}x{IMG_H}&scale={SCALE}"
        f"&center={center_lat},{center_lng}&zoom={zoom}"
        f"&maptype=roadmap&style=feature:poi|visibility:off"
        f"&key={api_key}"
    )

    # Fetch base map
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            logger.warning("Static map fetch: %s %s", resp.status_code, resp.headers.get("content-type", ""))
            return None
        raw_bytes = resp.content
    except Exception as e:
        logger.warning("Static map fetch error: %s", e)
        return None

    # Draw labels with PIL
    try:
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = _pil_font(22)

        DOT_R = 10
        ORANGE = (255, 107, 53, 255)
        GREEN  = (52, 168, 83, 255)
        WHITE  = (255, 255, 255, 255)
        LABEL_BG = (0, 0, 0, 150)

        for entry in with_coords:
            # _to_pixel works in logical pixels (IMG_W×IMG_H); multiply by SCALE
            # to get actual pixel position in the retina image (PIX_W×PIX_H).
            _lx, _ly = _to_pixel(entry.lat, entry.lng, center_lat, center_lng, zoom, IMG_W, IMG_H)
            px, py = _lx * SCALE, _ly * SCALE
            if not (DOT_R <= px <= PIX_W - DOT_R and DOT_R <= py <= PIX_H - DOT_R):
                continue

            color = GREEN if entry.status == "visited" else ORANGE

            # Solid dot
            draw.ellipse([px - DOT_R, py - DOT_R, px + DOT_R, py + DOT_R],
                         fill=color, outline=WHITE, width=2)

            # Label text
            label = entry.name if len(entry.name) <= 20 else entry.name[:19] + "\u2026"
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad_x, pad_y = 8, 5
            lw, lh = tw + pad_x * 2, th + pad_y * 2

            # Place label to the right; flip left if it would overflow
            lx = px + DOT_R + 4
            if lx + lw > PIX_W - 4:
                lx = px - DOT_R - lw - 4
            ly = py - lh // 2

            draw.rounded_rectangle([lx, ly, lx + lw, ly + lh],
                                   radius=lh // 2, fill=LABEL_BG)
            draw.text((lx + pad_x, ly + pad_y), label, font=font, fill=WHITE)

        result = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        result.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    except Exception as e:
        logger.warning("Static map label draw failed: %s — returning unlabelled", e)
        return raw_bytes  # graceful fallback: send the unlabelled map


def _get_region(area: str | None) -> str:
    if not area:
        return "Other"
    return AREA_TO_REGION.get(area, "Other")


def _fmt_date(dt) -> str:
    return f"{dt.day} {dt.strftime('%b')}"


async def show_wishlist(message: Message, chat, user) -> None:
    """Display the wishlist. Called from view_wishlist_handler and start.py quick action."""
    try:
        await ensure_user_and_chat(
            telegram_id=user.id,
            display_name=user.full_name or user.username or "Friend",
            chat_id=chat.id,
            chat_type=chat.type,
            chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
        )

        entries = await get_wishlist_entries(chat.id)

        if not entries:
            await message.reply_text(
                "Your wishlist is empty! Use /add to start building your list 👀"
            )
            return

        webapp_base = os.getenv("WEBAPP_BASE_URL", "").strip().rstrip("/")

        # ── WebApp mode: static map preview + open button ───────────────────
        if webapp_base:
            count = len(entries)
            webapp_url = f"{webapp_base}/webapp/index.html"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗺 Open map", web_app=WebAppInfo(url=webapp_url))
            ]])
            caption = f"You've got {count} place{'s' if count != 1 else ''} saved 👇"

            image_bytes = await _build_static_map_image(entries)
            if image_bytes:
                try:
                    await message.reply_photo(
                        photo=image_bytes,
                        caption=caption,
                        reply_markup=keyboard,
                    )
                    return
                except Exception as e:
                    logger.warning("Static map reply_photo failed: %s", e)

            await message.reply_text(caption, reply_markup=keyboard)
            return

        # ── Fallback: text list (no WebApp configured) ─────────────────────
        added_by_ids = list({e.added_by for e in entries})
        display_names = await get_user_display_names(added_by_ids)

        grouped: dict[str, list] = {r: [] for r in REGION_ORDER}
        for entry in entries:
            grouped[_get_region(entry.area)].append(entry)

        lines = [f"📋 <b>Your Wishlist</b> — {len(entries)} place{'s' if len(entries) != 1 else ''}\n"]

        for region in REGION_ORDER:
            region_entries = grouped[region]
            if not region_entries:
                continue
            lines.append(f"\n📍 <b>{region}</b>")
            for entry in region_entries:
                adder = display_names.get(entry.added_by, "Someone")
                adder_label = "You" if entry.added_by == str(user.id) else html.escape(adder)
                note_line = f"\n   📝 {html.escape(entry.notes)}" if entry.notes else ""
                lines.append(
                    f"\n🔖 <b>{html.escape(entry.name)}</b>\n"
                    f"   {html.escape(entry.address)}\n"
                    f"   Added by {adder_label} · {_fmt_date(entry.date_added)}"
                    + note_line
                )

        await message.reply_html("\n".join(lines))

    except Exception as e:
        logger.error("show_wishlist error for user %s: %s", user.id, e)
        await log_error(user.id, chat.id, "/viewwishlist", type(e).__name__, str(e))
        await message.reply_text(
            "Something went wrong on our end — not your fault! Try again in a bit 🙏"
        )


async def view_wishlist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    logger.info("/viewwishlist called by user %s in chat %s", user.id, chat.id)
    await ensure_user_and_chat(
        telegram_id=user.id,
        display_name=user.full_name or user.username or "Friend",
        chat_id=chat.id,
        chat_type=chat.type,
        chat_name=None if is_private_chat(chat.id, user.id) else (chat.title or "Group"),
    )
    await reactivate_if_needed(user.id, chat.id, context.bot)
    await show_wishlist(update.message, chat, user)
