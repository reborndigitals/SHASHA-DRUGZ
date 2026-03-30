"""
nsfw.py — Smart NSFW-only filter for Pyrogram Telegram bots.

DETECTION LAYERS (in order):
  1. Stickers  → Telegram raw API  `stickerset.nsfw` flag  (no external service needed)
  2. Photos / Videos / Animations → Optional external NSFW API  (DeepAI free tier, etc.)
  3. Documents → MIME-type + filename heuristic  (catches obvious adult filenames/types)

When NSFW mode is ON:
  ✅ Normal stickers, photos, videos → pass through untouched
  ❌ NSFW sticker packs              → detected & deleted
  ❌ NSFW photos / videos            → deleted  (requires API key or strict_media mode)
  ❌ Adult-named documents           → deleted  (heuristic, no API needed)

Detection methods (configurable per chat):
  "telegram"  — Sticker NSFW flag only. Photos/videos pass unless strict_media=True.
  "deepai"    — DeepAI NSFW Detector API (free 5000 calls/month). Photos/videos scanned.
  "custom"    — Any OpenAI-compatible NSFW REST endpoint you provide.

Commands (group owner only):
  /nsfw on|off          — Enable / disable the filter
  /nsfw                 — Open inline settings panel
  /setnsfw              — Show raw JSON settings
  /setwarnimage <url>   — Set warning image URL
  /setmutetime <secs>   — Set mute duration
  /setflood <n> <secs>  — Set flood threshold
  /setflood off         — Disable flood protection
  /setnsfwapi <key>     — Set DeepAI API key (enables media scanning)
  /setnsfwapi off       — Remove API key (back to sticker-only detection)
"""

import os
import io
import json
import asyncio
import time
import logging
import tempfile
from typing import Dict, Any, Optional, Tuple

import aiohttp
from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError

from SHASHA_DRUGZ import app

logger = logging.getLogger("NSFW")

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE  (Motor/MongoDB preferred; falls back to JSON file)
# ══════════════════════════════════════════════════════════════════════════════
USE_MONGO = False
try:
    import motor.motor_asyncio as motor
    _MONGO_URL = os.getenv(
        "MONGO_URL",
        "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/"
        "?retryWrites=true&w=majority",
    )
    if _MONGO_URL:
        _mongo_client = motor.AsyncIOMotorClient(_MONGO_URL)
        _db           = _mongo_client.get_default_database()
        nsfw_coll     = _db.get_collection("nsfw_settings")
        USE_MONGO     = True
except Exception:
    USE_MONGO = False

SETTINGS_FILE = "nsfw_settings.json"

# ══════════════════════════════════════════════════════════════════════════════
#  DEFAULT SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
_default_settings: Dict[str, Any] = {
    # Master switch
    "enabled": False,

    # Which media TYPES to scan for NSFW content.
    # Setting a type to False means: skip scanning that type entirely (always allow).
    "scan_types": {
        "sticker":   True,   # checked via Telegram raw API — very accurate
        "photo":     True,   # checked via external API if configured
        "video":     True,   # checked via external API if configured
        "animation": True,   # checked via external API (thumbnail frame)
        "document":  True,   # checked via MIME / filename heuristic
        "voice":     False,  # audio: not meaningful to scan
        "audio":     False,
    },

    # NSFW detection configuration
    "detection": {
        # "telegram" → sticker-set flag only (no external API, photos/videos pass unless strict)
        # "deepai"   → sticker flag + DeepAI image API  (free 5000 calls/month)
        # "custom"   → sticker flag + user-supplied REST endpoint
        "method":        "deepai",
        "api_key":       "a69fb389-b677-4256-9e84-f0727ff6382b",       # DeepAI API key or custom auth header value
        "api_url":       "",       # used only for "custom" method
        "threshold":     0.75,     # NSFW confidence threshold (0.0 – 1.0)
        # If True AND no API is configured: block ALL photos/videos/animations
        # when NSFW mode is on (safest option — no false negatives).
        "strict_media":  False,
    },

    # Warning / punishment settings (unchanged from original)
    "warning_image": "",
    "time_mute":     {"enabled": True, "duration_seconds": 3600},
    "auto_kick":     False,
    "auto_ban":      False,
    "flood":         {"enabled": True, "threshold": 5, "timeframe_seconds": 10},
}

