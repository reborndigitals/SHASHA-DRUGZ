# ============================================================
#   GC MANAGER MODULE FOR SHASHA_DRUGZ
#   Drop this file into: SHASHA_DRUGZ/plugins/gcmanager.py
#   Single-file — zero extra files needed.
# ============================================================

import re
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import filters, enums
from pyrogram.errors import (
    ChatAdminRequired,
    UserAdminInvalid,
    MessageDeleteForbidden,
    RPCError,
)
from pyrogram.types import (
    Message,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import OWNER_ID

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  CONFIG  (edit these or pull from env)
# ─────────────────────────────────────────────────────────────
import os

MONGODB_URI: str = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://theamanchaudhary:updatesbyaman@cluster0.qda0aop.mongodb.net/?appName=Cluster0",
)
DATABASE_NAME: str = os.getenv("DATABASE_NAME", "group_manager")
MAX_LINKS_PER_USER: int = int(os.getenv("MAX_LINKS_PER_USER", "1"))
ENABLE_FRAUD_DETECTION: bool = os.getenv("ENABLE_FRAUD_DETECTION", "true").lower() == "true"

# ─────────────────────────────────────────────────────────────
#  DATABASE  (async motor, lazy-init)
# ─────────────────────────────────────────────────────────────
_mongo_client: Optional[AsyncIOMotorClient] = None
_db = None


async def get_db():
    global _mongo_client, _db
    if _db is None:
        _mongo_client = AsyncIOMotorClient(MONGODB_URI)
        _db = _mongo_client[DATABASE_NAME]
    return _db


# ── Group helpers ─────────────────────────────────────────────

async def db_add_allowed_group(chat_id: int, chat_title: str, added_by: int) -> bool:
    db = await get_db()
    try:
        await db.allowed_groups.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "chat_title": chat_title,
                      "added_by": added_by, "added_at": datetime.utcnow(), "is_active": True}},
            upsert=True,
        )
        return True
    except Exception as e:
        logger.error(f"db_add_allowed_group: {e}")
        return False


async def db_remove_allowed_group(chat_id: int) -> bool:
    db = await get_db()
    try:
        r = await db.allowed_groups.delete_one({"chat_id": chat_id})
        return r.deleted_count > 0
    except Exception as e:
        logger.error(f"db_remove_allowed_group: {e}")
        return False


async def db_is_group_allowed(chat_id: int) -> bool:
    db = await get_db()
    try:
        return bool(await db.allowed_groups.find_one({"chat_id": chat_id, "is_active": True}))
    except Exception as e:
        logger.error(f"db_is_group_allowed: {e}")
        return False


async def db_get_all_allowed_groups() -> List[Dict]:
    db = await get_db()
    try:
        return await db.allowed_groups.find({"is_active": True}).to_list(length=None)
    except Exception as e:
        logger.error(f"db_get_all_allowed_groups: {e}")
        return []


# ── Session helpers ───────────────────────────────────────────

async def db_create_session(chat_id: int, created_by: int) -> Optional[str]:
    db = await get_db()
    try:
        result = await db.sessions.insert_one({
            "chat_id": chat_id, "created_by": created_by,
            "created_at": datetime.utcnow(), "is_active": True, "closed_at": None,
        })
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"db_create_session: {e}")
        return None


async def db_get_active_session(chat_id: int) -> Optional[Dict]:
    db = await get_db()
    try:
        return await db.sessions.find_one({"chat_id": chat_id, "is_active": True})
    except Exception as e:
        logger.error(f"db_get_active_session: {e}")
        return None


async def db_close_session(chat_id: int) -> bool:
    db = await get_db()
    try:
        await db.sessions.update_one(
            {"chat_id": chat_id, "is_active": True},
            {"$set": {"is_active": False, "closed_at": datetime.utcnow()}},
        )
        return True
    except Exception as e:
        logger.error(f"db_close_session: {e}")
        return False


async def db_clear_session_data(chat_id: int, session_id: str):
    db = await get_db()
    filt = {"chat_id": chat_id, "session_id": session_id}
    for col in ("links", "safe_list", "ad_list", "sr_list"):
        try:
            await db[col].delete_many(filt)
        except Exception as e:
            logger.error(f"db_clear_session_data [{col}]: {e}")


# ── Link helpers ──────────────────────────────────────────────

async def db_add_link(chat_id: int, user_id: int, username: str,
                      link: str, encrypted: str, session_id: str):
    db = await get_db()
    try:
        await db.links.insert_one({
            "chat_id": chat_id, "user_id": user_id, "username": username,
            "link": link, "encrypted_link": encrypted, "session_id": session_id,
            "is_verified": False, "submitted_at": datetime.utcnow(),
        })
    except Exception as e:
        logger.error(f"db_add_link: {e}")


async def db_get_user_links(chat_id: int, user_id: int, session_id: str) -> List[Dict]:
    db = await get_db()
    try:
        return await db.links.find(
            {"chat_id": chat_id, "user_id": user_id, "session_id": session_id}
        ).to_list(length=None)
    except Exception as e:
        logger.error(f"db_get_user_links: {e}")
        return []


async def db_get_all_users_with_links(chat_id: int, session_id: str) -> List[Dict]:
    db = await get_db()
    try:
        pipeline = [
            {"$match": {"chat_id": chat_id, "session_id": session_id}},
            {"$group": {
                "_id": "$user_id",
                "username": {"$first": "$username"},
                "user_id": {"$first": "$user_id"},
                "links": {"$push": "$link"},
            }},
        ]
        return await db.links.aggregate(pipeline).to_list(length=None)
    except Exception as e:
        logger.error(f"db_get_all_users_with_links: {e}")
        return []


