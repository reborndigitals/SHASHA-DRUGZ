# ============================================================
#   SHASHA USERBOT MODULE — FULL SINGLE FILE  v2.3
#   Compatible with SHASHA_DRUGZ framework
#   All commands prefixed with dot (.)
# ============================================================
import asyncio
import io
import logging
import os
import platform
import re
import textwrap
import time
import traceback
import random
from datetime import datetime, timedelta
from functools import wraps

import httpx
import motor.motor_asyncio
import psutil
from pyrogram import Client, filters
from pyrogram.errors import (
    AuthKeyUnregistered,
    FloodWait,
    SessionRevoked,
)
from pyrogram.types import (
    ChatPermissions,
    ChatPrivileges,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from SHASHA_DRUGZ import app
from config import API_HASH, API_ID, BOT_USERNAME, MONGO_DB_URI

# ─────────────────────────────────────────────
#  LOGGER
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s | SHASHA | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("SHASHA")

# ─────────────────────────────────────────────
#  COLLECTION NAME CONSTANTS
# ─────────────────────────────────────────────
COL_CFG       = "cfg"
COL_AFK       = "afk"
COL_PMGUARD   = "pmguard"
COL_WARNS     = "warns"
COL_RAID      = "raid"
COL_SAVED     = "saved"
COL_SETUSER   = "setuser"
COL_WHISPER   = "whisper"
COL_AUTOREPLY = "autoreply"
COL_FLOOD     = "flood"

# ─────────────────────────────────────────────
#  HANDLER GROUP CONSTANTS
#  group=0  → default — all /commands live here
#  group=5  → passive watchers (AFK, view-once)
#  group=10 → session string catcher (lowest priority)
# ─────────────────────────────────────────────
GRP_DEFAULT  = 0
GRP_WATCHERS = 5
GRP_SESSION  = 10

# ─────────────────────────────────────────────
#  GLOBAL HTTP CLIENT
# ─────────────────────────────────────────────
HTTP = httpx.AsyncClient(timeout=30)

# ─────────────────────────────────────────────
#  BOT START TIME
# ─────────────────────────────────────────────
_BOT_START = time.time()

# ─────────────────────────────────────────────
#  DATABASE HELPERS  (fully isolated per user)
# ─────────────────────────────────────────────
_mongo        = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DB_URI)
_db           = _mongo["SHASHA_USERBOT"]
_sessions_col = _db["_sessions"]
_gcol         = _db["global_settings"]


def _col(uid: int, name: str):
    return _db[f"u{uid}_{name}"]


async def _get(uid: int, col: str, key: str, default=None):
    try:
        doc = await _col(uid, col).find_one({"_id": key})
        return doc["v"] if doc else default
    except Exception as e:
        log.error(f"_get({uid},{col},{key}): {e}")
        return default


async def _set(uid: int, col: str, key: str, value):
    try:
        await _col(uid, col).update_one(
            {"_id": key}, {"$set": {"v": value}}, upsert=True
        )
    except Exception as e:
        log.error(f"_set({uid},{col},{key}): {e}")


async def _del(uid: int, col: str, key: str):
    try:
        await _col(uid, col).delete_one({"_id": key})
    except Exception as e:
        log.error(f"_del({uid},{col},{key}): {e}")


async def _all_keys(uid: int, col: str):
    try:
        cursor = _col(uid, col).find({})
        return [doc["_id"] async for doc in cursor]
    except Exception as e:
        log.error(f"_all_keys({uid},{col}): {e}")
        return []


async def _gget(key: str, default=None):
    try:
        doc = await _gcol.find_one({"_id": key})
        return doc["v"] if doc else default
    except Exception as e:
        log.error(f"_gget({key}): {e}")
        return default


async def _gset(key: str, value):
    try:
        await _gcol.update_one({"_id": key}, {"$set": {"v": value}}, upsert=True)
    except Exception as e:
        log.error(f"_gset({key}): {e}")


# ─────────────────────────────────────────────
#  OWNER HELPERS
# ─────────────────────────────────────────────
async def _get_main_owner() -> int | None:
    v = await _gget("main_owner")
    return int(v) if v else None


async def _set_main_owner(uid: int):
    await _gset("main_owner", uid)


async def _is_main_owner(uid: int) -> bool:
    mo = await _get_main_owner()
    return mo is not None and uid == mo


# ─────────────────────────────────────────────
#  SESSION STORE
# ─────────────────────────────────────────────
async def _save_session(uid: int, session: str):
    try:
        await _sessions_col.update_one(
            {"_id": uid}, {"$set": {"session": session}}, upsert=True
        )
        await _set(uid, COL_CFG, "session", session)
    except Exception as e:
        log.error(f"_save_session({uid}): {e}")


async def _load_session(uid: int) -> str | None:
    try:
        doc = await _sessions_col.find_one({"_id": uid})
        return doc["session"] if doc else None
    except Exception as e:
        log.error(f"_load_session({uid}): {e}")
        return None


async def _delete_session(uid: int):
    try:
        await _sessions_col.delete_one({"_id": uid})
        await _del(uid, COL_CFG, "session")
    except Exception as e:
        log.error(f"_delete_session({uid}): {e}")


# ─────────────────────────────────────────────
#  USERBOT POOL
# ─────────────────────────────────────────────
_active_userbots: dict[int, Client] = {}


async def _get_userbot(uid: int) -> Client | None:
    if uid in _active_userbots:
        ub = _active_userbots[uid]
        if ub.is_connected:
            return ub
        _active_userbots.pop(uid, None)

    session = await _load_session(uid)
    if not session:
        return None
    try:
        ub = Client(
            name=f"shasha_ub_{uid}",
            session_string=session,
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
            no_updates=False,
        )
        await ub.start()
        _active_userbots[uid] = ub
        await _attach_userbot_handlers(uid, ub)
        log.info(f"Userbot started for uid={uid}")
        return ub
    except (SessionRevoked, AuthKeyUnregistered):
        log.warning(f"Session revoked for uid={uid}, removing.")
        await _delete_session(uid)
        return None
    except Exception as e:
        log.error(f"_get_userbot({uid}): {e}")
        return None


async def _stop_userbot(uid: int):
    ub = _active_userbots.pop(uid, None)
    if ub and ub.is_connected:
        try:
            await ub.stop()
            log.info(f"Userbot stopped for uid={uid}")
        except Exception as e:
            log.error(f"_stop_userbot({uid}): {e}")


async def _cleanup_userbots():
    while True:
        await asyncio.sleep(300)
        for uid in list(_active_userbots.keys()):
            try:
                if not _active_userbots[uid].is_connected:
                    _active_userbots.pop(uid, None)
                    log.info(f"Cleaned up disconnected userbot uid={uid}")
            except Exception as e:
                _active_userbots.pop(uid, None)
                log.error(f"Cleanup error uid={uid}: {e}")


asyncio.get_event_loop().create_task(_cleanup_userbots())


async def _restore_all_sessions():
    await asyncio.sleep(3)
    try:
        async for doc in _sessions_col.find({}):
            uid = doc["_id"]
            try:
                await _get_userbot(uid)
            except Exception as e:
                log.error(f"Restore session uid={uid}: {e}")
    except Exception as e:
        log.error(f"_restore_all_sessions: {e}")


asyncio.get_event_loop().create_task(_restore_all_sessions())


