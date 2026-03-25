# SHASHA_DRUGZ/plugins/PREMIUM/qualitybutton.py
# ══════════════════════════════════════════════════════════════
#  Quality Button Post System — SHASHA_DRUGZ Plugin
#
#  FEATURES:
#    • Create posts from replied message (text/photo/video/animation/document)
#    • Inline buttons via [Text](url) syntax  (max 8 per row, Telegram-safe)
#    • Edit saved post content + buttons (/editpost)
#    • Delete saved post (/delpost)
#    • Send post to current chat or any group/channel (/post <id> [chat_id])
#    • Auto scheduler — asks interval (hours) before scheduling
#    • Protected posts — no forward / no save
#    • All posts stored in MongoDB with full metadata
#    • Owner-only restriction on sensitive commands
#    • FloodWait handling in _send_post
#    • Scheduler duplicate-send lock (running flag)
#    • _pending memory-leak cleanup (5-min TTL)
#    • DB indexes created at startup
#    • Separate Motor client (own DB connection)
#
#  COMMANDS:
#    /createpost          → reply to any message to save it as a post
#    /post <id> [chat]    → send post here or to another chat_id / @username
#    /editpost <id>       → reply to new content to replace saved post
#    /delpost <id>        → delete saved post from DB
#    /mypost              → list all saved post IDs
#    /schedulepost <id>   → interactive scheduler (asks target + hours)
#    /cancelschedule <id> → cancel a pending scheduled post
#
#  BUTTON FORMAT  (inside post text/caption):
#    [Button1](url) [Button2](url)      ← one line = one row (max 8 buttons)
#    [Button3](url)
#
#  COLLECTIONS:
#    post_data       — saved posts
#    post_schedules  — active schedules
# ══════════════════════════════════════════════════════════════

import re
import asyncio
import logging
import random as _random
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)
from pyrogram.errors import (
    ChatAdminRequired,
    PeerIdInvalid,
    ChannelPrivate,
    FloodWait,
)

# ── App client ────────────────────────────────────────────────────────────────
from SHASHA_DRUGZ import app

# ── Config ────────────────────────────────────────────────────────────────────
# OWNER_ID  : int  OR  list[int]
# MONGO_DB_URI : str  OR  list[str]  (random pick if list)
from config import MONGO_DB_URI, OWNER_ID

_OWNERS: set[int] = (
    set(OWNER_ID)
    if isinstance(OWNER_ID, (list, tuple, set))
    else {int(OWNER_ID)}
)

logger = logging.getLogger("QualityButton")

# ══════════════════════════════════════════════════════════════
#  SEPARATE MOTOR CLIENT  (own DB connection for this module)
# ══════════════════════════════════════════════════════════════
_mongo_uri = (
    _random.choice(MONGO_DB_URI)
    if isinstance(MONGO_DB_URI, (list, tuple))
    else MONGO_DB_URI
)
_motor_client = AsyncIOMotorClient(_mongo_uri)

# ── Collections ───────────────────────────────────────────────────────────────
_db        = _motor_client["POST_SYSTEM"]
_posts     = _db["post_data"]        # saved posts
_schedules = _db["post_schedules"]   # active schedules

# ── In-memory conversation state (per user) ───────────────────────────────────
_pending: dict = {}
_PENDING_TTL   = 300   # seconds before stale entry is cleared


# ══════════════════════════════════════════════════════════════
#  STARTUP — DB indexes
# ══════════════════════════════════════════════════════════════

async def _create_indexes():
    try:
        await _posts.create_index("post_id", unique=True)
        await _schedules.create_index("next_send")
        logger.info("QualityButton: DB indexes ensured.")
    except Exception as e:
        logger.warning("QualityButton: index creation warning: %s", e)


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _is_owner(user_id: int) -> bool:
    return user_id in _OWNERS


async def _next_id() -> int:
    last = await _posts.find_one(sort=[("post_id", -1)])
    return (last["post_id"] + 1) if last else 1