async def db_get_users_with_multiple_links(chat_id: int, session_id: str) -> List[Dict]:
    db = await get_db()
    try:
        pipeline = [
            {"$match": {"chat_id": chat_id, "session_id": session_id}},
            {"$group": {"_id": "$user_id", "username": {"$first": "$username"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        return await db.links.aggregate(pipeline).to_list(length=None)
    except Exception as e:
        logger.error(f"db_get_users_with_multiple_links: {e}")
        return []


async def db_check_duplicate_link(chat_id: int, user_id: int,
                                   link: str, session_id: str) -> Tuple[bool, List[Dict]]:
    db = await get_db()
    try:
        existing = await db.links.find(
            {"chat_id": chat_id, "session_id": session_id,
             "link": link, "user_id": {"$ne": user_id}}
        ).to_list(length=None)
        return bool(existing), existing
    except Exception as e:
        logger.error(f"db_check_duplicate_link: {e}")
        return False, []


async def db_get_session_stats(chat_id: int, session_id: str) -> Dict:
    db = await get_db()
    try:
        total_links = await db.links.count_documents({"chat_id": chat_id, "session_id": session_id})
        pipeline = [
            {"$match": {"chat_id": chat_id, "session_id": session_id}},
            {"$group": {"_id": "$user_id"}},
            {"$count": "count"},
        ]
        result = await db.links.aggregate(pipeline).to_list(length=None)
        unique_users = result[0]["count"] if result else 0
        return {"total_links": total_links, "unique_users": unique_users}
    except Exception as e:
        logger.error(f"db_get_session_stats: {e}")
        return {"total_links": 0, "unique_users": 0}


async def db_mark_user_links_verified(chat_id: int, user_id: int, session_id: str):
    db = await get_db()
    try:
        await db.links.update_many(
            {"chat_id": chat_id, "user_id": user_id, "session_id": session_id},
            {"$set": {"is_verified": True}},
        )
    except Exception as e:
        logger.error(f"db_mark_user_links_verified: {e}")


# ── Safe list helpers ─────────────────────────────────────────

async def db_is_user_in_safe_list(chat_id: int, session_id: str, user_id: int) -> bool:
    db = await get_db()
    try:
        return bool(await db.safe_list.find_one(
            {"chat_id": chat_id, "session_id": session_id, "user_id": user_id}
        ))
    except Exception as e:
        logger.error(f"db_is_user_in_safe_list: {e}")
        return False


async def db_add_to_safe_list(chat_id: int, session_id: str,
                               user_id: int, username: str, keyword: str):
    db = await get_db()
    try:
        await db.safe_list.insert_one({
            "chat_id": chat_id, "session_id": session_id, "user_id": user_id,
            "username": username, "ad_text": keyword, "added_at": datetime.utcnow(),
        })
    except Exception as e:
        logger.error(f"db_add_to_safe_list: {e}")


async def db_get_safe_users(chat_id: int, session_id: str) -> List[Dict]:
    db = await get_db()
    try:
        return await db.safe_list.find(
            {"chat_id": chat_id, "session_id": session_id}
        ).to_list(length=None)
    except Exception as e:
        logger.error(f"db_get_safe_users: {e}")
        return []


# ── Ad tracking helpers ───────────────────────────────────────

async def db_enable_ad_tracking(chat_id: int, session_id: str):
    db = await get_db()
    try:
        await db.sessions.update_one(
            {"chat_id": chat_id, "session_id": session_id},
            {"$set": {"ad_tracking": True}},
        )
        await db.ad_tracking.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "session_id": session_id, "enabled": True}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"db_enable_ad_tracking: {e}")


async def db_is_ad_tracking_enabled(chat_id: int) -> bool:
    db = await get_db()
    try:
        doc = await db.ad_tracking.find_one({"chat_id": chat_id, "enabled": True})
        return bool(doc)
    except Exception as e:
        logger.error(f"db_is_ad_tracking_enabled: {e}")
        return False


async def db_add_to_ad_list(chat_id: int, user_id: int, username: str):
    db = await get_db()
    try:
        await db.ad_list.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {"chat_id": chat_id, "user_id": user_id, "username": username,
                      "added_at": datetime.utcnow()}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"db_add_to_ad_list: {e}")


# ── SR list helpers ───────────────────────────────────────────

async def db_add_to_sr_list(chat_id: int, user_id: int, username: str):
    db = await get_db()
    try:
        await db.sr_list.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {"chat_id": chat_id, "user_id": user_id, "username": username,
                      "requested_at": datetime.utcnow()}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"db_add_to_sr_list: {e}")


async def db_get_sr_list(chat_id: int) -> List[Dict]:
    db = await get_db()
    try:
        return await db.sr_list.find({"chat_id": chat_id}).to_list(length=None)
    except Exception as e:
        logger.error(f"db_get_sr_list: {e}")
        return []


# ── Warning helpers ───────────────────────────────────────────

async def db_get_warn_limit(chat_id: int) -> int:
    db = await get_db()
    try:
        doc = await db.gc_settings.find_one({"chat_id": chat_id})
        return doc.get("warn_limit", 3) if doc else 3
    except Exception as e:
        logger.error(f"db_get_warn_limit: {e}")
        return 3


async def db_set_warn_limit(chat_id: int, limit: int):
    db = await get_db()
    try:
        await db.gc_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"warn_limit": limit}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"db_set_warn_limit: {e}")


# ── Custom pin message helpers ────────────────────────────────

async def db_set_rs(chat_id: int, slot: int, text: str):
    db = await get_db()
    try:
        await db.gc_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {f"rs{slot}": text}},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"db_set_rs: {e}")


async def db_get_rs(chat_id: int, slot: int) -> Optional[str]:
    db = await get_db()
    try:
        doc = await db.gc_settings.find_one({"chat_id": chat_id})
        return doc.get(f"rs{slot}") if doc else None
    except Exception as e:
        logger.error(f"db_get_rs: {e}")
        return None


# ── Anon mode helpers ─────────────────────────────────────────

async def db_toggle_anon_mode(chat_id: int) -> bool:
    """Toggle anon admin mode; returns new state."""
    db = await get_db()
    try:
        doc = await db.gc_settings.find_one({"chat_id": chat_id})
        current = doc.get("anon_mode", False) if doc else False
        new_state = not current
        await db.gc_settings.update_one(
            {"chat_id": chat_id},
            {"$set": {"anon_mode": new_state}},
            upsert=True,
        )
        return new_state
    except Exception as e:
        logger.error(f"db_toggle_anon_mode: {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────

def encrypt_link(link: str) -> str:
    return hashlib.sha256(link.encode()).hexdigest()[:16]


def extract_twitter_links(text: str) -> List[str]:
    if not text:
        return []
    patterns = [
        r"https?://(?:www\.)?twitter\.com/[^\s]+",
        r"https?://(?:www\.)?x\.com/[^\s]+",
        r"https?://t\.co/[^\s]+",
    ]
    links = []
    for p in patterns:
        links.extend(re.findall(p, text))
    seen, unique = set(), []
    for lnk in links:
        if lnk not in seen:
            seen.add(lnk)
            unique.append(lnk)
    return unique


def extract_username_from_link(link: str) -> str:
    for pattern in [r"twitter\.com/([^/\s?]+)", r"x\.com/([^/\s?]+)"]:
        m = re.search(pattern, link)
        if m:
            return m.group(1)
    return "unknown"


def parse_duration(duration_str: str) -> timedelta:
    if not duration_str:
        return timedelta(days=3)
    total_seconds = 0
    matches = re.findall(
        r"(\d+)\s*([dhms]|day|days|hour|hours|minute|minutes|second|seconds)",
        duration_str.lower()
    )
    for value, unit in matches:
        v = int(value)
        if unit in ("d", "day", "days"):
            total_seconds += v * 86400
        elif unit in ("h", "hour", "hours"):
            total_seconds += v * 3600
        elif unit in ("m", "minute", "minutes"):
            total_seconds += v * 60
        elif unit in ("s", "second", "seconds"):
            total_seconds += v
    return timedelta(seconds=total_seconds) if total_seconds > 0 else timedelta(days=3)


def mention(user_id: int, name: str) -> str:
    return f"[{name}](tg://openmessage?user_id={user_id})"


async def is_group_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


# Locked & unlocked ChatPermissions presets
LOCKED_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
)