# ─────────────────────────────────────────────
#  require_ub DECORATOR
# ─────────────────────────────────────────────
def require_ub(func):
    @wraps(func)
    async def wrapper(client, m: Message, *args, **kwargs):
        ub = await _get_userbot(m.from_user.id)
        if not ub:
            await m.reply(
                "❌ No userbot connected.\nUse /usersession to add one.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "➕ Add Session",
                        url=f"https://t.me/{BOT_USERNAME}?start=session",
                    )
                ]]),
            )
            return
        return await func(client, m, ub, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────
#  DYNAMIC USERBOT HANDLERS (on userbot client)
# ─────────────────────────────────────────────
async def _attach_userbot_handlers(uid: int, ub: Client):
    _me_cache: dict = {}

    async def _me():
        if "me" not in _me_cache:
            _me_cache["me"] = await ub.get_me()
        return _me_cache["me"]

    @ub.on_message(filters.group & ~filters.bot)
    async def _ub_group(client, m: Message):
        if not m.from_user:
            return
        if m.from_user.id == uid:
            afk = await _get(uid, COL_AFK, "status")
            if afk:
                await _del(uid, COL_AFK, "status")
                try:
                    elapsed = int(time.time() - afk["since"])
                    await m.reply(f"✅ Welcome back! (AFK for {elapsed}s)")
                except Exception as e:
                    log.error(f"AFK clear: {e}")
            return
        if m.reply_to_message and m.reply_to_message.from_user:
            if m.reply_to_message.from_user.id == uid:
                afk = await _get(uid, COL_AFK, "status")
                if afk:
                    elapsed = int(time.time() - afk["since"])
                    try:
                        await m.reply(
                            f"🌙 **User is AFK**\n"
                            f"Reason: {afk['reason']}\n"
                            f"Away: {elapsed}s ago"
                        )
                    except Exception as e:
                        log.error(f"AFK reply: {e}")
        if m.text:
            me = await _me()
            tag_on = await _get(uid, COL_CFG, "tagalert")
            if tag_on and me.username and f"@{me.username.lower()}" in m.text.lower():
                log_chat = await _get(uid, COL_CFG, "logger")
                if log_chat:
                    try:
                        await client.send_message(
                            int(log_chat),
                            f"🔔 **Tag Alert**\n"
                            f"Group: {getattr(m.chat,'title',m.chat.id)} (`{m.chat.id}`)\n"
                            f"By: [{m.from_user.first_name}](tg://user?id={m.from_user.id})\n"
                            f"Msg: {m.text}",
                        )
                    except Exception as e:
                        log.error(f"Tagalert: {e}")
        raid = await _get(uid, COL_RAID, "active")
        if raid and m.from_user.id == raid.get("target"):
            last = await _get(uid, COL_RAID, "last_reply") or 0
            if time.time() - last >= 5:
                await _set(uid, COL_RAID, "last_reply", time.time())
                try:
                    await m.reply(random.choice(raid.get("replies", ["👀"])))
                except Exception as e:
                    log.error(f"Raid reply: {e}")
        flood_cfg = await _get(uid, COL_FLOOD, f"cfg_{m.chat.id}")
        if flood_cfg and flood_cfg.get("on"):
            sender = m.from_user.id
            limit  = flood_cfg.get("limit", 5)
            window = flood_cfg.get("window", 10)
            key    = f"track_{m.chat.id}_{sender}"
            track  = await _get(uid, COL_FLOOD, key) or {"count": 0, "since": time.time()}
            if time.time() - track["since"] > window:
                track = {"count": 1, "since": time.time()}
            else:
                track["count"] += 1
            await _set(uid, COL_FLOOD, key, track)
            if track["count"] >= limit:
                try:
                    until = datetime.now() + timedelta(seconds=60)
                    await client.restrict_chat_member(
                        m.chat.id, sender,
                        permissions=ChatPermissions(),
                        until_date=until,
                    )
                    await _set(uid, COL_FLOOD, key, {"count": 0, "since": time.time()})
                    try:
                        await m.reply(
                            f"🚫 [{m.from_user.first_name}](tg://user?id={sender}) "
                            f"muted 60s for flooding."
                        )
                    except Exception:
                        pass
                except Exception as e:
                    log.error(f"Antiflood mute: {e}")
        if m.text:
            keywords = await _all_keys(uid, COL_AUTOREPLY)
            txt_lower = m.text.lower()
            for kw in keywords:
                if kw.lower() in txt_lower:
                    reply_text = await _get(uid, COL_AUTOREPLY, kw)
                    if reply_text:
                        try:
                            await m.reply(reply_text)
                        except Exception as e:
                            log.error(f"Autoreply: {e}")
                        break

    @ub.on_message(filters.private & ~filters.bot & ~filters.me)
    async def _ub_pmguard(client, m: Message):
        guard = await _get(uid, COL_PMGUARD, "status")
        if not guard or not guard.get("on"):
            return
        sender = m.from_user.id
        if await _get(uid, COL_PMGUARD, f"approved_{sender}"):
            return
        warns   = (await _get(uid, COL_PMGUARD, f"warn_{sender}") or 0) + 1
        limit   = await _get(uid, COL_PMGUARD, "limit") or 3
        msg_txt = (
            await _get(uid, COL_PMGUARD, "msg")
            or f"⚠️ Warning {warns}/{limit}. You are not authorized to PM."
        )
        warn_img = await _get(uid, COL_PMGUARD, "img")
        await _set(uid, COL_PMGUARD, f"warn_{sender}", warns)
        if warns >= limit:
            try:
                await m.reply("🚫 You have been blocked.")
                await client.block_user(sender)
                log.info(f"PMGuard blocked {sender} for uid={uid}")
            except Exception as e:
                log.error(f"PMGuard block: {e}")
        else:
            try:
                if warn_img:
                    await client.send_photo(sender, warn_img, caption=msg_txt)
                else:
                    await m.reply(msg_txt)
            except Exception as e:
                log.error(f"PMGuard warn: {e}")

    @ub.on_message(filters.private & filters.me)
    async def _ub_self_msg(client, m: Message):
        await _del(uid, COL_AFK, "status")


# ─────────────────────────────────────────────
#  COMMAND FILTER: dot-prefix
# ─────────────────────────────────────────────
def dot_cmd(*cmds):
    patterns = [re.compile(rf"^\.{re.escape(c)}(\s|$)", re.I) for c in cmds]

    def _filter(_, __, m: Message):
        if not m.text:
            return False
        return any(p.match(m.text) for p in patterns)

    return filters.create(_filter)


def _args(m: Message) -> str:
    parts = m.text.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


async def _get_target(m: Message):
    if m.reply_to_message and m.reply_to_message.from_user:
        return m.reply_to_message.from_user.id
    first = _args(m).split()[0] if _args(m).split() else None
    if first:
        raw = first.lstrip("@")
        try:
            return int(raw)
        except ValueError:
            try:
                user = await app.get_users(raw)
                return user.id
            except Exception as e:
                log.error(f"_get_target resolve {raw}: {e}")
    return None


# ─────────────────────────────────────────────
#  /usersession
# ─────────────────────────────────────────────
async def _process_session(m: Message, session: str):
    uid  = m.from_user.id
    prog = await m.reply("🔄 Validating session…")
    try:
        test = Client(
            name=f"test_{uid}",
            session_string=session,
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
            no_updates=True,
        )
        await test.start()
        me = await test.get_me()
        await test.stop()
    except Exception as e:
        await prog.edit(f"❌ Invalid session.\nError: `{e}`")
        return
    await _save_session(uid, session)
    await _stop_userbot(uid)
    ub = await _get_userbot(uid)
    if ub:
        await prog.edit(
            f"✅ **Userbot Connected!**\n"
            f"👤 Name    : `{me.first_name}`\n"
            f"🆔 ID      : `{me.id}`\n"
            f"📱 Username: @{me.username or 'N/A'}"
        )
    else:
        await prog.edit("❌ Session valid but failed to start. Try again.")


@app.on_message(filters.command("usersession"))
async def cmd_usersession(_, m: Message):
    if (
        m.reply_to_message
        and m.reply_to_message.text
        and len(m.reply_to_message.text) >= 200
    ):
        await _process_session(m, m.reply_to_message.text.strip())
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📥 Type Session String",
            url=f"https://t.me/{BOT_USERNAME}?start=session",
        )
    ]])
    await m.reply(
        "**🔑 Connect Your Userbot**\n\n"
        "Send your Pyrogram session string in this private chat, "
        "or reply to it with `/usersession`.\n\n"
        "Generate one at [@StringFatherBot](https://t.me/StringFatherBot)",
        reply_markup=kb,
    )


# ─────────────────────────────────────────────
#  [FIX] Session string catcher — group=10
#  Runs last so it never blocks any /command handlers.
# ─────────────────────────────────────────────
@app.on_message(
    filters.private
    & filters.text
    & ~filters.regex(r"^[/\.]"),
    group=GRP_SESSION,
)
async def _catch_session_string(_, m: Message):
    if not m.text:
        return
    if m.text.startswith("/") or m.text.startswith("."):
        return
    txt = m.text.strip()
    if len(txt) < 200 or not re.match(r"^[A-Za-z0-9_\-]{200,}$", txt):
        return
    await _process_session(m, txt)


# ─────────────────────────────────────────────
#  /rmuserbot
# ─────────────────────────────────────────────
@app.on_message(filters.command("rmuserbot"))
async def cmd_rmuserbot(_, m: Message):
    caller = m.from_user.id
    is_mo  = await _is_main_owner(caller)
    if m.command[1:] and is_mo:
        try:
            target = int(m.command[1])
        except ValueError:
            return await m.reply("❌ Provide a valid user ID.")
    else:
        target = caller
    if target != caller and not is_mo:
        return await m.reply("❌ Only the main bot owner can remove another user's bot.")
    await _stop_userbot(target)
    await _delete_session(target)
    names = await _db.list_collection_names()
    for col in names:
        if col.startswith(f"u{target}_"):
            await _db.drop_collection(col)
            log.info(f"Dropped collection {col}")
    await m.reply(f"🗑️ Userbot for `{target}` removed and all data wiped.")


