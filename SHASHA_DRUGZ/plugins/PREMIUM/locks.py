# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SHASHA_DRUGZ — Locks Module                                              ║
# ║  FULL REWRITE                                                             ║
# ║                                                                           ║
# ║  RULES:                                                                   ║
# ║  • Admin / SUDOER / Approved user  →  locks never apply                  ║
# ║  • Unapproved normal user          →  active locks enforced              ║
# ║  • No lock active                  →  all messages pass freely           ║
# ║  • "all" lock                      →  blocks every message (non-exempt)  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

import re
import unicodedata
from typing import List
from pyrogram import filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import MONGO_DB_URI
from motor.motor_asyncio import AsyncIOMotorClient

# Import shared exemption check from antiflood module
from SHASHA_DRUGZ.modules.antiflood import is_exempt

# ─── MongoDB ──────────────────────────────────────────────────────────────────
mongo = AsyncIOMotorClient(MONGO_DB_URI)
db    = mongo["SHASHA_DRUGZ"]["CHAT_LOCKS"]

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
# DB HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def get_locks(chat_id: int) -> List[str]:
    row = await db.find_one({"chat_id": chat_id})
    if not row:
        return []
    return row.get("locks", [])


async def update_locks(chat_id: int, locks: List[str]):
    await db.update_one({"chat_id": chat_id}, {"$set": {"locks": locks}}, upsert=True)


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN HELPERS (for command handlers — does not use is_exempt intentionally,
# approval status should not block admin commands)
# ═════════════════════════════════════════════════════════════════════════════

async def _is_admin_msg(message: Message) -> bool:
    try:
        if not message.from_user:
            return False
        if message.from_user.id in SUDOERS:
            return True
        mem = await app.get_chat_member(message.chat.id, message.from_user.id)
        return mem.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        return False


async def _is_admin_query(query: CallbackQuery) -> bool:
    try:
        if query.from_user.id in SUDOERS:
            return True
        mem = await app.get_chat_member(query.message.chat.id, query.from_user.id)
        return mem.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════════════
# KEYBOARD UI
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
# LOCK COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("locktypes") & filters.group)
async def open_lock_panel(_, message: Message):
    if not await _is_admin_msg(message):
        return await message.reply_text("Admins only.")
    locks = await get_locks(message.chat.id)
    await message.reply_text(
        "<blockquote>🔐 Available Locks</blockquote>",
        reply_markup=locks_keyboard(locks),
    )


@app.on_message(filters.command("locks") & filters.group)
async def show_locks(_, message: Message):
    locks = await get_locks(message.chat.id)
    if not locks:
        return await message.reply_text("No active locks in this chat.")
    await message.reply_text("Active locks:\n" + "\n".join(f"🔒 {x}" for x in locks))


# ═════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═════════════════════════════════════════════════════════════════════════════

@app.on_callback_query(filters.regex(r"^toggle::"))
async def toggle_callback(_, query: CallbackQuery):
    if not await _is_admin_query(query):
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
# DETECTION UTILITIES
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


def _has_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text or ""))


def _only_emoji(text: str) -> bool:
    if not text:
        return False
    s = re.sub(r"[\s\U0000FE0F\U0000200D]", "", text)
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
        t or "", re.IGNORECASE
    ))


def _has_botlink(t: str) -> bool:
    return bool(re.search(r"@\w*bot\b", t or "", re.IGNORECASE))


