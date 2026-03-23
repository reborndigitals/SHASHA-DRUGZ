from pyrogram import filters

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import add_off, add_on
from SHASHA_DRUGZ.utils.decorators.language import language


@app.on_message(filters.command(["logger"]) & SUDOERS)
@language
async def logger(client, message, _):
    usage = _["log_1"]
    if len(message.command) != 2:
        return await message.reply_text(usage)
    state = message.text.split(None, 1)[1].strip().lower()
    if state == "enable":
        await add_on(2)
        await message.reply_text(_["log_2"])
    elif state == "disable":
        await add_off(2)
        await message.reply_text(_["log_3"])
    else:
        await message.reply_text(usage)

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_59"
__help__ = """
🔻 /logger <enable|disable> ➠ ᴛᴜʀɴ ᴛʜᴇ ʟᴏɢɢɪɴɢ sʏsᴛᴇᴍ ᴏɴ ᴏʀ ᴏғғ ɪɴ ᴛʜᴇ ʙᴏᴛ
"""
