import asyncio
import logging
import time
from collections import defaultdict

from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserBlocked
from pyrogram.types import Message
from pymongo import MongoClient
from pyrogram.handlers import MessageHandler


# ================= CONFIG ================= #

API_ID = 29945235
API_HASH = "15e39599e18d844b5b731d589a5d01c2"

MONGO_DB_URI = "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority"

ADMINS = [8399160924, 6773435708]

STRING_SESSIONS = [
    "BQDMBnkAgP4mi-0bCSzgIadEuKsdDS7h4YcAgYtXTTqPWkHVe2zhB_e7hCFPkHMbnLXteG7hZs5fdBIHz7KCvUSaUTB21wPqK3kkDbs0B8bxQ4Blw_CjxJrbmHoWPevXB1_HIVOmWWvd4zldqypC_Ddj33WC6WgvOVVaFmQU2QGEAhycy4JTKSJDFU8gOxAi_TOxSYjjk9HiHYxnXo2DYqCK1UBXYF2TZC2mlyvtxS1VlHODX4gqsKzY9QpPvgcI2oXkr-Y7yjUhiL2laPFBQttyYINiVrCgWpTTxbBA_rI2iU0owZHzvgty-G-mbbke95AhYLndKoo44s3gRQLPP86hNiLQEgAAAAH2AVIjAQ",
    "BQHI7ZMAvRoC74JvkhabzOy2taIY48ninlKLfKKrH7OngNefTThsmwj_K3iwE0pK5SVydd4738nskDDrxLIBlZMv7prrOeJ-9lYrB8Z3PlNhll5niVD96zPwgb5xpmNCubmgVPbXSzLOwl0vvnkh80TVVt-Hqa2I1siibKJBT82X_NjBgGRAkvL--rwGoTjIp1uvJVug6k9msieXAIstuZepNHbbuM3pxDpcuN5t-8YlU8cg2F5V_vsSe0t1PLdGLr0-UGhDhQ_VOFlnVZ_I6QWTXl5-STcxQCnzNdh5iRPj8GGWTKy0P71XKX9gJVVBS3HpDGvyPfr-MzbjuU7xofF8qQUENgAAAAH0oQZcAA",
]

# ================= DEFAULTS ================= #

DEFAULT_LIMIT = 3

DEFAULT_PM_MSG = (
    "<blockquote>☆ . * ● ¸ . ✦ .★° :. ★ * • ○ ° ★</blockquote>\n"
    "<blockquote>ʜᴇʏ, ɪ'ᴍ 𝐏𝐦𝐒𝐞𝐜𝐮𝐫𝐞-✗-𝐁𝐨𝐭</blockquote>\n"
    "<blockquote>➽───────────────❥</blockquote>\n"
    "<blockquote>😈 Wait until my boss comes.\n"
    "🚫 Spam = Auto Block (Limit: {limit})</blockquote>\n"
    "<blockquote>☆ . * ● ¸ . ✦ .★° :. ★ * • ○ ° ★</blockquote>"
)

DEFAULT_BLOCK_MSG = (
    "<blockquote>ʙᴇᴇᴘ ʙᴏᴏᴘ ⚠️ Spammer detected!\n"
    "Blocked successfully 🚫</blockquote>"
)

# ================= DATABASE ================= #

mongo = MongoClient(MONGO_DB_URI)
db = mongo["PM_GUARD"]

users = db.users
config = db.config

def get_conf():
    c = config.find_one({"_id": "config"})
    if not c:
        c = {
            "_id": "config",
            "limit": DEFAULT_LIMIT,
            "pm_msg": DEFAULT_PM_MSG,
            "block_msg": DEFAULT_BLOCK_MSG,
            "pm_img": None,
            "img_on": False
        }
        config.insert_one(c)
    return c

# ================= SPAM CONTROL ================= #

LAST_PM = defaultdict(float)

def is_admin(uid):
    return uid in ADMINS

# ================= HANDLERS ================= #

