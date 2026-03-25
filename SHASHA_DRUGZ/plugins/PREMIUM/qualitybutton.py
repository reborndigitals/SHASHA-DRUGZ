# SHASHA_DRUGZ/plugins/PREMIUM/qualitybutton.py
# ══════════════════════════════════════════════════════════════
#  Quality Button Post System — SHASHA_DRUGZ Plugin
#
#  FEATURES:
#    • Create posts from replied message (text/photo/video/animation/document)
#    • Inline buttons via [Text](url) syntax
#    • Edit saved post content + buttons (/editpost)
#    • Delete saved post (/delpost)
#    • Send post to current chat or any group/channel (/post <id> [chat_id])
#    • Auto scheduler — asks interval (hours) before scheduling
#    • Protected posts — no forward / no save (ask after scheduler prompt)
#    • All posts stored in MongoDB with full metadata
#
#  COMMANDS:
#    /createpost          → reply to any message to save it as a post
#    /post <id> [chat]    → send post here or to another chat_id / @username
#    /editpost <id>       → reply to new content to replace saved post
#    /delpost <id>        → delete saved post from DB
#    /mypost              → list all saved post IDs
#    /schedulepost <id>   → interactive scheduler (asks hours + protection)
#    /cancelschedule <id> → cancel a pending scheduled post
#
#  BUTTON FORMAT  (inside post text/caption):
#    [Button Text](https://example.com)
#    Two buttons per row — third wraps to next row automatically.
#
#  SCHEDULER:
#    Bot asks: "How many hours between sends?" → then asks protected yes/no.
#    Stores schedule in DB; background loop fires every minute.
#
#  PROTECTED MODE:
#    Sends post with protect_content=True (Telegram no-forward flag).
#
#  COLLECTIONS:
#    post_data       — saved posts
#    post_schedules  — active schedules
# ══════════════════════════════════════════════════════════════
import re
import asyncio
import logging
from datetime import datetime, timedelta

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)
from pyrogram.errors import ChatAdminRequired, PeerIdInvalid, ChannelPrivate

from SHASHA_DRUGZ import app, mongo

logger = logging.getLogger("QualityButton")

# ── MongoDB ───────────────────────────────────────────────────────────────────
_db       = mongo["POST_SYSTEM"]
_posts    = _db["post_data"]        # saved posts
_schedules = _db["post_schedules"]  # active schedules

# ── Conversation state (in-memory, per user) ──────────────────────────────────
# Key: user_id  →  dict with pending action info
_pending: dict = {}

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
async def _next_id() -> int:
    last = await _posts.find_one(sort=[("post_id", -1)])
    return (last["post_id"] + 1) if last else 1

def _parse_buttons(text: str):
    """
    Parse buttons from text where each LINE becomes one ROW.
    Any number of [Label](url) on one line = that many buttons in that row.

    Example input (in post caption):
        [Btn1](url) [Btn2](url)
        [Btn3](url)
        [Btn4](url) [Btn5](url) [Btn6](url)

    → Row 1: Btn1, Btn2
    → Row 2: Btn3
    → Row 3: Btn4, Btn5, Btn6

    Lines with no buttons are kept as text content.
    """
    btn_pattern = r"\[(.*?)\]\((https?://\S+?)\)"
    rows = []
    clean_lines = []

    for line in text.splitlines():
        matches = re.findall(btn_pattern, line)
        if matches:
            rows.append([InlineKeyboardButton(name, url=url) for name, url in matches])
            # Remove button syntax from this line; if nothing left, skip it
            leftover = re.sub(btn_pattern, "", line).strip()
            if leftover:
                clean_lines.append(leftover)
        else:
            clean_lines.append(line)

    clean = "\n".join(clean_lines).strip()
    return clean, rows

