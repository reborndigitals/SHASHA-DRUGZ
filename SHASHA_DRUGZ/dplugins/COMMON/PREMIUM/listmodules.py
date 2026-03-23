# SHASHA_DRUGZ/dplugins/PREMIUM/listmodules.py

import os
import re
from pyrogram import Client, filters
from pyrogram.types import Message

from config import ADMINS_ID
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.mongo.deploydb import get_deployed_bot_by_id

PLUGINS_PATH = "SHASHA_DRUGZ/dplugins"


# -------------------- HELPERS --------------------

def scan_priced_modules():
    """
    Scan ONLY modules that explicitly define:
    MOD_NAME and MOD_PRICE
    """
    modules = []

    for root, _, files in os.walk(PLUGINS_PATH):
        for file in files:
            if not file.endswith(".py"):
                continue
            if file.startswith("_"):
                continue

            path = os.path.join(root, file)

            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                name_match = re.search(
                    r'MOD_NAME\s*=\s*[\'"](.+?)[\'"]',
                    content
                )
                price_match = re.search(
                    r'MOD_PRICE\s*=\s*[\'"](\d+)[\'"]',
                    content
                )

                if not name_match or not price_match:
                    continue

                modules.append({
                    "name": name_match.group(1),
                    "price": int(price_match.group(1))
                })

            except Exception:
                continue

    return sorted(modules, key=lambda x: x["price"])


def format_modules(modules):
    text = ""
    for m in modules:
        price = "FREE" if m["price"] == 0 else f"₹{m['price']}"
        text += f"• **{m['name']}** — `{price}`\n"
    return text or "_No paid modules found._"


# -------------------- PUBLIC COMMANDS --------------------

@Client.on_message(filters.command(["modules", "listmodules", "plugins"]))
async def list_all_modules(client: Client, message: Message):
    modules = scan_priced_modules()

    text = (
        "📦 **AVAILABLE MODULES & PRICELIST**\n\n"
        f"{format_modules(modules)}\n"
        "🧾 Prices are monthly.\n"
    )

    await message.reply_text(text)


# -------------------- MY MODULES (OWNER + ADMINS) --------------------

@Client.on_message(filters.command(["mymodules", "myplugins"]))
async def list_my_modules(client: Client, message: Message):
    user_id = message.from_user.id

    # Admin can always view
    if user_id in ADMINS_ID:
        modules = scan_priced_modules()
        return await message.reply_text(
            "📦 **ALL MODULES (ADMIN VIEW)**\n\n"
            f"{format_modules(modules)}"
        )

    # Normal user → must be deployed bot owner
    bot = await get_deployed_bot_by_id(message.chat.id)
    if not bot:
        return await message.reply_text(
            "❌ This command works only inside your deployed bot."
        )

    if bot["owner_id"] != user_id:
        return await message.reply_text(
            "❌ You are not the owner of this bot."
        )

    enabled = set(bot.get("modules", []))
    all_modules = scan_priced_modules()

    owned_modules = [m for m in all_modules if m["name"] in enabled]

    text = (
        "📦 **YOUR ENABLED MODULES**\n\n"
        f"{format_modules(owned_modules)}"
    )

    await message.reply_text(text)

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_34"
__help__ = """
🔻 /modules ➠ ʟɪꜱᴛ ᴀʟʟ ᴀᴠᴀɪʟᴀʙʟᴇ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜ ᴘʀɪᴄᴇ
🔻 /listmodules ➠ ꜱʜᴏᴡ ꜰᴜʟʟ ᴍᴏᴅᴜʟᴇ ᴘʀɪᴄᴇʟɪꜱᴛ
🔻 /plugins ➠ ᴠɪᴇᴡ ᴀʟʟ ᴘʟᴜɢɪɴꜱ ᴀɴᴅ ᴍᴏᴅᴜʟᴇꜱ
🔻 /mymodules ➠ ꜱʜᴏᴡ ʏᴏᴜʀ ᴇɴᴀʙʟᴇᴅ ᴍᴏᴅᴜʟᴇꜱ
🔻 /myplugins ➠ ʟɪꜱᴛ ᴍᴏᴅᴜʟᴇꜱ ᴀᴄᴛɪᴠᴇ ɪɴ ʏᴏᴜʀ ʙᴏᴛ
"""

MOD_TYPE = "TOOLS"
MOD_NAME = "Modules"
MOD_PRICE = "0"
