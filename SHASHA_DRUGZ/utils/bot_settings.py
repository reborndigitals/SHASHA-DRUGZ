# SHASHA_DRUGZ/utils/bot_settings.py
# =====================================================================
# Per-bot settings cache manager.
#
# HOW IT WORKS:
#   config.py defines START_IMG_URL etc. as _BotStr/_BotInt objects.
#   When any module uses those values, _BotStr._v() calls:
#       _bs._cache.get(bot_id, {}).get("start_image")
#   using the isolation ContextVar to know which bot is active.
#
#   This file manages that cache.
#
# CACHE LIFECYCLE:
#   • apply_to_config(bot_id)            — warm cache on bot startup
#   • invalidate(bot_id)                 — drop stale cache after DB write
#   • apply_to_config_and_invalidate()   — invalidate + force reload
#     (called by _update() in setbotinfo after every command)
#   • evict_bot_cache(bot_id)            — remove cache on bot stop/remove/expire
#     (called by deploy.py cleanup_bot_data and rmalldeploy)
#
# ISOLATION GUARANTEE:
#   _cache is keyed by bot_id (int).
#   Bot A's data is at _cache[bot_id_A].
#   Bot B's data is at _cache[bot_id_B].
#   Writing/invalidating/evicting one bot's entry NEVER touches another.
#   All asyncio tasks for Bot A read _cache[bot_id_A] only — the
#   ContextVar _current_bot_id (set by isolation handlers in deploy.py)
#   ensures each task knows which bot_id to look up.
#
# DISPLAY GETTERS:
#   get_start_image / get_ping_image etc. are still provided so
#   /botsettings and /botinfo can show current stored values.
# =====================================================================

import logging
from typing import Optional
from SHASHA_DRUGZ.core.mongo import raw_mongodb
import config as _cfg

# ── Per-bot settings cache ────────────────────────────────────────────────────
# Key:   bot_id (int)
# Value: raw MongoDB document dict from bot_{id}_settings collection
#        e.g. {"_id":"config","start_image":"https://...","must_join":{...}, ...}
#
# ISOLATION: this dict is ONLY indexed by bot_id.
# _cache[bot_id_A] and _cache[bot_id_B] are completely independent entries.
# No operation on one key can affect another key.
_cache: dict = {}


def _col(bot_id: int):
    """Isolated MongoDB collection for this bot's settings."""
    return raw_mongodb[f"bot_{bot_id}_settings"]


async def get_bot_settings(bot_id: int, force: bool = False) -> dict:
    """
    Return the settings dict for bot_id.
    Result is cached in-memory; call invalidate(bot_id) to refresh.
    Returns {} if no settings document exists yet — _BotStr will then
    fall back to the hardcoded config.py default value.

    ISOLATION: only _cache[bot_id] is read or written.
    """
    if not force and bot_id in _cache:
        return _cache[bot_id]
    try:
        doc = await _col(bot_id).find_one({"_id": "config"})
        result = doc or {}
    except Exception as exc:
        logging.warning(f"[bot_settings] DB read error bot={bot_id}: {exc}")
        result = {}
    _cache[bot_id] = result
    return result


def invalidate(bot_id: int):
    """
    Drop the in-memory cache for bot_id only.
    Call this from setbotinfo._update() before re-reading DB.
    After invalidation, the next get_bot_settings() call goes to MongoDB.

    ISOLATION: only _cache[bot_id] is removed. All other bots unaffected.
    """
    _cache.pop(bot_id, None)


def evict_bot_cache(bot_id: int):
    """
    Remove this bot's cache entry permanently.

    Called by deploy.py in:
      • cleanup_bot_data()        — bot removed / expired / refunded
      • confirm_rmalldeploy_cb()  — all bots nuked at once (also clears entire dict)

    Without this, if the same bot_id is redeployed later (e.g. owner
    re-buys after expiry), the new bot would pick up the old owner's
    stale cached settings until the next explicit reload.

    ISOLATION: only _cache[bot_id] is popped. Other bots unaffected.
    """
    _cache.pop(bot_id, None)
    logging.info(f"[bot_settings] bot={bot_id} cache evicted ✅")


