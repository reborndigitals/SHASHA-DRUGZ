import re
import unicodedata
from typing import List

from pyrogram import Client, filters, enums
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

# Mongo
mongo = AsyncIOMotorClient(MONGO_DB_URI)
db = mongo["SHASHA_DRUGZ"]["CHAT_LOCKS"]

# --- full list of 45 lock types (match user's names) ---
LOCK_TYPES = [
    "all", "album", "anonchannel", "audio", "bot", "botlink", "button",
    "cashtags", "checklist", "cjk", "command", "comment", "contact", "cyrillic",
    "document", "email", "emoji", "emojicustom", "emojigame", "emojionly",
    "externalreply", "forward", "forwardbot", "forwardchannel", "forwardstory",
    "forwarduser", "game", "gif", "inline", "invitelink", "location", "phone",
    "photo", "poll", "rtl", "spoiler", "sticker", "stickeranimated", "stickerpremium",
    "text", "url", "video", "videonote", "voice", "zalgo"
]


# -------------------- helpers: DB & admin --------------------

async def get_locks(chat_id: int) -> List[str]:
    row = await db.find_one({"chat_id": chat_id})
    if not row:
        await db.insert_one({"chat_id": chat_id, "locks": []})
        return []
    return row.get("locks", [])


async def update_locks(chat_id: int, locks: List[str]):
    await db.update_one({"chat_id": chat_id}, {"$set": {"locks": locks}}, upsert=True)


async def is_admin_from_message(message: Message) -> bool:
    """Return True if message.from_user is admin or owner or in SUDOERS."""
    try:
        if not message.from_user:
            return False
        if message.from_user.id in SUDOERS:
            return True
        mem = await app.get_chat_member(message.chat.id, message.from_user.id)
        return mem.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        return False


async def is_admin_from_query(query: CallbackQuery) -> bool:
    try:
        if query.from_user.id in SUDOERS:
            return True
        mem = await app.get_chat_member(query.message.chat.id, query.from_user.id)
        return mem.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except Exception:
        return False


# -------------------- keyboard UI --------------------

def locks_keyboard(active: List[str]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, l in enumerate(LOCK_TYPES, 1):
        icon = "–" if l in active else "+"
        row.append(InlineKeyboardButton(f"{icon} {l}", callback_data=f"toggle::{l}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    # final control row
    rows.append([InlineKeyboardButton("⌯ Close ⌯", callback_data="locks::close")])
    return InlineKeyboardMarkup(rows)


# -------------------- commands --------------------

@Client.on_message(filters.command("locktypes") & filters.group)
async def open_lock_panel(_, message: Message):
    if not await is_admin_from_message(message):
        return await message.reply_text("Admins only.")
    locks = await get_locks(message.chat.id)
    await message.reply_text("<blockquote>🔐 Available Locks</blockquote>", reply_markup=locks_keyboard(locks))


@Client.on_message(filters.command("locks") & filters.group)
async def show_locks(_, message: Message):
    locks = await get_locks(message.chat.id)
    if not locks:
        return await message.reply_text("No active locks in this chat.")
    await message.reply_text("Active locks:\n" + "\n".join(f"🔒 {x}" for x in locks))


# -------------------- callback handling --------------------

@Client.on_callback_query(filters.regex(r"^toggle::"))
async def toggle_callback(_, query: CallbackQuery):
    # admin check
    if not await is_admin_from_query(query):
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

    # refresh keyboard
    try:
        await query.message.edit_text("<blockquote>🔐 Available Locks</blockquote>", reply_markup=locks_keyboard(locks))
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^locks::close$"))
async def close_callback(_, query: CallbackQuery):
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer()


# -------------------- detection utilities --------------------

EMOJI_RE = re.compile(
    "["                            # wide ranges of emoji + symbols
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


def contains_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text or ""))


def only_emoji(text: str) -> bool:
    if not text:
        return False
    # strip whitespace and typical punctuation, then test if all leftover are emoji
    s = re.sub(r"[\s\U0000FE0F\U0000200D]", "", text)
    return bool(s) and all(EMOJI_RE.fullmatch(ch) for ch in s)


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", text or ""))


def contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text or ""))