def _build_markup(raw_buttons: list) -> InlineKeyboardMarkup | None:
    """Rebuild InlineKeyboardMarkup from stored list-of-lists-of-dicts."""
    if not raw_buttons:
        return None
    rows = [
        [InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
        for row in raw_buttons
    ]
    return InlineKeyboardMarkup(rows) if rows else None

def _serialize_buttons(button_rows: list) -> list:
    """Convert list[list[InlineKeyboardButton]] → list[list[dict]] for DB."""
    return [
        [{"text": b.text, "url": b.url} for b in row]
        for row in button_rows
    ]

def _extract_media(msg: Message) -> tuple[str, str | None]:
    """Return (media_type, file_id) from a Pyrogram message."""
    if msg.photo:
        return "photo", msg.photo.file_id
    if msg.animation:
        return "animation", msg.animation.file_id
    if msg.video:
        return "video", msg.video.file_id
    if msg.document:
        return "document", msg.document.file_id
    return "text", None

async def _send_post(client, chat_id, data: dict, protect: bool = False):
    """Send a post dict to any chat_id. Raises on failure."""
    text    = data.get("text", "")
    markup  = _build_markup(data.get("buttons", []))
    pmode   = data.get("parse_mode", "html")
    fid     = data.get("file_id")
    ptype   = data.get("type", "text")
    kwargs  = dict(
        caption=text,
        reply_markup=markup,
        parse_mode=pmode,
        protect_content=protect,
    )
    if ptype == "photo":
        await client.send_photo(chat_id, fid, **kwargs)
    elif ptype == "animation":
        await client.send_animation(chat_id, fid, **kwargs)
    elif ptype == "video":
        await client.send_video(chat_id, fid, **kwargs)
    elif ptype == "document":
        await client.send_document(chat_id, fid, **kwargs)
    else:
        await client.send_message(
            chat_id, text,
            reply_markup=markup,
            parse_mode=pmode,
            disable_web_page_preview=False,
            protect_content=protect,
        )

# ══════════════════════════════════════════════════════════════
#  /createpost — save a post from replied message
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("createpost") & filters.private | filters.command("createpost") & filters.group)
async def cmd_createpost(_, message: Message):
    if not message.reply_to_message:
        return await message.reply_text(
            "<blockquote>❌ **ᴜsᴀɢᴇ:** Reply to a message and use `/createpost`.</blockquote>"
        )

    msg  = message.reply_to_message
    text = msg.text or msg.caption or ""

    if msg.sticker:
        return await message.reply_text("<blockquote>❌ Stickers are not supported.</blockquote>")

    clean_text, buttons = _parse_buttons(text)
    ptype, fid          = _extract_media(msg)
    post_id             = await _next_id()

    doc = {
        "post_id":    post_id,
        "text":       clean_text,
        "buttons":    _serialize_buttons(buttons),
        "parse_mode": "html",
        "type":       ptype,
        "file_id":    fid,
        "protected":  False,
        "created_by": message.from_user.id,
        "created_at": datetime.utcnow(),
    }
    await _posts.insert_one(doc)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 sᴇɴᴅ ɴᴏᴡ",     callback_data=f"qb_sendnow_{post_id}"),
        InlineKeyboardButton("🗓 sᴄʜᴇᴅᴜʟᴇ",      callback_data=f"qb_schedule_{post_id}"),
    ], [
        InlineKeyboardButton("🗑 ᴅᴇʟᴇᴛᴇ ᴘᴏsᴛ",  callback_data=f"qb_del_{post_id}"),
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",       callback_data="qb_close"),
    ]])
    await message.reply_text(
        f"<blockquote>✅ **ᴘᴏsᴛ sᴀᴠᴇᴅ!**\n\n"
        f"🆔 **ᴘᴏsᴛ ID:** `{post_id}`\n"
        f"📁 **ᴛʏᴘᴇ:** `{ptype}`\n"
        f"🔘 **ʙᴜᴛᴛᴏɴs:** `{sum(len(r) for r in buttons)}`\n\n"
        f"ᴜsᴇ `/post {post_id}` ᴛᴏ sᴇɴᴅ ɪᴛ.</blockquote>",
        reply_markup=kb,
    )