# ─────────────────────────────────────────────
#  /rmalluserbots (main owner only)
# ─────────────────────────────────────────────
@app.on_message(filters.command("rmalluserbots"))
async def cmd_rmalluserbots(_, m: Message):
    if not await _is_main_owner(m.from_user.id):
        return await m.reply("❌ Main bot owner only.")
    for uid in list(_active_userbots.keys()):
        await _stop_userbot(uid)
    names = await _db.list_collection_names()
    for col in names:
        if re.match(r"^u\d+_", col):
            await _db.drop_collection(col)
    await _sessions_col.drop()
    log.info("All userbots removed by main owner.")
    await m.reply("🗑️ All userbots and user data wiped.")


# ─────────────────────────────────────────────
#  [FIX-BUG1] View-once saver — group=5
#  Was in group=0 (filters.private), blocking ALL private
#  messages. Now in group=5 — command handlers run first.
# ─────────────────────────────────────────────
@app.on_message(filters.private, group=GRP_WATCHERS)
async def _catch_view_once(_, m: Message):
    if not m.photo and not m.video:
        return
    if not getattr(m, "ttl_seconds", None):
        return
    if not m.from_user:
        return
    uid  = m.from_user.id
    path = await app.download_media(m)
    await _set(uid, COL_SAVED, f"vonce_{m.id}", path)
    await m.reply("📸 View-once media saved! Use `.saved` to retrieve.")


# ─────────────────────────────────────────────
#  [FIX-BUG2] AFK main-bot watcher — group=5
#  Was in group=0 (filters.group & ~filters.bot), blocking
#  ALL group commands. Now in group=5 — runs after commands.
# ─────────────────────────────────────────────
@app.on_message(filters.group & ~filters.bot, group=GRP_WATCHERS)
async def _afk_main_watcher(_, m: Message):
    if not m.from_user or not m.reply_to_message or not m.reply_to_message.from_user:
        return
    target_uid = m.reply_to_message.from_user.id
    afk = await _get(target_uid, COL_AFK, "status")
    if afk:
        elapsed = int(time.time() - afk["since"])
        try:
            await m.reply(
                f"🌙 **{m.reply_to_message.from_user.first_name}** is AFK\n"
                f"Reason: {afk['reason']}\n"
                f"Since: {elapsed}s ago"
            )
        except Exception as e:
            log.error(f"AFK main watcher: {e}")


