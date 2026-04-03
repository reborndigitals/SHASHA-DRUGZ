#warns.py
# ╔══════════════════════════════════════════════════════════════╗
# ║             SHASHA_DRUGZ — Warn System Module                ║
# ║     Enhanced Single-file Pyrogram Module (MongoDB)           ║
# ╚══════════════════════════════════════════════════════════════╝

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)
from pyrogram.enums import ChatMemberStatus
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB_URI, BANNED_USERS
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
# ─── MongoDB Setup ────────────────────────────────────────────────────────────
_mongo       = AsyncIOMotorClient(MONGO_DB_URI)
_db          = _mongo["SHASHA_DRUGZ"]
warn_col     = _db["warns"]
settings_col = _db["warn_settings"]
# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
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
async def _get_warns(chat_id: int, user_id: int) -> int:
    data = await warn_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return data["count"] if data else 0
async def _add_warn(chat_id: int, user_id: int):
    await warn_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
    )
async def _reset_warn(chat_id: int, user_id: int):
    await warn_col.delete_one({"chat_id": chat_id, "user_id": user_id})
async def _get_warn_limit(chat_id: int) -> int:
    data = await settings_col.find_one({"chat_id": chat_id})
    return data["limit"] if data and "limit" in data else 3
async def _get_warn_action(chat_id: int) -> str:
    """Returns 'ban' or 'mute' — default is 'ban'."""
    data = await settings_col.find_one({"chat_id": chat_id})
    return data.get("action", "ban") if data else "ban"