# ══════════════════════════════════════════════════════════════
#  /post <id> [chat_id] — send post here or to another chat
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("post"))
async def cmd_post(client, message: Message):
    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:**\n"
            "`/post <id>` — send here\n"
            "`/post <id> -100xxxxxxxxxx` — send to channel/group</blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    data = await _posts.find_one({"post_id": post_id})
    if not data:
        return await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

    # Target chat: argument or current chat
    if len(args) >= 3:
        raw = args[2]
        try:
            target_chat = int(raw) if raw.lstrip("-").isdigit() else raw
        except Exception:
            return await message.reply_text("<blockquote>❌ Invalid chat ID / username.</blockquote>")
    else:
        target_chat = message.chat.id

    protect = data.get("protected", False)

    try:
        await _send_post(client, target_chat, data, protect=protect)
        if target_chat != message.chat.id:
            await message.reply_text(
                f"<blockquote>✅ **ᴘᴏsᴛ `{post_id}` sᴇɴᴛ** ᴛᴏ `{target_chat}`!</blockquote>"
            )
    except ChatAdminRequired:
        await message.reply_text("<blockquote>❌ I'm not an admin in that chat.</blockquote>")
    except (PeerIdInvalid, ChannelPrivate):
        await message.reply_text("<blockquote>❌ Chat not found or I'm not a member.</blockquote>")
    except Exception as e:
        await message.reply_text(f"<blockquote>❌ Failed: `{e}`</blockquote>")

# ══════════════════════════════════════════════════════════════
#  /editpost <id> — reply to new content to replace post
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("editpost"))
async def cmd_editpost(_, message: Message):
    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** Reply to new content + `/editpost <id>`</blockquote>"
        )

    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    data = await _posts.find_one({"post_id": post_id})
    if not data:
        return await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

    if not message.reply_to_message:
        return await message.reply_text(
            "<blockquote>❌ Reply to the **new content** you want to replace this post with.</blockquote>"
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
        f"<blockquote>✅ **ᴘᴏsᴛ `{post_id}` ᴜᴘᴅᴀᴛᴇᴅ!**\n\n"
        f"📁 **ɴᴇᴡ ᴛʏᴘᴇ:** `{ptype}`\n"
        f"🔘 **ʙᴜᴛᴛᴏɴs:** `{sum(len(r) for r in buttons)}`</blockquote>"
    )

# ══════════════════════════════════════════════════════════════
#  /delpost <id> — delete a saved post
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("delpost"))
async def cmd_delpost(_, message: Message):
    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/delpost <id>`</blockquote>"
        )
    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    result = await _posts.delete_one({"post_id": post_id})
    # also remove any schedules for this post
    await _schedules.delete_many({"post_id": post_id})

    if result.deleted_count:
        await message.reply_text(
            f"<blockquote>🗑 **ᴘᴏsᴛ `{post_id}` ᴅᴇʟᴇᴛᴇᴅ.**</blockquote>"
        )
    else:
        await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

# ══════════════════════════════════════════════════════════════
#  /mypost — list all saved posts
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("mypost"))
async def cmd_mypost(_, message: Message):
    cursor = _posts.find().sort("post_id", 1)
    posts  = [doc async for doc in cursor]

    if not posts:
        return await message.reply_text(
            "<blockquote>⚠️ ɴᴏ ᴘᴏsᴛs sᴀᴠᴇᴅ ʏᴇᴛ.</blockquote>"
        )

    lines = ["<blockquote>📋 **sᴀᴠᴇᴅ ᴘᴏsᴛs:**\n"]
    for doc in posts:
        pid      = doc["post_id"]
        ptype    = doc.get("type", "text")
        buttons  = sum(len(r) for r in doc.get("buttons", []))
        protected = "🔒" if doc.get("protected") else "🔓"
        lines.append(f"• `{pid}` — `{ptype}` {protected} — {buttons} ʙᴛɴ(s)")
    lines.append("</blockquote>")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="qb_close")
    ]])
    await message.reply_text("\n".join(lines), reply_markup=kb)

# ══════════════════════════════════════════════════════════════
#  /schedulepost <id> — interactive scheduler
#  Step 1: ask target chat
#  Step 2: ask interval (hours)
#  Step 3: ask protected yes/no
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("schedulepost"))
async def cmd_schedulepost(_, message: Message):
    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/schedulepost <id>`</blockquote>"
        )
    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    data = await _posts.find_one({"post_id": post_id})
    if not data:
        return await message.reply_text("<blockquote>❌ Post not found.</blockquote>")

    user_id = message.from_user.id
    _pending[user_id] = {
        "step":        "ask_chat",
        "post_id":     post_id,
        "chat_id":     message.chat.id,
        "protected":   data.get("protected", False),
    }
    # Only YES button — tapping it moves to hours step
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📍 ᴛʜɪs ᴄʜᴀᴛ",      callback_data=f"qb_sc_thischat_{post_id}"),
        InlineKeyboardButton("✍️ ᴇɴᴛᴇʀ ᴄʜᴀᴛ ID",   callback_data=f"qb_sc_enterchat_{post_id}"),
    ], [
        InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻",        callback_data="qb_close"),
    ]])
    await message.reply_text(
        f"<blockquote>🗓 **sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ `{post_id}`**\n\n"
        f"**sᴛᴇᴘ 1/2:** Where should this post be sent?</blockquote>",
        reply_markup=kb,
    )