OPEN_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)

MUTED_PERMS = ChatPermissions()   # all False by default


# ─────────────────────────────────────────────────────────────
#  RESOLVE TARGET HELPER
# ─────────────────────────────────────────────────────────────

async def _resolve_target(client, message: Message) -> Tuple[Optional[int], Optional[str]]:
    """Resolve target user_id and display_name from reply or first arg."""
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        return u.id, f"@{u.username}" if u.username else u.first_name
    args = message.command[1:]
    if args:
        uname = args[0].lstrip("@")
        try:
            u = await client.get_users(uname)
            return u.id, f"@{u.username}" if u.username else u.first_name
        except Exception:
            pass
        db = await get_db()
        doc = (await db.links.find_one({"username": uname})
               or await db.safe_list.find_one({"username": uname})
               or await db.ad_list.find_one({"username": uname}))
        if doc:
            return doc["user_id"], f"@{uname}"
    return None, None


# ─────────────────────────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────────────────────────

# ── /gcstarts ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcstarts"]))
async def gcstarts_command(client, message: Message):
    """Start a new group session."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text(
            "👋 **Welcome to GC Manager Bot!**\n\n"
            "Add me to your group and use /gcstarts to begin a session.\n\n"
            "👑 **Owner Commands:**\n"
            "/gcmanage — Configure allowed groups\n"
            "/gcpanel — Admin panel"
        )

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
        return await message.reply_text("❌ Only admins can activate the bot!")

    if not await db_is_group_allowed(chat_id):
        return await message.reply_text(
            f"⚠️ This group is not authorized!\n"
            f"Contact the bot owner to whitelist it.\n"
            f"Group ID: `{chat_id}`"
        )

    session = await db_get_active_session(chat_id)
    if not session:
        session_id = await db_create_session(chat_id, user_id)
        if not session_id:
            return await message.reply_text("❌ Failed to create session!")

        try:
            await client.set_chat_permissions(chat_id, OPEN_PERMS)
        except Exception as e:
            logger.warning(f"Could not set chat permissions: {e}")

        try:
            await client.send_video(
                chat_id,
                video="https://envs.sh/M-h.mp4",
                caption=(
                    "✅ **Group session activated!**\n\n"
                    "The bot is now tracking link submissions.\n"
                    "🔓 Group is unlocked — all users can message."
                ),
            )
        except Exception:
            await message.reply_text(
                "✅ **Group session activated!**\n\n"
                "The bot is now tracking link submissions.\n"
                "🔓 Group is unlocked — all users can message."
            )
    else:
        try:
            await client.set_chat_permissions(chat_id, OPEN_PERMS)
        except Exception as e:
            logger.warning(f"Could not set chat permissions: {e}")
        await message.reply_text(
            "✅ Session already active!!\n"
            "🔓 Group is unlocked — all users can message."
        )


# ── /gcclose ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcclose"]))
async def gcclose_command(client, message: Message):
    """Lock the group without ending the session."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("This command is only available in groups!")

    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ This command is only for admins!")

    if not await db_get_active_session(chat_id):
        return await message.reply_text("❌ No active session! Use /gcstarts to begin.")

    try:
        await client.set_chat_permissions(chat_id, LOCKED_PERMS)
        try:
            await client.send_video(
                chat_id,
                video="https://envs.sh/M-d.mp4",
                caption=(
                    "🔒 **Group locked!**\n\n"
                    "No one can send messages.\n"
                    "Session is still active but paused.\n\n"
                    "Use /gcreopen to unlock the group."
                ),
            )
        except Exception:
            await message.reply_text(
                "🔒 **Group locked!**\n\n"
                "Session is still active but paused.\n"
                "Use /gcreopen to unlock."
            )
    except Exception as e:
        logger.error(f"gcclose: {e}")
        await message.reply_text(
            "❌ Cannot lock group!\n"
            "Make sure the bot has 'Restrict Members' permission."
        )


# ── /gcreopen ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcreopen"]))
async def gcreopen_command(client, message: Message):
    """Unlock the group and continue the session."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("This command is only available in groups!")

    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ This command is only for admins!")

    if not await db_get_active_session(chat_id):
        return await message.reply_text("❌ No active session! Use /gcstarts to begin.")

    try:
        await client.set_chat_permissions(chat_id, OPEN_PERMS)
        await message.reply_text(
            "🔓 **Group unlocked!**\n\n"
            "✅ Users can now send messages.\n"
            "Session continues — link tracking is active."
        )
    except Exception as e:
        logger.error(f"gcreopen: {e}")
        await message.reply_text(
            "❌ Cannot unlock group!\n"
            "Make sure the bot has 'Restrict Members' permission."
        )


# ── /gcend ────────────────────────────────────────────────────
@app.on_message(filters.command(["gcend"]))
async def gcend_command(client, message: Message):
    """End the current session and clear all data."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("This command is only available in groups!")

    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ This command is only for admins!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session found!")

    session_id = str(session["_id"])
    await db_clear_session_data(chat_id, session_id)
    await db_close_session(chat_id)

    try:
        await client.set_chat_permissions(chat_id, LOCKED_PERMS)
    except Exception as e:
        logger.warning(f"gcend lock: {e}")

    try:
        await client.send_photo(
            chat_id,
            photo="https://envs.sh/XD_.jpg",
            caption=(
                "✅ **Session ended and data cleared!**\n\n"
                "All tracked links and user data have been removed.\n"
                "🔒 Group is locked — use /gcstarts to begin a new session."
            ),
        )
    except Exception:
        await message.reply_text(
            "✅ **Session ended and data cleared!**\n\n"
            "🔒 Group is locked — use /gcstarts to begin a new session."
        )


# ── /gcclear ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcclear"]))
async def gcclear_command(client, message: Message):
    """Clear tracked data but keep the session active."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("This command is only available in groups!")

    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ This command is only for admins!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session found!")

    await db_clear_session_data(chat_id, str(session["_id"]))
    await message.reply_text(
        "✅ **All tracked data cleared!**\n\n"
        "The session is still active but all previous data has been removed."
    )


# ── /gcclearall ───────────────────────────────────────────────
@app.on_message(filters.command(["gcclearall"]))
async def gcclearall_command(client, message: Message):
    """Delete recent messages in the group (last ~1 000)."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("This command is only available in groups!")

    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ This command is only for admins!")

    status_msg = await message.reply_text(
        "⏳ **Starting deletion process...**\n"
        "Note: Telegram only allows deletion of messages from the last 48 h."
    )

    deleted = failed = 0
    current_id = message.id

    for msg_id in range(current_id, max(current_id - 1000, 0), -1):
        try:
            await client.delete_messages(chat_id, msg_id)
            deleted += 1
            if deleted % 50 == 0:
                try:
                    await status_msg.edit_text(
                        f"🗑️ **Deleting...**\n✅ Deleted: {deleted}\n❌ Failed: {failed}"
                    )
                except Exception:
                    pass
        except Exception:
            failed += 1
            if failed > 100:
                break

    try:
        await status_msg.edit_text(
            f"✅ **Clear All Complete**\n\n"
            f"🗑️ Deleted: {deleted} messages\n"
            f"❌ Failed/old: {failed} messages"
        )
    except Exception:
        pass


