import random

from pyrogram import filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import db
from SHASHA_DRUGZ.utils.decorators import AdminRightsCheck
from SHASHA_DRUGZ.utils.inline import close_markup
from config import BANNED_USERS

@app.on_message(
    filters.command(["shuffle", "cshuffle"]) & filters.group & ~BANNED_USERS
)
@AdminRightsCheck
async def admins(Client, message: Message, _, chat_id):
    check = db.get(chat_id)
    if not check:
        return await message.reply_text(_["queue_2"])
    try:
        popped = check.pop(0)
    except:
        return await message.reply_text(_["admin_15"], reply_markup=close_markup(_))
    check = db.get(chat_id)
    if not check:
        check.insert(0, popped)
        return await message.reply_text(_["admin_15"], reply_markup=close_markup(_))
    random.shuffle(check)
    check.insert(0, popped)
    await message.reply_text(
        _["admin_16"].format(message.from_user.mention), reply_markup=close_markup(_)
    )

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_66"
__help__ = """
🔻 /shuffle ➠ sʜᴜғғʟᴇ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ǫᴜᴇᴜᴇ ᴏғ ᴛʀᴀᴄᴋs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
🔻 /cshuffle ➠ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ǫᴜᴇᴜᴇ ᴀɴᴅ sʜᴜғғʟᴇ ᴛʀᴀᴄᴋs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
"""
