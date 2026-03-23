from pyrogram import Client, filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.errors import capture_err

print("[webss] webss")

@Client.on_message(filters.command("webss", prefixes=["/", "!", "%", ",", "", ".", "@", "#"]))
@capture_err
async def take_ss(client: Client, message: Message):
    try:
        if len(message.command) != 2:
            return await message.reply_text(
                "**» ɢɪᴠᴇ ᴀ ᴜʀʟ ᴛᴏ ғᴇᴛᴄʜ sᴄʀᴇᴇɴsʜᴏᴛ...**"
            )
        url = message.text.split(None, 1)[1]
        m = await message.reply_text("**» ᴛʀʏɪɴɢ ᴛᴏ ᴛᴀᴋᴇ sᴄʀᴇᴇɴsʜᴏᴛ...**")
        await m.edit("**» ᴜᴩʟᴏᴀᴅɪɴɢ ᴄᴀᴩᴛᴜʀᴇᴅ sᴄʀᴇᴇɴsʜᴏᴛ...**")
        try:
            await message.reply_photo(
                photo=f"https://webshot.amanoteam.com/print?q={url}",
                quote=False,
            )
        except TypeError:
            return await m.edit("**» ɴᴏ sᴜᴄʜ ᴡᴇʙsɪᴛᴇ.**")
        await m.delete()
    except Exception as e:
        await message.reply_text(str(e))

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_60"
__help__ = """
🔻 /webss [url] ➠ ᴛᴀᴋᴇꜱ ᴀ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ ᴏꜰ ᴛʜᴇ ɢɪᴠᴇɴ ᴡᴇʙꜱɪᴛᴇ ᴀɴᴅ ꜱᴇɴᴅꜱ ɪᴛ ʙᴀᴄᴋ.
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "WebSS"
MOD_PRICE = "10"