# ══════════════════════════════════════════════════════════════
#  /cancelschedule <id> — cancel an active schedule
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.command("cancelschedule"))
async def cmd_cancelschedule(_, message: Message):
    args = message.command
    if len(args) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/cancelschedule <id>`</blockquote>"
        )
    try:
        post_id = int(args[1])
    except ValueError:
        return await message.reply_text("<blockquote>❌ Invalid post ID.</blockquote>")

    result = await _schedules.delete_many({"post_id": post_id})
    if result.deleted_count:
        await message.reply_text(
            f"<blockquote>✅ **sᴄʜᴇᴅᴜʟᴇ ғᴏʀ ᴘᴏsᴛ `{post_id}` ᴄᴀɴᴄᴇʟʟᴇᴅ.**</blockquote>"
        )
    else:
        await message.reply_text(
            f"<blockquote>⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ sᴄʜᴇᴅᴜʟᴇ ғᴏʀ ᴘᴏsᴛ `{post_id}`.</blockquote>"
        )

# ══════════════════════════════════════════════════════════════
#  CONVERSATION HANDLER — captures plain-text replies for
#  scheduler steps (chat ID entry, hours entry)
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.text & ~filters.command(None) & (filters.private | filters.group))
async def conversation_handler(_, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id or user_id not in _pending:
        return

    state = _pending[user_id]
    step  = state.get("step")

    # ── Step: user entered a custom chat ID ──────────────────
    if step == "enter_chat":
        raw = message.text.strip()
        try:
            target = int(raw) if raw.lstrip("-").isdigit() else raw
        except Exception:
            return await message.reply_text(
                "<blockquote>❌ Invalid chat ID. Try again or /cancelschedule.</blockquote>"
            )
        state["target_chat"] = target
        state["step"]        = "ask_hours"
        _pending[user_id]    = state
        await message.reply_text(
            "<blockquote>🗓 **sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ**\n\n"
            "**sᴛᴇᴘ 2/2:** How many **hours** between each send?\n"
            "_(e.g. `1`, `6`, `24`)_</blockquote>",
            reply_markup=ForceReply(selective=True),
        )
        return

    # ── Step: user entered hours → confirm & save schedule ───
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
        })

        prot_str = "🔒 Protected" if protected else "🔓 Not protected"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="qb_close")
        ]])
        await message.reply_text(
            f"<blockquote>✅ **ᴘᴏsᴛ `{post_id}` sᴄʜᴇᴅᴜʟᴇᴅ!**\n\n"
            f"📍 **ᴛᴀʀɢᴇᴛ:** `{target_chat}`\n"
            f"⏱ **ɪɴᴛᴇʀᴠᴀʟ:** every `{hours}h`\n"
            f"🔐 **ᴘʀᴏᴛᴇᴄᴛɪᴏɴ:** {prot_str}\n"
            f"🕐 **ɴᴇxᴛ sᴇɴᴅ:** `{next_send.strftime('%Y-%m-%d %H:%M')} UTC`\n\n"
            f"ᴜsᴇ `/cancelschedule {post_id}` ᴛᴏ sᴛᴏᴘ.</blockquote>",
            reply_markup=kb,
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

    # ── Send now (from createpost menu) ───────────────────────
    if data.startswith("qb_sendnow_"):
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

    # ── Delete post (from createpost menu) ────────────────────
    if data.startswith("qb_del_"):
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
        post_id = int(data.split("_")[3])
        state   = _pending.get(user_id, {})
        state["target_chat"] = chat_id
        state["step"]        = "ask_hours"
        state["post_id"]     = post_id
        _pending[user_id]    = state
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>🗓 **sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ**\n\n"
            "**sᴛᴇᴘ 2/2:** How many **hours** between each send?\n"
            "_(e.g. `1`, `6`, `24`)_</blockquote>",
        )
        return

    # ── Schedule: enter custom chat ID ───────────────────────
    if data.startswith("qb_sc_enterchat_"):
        post_id = int(data.split("_")[3])
        state   = _pending.get(user_id, {"post_id": post_id, "chat_id": chat_id})
        state["step"]    = "enter_chat"
        state["post_id"] = post_id
        _pending[user_id] = state
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>🗓 **sᴄʜᴇᴅᴜʟᴇ ᴘᴏsᴛ**\n\n"
            "**sᴛᴇᴘ 1/2:** Send me the **chat ID** or **@username** "
            "where this post should be scheduled.</blockquote>",
        )
        return


    await cq.answer()

# ══════════════════════════════════════════════════════════════
#  BACKGROUND SCHEDULER LOOP
#  Checks every 60 seconds for due schedules and fires them.
# ══════════════════════════════════════════════════════════════
async def _scheduler_loop():
    await asyncio.sleep(10)  # brief startup delay
    logger.info("QualityButton scheduler started.")
    while True:
        try:
            now     = datetime.utcnow()
            cursor  = _schedules.find({"active": True, "next_send": {"$lte": now}})
            async for sched in cursor:
                post_id     = sched["post_id"]
                target_chat = sched["target_chat"]
                protected   = sched.get("protected", False)
                hours       = sched.get("hours", 24)

                post_data = await _posts.find_one({"post_id": post_id})
                if not post_data:
                    # Post deleted — remove schedule
                    await _schedules.delete_one({"_id": sched["_id"]})
                    continue

                try:
                    await _send_post(app, target_chat, post_data, protect=protected)
                    logger.info("Scheduled post %s sent to %s", post_id, target_chat)
                except Exception as e:
                    logger.warning("Schedule send failed (post %s): %s", post_id, e)

                # Update next send time
                next_send = datetime.utcnow() + timedelta(hours=hours)
                await _schedules.update_one(
                    {"_id": sched["_id"]},
                    {"$set": {"next_send": next_send}},
                )
        except Exception as e:
            logger.error("Scheduler loop error: %s", e)

        await asyncio.sleep(60)

# Kick off scheduler as a background task when module loads
asyncio.get_event_loop().create_task(_scheduler_loop())

# ══════════════════════════════════════════════════════════════
#  MODULE METADATA
# ══════════════════════════════════════════════════════════════
__menu__     = "CMD_PRO"
__mod_name__ = "H_B_84"
__help__ = """
**ᴘᴏsᴛ sʏsᴛᴇᴍ**

🔻 `/createpost` _(reply)_ ➠ sᴀᴠᴇ ᴀ ɴᴇᴡ ᴘᴏsᴛ
🔻 `/post <id>` ➠ sᴇɴᴅ ᴘᴏsᴛ ʜᴇʀᴇ
🔻 `/post <id> -100xxx` ➠ sᴇɴᴅ ᴛᴏ ᴄʜᴀɴɴᴇʟ / ɢʀᴏᴜᴘ
🔻 `/editpost <id>` _(reply)_ ➠ ʀᴇᴘʟᴀᴄᴇ ᴘᴏsᴛ ᴄᴏɴᴛᴇɴᴛ
🔻 `/delpost <id>` ➠ ᴅᴇʟᴇᴛᴇ ᴀ sᴀᴠᴇᴅ ᴘᴏsᴛ
🔻 `/mypost` ➠ ʟɪsᴛ ᴀʟʟ sᴀᴠᴇᴅ ᴘᴏsᴛs

**sᴄʜᴇᴅᴜʟᴇʀ:**
🔻 `/schedulepost <id>` ➠ sᴄʜᴇᴅᴜʟᴇ ᴀ ᴘᴏsᴛ (ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ)
🔻 `/cancelschedule <id>` ➠ sᴛᴏᴘ ᴀ sᴄʜᴇᴅᴜʟᴇᴅ ᴘᴏsᴛ

**ʙᴜᴛᴛᴏɴ ғᴏʀᴍᴀᴛ _(ɪɴ ᴛᴇxᴛ/ᴄᴀᴘᴛɪᴏɴ)_:**
`[Button1 Text](https://example.com)[Button2 Text](https://example.com)`
`[Button3 Text](https://example.com)`

**ɴᴏᴛᴇs:**
• Protected posts = no forward / no save
• Scheduler runs every 60 seconds
• Supports: text, photo, video, GIF, document
"""