async def pm_guard(_, msg: Message):
    if msg.chat.type != enums.ChatType.PRIVATE:
        return
    if msg.from_user is None:
        return

    uid = msg.from_user.id
    if is_admin(uid):
        return

    if users.find_one({"_id": uid, "approved": True}):
        return

    now = time.time()
    if now - LAST_PM[uid] < 2:
        return
    LAST_PM[uid] = now

    conf = get_conf()
    data = users.find_one({"_id": uid})

    warns = data["warns"] if data else 0
    warns += 1

    users.update_one(
        {"_id": uid},
        {"$set": {"warns": warns, "approved": False}},
        upsert=True
    )

    try:
        if warns >= conf["limit"]:
            await msg.reply(conf["block_msg"])
            await msg.chat.block()
        else:
            text = conf["pm_msg"].format(limit=conf["limit"])
            if conf["img_on"] and conf["pm_img"]:
                await msg.reply_photo(conf["pm_img"], caption=text)
            else:
                await msg.reply(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except UserBlocked:
        pass

# ================= COMMANDS ================= #

async def approve(_, msg: Message):
    if not is_admin(msg.from_user.id) or not msg.reply_to_message:
        return
    uid = msg.reply_to_message.from_user.id
    users.update_one({"_id": uid}, {"$set": {"approved": True, "warns": 0}}, upsert=True)
    await msg.reply("✅ Approved")

async def disapprove(_, msg: Message):
    if not is_admin(msg.from_user.id) or not msg.reply_to_message:
        return
    uid = msg.reply_to_message.from_user.id
    users.delete_one({"_id": uid})
    await msg.reply("❌ Disapproved")

async def setlimit(_, msg: Message):
    if not is_admin(msg.from_user.id):
        return
    try:
        n = int(msg.text.split()[1])
        config.update_one({"_id": "config"}, {"$set": {"limit": n}}, upsert=True)
        await msg.reply(f"✅ Limit set to {n}")
    except:
        await msg.reply("❌ Usage: .setlimit <number>")

async def setpmmsg(_, msg: Message):
    if not is_admin(msg.from_user.id):
        return
    text = msg.text.split(None, 1)[1]
    config.update_one({"_id": "config"}, {"$set": {"pm_msg": text}}, upsert=True)
    await msg.reply("✅ PM Message updated")

async def setblockmsg(_, msg: Message):
    if not is_admin(msg.from_user.id):
        return
    text = msg.text.split(None, 1)[1]
    config.update_one({"_id": "config"}, {"$set": {"block_msg": text}}, upsert=True)
    await msg.reply("✅ Block Message updated")

async def setpmimg(_, msg: Message):
    if not is_admin(msg.from_user.id) or not msg.reply_to_message.photo:
        return
    fid = msg.reply_to_message.photo.file_id
    config.update_one({"_id": "config"}, {"$set": {"pm_img": fid}}, upsert=True)
    await msg.reply("✅ PM Image saved")

async def toggleimg(_, msg: Message):
    if not is_admin(msg.from_user.id):
        return
    c = get_conf()
    new = not c["img_on"]
    config.update_one({"_id": "config"}, {"$set": {"img_on": new}}, upsert=True)
    await msg.reply(f"🖼️ Image {'ON' if new else 'OFF'}")

async def forceblock(_, msg: Message):
    if not is_admin(msg.from_user.id) or not msg.reply_to_message:
        return
    await msg.reply_to_message.chat.block()
    await msg.reply("🚫 User blocked")

async def pmhelp(_, msg: Message):
    await msg.reply(
        "<b>🛡️ PM Guard Commands</b>\n\n"
        "`.a` - Approve User (Reply)\n"
        "`.da` - Disapprove User (Reply)\n"
        "`.setlimit <n>` - Set Max Warns\n"
        "`.setpmmsg <text>` - Set Warning Text\n"
        "`.setblockmsg <text>` - Set Block Text\n"
        "`.setpmimg` (Reply) - Set Image\n"
        "`.pmimg` - Toggle Image On/Off\n"
        "`.block` (Reply) - Force Block"
    )

# ================= LOAD ================= #

clients = []

for i, s in enumerate(STRING_SESSIONS):
    app = Client(
        name=f"pm_guard_{i}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=s,
        in_memory=True
    )

    app.add_handler(MessageHandler(pm_guard, filters.private & ~filters.me))

    app.add_handler(MessageHandler(approve, filters.command("a", ".")))
    app.add_handler(MessageHandler(disapprove, filters.command("da", ".")))
    app.add_handler(MessageHandler(setlimit, filters.command("setlimit", ".")))
    app.add_handler(MessageHandler(setpmmsg, filters.command("setpmmsg", ".")))
    app.add_handler(MessageHandler(setblockmsg, filters.command("setblockmsg", ".")))
    app.add_handler(MessageHandler(setpmimg, filters.command("setpmimg", ".")))
    app.add_handler(MessageHandler(toggleimg, filters.command("pmimg", ".")))
    app.add_handler(MessageHandler(forceblock, filters.command("block", ".")))
    app.add_handler(MessageHandler(pmhelp, filters.command("pmhelp", ".")))

    clients.append(app)

async def start_all():
    for c in clients:
        await c.start()
    print("🛡️ PM Guard Loaded Successfully")
    await asyncio.Event().wait()

asyncio.run(start_all())
