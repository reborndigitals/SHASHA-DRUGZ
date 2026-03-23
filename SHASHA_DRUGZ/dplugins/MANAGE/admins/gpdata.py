from pyrogram import filters, Client, enums
from pyrogram.types import Message
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter
from SHASHA_DRUGZ.utils.database import delete_served_chat


print("[gpdatw] removephoto, setphoto, settitle, setdiscription, leavegroup")


# ------------------------------------------------------------------------------- #
# REMOVE PHOTO
# ------------------------------------------------------------------------------- #
@Client.on_message(filters.command("removephoto") & admin_filter & SUDOERS)
async def deletechatphoto(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    msg = await message.reply_text("**ᴘʀᴏᴄᴇssɪɴɢ....**")

    if message.chat.type == enums.ChatType.PRIVATE:
        return await msg.edit("**ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋ ᴏɴ ɢʀᴏᴜᴘs !**")

    try:
        admin_check = await app.get_chat_member(chat_id, user_id)
        if admin_check.privileges.can_change_info:
            await app.delete_chat_photo(chat_id)
            await msg.edit(
                "**sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ ᴘʀᴏғɪʟᴇ ᴘʜᴏᴛᴏ ғʀᴏᴍ ɢʀᴏᴜᴘ !**\n"
                f"ʙʏ {message.from_user.mention}"
            )
    except:
        await msg.edit(
            "**ᴛʜᴇ ᴜsᴇʀ ᴍᴜsᴛ ʜᴀᴠᴇ ᴄʜᴀɴɢᴇ ɪɴғᴏ ᴀᴅᴍɪɴ ʀɪɢʜᴛs !**"
        )


# ------------------------------------------------------------------------------- #
# SET PHOTO
# ------------------------------------------------------------------------------- #
@Client.on_message(filters.command("setphoto") & admin_filter & SUDOERS)
async def setchatphoto(client: Client, message: Message):
    reply = message.reply_to_message
    chat_id = message.chat.id
    user_id = message.from_user.id
    msg = await message.reply_text("ᴘʀᴏᴄᴇssɪɴɢ...")

    if message.chat.type == enums.ChatType.PRIVATE:
        return await msg.edit("**ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋ ᴏɴ ɢʀᴏᴜᴘs !**")

    if not reply:
        return await msg.edit("**ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ.**")

    try:
        admin_check = await app.get_chat_member(chat_id, user_id)
        if admin_check.privileges.can_change_info:
            photo = await reply.download()
            await message.chat.set_photo(photo=photo)
            await msg.edit(
                "**sᴜᴄᴄᴇssғᴜʟʟʏ ɴᴇᴡ ᴘʀᴏғɪʟᴇ ᴘʜᴏᴛᴏ ɪɴsᴇʀᴛ !**\n"
                f"ʙʏ {message.from_user.mention}"
            )
    except:
        await msg.edit("**ᴄʜᴀɴɢᴇ ɪɴғᴏ ᴀᴅᴍɪɴ ʀɪɢʜᴛs ʀᴇǫᴜɪʀᴇᴅ !**")


# ------------------------------------------------------------------------------- #
# SET TITLE
# ------------------------------------------------------------------------------- #
@Client.on_message(filters.command("settitle") & admin_filter & SUDOERS)
async def setgrouptitle(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    msg = await message.reply_text("ᴘʀᴏᴄᴇssɪɴɢ...")

    if message.chat.type == enums.ChatType.PRIVATE:
        return await msg.edit("**ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋ ᴏɴ ɢʀᴏᴜᴘs !**")

    title = None
    if message.reply_to_message:
        title = message.reply_to_message.text
    elif len(message.command) > 1:
        title = message.text.split(None, 1)[1]

    if not title:
        return await msg.edit("**ʀᴇᴘʟʏ ᴛᴏ ᴛᴇxᴛ ᴏʀ ɢɪᴠᴇ ᴀ ᴛɪᴛʟᴇ !**")

    try:
        admin_check = await app.get_chat_member(chat_id, user_id)
        if admin_check.privileges.can_change_info:
            await message.chat.set_title(title)
            await msg.edit(
                "**sᴜᴄᴄᴇssғᴜʟʟʏ ɴᴇᴡ ɢʀᴏᴜᴘ ɴᴀᴍᴇ ɪɴsᴇʀᴛ !**\n"
                f"ʙʏ {message.from_user.mention}"
            )
    except:
        await msg.edit("**ᴄʜᴀɴɢᴇ ɪɴғᴏ ᴀᴅᴍɪɴ ʀɪɢʜᴛs ʀᴇǫᴜɪʀᴇᴅ !**")


# ------------------------------------------------------------------------------- #
# SET DESCRIPTION
# ------------------------------------------------------------------------------- #
@Client.on_message(filters.command("setdiscription") & admin_filter & SUDOERS)
async def setg_discription(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    msg = await message.reply_text("**ᴘʀᴏᴄᴇssɪɴɢ...**")

    if message.chat.type == enums.ChatType.PRIVATE:
        return await msg.edit("**ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋs ᴏɴ ɢʀᴏᴜᴘs!**")

    description = None
    if message.reply_to_message:
        description = message.reply_to_message.text
    elif len(message.command) > 1:
        description = message.text.split(None, 1)[1]

    if not description:
        return await msg.edit("**ʀᴇᴘʟʏ ᴛᴏ ᴛᴇxᴛ ᴏʀ ɢɪᴠᴇ ᴅɪsᴄʀɪᴘᴛɪᴏɴ !**")

    try:
        admin_check = await app.get_chat_member(chat_id, user_id)
        if admin_check.privileges.can_change_info:
            await message.chat.set_description(description)
            await msg.edit(
                "**sᴜᴄᴄᴇssғᴜʟʟʏ ɴᴇᴡ ɢʀᴏᴜᴘ ᴅɪsᴄʀɪᴘᴛɪᴏɴ ɪɴsᴇʀᴛ!**\n"
                f"ʙʏ {message.from_user.mention}"
            )
    except:
        await msg.edit("**ᴄʜᴀɴɢᴇ ɪɴғᴏ ᴀᴅᴍɪɴ ʀɪɢʜᴛs ʀᴇǫᴜɪʀᴇᴅ !**")


# ------------------------------------------------------------------------------- #
# LEAVE GROUP
# ------------------------------------------------------------------------------- #
@Client.on_message(filters.command("leavegroup") & SUDOERS)
async def bot_leave(client: Client, message: Message):
    chat_id = message.chat.id
    await message.reply_text("**sᴜᴄᴄᴇssғᴜʟʟʏ ʜɪʀᴏ !!**")
    await app.leave_chat(chat_id, delete=True)
    await delete_served_chat(chat_id)

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_46"
__help__ = """
🔻 /removephoto ➠ ʀᴇᴍᴏᴠᴇs ᴛʜᴇ ɢʀᴏᴜᴘ ᴘʀᴏғɪʟᴇ ᴘʜᴏᴛᴏ (ᴀᴅᴍɪɴ + sᴜᴅᴏ)
🔻 /setphoto (reply) ➠ sᴇᴛs ᴀ ɴᴇᴡ ɢʀᴏᴜᴘ ᴘʀᴏғɪʟᴇ ᴘʜᴏᴛᴏ ғʀᴏᴍ ʀᴇᴘʟɪᴇᴅ ɪᴍᴀɢᴇ (ᴀᴅᴍɪɴ + sᴜᴅᴏ)
🔻 /settitle <text> ➠ ᴄʜᴀɴɢᴇs ᴛʜᴇ ɢʀᴏᴜᴘ ɴᴀᴍᴇ (ᴀᴅᴍɪɴ + sᴜᴅᴏ)
🔻 /setdiscription <text> ➠ sᴇᴛs ᴀ ɴᴇᴡ ɢʀᴏᴜᴘ ᴅɪsᴄʀɪᴘᴛɪᴏɴ (ᴀᴅᴍɪɴ + sᴜᴅᴏ)
🔻 /leavegroup ➠ ʙᴏᴛ ʟᴇᴀᴠᴇs ᴛʜᴇ ɢʀᴏᴜᴘ ᴀɴᴅ ʀᴇᴍᴏᴠᴇs ɪᴛ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ (sᴜᴅᴏ ᴏɴʟʏ)
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "EditGroup"
MOD_PRICE = "20"
