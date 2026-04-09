# ================= 🔥 MOVE BOT SYSTEM (PERSISTENT) ================= #

import asyncio
import uuid
import logging

from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError

import config

logging.basicConfig(level=logging.INFO)

# ================= ⚙️ MONGO ================= #

mongo = MongoClient(config.MONGO_URL)
db = mongo["MOVE_BOTS_DB"]
bots_collection = db["TOKENS"]

# ================= ⚙️ CONFIG ================= #

MAIN_BOT_USERNAME = "ShashaOffiBot"

DEFAULT_BOTS = [
    #"7992290736:AAGD8qaq9az6oFSkoU8bnDZQWELrVUZLuJA",
    #"2096983652:AAG_4MVAdZ8akrRmvIl7228CKrRFOYogLzY",
    #"8273429160:AAHl1bSe5kD3PA_eE0H1ZtIbUO_s8QHaQck",
]

# ================= MESSAGE ================= #

UPGRADE_TEXT = (
    "<blockquote><b>⚡ ᴡᴇ’ᴠᴇ ᴜᴘɢʀᴀᴅᴇᴅ!</b></blockquote>"
    "<blockquote>"
    "[˹𝐒ʜᴧƨнᴧ ༭ 𝐃꧊ꝛʋɢ𝗌˼𓆩𔘓⃭𓆪](https://t.me/ShashaOffiBot)\n"
    "[˹𝐒ʜᴧƨнᴧ ༭ 𝐃꧊ꝛʋɢ𝗌˼𓆩𔘓⃭𓆪](https://t.me/ShashaOffiBot)\n"
    "[˹𝐒ʜᴧƨнᴧ ༭ 𝐃꧊ꝛʋɢ𝗌˼𓆩𔘓⃭𓆪](https://t.me/ShashaOffiBot)\n"
    "[˹𝐒ʜᴧƨнᴧ ༭ 𝐃꧊ꝛʋɢ𝗌˼𓆩𔘓⃭𓆪](https://t.me/ShashaOffiBot)"
    "</blockquote>"
    "<blockquote>"
    "🔻 ᴍᴀɴᴀɢᴇᴍᴇɴᴛ + ғᴇᴅ\n"
    "🔻 ᴍᴜsɪᴄ + ᴄʜᴀᴛ + ʀᴇᴀᴄᴛ\n"
    "🔻 ʀᴀɴᴋɪɴɢ + ɢᴀᴍᴇs\n"
    "🔻 ᴊᴏɪɴ ʀᴇǫ + sᴀɴɢᴍᴀᴛᴀ\n"
    "🔻 ᴅᴇᴘʟᴏʏ sʏsᴛᴇᴍ"
    "</blockquote>"
    "<blockquote>🚀 ᴜᴘɢʀᴀᴅᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɴᴏᴡ</blockquote>"
)

# ================= BUTTON ================= #

def get_buttons():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ ᴋɪᴅɴᴀᴘ ᴍᴇ",
                    url=f"https://t.me/{MAIN_BOT_USERNAME}?startgroup=true",
                )
            ]
        ]
    )

# ================= FILTER ================= #

COMMAND_FILTER = filters.regex(r"^[\/@#\.]") & ~filters.bot

# ================= STORAGE ================= #

running_bots = {}

# ================= VALIDATE TOKEN ================= #

async def validate_token(token):

    try:

        test_bot = Client(
            name=f"check_{uuid.uuid4().hex}",
            bot_token=token,
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            in_memory=True,
        )

        await test_bot.start()
        me = await test_bot.get_me()
        await test_bot.stop()

        return True, me.username

    except Exception:
        return False, None

# ================= CREATE BOT ================= #

async def create_bot(token):

    try:

        bot = Client(
            name=f"move_{uuid.uuid4().hex}",
            bot_token=token,
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            in_memory=True,
        )

        @bot.on_message(COMMAND_FILTER)
        async def reply_upgrade(client, message):

            try:
                await message.reply(
                    UPGRADE_TEXT,
                    reply_markup=get_buttons(),
                    disable_web_page_preview=True,
                )
            except Exception:
                pass

        await bot.start()

        running_bots[token] = bot

        logging.info(f"✅ MoveBot Started → {token[:10]}")

    except RPCError as e:
        logging.error(f"❌ Start Failed {token[:10]} → {e}")

# ================= LOAD SAVED BOTS ================= #

async def load_saved_bots():

    tokens = [x["token"] for x in bots_collection.find()]

    for token in tokens:
        await create_bot(token)
        await asyncio.sleep(2)

# ================= ADD BOT ================= #

@Client.on_message(filters.command("movebot") & filters.private)
async def add_movebot(client, message):

    if len(message.command) != 2:
        return await message.reply("Example:\n/movebot <bot_token>")

    token = message.command[1]

    if bots_collection.find_one({"token": token}):
        return await message.reply("⚠️ Bot already added.")

    msg = await message.reply("🔍 Checking bot token...")

    valid, username = await validate_token(token)

    if not valid:
        return await msg.edit("❌ Invalid bot token.")

    bots_collection.insert_one({"token": token})

    await create_bot(token)

    await msg.edit(f"✅ Bot added successfully → @{username}")

# ================= DELETE BOT ================= #

@Client.on_message(filters.command("delmove") & filters.private)
async def remove_movebot(client, message):

    if len(message.command) != 2:
        return await message.reply("Example:\n/delmove <bot_token>")

    token = message.command[1]

    data = bots_collection.find_one({"token": token})

    if not data:
        return await message.reply("❌ Bot not found.")

    bots_collection.delete_one({"token": token})

    bot = running_bots.get(token)

    if bot:
        await bot.stop()
        del running_bots[token]

    await message.reply("🗑 Bot removed successfully.")

# ================= START DEFAULT + SAVED ================= #

async def load_movebots():

    for token in DEFAULT_BOTS:
        if not bots_collection.find_one({"token": token}):
            bots_collection.insert_one({"token": token})

    await load_saved_bots()