def _parse_buttons(text: str):
    """
    Parse [Label](url) pairs from text.
    Each line = one button row. Max 8 buttons per row (Telegram limit).
    Lines with no buttons are preserved as plain text.
    """
    btn_pattern = r"\[(.*?)\]\((https?://\S+?)\)"
    rows        = []
    clean_lines = []

    for line in text.splitlines():
        matches = re.findall(btn_pattern, line)
        if matches:
            matches = matches[:8]   # enforce Telegram per-row limit
            rows.append([InlineKeyboardButton(name, url=url) for name, url in matches])
            leftover = re.sub(btn_pattern, "", line).strip()
            if leftover:
                clean_lines.append(leftover)
        else:
            clean_lines.append(line)

    return "\n".join(clean_lines).strip(), rows


def _build_markup(raw_buttons: list) -> InlineKeyboardMarkup | None:
    if not raw_buttons:
        return None
    rows = [
        [InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
        for row in raw_buttons
    ]
    return InlineKeyboardMarkup(rows) if rows else None


def _serialize_buttons(button_rows: list) -> list:
    return [
        [{"text": b.text, "url": b.url} for b in row]
        for row in button_rows
    ]


def _extract_media(msg: Message) -> tuple[str, str | None]:
    if msg.photo:      return "photo",     msg.photo.file_id
    if msg.animation:  return "animation", msg.animation.file_id
    if msg.video:      return "video",     msg.video.file_id
    if msg.document:   return "document",  msg.document.file_id
    return "text", None


def _pending_set(user_id: int, data: dict):
    """Store pending state and stamp it with current time (for TTL)."""
    data["time"]      = datetime.utcnow()
    _pending[user_id] = data


def _pending_cleanup():
    """Drop any _pending entries older than _PENDING_TTL seconds."""
    now = datetime.utcnow()
    for uid in list(_pending.keys()):
        ts = _pending[uid].get("time")
        if ts and (now - ts).total_seconds() > _PENDING_TTL:
            _pending.pop(uid, None)


async def _send_post(client, chat_id, data: dict, protect: bool = False):
    """
    Send a saved post to chat_id.
    Handles FloodWait automatically (waits + retries once).
    All other exceptions propagate to the caller.
    """
    text   = data.get("text", "")
    markup = _build_markup(data.get("buttons", []))
    pmode  = data.get("parse_mode", "html")
    fid    = data.get("file_id")
    ptype  = data.get("type", "text")

    media_kw = dict(
        caption=text,
        reply_markup=markup,
        parse_mode=pmode,
        protect_content=protect,
    )

    async def _do():
        if ptype == "photo":
            await client.send_photo(chat_id, fid, **media_kw)
        elif ptype == "animation":
            await client.send_animation(chat_id, fid, **media_kw)
        elif ptype == "video":
            await client.send_video(chat_id, fid, **media_kw)
        elif ptype == "document":
            await client.send_document(chat_id, fid, **media_kw)
        else:
            await client.send_message(
                chat_id, text,
                reply_markup=markup,
                parse_mode=pmode,
                disable_web_page_preview=False,
                protect_content=protect,
            )

    try:
        await _do()
    except FloodWait as e:
        logger.warning("FloodWait %ss — retrying after wait.", e.value)
        await asyncio.sleep(e.value)
        await _do()


# ══════════════════════════════════════════════════════════════
#  /createpost
# ══════════════════════════════════════════════════════════════

@app.on_message(
    (filters.command("createpost") & filters.private) |
    (filters.command("createpost") & filters.group)
)
async def cmd_createpost(_, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )
    if not message.reply_to_message:
        return await message.reply_text(
            "<blockquote>❌ <b>ᴜsᴀɢᴇ:</b> Reply to a message and use "
            "<code>/createpost</code>.</blockquote>"
        )

    msg  = message.reply_to_message
    text = msg.text or msg.caption or ""

    if msg.sticker:
        return await message.reply_text(
            "<blockquote>❌ Stickers are not supported.</blockquote>"
        )

    clean_text, buttons = _parse_buttons(text)
    ptype, fid          = _extract_media(msg)
    post_id             = await _next_id()

    await _posts.insert_one({
        "post_id":    post_id,
        "text":       clean_text,
        "buttons":    _serialize_buttons(buttons),
        "parse_mode": "html",
        "type":       ptype,
        "file_id":    fid,
        "protected":  False,
        "created_by": message.from_user.id,
        "created_at": datetime.utcnow(),
    })

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 sᴇɴᴅ ɴᴏᴡ",    callback_data=f"qb_sendnow_{post_id}"),
        InlineKeyboardButton("🗓 sᴄʜᴇᴅᴜʟᴇ",     callback_data=f"qb_schedule_{post_id}"),
    ], [
        InlineKeyboardButton("🗑 ᴅᴇʟᴇᴛᴇ ᴘᴏsᴛ", callback_data=f"qb_del_{post_id}"),
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="qb_close"),
    ]])

    await message.reply_text(
        f"<blockquote>✅ <b>ᴘᴏsᴛ sᴀᴠᴇᴅ!</b>\n\n"
        f"🆔 <b>ᴘᴏsᴛ ID:</b> <code>{post_id}</code>\n"
        f"📁 <b>ᴛʏᴘᴇ:</b> <code>{ptype}</code>\n"
        f"🔘 <b>ʙᴜᴛᴛᴏɴs:</b> <code>{sum(len(r) for r in buttons)}</code>\n\n"
        f"ᴜsᴇ <code>/post {post_id}</code> ᴛᴏ sᴇɴᴅ ɪᴛ.</blockquote>",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════════
#  /post <id> [chat_id]
# ══════════════════════════════════════════════════════════════

@app.on_message(filters.command("post"))
async def cmd_post(client, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )

    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote><b>ᴜsᴀɢᴇ:</b>\n"
            "<code>/post &lt;id&gt;</code> — send here\n"
            "<code>/post &lt;id&gt; -100xxxxxxxxxx</code> — send to channel/group</blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    data = await _posts.find_one({"post_id": post_id})
    if not data:
        return await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

    if len(args) >= 3:
        raw = args[2]
        target_chat = int(raw) if raw.lstrip("-").isdigit() else raw
    else:
        target_chat = message.chat.id

    try:
        await _send_post(client, target_chat, data, protect=data.get("protected", False))
        if target_chat != message.chat.id:
            await message.reply_text(
                f"<blockquote>✅ <b>ᴘᴏsᴛ <code>{post_id}</code> sᴇɴᴛ</b> "
                f"ᴛᴏ <code>{target_chat}</code>!</blockquote>"
            )
    except ChatAdminRequired:
        await message.reply_text("<blockquote>❌ I'm not an admin in that chat.</blockquote>")
    except (PeerIdInvalid, ChannelPrivate):
        await message.reply_text("<blockquote>❌ Chat not found or I'm not a member.</blockquote>")
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ Failed: <code>{e}</code></blockquote>")


# ══════════════════════════════════════════════════════════════
#  /editpost <id>
# ══════════════════════════════════════════════════════════════

@app.on_message(filters.command("editpost"))
async def cmd_editpost(_, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )

    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote><b>ᴜsᴀɢᴇ:</b> Reply to new content + "
            "<code>/editpost &lt;id&gt;</code></blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    if not await _posts.find_one({"post_id": post_id}):
        return await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

    if not message.reply_to_message:
        return await message.reply_text(
            "<blockquote>❌ Reply to the <b>new content</b> you want to replace this post with.</blockquote>"
        )

    msg  = message.reply_to_message
    text = msg.text or msg.caption or ""

    if msg.sticker:
        return await message.reply_text("<blockquote>❌ Stickers are not supported.</blockquote>")

    clean_text, buttons = _parse_buttons(text)
    ptype, fid          = _extract_media(msg)

    await _posts.update_one(
        {"post_id": post_id},
        {"$set": {
            "text":       clean_text,
            "buttons":    _serialize_buttons(buttons),
            "type":       ptype,
            "file_id":    fid,
            "updated_at": datetime.utcnow(),
        }}
    )

    await message.reply_text(
        f"<blockquote>✅ <b>ᴘᴏsᴛ <code>{post_id}</code> ᴜᴘᴅᴀᴛᴇᴅ!</b>\n\n"
        f"📁 <b>ɴᴇᴡ ᴛʏᴘᴇ:</b> <code>{ptype}</code>\n"
        f"🔘 <b>ʙᴜᴛᴛᴏɴs:</b> <code>{sum(len(r) for r in buttons)}</code></blockquote>"
    )


# ══════════════════════════════════════════════════════════════
#  /delpost <id>
# ══════════════════════════════════════════════════════════════

@app.on_message(filters.command("delpost"))
async def cmd_delpost(_, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )

    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote><b>ᴜsᴀɢᴇ:</b> <code>/delpost &lt;id&gt;</code></blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    result = await _posts.delete_one({"post_id": post_id})
    await _schedules.delete_many({"post_id": post_id})

    if result.deleted_count:
        await message.reply_text(
            f"<blockquote>🗑 <b>ᴘᴏsᴛ <code>{post_id}</code> ᴅᴇʟᴇᴛᴇᴅ.</b></blockquote>"
        )
    else:
        await message.reply_text("<blockquote>❌ Post not found.</blockquote>")


# ══════════════════════════════════════════════════════════════
#  /mypost
# ══════════════════════════════════════════════════════════════

@app.on_message(filters.command("mypost"))
async def cmd_mypost(_, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )

    posts = [doc async for doc in _posts.find().sort("post_id", 1)]

    if not posts:
        return await message.reply_text(
            "<blockquote>⚠️ ɴᴏ ᴘᴏsᴛs sᴀᴠᴇᴅ ʏᴇᴛ.</blockquote>"
        )

    lines = ["<blockquote>📋 <b>sᴀᴠᴇᴅ ᴘᴏsᴛs:</b>\n"]
    for doc in posts:
        pid       = doc["post_id"]
        ptype     = doc.get("type", "text")
        btn_count = sum(len(r) for r in doc.get("buttons", []))
        lock      = "🔒" if doc.get("protected") else "🔓"
        lines.append(
            f"• <code>{pid}</code> — <code>{ptype}</code> {lock} — {btn_count} ʙᴛɴ(s)"
        )
    lines.append("</blockquote>")

    await message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="qb_close")
        ]])
    )