# ─────────────────────────────────────────────
#  1. BAN / UNBAN / TBAN / SBAN / KICK
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("ban") & filters.group & filters.me)
@require_ub
async def cmd_ban(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide a username/ID.")
    try:
        await ub.ban_chat_member(m.chat.id, target)
        await m.reply(f"🔨 Banned `{target}`")
    except Exception as e:
        log.error(f"ban: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("unban") & filters.group & filters.me)
@require_ub
async def cmd_unban(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide a username/ID.")
    try:
        await ub.unban_chat_member(m.chat.id, target)
        await m.reply(f"✅ Unbanned `{target}`")
    except Exception as e:
        log.error(f"unban: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("tban") & filters.group & filters.me)
@require_ub
async def cmd_tban(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    args         = _args(m).split()
    duration_str = next((a for a in args if re.match(r"^\d+[mhd]$", a)), "1h")
    unit  = duration_str[-1]
    val   = int(duration_str[:-1])
    mult  = {"m": 60, "h": 3600, "d": 86400}.get(unit, 3600)
    until = datetime.now() + timedelta(seconds=val * mult)
    try:
        await ub.ban_chat_member(m.chat.id, target, until_date=until)
        await m.reply(f"⏳ Temp-banned `{target}` for {duration_str}")
    except Exception as e:
        log.error(f"tban: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("sban") & filters.group & filters.me)
@require_ub
async def cmd_sban(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return
    try:
        await ub.ban_chat_member(m.chat.id, target)
        try:
            await m.delete()
        except Exception:
            pass
    except Exception as e:
        log.error(f"sban: {e}")


@app.on_message(dot_cmd("kick") & filters.group & filters.me)
@require_ub
async def cmd_kick(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    try:
        await ub.ban_chat_member(m.chat.id, target)
        await ub.unban_chat_member(m.chat.id, target)
        await m.reply(f"👢 Kicked `{target}`")
    except Exception as e:
        log.error(f"kick: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  2. WARN / UNWARN / MUTE / UNMUTE
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("warn") & filters.group & filters.me)
@require_ub
async def cmd_warn(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user.")
    uid    = m.from_user.id
    key    = f"warn_{m.chat.id}_{target}"
    count  = (await _get(uid, COL_WARNS, key) or 0) + 1
    limit  = await _get(uid, COL_WARNS, "limit") or 3
    reason = _args(m) or "No reason"
    await _set(uid, COL_WARNS, key, count)
    if count >= limit:
        try:
            await ub.ban_chat_member(m.chat.id, target)
            await _set(uid, COL_WARNS, key, 0)
            await m.reply(f"⚠️ {count}/{limit} warns — **Banned** `{target}`\nReason: {reason}")
        except Exception as e:
            log.error(f"warn-ban: {e}")
            await m.reply(f"❌ {e}")
    else:
        await m.reply(f"⚠️ Warned `{target}` — {count}/{limit}\nReason: {reason}")


@app.on_message(dot_cmd("unwarn") & filters.group & filters.me)
async def cmd_unwarn(_, m: Message):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user.")
    uid = m.from_user.id
    await _set(uid, COL_WARNS, f"warn_{m.chat.id}_{target}", 0)
    await m.reply(f"✅ Warns cleared for `{target}`")


@app.on_message(dot_cmd("mute") & filters.group & filters.me)
@require_ub
async def cmd_mute(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    args  = _args(m).split()
    until = None
    label = ""
    raw   = next((a for a in args if re.match(r"^\d+[mhd]$", a)), None)
    if raw:
        unit  = raw[-1]
        val   = int(raw[:-1])
        mult  = {"m": 60, "h": 3600, "d": 86400}.get(unit, 60)
        until = datetime.now() + timedelta(seconds=val * mult)
        label = f" for {raw}"
    try:
        await ub.restrict_chat_member(
            m.chat.id, target,
            permissions=ChatPermissions(),
            until_date=until,
        )
        await m.reply(f"🔇 Muted `{target}`{label}")
    except Exception as e:
        log.error(f"mute: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("unmute") & filters.group & filters.me)
@require_ub
async def cmd_unmute(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    try:
        await ub.restrict_chat_member(
            m.chat.id, target,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await m.reply(f"🔊 Unmuted `{target}`")
    except Exception as e:
        log.error(f"unmute: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  3. ID / INFO / ADMINLIST / BOTLIST
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("id") & filters.me)
async def cmd_id(_, m: Message):
    lines = [f"**Chat ID:** `{m.chat.id}`"]
    if m.reply_to_message and m.reply_to_message.from_user:
        lines.append(f"**User ID:** `{m.reply_to_message.from_user.id}`")
    else:
        lines.append(f"**Your ID:** `{m.from_user.id}`")
    if m.reply_to_message and getattr(m.reply_to_message, "forward_from", None):
        lines.append(f"**Fwd From ID:** `{m.reply_to_message.forward_from.id}`")
    await m.reply("\n".join(lines))


@app.on_message(dot_cmd("info") & filters.me)
async def cmd_info(_, m: Message):
    user = (
        m.reply_to_message.from_user
        if m.reply_to_message and m.reply_to_message.from_user
        else m.from_user
    )
    if not user:
        return await m.reply("No user found.")
    uname = f"@{user.username}" if user.username else "—"
    await m.reply(
        f"👤 **User Info**\n"
        f"Name    : [{user.first_name}](tg://user?id={user.id})\n"
        f"Username: {uname}\n"
        f"ID      : `{user.id}`\n"
        f"Bot     : `{'Yes' if user.is_bot else 'No'}`"
    )


@app.on_message(dot_cmd("adminlist") & filters.group & filters.me)
async def cmd_adminlist(_, m: Message):
    admins = []
    async for member in app.get_chat_members(m.chat.id, filter="administrators"):
        title = member.custom_title or ""
        admins.append(
            f"• [{member.user.first_name}](tg://user?id={member.user.id})"
            + (f" — __{title}__" if title else "")
        )
    await m.reply(
        "**👮 Admin List:**\n" + "\n".join(admins) if admins else "No admins found."
    )


@app.on_message(dot_cmd("botlist") & filters.group & filters.me)
async def cmd_botlist(_, m: Message):
    bots = []
    async for member in app.get_chat_members(m.chat.id):
        if member.user.is_bot:
            uname = f" @{member.user.username}" if member.user.username else ""
            bots.append(
                f"• [{member.user.first_name}](tg://user?id={member.user.id}){uname}"
            )
    await m.reply(
        "**🤖 Bot List:**\n" + "\n".join(bots) if bots else "No bots found."
    )


# ─────────────────────────────────────────────
#  4. PROMOTE / DEMOTE
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("promote") & filters.group & filters.me)
@require_ub
async def cmd_promote(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    title = _args(m).strip() or "Admin"
    try:
        await ub.promote_chat_member(
            m.chat.id, target,
            privileges=ChatPrivileges(
                can_manage_chat=True,
                can_delete_messages=True,
                can_restrict_members=True,
                can_invite_users=True,
                can_pin_messages=True,
            ),
        )
        await ub.set_administrator_title(m.chat.id, target, title)
        await m.reply(f"⭐ Promoted `{target}` as **{title}**")
    except Exception as e:
        log.error(f"promote: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("demote") & filters.group & filters.me)
@require_ub
async def cmd_demote(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    try:
        await ub.promote_chat_member(
            m.chat.id, target,
            privileges=ChatPrivileges(),
        )
        await m.reply(f"🔻 Demoted `{target}`")
    except Exception as e:
        log.error(f"demote: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  5. PIN / UNPIN
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("pin") & filters.group & filters.me)
@require_ub
async def cmd_pin(_, m: Message, ub: Client):
    if not m.reply_to_message:
        return await m.reply("Reply to a message to pin.")
    loud = "loud" in _args(m).lower()
    try:
        await ub.pin_chat_message(
            m.chat.id, m.reply_to_message.id,
            disable_notification=not loud,
        )
        await m.reply("📌 Pinned!")
    except Exception as e:
        log.error(f"pin: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("unpin") & filters.group & filters.me)
@require_ub
async def cmd_unpin(_, m: Message, ub: Client):
    try:
        if m.reply_to_message:
            await ub.unpin_chat_message(m.chat.id, m.reply_to_message.id)
        else:
            await ub.unpin_all_chat_messages(m.chat.id)
        await m.reply("📌 Unpinned!")
    except Exception as e:
        log.error(f"unpin: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  6. REPORT @ADMIN
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("report") & filters.group & filters.me)
async def cmd_report(_, m: Message):
    if not m.reply_to_message:
        return await m.reply("Reply to the message you want to report.")
    pings = []
    async for member in app.get_chat_members(m.chat.id, filter="administrators"):
        if not member.user.is_bot:
            pings.append(f"[​](tg://user?id={member.user.id})")
    cid = str(m.chat.id).lstrip("-100")
    await m.reply(
        f"🚨 **Report by [{m.from_user.first_name}](tg://user?id={m.from_user.id})**"
        + "".join(pings)
        + f"\n[Jump to message](https://t.me/c/{cid}/{m.reply_to_message.id})"
    )


# ─────────────────────────────────────────────
#  7. PURGE
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("purge") & filters.group & filters.me)
@require_ub
async def cmd_purge(_, m: Message, ub: Client):
    if not m.reply_to_message:
        return await m.reply("Reply to the first message to purge from.")
    ids    = list(range(m.reply_to_message.id, m.id + 1))
    chunks = [ids[i:i+100] for i in range(0, len(ids), 100)]
    await asyncio.gather(
        *[ub.delete_messages(m.chat.id, chunk) for chunk in chunks],
        return_exceptions=True,
    )
    info = await app.send_message(m.chat.id, f"🗑️ Purged ~{len(ids)} messages.")
    await asyncio.sleep(3)
    try:
        await info.delete()
    except Exception:
        pass


# ─────────────────────────────────────────────
#  8. TAGALL / MENTION / ALL / UTAG / GMTAG / GNTAG / SETUSER
# ─────────────────────────────────────────────
async def _get_setuser(uid: int, chat_id: int) -> list:
    return await _get(uid, COL_SETUSER, str(chat_id)) or []


async def _set_setuser(uid: int, chat_id: int, lst: list):
    await _set(uid, COL_SETUSER, str(chat_id), lst)


@app.on_message(dot_cmd("setuser") & filters.group & filters.me)
async def cmd_setuser(_, m: Message):
    uid   = m.from_user.id
    users = []
    if m.reply_to_message and m.reply_to_message.from_user:
        users.append(m.reply_to_message.from_user.id)
    else:
        for chunk in _args(m).split():
            try:
                u = await app.get_users(chunk.lstrip("@"))
                users.append(u.id)
            except Exception as e:
                log.error(f"setuser resolve {chunk}: {e}")
    users = users[:5]
    if not users:
        return await m.reply("Provide up to 5 users or reply to one.")
    existing = await _get_setuser(uid, m.chat.id)
    combined = list(set(existing + users))
    await _set_setuser(uid, m.chat.id, combined)
    await m.reply(f"✅ Added {len(users)} user(s). Total in list: {len(combined)}")


async def _tag_members(m: Message, members: list, header: str = ""):
    for i in range(0, len(members), 5):
        batch = members[i:i+5]
        parts = []
        for u in batch:
            if isinstance(u, int):
                parts.append(f"[​](tg://user?id={u})")
            else:
                parts.append(
                    f"[{getattr(u,'first_name',str(u))}]"
                    f"(tg://user?id={getattr(u,'id',u)})"
                )
        text = (header if i == 0 else "") + " ".join(parts)
        try:
            await m.reply(text)
            await asyncio.sleep(0.5)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            log.error(f"_tag_members: {e}")


@app.on_message((dot_cmd("tagall") | dot_cmd("mention") | dot_cmd("all")) & filters.group & filters.me)
async def cmd_tagall(_, m: Message):
    header  = _args(m) or "👋 Attention everyone!"
    members = []
    async for mem in app.get_chat_members(m.chat.id):
        if not mem.user.is_bot:
            members.append(mem.user)
    await _tag_members(m, members, f"{header}\n")


@app.on_message(dot_cmd("utag") & filters.group & filters.me)
async def cmd_utag(_, m: Message):
    uid = m.from_user.id
    ids = await _get_setuser(uid, m.chat.id)
    if not ids:
        return await m.reply("No users set. Use `.setuser` first.")
    header = _args(m) or "👋"
    await _tag_members(m, ids, f"{header}\n")


_GM_MSGS = [
    "🌅 Good Morning everyone! Have a wonderful day!",
    "☀️ Rise and shine! Wishing you all a bright morning!",
    "🌞 Good Morning! May your day be as bright as the sun!",
]
_GN_MSGS = [
    "🌙 Good Night everyone! Rest well!",
    "⭐ Sweet dreams! Good Night!",
    "🌛 Good Night! Sleep tight!",
]


@app.on_message(dot_cmd("gmtag") & filters.group & filters.me)
async def cmd_gmtag(_, m: Message):
    members = []
    async for mem in app.get_chat_members(m.chat.id):
        if not mem.user.is_bot:
            members.append(mem.user)
    await _tag_members(m, members, random.choice(_GM_MSGS) + "\n")


@app.on_message(dot_cmd("gntag") & filters.group & filters.me)
async def cmd_gntag(_, m: Message):
    members = []
    async for mem in app.get_chat_members(m.chat.id):
        if not mem.user.is_bot:
            members.append(mem.user)
    await _tag_members(m, members, random.choice(_GN_MSGS) + "\n")


# ─────────────────────────────────────────────
#  9. AFK
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("afk") & filters.me)
async def cmd_afk(_, m: Message):
    uid    = m.from_user.id
    reason = _args(m) or "AFK"
    await _set(uid, COL_AFK, "status", {"reason": reason, "since": time.time()})
    await m.reply(f"🌙 AFK mode enabled\nReason: **{reason}**")


# ─────────────────────────────────────────────
#  10. BROADCAST
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("broadcast") & filters.me)
@require_ub
async def cmd_broadcast(_, m: Message, ub: Client):
    if not m.reply_to_message:
        return await m.reply("Reply to the message you want to broadcast.")
    flags      = _args(m).lower()
    do_pin     = "-pin"   in flags
    users_only = "-users" in flags
    loud       = "-loud"  in flags
    sent = failed = 0
    prog = await m.reply("📢 Broadcasting…")
    async for dialog in ub.get_dialogs():
        chat = dialog.chat
        if users_only and chat.type.value != "private":
            continue
        try:
            sent_msg = await m.reply_to_message.copy(chat.id)
            if do_pin:
                try:
                    await ub.pin_chat_message(
                        chat.id, sent_msg.id, disable_notification=not loud
                    )
                except Exception:
                    pass
            sent += 1
            await asyncio.sleep(0.3)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            log.error(f"broadcast to {chat.id}: {e}")
            failed += 1
    await prog.edit(f"📢 Done!\n✅ Sent: {sent}  ❌ Failed: {failed}")


# ─────────────────────────────────────────────
#  11. CARBON
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("carbon") & filters.me)
async def cmd_carbon(_, m: Message):
    code = _args(m)
    if not code and m.reply_to_message:
        code = m.reply_to_message.text or ""
    if not code:
        return await m.reply("Provide code or reply to a message.")
    try:
        r = await HTTP.post(
            "https://carbonara.solopov.dev/api/cook",
            json={"code": code},
        )
        r.raise_for_status()
        photo = io.BytesIO(r.content)
        photo.name = "carbon.png"
        await m.reply_photo(photo)
    except Exception as e:
        log.error(f"carbon: {e}")
        await m.reply(f"❌ Carbon failed: {e}")


# ─────────────────────────────────────────────
#  12. STICKER ID / KANG
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("stickerid") & filters.me)
async def cmd_stickerid(_, m: Message):
    if m.reply_to_message and m.reply_to_message.sticker:
        s = m.reply_to_message.sticker
        await m.reply(
            f"🗂 **Sticker ID:** `{s.file_id}`\n"
            f"📦 Pack: `{s.set_name or 'N/A'}`\n"
            f"🎞 Animated: `{s.is_animated}`\n"
            f"📹 Video: `{s.is_video}`"
        )
    else:
        await m.reply("Reply to a sticker.")


@app.on_message(dot_cmd("kang") & filters.group & filters.me)
@require_ub
async def cmd_kang(_, m: Message, ub: Client):
    if not m.reply_to_message:
        return await m.reply("Reply to a sticker or image.")
    msg  = m.reply_to_message
    uid  = m.from_user.id
    me   = await ub.get_me()
    safe = (me.username or str(me.id)).lower().replace("bot", "")
    pack_name  = f"ub_{uid}_by_{safe}"
    pack_title = f"@{BOT_USERNAME} Kanged"
    sticker_file = None
    is_animated  = False
    is_video     = False
    try:
        if msg.sticker:
            sticker_file = await ub.download_media(msg.sticker.file_id)
            is_animated  = msg.sticker.is_animated
            is_video     = msg.sticker.is_video
        elif msg.photo:
            sticker_file = await ub.download_media(msg.photo.file_id)
        elif msg.document and msg.document.mime_type == "image/webp":
            sticker_file = await ub.download_media(msg.document.file_id)
        else:
            return await m.reply("Reply to a sticker, photo, or .webp document.")
        emoji = _args(m).strip() or "🔥"
        import importlib
        stickers_mod = importlib.import_module("pyrogram.raw.functions.stickers")
        types_mod    = importlib.import_module("pyrogram.raw.types")
        peer         = await ub.resolve_peer(me.id)
        async def _input_doc():
            media = await ub.invoke(
                importlib.import_module(
                    "pyrogram.raw.functions.messages"
                ).UploadMedia(
                    peer=peer,
                    media=types_mod.InputMediaUploadedDocument(
                        file=await ub.save_file(sticker_file),
                        mime_type=(
                            "application/x-tgsticker" if is_animated
                            else "video/webm" if is_video
                            else "image/webp"
                        ),
                        attributes=[
                            types_mod.DocumentAttributeFilename(
                                file_name=(
                                    "sticker.tgs" if is_animated
                                    else "sticker.webm" if is_video
                                    else "sticker.webp"
                                )
                            )
                        ],
                    ),
                )
            )
            return types_mod.InputDocument(
                id=media.document.id,
                access_hash=media.document.access_hash,
                file_reference=media.document.file_reference,
            )
        sticker_item = types_mod.InputStickerSetItem(
            document=await _input_doc(),
            emoji=emoji,
        )
        try:
            await ub.invoke(
                stickers_mod.AddStickerToSet(
                    stickerset=types_mod.InputStickerSetShortName(short_name=pack_name),
                    sticker=sticker_item,
                )
            )
            await m.reply(f"✅ Added to pack!\nt.me/addstickers/{pack_name}")
        except Exception:
            await ub.invoke(
                stickers_mod.CreateStickerSet(
                    user_id=peer,
                    title=pack_title,
                    short_name=pack_name,
                    stickers=[sticker_item],
                    animated=is_animated,
                    videos=is_video,
                )
            )
            await m.reply(f"✅ Pack created!\nt.me/addstickers/{pack_name}")
    except Exception as e:
        log.error(f"kang: {e}")
        await m.reply(f"❌ Kang failed: {e}")
    finally:
        if sticker_file and os.path.exists(sticker_file):
            os.remove(sticker_file)


# ─────────────────────────────────────────────
#  13. SAVED (view-once retrieval command)
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("saved") & filters.me)
async def cmd_saved(_, m: Message):
    uid  = m.from_user.id
    keys = await _all_keys(uid, COL_SAVED)
    if not keys:
        return await m.reply("No saved media.")
    await m.reply(f"💾 {len(keys)} saved item(s):")
    for k in keys:
        path = await _get(uid, COL_SAVED, k)
        if path and os.path.exists(path):
            try:
                await m.reply_document(path)
            except Exception as e:
                log.error(f"saved send {k}: {e}")


# ─────────────────────────────────────────────
#  14. WHISPER
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("whisper") & filters.me)
async def cmd_whisper(_, m: Message):
    args  = _args(m)
    parts = args.split(None, 1)
    if len(parts) < 2:
        return await m.reply("Usage: `.whisper @username message`")
    target_raw, secret = parts[0], parts[1]
    try:
        target = await app.get_users(target_raw.lstrip("@"))
    except Exception as e:
        return await m.reply(f"❌ Cannot find user {target_raw}: {e}")
    uid = m.from_user.id
    wid = f"w{int(time.time())}_{uid}"
    await _set(uid, COL_WHISPER, wid, {
        "secret":   secret,
        "for_uid":  target.id,
        "from_uid": uid,
        "read":     False,
    })
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "👁 Read Whisper (1 time only)",
            callback_data=f"whisper_{uid}_{wid}",
        )
    ]])
    await app.send_message(
        target.id,
        f"🤫 **Whisper from [{m.from_user.first_name}](tg://user?id={uid})**\n"
        f"_(tap below to read — one time only)_",
        reply_markup=kb,
    )
    await m.reply(f"✅ Whisper sent to {target.first_name}.")


@app.on_callback_query(filters.regex(r"^whisper_(\d+)_(w\d+_\d+)$"))
async def _whisper_cb(_, cq):
    match     = re.match(r"^whisper_(\d+)_(w\d+_\d+)$", cq.data)
    owner_uid = int(match.group(1))
    wid       = match.group(2)
    data = await _get(owner_uid, COL_WHISPER, wid)
    if not data:
        return await cq.answer("❌ Whisper expired or not found.", show_alert=True)
    if cq.from_user.id != data["for_uid"]:
        return await cq.answer("❌ This whisper is not for you.", show_alert=True)
    if data.get("read"):
        return await cq.answer("👁 Already read.", show_alert=True)
    data["read"] = True
    await _set(owner_uid, COL_WHISPER, wid, data)
    await cq.answer(f"🤫 {data['secret']}", show_alert=True)
    await _del(owner_uid, COL_WHISPER, wid)


# ─────────────────────────────────────────────
#  15. EVAL (owner only)
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("eval") & filters.me)
async def cmd_eval(_, m: Message):
    if not await _is_main_owner(m.from_user.id):
        return await m.reply("❌ Owner only.")
    code = _args(m)
    if not code:
        return await m.reply("Provide code to eval.")
    result = None
    try:
        exec_globals = {
            "app": app, "m": m, "asyncio": asyncio,
            "_db": _db, "_get": _get, "_set": _set,
        }
        exec(
            "async def __ev():\n" + textwrap.indent(code, "    "),
            exec_globals,
        )
        result = await exec_globals["__ev"]()
    except Exception:
        result = traceback.format_exc()
    await m.reply(
        f"**Input:**\n```\n{code}\n```\n\n**Output:**\n```\n{result}\n```"
    )


# ─────────────────────────────────────────────
#  16. JOIN / LEAVE / START / END VC
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("joinvc") & filters.group & filters.me)
@require_ub
async def cmd_joinvc(_, m: Message, ub: Client):
    try:
        from pytgcalls import PyTgCalls
        from pytgcalls.types.input_stream import AudioPiped
        ptc = PyTgCalls(ub)
        await ptc.start()
        await ptc.join_group_call(m.chat.id, AudioPiped("silence.mp3"))
        await m.reply("🎙 Joined VC")
    except ImportError:
        await m.reply("❌ `pytgcalls` not installed.")
    except Exception as e:
        log.error(f"joinvc: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("leavevc") & filters.group & filters.me)
@require_ub
async def cmd_leavevc(_, m: Message, ub: Client):
    try:
        from pytgcalls import PyTgCalls
        ptc = PyTgCalls(ub)
        await ptc.start()
        await ptc.leave_group_call(m.chat.id)
        await m.reply("👋 Left VC")
    except ImportError:
        await m.reply("❌ `pytgcalls` not installed.")
    except Exception as e:
        log.error(f"leavevc: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("startvc") & filters.group & filters.me)
@require_ub
async def cmd_startvc(_, m: Message, ub: Client):
    try:
        await ub.send_message(m.chat.id, "🎙 Starting VC via userbot…")
        await m.reply("✅ VC start initiated.")
    except Exception as e:
        log.error(f"startvc: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("endvc") & filters.group & filters.me)
@require_ub
async def cmd_endvc(_, m: Message, ub: Client):
    try:
        import importlib
        DiscardGroupCall = importlib.import_module(
            "pyrogram.raw.functions.phone"
        ).DiscardGroupCall
        await ub.invoke(DiscardGroupCall(call=m.chat.id))
        await m.reply("⛔ VC ended.")
    except Exception as e:
        log.error(f"endvc: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  17. LOCK / UNLOCK
# ─────────────────────────────────────────────
_LOCK_PERMS = {
    "sticker":  ChatPermissions(can_send_other_messages=False),
    "media":    ChatPermissions(can_send_media_messages=False),
    "video":    ChatPermissions(can_send_media_messages=False),
    "files":    ChatPermissions(can_send_media_messages=False),
    "messages": ChatPermissions(can_send_messages=False),
    "all":      ChatPermissions(),
}


@app.on_message(dot_cmd("lock") & filters.group & filters.me)
@require_ub
async def cmd_lock(_, m: Message, ub: Client):
    lock_type = _args(m).lower().strip()
    if lock_type not in _LOCK_PERMS:
        return await m.reply(
            "Usage: `.lock <type>`\nTypes: " + ", ".join(_LOCK_PERMS.keys())
        )
    try:
        await ub.set_chat_permissions(m.chat.id, _LOCK_PERMS[lock_type])
        await m.reply(f"🔒 Locked: **{lock_type}**")
    except Exception as e:
        log.error(f"lock: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("unlock") & filters.group & filters.me)
@require_ub
async def cmd_unlock(_, m: Message, ub: Client):
    try:
        await ub.set_chat_permissions(
            m.chat.id,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_invite_users=True,
            ),
        )
        await m.reply("🔓 All permissions unlocked.")
    except Exception as e:
        log.error(f"unlock: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  18. PING
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("ping") & filters.me)
async def cmd_ping(_, m: Message):
    t0  = time.time()
    msg = await m.reply("🏓 Pinging…")
    t1  = time.time()
    await msg.edit(f"🏓 Pong! `{round((t1-t0)*1000, 2)} ms`")


# ─────────────────────────────────────────────
#  19. SETBIO / MYBIO / SETMYBIO
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("setbio") & filters.me)
@require_ub
async def cmd_setbio(_, m: Message, ub: Client):
    bio = _args(m)
    if not bio:
        return await m.reply("Usage: `.setbio <new bio>`")
    try:
        await ub.update_profile(bio=bio)
        await m.reply("✅ Bio updated.")
    except Exception as e:
        log.error(f"setbio: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("mybio") & filters.me)
async def cmd_mybio(_, m: Message):
    uid = m.from_user.id
    bio = await _get(uid, COL_CFG, "bio_note")
    await m.reply(f"📝 Saved bio note:\n{bio}" if bio else "No bio note. Use `.setmybio`")


@app.on_message(dot_cmd("setmybio") & filters.me)
async def cmd_setmybio(_, m: Message):
    uid  = m.from_user.id
    text = _args(m)
    if m.reply_to_message and m.reply_to_message.from_user:
        target = m.reply_to_message.from_user.id
        await _set(uid, COL_CFG, f"bio_note_{target}", text)
        await m.reply(f"✅ Bio note saved for `{target}`")
    else:
        await _set(uid, COL_CFG, "bio_note", text)
        await m.reply("✅ Bio note saved.")


# ─────────────────────────────────────────────
#  20. SANGMATA (SG)
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("sg") & filters.me)
async def cmd_sg(_, m: Message):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    try:
        await app.send_message("@SangMata_BOT", f"/getinfo {target}")
        await asyncio.sleep(3)
        async for msg in app.get_chat_history("@SangMata_BOT", limit=5):
            if msg.text and str(target) in (msg.text or ""):
                return await m.reply(msg.text)
        await m.reply("No data from SangMata for that user.")
    except Exception as e:
        log.error(f"sg: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  21. LOGGERID
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("loggerid") & filters.me)
async def cmd_loggerid(_, m: Message):
    uid = m.from_user.id
    await _set(uid, COL_CFG, "logger", m.chat.id)
    await m.reply(f"✅ Log group set to `{m.chat.id}`")


# ─────────────────────────────────────────────
#  22. TAGALERT
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("tagalert") & filters.me)
async def cmd_tagalert(_, m: Message):
    uid   = m.from_user.id
    state = _args(m).lower()
    if state not in ("on", "off"):
        return await m.reply("Usage: `.tagalert on/off`")
    await _set(uid, COL_CFG, "tagalert", state == "on")
    await m.reply(f"🔔 Tag alert **{'enabled' if state=='on' else 'disabled'}**.")


# ─────────────────────────────────────────────
#  23. TGT / IMBP / TGM
# ─────────────────────────────────────────────
async def _upload_telegra_ph(path: str) -> str:
    with open(path, "rb") as f:
        r = await HTTP.post(
            "https://telegra.ph/upload",
            files={"file": ("image.jpg", f, "image/jpeg")},
        )
    return "https://telegra.ph" + r.json()[0]["src"]


async def _upload_imgbb(path: str) -> str:
    import base64
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    r = await HTTP.post(
        "https://api.imgbb.com/1/upload",
        data={"key": "free", "image": b64},
    )
    return r.json().get("data", {}).get("url", "Failed")


async def _upload_catbox(path: str) -> str:
    with open(path, "rb") as f:
        r = await HTTP.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
        )
    return r.text.strip()


async def _img_upload_handler(m: Message, uploader):
    if not m.reply_to_message or not m.reply_to_message.photo:
        return await m.reply("Reply to a photo.")
    path = await app.download_media(m.reply_to_message.photo)
    try:
        url = await uploader(path)
        await m.reply(f"🔗 {url}")
    except Exception as e:
        log.error(f"img_upload: {e}")
        await m.reply(f"❌ {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)


@app.on_message(dot_cmd("tgt") & filters.me)
async def cmd_tgt(_, m: Message):
    await _img_upload_handler(m, _upload_telegra_ph)


@app.on_message(dot_cmd("imbp") & filters.me)
async def cmd_imbp(_, m: Message):
    await _img_upload_handler(m, _upload_imgbb)


@app.on_message(dot_cmd("tgm") & filters.me)
async def cmd_tgm(_, m: Message):
    await _img_upload_handler(m, _upload_catbox)


# ─────────────────────────────────────────────
#  24. TR — TRANSLATE
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("tr") & filters.me)
async def cmd_tr(_, m: Message):
    text = _args(m)
    if not text and m.reply_to_message:
        text = m.reply_to_message.text or m.reply_to_message.caption or ""
    if not text:
        return await m.reply("Provide text or reply to a message.")
    dest  = "en"
    parts = text.split(None, 1)
    if len(parts) == 2 and len(parts[0]) <= 3 and parts[0].isalpha():
        dest, text = parts[0], parts[1]
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source="auto", target=dest).translate(text)
        await m.reply(f"🌐 **Translation → {dest}:**\n{translated}")
    except ImportError:
        await m.reply("❌ Install `deep-translator`: `pip install deep-translator`")
    except Exception as e:
        log.error(f"tr: {e}")
        await m.reply(f"❌ {e}")


# ─────────────────────────────────────────────
#  25. PMGUARD COMMANDS
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("pmguard") & filters.me)
async def cmd_pmguard(_, m: Message):
    uid   = m.from_user.id
    state = _args(m).lower()
    if state not in ("on", "off"):
        return await m.reply("Usage: `.pmguard on/off`")
    cur = await _get(uid, COL_PMGUARD, "status") or {}
    cur["on"] = (state == "on")
    await _set(uid, COL_PMGUARD, "status", cur)
    await m.reply(f"🛡 PMGuard **{'ON' if state=='on' else 'OFF'}**")


@app.on_message(dot_cmd("setwarn") & filters.me)
async def cmd_setwarn(_, m: Message):
    uid = m.from_user.id
    try:
        limit = int(_args(m))
    except Exception:
        return await m.reply("Usage: `.setwarn <number>`")
    await _set(uid, COL_PMGUARD, "limit", limit)
    await m.reply(f"✅ PM warn limit set to {limit}")


@app.on_message(dot_cmd("resetwarn") & filters.me)
async def cmd_resetwarn(_, m: Message):
    uid = m.from_user.id
    await _set(uid, COL_PMGUARD, "limit", 3)
    await m.reply("✅ PM warn limit reset to 3")


@app.on_message(dot_cmd("setpmmsg") & filters.me)
async def cmd_setpmmsg(_, m: Message):
    uid = m.from_user.id
    msg = _args(m)
    if not msg:
        return await m.reply("Usage: `.setpmmsg <message>`")
    await _set(uid, COL_PMGUARD, "msg", msg)
    await m.reply("✅ PM warn message updated.")


@app.on_message(dot_cmd("resetpmmsg") & filters.me)
async def cmd_resetpmmsg(_, m: Message):
    uid = m.from_user.id
    await _del(uid, COL_PMGUARD, "msg")
    await m.reply("✅ PM warn message reset to default.")


@app.on_message(dot_cmd("setpmimg") & filters.me)
async def cmd_setpmimg(_, m: Message):
    uid = m.from_user.id
    if m.reply_to_message and m.reply_to_message.photo:
        await _set(uid, COL_PMGUARD, "img", m.reply_to_message.photo.file_id)
        await m.reply("✅ PM warn image set.")
    else:
        await m.reply("Reply to an image.")


@app.on_message(dot_cmd("resetpmimg") & filters.me)
async def cmd_resetpmimg(_, m: Message):
    uid = m.from_user.id
    await _del(uid, COL_PMGUARD, "img")
    await m.reply("✅ PM warn image removed.")


@app.on_message(dot_cmd("block") & filters.me)
@require_ub
async def cmd_block(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    try:
        await ub.block_user(target)
        await m.reply(f"🚫 Blocked `{target}`")
    except Exception as e:
        log.error(f"block: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("unblock") & filters.me)
@require_ub
async def cmd_unblock(_, m: Message, ub: Client):
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    try:
        await ub.unblock_user(target)
        await m.reply(f"✅ Unblocked `{target}`")
    except Exception as e:
        log.error(f"unblock: {e}")
        await m.reply(f"❌ {e}")


@app.on_message(dot_cmd("clrwarns") & filters.me)
async def cmd_clrwarns(_, m: Message):
    uid    = m.from_user.id
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user.")
    await _del(uid, COL_PMGUARD, f"warn_{target}")
    await m.reply(f"✅ PM warns cleared for `{target}`")


@app.on_message(dot_cmd("a") & filters.me)
async def cmd_approve(_, m: Message):
    uid    = m.from_user.id
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    await _set(uid, COL_PMGUARD, f"approved_{target}", True)
    await m.reply(f"✅ Approved `{target}` — PMGuard will skip them.")


@app.on_message(dot_cmd("da") & filters.me)
async def cmd_disapprove(_, m: Message):
    uid    = m.from_user.id
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user or provide ID.")
    await _del(uid, COL_PMGUARD, f"approved_{target}")
    await m.reply(f"✅ Disapproved `{target}` — PMGuard active again.")


# ─────────────────────────────────────────────
#  26. RAID
# ─────────────────────────────────────────────
_RAID_DEFAULTS = [
    "🤖 Raid engaged!", "💥 Got you!", "👀 Stop spamming!",
    "🔥 You've been noticed!", "😈 Watching you.", "⚡ Raid!",
]


@app.on_message(dot_cmd("raid") & filters.me)
@require_ub
async def cmd_raid(_, m: Message, ub: Client):
    uid    = m.from_user.id
    target = await _get_target(m)
    if not target:
        return await m.reply("Reply to a user, mention, or provide user ID.")
    custom = _args(m).split()
    if custom and (custom[0].startswith("@") or custom[0].isdigit()):
        custom = custom[1:]
    replies = custom if custom else _RAID_DEFAULTS
    await _set(uid, COL_RAID, "active", {"target": target, "replies": replies})
    await _set(uid, COL_RAID, "last_reply", 0)
    await m.reply(
        f"🚨 Raid started on `{target}`!\n"
        "Reply cooldown: 5s.\nUse `.stopraid` to stop."
    )


@app.on_message(dot_cmd("stopraid") & filters.me)
async def cmd_stopraid(_, m: Message):
    uid = m.from_user.id
    await _del(uid, COL_RAID, "active")
    await _del(uid, COL_RAID, "last_reply")
    await m.reply("✅ Raid stopped.")


# ─────────────────────────────────────────────
#  ALIVE — system stats
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("alive") & filters.me)
async def cmd_alive(_, m: Message):
    uid      = m.from_user.id
    ub       = _active_userbots.get(uid)
    status   = "✅ Connected" if ub and ub.is_connected else "❌ Not connected"
    up_secs  = int(time.time() - _BOT_START)
    h, r     = divmod(up_secs, 3600)
    mn, s    = divmod(r, 60)
    try:
        cpu      = psutil.cpu_percent(interval=0.3)
        ram      = psutil.virtual_memory()
        ram_info = (
            f"{ram.used/1024**2:.1f} MB / "
            f"{ram.total/1024**2:.1f} MB ({ram.percent}%)"
        )
    except Exception:
        cpu = "N/A"
        ram_info = "N/A"
    await m.reply(
        f"🤖 **SHASHA Userbot — Alive!**\n\n"
        f"⏱ Uptime    : `{h}h {mn}m {s}s`\n"
        f"💻 CPU       : `{cpu}%`\n"
        f"🧠 RAM       : `{ram_info}`\n"
        f"🐍 Python    : `{platform.python_version()}`\n"
        f"📡 Userbot   : {status}\n"
        f"👥 Active UBs: `{len(_active_userbots)}`"
    )


# ─────────────────────────────────────────────
#  AUTOREPLY
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("setreply") & filters.me)
async def cmd_setreply(_, m: Message):
    uid  = m.from_user.id
    args = _args(m)
    if "|" not in args:
        return await m.reply("Usage: `.setreply keyword | reply text`")
    kw, reply_text = [p.strip() for p in args.split("|", 1)]
    if not kw or not reply_text:
        return await m.reply("Both keyword and reply text are required.")
    await _set(uid, COL_AUTOREPLY, kw.lower(), reply_text)
    await m.reply(f"✅ Auto-reply set for keyword: `{kw}`")


@app.on_message(dot_cmd("delreply") & filters.me)
async def cmd_delreply(_, m: Message):
    uid = m.from_user.id
    kw  = _args(m).lower().strip()
    if not kw:
        return await m.reply("Usage: `.delreply keyword`")
    await _del(uid, COL_AUTOREPLY, kw)
    await m.reply(f"✅ Removed auto-reply for `{kw}`")


@app.on_message(dot_cmd("listreplies") & filters.me)
async def cmd_listreplies(_, m: Message):
    uid  = m.from_user.id
    keys = await _all_keys(uid, COL_AUTOREPLY)
    if not keys:
        return await m.reply("No auto-replies set.")
    lines = []
    for k in keys:
        v = await _get(uid, COL_AUTOREPLY, k)
        lines.append(f"• `{k}` → {v}")
    await m.reply("**🔁 Auto-Replies:**\n" + "\n".join(lines))


# ─────────────────────────────────────────────
#  ANTIFLOOD
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("antiflood") & filters.group & filters.me)
async def cmd_antiflood(_, m: Message):
    uid  = m.from_user.id
    args = _args(m).split()
    state = args[0].lower() if args else ""
    if state not in ("on", "off"):
        return await m.reply(
            "Usage: `.antiflood on [limit] [window_secs]` or `.antiflood off`"
        )
    if state == "off":
        await _del(uid, COL_FLOOD, f"cfg_{m.chat.id}")
        return await m.reply("✅ Antiflood disabled for this chat.")
    limit  = int(args[1]) if len(args) > 1 else 5
    window = int(args[2]) if len(args) > 2 else 10
    await _set(uid, COL_FLOOD, f"cfg_{m.chat.id}", {
        "on": True, "limit": limit, "window": window,
    })
    await m.reply(
        f"✅ Antiflood enabled.\n"
        f"Trigger: `{limit}` msgs in `{window}s` → mute 60s"
    )


# ─────────────────────────────────────────────
#  AUTOPIC
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("autopic") & filters.me)
@require_ub
async def cmd_autopic(_, m: Message, ub: Client):
    action = _args(m).lower().strip()
    if action == "clear":
        try:
            photos = await ub.get_profile_photos("me", limit=1)
            if photos:
                await ub.delete_profile_photos([p.file_id for p in photos])
                await m.reply("✅ Profile photo removed.")
            else:
                await m.reply("No profile photo to remove.")
        except Exception as e:
            log.error(f"autopic clear: {e}")
            await m.reply(f"❌ {e}")
        return
    if action == "set" and m.reply_to_message and m.reply_to_message.photo:
        path = await app.download_media(m.reply_to_message.photo)
        try:
            await ub.set_profile_photo(photo=path)
            await m.reply("✅ Profile photo updated!")
        except Exception as e:
            log.error(f"autopic set: {e}")
            await m.reply(f"❌ {e}")
        finally:
            if os.path.exists(path):
                os.remove(path)
    else:
        await m.reply(
            "Usage:\n"
            "`.autopic set` _(reply to a photo)_\n"
            "`.autopic clear` _(remove profile photo)_"
        )


