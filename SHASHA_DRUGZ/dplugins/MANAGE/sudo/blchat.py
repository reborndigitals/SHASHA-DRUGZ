from pyrogram import Client, filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import blacklist_chat, blacklisted_chats, whitelist_chat
from SHASHA_DRUGZ.utils.decorators.language import language
from config import BANNED_USERS


@Client.on_message(filters.command(["blchat", "blacklistchat"]) & SUDOERS)
@language
async def blacklist_chat_func(client, message: Message, _):
    if len(message.command) != 2:
        return await message.reply_text(_["black_1"])
    chat_id = int(message.text.strip().split()[1])
    if chat_id in await blacklisted_chats():
        return await message.reply_text(_["black_2"])
    blacklisted = await blacklist_chat(chat_id)
    if blacklisted:
        await message.reply_text(_["black_3"])
    else:
        await message.reply_text(_["black_9"])
    try:
        await app.leave_chat(chat_id)
    except:
        pass


@Client.on_message(
    filters.command(["whitelistchat", "unblacklistchat", "unblchat"]) & SUDOERS
)
@language
async def white_funciton(client, message: Message, _):
    if len(message.command) != 2:
        return await message.reply_text(_["black_4"])
    chat_id = int(message.text.strip().split()[1])
    if chat_id not in await blacklisted_chats():
        return await message.reply_text(_["black_5"])
    whitelisted = await whitelist_chat(chat_id)
    if whitelisted:
        return await message.reply_text(_["black_6"])
    await message.reply_text(_["black_9"])

@Client.on_message(filters.command(["blchats", "blacklistedchats"]) & ~BANNED_USERS)
@language
async def all_chats(client, message: Message, _):
    text = _["black_7"]
    j = 0
    for count, chat_id in enumerate(await blacklisted_chats(), 1):
        try:
            title = (await app.get_chat(chat_id)).title
        except:
            title = "ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ"
        j = 1
        text += f"{count}. {title}[<code>{chat_id}</code>]\n"
    if j == 0:
        await message.reply_text(_["black_8"].format(app.mention))
    else:
        await message.reply_text(text)


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_37"
__help__ = """
🔻 /blchat /blacklistchat <chat_id> ➠ ᴀᴅᴅ ᴀ ᴄʜᴀᴛ ᴛᴏ ᴛʜᴇ ʙʟᴀᴄᴋʟɪsᴛ ᴀɴᴅ ʙᴏᴛ ᴡɪʟʟ ʟᴇᴀᴠᴇ ɪᴛ  
🔻 /unblchat /whitelistchat <chat_id> ➠ ʀᴇᴍᴏᴠᴇ ᴀ ᴄʜᴀᴛ ғʀᴏᴍ ʙʟᴀᴄᴋʟɪsᴛ 
🔻 /blchats /blacklistedchats ➠ ʟɪsᴛ ᴀʟʟ ʙʟᴀᴄᴋʟɪsᴛᴇᴅ ᴄʜᴀᴛs
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "BlockChat"
MOD_PRICE = "20"