# ══════════════════════════════════════════════════════════════
#  /schedulepost <id>
# ══════════════════════════════════════════════════════════════

@app.on_message(filters.command("schedulepost"))
async def cmd_schedulepost(_, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )

    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote><b>ᴜsᴀɢᴇ:</b> <code>/schedulepost &lt;id&gt;</code></blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    data = await _posts.find_one({"post_id": post_id})
    if not data:
        return await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

    user_id = message.from_user.id
    _pending_set(user_id, {
        "step":      "ask_chat",
        "post_id":   post_id,
        "chat_id":   message.chat.id,
        "protected": data.get("protected", False),
    })

    await message.reply_text(
        f"<blockquote>🗓 <b>sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ <code>{post_id}</code></b>\n\n"
        f"<b>sᴛᴇᴘ 1/2:</b> Where should this post be sent?</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📍 ᴛʜɪs ᴄʜᴀᴛ",    callback_data=f"qb_sc_thischat_{post_id}"),
            InlineKeyboardButton("✍️ ᴇɴᴛᴇʀ ᴄʜᴀᴛ ID", callback_data=f"qb_sc_enterchat_{post_id}"),
        ], [
            InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻",      callback_data="qb_close"),
        ]])
    )


# ══════════════════════════════════════════════════════════════
#  /cancelschedule <id>
# ══════════════════════════════════════════════════════════════

