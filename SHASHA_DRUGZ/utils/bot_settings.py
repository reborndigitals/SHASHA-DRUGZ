# SHASHA_DRUGZ/utils/bot_settings.py
import logging
from typing import Optional
from SHASHA_DRUGZ.core.mongo import raw_mongodb
import config as _cfg

# ── Per-bot settings cache ─────────────────────────────────────────────────────
_cache: dict = {}

def _col(bot_id: int):
    return raw_mongodb[f"bot_{bot_id}_settings"]

async def get_bot_settings(bot_id: int, force: bool = False) -> dict:
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
    _cache.pop(bot_id, None)

def evict_bot_cache(bot_id: int):
    """
    Remove this bot's cache entry permanently.
    Called by deploy.py in:
      • cleanup_bot_data()        — bot removed / expired / refunded
      • confirm_rmalldeploy_cb()  — all bots nuked at once
    Without this, if the same bot_id is redeployed later the new bot
    would pick up stale cached settings.
    """
    _cache.pop(bot_id, None)
    logging.info(f"[bot_settings] bot={bot_id} cache evicted ✅")

async def apply_to_config(bot_id: int, force: bool = False) -> None:
    await get_bot_settings(bot_id, force=force)
    logging.info(f"[bot_settings] bot={bot_id} cache warmed from DB ✅")

async def apply_to_config_and_invalidate(bot_id: int) -> None:
    invalidate(bot_id)
    await get_bot_settings(bot_id, force=True)
    logging.info(f"[bot_settings] bot={bot_id} cache refreshed after update ✅")

# ── Display getters ────────────────────────────────────────────────────────────
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

async def get_assistant_session(bot_id: int) -> Optional[str]:
    """
    Returns the assistant string session stored for this bot via /setassistant.
    Returns None if not set (falls back to config.py STRING1).
    Call this from get_assistant() in database.py to support per-bot assistants.
    """
    d = await get_bot_settings(bot_id)
    mode = d.get("assistant_mode")
    if mode == "single":
        return d.get("assistant_string") or None
    # multi-assistant: return first string in the list
    if mode == "multi":
        multi = d.get("assistant_multi") or []
        return multi[0] if multi else None
    return None

async def get_all_assistant_sessions(bot_id: int) -> list:
    """
    Returns all assistant string sessions for this bot.
    Used when assistant_mode == 'multi'.
    Returns [] if not set.
    """
    d = await get_bot_settings(bot_id)
    mode = d.get("assistant_mode")
    if mode == "multi":
        return d.get("assistant_multi") or []
    if mode == "single":
        s = d.get("assistant_string")
        return [s] if s else []
    return []
