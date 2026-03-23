import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
import config
from SHASHA_DRUGZ.core.userbot import Userbot
from SHASHA_DRUGZ import app
from datetime import datetime
from SHASHA_DRUGZ.utils.database import get_assistant
# Assuming Userbot is defined elsewhere
print("[botschk] botschk ")

last_checked_time = None

@Client.on_message(filters.command("botschk") & filters.group)
async def check_bots_command(client, message):
    global last_checked_time
    try:
        # Start the Pyrogram client
        userbot = await get_assistant(message.chat.id)

        # Get current time before sending messages
        start_time = datetime.now()

        # Extract bot username from command
        command_parts = message.command
        if len(command_parts) == 2:
            bot_username = command_parts[1]
            response = ""  # Define response variable
            try:
                bot = await userbot.get_users(bot_username)
                bot_id = bot.id
                await asyncio.sleep(0.5)
                await userbot.send_message(bot_id, "/start")
                await asyncio.sleep(3)
                # Check if bot responded to /start message
                async for bot_message in userbot.get_chat_history(bot_id, limit=1):
                    if bot_message.from_user.id == bot_id:
                        response += f"╭⎋ {bot.mention}\n l\n╰⊚ **sᴛᴀᴛᴜs: ᴏɴʟɪɴᴇ ✨**\n\n"
                    else:
                        response += f"╭⎋ [{bot.mention}](tg://user?id={bot.id})\n l\n╰⊚ **sᴛᴀᴛᴜs: ᴏғғʟɪɴᴇ ❄**\n\n"
            except Exception:
                response += f"╭⎋ {bot_username}\n l\n╰⊚ **ᴇɪᴛʜᴇʀ ʏᴏᴜ ʜᴀᴠᴇ ɢɪᴠᴇɴ ᴡʀᴏɴɢ ᴜsᴇʀɴᴀᴍᴇ ᴏᴛʜᴇʀᴡɪsᴇ ɪ ᴀᴍ ᴜɴᴀʙʟᴇ ᴛᴏ ᴄʜᴇᴄᴋ ᴅᴜᴇ ᴛᴏ ʟɪᴍɪᴛᴀᴛɪᴏɴ. **\n\n"
            # Update last checked time
            last_checked_time = start_time.strftime("%Y-%m-%d")
            await message.reply_text(f"{response}⏲️ ʟᴀsᴛ ᴄʜᴇᴄᴋ: {last_checked_time}")
        else:
            await message.reply_text("ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ.\n\nᴘʟᴇᴀsᴇ ᴜsᴇ /botschk Bot_Username\n\nʟɪᴋᴇ :- `/botschk @ShashaOffiBot`")
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")
        print(f"Error occurred during /botschk command: {e}")
    
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_17"
__help__ = """
🔻 /botschk <bot_username> ➠ ᴄʜᴇᴄᴋs ᴡʜᴇᴛʜᴇʀ ᴀ ʙᴏᴛ ɪs ᴏɴʟɪɴᴇ ᴏʀ ᴏғғʟɪɴᴇ ʙʏ sᴇɴᴅɪɴɢ /start

📍 ᴇxᴀᴍᴘʟᴇ:
   /botschk @ShashaOffiBot
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Bot-Check"
MOD_PRICE = "10"