@app.on_message(filters.command("cancelschedule"))
async def cmd_cancelschedule(_, message: Message):
    if not _is_owner(message.from_user.id):
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪsᴇᴅ.</blockquote>"
        )

    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote><b>ᴜsᴀɢᴇ:</b> <code>/cancelschedule &lt;id&gt;</code></blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    result = await _schedules.delete_many({"post_id": post_id})
    if result.deleted_count:
        await message.reply_text(
            f"<blockquote>✅ <b>sᴄʜᴇᴅᴜʟᴇ ғᴏʀ ᴘᴏsᴛ <code>{post_id}</code> ᴄᴀɴᴄᴇʟʟᴇᴅ.</b></blockquote>"
        )
    else:
        await message.reply_text(
            f"<blockquote>⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ sᴄʜᴇᴅᴜʟᴇ ғᴏʀ ᴘᴏsᴛ <code>{post_id}</code>.</blockquote>"
        )


# ══════════════════════════════════════════════════════════════
#  CONVERSATION HANDLER
#  Only fires for users who have an active _pending state.
#  Explicit command exclusion prevents any collision with other modules.
# ══════════════════════════════════════════════════════════════

@app.on_message(
    filters.text
    & ~filters.command([
        "createpost", "post", "editpost", "delpost",
        "mypost", "schedulepost", "cancelschedule",
    ])
    & (filters.private | filters.group)
)
async def conversation_handler(_, message: Message):
    _pending_cleanup()   # TTL sweep on every incoming text

    user_id = message.from_user.id if message.from_user else None
    if not user_id or user_id not in _pending:
        return

    state = _pending[user_id]
    step  = state.get("step")

    # ── Step: waiting for custom chat ID ─────────────────────
    if step == "enter_chat":
        raw = message.text.strip()
        try:
            target = int(raw) if raw.lstrip("-").isdigit() else raw
        except Exception:
            return await message.reply_text(
                "<blockquote>❌ Invalid chat ID. Try again or use /cancelschedule.</blockquote>"
            )
        state["target_chat"] = target
        state["step"]        = "ask_hours"
        _pending_set(user_id, state)
        await message.reply_text(
            "<blockquote>🗓 <b>sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ</b>\n\n"
            "<b>sᴛᴇᴘ 2/2:</b> How many <b>hours</b> between each send?\n"
            "<i>(e.g. 1, 6, 24)</i></blockquote>",
            reply_markup=ForceReply(selective=True),
        )
        return

    # ── Step: waiting for interval in hours ──────────────────
    if step == "ask_hours":
        try:
            hours = float(message.text.strip())
            if hours <= 0:
                raise ValueError
        except ValueError:
            return await message.reply_text(
                "<blockquote>❌ Please enter a valid number greater than 0.</blockquote>"
            )

        state       = _pending.pop(user_id, {})
        post_id     = state.get("post_id")
        target_chat = state.get("target_chat", message.chat.id)
        protected   = state.get("protected", False)
        next_send   = datetime.utcnow() + timedelta(hours=hours)

        await _schedules.insert_one({
            "post_id":     post_id,
            "target_chat": target_chat,
            "hours":       hours,
            "protected":   protected,
            "next_send":   next_send,
            "active":      True,
            "running":     False,   # duplicate-send lock flag
        })

        prot_str = "🔒 Protected" if protected else "🔓 Not protected"
        await message.reply_text(
            f"<blockquote>✅ <b>ᴘᴏsᴛ <code>{post_id}</code> sᴄʜᴇᴅᴜʟᴇᴅ!</b>\n\n"
            f"📍 <b>ᴛᴀʀɢᴇᴛ:</b> <code>{target_chat}</code>\n"
            f"⏱ <b>ɪɴᴛᴇʀᴠᴀʟ:</b> every <code>{hours}h</code>\n"
            f"🔐 <b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ:</b> {prot_str}\n"
            f"🕐 <b>ɴᴇxᴛ sᴇɴᴅ:</b> <code>{next_send.strftime('%Y-%m-%d %H:%M')} UTC</code>\n\n"
            f"ᴜsᴇ <code>/cancelschedule {post_id}</code> ᴛᴏ sᴛᴏᴘ.</blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="qb_close")
            ]])
        )
        return


