import aiohttp
import asyncio
from time import time
from pyrogram import Client, filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app

print("[ccbin] Loaded ccbin.py")

# Anti-Spam Memory
user_last_message_time = {}
user_command_count = {}

SPAM_THRESHOLD = 2        # max 2 commands
SPAM_WINDOW_SECONDS = 5   # within 5 seconds


# --------------------------
# BIN Lookup Function (API)
# Using public API: https://lookup.binlist.net/ 
# --------------------------
async def fetch_bin_info(bin_code: str):
    url = f"https://lookup.binlist.net/{bin_code}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


@Client.on_message(filters.command(["bin", "ccbin", "bininfo"], [".", "!", "/"]))
async def check_ccbin(client, message: Message):
    user_id = message.from_user.id
    current_time = time()

    # ------- Anti-Spam -------
    last_time = user_last_message_time.get(user_id, 0)

    if current_time - last_time < SPAM_WINDOW_SECONDS:
        user_last_message_time[user_id] = current_time
        user_command_count[user_id] = user_command_count.get(user_id, 0) + 1

        if user_command_count[user_id] > SPAM_THRESHOLD:
            warn = await message.reply_text(
                f"**{message.from_user.mention} Don't spam. Try again after 5 seconds.**"
            )
            await asyncio.sleep(3)
            await warn.delete()
            return
    else:
        user_command_count[user_id] = 1
        user_last_message_time[user_id] = current_time

    # ------- Input Check -------
    if len(message.command) < 2:
        return await message.reply_text(
            "<b>Please enter a BIN number to get details.</b>"
        )

    try:
        await message.delete()
    except:
        pass

    aux = await message.reply_text("<b>Checking BIN...</b>")

    bin_code = message.text.split(None, 1)[1].strip()

    if not bin_code.isdigit() or len(bin_code) < 6:
        return await aux.edit("<b>❌ Invalid BIN. Must be 6+ digits.</b>")

    # ------- Fetch BIN Data -------
    try:
        data = await fetch_bin_info(bin_code)

        if not data:
            return await aux.edit("🚫 BIN not recognized.")

        bank = data.get("bank", {}).get("name", "Unknown")
        country = data.get("country", {}).get("name", "Unknown")
        flag = data.get("country", {}).get("emoji", "🏳️")
        iso = data.get("country", {}).get("alpha2", "N/A")
        level = data.get("brand", "N/A")
        prepaid = "Yes" if data.get("prepaid") else "No"
        ctype = data.get("type", "N/A")
        vendor = data.get("scheme", "N/A")

        return await aux.edit(f"""
<b>💠 BIN Details:</b>

<b>🏦 Bank:</b> <tt>{bank}</tt>
<b>💳 BIN:</b> <tt>{bin_code}</tt>
<b>🏡 Country:</b> <tt>{country}</tt>
<b>{flag} Flag:</b> <tt>{flag}</tt>
<b>🧿 ISO:</b> <tt>{iso}</tt>
<b>⏳ Level:</b> <tt>{level}</tt>
<b>🔴 Prepaid:</b> <tt>{prepaid}</tt>
<b>🆔 Type:</b> <tt>{ctype}</tt>
<b>ℹ️ Vendor:</b> <tt>{vendor}</tt>
""")

    except Exception as e:
        return await aux.edit("🚫 Error fetching BIN info. Try again later.")


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_17"
__help__ = """
🔻 /bin | /ccbin | /bininfo ➠ ɢᴇᴛs ᴄᴀʀᴅ ʙɪɴ ᴅᴇᴛᴀɪʟs ʟɪᴋᴇ ʙᴀɴᴋ, ᴄᴏᴜɴᴛʀʏ, ᴄᴀʀᴅ ᴛʏᴘᴇ, ᴠᴇɴᴅᴏʀ & ᴘʀᴇᴘᴀɪᴅ sᴛᴀᴛᴜs
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "CC-Bins"
MOD_PRICE = "20"