# ─────────────────────────────────────────────
#  27. MYSTART / MYHELP
# ─────────────────────────────────────────────
@app.on_message(dot_cmd("mystart") & filters.me)
async def cmd_mystart(_, m: Message):
    uid    = m.from_user.id
    ub     = _active_userbots.get(uid)
    status = "✅ Connected" if ub and ub.is_connected else "❌ Not connected"
    is_mo  = await _is_main_owner(uid)
    await m.reply(
        f"👋 **SHASHA Userbot**\n\n"
        f"**Status       :** {status}\n"
        f"**Your ID      :** `{uid}`\n"
        f"**Main Owner   :** {'Yes ✅' if is_mo else 'No'}\n"
        f"**Active UBs   :** `{len(_active_userbots)}`\n"
        f"**Cmd prefix   :** `.` (dot)\n\n"
        f"Use `.myhelp` for full command list.\n"
        f"Use `.alive` for system stats."
    )


@app.on_message(dot_cmd("myhelp") & filters.me)
async def cmd_myhelp(_, m: Message):
    help_text = (
        "**🤖 SHASHA USERBOT — COMMAND LIST**\n\n"
        "**🔑 Session**\n"
        "`/usersession` — Connect userbot session\n"
        "`/rmuserbot` — Remove your userbot\n"
        "`/rmuserbot <id>` — Remove a user's bot _(owner only)_\n"
        "`/rmalluserbots` — Wipe all userbots _(owner only)_\n\n"
        "**🛡️ Moderation** _(group)_\n"
        "`.ban` `.unban` `.tban [10m/1h/1d]` `.sban` `.kick`\n"
        "`.warn [reason]` `.unwarn`\n"
        "`.mute [10m/1h/1d]` `.unmute`\n"
        "`.promote [title]` `.demote`\n"
        "`.pin [loud]` `.unpin`\n"
        "`.lock <type>` `.unlock`\n"
        "`.purge` _(reply to start msg)_\n"
        "`.report` _(pings all admins)_\n\n"
        "**👥 Tagging** _(group)_\n"
        "`.tagall` `.mention` `.all`\n"
        "`.utag` — tag setuser list\n"
        "`.gmtag` / `.gntag` — good morning/night tag\n"
        "`.setuser @u1 @u2...` — build tag list _(max 5)_\n\n"
        "**💬 Messaging**\n"
        "`.afk [reason]` — go AFK\n"
        "`.broadcast [-pin -users -loud]` _(reply to msg)_\n"
        "`.whisper @user message` — one-time read msg\n\n"
        "**🖼 Media / Tools**\n"
        "`.carbon [code]` — code screenshot\n"
        "`.stickerid` — get sticker file ID\n"
        "`.kang [emoji]` — add sticker to your pack\n"
        "`.saved` — retrieve saved view-once media\n"
        "`.tgt` / `.imbp` / `.tgm` — image → link\n"
        "`.tr [lang] text` — translate _(default EN)_\n"
        "`.autopic set/clear` — manage profile photo\n\n"
        "**📋 Info**\n"
        "`.id` `.info` `.adminlist` `.botlist`\n"
        "`.ping` `.alive` `.loggerid` `.sg`\n\n"
        "**🔔 Alerts / VC**\n"
        "`.tagalert on/off`\n"
        "`.joinvc` `.leavevc` `.startvc` `.endvc`\n\n"
        "**🛡 PMGuard**\n"
        "`.pmguard on/off`\n"
        "`.setwarn <n>` `.resetwarn`\n"
        "`.setpmmsg` `.resetpmmsg`\n"
        "`.setpmimg` `.resetpmimg`\n"
        "`.block` `.unblock`\n"
        "`.clrwarns` `.a` _(approve)_ `.da` _(disapprove)_\n\n"
        "**🔁 Auto-Reply** _(userbot)_\n"
        "`.setreply keyword | reply`\n"
        "`.delreply keyword`\n"
        "`.listreplies`\n\n"
        "**🛑 Antiflood** _(group)_\n"
        "`.antiflood on [limit] [window]`\n"
        "`.antiflood off`\n\n"
        "**⚔️ Raid**\n"
        "`.raid` _(reply/mention/id)_ — 5s cooldown\n"
        "`.stopraid`\n\n"
        "**👤 Bio**\n"
        "`.setbio <bio>` `.mybio` `.setmybio [reply]`\n\n"
        "**⚙️ Dev** _(owner only)_\n"
        "`.eval <code>`\n\n"
        "`.mystart` — status  |  `.myhelp` — this menu"
    )
    await m.reply(help_text)



