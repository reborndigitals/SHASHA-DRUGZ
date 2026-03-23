# SHASHA_DRUGZ/plugins/setmybio.py
import os
import json
from pyrogram import Client, filters
from pyrogram.types import Message

print("[setmybio] setmybio, mybio, userbio, delbio")

BIO_DB_PATH = "SHASHA_DRUGZ/utils/localdb/user_bios.json"
os.makedirs("SHASHA_DRUGZ/utils/localdb", exist_ok=True)


def load_bios():
    if not os.path.exists(BIO_DB_PATH):
        return {}
    try:
        with open(BIO_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_bios(data):
    with open(BIO_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# -----------------------------------------------------------
# /setmybio → 2 modes:
# 1. Reply + /setmybio = copy that user's bio into YOUR bio
# 2. /setmybio <text> = set your own bio manually
# -----------------------------------------------------------
@Client.on_message(filters.command("setmybio"))
async def set_my_bio(client: Client, message: Message):

    db = load_bios()
    your_id = str(message.from_user.id)

    # MODE 1 → Copy bio from replied user
    if message.reply_to_message and message.reply_to_message.from_user and len(message.command) == 1:
        target = message.reply_to_message.from_user
        target_id = str(target.id)

        if target_id not in db:
            await message.reply_text("❌ This user has no saved bio to copy.")
            return

        db[your_id] = db[target_id]
        save_bios(db)

        await message.reply_text(
            f"✅ **Bio copied from {target.first_name}!**\n\n`{db[target_id]}`"
        )
        return

    # MODE 2 → Manual bio setting
    if len(message.command) > 1:
        bio_text = " ".join(message.command[1:])
        db[your_id] = bio_text
        save_bios(db)

        await message.reply_text(f"✅ **Your bio has been set!**\n\n`{bio_text}`")
        return

    # No text + no reply
    await message.reply_text("📌 Usage:\n• Reply + `/setmybio` to copy bio\n• `/setmybio <text>` to set your bio")
    return


# -----------------------------------------------------------
# /mybio → Show your own bio
# -----------------------------------------------------------
@Client.on_message(filters.command("mybio"))
async def my_bio(client: Client, message: Message):
    db = load_bios()
    user_id = str(message.from_user.id)

    if user_id not in db:
        await message.reply_text("❌ You don't have a bio saved.")
        return

    await message.reply_text(f"📝 **Your Bio:**\n`{db[user_id]}`")


# -----------------------------------------------------------
# /userbio → Show another user's bio (must reply)
# -----------------------------------------------------------
@Client.on_message(filters.command("userbio"))
async def user_bio(client: Client, message: Message):

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("⚠️ Reply to a user to view their bio.")
        return

    db = load_bios()
    target = message.reply_to_message.from_user
    target_id = str(target.id)

    if target_id not in db:
        await message.reply_text("❌ This user has no saved bio.")
        return

    await message.reply_text(
        f"🧾 **{target.first_name}'s Bio:**\n`{db[target_id]}`"
    )


# -----------------------------------------------------------
# /delbio → Delete your own bio
# -----------------------------------------------------------
@Client.on_message(filters.command("delbio"))
async def del_bio(client: Client, message: Message):
    db = load_bios()
    user_id = str(message.from_user.id)

    if user_id not in db:
        await message.reply_text("❌ You don't have a saved bio to delete.")
        return

    del db[user_id]
    save_bios(db)

    await message.reply_text("🗑️ **Your bio has been deleted.**")

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_5"
__help__ = """
🔻 /setmybio ➠ sᴇᴛ ʏᴏᴜʀ ᴏᴡɴ ʙɪᴏ ᴍᴀɴᴜᴀʟʟʏ ᴏʀ ᴄᴏᴘʏ ᴀ ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ's ʙɪᴏ
    • /setmybio + reply → ᴄᴏᴘʏ ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ ʙɪᴏ
    • /setmybio <text> → sᴇᴛ ʏᴏᴜʀ ᴏᴡɴ ʙɪᴏ

🔻 /mybio ➠ sʜᴏᴡ ʏᴏᴜʀ ᴏᴡɴ ʙɪᴏ
🔻 /userbio ➠ sʜᴏᴡ ᴀɴᴏᴛʜᴇʀ ᴜsᴇʀ's ʙɪᴏ (ᴍᴜsᴛ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇᴍ)
🔻 /delbio ➠ ᴅᴇʟᴇᴛᴇ ʏᴏᴜʀ ᴏᴡɴ ʙɪᴏ
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "Set-Bio"
MOD_PRICE = "30"
