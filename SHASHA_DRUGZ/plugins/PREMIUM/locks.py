# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SHASHA_DRUGZ — Locks + Approval + CleanService + AntiFlood              ║
# ║  MERGED SINGLE FILE — No external imports needed                         ║
# ║                                                                           ║
# ║  RULES:                                                                   ║
# ║  • Approved user / Admin / SUDOER           → exempt from locks & flood  ║
# ║  • Unapproved user, lock matches msg type   → delete that message only   ║
# ║  • Unapproved user, lock does NOT match     → NEVER deleted              ║
# ║  • Normal messages (no lock active)         → NEVER deleted              ║
# ║  • Approval ON/OFF                          → zero effect on deletion    ║
# ║  • Flood ON + limit exceeded + NOT exempt   → delete + mute 60s         ║
# ║  • Commands (/)                             → NEVER deleted              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
import re
import time
import unicodedata
from typing import List
from collections import defaultdict
from pyrogram import filters, enums
from pyrogram.types import (
    Message,
    ChatPermissions,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.enums import ChatMemberStatus
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import MONGO_DB_URI, BANNED_USERS
from motor.motor_asyncio import AsyncIOMotorClient

# ─── MongoDB ──────────────────────────────────────────────────────────────────
mongo        = AsyncIOMotorClient(MONGO_DB_URI)
_db          = mongo["SHASHA_DRUGZ"]
locks_col    = _db["CHAT_LOCKS"]
approval_col = _db["approval"]
settings_col = _db["settings"]
flood_col    = _db["flood"]

# ─── In-memory flood tracker ──────────────────────────────────────────────────
_flood_cache: dict[tuple, list] = defaultdict(list)

# ─── Lock types ───────────────────────────────────────────────────────────────
LOCK_TYPES = [
    "all", "album", "anonchannel", "audio", "bot", "botlink", "button",
    "cashtags", "checklist", "cjk", "command", "comment", "contact", "cyrillic",
    "document", "email", "emoji", "emojicustom", "emojigame", "emojionly",
    "externalreply", "forward", "forwardbot", "forwardchannel", "forwardstory",
    "forwarduser", "game", "gif", "inline", "invitelink", "location", "phone",
    "photo", "poll", "rtl", "spoiler", "sticker", "stickeranimated", "stickerpremium",
    "text", "url", "video", "videonote", "voice", "zalgo"
]

# ═════════════════════════════════════════════════════════════════════════════
# CORE HELPERS
# ═════════════════════════════════════════════════════════════════════════════
async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    """True if SUDOER, group admin, or owner."""
    if user_id in SUDOERS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

async def _is_approved(chat_id: int, user_id: int) -> bool:
    """True if user was /approved in this chat."""
    doc = await approval_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc is not None

async def _is_cleanservice_on(chat_id: int) -> bool:
    """True ONLY when cleanservice is stored as boolean True in DB."""
    data = await settings_col.find_one({"chat_id": chat_id})
    if data is None:
        return False
    return data.get("cleanservice") is True

async def _get_flood_settings(chat_id: int) -> tuple:
    """Returns (limit: int|None, enabled: bool)."""
    data = await flood_col.find_one({"chat_id": chat_id})
    if data:
        return data.get("limit"), (data.get("enabled") is True)
    return None, False

async def is_admin_or_sudo(client, chat_id: int, user_id: int) -> bool:
    """
    Exemption for LOCKS and FLOOD:
    Exempt = SUDOER OR admin/owner OR approved user.
    Approved users are fully whitelisted — locks + flood do NOT apply to them.
    """
    if user_id in SUDOERS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        if m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except Exception:
        pass
    return await _is_approved(chat_id, user_id)

# Alias used by flood_checker
is_exempt = is_admin_or_sudo

# ═════════════════════════════════════════════════════════════════════════════
# LOCKS — DB HELPERS
# ═════════════════════════════════════════════════════════════════════════════
async def get_locks(chat_id: int) -> List[str]:
    row = await locks_col.find_one({"chat_id": chat_id})
    if not row:
        return []
    return row.get("locks", [])

async def update_locks(chat_id: int, locks: List[str]):
    await locks_col.update_one(
        {"chat_id": chat_id}, {"$set": {"locks": locks}}, upsert=True
    )

# ═════════════════════════════════════════════════════════════════════════════
# LOCKS — KEYBOARD UI
# ═════════════════════════════════════════════════════════════════════════════
def locks_keyboard(active: List[str]) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, lt in enumerate(LOCK_TYPES, 1):
        icon = "–" if lt in active else "+"
        row.append(InlineKeyboardButton(f"{icon} {lt}", callback_data=f"toggle::{lt}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⌯ Close ⌯", callback_data="locks::close")])
    return InlineKeyboardMarkup(rows)