async def _resolve_user(client, message: Message):
    """Return a user object from reply, username, or user ID argument."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    if len(message.command) > 1:
        try:
            return await client.get_users(message.command[1])
        except Exception:
            return None
    return None
# ─── Inline markup helpers ────────────────────────────────────────────────────
def _warn_buttons(chat_id: int, user_id: int, warns: int, limit: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"⚠️ Warns: {warns}/{limit}",
                callback_data=f"warninfo|{chat_id}|{user_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🗑 Reset Warns",
                callback_data=f"resetwarn|{chat_id}|{user_id}",
            ),
            InlineKeyboardButton(
                "✅ Close",
                callback_data="warn_close",
            ),
        ],
    ])
def _warns_view_buttons(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🗑 Reset Warns",
                callback_data=f"resetwarn|{chat_id}|{user_id}",
            ),
            InlineKeyboardButton(
                "✅ Close",
                callback_data="warn_close",
            ),
        ],
    ])
def _reset_confirm_buttons(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Yes, Reset",
                callback_data=f"confirmreset|{chat_id}|{user_id}",
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="warn_close",
            ),
        ],
    ])
def _action_buttons(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚫 Ban",  callback_data=f"warnaction|{chat_id}|ban"),
            InlineKeyboardButton("🔇 Mute", callback_data=f"warnaction|{chat_id}|mute"),
        ],
        [
            InlineKeyboardButton("✅ Close", callback_data="warn_close"),
        ],
    ])
# ═════════════════════════════════════════════════════════════════════════════
# /warn
# ═════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("warn") & filters.group & ~BANNED_USERS)
async def warn_user(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can warn users.**")
    user = await _resolve_user(client, message)
    if not user:
        return await message.reply_text(
            "**» Reply to a user, or provide a username / user ID.**"
        )
    if user.is_bot:
        return await message.reply_text("**» Bots cannot be warned.**")
    if await _is_admin(client, message.chat.id, user.id):
        return await message.reply_text("**» Admins cannot be warned.**")
    chat_id = message.chat.id
    await _add_warn(chat_id, user.id)
    warns = await _get_warns(chat_id, user.id)
    limit = await _get_warn_limit(chat_id)
    action = await _get_warn_action(chat_id)
    # ── Limit reached → punish ────────────────────────────────────────────
    if warns >= limit:
        await _reset_warn(chat_id, user.id)
        if action == "mute":
            try:
                await client.restrict_chat_member(
                    chat_id,
                    user.id,
                    ChatPermissions(can_send_messages=False),
                )
            except Exception:
                pass
            punishment = "🔇 **Muted**"
        else:
            try:
                await client.ban_chat_member(chat_id, user.id)
            except Exception:
                pass
            punishment = "🚫 **Banned**"
        return await message.reply_text(
            f"**» {punishment}**\n\n"
            f"**User:** {user.mention}\n"
            f"**Reason:** Warn limit reached (`{limit}/{limit}`)\n"
            f"**Action:** {punishment}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Close", callback_data="warn_close")]
            ]),
        )
    # ── Normal warn ───────────────────────────────────────────────────────
    await message.reply_text(
        f"**» ⚠️ Warning Issued**\n\n"
        f"**User:** {user.mention}\n"
        f"**Warned by:** {message.from_user.mention}\n"
        f"**Warns:** `{warns}/{limit}`\n\n"
        f"{'⚠️ ' * warns}{'▪️ ' * (limit - warns)}",
        reply_markup=_warn_buttons(chat_id, user.id, warns, limit),
    )
# ═════════════════════════════════════════════════════════════════════════════
# /warns
# ═════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("warns") & filters.group & ~BANNED_USERS)
async def check_warns(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can check warns.**")
    user = await _resolve_user(client, message)
    if not user:
        return await message.reply_text(
            "**» Reply to a user, or provide a username / user ID.**"
        )
    chat_id  = message.chat.id
    warns    = await _get_warns(chat_id, user.id)
    limit    = await _get_warn_limit(chat_id)
    action   = await _get_warn_action(chat_id)
    bar      = "⚠️ " * warns + "▪️ " * (limit - warns)
    await message.reply_text(
        f"**» Warn Status**\n\n"
        f"**User:** {user.mention}\n"
        f"**Warns:** `{warns}/{limit}`\n"
        f"**On Limit:** {'🚫 Ban' if action == 'ban' else '🔇 Mute'}\n\n"
        f"{bar}",
        reply_markup=_warns_view_buttons(chat_id, user.id),
    )
# ═════════════════════════════════════════════════════════════════════════════
# /resetwarn
# ═════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("resetwarn") & filters.group & ~BANNED_USERS)
async def reset_warns_cmd(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can reset warns.**")
    user = await _resolve_user(client, message)
    if not user:
        return await message.reply_text(
            "**» Reply to a user, or provide a username / user ID.**"
        )
    await message.reply_text(
        f"**» Reset warns for {user.mention}?**\n\n"
        f"This will clear all their warnings.",
        reply_markup=_reset_confirm_buttons(message.chat.id, user.id),
    )
# ═════════════════════════════════════════════════════════════════════════════
# /setwarnlimit
# ═════════════════════════════════════════════════════════════════════════════
@Client.on_message(filters.command("setwarnlimit") & filters.group & ~BANNED_USERS)
async def set_warn_limit(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can change warn settings.**")
    if len(message.command) < 2:
        limit  = await _get_warn_limit(message.chat.id)
        action = await _get_warn_action(message.chat.id)
        return await message.reply_text(
            f"**» Current Warn Settings**\n\n"
            f"**Limit:** `{limit}`\n"
            f"**Action on limit:** {'🚫 Ban' if action == 'ban' else '🔇 Mute'}\n\n"
            f"Usage: `/setwarnlimit <number>`",
            reply_markup=_action_buttons(message.chat.id),
        )
    try:
        limit = int(message.command[1])
        if limit < 1:
            raise ValueError
    except ValueError:
        return await message.reply_text(
            "**» Provide a valid number greater than 0.**\nExample: `/setwarnlimit 3`"
        )
    await settings_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"limit": limit}},
        upsert=True,
    )
    action = await _get_warn_action(message.chat.id)
    await message.reply_text(
        f"**» ⚙️ Warn Settings Updated**\n\n"
        f"**New Limit:** `{limit}`\n"
        f"**Action on limit:** {'🚫 Ban' if action == 'ban' else '🔇 Mute'}\n\n"
        f"Tap below to change the punishment action:",
        reply_markup=_action_buttons(message.chat.id),
    )
# ═════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═════════════════════════════════════════════════════════════════════════════
@Client.on_callback_query(filters.regex(r"^warninfo\|"))
async def cb_warn_info(client, cb: CallbackQuery):
    _, chat_id, user_id = cb.data.split("|")
    chat_id = int(chat_id)
    user_id = int(user_id)
    if not await _is_admin(client, chat_id, cb.from_user.id):
        return await cb.answer("Only admins can do this.", show_alert=True)
    warns = await _get_warns(chat_id, user_id)
    limit = await _get_warn_limit(chat_id)
    await cb.answer(f"Warns: {warns}/{limit}", show_alert=True)
@Client.on_callback_query(filters.regex(r"^resetwarn\|"))
async def cb_reset_prompt(client, cb: CallbackQuery):
    _, chat_id, user_id = cb.data.split("|")
    chat_id = int(chat_id)
    user_id = int(user_id)
    if not await _is_admin(client, chat_id, cb.from_user.id):
        return await cb.answer("Only admins can reset warns.", show_alert=True)
    try:
        user = await client.get_users(user_id)
        name = user.mention
    except Exception:
        name = f"`{user_id}`"
    await cb.message.edit_text(
        f"**» Reset warns for {name}?**\n\nThis will clear all their warnings.",
        reply_markup=_reset_confirm_buttons(chat_id, user_id),
    )
    await cb.answer()
@Client.on_callback_query(filters.regex(r"^confirmreset\|"))
async def cb_confirm_reset(client, cb: CallbackQuery):
    _, chat_id, user_id = cb.data.split("|")
    chat_id = int(chat_id)
    user_id = int(user_id)
    if not await _is_admin(client, chat_id, cb.from_user.id):
        return await cb.answer("Only admins can reset warns.", show_alert=True)
    await _reset_warn(chat_id, user_id)
    try:
        user = await client.get_users(user_id)
        name = user.mention
    except Exception:
        name = f"`{user_id}`"
    await cb.message.edit_text(
        f"**» ✅ Warns Reset**\n\n"
        f"All warnings for {name} have been cleared.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Close", callback_data="warn_close")]
        ]),
    )
    await cb.answer("Warns cleared!", show_alert=False)
@Client.on_callback_query(filters.regex(r"^warnaction\|"))
async def cb_warn_action(client, cb: CallbackQuery):
    _, chat_id, action = cb.data.split("|")
    chat_id = int(chat_id)
    if not await _is_admin(client, chat_id, cb.from_user.id):
        return await cb.answer("Only admins can change this.", show_alert=True)
    await settings_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"action": action}},
        upsert=True,
    )
    limit = await _get_warn_limit(chat_id)
    label = "🚫 Ban" if action == "ban" else "🔇 Mute"
    await cb.message.edit_text(
        f"**» ⚙️ Warn Action Updated**\n\n"
        f"**Limit:** `{limit}`\n"
        f"**Action on limit:** {label}\n\n"
        f"Users will be **{action}ned** when they reach `{limit}` warns.",
        reply_markup=_action_buttons(chat_id),
    )
    await cb.answer(f"Action set to {action}!", show_alert=False)
@Client.on_callback_query(filters.regex(r"^warn_close$"))
async def cb_warn_close(client, cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        await cb.answer("Already closed.", show_alert=False)
# ─────────────────────────────────────────────────────────────────────────────
# Help text
# ─────────────────────────────────────────────────────────────────────────────
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_90"
__help__ = """
🔻 /warn — ʀᴇᴘʟʏ/ᴜsᴇʀɴᴀᴍᴇ/ɪᴅ ᴛᴏ ᴡᴀʀɴ ᴀ ᴜsᴇʀ (+1 ᴡᴀʀɴ)
🔻 /warns — ᴄʜᴇᴄᴋ ᴀ ᴜsᴇʀ's ᴄᴜʀʀᴇɴᴛ ᴡᴀʀɴ ᴄᴏᴜɴᴛ
🔻 /resetwarn — ʀᴇsᴇᴛ ᴀʟʟ ᴡᴀʀɴs ғᴏʀ ᴀ ᴜsᴇʀ
🔻 /setwarnlimit <number> — sᴇᴛ ᴍᴀx ᴡᴀʀɴs ʙᴇғᴏʀᴇ ᴀᴜᴛᴏ-ᴀᴄᴛɪᴏɴ (ᴅᴇғᴀᴜʟᴛ: 3)
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Warns"
MOD_PRICE = "50"
