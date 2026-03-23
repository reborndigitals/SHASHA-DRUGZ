from SHASHA_DRUGZ import app
from config import OWNER_ID
from pyrogram import filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter
from SHASHA_DRUGZ.misc import SUDOERS

print("[banall] catall + unbanall")

BOT_ID = app.me.id


# =========================
# BAN ALL
# =========================
@app.on_message(filters.command("catall") & SUDOERS)
async def ban_all(_, msg):
    chat_id = msg.chat.id    
    bot = await app.get_chat_member(chat_id, BOT_ID)
    bot_permission = bot.privileges and bot.privileges.can_restrict_members

    if bot_permission:
        async for member in app.get_chat_members(chat_id):
            try:
                await app.ban_chat_member(chat_id, member.user.id)
                await msg.reply_text(
                    f"**‣ ᴏɴᴇ ᴍᴏʀᴇ ʙᴀɴɴᴇᴅ.**\n\n➻ {member.user.mention}"
                )
            except Exception:
                pass
    else:
        await msg.reply_text(
            "ᴇɪᴛʜᴇʀ ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴛʜᴇ ʀɪɢʜᴛ ᴛᴏ ʀᴇsᴛʀɪᴄᴛ ᴜsᴇʀs "
            "ᴏʀ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ɪɴ sᴜᴅᴏ ᴜsᴇʀs"
        )


# =========================
# UNBAN ALL
# =========================
@app.on_message(filters.command("unbanall") & SUDOERS)
async def unban_all(_, msg):
    chat_id = msg.chat.id
    bot = await app.get_chat_member(chat_id, BOT_ID)
    bot_permission = bot.privileges and bot.privileges.can_restrict_members

    if bot_permission:
        async for member in app.get_chat_members(
            chat_id,
            filter=enums.ChatMembersFilter.BANNED
        ):
            try:
                await app.unban_chat_member(chat_id, member.user.id)
                await msg.reply_text(
                    f"**‣ ᴏɴᴇ ᴜɴʙᴀɴɴᴇᴅ.**\n\n➻ {member.user.mention}"
                )
            except Exception:
                pass
    else:
        await msg.reply_text(
            "ᴇɪᴛʜᴇʀ ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴛʜᴇ ʀɪɢʜᴛ ᴛᴏ ᴜɴʙᴀɴ ᴜsᴇʀs "
            "ᴏʀ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ɪɴ sᴜᴅᴏ ᴜsᴇʀs"
        )

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_4"
__help__ = """
🔻 /catall ➠ ʙᴀɴꜱ ᴀʟʟ ᴍᴇᴍʙᴇʀꜱ ꜰʀᴏᴍ ᴛʜᴇ ɢʀᴏᴜᴘ (ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴏɴʟʏ).
🔻 /unbanall ➠ ᴜɴʙᴀɴꜱ ᴀʟʟ ᴘʀᴇᴠɪᴏᴜꜱʟʏ ʙᴀɴɴᴇᴅ ᴜꜱᴇʀꜱ (ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴏɴʟʏ).
"""