# ═════════════════════════════════════════════════════════════════════════════
# LOCKS — COMMANDS
# ═════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("locktypes") & filters.group & ~BANNED_USERS)
async def open_lock_panel(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("Admins only.")
    locks = await get_locks(message.chat.id)
    await message.reply_text(
        "<blockquote>🔐 Available Locks</blockquote>",
        reply_markup=locks_keyboard(locks),
    )

@app.on_message(filters.command("locks") & filters.group & ~BANNED_USERS)
async def show_locks(client, message: Message):
    locks = await get_locks(message.chat.id)
    if not locks:
        return await message.reply_text("No active locks in this chat.")
    await message.reply_text("Active locks:\n" + "\n".join(f"🔒 {x}" for x in locks))

# ═════════════════════════════════════════════════════════════════════════════
# LOCKS — CALLBACKS
# ═════════════════════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^toggle::"))
async def toggle_callback(client, query: CallbackQuery):
    if not await _is_admin(client, query.message.chat.id, query.from_user.id):
        return await query.answer("Admins only.", show_alert=True)
    _, lock_type = query.data.split("::", 1)
    locks = await get_locks(query.message.chat.id)
    if lock_type in locks:
        locks.remove(lock_type)
        await update_locks(query.message.chat.id, locks)
        await query.answer(f"🍏 Unlocked: {lock_type}", show_alert=True)
    else:
        locks.append(lock_type)
        await update_locks(query.message.chat.id, locks)
        await query.answer(f"🍎 Locked: {lock_type}", show_alert=True)
    try:
        await query.message.edit_text(
            "<blockquote>🔐 Available Locks</blockquote>",
            reply_markup=locks_keyboard(locks),
        )
    except Exception:
        pass

@app.on_callback_query(filters.regex(r"^locks::close$"))
async def close_callback(_, query: CallbackQuery):
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer()

# ═════════════════════════════════════════════════════════════════════════════
# LOCKS — DETECTION UTILITIES
# ═════════════════════════════════════════════════════════════════════════════
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+"
)

def _has_emoji(t: str) -> bool:
    return bool(EMOJI_RE.search(t or ""))

def _only_emoji(t: str) -> bool:
    if not t:
        return False
    s = re.sub(r"[\s\U0000FE0F\U0000200D]", "", t)
    return bool(s) and all(EMOJI_RE.fullmatch(ch) for ch in s)