# ── /gcrefresh ────────────────────────────────────────────────
@app.on_message(filters.command(["gcrefresh"]))
async def gcrefresh_command(client, message: Message):
    """Refresh/verify the admin list for this group."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("This command is only available in groups!")

    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ This command is only for admins!")

    try:
        admins = await client.get_chat_members(
            chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
        )
        admin_list = [m async for m in admins]
        await message.reply_text(
            f"✅ Admin list refreshed!\n📊 Found **{len(admin_list)}** admins."
        )
    except Exception as e:
        logger.error(f"gcrefresh: {e}")
        await message.reply_text(f"❌ Error refreshing admins: {e}")


# ─────────────────────────────────────────────────────────────
#  BOT OWNER COMMANDS
# ─────────────────────────────────────────────────────────────

# ── /gcmanage ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcmanage"]) & filters.private)
async def gcmanage_command(client, message: Message):
    """Group management panel (bot owner only, PM only)."""
    if message.from_user.id != OWNER_ID and message.from_user.id not in SUDOERS:
        return await message.reply_text("❌ This command is only for the bot owner!")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View Allowed Groups", callback_data="gc_view_groups")],
        [InlineKeyboardButton("➕ Add Group", callback_data="gc_add_group_info")],
        [InlineKeyboardButton("➖ Remove Group", callback_data="gc_remove_group_info")],
    ])
    await message.reply_text(
        "🛠️ **Group Management Panel**\n\nSelect an option:",
        reply_markup=keyboard
    )


@app.on_callback_query(filters.regex(r"^gc_(view_groups|add_group_info|remove_group_info)$"))
async def gcmanage_callback(client, query: CallbackQuery):
    if query.from_user.id != OWNER_ID and query.from_user.id not in SUDOERS:
        return await query.answer("Not authorized!", show_alert=True)

    await query.answer()

    if query.data == "gc_view_groups":
        groups = await db_get_all_allowed_groups()
        if not groups:
            return await query.message.edit_text("📋 **Allowed Groups**\n\nNo groups added yet.")
        text = "📋 **Allowed Groups**\n\n"
        for idx, g in enumerate(groups, 1):
            added = g.get("added_at", datetime.utcnow()).strftime("%Y-%m-%d")
            text += (
                f"{idx}. **{g.get('chat_title', 'Unknown')}**\n"
                f"   ID: `{g['chat_id']}`\n"
                f"   Added: {added}\n\n"
            )
        await query.message.edit_text(text)

    elif query.data == "gc_add_group_info":
        await query.message.edit_text(
            "➕ **Add New Group**\n\n"
            "1. Add the bot to your group and make it admin\n"
            "2. Note the Group ID from /gcstarts\n"
            "3. Send: `/gcaddgroup <group_id>`\n\n"
            "Example: `/gcaddgroup -1001234567890`"
        )

    elif query.data == "gc_remove_group_info":
        await query.message.edit_text(
            "➖ **Remove Group**\n\n"
            "Send: `/gcremovegroup <group_id>`\n\n"
            "Example: `/gcremovegroup -1001234567890`"
        )


# ── /gcaddgroup ───────────────────────────────────────────────
@app.on_message(filters.command(["gcaddgroup"]) & filters.private)
async def gcaddgroup_command(client, message: Message):
    if message.from_user.id != OWNER_ID and message.from_user.id not in SUDOERS:
        return await message.reply_text("❌ Only the bot owner can use this!")

    args = message.command[1:]
    if not args:
        return await message.reply_text("❌ Usage: `/gcaddgroup <group_id>`")

    try:
        chat_id = int(args[0])
    except ValueError:
        return await message.reply_text("❌ Invalid group ID! Must be a number.")

    try:
        chat = await client.get_chat(chat_id)
        chat_title = chat.title or f"Group {chat_id}"
    except Exception:
        chat_title = f"Group {chat_id}"

    success = await db_add_allowed_group(chat_id, chat_title, message.from_user.id)
    if success:
        await message.reply_text(
            f"✅ **Group Added!**\n\n📝 {chat_title}\n🆔 `{chat_id}`\n\nThe group can now use the bot."
        )
    else:
        await message.reply_text("❌ Failed to add group!")


# ── /gcremovegroup ────────────────────────────────────────────
@app.on_message(filters.command(["gcremovegroup"]) & filters.private)
async def gcremovegroup_command(client, message: Message):
    if message.from_user.id != OWNER_ID and message.from_user.id not in SUDOERS:
        return await message.reply_text("❌ Only the bot owner can use this!")

    args = message.command[1:]
    if not args:
        return await message.reply_text("❌ Usage: `/gcremovegroup <group_id>`")

    try:
        chat_id = int(args[0])
    except ValueError:
        return await message.reply_text("❌ Invalid group ID! Must be a number.")

    success = await db_remove_allowed_group(chat_id)
    if success:
        await message.reply_text(
            f"✅ **Group Removed!**\n🆔 `{chat_id}`\nThe group can no longer use the bot."
        )
    else:
        await message.reply_text("❌ Group not found in the allowed list!")


# ── /gcpanel ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcpanel"]))
async def gcpanel_command(client, message: Message):
    """Full admin panel (owner/sudoers)."""
    if message.from_user.id != OWNER_ID and message.from_user.id not in SUDOERS:
        return await message.reply_text("❌ Only the bot owner can use this!")

    groups = await db_get_all_allowed_groups()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 All Groups", callback_data="gc_view_groups"),
         InlineKeyboardButton("➕ Add Group", callback_data="gc_add_group_info")],
        [InlineKeyboardButton("➖ Remove Group", callback_data="gc_remove_group_info")],
    ])
    await message.reply_text(
        f"👑 **GC Manager Panel**\n\n"
        f"📊 Allowed groups: **{len(groups)}**\n\n"
        f"Use the buttons below or:\n"
        f"/gcaddgroup — Add a group\n"
        f"/gcremovegroup — Remove a group\n"
        f"/gcmanage — Full management panel",
        reply_markup=keyboard,
    )


# ── /gclinks ─────────────────────────────────────────────────
@app.on_message(filters.command(["gclinks"]) & filters.private)
async def gclinks_command(client, message: Message):
    """View links by group (PM only, owner/sudoers)."""
    if message.from_user.id != OWNER_ID and message.from_user.id not in SUDOERS:
        return await message.reply_text("❌ Only the bot owner can use this!")

    groups = await db_get_all_allowed_groups()
    if not groups:
        return await message.reply_text("No allowed groups found.")

    text = "📎 **Links Overview by Group**\n\n"
    for g in groups:
        cid = g["chat_id"]
        session = await db_get_active_session(cid)
        if session:
            sid = str(session["_id"])
            stats = await db_get_session_stats(cid, sid)
            text += (
                f"**{g.get('chat_title', cid)}** (`{cid}`)\n"
                f"  👤 {stats['unique_users']} users | 🔗 {stats['total_links']} links\n\n"
            )
        else:
            text += f"**{g.get('chat_title', cid)}** — no active session\n\n"

    await message.reply_text(text)


# ─────────────────────────────────────────────────────────────
#  MODERATION COMMANDS
# ─────────────────────────────────────────────────────────────

# ── /unsafe ───────────────────────────────────────────────────
@app.on_message(filters.command(["unsafe"]))
async def unsafe_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session!")

    db = await get_db()
    unverified = await db.links.find(
        {"chat_id": chat_id, "session_id": str(session["_id"]), "is_verified": False}
    ).to_list(length=None)

    if not unverified:
        return await message.reply_text("✅ All users are verified!")

    users: Dict[int, str] = {}
    for lnk in unverified:
        users[lnk["user_id"]] = lnk["username"]

    text = "⚠️ **Unverified Users:**\n\n"
    for idx, uname in enumerate(users.values(), 1):
        text += f"{idx}. @{uname}\n"
    await message.reply_text(text)


# ── /safe ─────────────────────────────────────────────────────
@app.on_message(filters.command(["safe"]))
async def safe_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session!")

    session_id = str(session["_id"])
    safe_users = await db_get_safe_users(chat_id, session_id)
    if not safe_users:
        return await message.reply_text("❌ No users have sent ad/done messages yet!")

    text = "✅ **Safe List — Users who sent ad/done:**\n\n"
    for idx, u in enumerate(safe_users, 1):
        uname = u.get("username", "Unknown")
        uid = u.get("user_id")
        ad_text = u.get("ad_text", "ad")
        user_links = await db_get_user_links(chat_id, uid, session_id)
        if user_links:
            tw = extract_username_from_link(user_links[0]["link"])
            tw_link = user_links[0]["link"]
            text += f"{idx}. [{tw}]({tw_link}) 𝕏 "
        else:
            text += f"{idx}. "
        text += f"[(@{uname})](tg://user?id={uid}) ✅ {ad_text}\n"

    text += f"\n📊 **Total:** {len(safe_users)} users marked safe"
    await message.reply_text(text, disable_web_page_preview=True)


# ── /gccheck ─────────────────────────────────────────────────
@app.on_message(filters.command(["gccheck"]))
async def gccheck_command(client, message: Message):
    """Enable ad/done tracking."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session! Use /gcstarts first.")

    await db_enable_ad_tracking(chat_id, str(session["_id"]))
    await message.reply_text(
        "✅ **Check mode enabled!**\n\n"
        "I will now track 'ad', 'all done', 'all dn', 'done' messages and mark users safe."
    )