def _detect_type(message: Message) -> str:
    """
    Inspect the message and return a single lock-type string.
    This is pure detection — no deletion happens here.
    """

    # ── Media / special types ─────────────────────────────────────────────────
    if message.media_group_id:
        return "album"

    if message.sender_chat and getattr(message.sender_chat, "type", "") == "channel":
        return "anonchannel"

    if message.new_chat_members:
        for m in message.new_chat_members:
            if m.is_bot:
                return "bot"
        return "text"   # non-bot members joining → not a lockable type

    if message.audio:      return "audio"
    if message.voice:      return "voice"
    if message.video_note: return "videonote"
    if message.video:      return "video"
    if message.photo:      return "photo"
    if message.document:   return "document"
    if message.animation:  return "gif"

    if message.sticker:
        if getattr(message.sticker, "is_animated", False):  return "stickeranimated"
        if getattr(message.sticker, "is_premium", False):   return "stickerpremium"
        return "sticker"

    if message.poll:  return "poll"
    if message.game:  return "game"
    if message.dice:  return "emojigame"

    # ── Forwards ──────────────────────────────────────────────────────────────
    if message.forward_from or message.forward_from_chat or message.forward_sender_name:
        if message.forward_from and getattr(message.forward_from, "is_bot", False):
            return "forwardbot"
        if message.forward_from_chat and getattr(message.forward_from_chat, "type", "") == "channel":
            return "forwardchannel"
        if message.forward_from:
            return "forwarduser"
        if message.forward_sender_name and not message.forward_from:
            return "forwardstory"
        return "forward"

    # ── Inline bot ────────────────────────────────────────────────────────────
    if message.via_bot:
        return "inline"

    # ── External reply ────────────────────────────────────────────────────────
    if message.reply_to_message:
        rto = message.reply_to_message
        if rto.forward_from_chat and rto.forward_from_chat.id != message.chat.id:
            return "externalreply"

    # ── Spoiler (entity check) ────────────────────────────────────────────────
    entities = getattr(message, "entities", None) or getattr(message, "caption_entities", None)
    if entities:
        for e in entities:
            if getattr(e, "type", None) == "spoiler":
                return "spoiler"

    # ── Inline button markup ──────────────────────────────────────────────────
    if getattr(message, "reply_markup", None):
        return "button"

    # ── Caption (media with caption) ─────────────────────────────────────────
    if message.caption:
        cap = message.caption
        if _has_invite(cap):  return "invitelink"
        if _has_url(cap):     return "url"
        if _has_email(cap):   return "email"
        if _has_phone(cap):   return "phone"
        return "text"

    # ── Plain text ────────────────────────────────────────────────────────────
    if message.text:
        t = message.text
        if t.strip().startswith("/"):         return "command"
        if _has_invite(t):                    return "invitelink"
        if _has_botlink(t):                   return "botlink"
        if _has_url(t):                       return "url"
        if _has_email(t):                     return "email"
        if _has_phone(t):                     return "phone"
        if _has_cashtag(t):                   return "cashtags"
        if _has_checklist(t):                 return "checklist"
        if _has_cjk(t):                       return "cjk"
        if _has_cyrillic(t):                  return "cyrillic"
        if _has_rtl(t):                       return "rtl"
        if _is_zalgo(t):                      return "zalgo"
        if _only_emoji(t):                    return "emojionly"
        if _has_emoji(t):                     return "emoji"
        if message.sender_chat and not message.from_user:
            return "comment"
        return "text"

    return "text"


# ═════════════════════════════════════════════════════════════════════════════
# LOCK ENFORCER  (group=10 — runs last, after approval+flood)
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.group, group=10)
async def lock_enforcer(client, message: Message):
    """
    RULES:
    • No active locks          → return, never delete
    • Exempt user              → return, never delete  (admin/approved/sudoer)
    • msg_type in active locks → delete
    • "all" lock active        → delete everything (non-exempt)

    Approved users are whitelisted — even if a lock is ON,
    their messages are NEVER deleted.
    """

    # ── Step 1: any locks at all? ─────────────────────────────────────────────
    locks = await get_locks(message.chat.id)
    if not locks:
        return   # nothing locked → pass all messages

    # ── Step 2: exemption check ───────────────────────────────────────────────
    # from_user is None for anonymous channel posts — those are never exempt
    if message.from_user:
        if await is_exempt(client, message.chat.id, message.from_user.id):
            return   # admin / approved / sudoer → never deleted by locks

    # ── Step 3: detect message type ───────────────────────────────────────────
    msg_type = _detect_type(message)

    # ── Step 4: delete if locked ──────────────────────────────────────────────
    should_delete = ("all" in locks) or (msg_type in locks)

    if should_delete:
        try:
            await message.delete()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_29"
__help__ = """
🔻 /locktypes ➠ ᴏᴘᴇɴꜱ ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ ʟᴏᴄᴋ ᴘᴀɴᴇʟ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ)
🔻 /locks ➠ ꜱʜᴏᴡ ᴀʟʟ ᴀᴄᴛɪᴠᴇ ʟᴏᴄᴋꜱ

🔒 all ➠ ʙʟᴏᴄᴋ ᴇᴠᴇʀʏᴛʜɪɴɢ
🔒 album / anonchannel / audio / voice / videonote
🔒 video / photo / document / gif
🔒 sticker / stickeranimated / stickerpremium
🔒 poll / game / emojigame
🔒 bot / botlink / command
🔒 forward / forwarduser / forwardbot / forwardchannel / forwardstory
🔒 inline / invitelink / externalreply
🔒 url / email / phone / cashtags / checklist
🔒 emoji / emojionly / emojicustom
🔒 cjk / cyrillic / rtl / zalgo
🔒 spoiler / button / comment / text

📌 Approved users bypass ALL locks.
"""