# ══════════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLER
# ══════════════════════════════════════════════════════════════

@app.on_callback_query(filters.regex(r"^qb_"))
async def qb_callbacks(client, cq):
    data    = cq.data
    user_id = cq.from_user.id
    chat_id = cq.message.chat.id

    # ── Close ─────────────────────────────────────────────────
    if data == "qb_close":
        _pending.pop(user_id, None)
        try:
            await cq.message.delete()
        except Exception:
            pass
        return await cq.answer()

    # ── Send now ──────────────────────────────────────────────
    if data.startswith("qb_sendnow_"):
        if not _is_owner(user_id):
            return await cq.answer("❌ Not authorised.", show_alert=True)
        post_id = int(data.split("_")[2])
        db_data = await _posts.find_one({"post_id": post_id})
        if not db_data:
            return await cq.answer("❌ Post not found.", show_alert=True)
        try:
            await _send_post(client, chat_id, db_data, protect=db_data.get("protected", False))
            await cq.answer("✅ Sent!")
        except Exception as e:
            await cq.answer(f"❌ {e}", show_alert=True)
        return

    # ── Schedule shortcut (from createpost menu) ──────────────
    if data.startswith("qb_schedule_"):
        if not _is_owner(user_id):
            return await cq.answer("❌ Not authorised.", show_alert=True)
        post_id = int(data.split("_")[2])
        db_data = await _posts.find_one({"post_id": post_id})
        if not db_data:
            return await cq.answer("❌ Post not found.", show_alert=True)

        _pending_set(user_id, {
            "step":      "ask_chat",
            "post_id":   post_id,
            "chat_id":   chat_id,
            "protected": db_data.get("protected", False),
        })
        await cq.answer()
        await cq.message.edit_text(
            f"<blockquote>🗓 <b>sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ <code>{post_id}</code></b>\n\n"
            f"<b>sᴛᴇᴘ 1/2:</b> Where should this post be sent?</blockquote>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📍 ᴛʜɪs ᴄʜᴀᴛ",    callback_data=f"qb_sc_thischat_{post_id}"),
                InlineKeyboardButton("✍️ ᴇɴᴛᴇʀ ᴄʜᴀᴛ ID", callback_data=f"qb_sc_enterchat_{post_id}"),
            ], [
                InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻",      callback_data="qb_close"),
            ]])
        )
        return

    # ── Delete post ───────────────────────────────────────────
    if data.startswith("qb_del_"):
        if not _is_owner(user_id):
            return await cq.answer("❌ Not authorised.", show_alert=True)
        post_id = int(data.split("_")[2])
        await _posts.delete_one({"post_id": post_id})
        await _schedules.delete_many({"post_id": post_id})
        await cq.answer("🗑 Post deleted.")
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    # ── Schedule: this chat ───────────────────────────────────
    if data.startswith("qb_sc_thischat_"):
        if not _is_owner(user_id):
            return await cq.answer("❌ Not authorised.", show_alert=True)
        post_id = int(data.split("_")[3])
        state   = _pending.get(user_id, {})
        state.update({"target_chat": chat_id, "step": "ask_hours", "post_id": post_id})
        _pending_set(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>🗓 <b>sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ</b>\n\n"
            "<b>sᴛᴇᴘ 2/2:</b> How many <b>hours</b> between each send?\n"
            "<i>(e.g. 1, 6, 24)</i></blockquote>",
        )
        return

    # ── Schedule: enter custom chat ID ────────────────────────
    if data.startswith("qb_sc_enterchat_"):
        if not _is_owner(user_id):
            return await cq.answer("❌ Not authorised.", show_alert=True)
        post_id = int(data.split("_")[3])
        state   = _pending.get(user_id, {"post_id": post_id, "chat_id": chat_id})
        state.update({"step": "enter_chat", "post_id": post_id})
        _pending_set(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>🗓 <b>sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ</b>\n\n"
            "<b>sᴛᴇᴘ 1/2:</b> Send me the <b>chat ID</b> or <b>@username</b> "
            "where this post should be scheduled.</blockquote>",
        )
        return

    await cq.answer()