# ── /gcsr ─────────────────────────────────────────────────────
@app.on_message(filters.command(["gcsr"]))
async def gcsr_command(client, message: Message):
    """Request screen recording from a user (reply)."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")
    if not message.reply_to_message:
        return await message.reply_text("❌ Reply to the user's message to request SR!")

    u = message.reply_to_message.from_user
    username = u.username or u.first_name
    await db_add_to_sr_list(chat_id, u.id, username)

    name = f"@{u.username}" if u.username else u.first_name
    await message.reply_text(
        f"📹 {name}, please recheck — your likes may be missing!\n\n"
        "Send a **screen recording** via DM to the admins.\n"
        "Make sure your profile is visible and your TL profile is mentioned or pinned as per the post."
    )


# ── /gcadd ────────────────────────────────────────────────────
@app.on_message(filters.command(["gcadd"]))
async def gcadd_command(client, message: Message):
    """Manually add a user to the ad/done (safe) list."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")
    if not message.reply_to_message:
        return await message.reply_text("❌ Reply to the user's message!")

    u = message.reply_to_message.from_user
    username = u.username or u.first_name
    await db_add_to_ad_list(chat_id, u.id, username)

    session = await db_get_active_session(chat_id)
    if session:
        await db_add_to_safe_list(chat_id, str(session["_id"]), u.id, username, "manual")
        await db_mark_user_links_verified(chat_id, u.id, str(session["_id"]))

    name = f"@{u.username}" if u.username else u.first_name
    await message.reply_text(f"✅ {name} added to the ad list!")


# ── /gcsetwarnlimit ───────────────────────────────────────────
@app.on_message(filters.command(["gcsetwarnlimit"]))
async def gcsetwarnlimit_command(client, message: Message):
    """Set the warning limit before auto-mute."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    args = message.command[1:]
    if not args or not args[0].isdigit():
        current = await db_get_warn_limit(chat_id)
        return await message.reply_text(
            f"⚙️ Current warn limit: **{current}**\n\nUsage: `/gcsetwarnlimit <number>`"
        )

    limit = int(args[0])
    if limit < 1 or limit > 20:
        return await message.reply_text("❌ Limit must be between 1 and 20.")
    await db_set_warn_limit(chat_id, limit)
    await message.reply_text(f"✅ Warning limit set to **{limit}**!")


# ── /muteunsafe ───────────────────────────────────────────────
@app.on_message(filters.command(["muteunsafe"]))
async def muteunsafe_command(client, message: Message):
    """Mute all unverified users."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session!")

    session_id = str(session["_id"])
    db = await get_db()
    unverified_links = await db.links.find(
        {"chat_id": chat_id, "session_id": session_id, "is_verified": False}
    ).to_list(length=None)

    unique_users = {lnk["user_id"] for lnk in unverified_links}
    args = message.command[1:]
    duration_str = " ".join(args) if args else "3d"
    duration = parse_duration(duration_str)
    until = datetime.utcnow() + duration

    muted = failed = 0
    for uid in unique_users:
        try:
            await client.restrict_chat_member(chat_id, uid, MUTED_PERMS, until_date=until)
            muted += 1
        except Exception as e:
            logger.error(f"muteunsafe user {uid}: {e}")
            failed += 1

    await message.reply_text(
        f"🔇 **Mute Operation Complete**\n\n"
        f"✅ Muted: {muted}\n❌ Failed: {failed}\n⏱️ Duration: {duration_str}"
    )


