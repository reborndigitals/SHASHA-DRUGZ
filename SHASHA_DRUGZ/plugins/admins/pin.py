from pyrogram import enums, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter

print("[gpdatw] pin, unpin, pinned")

# ------------------------------------------------------------------------------- #
# PIN
# ------------------------------------------------------------------------------- #
@app.on_message(
    filters.command("pin")
    & admin_filter
    & SUDOERS
    # Removed & ~filters.edited
)
async def pin(_, message: Message):
    if not message.from_user:
        return await message.reply_text("**ᴄᴀɴ'ᴛ ɪᴅᴇɴᴛɪғʏ ᴜsᴇʀ.**")

    replied = message.reply_to_message
    chat_id = message.chat.id
    chat_title = message.chat.title
    user_id = message.from_user.id

    name = message.from_user.mention if message.from_user else "Anonymous Admin"

    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("**ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋs ᴏɴʟʏ ᴏɴ ɢʀᴏᴜᴘs !**")

    if not replied:
        return await message.reply_text("**ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴘɪɴ ɪᴛ !**")

    member = await app.get_chat_member(chat_id, user_id)
    if not member.privileges or not member.privileges.can_pin_messages:
        return await message.reply_text("**ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘɪɴ ʀɪɢʜᴛs.**")

    # pin mode
    text = message.text.lower()
    silent = "silent" in text
    loud = "loud" in text

    disable_notification = silent and not loud

    try:
        await replied.pin(disable_notification=disable_notification)
        await message.reply_text(
            f"**sᴜᴄᴄᴇssғᴜʟʟʏ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ!**\n\n"
            f"**ᴄʜᴀᴛ:** {chat_title}\n"
            f"**ᴀᴅᴍɪɴ:** {name}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(" 📝 ᴠɪᴇᴡ ᴍᴇssᴀɢᴇ ", url=replied.link)]]
            ),
        )
    except Exception:
        await message.reply_text(
            "**ғᴀɪʟᴇᴅ ᴛᴏ ᴘɪɴ ᴍᴇssᴀɢᴇ. ᴍᴀᴋᴇ sᴜʀᴇ ɪ ʜᴀᴠᴇ ᴀᴅᴍɪɴ ʀɪɢʜᴛs.**"
        )

# ------------------------------------------------------------------------------- #
# PINNED
# ------------------------------------------------------------------------------- #
@app.on_message(filters.command("pinned"))  # Removed & ~filters.edited
async def pinned(_, message: Message):
    chat = await app.get_chat(message.chat.id)

    if not chat.pinned_message:
        return await message.reply_text("**ɴᴏ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ ғᴏᴜɴᴅ**")

    try:
        await message.reply_text(
            "ʜᴇʀᴇ ɪs ᴛʜᴇ ʟᴀᴛᴇsᴛ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("📝 ᴠɪᴇᴡ ᴍᴇssᴀɢᴇ", url=chat.pinned_message.link)]]
            ),
        )
    except Exception:
        await message.reply_text("**ᴜɴᴀʙʟᴇ ᴛᴏ ғᴇᴛᴄʜ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ.**")

# ------------------------------------------------------------------------------- #
# UNPIN
# ------------------------------------------------------------------------------- #
@app.on_message(
    filters.command("unpin")
    & admin_filter
    & SUDOERS
    # Removed & ~filters.edited
)
async def unpin(_, message: Message):
    if not message.from_user:
        return await message.reply_text("**ᴄᴀɴ'ᴛ ɪᴅᴇɴᴛɪғʏ ᴜsᴇʀ.**")

    replied = message.reply_to_message
    chat_id = message.chat.id
    chat_title = message.chat.title
    user_id = message.from_user.id

    name = message.from_user.mention if message.from_user else "Anonymous Admin"

    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text("**ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋs ᴏɴʟʏ ᴏɴ ɢʀᴏᴜᴘs !**")

    if not replied:
        return await message.reply_text("**ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴜɴᴘɪɴ ɪᴛ !**")

    member = await app.get_chat_member(chat_id, user_id)
    if not member.privileges or not member.privileges.can_pin_messages:
        return await message.reply_text("**ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘɪɴ ʀɪɢʜᴛs.**")

    try:
        await replied.unpin()
        await message.reply_text(
            f"**sᴜᴄᴄᴇssғᴜʟʟʏ ᴜɴᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ!**\n\n"
            f"**ᴄʜᴀᴛ:** {chat_title}\n"
            f"**ᴀᴅᴍɪɴ:** {name}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(" 📝 ᴠɪᴇᴡ ᴍᴇssᴀɢᴇ ", url=replied.link)]]
            ),
        )
    except Exception:
        await message.reply_text(
            "**ғᴀɪʟᴇᴅ ᴛᴏ ᴜɴᴘɪɴ ᴍᴇssᴀɢᴇ. ᴍᴀᴋᴇ sᴜʀᴇ ɪ ʜᴀᴠᴇ ᴀᴅᴍɪɴ ʀɪɢʜᴛs.**"
        )

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_6"
__help__ = """
🔻 /pin (reply) ➠ ᴘɪɴs ᴀ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
🔻 /pin silent (reply) ➠ ᴘɪɴs ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜᴏᴜᴛ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴs
🔻 /pin loud (reply) ➠ ᴘɪɴs ᴀ ᴍᴇssᴀɢᴇ ᴡɪᴛʜ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴs
🔻 /unpin (reply) ➠ ᴜɴᴘɪɴs ᴛʜᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ
🔻 /pinned ➠ sʜᴏᴡs ᴛʜᴇ ʟᴀᴛᴇsᴛ ᴘɪɴɴᴇᴅ ᴍᴇssᴀɢᴇ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
"""
