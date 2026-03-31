# ╔══════════════════════════════════════════════════════════════╗
# ║   SHASHA_DRUGZ — Approval + CleanService + AntiFlood Module  ║
# ║   Enhanced Single-file Pyrogram Module (MongoDB required)    ║
# ╚══════════════════════════════════════════════════════════════╝
import time
from pyrogram import filters
from pyrogram.types import Message, ChatPermissions
from pyrogram.enums import ChatMemberStatus
from collections import defaultdict
from config import MONGO_DB_URI, BANNED_USERS
from motor.motor_asyncio import AsyncIOMotorClient
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
# ─── MongoDB Setup ───────────────────────────────────────────────────────────
mongo    = AsyncIOMotorClient(MONGO_DB_URI)
_db      = mongo["SHASHA_DRUGZ"]
approval_col  = _db["approval"]
settings_col  = _db["settings"]
flood_col     = _db["flood"]
# ─── In-memory flood tracker ─────────────────────────────────────────────────
_flood_cache: dict[tuple, list] = defaultdict(list)
# ═════════════════════════════════════════════════════════════════════════════
# HELPERS — Admin check
# ═════════════════════════════════════════════════════════════════════════════
async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False
# ═════════════════════════════════════════════════════════════════════════════
# ✅  APPROVAL SYSTEM
# ═════════════════════════════════════════════════════════════════════════════
# ── DB helpers ────────────────────────────────────────────────────────────────
async def _is_approved(chat_id: int, user_id: int) -> bool:
    return bool(await approval_col.find_one({"chat_id": chat_id, "user_id": user_id}))
async def _is_approval_on(chat_id: int) -> bool:
    data = await settings_col.find_one({"chat_id": chat_id})
    return bool(data and data.get("approval", False))
# ── /approval on | off ────────────────────────────────────────────────────────
@app.on_message(filters.command("approval") & filters.group & ~BANNED_USERS)
async def toggle_approval(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")
    if len(message.command) < 2:
        state = await _is_approval_on(message.chat.id)
        status = "**ON** ✅" if state else "**OFF** ❌"
        return await message.reply_text(f"**» Approval Mode:** {status}")
    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/approval on` or `/approval off`")
    enabled = arg == "on"
    await settings_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"approval": enabled}},
        upsert=True,
    )
    if enabled:
        await message.reply_text(
            "**» Approval Mode: ON ✅**\n\n"
            "Only approved users can send messages.\n"
            "Use /approve (reply) to approve someone."
        )
    else:
        await message.reply_text("**» Approval Mode: OFF ❌**\n\nAll users can send messages freely.")
# ── /approve ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("approve") & filters.group & ~BANNED_USERS)
async def approve_user(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can approve users.**")
    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» Could not find that user.**")
    if not user:
        return await message.reply_text("**» Reply to a user or provide a username/ID.**")
    if await _is_approved(message.chat.id, user.id):
        return await message.reply_text(f"**» {user.mention} is already approved.**")
    await approval_col.update_one(
        {"chat_id": message.chat.id, "user_id": user.id},
        {"$set": {"name": user.first_name}},
        upsert=True,
    )
    await message.reply_text(
        f"**» ✅ Approved:** {user.mention}\n"
        f"They can now send messages freely."
    )
# ── /unapprove ────────────────────────────────────────────────────────────────
@app.on_message(filters.command("unapprove") & filters.group & ~BANNED_USERS)
async def unapprove_user(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can unapprove users.**")
    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» Could not find that user.**")
    if not user:
        return await message.reply_text("**» Reply to a user or provide a username/ID.**")
    result = await approval_col.delete_one({"chat_id": message.chat.id, "user_id": user.id})
    if result.deleted_count:
        await message.reply_text(f"**» ❌ Unapproved:** {user.mention}")
    else:
        await message.reply_text(f"**» {user.mention} was not approved.**")
# ── /approved ─────────────────────────────────────────────────────────────────
@app.on_message(filters.command("approved") & filters.group & ~BANNED_USERS)
async def list_approved(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can view approved users.**")
    entries = []
    async for doc in approval_col.find({"chat_id": message.chat.id}):
        entries.append(doc)
    if not entries:
        return await message.reply_text("**» No approved users in this group.**")
    lines = ["**» ✅ Approved Users:**\n"]
    for i, doc in enumerate(entries, 1):
        uid  = doc["user_id"]
        name = doc.get("name", "Unknown")
        lines.append(f"**{i}.** [{name}](tg://user?id={uid}) — `{uid}`")
    await message.reply_text(
        "\n".join(lines),
        disable_web_page_preview=True,
    )
# ── Enforcement: delete messages from unapproved users ───────────────────────
# FIX: Added ~filters.command so commands are never blocked by approval enforcement
@app.on_message(filters.group & ~filters.service & ~filters.command & ~BANNED_USERS)
async def enforce_approval(client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    # Extra safety: never block command messages
    if message.text and message.text.startswith("/"):
        return
    if not await _is_approval_on(message.chat.id):
        return
    if await _is_admin(client, message.chat.id, message.from_user.id):
        return
    if await _is_approved(message.chat.id, message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
# ═════════════════════════════════════════════════════════════════════════════
# 🧹  CLEAN SERVICE
# ═════════════════════════════════════════════════════════════════════════════
async def _is_cleanservice_on(chat_id: int) -> bool:
    data = await settings_col.find_one({"chat_id": chat_id})
    return bool(data and data.get("cleanservice", False))
# ── /cleanservice on | off ────────────────────────────────────────────────────
@app.on_message(filters.command("cleanservice") & filters.group & ~BANNED_USERS)
async def cleanservice_toggle(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")
    if len(message.command) < 2:
        state = await _is_cleanservice_on(message.chat.id)
        status = "**ON** 🧹" if state else "**OFF** ❌"
        return await message.reply_text(f"**» Clean Service:** {status}")
    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/cleanservice on` or `/cleanservice off`")
    enabled = arg == "on"
    await settings_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"cleanservice": enabled}},
        upsert=True,
    )
    if enabled:
        await message.reply_text(
            "**» 🧹 Clean Service: ON**\n\n"
            "Join / leave messages will be auto-deleted."
        )
    else:
        await message.reply_text("**» ❌ Clean Service: OFF**\n\nJoin / leave messages will be visible.")