# ── /unmuteunsafe ─────────────────────────────────────────────
@app.on_message(filters.command(["unmuteunsafe"]))
async def unmuteunsafe_command(client, message: Message):
    """Unmute all unverified users."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session!")

    session_id = str(session["_id"])
    db = await get_db()
    unverified_links = await db.links.find(
        {"chat_id": chat_id, "session_id": session_id, "is_verified": False}
    ).to_list(length=None)

    unique_users = {lnk["user_id"] for lnk in unverified_links}
    unmuted = failed = 0
    for uid in unique_users:
        try:
            await client.restrict_chat_member(chat_id, uid, OPEN_PERMS)
            unmuted += 1
        except Exception as e:
            logger.error(f"unmuteunsafe user {uid}: {e}")
            failed += 1

    await message.reply_text(
        f"🔊 **Unmute Operation Complete**\n\n✅ Unmuted: {unmuted}\n❌ Failed: {failed}"
    )


# ── /gcmute ───────────────────────────────────────────────────
@app.on_message(filters.command(["gcmute"]))
async def gcmute_command(client, message: Message):
    """Mute a user. Usage: /gcmute [duration] (reply) or /gcmute @username [duration]"""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    user_id, display = await _resolve_target(client, message)
    if not user_id:
        return await message.reply_text(
            "❌ Usage:\n"
            "• Reply to a user's message: /gcmute [duration]\n"
            "• /gcmute @username [duration]"
        )

    args = message.command[1:]
    if message.reply_to_message:
        duration_str = " ".join(args) if args else ""
    else:
        duration_str = " ".join(args[1:]) if len(args) > 1 else ""

    duration = parse_duration(duration_str) if duration_str else timedelta(days=3)
    until = datetime.utcnow() + duration

    try:
        await client.restrict_chat_member(chat_id, user_id, MUTED_PERMS, until_date=until)
        dur_display = duration_str or "3d"
        await message.reply_text(
            f"🔇 **User Muted**\n\n👤 {display}\n⏱️ Duration: {dur_display}"
        )
    except ChatAdminRequired:
        await message.reply_text("❌ I need 'Restrict Members' permission!")
    except UserAdminInvalid:
        await message.reply_text("❌ Can't mute an admin!")
    except Exception as e:
        await message.reply_text(f"❌ Failed: {e}")


# ── /gcunmute ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcunmute"]))
async def gcunmute_command(client, message: Message):
    """Unmute a user. Usage: /gcunmute (reply) or /gcunmute @username"""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    user_id, display = await _resolve_target(client, message)
    if not user_id:
        return await message.reply_text(
            "❌ Usage:\n"
            "• Reply to a user's message: /gcunmute\n"
            "• /gcunmute @username"
        )

    try:
        await client.restrict_chat_member(chat_id, user_id, OPEN_PERMS)
        await message.reply_text(
            f"🔊 **User Unmuted**\n\n👤 {display}\n✅ All restrictions removed."
        )
    except Exception as e:
        await message.reply_text(f"❌ Failed to unmute: {e}")


# ── /unmuteall ────────────────────────────────────────────────
@app.on_message(filters.command(["unmuteall"]))
async def unmuteall_command(client, message: Message):
    """Restore default group permissions (unmute everyone)."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    try:
        await client.set_chat_permissions(chat_id, OPEN_PERMS)
        await message.reply_text(
            "🔊 **Unmute All Complete**\n\n"
            "✅ All group restrictions lifted. Default permissions restored."
        )
    except Exception as e:
        await message.reply_text(f"❌ Failed to unmute all: {e}")


# ─────────────────────────────────────────────────────────────
#  PIN & CUSTOM MESSAGE COMMANDS
# ─────────────────────────────────────────────────────────────

DROP_LINK_TEXT = (
    "🔗 **DROP YOUR LINK NOW!**\n\n"
    "📌 Share your Twitter/X profile link below.\n"
    "⚠️ One link per user. Duplicates will be deleted.\n"
    "✅ After sharing, wait for further instructions from admins."
)


# ── /p — Pin the default 'drop link' message ─────────────────
@app.on_message(filters.command(["p"]))
async def pin_drop_link_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    sent = await client.send_message(chat_id, DROP_LINK_TEXT)
    try:
        await client.pin_chat_message(chat_id, sent.id)
    except Exception as e:
        logger.warning(f"/p pin failed: {e}")


# ── /setrs, /setrs2, /setrs3, /setrs4 ────────────────────────
for _slot in range(1, 5):
    def _make_setrs(slot):
        cmd = "setrs" if slot == 1 else f"setrs{slot}"

        @app.on_message(filters.command([cmd]))
        async def _setrs(client, message: Message, _s=slot):
            if message.chat.type == enums.ChatType.PRIVATE:
                return await message.reply_text("Groups only!")
            chat_id = message.chat.id
            if not await is_group_admin(client, chat_id, message.from_user.id):
                return await message.reply_text("❌ Admins only!")

            if message.reply_to_message and message.reply_to_message.text:
                text = message.reply_to_message.text
            else:
                parts = message.text.split(None, 1)
                if len(parts) < 2:
                    suffix = "" if _s == 1 else str(_s)
                    return await message.reply_text(
                        f"❌ Usage: `/setrs{suffix} <your custom message>`\n"
                        "Or reply to a message."
                    )
                text = parts[1]

            await db_set_rs(chat_id, _s, text)
            await message.reply_text(f"✅ Custom pin message **RS{_s}** saved!")

        return _setrs

    _make_setrs(_slot)


# ── /rs1, /rs2, /rs3, /rs4 ───────────────────────────────────
for _slot in range(1, 5):
    def _make_rs(slot):
        @app.on_message(filters.command([f"rs{slot}"]))
        async def _rs(client, message: Message, _s=slot):
            if message.chat.type == enums.ChatType.PRIVATE:
                return await message.reply_text("Groups only!")
            chat_id = message.chat.id
            if not await is_group_admin(client, chat_id, message.from_user.id):
                return await message.reply_text("❌ Admins only!")

            text = await db_get_rs(chat_id, _s)
            if not text:
                suffix = "" if _s == 1 else str(_s)
                return await message.reply_text(
                    f"❌ No custom message set for RS{_s}.\n"
                    f"Use `/setrs{suffix} <message>` to set one."
                )
            sent = await client.send_message(chat_id, text)
            try:
                await client.pin_chat_message(chat_id, sent.id)
            except Exception as e:
                logger.warning(f"/rs{_s} pin failed: {e}")

        return _rs

    _make_rs(_slot)


# ─────────────────────────────────────────────────────────────
#  SETTINGS COMMANDS
# ─────────────────────────────────────────────────────────────