def contains_rtl(text: str) -> bool:
    return bool(re.search(r"[\u0590-\u06FF]", text or ""))


def contains_email(text: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or ""))


def contains_url(text: str) -> bool:
    return bool(re.search(r"(https?://|www\.)", text or ""))


def contains_phone(text: str) -> bool:
    # simple phone heuristic: sequence of 7-15 digits, optionally + at start
    return bool(re.search(r"\+?\d[\d\-\s]{6,}\d", text or ""))


def contains_cashtag(text: str) -> bool:
    return bool(re.search(r"[\$₹€£¥]", text or ""))


def contains_checklist(text: str) -> bool:
    # detects common checklist / checkbox characters
    return bool(re.search(r"[☐☑✔️\u2705\U0001F5F8]", text or ""))


def is_zalgo_text(text: str) -> bool:
    # count combining marks (category 'Mn') — zalgo often has many combining marks
    if not text:
        return False
    total = 0
    combining = 0
    for ch in text:
        total += 1
        if unicodedata.category(ch) == "Mn":
            combining += 1
    # if more than 30% of characters are combining or > 10 combining marks -> zalgo
    return (total > 0 and combining / total > 0.30) or (combining > 10)


# -------------------- primary filter (auto-delete) --------------------

@Client.on_message(filters.group, group=99)
async def lock_enforcer(_, message: Message):
    # quick pass: if no locks or sender is sudoer -> allow
    locks = await get_locks(message.chat.id)
    if not locks:
        return
    if message.from_user and message.from_user.id in SUDOERS:
        return

    # HELPER: mark booleans for features
    msg_type = None  # type string to compare against lock names

    # 1) album — messages that are part of a media group
    if message.media_group_id:
        msg_type = "album"

    # 2) anonymous channel post (sender_chat set and is a channel)
    elif message.sender_chat and getattr(message.sender_chat, "type", "") == "channel":
        msg_type = "anonchannel"

    # 3) new_chat_members containing a bot -> 'bot' lock (someone added a bot)
    elif message.new_chat_members:
        for m in message.new_chat_members:
            if m.is_bot:
                msg_type = "bot"
                break

    # 4) audio / voice / video_note / video / photo / document / sticker / gif
    elif message.audio:
        msg_type = "audio"
    elif message.voice:
        msg_type = "voice"
    elif message.video_note:          # ✅ fixed: correct attribute name
        msg_type = "videonote"
    elif message.video:
        msg_type = "video"
    elif message.photo:
        msg_type = "photo"
    elif message.document:
        msg_type = "document"
    elif message.animation:
        # Telegram animation = GIF-like (animation)
        msg_type = "gif"
    elif message.sticker:
        # sticker variants
        if getattr(message.sticker, "is_animated", False):
            msg_type = "stickeranimated"
        elif getattr(message.sticker, "is_premium", False):
            msg_type = "stickerpremium"
        else:
            msg_type = "sticker"

    # 5) poll
    elif message.poll:
        msg_type = "poll"

    # 6) game / dice (small heuristic)
    elif message.game:
        msg_type = "game"
    elif message.dice:
        msg_type = "emojigame"

    # 7) forwarded messages
    elif message.forward_from or message.forward_from_chat or message.forward_sender_name:
        # forwardbot: forward_from.is_bot
        if message.forward_from and getattr(message.forward_from, "is_bot", False):
            msg_type = "forwardbot"
        # forwardchannel: forwarded from a channel-like
        elif message.forward_from_chat and getattr(message.forward_from_chat, "type", "") == "channel":
            msg_type = "forwardchannel"
        # forwarduser: forwarded from a user
        elif message.forward_from:
            msg_type = "forwarduser"
        # forwardstory (heuristic): if forward_sender_name exists and no forward_from object
        elif message.forward_sender_name and not message.forward_from:
            msg_type = "forwardstory"
        else:
            msg_type = "forward"

    # 8) inline (via_bot indicates was sent through inline bot)
    elif message.via_bot:
        msg_type = "inline"

    # 9) replies to messages from other chats => externalreply
    elif message.reply_to_message and (message.reply_to_message.forward_from_chat or (message.reply_to_message.sender_chat and getattr(message.reply_to_message.sender_chat, "type", "") != "channel")):
        msg_type = "externalreply"

    # 10) captions or text — more granular checks
    elif message.caption:
        text = (message.caption or "") or ""
        # url in caption
        if contains_url(text):
            msg_type = "url"
        else:
            # default caption treated as text
            msg_type = "text"
    elif message.text:
        text = message.text or ""
        lower = text.lower()

        # command (starts with /)
        if lower.strip().startswith("/"):
            msg_type = "command"

        # botlink (username with 'bot' or @... that references bots)
        elif re.search(r"@\w*bot\b", lower):
            msg_type = "botlink"

        # invitelink (group/channel invite links or tg.me/joinchat etc)
        elif re.search(r"(t\.me\/joinchat|t\.me\/\+|telegram\.me\/|joinchat|invite\.link|telegram\.dog\/|t\.me\/)", lower):
            msg_type = "invitelink"

        # url
        elif contains_url(lower):
            msg_type = "url"

        # email
        elif contains_email(lower):
            msg_type = "email"

        # phone
        elif contains_phone(lower):
            msg_type = "phone"

        # cashtags
        elif contains_cashtag(lower):
            msg_type = "cashtags"

        # checklist
        elif contains_checklist(lower):
            msg_type = "checklist"

        # cjk
        elif contains_cjk(lower):
            msg_type = "cjk"

        # cyrillic
        elif contains_cyrillic(lower):
            msg_type = "cyrillic"

        # rtl
        elif contains_rtl(lower):
            msg_type = "rtl"

        # zalgo
        elif is_zalgo_text(lower):
            msg_type = "zalgo"

        # only emoji (emoji-only message)
        elif only_emoji(lower):
            msg_type = "emojionly"

        # contains any emoji
        elif contains_emoji(lower):
            msg_type = "emoji"

        # contains buttons? there's no direct field on message, but reply_markup may have inline_keyboard/buttons
        elif getattr(message, "reply_markup", None):
            # treat as button if reply_markup contains InlineKeyboardMarkup
            msg_type = "button"

        # comment - heuristic:
        # messages that originate from a linked channel as "discussion comment" usually have sender_chat but the sender isn't a chat member.
        # We'll mark "comment" if sender_chat is present and from_user is None or message.author_signature exists.
        elif message.sender_chat and message.from_user is None:
            msg_type = "comment"

        else:
            msg_type = "text"

    # fallback: treat unknown as text
    if not msg_type:
        msg_type = "text"

    # If the message is a reply_to_message to a message belonging to another chat -> externalreply
    try:
        if message.reply_to_message:
            if message.reply_to_message.forward_from_chat and message.reply_to_message.forward_from_chat.id != message.chat.id:
                msg_type = "externalreply"
    except Exception:
        pass

    # If message.entities contain Spoiler entity
    has_spoiler = False
    if getattr(message, "entities", None):
        for e in message.entities:
            if e.type == "spoiler":
                has_spoiler = True
                break
    if has_spoiler:
        msg_type = "spoiler"

    # Additional detection for 'button' when reply_markup is present (inline keyboard or keyboard)
    if getattr(message, "reply_markup", None):
        # if reply_markup exists then it's a button message (e.g. inline keyboard or keyboard)
        msg_type = "button"

    # Additional detection: 'botlink' inside text like @username containing 'bot'
    if message.text and "@" in message.text and re.search(r"@\w*bot\b", message.text, re.IGNORECASE):
        msg_type = "botlink"

    # Additional detection: 'invitelink' for plain t.me/ or joinchat etc in text or entities
    if message.text and re.search(r"(t\.me\/joinchat|t\.me\/\+|t\.me\/|telegram\.me\/|joinchat|invite\.link)", message.text, re.IGNORECASE):
        msg_type = "invitelink"

    # Now final check: if msg_type matches any active locks OR 'all' is set -> delete
    try:
        locks_active = await get_locks(message.chat.id)
        # If all locked
        if "all" in locks_active:
            await message.delete()
            return
        # If specific lock is active
        if msg_type in locks_active:
            await message.delete()
            return
        # Some locks are detected by multiple signals; check additional possible matches:
        # ex: 'botlink' could be detected as url/text earlier — ensure it's caught:
        extra_checks = {
            "botlink": lambda: message.text and re.search(r"@\w*bot\b", message.text, re.IGNORECASE),
            "url": lambda: (message.text and contains_url(message.text)) or (message.caption and contains_url(message.caption)),
            "email": lambda: (message.text and contains_email(message.text)) or (message.caption and contains_email(message.caption)),
            "phone": lambda: (message.text and contains_phone(message.text)) or (message.caption and contains_phone(message.caption)),
            "cashtags": lambda: (message.text and contains_cashtag(message.text)) or (message.caption and contains_cashtag(message.caption)),
            "checklist": lambda: (message.text and contains_checklist(message.text)) or (message.caption and contains_checklist(message.caption)),
            "emojionly": lambda: (message.text and only_emoji(message.text)) or (message.caption and only_emoji(message.caption)),
            "emoji": lambda: (message.text and contains_emoji(message.text)) or (message.caption and contains_emoji(message.caption)),
            "invitelink": lambda: (message.text and re.search(r"(t\.me\/joinchat|t\.me\/\+|t\.me\/|telegram\.me\/|joinchat|invite\.link)", message.text, re.IGNORECASE)) or (message.caption and re.search(r"(t\.me\/joinchat|t\.me\/\+|t\.me\/|telegram\.me\/|joinchat|invite\.link)", message.caption, re.IGNORECASE)),
            "inline": lambda: bool(message.via_bot),
            "button": lambda: bool(getattr(message, "reply_markup", None)),
            "emojiCustom": lambda: False,  # custom emoji detection via message.entities is not straightforward; skip special detection
        }
        # iterate extras
        for lockname, checker in extra_checks.items():
            if lockname in locks_active:
                try:
                    if checker():
                        await message.delete()
                        return
                except Exception:
                    pass

    except Exception:
        # silently ignore DB / deletion errors
        pass

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_29"
__help__ = """
🔻 /locktypes ➠ ᴏᴘᴇɴꜱ ᴛʜᴇ ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ ʟᴏᴄᴋ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ (ᴀᴅᴍɪɴꜱ / ꜱᴜᴅᴏ ᴏɴʟʏ).
🔻 /locks ➠ ꜱʜᴏᴡꜱ ᴀʟʟ ᴀᴄᴛɪᴠᴇ ʟᴏᴄᴋꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.

🔒 all ➠ ʙʟᴏᴄᴋꜱ ᴀʟʟ ᴍᴇꜱꜱᴀɢᴇꜱ  
🔒 album ➠ ᴍᴇᴅɪᴀ ɢʀᴏᴜᴘꜱ  
🔒 anonchannel ➠ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴄʜᴀɴɴᴇʟ ᴍᴇꜱꜱᴀɢᴇꜱ  
🔒 audio / voice / videonote  
🔒 photo / video / gif / document  
🔒 sticker / stickeranimated / stickerpremium  
🔒 poll / game / emojigame  
🔒 bot ➠ ʙᴏᴛꜱ ᴀᴅᴅᴇᴅ ᴛᴏ ɢʀᴏᴜᴘ  
🔒 botlink ➠ @ʙᴏᴛ ᴜꜱᴇʀɴᴀᴍᴇꜱ  
🔒 command ➠ /ᴄᴏᴍᴍᴀɴᴅꜱ  
🔒 forward / forwarduser / forwardbot / forwardchannel / forwardstory  
🔒 inline ➠ ɪɴʟɪɴᴇ ʙᴏᴛ ᴍᴇꜱꜱᴀɢᴇꜱ  
🔒 invitelink ➠ ɢʀᴏᴜᴘ / ᴄʜᴀɴɴᴇʟ ʟɪɴᴋꜱ  
🔒 url / email / phone / cashtags  
🔒 checklist  
🔒 emoji / emojionly  
🔒 cjk / cyrillic / rtl  
🔒 zalgo  
🔒 spoiler  
🔒 button ➠ ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪᴛʜ ʙᴜᴛᴛᴏɴꜱ  
🔒 text / comment / location / contact
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Locks"
MOD_PRICE = "50"