# ── Auto-delete join messages ─────────────────────────────────────────────────
@app.on_message(filters.new_chat_members)
async def auto_delete_join(client, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass
# ── Auto-delete leave messages ────────────────────────────────────────────────
@app.on_message(filters.left_chat_member)
async def auto_delete_leave(client, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass
# ═════════════════════════════════════════════════════════════════════════════
# ⚙️  ANTI-FLOOD SYSTEM
# ═════════════════════════════════════════════════════════════════════════════
# ── DB helpers ────────────────────────────────────────────────────────────────
async def _get_flood_settings(chat_id: int) -> tuple[int | None, bool]:
    data = await flood_col.find_one({"chat_id": chat_id})
    if data:
        return data.get("limit"), data.get("enabled", False)
    return None, False
# ── /antiflood <number> ───────────────────────────────────────────────────────
@app.on_message(filters.command("antiflood") & filters.group & ~BANNED_USERS)
async def set_antiflood(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")
    if len(message.command) < 2:
        limit, enabled = await _get_flood_settings(message.chat.id)
        status = "**ON** ✅" if enabled else "**OFF** ❌"
        lim_text = str(limit) if limit else "Not set"
        return await message.reply_text(
            f"**» Flood Protection:** {status}\n"
            f"**» Message Limit:** `{lim_text}` per 10 sec"
        )
    try:
        limit = int(message.command[1])
        if limit < 1:
            raise ValueError
    except ValueError:
        return await message.reply_text("**» Provide a valid number greater than 0.**\nExample: `/antiflood 5`")
    await flood_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"limit": limit}},
        upsert=True,
    )
    await message.reply_text(
        f"**» ⚙️ Flood limit set to `{limit}` messages per 10 seconds.**\n"
        f"Use `/flood on` to activate protection."
    )