# ── /gcsettings ───────────────────────────────────────────────
@app.on_message(filters.command(["gcsettings"]))
async def gcsettings_command(client, message: Message):
    """Show current group settings."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    db = await get_db()
    doc = await db.gc_settings.find_one({"chat_id": chat_id}) or {}
    session = await db_get_active_session(chat_id)
    warn_limit = doc.get("warn_limit", 3)
    anon_mode = doc.get("anon_mode", False)
    rs_slots = [f"RS{i}: {'set ✅' if doc.get(f'rs{i}') else 'not set ❌'}" for i in range(1, 5)]

    text = (
        f"⚙️ **GC Settings — {message.chat.title}**\n\n"
        f"📌 Session: {'Active ✅' if session else 'None ❌'}\n"
        f"⚠️ Warn Limit: **{warn_limit}**\n"
        f"🕵️ Anon Mode: {'ON ✅' if anon_mode else 'OFF ❌'}\n"
        f"🔗 Max Links/User: **{MAX_LINKS_PER_USER}**\n"
        f"🛡️ Fraud Detection: {'ON ✅' if ENABLE_FRAUD_DETECTION else 'OFF ❌'}\n\n"
        f"📌 **Custom Pin Messages:**\n" + "\n".join(f"  • {s}" for s in rs_slots)
    )
    await message.reply_text(text)


# ── /anonmode ─────────────────────────────────────────────────
@app.on_message(filters.command(["anonmode"]))
async def anonmode_command(client, message: Message):
    """Toggle anonymous admin mode."""
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    if not await is_group_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("❌ Admins only!")

    new_state = await db_toggle_anon_mode(chat_id)
    state_text = (
        "**ON** — admin names are hidden in bot messages."
        if new_state else
        "**OFF** — admin names are shown."
    )
    await message.reply_text(f"🕵️ Anonymous Admin Mode: {state_text}")


# ─────────────────────────────────────────────────────────────
#  USER COMMANDS
# ─────────────────────────────────────────────────────────────

# ── /gchelp ───────────────────────────────────────────────────
@app.on_message(filters.command(["gchelp"]))
async def gchelp_command(client, message: Message):
    await message.reply_text(
        "🤖 **Bot Help Menu**\n\n"
        "👤 **General:**\n"
        "/gchelp — This menu\n"
        "/gcrule — Show group rules\n\n"
        "👥 **User Commands:**\n"
        "/gcmulti — Users with multiple links\n"
        "/gclist — All users who submitted links\n"
        "/gccount — Total user count\n"
        "/srlist — Pending SR requests\n\n"
        "🛡️ **Admin Commands:**\n"
        "/gcstarts — Start a new session\n"
        "/gcclose — Lock the group\n"
        "/gcreopen — Unlock the group\n"
        "/gcend — End session & clear data\n"
        "/gcclear — Clear data (keep session)\n"
        "/gcclearall — Delete recent messages\n"
        "/gcrefresh — Refresh admin list\n"
        "/gccheck — Enable check/ad tracking\n"
        "/unsafe — List unverified users\n"
        "/safe — List verified users\n"
        "/muteunsafe [duration] — Mute unverified users\n"
        "/unmuteunsafe — Unmute unverified users\n"
        "/gcmute [duration] — Mute user (reply / @user)\n"
        "/gcunmute — Unmute user (reply / @user)\n"
        "/unmuteall — Unmute everyone\n"
        "/gcsr — Request SR (reply)\n"
        "/gcadd — Add to ad list (reply)\n"
        "/gclink — Get user's links (reply)\n"
        "/gcsetwarnlimit — Set warn limit\n"
        "/gcsettings — View group settings\n"
        "/anonmode — Toggle anon admin\n\n"
        "📌 **Pin Commands:**\n"
        "/p — Pin 'drop link' message\n"
        "/setrs [/setrs2-4] — Set custom pin\n"
        "/rs1-4 — Pin custom message\n\n"
        "👑 **Owner (PM only):**\n"
        "/gcpanel — Admin panel\n"
        "/gcmanage — Manage groups\n"
        "/gcaddgroup — Add group\n"
        "/gcremovegroup — Remove group\n"
        "/gclinks — Links overview\n\n"
        "⏱️ **Duration Format:** `10s` `5m` `2h` `3d`"
    )


# ── /gcrule ───────────────────────────────────────────────────
@app.on_message(filters.command(["gcrule"]))
async def gcrule_command(client, message: Message):
    await message.reply_text(
        "📜 **Group Rules for Like Sessions**\n\n"
        "> 1️⃣ Submit your Twitter/X link when requested\n"
        "> 2️⃣ Complete all required interactions (likes/retweets)\n"
        "> 3️⃣ Don't share multiple links unless permitted\n"
        "> 4️⃣ Don't share the same link as other users\n"
        "> 5️⃣ Verify your submission if asked\n"
        "> 6️⃣ Submit screen recording in DM when requested\n"
        "> 7️⃣ Follow admin instructions promptly\n\n"
        "⚠️ **Violations may result in:**\n"
        "> • Fraud alerts\n"
        "> • Warnings\n"
        "> • Temporary mute\n"
        "> • Removal from session\n"
        "> • Ban from future sessions\n\n"
        "🚨 **Fraud Detection Active**\n"
        "The bot auto-detects: duplicate links, multiple accounts sharing a link, "
        "and excessive link submissions.\n\n"
        "Stay safe and follow the rules! 🤝\n\n"
        "Powered by @Super_Fasttt_Bot"
    )


# ── /gcmulti ─────────────────────────────────────────────────
@app.on_message(filters.command(["gcmulti"]))
async def gcmulti_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session! Use /gcstarts to begin.")

    multi_users = await db_get_users_with_multiple_links(chat_id, str(session["_id"]))
    if not multi_users:
        return await message.reply_text("✅ No users with multiple links found!")

    text = "👥 **Users with Multiple Links:**\n\n"
    for u in multi_users:
        text += f"• @{u.get('username', 'Unknown')} — {u.get('count', 0)} links\n"
    await message.reply_text(text)


# ── /gclist ───────────────────────────────────────────────────
@app.on_message(filters.command(["gclist"]))
async def gclist_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session! Use /gcstarts to begin.")

    session_id = str(session["_id"])
    users = await db_get_all_users_with_links(chat_id, session_id)
    if not users:
        return await message.reply_text("❌ No users have submitted links yet!")

    text = "📋 **Users who submitted links:**\n\n"
    for idx, u in enumerate(users, 1):
        uname = u.get("username", "Unknown")
        uid = u.get("user_id")
        links = u.get("links", [])
        tw_user = extract_username_from_link(links[0]) if links else "unknown"
        if links:
            text += f"{idx}. [{tw_user}]({links[0]}) 𝕏 "
        else:
            text += f"{idx}. {tw_user} 𝕏 "
        text += f"[(@{uname})](tg://user?id={uid})\n"

    stats = await db_get_session_stats(chat_id, session_id)
    text += f"\n📊 **Total:** {stats['unique_users']} users | {stats['total_links']} links"
    await message.reply_text(text, disable_web_page_preview=True)


# ── /gccount ─────────────────────────────────────────────────
@app.on_message(filters.command(["gccount"]))
async def gccount_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    chat_id = message.chat.id
    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session!")
    stats = await db_get_session_stats(chat_id, str(session["_id"]))
    await message.reply_text(
        f"📊 Total users with submitted links: **{stats['unique_users']}**"
    )


# ── /gclink ───────────────────────────────────────────────────
@app.on_message(filters.command(["gclink"]))
async def gclink_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    if not message.reply_to_message:
        return await message.reply_text("❌ Reply to a user's message to get their links!")

    chat_id = message.chat.id
    u = message.reply_to_message.from_user
    session = await db_get_active_session(chat_id)
    if not session:
        return await message.reply_text("❌ No active session!")

    links = await db_get_user_links(chat_id, u.id, str(session["_id"]))
    if not links:
        return await message.reply_text(f"No links found for @{u.username or u.first_name}")

    text = f"🔗 **Links from @{u.username or u.first_name}:**\n\n"
    for idx, lnk in enumerate(links, 1):
        text += f"{idx}. 🔐 `{lnk['encrypted_link']}`\n"
    await message.reply_text(text)


# ── /srlist ───────────────────────────────────────────────────
@app.on_message(filters.command(["srlist"]))
async def srlist_command(client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("Groups only!")
    sr_users = await db_get_sr_list(message.chat.id)
    if not sr_users:
        return await message.reply_text("✅ No pending screen recording requests!")

    text = "📹 **Users requested to submit SR:**\n\n"
    for u in sr_users:
        text += f"• @{u.get('username', 'Unknown')}\n"
    await message.reply_text(text)


# ─────────────────────────────────────────────────────────────
#  MESSAGE HANDLER — track Twitter/X links
# ─────────────────────────────────────────────────────────────

@app.on_message(
    filters.group
    & ~filters.command
    & (filters.text | filters.caption)
)
async def handle_group_messages(client, message: Message):
    """Track Twitter/X links and ad/done keywords in groups."""
    chat_id = message.chat.id
    if not message.from_user:
        return  # Channel posts inside groups

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Only act on allowed groups with active sessions
    if not await db_is_group_allowed(chat_id):
        return
    session = await db_get_active_session(chat_id)
    if not session or not session.get("is_active"):
        return

    session_id = str(session["_id"])
    raw_text = (message.text or message.caption or "").lower().strip()

    # ── Ad/done detection ──────────────────────────────────────
    if raw_text and await db_is_ad_tracking_enabled(chat_id):
        ad_keywords = ["all done", "all dn", "done", "ad"]
        for kw in ad_keywords:
            if kw in raw_text:
                already_safe = await db_is_user_in_safe_list(chat_id, session_id, user_id)
                if not already_safe:
                    await db_add_to_safe_list(chat_id, session_id, user_id, username, kw)
                    await db_mark_user_links_verified(chat_id, user_id, session_id)

                safe_users = await db_get_safe_users(chat_id, session_id)
                position = next(
                    (i + 1 for i, u in enumerate(safe_users) if u["user_id"] == user_id), 0
                )
                user_links = await db_get_user_links(chat_id, user_id, session_id)
                if user_links:
                    tw_user = extract_username_from_link(user_links[0]["link"])
                    tw_link = user_links[0]["link"]
                    reply = (
                        f"{position}. 🆇 [{tw_user}]({tw_link})\n\n"
                        "✅ Link tracked and encrypted!"
                    )
                    try:
                        await message.reply_text(reply, disable_web_page_preview=True)
                    except Exception as e:
                        logger.error(f"ad reply: {e}")
                break

    # ── Link extraction ────────────────────────────────────────
    raw_full = message.text or message.caption or ""
    links = extract_twitter_links(raw_full)
    if not links:
        return

    # Admins' links are ignored
    if await is_group_admin(client, chat_id, user_id):
        return

    # Check if user already hit the limit
    existing = await db_get_user_links(chat_id, user_id, session_id)
    if len(existing) >= MAX_LINKS_PER_USER:
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await client.send_message(
                chat_id,
                f"⚠️ Warning @{username}\n\n"
                f"You've already submitted {len(existing)} link(s). "
                f"Maximum allowed: {MAX_LINKS_PER_USER}.\n"
                "Your message has been deleted.",
            )
        except Exception as e:
            logger.error(f"handle_group_messages warn: {e}")
        return

    for link in links:
        # Duplicate link check
        if ENABLE_FRAUD_DETECTION:
            is_dup, dup_users = await db_check_duplicate_link(chat_id, user_id, link, session_id)
            if is_dup:
                orig = dup_users[0].get("username", "Unknown") if dup_users else "Unknown"
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await client.send_message(
                        chat_id,
                        f"⚠️ Warning @{username}\n\n"
                        f"This link was already submitted by @{orig}.\n"
                        "Duplicate links are not allowed. Your message has been deleted.",
                    )
                except Exception as e:
                    logger.error(f"dup warn: {e}")
                continue

        encrypted = encrypt_link(link)
        await db_add_link(chat_id, user_id, username, link, encrypted, session_id)
        logger.info(f"Link stored: {username} ({user_id}) — {encrypted}")


# ─────────────────────────────────────────────────────────────
#  MODULE METADATA (SHASHA_DRUGZ plugin system)
# ─────────────────────────────────────────────────────────────

__menu__ = "CMD_MANAGE"
__mod_name__ = "GC_MANAGER"
__help__ = """
**GC Manager** — Full group session & link tracking module.