# ══════════════════════════════════════════════════════════════
#  BACKGROUND SCHEDULER LOOP
#  • Ticks every 60 s
#  • `running` flag prevents duplicate sends across restarts
#  • Atomic check-and-set via update_one with filter {"running": False}
#  • Clears stale _pending entries each tick
# ══════════════════════════════════════════════════════════════

async def _scheduler_loop():
    await _create_indexes()
    await asyncio.sleep(10)
    logger.info("QualityButton scheduler started.")

    while True:
        _pending_cleanup()

        try:
            now    = datetime.utcnow()
            cursor = _schedules.find({
                "active":    True,
                "running":   False,
                "next_send": {"$lte": now},
            })

            async for sched in cursor:
                sched_id    = sched["_id"]
                post_id     = sched["post_id"]
                target_chat = sched["target_chat"]
                protected   = sched.get("protected", False)
                hours       = sched.get("hours", 24)

                # Atomic lock acquisition — skip if another worker got it
                lock = await _schedules.update_one(
                    {"_id": sched_id, "running": False},
                    {"$set": {"running": True}},
                )
                if lock.modified_count == 0:
                    continue

                post_data = await _posts.find_one({"post_id": post_id})
                if not post_data:
                    await _schedules.delete_one({"_id": sched_id})
                    continue

                try:
                    await _send_post(app, target_chat, post_data, protect=protected)
                    logger.info("Scheduled post %s sent to %s", post_id, target_chat)
                except Exception as e:
                    logger.warning("Schedule send failed (post %s): %s", post_id, e)

                next_send = datetime.utcnow() + timedelta(hours=hours)
                await _schedules.update_one(
                    {"_id": sched_id},
                    {"$set": {"next_send": next_send, "running": False}},
                )

        except Exception as e:
            logger.error("Scheduler loop error: %s", e)

        await asyncio.sleep(60)