# ── /flood on | off ───────────────────────────────────────────────────────────
@app.on_message(filters.command("flood") & filters.group & ~BANNED_USERS)
async def toggle_flood(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")
    if len(message.command) < 2:
        _, enabled = await _get_flood_settings(message.chat.id)
        status = "**ON** ✅" if enabled else "**OFF** ❌"
        return await message.reply_text(f"**» Flood Protection:** {status}")
    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/flood on` or `/flood off`")
    enabled = arg == "on"
    limit, _ = await _get_flood_settings(message.chat.id)
    if enabled and not limit:
        return await message.reply_text(
            "**» Set a flood limit first.**\nExample: `/antiflood 5`"
        )
    await flood_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"enabled": enabled}},
        upsert=True,
    )
    if enabled:
        await message.reply_text(
            f"**» ✅ Flood Protection: ON**\n"
            f"Users sending more than `{limit}` messages in 10 seconds will be restricted."
        )
    else:
        await message.reply_text("**» ❌ Flood Protection: OFF**")
# ── Flood checker (runs on every group message) ───────────────────────────────
# FIX: Added ~filters.command so commands are never counted or blocked by flood checker
@app.on_message(filters.group & ~filters.service & ~filters.command & ~BANNED_USERS)
async def flood_checker(client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    # Extra safety: never count or block command messages
    if message.text and message.text.startswith("/"):
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    limit, enabled = await _get_flood_settings(chat_id)
    if not enabled or not limit:
        return
    # Admins are immune
    if await _is_admin(client, chat_id, user_id):
        return
    now = time.time()
    key = (chat_id, user_id)
    _flood_cache[key] = [t for t in _flood_cache[key] if now - t < 10]
    _flood_cache[key].append(now)
    if len(_flood_cache[key]) > limit:
        try:
            await message.delete()
        except Exception:
            pass
        # Mute the user for 60 seconds as punishment
        try:
            await client.restrict_chat_member(
                chat_id,
                user_id,
                ChatPermissions(can_send_messages=False),
                until_date=int(now) + 60,
            )
            warn = await message.reply_text(
                f"**» ⚠️ {message.from_user.mention} has been muted for 60 seconds due to flooding.**"
            )
            # Clear their cache so re-mute isn't triggered every message
            _flood_cache[key] = []
        except Exception:
            pass
# ─────────────────────────────────────────────────────────────────────────────
# Help text
# ─────────────────────────────────────────────────────────────────────────────
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_89"
__help__ = """
🔻 /approval on — ᴇɴᴀʙʟᴇ ᴀᴘᴘʀᴏᴠᴀʟ ᴍᴏᴅᴇ
🔻 /approval off — ᴅɪsᴀʙʟᴇ ᴀᴘᴘʀᴏᴠᴀʟ ᴍᴏᴅᴇ
🔻 /approve — ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴛᴏ ᴀᴘᴘʀᴏᴠᴇ ᴛʜᴇᴍ
🔻 /unapprove — ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴛᴏ ᴜɴᴀᴘᴘʀᴏᴠᴇ ᴛʜᴇᴍ
🔻 /approved — ʟɪsᴛ ᴀʟʟ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜsᴇʀs
🧹 **CLEAN SERVICE**
🔻 /cleanservice on — ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ ᴊᴏɪɴ/ʟᴇᴀᴠᴇ ᴍᴇssᴀɢᴇs
🔻 /cleanservice off — sʜᴏᴡ ᴊᴏɪɴ/ʟᴇᴀᴠᴇ ᴍᴇssᴀɢᴇs
⚙️ **ANTI-FLOOD**
🔻 /antiflood <number> — sᴇᴛ ᴍᴇssᴀɢᴇ ғʟᴏᴏᴅ ʟɪᴍɪᴛ (ᴘᴇʀ 10 sᴇᴄ)
🔻 /flood on — ᴇɴᴀʙʟᴇ ғʟᴏᴏᴅ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ
🔻 /flood off — ᴅɪsᴀʙʟᴇ ғʟᴏᴏᴅ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ
"""
