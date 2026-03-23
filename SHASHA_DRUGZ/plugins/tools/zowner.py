from pyrogram import Client, filters
import requests
import random
import os
import re
import asyncio
import time
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import add_served_chat, delete_served_chat
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from SHASHA_DRUGZ.utils.database import get_assistant
import asyncio
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.mongo.afkdb import HEHE
from SHASHA_DRUGZ.core.userbot import Userbot
from pyrogram import Client, filters
from pyrogram.errors import UserAlreadyParticipant
from SHASHA_DRUGZ import app
import asyncio
import random
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChatAdminRequired,
    InviteRequestSent,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter
from SHASHA_DRUGZ.utils.decorators.userbotjoin import UserbotWrapper
from SHASHA_DRUGZ.utils.database import get_assistant, is_active_chat

@app.on_message(
    filters.command("repo")
    & filters.group)
async def help(client: Client, message: Message):
    await message.reply_photo(
        photo=f"https://graph.org/file/f21bcb4b8b9c421409b64.png",
        caption=f"""🐦‍🔥 𝐶𝑙𝑖𝑐𝑘 𝐵𝑒𝑙𝑜𝑤 𝐵𝑢𝑡𝑡𝑜𝑛 𝑇𝑜 𝐺𝑒𝑡 𝑅𝑒𝑝𝑜  🥹""",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💕 𝐒𖽙𖽪𖽷𖽝𖽞 🦋", url=f"https://t.me/HeartBeat_Offi")
                ]
            ]
        ),
    )

@app.on_message(
    filters.command("repo")
    & filters.group)
async def help(client: Client, message: Message):
    userbot = await get_assistant(chat_id)
    await message.reply_photo(
        photo=f"https://graph.org/file/f21bcb4b8b9c421409b64.png",
        caption=f"""🐦‍🔥 𝐶𝑙𝑖𝑐𝑘 𝐵𝑒𝑙𝑜𝑤 𝐵𝑢𝑡𝑡𝑜𝑛 𝑇𝑜 𝐺𝑒𝑡 𝑅𝑒𝑝𝑜  🥹""",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💕 𝐒𖽙𖽪𖽷𖽝𖽞 🦋", url=f"https://t.me/HeartBeat_Offi")
                ]
            ]
        ),
    )

@app.on_message(
    filters.command("repo")
    & filters.private)
async def help(client: Client, message: Message):
    await message.reply_photo(
        photo=f"https://graph.org/file/f21bcb4b8b9c421409b64.png",
        caption=f"""🐦‍🔥 𝐶𝑙𝑖𝑐𝑘 𝐵𝑒𝑙𝑜𝑤 𝐵𝑢𝑡𝑡𝑜𝑛 𝑇𝑜 𝐺𝑒𝑡 𝑅𝑒𝑝𝑜  🥹""",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💕 𝐒𖽙𖽪𖽷𖽝𖽞 🦋", url=f"https://t.me/HeartBeat_Offi")
                ]
            ]
        ),
    )

# --------------------------------------------------------------------------------- #

@app.on_message(filters.command(["hi", "hii", "hello", "hui","ok", "bye", "welcome", "thanks"] ,prefixes=["/", "!", "%", ",", "", ".", "@", "#"]) & filters.group)
async def bot_check(_, message):
    chat_id = message.chat.id
    await add_served_chat(chat_id)


# --------------------------------------------------------------------------------- #




import asyncio
import time

@app.on_message(filters.command("gadd") & filters.user(int(HEHE)))
async def add_all(client, message):
    command_parts = message.text.split(" ")
    if len(command_parts) != 2:
        await message.reply("**⚠️ ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ. ᴘʟᴇᴀsᴇ ᴜsᴇ ʟɪᴋᴇ » `/join @HeartBeat_Offi`**")
        return
    
    bot_username = command_parts[1]
    try:
        userbot = await get_assistant(message.chat.id)
        bot = await app.get_users(bot_username)
        app_id = bot.id
        done = 0
        failed = 0
        lol = await message.reply("🔄 **ᴀᴅᴅɪɴɢ ɢɪᴠᴇɴ ʙᴏᴛ ɪɴ ᴀʟʟ ᴄʜᴀᴛs!**")
        
        async for dialog in userbot.get_dialogs():
            if dialog.chat.id == -1001515341564:
                continue
            try:
                await userbot.add_chat_members(dialog.chat.id, app_id)
                done += 1
                await lol.edit(
                    f"**🔂 ᴀᴅᴅɪɴɢ {bot_username}**\n\n**➥ ᴀᴅᴅᴇᴅ ɪɴ {done} ᴄʜᴀᴛs ✅**\n**➥ ғᴀɪʟᴇᴅ ɪɴ {failed} ᴄʜᴀᴛs ❌**\n\n**➲ ᴀᴅᴅᴇᴅ ʙʏ»** @{userbot.username}"
                )
            except Exception as e:
                failed += 1
                await lol.edit(
                    f"**🔂 ᴀᴅᴅɪɴɢ {bot_username}**\n\n**➥ ᴀᴅᴅᴇᴅ ɪɴ {done} ᴄʜᴀᴛs ✅**\n**➥ ғᴀɪʟᴇᴅ ɪɴ {failed} ᴄʜᴀᴛs ❌**\n\n**➲ ᴀᴅᴅɪɴɢ ʙʏ»** @{userbot.username}"
                )
            await asyncio.sleep(3)  # Adjust sleep time based on rate limits
        
        await lol.edit(
            f"**➻ {bot_username} ʙᴏᴛ ᴀᴅᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ🎉**\n\n**➥ ᴀᴅᴅᴇᴅ ɪɴ {done} ᴄʜᴀᴛs ✅**\n**➥ ғᴀɪʟᴇᴅ ɪɴ {failed} ᴄʜᴀᴛs ❌**\n\n**➲ ᴀᴅᴅᴇᴅ ʙʏ»** @{userbot.username}"
        )
    except Exception as e:
        await message.reply(f"Error: {str(e)}")