🔧 **Session:**
/gcstarts — Start session / unlock group
/gcclose — Lock group (session stays)
/gcreopen — Unlock group
/gcend — End session & clear all data
/gcclear — Clear data, keep session
/gcclearall — Delete recent messages
/gcrefresh — Refresh admin list
✅ **Check & Verify:**
/gccheck — Enable ad/done tracking
/unsafe — List unverified users
/safe — List verified users
🔇 **Mute:**
/muteunsafe [dur] — Mute unverified
/unmuteunsafe — Unmute unverified
/gcmute [dur] — Mute user (reply / @user)
/gcunmute — Unmute user (reply / @user)
/unmuteall — Restore group permissions
📹 **SR / Ad:**
/gcsr — Request screen recording (reply)
/gcadd — Add user to ad list (reply)
/srlist — Pending SR list
📌 **Pin:**
/p — Pin 'drop link' message
/setrs [/setrs2-4] — Save custom pin text
/rs1-4 — Send & pin custom message
👥 **Users:**
/gclist — All submitted links
/gcmulti — Users with multiple links
/gccount — Unique user count
/gclink — Links of a user (reply)
⚙️ **Settings:**
/gcsettings — View current settings
/anonmode — Toggle anon admin mode
/gcsetwarnlimit <n> — Set warn limit
👑 **Owner (PM):**
/gcpanel — Admin panel
/gcmanage — Group management
/gcaddgroup — Add allowed group
/gcremovegroup — Remove allowed group
/gclinks — Links overview per group
"""