# Attach scheduler to the running event loop safely
asyncio.ensure_future(_scheduler_loop())


# ══════════════════════════════════════════════════════════════
#  MODULE METADATA
# ══════════════════════════════════════════════════════════════

__menu__     = "CMD_PRO"
__mod_name__ = "H_B_84"
__help__ = """
<b>ᴘᴏsᴛ sʏsᴛᴇᴍ</b>
🔻 <code>/createpost</code> <i>(reply)</i> ➠ sᴀᴠᴇ ᴀ ɴᴇᴡ ᴘᴏsᴛ
🔻 <code>/post &lt;id&gt;</code> ➠ sᴇɴᴅ ᴘᴏsᴛ ʜᴇʀᴇ
🔻 <code>/post &lt;id&gt; -100xxx</code> ➠ sᴇɴᴅ ᴛᴏ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ
🔻 <code>/editpost &lt;id&gt;</code> <i>(reply)</i> ➠ ʀᴇᴘʟᴀᴄᴇ ᴘᴏsᴛ ᴄᴏɴᴛᴇɴᴛ
🔻 <code>/delpost &lt;id&gt;</code> ➠ ᴅᴇʟᴇᴛᴇ ᴀ sᴀᴠᴇᴅ ᴘᴏsᴛ
🔻 <code>/mypost</code> ➠ ʟɪsᴛ ᴀʟʟ sᴀᴠᴇᴅ ᴘᴏsᴛs
<b>sᴄʜᴇᴅᴜʟᴇʀ:</b>
🔻 <code>/schedulepost &lt;id&gt;</code> ➠ sᴄʜᴇᴅᴜʟᴇ ᴀ ᴘᴏsᴛ (ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ)
🔻 <code>/cancelschedule &lt;id&gt;</code> ➠ sᴛᴏᴘ ᴀ sᴄʜᴇᴅᴜʟᴇᴅ ᴘᴏsᴛ
<b>ʙᴜᴛᴛᴏɴ ғᴏʀᴍᴀᴛ</b> <i>(ɪɴ ᴛᴇxᴛ/ᴄᴀᴘᴛɪᴏɴ)</i>:
<code>[Button1](https://example.com) [Button2](https://example.com)</code>
<code>[Button3](https://example.com)</code>
"""