def _has_cjk(t: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", t or ""))

def _has_cyrillic(t: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", t or ""))

def _has_rtl(t: str) -> bool:
    return bool(re.search(r"[\u0590-\u06FF]", t or ""))

def _has_email(t: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t or ""))

def _has_url(t: str) -> bool:
    return bool(re.search(r"(https?://|www\.)", t or ""))

def _has_phone(t: str) -> bool:
    return bool(re.search(r"\+?\d[\d\-\s]{6,}\d", t or ""))

def _has_cashtag(t: str) -> bool:
    return bool(re.search(r"[\$₹€£¥]", t or ""))

def _has_checklist(t: str) -> bool:
    return bool(re.search(r"[☐☑✔️\u2705\U0001F5F8]", t or ""))

def _is_zalgo(t: str) -> bool:
    if not t:
        return False
    combining = sum(1 for ch in t if unicodedata.category(ch) == "Mn")
    total = len(t)
    return combining > 10 or (total > 0 and combining / total > 0.30)

def _has_invite(t: str) -> bool:
    return bool(re.search(
        r"(t\.me\/joinchat|t\.me\/\+|t\.me\/|telegram\.me\/|joinchat|invite\.link|telegram\.dog\/)",
        t or "", re.IGNORECASE,
    ))

def _has_botlink(t: str) -> bool:
    return bool(re.search(r"@\w*bot\b", t or "", re.IGNORECASE))

def _detect_types(message: Message) -> List[str]:
    """
    Returns ALL matching lock-type strings for this message.

    ┌─────────────────────────────────────────────────────────────┐
    │  WHY a list instead of a single string?                     │
    │  A sticker that is also animated matches BOTH "sticker"     │
    │  and "stickeranimated". Returning a list lets the enforcer  │
    │  delete if ANY of the active locks appear in the list —     │
    │  so locking "sticker" catches all stickers, while locking   │
    │  "stickeranimated" only catches animated ones.              │
    └─────────────────────────────────────────────────────────────┘
    """
    types: List[str] = []

    # ── album ──────────────────────────────────────────────────────────────
    if message.media_group_id:
        types.append("album")

    # ── anonchannel ────────────────────────────────────────────────────────
    if message.sender_chat and getattr(message.sender_chat, "type", "") == "channel":
        types.append("anonchannel")
        return types  # channel post — nothing else applies

    # ── new chat members ───────────────────────────────────────────────────
    if message.new_chat_members:
        for m in message.new_chat_members:
            if m.is_bot:
                types.append("bot")
        if not types:
            types.append("text")
        return types

    # ── media types ────────────────────────────────────────────────────────
    if message.audio:
        types.append("audio")

    if message.voice:
        types.append("voice")

    if message.video_note:
        types.append("videonote")

    if message.video:
        types.append("video")

    if message.photo:
        types.append("photo")

    if message.document:
        types.append("document")

    if message.animation:
        types.append("gif")

    if message.sticker:
        # Always tag as "sticker" so a plain "sticker" lock catches everything
        types.append("sticker")
        if getattr(message.sticker, "is_animated", False):
            types.append("stickeranimated")
        if getattr(message.sticker, "is_premium", False):
            types.append("stickerpremium")

    if message.poll:
        types.append("poll")

    if message.game:
        types.append("game")

    if message.dice:
        types.append("emojigame")

    # ── forward ────────────────────────────────────────────────────────────
    if message.forward_from or message.forward_from_chat or message.forward_sender_name:
        types.append("forward")
        if message.forward_from and getattr(message.forward_from, "is_bot", False):
            types.append("forwardbot")
        if message.forward_from_chat and getattr(message.forward_from_chat, "type", "") == "channel":
            types.append("forwardchannel")
        if message.forward_from and not getattr(message.forward_from, "is_bot", False):
            types.append("forwarduser")
        if message.forward_sender_name and not message.forward_from:
            types.append("forwardstory")

    # ── inline bot ─────────────────────────────────────────────────────────
    if message.via_bot:
        types.append("inline")

    # ── external reply ─────────────────────────────────────────────────────
    if message.reply_to_message:
        rto = message.reply_to_message
        if rto.forward_from_chat and rto.forward_from_chat.id != message.chat.id:
            types.append("externalreply")

    # ── spoiler entities ───────────────────────────────────────────────────
    for attr in ("entities", "caption_entities"):
        for e in (getattr(message, attr, None) or []):
            if getattr(e, "type", None) == "spoiler":
                types.append("spoiler")
                break

    # ── inline keyboard button ─────────────────────────────────────────────
    if getattr(message, "reply_markup", None):
        types.append("button")

    # ── caption-based checks (photos/videos/docs with captions) ───────────
    if message.caption and not types:
        cap = message.caption
        if _has_invite(cap):
            types.append("invitelink")
        elif _has_url(cap):
            types.append("url")
        elif _has_email(cap):
            types.append("email")
        elif _has_phone(cap):
            types.append("phone")
        else:
            types.append("text")

    # ── pure text message ──────────────────────────────────────────────────
    if message.text and not types:
        t = message.text
        if t.strip().startswith("/"):
            types.append("command")
        elif _has_invite(t):
            types.append("invitelink")
        elif _has_botlink(t):
            types.append("botlink")
        elif _has_url(t):
            types.append("url")
        elif _has_email(t):
            types.append("email")
        elif _has_phone(t):
            types.append("phone")
        elif _has_cashtag(t):
            types.append("cashtags")
        elif _has_checklist(t):
            types.append("checklist")
        elif _has_cjk(t):
            types.append("cjk")
        elif _has_cyrillic(t):
            types.append("cyrillic")
        elif _has_rtl(t):
            types.append("rtl")
        elif _is_zalgo(t):
            types.append("zalgo")
        elif _only_emoji(t):
            types.append("emojionly")
        elif _has_emoji(t):
            types.append("emoji")
        elif message.sender_chat and not message.from_user:
            types.append("comment")
        else:
            types.append("text")

    # ── fallback ───────────────────────────────────────────────────────────
    if not types:
        types.append("text")

    return types

# ═════════════════════════════════════════════════════════════════════════════
# LOCKS — ENFORCER  (group=10, runs last)
# ═════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.group, group=10)
async def lock_enforcer(client, message: Message):
    """
    RULES (strictly in order):
      1. Any locks active?               No  → return immediately (NEVER delete)
      2. Is user exempt?                 Yes → return immediately (admin/sudo/approved)
      3. Detect ALL message types
      4. ANY detected type matches an active lock?  Yes → delete
      5. No match                                        → NEVER delete

    Approval ON/OFF has NO role here.
    Only active locks + non-exempt user triggers deletion.
    Commands (/) are NEVER deleted (they resolve to "command" type and
    "command" lock must be explicitly enabled to affect them).
    """
    # ── Step 1: skip entirely if no locks are set ──────────────────────────
    locks = await get_locks(message.chat.id)
    if not locks:
        return

    # ── Step 2: exempt check (admin / sudoer / approved) ──────────────────
    # anon-channel posts have no from_user — never exempt, always checked
    if message.from_user:
        if await is_exempt(client, message.chat.id, message.from_user.id):
            return

    # ── Step 3: detect ALL matching types for this message ─────────────────
    msg_types = _detect_types(message)

    # ── Step 4: delete only if at least one type matches an active lock ────
    #   "all" lock → delete everything regardless of type
    if "all" in locks or any(t in locks for t in msg_types):
        try:
            await message.delete()
        except Exception:
            pass

    # ── Step 5: no match → do nothing (message stays) ─────────────────────

# ═════════════════════════════════════════════════════════════════════════════
# APPROVAL — COMMANDS
# ═════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("approve") & filters.group & ~BANNED_USERS)
async def cmd_approve(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can approve users.**")
    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» User not found.**")
    if not user:
        return await message.reply_text("**» Reply to a user or provide username/ID.**")
    if await _is_approved(message.chat.id, user.id):
        return await message.reply_text(f"**» {user.mention} is already approved.**")
    await approval_col.update_one(
        {"chat_id": message.chat.id, "user_id": user.id},
        {"$set": {"name": user.first_name}},
        upsert=True,
    )
    await message.reply_text(
        f"**» ✅ {user.mention} approved.**\n"
        "They bypass all locks and flood limits."
    )

@app.on_message(filters.command("unapprove") & filters.group & ~BANNED_USERS)
async def cmd_unapprove(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can unapprove.**")
    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» User not found.**")
    if not user:
        return await message.reply_text("**» Reply to a user or provide username/ID.**")
    result = await approval_col.delete_one(
        {"chat_id": message.chat.id, "user_id": user.id}
    )
    if result.deleted_count:
        await message.reply_text(f"**» ❌ {user.mention} unapproved.**")
    else:
        await message.reply_text(f"**» {user.mention} was not approved.**")

@app.on_message(filters.command("approved") & filters.group & ~BANNED_USERS)
async def cmd_approved_list(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can view this.**")
    entries = [doc async for doc in approval_col.find({"chat_id": message.chat.id})]
    if not entries:
        return await message.reply_text("**» No approved users.**")
    lines = ["**» ✅ Approved Users:**\n"]
    for i, doc in enumerate(entries, 1):
        uid  = doc["user_id"]
        name = doc.get("name", "Unknown")
        lines.append(f"**{i}.** [{name}](tg://user?id={uid}) — `{uid}`")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)

# ═════════════════════════════════════════════════════════════════════════════
# CLEAN SERVICE — COMMANDS + HANDLERS
# ═════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("cleanservice") & filters.group & ~BANNED_USERS)
async def cmd_cleanservice(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")
    if len(message.command) < 2:
        on = await _is_cleanservice_on(message.chat.id)
        return await message.reply_text(
            f"**» Clean Service:** {'**ON** 🧹' if on else '**OFF** ❌'}"
        )
    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/cleanservice on` or `/cleanservice off`")
    enabled = arg == "on"
    await settings_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"cleanservice": enabled}}, upsert=True
    )
    if enabled:
        await message.reply_text(
            "**» 🧹 Clean Service: ON**\nJoin/leave messages will be auto-deleted."
        )
    else:
        await message.reply_text("**» ❌ Clean Service: OFF**")

@app.on_message(filters.new_chat_members)
async def auto_del_join(_, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass

@app.on_message(filters.left_chat_member)
async def auto_del_leave(_, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass

# ═════════════════════════════════════════════════════════════════════════════
# ANTI-FLOOD — COMMANDS
# ═════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command("antiflood") & filters.group & ~BANNED_USERS)
async def cmd_antiflood(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")
    if len(message.command) < 2:
        limit, enabled = await _get_flood_settings(message.chat.id)
        status   = "**ON** ✅" if enabled else "**OFF** ❌"
        lim_text = str(limit) if limit else "Not set"
        return await message.reply_text(
            f"**» Flood Protection:** {status}\n"
            f"**» Limit:** `{lim_text}` msgs / 10 sec"
        )
    try:
        limit = int(message.command[1])
        if limit < 1:
            raise ValueError
    except ValueError:
        return await message.reply_text(
            "**» Valid number > 0 needed.**\nEx: `/antiflood 5`"
        )
    await flood_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"limit": limit}}, upsert=True
    )
    await message.reply_text(
        f"**» Flood limit set: `{limit}` msgs / 10 sec.**\n"
        "Use `/flood on` to enable."
    )

@app.on_message(filters.command("flood") & filters.group & ~BANNED_USERS)
async def cmd_flood_toggle(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")
    if len(message.command) < 2:
        _, enabled = await _get_flood_settings(message.chat.id)
        return await message.reply_text(
            f"**» Flood Protection:** {'**ON** ✅' if enabled else '**OFF** ❌'}"
        )
    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/flood on` or `/flood off`")
    enabled = arg == "on"
    limit, _ = await _get_flood_settings(message.chat.id)
    if enabled and not limit:
        return await message.reply_text(
            "**» Set limit first.**\nEx: `/antiflood 5`"
        )
    await flood_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"enabled": enabled}}, upsert=True
    )
    if enabled:
        await message.reply_text(
            f"**» ✅ Flood Protection: ON**\n"
            f">`{limit}` msgs in 10 sec = muted 60s."
        )
    else:
        for k in [k for k in _flood_cache if k[0] == message.chat.id]:
            del _flood_cache[k]
        await message.reply_text("**» ❌ Flood Protection: OFF**")

# ═════════════════════════════════════════════════════════════════════════════
# ANTI-FLOOD — ENFORCER  (group=6)
# ═════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.group & ~filters.service & ~BANNED_USERS, group=6)
async def flood_checker(client, message: Message):
    """
    Act ONLY when ALL true:
      • Real non-bot user
      • Not a command
      • Flood is strictly enabled AND limit is set
      • User is NOT exempt (admin / sudo / approved)
    Every other case → return immediately. Message untouched.
    """
    if not message.from_user or message.from_user.is_bot:
        return
    if message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    limit, enabled = await _get_flood_settings(chat_id)

    # HARD GUARD — flood must be boolean True AND limit must exist
    if enabled is not True or not limit:
        return

    # Exempt (admin / approved) → pass
    if await is_exempt(client, chat_id, user_id):
        return

    # Sliding 10-second window
    now = time.time()
    key = (chat_id, user_id)
    _flood_cache[key] = [t for t in _flood_cache[key] if now - t < 10]
    _flood_cache[key].append(now)

    # Under limit → pass
    if len(_flood_cache[key]) <= limit:
        return

    # Over limit → delete + mute 60s
    try:
        await message.delete()
    except Exception:
        pass
    try:
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=int(now) + 60,
        )
        await client.send_message(
            chat_id,
            f"**» ⚠️ {message.from_user.mention} muted 60s — flooding.**",
        )
        _flood_cache[key] = []
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_29"
__help__ = """
🔻 /locktypes — open interactive lock panel
🔻 /locks — show active locks

✅ **APPROVAL**
🔻 /approve — reply to approve a user (bypasses locks + flood)
🔻 /unapprove — remove approval
🔻 /approved — list approved users

🧹 **CLEAN SERVICE**
🔻 /cleanservice on|off — auto-delete join/leave messages

⚙️ **ANTI-FLOOD**
🔻 /antiflood <n> — set limit (msgs per 10 sec)
🔻 /flood on|off — enable/disable flood protection
"""