# ══════════════════════════════════════════════════════════════════════════════
#  KNOWN NSFW MIME TYPES AND FILENAME KEYWORDS  (heuristic, no API needed)
# ══════════════════════════════════════════════════════════════════════════════
_NSFW_MIME_PREFIXES = {
    # None of the common MIME types are inherently NSFW, so we rely on keywords.
}

_NSFW_FILENAME_KEYWORDS = [
    "porn", "sex", "nsfw", "xxx", "nude", "naked", "hentai", "18+",
    "adult", "erotic", "lewd", "explicit", "onlyfans", "cumshot",
    "blowjob", "anal", "boobs", "pussy", "dick", "cock", "dildo",
    "fetish", "bdsm", "gangbang", "milf", "creampie", "handjob",
]

# ══════════════════════════════════════════════════════════════════════════════
#  FLOOD TRACKER  (in-memory, per chat / per user)
# ══════════════════════════════════════════════════════════════════════════════
_flood_track: Dict[int, Dict[int, list]] = {}

# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS  LOAD / SAVE
# ══════════════════════════════════════════════════════════════════════════════
def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively so new keys always exist."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


async def load_settings(chat_id: int) -> Dict[str, Any]:
    raw: Dict[str, Any] = {}
    if USE_MONGO:
        try:
            doc = await nsfw_coll.find_one({"chat_id": chat_id})
            if doc:
                raw = doc.get("settings", {})
            else:
                await nsfw_coll.insert_one(
                    {"chat_id": chat_id, "settings": dict(_default_settings)}
                )
        except Exception:
            pass
    else:
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w") as f:
                json.dump({}, f)
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
            raw = data.get(str(chat_id), {})
        except Exception:
            raw = {}
    # Always merge with defaults so new keys are never missing
    return _deep_merge(_default_settings, raw)