async def apply_to_config(bot_id: int, force: bool = False) -> None:
    """
    Warm the per-bot settings cache from MongoDB.

    Call this on deployed-bot startup (after bc.start()) so the very
    first request from this bot already sees the correct stored values.

    config.py's _BotStr objects read from _cache dynamically on every
    access — no global config patching needed, no race conditions.

    ISOLATION: only _cache[bot_id] is populated.
    """
    await get_bot_settings(bot_id, force=force)
    logging.info(f"[bot_settings] bot={bot_id} cache warmed from DB ✅")


async def apply_to_config_and_invalidate(bot_id: int) -> None:
    """
    Invalidate stale cache then force-reload from MongoDB.

    Called by setbotinfo._update() after every successful DB write so
    the next access to START_IMG_URL etc. returns the new value immediately.

    ISOLATION: only _cache[bot_id] is invalidated and reloaded.
    All other bots' cache entries are completely untouched.
    """
    invalidate(bot_id)
    await get_bot_settings(bot_id, force=True)
    logging.info(f"[bot_settings] bot={bot_id} cache refreshed after update ✅")


# ── Display getters ────────────────────────────────────────────────────────────
# Used by /botsettings and /botinfo in setbotinfo.py to show stored values.
# These always read from the DB-backed cache (not from the live config proxy),
# so they show what's actually saved — useful for the owner to confirm changes.

async def get_start_image(bot_id: int) -> str:
    d = await get_bot_settings(bot_id)
    return d.get("start_image") or _cfg._DEFAULT_START_IMG


async def get_ping_image(bot_id: int) -> str:
    d = await get_bot_settings(bot_id)
    return d.get("ping_image") or _cfg._DEFAULT_PING_IMG


async def get_start_message(bot_id: int) -> Optional[str]:
    d = await get_bot_settings(bot_id)
    return d.get("start_message") or None


async def get_support_chat(bot_id: int) -> str:
    d = await get_bot_settings(bot_id)
    val = d.get("support_chat")
    if val:
        val = val.strip().lstrip("@")
        return val if val.startswith("http") else f"https://t.me/{val}"
    return _cfg._DEFAULT_SUPPORT_CHAT


async def get_support_channel(bot_id: int) -> str:
    d = await get_bot_settings(bot_id)
    val = d.get("update_channel")
    if val:
        val = val.strip().lstrip("@")
        return val if val.startswith("http") else f"https://t.me/{val}"
    return _cfg._DEFAULT_SUPPORT_CHANNEL


async def get_must_join_status(bot_id: int) -> dict:
    d = await get_bot_settings(bot_id)
    mj = d.get("must_join") or {}
    return {
        "enabled": mj.get("enabled", False),
        "link":    mj.get("link"),
    }


async def get_must_join(bot_id: int) -> Optional[str]:
    """Returns must-join link if enabled, else None."""
    status = await get_must_join_status(bot_id)
    return status["link"] if status["enabled"] and status["link"] else None


async def get_auto_gcast_status(bot_id: int) -> dict:
    d = await get_bot_settings(bot_id)
    ag = d.get("auto_gcast") or {}
    return {
        "enabled": ag.get("enabled", False),
        "message": ag.get("message") or _cfg._DEFAULT_AUTO_GCAST_MSG,
    }


async def get_log_channel(bot_id: int) -> Optional[int]:
    d = await get_bot_settings(bot_id)
    if d.get("logging") and d.get("log_channel"):
        return d["log_channel"]
    return int(_cfg.LOG_GROUP_ID)


async def get_assistant_config(bot_id: int) -> dict:
    d = await get_bot_settings(bot_id)
    return {
        "mode":   d.get("assistant_mode"),
        "string": d.get("assistant_string"),
        "multi":  d.get("assistant_multi") or [],
    }
