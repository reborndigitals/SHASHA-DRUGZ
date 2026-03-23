from pyrogram import Client, filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import autoend_off, autoend_on


@Client.on_message(filters.command("autoend") & SUDOERS)
async def auto_end_stream(client, message: Message):
    usage = "<b>ᴇxᴀᴍᴘʟᴇ :</b>\n\n/autoend [ᴇɴᴀʙʟᴇ | ᴅɪsᴀʙʟᴇ]"
    if len(message.command) != 2:
        return await message.reply_text(usage)
    state = message.text.split(None, 1)[1].strip().lower()
    if state == "enable":
        await autoend_on()
        await message.reply_text(
            "» ᴀᴜᴛᴏ ᴇɴᴅ sᴛʀᴇᴀᴍ ᴇɴᴀʙʟᴇᴅ.\n\nᴀssɪsᴛᴀɴᴛ ᴡɪʟʟ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʟᴇᴀᴠᴇ ᴛʜᴇ ᴠɪᴅᴇᴏᴄʜᴀᴛ ᴀғᴛᴇʀ ғᴇᴡ ᴍɪɴs ᴡʜᴇɴ ɴᴏ ᴏɴᴇ ɪs ʟɪsᴛᴇɴɪɴɢ."
        )
    elif state == "disable":
        await autoend_off()
        await message.reply_text("» ᴀᴜᴛᴏ ᴇɴᴅ sᴛʀᴇᴀᴍ ᴅɪsᴀʙʟᴇᴅ.")
    else:
        await message.reply_text(usage)

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_47"
__help__ = """
🔻 /autoend <enable | disable> ➠ ᴇɴᴀʙʟᴇ ᴏʀ ᴅɪsᴀʙʟᴇ ᴀᴜᴛᴏ ᴇɴᴅ ғᴏʀ ᴠɪᴅᴇᴏ ᴄʜᴀᴛs
"""
MOD_TYPE = "MUSIC"
MOD_NAME = "Auto-EndVC"
MOD_PRICE = "20"