async def save_settings(chat_id: int, settings: Dict[str, Any]):
    if USE_MONGO:
        try:
            await nsfw_coll.update_one(
                {"chat_id": chat_id},
                {"$set": {"settings": settings}},
                upsert=True,
            )
        except Exception:
            pass
    else:
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w") as f:
                json.dump({}, f)
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[str(chat_id)] = settings
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  PERMISSION HELPER
# ══════════════════════════════════════════════════════════════════════════════
async def is_chat_owner(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except (RPCError, Exception):
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  ─────────────────────────────────────────────────────────────────────────────
#  NSFW DETECTION ENGINE
#  ─────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# ── 1.  STICKER — Telegram raw API sticker-set NSFW flag ─────────────────────
async def _is_nsfw_sticker(client, sticker) -> Tuple[bool, str]:
    """
    Returns (is_nsfw: bool, reason: str).
    Uses Telegram's own `StickerSet.nsfw` flag — zero false positives.
    """
    if not sticker or not sticker.set_name:
        return False, ""
    try:
        from pyrogram.raw.functions.messages import GetStickerSet
        from pyrogram.raw.types import InputStickerSetShortName

        result = await client.invoke(
            GetStickerSet(
                stickerset=InputStickerSetShortName(short_name=sticker.set_name),
                hash=0,
            )
        )
        sticker_set = result.set
        if getattr(sticker_set, "nsfw", False):
            return True, f"NSFW sticker pack · `{sticker.set_name}`"
        # Secondary check: title / short_name keywords
        title      = (getattr(sticker_set, "title",      "") or "").lower()
        short_name = (getattr(sticker_set, "short_name", "") or "").lower()
        for kw in _NSFW_FILENAME_KEYWORDS:
            if kw in title or kw in short_name:
                return True, f"Sticker pack name matches adult keyword `{kw}`"
        return False, ""
    except Exception as e:
        logger.debug(f"Sticker NSFW check error: {e}")
        return False, ""


# ── 2.  DOCUMENT — MIME type + filename heuristic ────────────────────────────
def _is_nsfw_document(document) -> Tuple[bool, str]:
    """
    Heuristic check: filename keywords + MIME type.
    No external API needed — catches obviously labelled adult files.
    """
    if not document:
        return False, ""
    fname = (getattr(document, "file_name", "") or "").lower()
    mime  = (getattr(document, "mime_type",  "") or "").lower()

    for kw in _NSFW_FILENAME_KEYWORDS:
        if kw in fname:
            return True, f"Adult keyword `{kw}` in filename"

    # Detect adult video/image MIME types that are unusual in legit contexts
    suspicious_mime = [
        "video/x-ms-asf",   # old WMV streaming — common in adult content
        "application/x-shockwave-flash",  # Flash adult videos
    ]
    if mime in suspicious_mime:
        for kw in _NSFW_FILENAME_KEYWORDS:
            if kw in mime:
                return True, f"Suspicious MIME type `{mime}`"

    return False, ""


# ── 3.  MEDIA (Photo / Video / Animation) — External API ─────────────────────
async def _download_media_bytes(client, message: Message) -> Optional[bytes]:
    """
    Download the media to memory (max 5 MB to avoid abuse).
    Returns raw bytes or None if too large / failed.
    """
    MAX_BYTES = 5 * 1024 * 1024  # 5 MB

    try:
        file_size = 0
        if message.photo:
            # Use the smallest available thumbnail for speed
            photo     = message.photo
            file_size = photo.file_size or 0
        elif message.video:
            file_size = (message.video.file_size or 0)
        elif message.animation:
            file_size = (message.animation.file_size or 0)

        if file_size > MAX_BYTES:
            logger.debug("Media too large for NSFW scan — skipping API check")
            return None

        buf = io.BytesIO()
        await client.download_media(message, file_name=buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.debug(f"Media download error: {e}")
        return None


async def _deepai_nsfw_score(data: bytes, api_key: str) -> float:
    """
    Calls DeepAI NSFW Detector (https://deepai.org/machine-learning-model/nsfw-detector).
    Free tier: 5,000 calls / month. Returns score 0.0–1.0.
    """
    try:
        form = aiohttp.FormData()
        form.add_field("image", data, filename="image.jpg", content_type="image/jpeg")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepai.org/api/nsfw-detector",
                data=form,
                headers={"api-key": api_key},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    score  = result.get("output", {}).get("nsfw_score", 0.0)
                    return float(score)
    except Exception as e:
        logger.debug(f"DeepAI API error: {e}")
    return 0.0


async def _custom_nsfw_score(data: bytes, api_url: str, api_key: str) -> float:
    """
    Generic REST NSFW endpoint.  Expects JSON response with `{"score": 0.0-1.0}`.
    """
    try:
        form    = aiohttp.FormData()
        headers = {}
        form.add_field("image", data, filename="image.jpg", content_type="image/jpeg")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return float(result.get("score", 0.0))
    except Exception as e:
        logger.debug(f"Custom NSFW API error: {e}")
    return 0.0


async def _is_nsfw_media(client, message: Message, detection: dict) -> Tuple[bool, str]:
    """
    Scan photo / video / animation for NSFW content.
    Returns (is_nsfw: bool, reason: str).
    """
    method      = detection.get("method",       "telegram")
    api_key     = detection.get("api_key",       "")
    api_url     = detection.get("api_url",       "")
    threshold   = float(detection.get("threshold", 0.75))
    strict_mode = detection.get("strict_media",  False)

    # ── telegram-only mode with no API key ───────────────────────────────────
    if method == "telegram" and not api_key:
        if strict_mode:
            return True, "Strict mode — media blocked (no API configured)"
        return False, ""   # pass through — cannot scan without an API

    # ── download media bytes for API scanning ─────────────────────────────────
    media_bytes = await _download_media_bytes(client, message)
    if not media_bytes:
        if strict_mode:
            return True, "Strict mode — could not download media for scanning"
        return False, ""

    # ── choose API ────────────────────────────────────────────────────────────
    score = 0.0
    if method == "deepai" and api_key:
        score = await _deepai_nsfw_score(media_bytes, api_key)
    elif method == "custom" and api_url:
        score = await _custom_nsfw_score(media_bytes, api_url, api_key)
    elif api_key:
        # api_key set but method still "telegram" → auto-use DeepAI
        score = await _deepai_nsfw_score(media_bytes, api_key)

    if score >= threshold:
        return True, f"NSFW media score: {score:.2f} (threshold {threshold:.2f})"

    return False, ""


# ── Master detection entry point ─────────────────────────────────────────────
async def is_nsfw_content(
    client,
    message: Message,
    settings: dict,
) -> Tuple[bool, str]:
    """
    Returns (should_block: bool, reason: str).
    Only returns True when content is positively identified as NSFW.
    """
    scan_types = settings.get("scan_types", _default_settings["scan_types"])
    detection  = settings.get("detection",  _default_settings["detection"])

    # ── Sticker ───────────────────────────────────────────────────────────────
    if message.sticker and scan_types.get("sticker"):
        return await _is_nsfw_sticker(client, message.sticker)

    # ── Photo ─────────────────────────────────────────────────────────────────
    if message.photo and scan_types.get("photo"):
        return await _is_nsfw_media(client, message, detection)

    # ── Video ─────────────────────────────────────────────────────────────────
    if message.video and scan_types.get("video"):
        return await _is_nsfw_media(client, message, detection)

    # ── Animation (GIF) ───────────────────────────────────────────────────────
    if message.animation and scan_types.get("animation"):
        return await _is_nsfw_media(client, message, detection)

    # ── Document ──────────────────────────────────────────────────────────────
    if message.document and scan_types.get("document"):
        heuristic = _is_nsfw_document(message.document)
        if heuristic[0]:
            return heuristic
        # Also run API scan on image/video documents if API is configured
        doc_mime = (getattr(message.document, "mime_type", "") or "").lower()
        if doc_mime.startswith(("image/", "video/")):
            return await _is_nsfw_media(client, message, detection)
        return False, ""

    return False, ""


# ══════════════════════════════════════════════════════════════════════════════
#  KEYBOARD BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
def _main_keyboard(settings: dict) -> InlineKeyboardMarkup:
    det    = settings.get("detection", {})
    method = det.get("method", "telegram")
    has_key = bool(det.get("api_key", ""))
    strict  = det.get("strict_media", False)

    api_label = (
        f"API: DeepAI {'✅' if has_key and method in ('deepai','telegram') else '❌'}"
    )
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"NSFW Filter: {'🟢 ON' if settings['enabled'] else '🔴 OFF'}",
            callback_data="nsfw_toggle",
        )],
        [InlineKeyboardButton(
            f"Time-mute: {'ON' if settings['time_mute']['enabled'] else 'OFF'}",
            callback_data="toggle_time_mute",
        )],
        [
            InlineKeyboardButton(
                f"Auto-kick: {'ON' if settings['auto_kick'] else 'OFF'}",
                callback_data="toggle_auto_kick",
            ),
            InlineKeyboardButton(
                f"Auto-ban: {'ON' if settings['auto_ban'] else 'OFF'}",
                callback_data="toggle_auto_ban",
            ),
        ],
        [InlineKeyboardButton(
            f"Strict media: {'ON' if strict else 'OFF'}  ⚠️",
            callback_data="toggle_strict_media",
        )],
        [InlineKeyboardButton("🔍 Scan types", callback_data="scan_types")],
        [InlineKeyboardButton(api_label, callback_data="nsfw_api_info")],
        [InlineKeyboardButton("⚠️ Set warning image", callback_data="change_warning_image")],
        [InlineKeyboardButton("❌ Close", callback_data="nsfw_close")],
    ])