# ─────────────────────────────────────────────
#  MODULE META
# ─────────────────────────────────────────────
__menu__     = "CMD_PRO"
__mod_name__ = "H_B_80"
__help__     = """
🔻 /usersession ➠ ᴄᴏɴɴᴇᴄᴛꜱ ʏᴏᴜʀ ᴜꜱᴇʀʙᴏᴛ ꜱᴇꜱꜱɪᴏɴ (ʀᴇᴘʟʏ ᴏʀ ꜱᴇɴᴅ ꜱᴇꜱꜱɪᴏɴ ꜱᴛʀɪɴɢ).
🔻 /rmuserbot ➠ ʀᴇᴍᴏᴠᴇꜱ ʏᴏᴜʀ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴜꜱᴇʀʙᴏᴛ ᴀɴᴅ ᴄʟᴇᴀʀꜱ ᴅᴀᴛᴀ.
🔻 /rmuserbot <id> ➠ ʀᴇᴍᴏᴠᴇꜱ ꜱᴘᴇᴄɪꜰɪᴄ ᴜꜱᴇʀʙᴏᴛ (ᴍᴀɪɴ ᴏᴡɴᴇʀ ᴏɴʟʏ).
🔻 /rmalluserbots ➠ ʀᴇᴍᴏᴠᴇꜱ ᴀʟʟ ᴜꜱᴇʀʙᴏᴛꜱ ᴀɴᴅ ᴡɪᴘᴇꜱ ᴀʟʟ ᴜꜱᴇʀ ᴅᴀᴛᴀ (ᴍᴀɪɴ ᴏᴡɴᴇʀ).
━━━━━━━━━━━━━━━━━━━━
🔻 .mystart ➠ ꜱʜᴏᴡꜱ ᴜꜱᴇʀʙᴏᴛ ꜱᴛᴀᴛᴜꜱ ᴀɴᴅ ᴄᴏɴɴᴇᴄᴛɪᴏɴ ɪɴꜰᴏ.
🔻 .myhelp ➠ ᴏᴘᴇɴꜱ ᴄᴏᴍᴘʟᴇᴛᴇ ᴜꜱᴇʀʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅ ʜᴇʟᴘ ᴍᴇɴᴜ.
"""

# ─────────────────────────────────────────────
#  END OF MODULE
# ─────────────────────────────────────────────