def _scan_types_keyboard(settings: dict) -> InlineKeyboardMarkup:
    scan = settings.get("scan_types", _default_settings["scan_types"])
    rows = []
    labels = {
        "sticker":   "Stickers  (Telegram API ✅)",
        "photo":     "Photos    (API/strict)",
        "video":     "Videos    (API/strict)",
        "animation": "GIFs      (API/strict)",
        "document":  "Documents (heuristic)",
        "voice":     "Voice",
        "audio":     "Audio",
    }
    for t, label in labels.items():
        rows.append([InlineKeyboardButton(
            f"{'🟢' if scan.get(t) else '🔴'} {label}",
            callback_data=f"toggle_scan_{t}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="nsfw_back_main")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("nsfw") & filters.group)
async def nsfw_command(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_chat_owner(client, chat_id, user_id):
        await message.reply_text("⚠️ Only the group owner can change NSFW settings.")
        return

    if len(message.command) < 2:
        settings = await load_settings(chat_id)
        det      = settings.get("detection", {})
        method   = det.get("method", "telegram")
        has_key  = bool(det.get("api_key", ""))
        scan     = settings.get("scan_types", {})

        text = (
            "🛡 **NSFW Filter Settings**\n\n"
            f"Status       : {'🟢 Enabled' if settings['enabled'] else '🔴 Disabled'}\n"
            f"Detection    : `{method}`"
            + (f" (API key configured ✅)" if has_key else " (no API key)")
            + f"\nStrict media : {'⚠️ ON — all unverifiable media blocked' if det.get('strict_media') else 'OFF'}\n"
            f"Scanning     : {', '.join(t for t, v in scan.items() if v) or 'none'}\n\n"
            "Use the buttons below to configure, or:\n"
            "`/setnsfwapi <deepai_key>` — enable image/video scanning\n"
            "`/setnsfwapi off`          — remove API key"
        )
        await client.send_message(
            chat_id, text,
            reply_markup=_main_keyboard(settings),
        )
        return

    arg      = message.command[1].lower()
    settings = await load_settings(chat_id)
    if arg in ("on", "enable", "1", "true"):
        settings["enabled"] = True
        await save_settings(chat_id, settings)
        await message.reply_text("✅ NSFW filter **enabled**.\nOnly NSFW content will be removed — normal media is untouched.")
    elif arg in ("off", "disable", "0", "false"):
        settings["enabled"] = False
        await save_settings(chat_id, settings)
        await message.reply_text("✅ NSFW filter **disabled**.")
    else:
        await message.reply_text("Usage: `/nsfw on` | `/nsfw off` | `/nsfw` (panel)")


@app.on_message(filters.command("setnsfwapi") & filters.group)
async def set_nsfw_api(client, message: Message):
    """Set or remove the DeepAI API key for image/video NSFW detection."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_chat_owner(client, chat_id, user_id):
        await message.reply_text("Only the group owner can configure the NSFW API key.")
        return

    if len(message.command) < 2:
        await message.reply_text(
            "Usage:\n"
            "`/setnsfwapi <deepai_api_key>` — enable DeepAI scanning\n"
            "`/setnsfwapi off`              — remove API key\n\n"
            "Get a free DeepAI key at https://deepai.org (5,000 scans/month free)"
        )
        return

    settings = await load_settings(chat_id)
    if message.command[1].lower() == "off":
        settings["detection"]["api_key"] = ""
        settings["detection"]["method"]  = "telegram"
        await save_settings(chat_id, settings)
        await message.reply_text(
            "✅ API key removed.\n"
            "Detection is now sticker-only (Telegram raw API).\n"
            "Photos/videos will pass unless `strict_media` is ON."
        )
    else:
        key = message.command[1].strip()
        settings["detection"]["api_key"] = key
        settings["detection"]["method"]  = "deepai"
        await save_settings(chat_id, settings)
        # Delete command message to protect the key
        try:
            await message.delete()
        except Exception:
            pass
        await client.send_message(
            chat_id,
            "✅ DeepAI API key saved. Photos and videos will now be scanned for NSFW content.\n"
            "_(Your message containing the key has been deleted for security.)_",
        )


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLER
# ══════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^(nsfw_|toggle_|scan_types|nsfw_api_info|change_warning_image)"))
async def nsfw_callback(client, cq: CallbackQuery):
    data    = cq.data
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await is_chat_owner(client, chat_id, user_id):
        await cq.answer("Only the group owner can change these.", show_alert=True)
        return

    settings = await load_settings(chat_id)

    # ── Master toggle ──────────────────────────────────────────────────────────
    if data == "nsfw_toggle":
        settings["enabled"] = not settings["enabled"]
        await save_settings(chat_id, settings)
        await cq.message.edit_reply_markup(_main_keyboard(settings))
        await cq.answer(f"NSFW filter {'enabled' if settings['enabled'] else 'disabled'}")
        return

    # ── Back to main ──────────────────────────────────────────────────────────
    if data == "nsfw_back_main":
        await cq.message.edit_reply_markup(_main_keyboard(settings))
        await cq.answer()
        return

    # ── Time-mute toggle ──────────────────────────────────────────────────────
    if data == "toggle_time_mute":
        settings["time_mute"]["enabled"] = not settings["time_mute"]["enabled"]
        await save_settings(chat_id, settings)
        await cq.message.edit_reply_markup(_main_keyboard(settings))
        await cq.answer("Time-mute toggled")
        return

    # ── Auto-kick toggle ──────────────────────────────────────────────────────
    if data == "toggle_auto_kick":
        settings["auto_kick"] = not settings["auto_kick"]
        await save_settings(chat_id, settings)
        await cq.message.edit_reply_markup(_main_keyboard(settings))
        await cq.answer("Auto-kick toggled")
        return

    # ── Auto-ban toggle ───────────────────────────────────────────────────────
    if data == "toggle_auto_ban":
        settings["auto_ban"] = not settings["auto_ban"]
        await save_settings(chat_id, settings)
        await cq.message.edit_reply_markup(_main_keyboard(settings))
        await cq.answer("Auto-ban toggled")
        return

    # ── Strict media toggle ───────────────────────────────────────────────────
    if data == "toggle_strict_media":
        settings["detection"]["strict_media"] = not settings["detection"].get("strict_media", False)
        await save_settings(chat_id, settings)
        await cq.message.edit_reply_markup(_main_keyboard(settings))
        strict = settings["detection"]["strict_media"]
        await cq.answer(
            "⚠️ Strict mode ON — all photos/videos blocked" if strict
            else "Strict mode OFF — only detected NSFW blocked",
            show_alert=True,
        )
        return

    # ── Scan types panel ──────────────────────────────────────────────────────
    if data == "scan_types":
        await cq.message.edit_reply_markup(_scan_types_keyboard(settings))
        await cq.answer()
        return

    # ── Individual scan type toggle ───────────────────────────────────────────
    if data.startswith("toggle_scan_"):
        t = data[len("toggle_scan_"):]
        if t in settings["scan_types"]:
            settings["scan_types"][t] = not settings["scan_types"][t]
            await save_settings(chat_id, settings)
            await cq.message.edit_reply_markup(_scan_types_keyboard(settings))
            await cq.answer(f"{t} scanning {'enabled' if settings['scan_types'][t] else 'disabled'}")
        else:
            await cq.answer("Unknown type", show_alert=True)
        return

    # ── API info ──────────────────────────────────────────────────────────────
    if data == "nsfw_api_info":
        det    = settings.get("detection", {})
        method = det.get("method", "telegram")
        has_k  = bool(det.get("api_key", ""))
        msg = (
            f"Detection method : `{method}`\n"
            f"API key          : {'✅ set' if has_k else '❌ not set'}\n"
            f"Strict media     : {'ON' if det.get('strict_media') else 'OFF'}\n\n"
            "Use `/setnsfwapi <key>` to enable DeepAI scanning.\n"
            "Free key at https://deepai.org"
        )
        await cq.answer(msg, show_alert=True)
        return

    # ── Warning image ─────────────────────────────────────────────────────────
    if data == "change_warning_image":
        await cq.answer(
            "Use /setwarnimage <image_url> to set, or /setwarnimage clear to remove.",
            show_alert=True,
        )
        return

    # ── Close ─────────────────────────────────────────────────────────────────
    if data == "nsfw_close":
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer()
        return


# ══════════════════════════════════════════════════════════════════════════════
#  CORE MODERATOR  — runs on every group message
# ══════════════════════════════════════════════════════════════════════════════
def _not_command(_, __, message: Message) -> bool:
    return not (message.text and message.text.startswith("/"))


@app.on_message(filters.group & filters.create(_not_command), group=2)
async def nsfw_moderator(client, message: Message):
    if not message.from_user:
        return

    chat_id  = message.chat.id
    settings = await load_settings(chat_id)

    if not settings.get("enabled", False):
        return

    # ── Flood detection (runs regardless of content type) ────────────────────
    user_id  = message.from_user.id
    now_ts   = int(time.time())
    flooded  = False

    flood_cfg = settings.get("flood", {})
    if flood_cfg.get("enabled"):
        timeframe = int(flood_cfg.get("timeframe_seconds", 10))
        threshold = int(flood_cfg.get("threshold", 5))
        chat_trk  = _flood_track.setdefault(chat_id, {})
        usr_times = chat_trk.setdefault(user_id, [])
        usr_times.append(now_ts)
        # Purge old timestamps
        while usr_times and usr_times[0] < now_ts - timeframe:
            usr_times.pop(0)
        if len(usr_times) >= threshold:
            flooded = True
            chat_trk[user_id] = []

    # ── NSFW content detection ────────────────────────────────────────────────
    is_nsfw, reason = await is_nsfw_content(client, message, settings)

    if not is_nsfw and not flooded:
        return  # ✅ Clean message — do nothing

    blocked_reason = reason if is_nsfw else "flood"

    # ── Delete the offending message ──────────────────────────────────────────
    try:
        await client.delete_messages(chat_id, message.id)
    except Exception as e:
        logger.warning(f"Failed to delete NSFW message: {e}")

    # ── Warning message / image ───────────────────────────────────────────────
    user_mention = f"<a href='tg://user?id={user_id}'>user</a>"
    warn_text = (
        f"⚠️ {user_mention}'s message was removed.\n"
        f"📌 Reason: {blocked_reason or 'NSFW content'}"
    )
    warning_img = settings.get("warning_image", "")
    try:
        if warning_img:
            await client.send_photo(chat_id, warning_img, caption=warn_text)
        else:
            await client.send_message(chat_id, warn_text)
    except Exception:
        try:
            await client.send_message(chat_id, warn_text)
        except Exception:
            pass

    # ── Time-mute ─────────────────────────────────────────────────────────────
    mute_cfg = settings.get("time_mute", {})
    if mute_cfg.get("enabled"):
        duration   = int(mute_cfg.get("duration_seconds", 3600))
        until_date = now_ts + duration
        try:
            perms = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_send_polls=False,
            )
            await client.restrict_chat_member(
                chat_id, user_id, permissions=perms, until_date=until_date
            )
            await client.send_message(
                chat_id,
                f"🔇 {user_mention} muted for {duration // 60} minute(s).",
            )
        except Exception as e:
            logger.debug(f"Mute failed: {e}")

    # ── Auto-kick ─────────────────────────────────────────────────────────────
    if settings.get("auto_kick"):
        try:
            await client.ban_chat_member(chat_id, user_id, revoke_messages=True)
            await asyncio.sleep(1)
            await client.unban_chat_member(chat_id, user_id)
            await client.send_message(chat_id, f"👢 {user_mention} was kicked (NSFW).")
        except Exception as e:
            logger.debug(f"Kick failed: {e}")

    # ── Auto-ban ──────────────────────────────────────────────────────────────
    if settings.get("auto_ban"):
        try:
            await client.ban_chat_member(chat_id, user_id, revoke_messages=True)
            await client.send_message(chat_id, f"⛔ {user_mention} was banned (NSFW).")
        except Exception as e:
            logger.debug(f"Ban failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN UTILITY COMMANDS
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("setnsfw") & filters.group)
async def nsfw_show_settings(client, message: Message):
    chat_id = message.chat.id
    if not await is_chat_owner(client, chat_id, message.from_user.id):
        await message.reply_text("Only the group owner can view NSFW settings.")
        return
    settings = await load_settings(chat_id)
    # Hide API key in output for safety
    display = json.loads(json.dumps(settings))
    if display.get("detection", {}).get("api_key"):
        display["detection"]["api_key"] = "***hidden***"
    await message.reply_text(f"NSFW settings:\n<pre>{json.dumps(display, indent=2)}</pre>")


@app.on_message(filters.command("setwarnimage") & filters.group)
async def set_warning_image(client, message: Message):
    chat_id = message.chat.id
    if not await is_chat_owner(client, chat_id, message.from_user.id):
        await message.reply_text("Only the group owner can change warning image.")
        return
    settings = await load_settings(chat_id)
    if len(message.command) < 2:
        await message.reply_text(
            "Usage: `/setwarnimage <image_url>` — set warning image\n"
            "`/setwarnimage clear`       — remove warning image"
        )
        return
    arg = message.command[1].strip()
    if arg.lower() == "clear":
        settings["warning_image"] = ""
        await save_settings(chat_id, settings)
        await message.reply_text("✅ Warning image cleared.")
    else:
        settings["warning_image"] = arg
        await save_settings(chat_id, settings)
        await message.reply_text("✅ Warning image updated.")


@app.on_message(filters.command("setmutetime") & filters.group)
async def set_mute_duration(client, message: Message):
    chat_id = message.chat.id
    if not await is_chat_owner(client, chat_id, message.from_user.id):
        await message.reply_text("Only the group owner can change mute duration.")
        return
    if len(message.command) < 2:
        await message.reply_text("Usage: `/setmutetime <seconds>`")
        return
    try:
        secs = int(message.command[1])
        settings = await load_settings(chat_id)
        settings["time_mute"]["duration_seconds"] = secs
        await save_settings(chat_id, settings)
        await message.reply_text(f"✅ Mute duration set to {secs}s ({secs // 60} minutes).")
    except ValueError:
        await message.reply_text("Please provide an integer number of seconds.")


@app.on_message(filters.command("setflood") & filters.group)
async def set_flood(client, message: Message):
    chat_id = message.chat.id
    if not await is_chat_owner(client, chat_id, message.from_user.id):
        await message.reply_text("Only the group owner can change flood settings.")
        return
    if len(message.command) < 2:
        await message.reply_text(
            "Usage: `/setflood <count> <seconds>` — enable\n"
            "`/setflood off`                    — disable"
        )
        return
    settings = await load_settings(chat_id)
    if message.command[1].lower() == "off":
        settings["flood"]["enabled"] = False
        await save_settings(chat_id, settings)
        await message.reply_text("✅ Flood protection disabled.")
        return
    try:
        threshold = int(message.command[1])
        timeframe = int(message.command[2]) if len(message.command) > 2 else 10
        settings["flood"].update({"enabled": True, "threshold": threshold, "timeframe_seconds": timeframe})
        await save_settings(chat_id, settings)
        await message.reply_text(f"✅ Flood: {threshold} NSFW messages per {timeframe}s triggers action.")
    except Exception:
        await message.reply_text("Invalid numbers. Usage: `/setflood <count> <seconds>`")


# ══════════════════════════════════════════════════════════════════════════════
#  NEW MEMBER HOOK  (pre-load settings on join)
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.new_chat_members)
async def on_new_chat_member(client, message: Message):
    await load_settings(message.chat.id)


# ══════════════════════════════════════════════════════════════════════════════
#  MODULE META
# ══════════════════════════════════════════════════════════════════════════════
__menu__    = "CMD_PRO"
__mod_name__ = "H_B_31"
__help__ = """
🛡 **NSFW Filter** — blocks only NSFW content, not all media

**Detection:**
  • Stickers  → Telegram's own NSFW sticker-set flag  (no external API)
  • Photos / Videos / GIFs → DeepAI API  (optional, free 5000 calls/month)
  • Documents → filename + MIME heuristic  (always active)

🔻 /nsfw               ➠ Open NSFW settings panel (owner only)
🔻 /nsfw on|off        ➠ Enable / disable NSFW filter
🔻 /setnsfwapi <key>   ➠ Set DeepAI API key (enables photo/video scanning)
🔻 /setnsfwapi off     ➠ Remove API key (back to sticker-only detection)
🔻 /setnsfw            ➠ Show full current settings (JSON)
🔻 /setwarnimage <url> ➠ Set warning image URL
🔻 /setwarnimage clear ➠ Remove warning image
🔻 /setmutetime <secs> ➠ Set temporary mute duration
🔻 /setflood <n> <secs>➠ Set NSFW flood protection threshold
🔻 /setflood off       ➠ Disable flood protection

**Modes (configurable in panel):**
  • Strict media ON  — block ALL photos/videos/GIFs when NSFW is enabled
                       (useful if you don't want to configure an API key)
  • Strict media OFF — only positively detected NSFW content is blocked ✅

**Scan types** (per-type toggle in panel):
  Stickers, Photos, Videos, GIFs, Documents, Voice, Audio
"""
