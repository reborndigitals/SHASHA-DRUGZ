from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.call import SHASHA
from SHASHA_DRUGZ.utils import bot_sys_stats
from SHASHA_DRUGZ.utils.decorators.language import language
from SHASHA_DRUGZ.utils.inline import supp_markup
from SHASHA_DRUGZ.utils.inline import close_markup
from config import BANNED_USERS, PING_IMG_URL, SUPPORT_CHANNEL, SUPPORT_CHAT
import aiohttp
import asyncio
from io import BytesIO
from PIL import Image, ImageEnhance 
from time import time
import asyncio
from SHASHA_DRUGZ.utils.extraction import extract_user

print("[ping] ping")

# Define a dictionary to track the last message timestamp for each user
user_last_message_time = {}
user_command_count = {}
# Define the threshold for command spamming (e.g., 20 commands within 60 seconds)
SPAM_THRESHOLD = 2
SPAM_WINDOW_SECONDS = 5
# Add these imports

async def make_carbon(code):
    url = "https://carbonara.solopov.dev/api/cook"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"code": code}) as resp:
            image = BytesIO(await resp.read())

    # Open the image using PIL
    carbon_image = Image.open(image)

    # Increase brightness
    enhancer = ImageEnhance.Brightness(carbon_image)
    bright_image = enhancer.enhance(1.7)  # Adjust the enhancement factor as needed

    # Save the modified image to BytesIO object with increased quality
    output_image = BytesIO()
    bright_image.save(output_image, format='PNG', quality=95)  # Adjust quality as needed
    output_image.name = "carbon.png"
    return output_image

@app.on_message(filters.command("ping", prefixes=["/", "!", "%", ",", "", ".", "@", "#"]) & ~BANNED_USERS)
@language
async def ping_com(client, message: Message, _):
    user_id = message.from_user.id
    current_time = time()
    # Update the last message timestamp for the user
    last_message_time = user_last_message_time.get(user_id, 0)

    if current_time - last_message_time < SPAM_WINDOW_SECONDS:
        # If less than the spam window time has passed since the last message
        user_last_message_time[user_id] = current_time
        user_command_count[user_id] = user_command_count.get(user_id, 0) + 1
        if user_command_count[user_id] > SPAM_THRESHOLD:
            # Block the user if they exceed the threshold
            hu = await message.reply_text(f"**{message.from_user.mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ ᴅᴏ sᴘᴀᴍ, ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**")
            await asyncio.sleep(3)
            await hu.delete()
            return 
    else:
        # If more than the spam window time has passed, reset the command count and update the message timestamp
        user_command_count[user_id] = 1
        user_last_message_time[user_id] = current_time

    #PING_IMG_URL = "https://graph.org/file/ffdb1be822436121cf5fd.png"
    captionss = "**ᴅιиg ᴅσиg ꨄ︎...**"
    response = await message.reply_photo(PING_IMG_URL, caption=(captionss))
    await asyncio.sleep(1)
    await response.edit_caption("**ᴅιиg ᴅσиg ꨄ︎.....**")
    await asyncio.sleep(1)
    await response.edit_caption("**⚡ѕт**")
    await asyncio.sleep(1)
    await response.edit_caption("**⚡ѕтα**")
    await asyncio.sleep(1.5)
    await response.edit_caption("**⚡ѕтαя**")
    await asyncio.sleep(2)
    await response.edit_caption("⚡ѕтαят")
    await asyncio.sleep(2)
    await response.edit_caption("**⚡ѕтαятιиg..**")
    await asyncio.sleep(3)
    await response.edit_caption("**⚡ѕтαятιиg.....**")
    start = datetime.now()
    pytgping = await SHASHA.ping()
    UP, CPU, RAM, DISK = await bot_sys_stats()
    resp = (datetime.now() - start).microseconds / 1000
    text =  _["ping_2"].format(resp, app.name, UP, RAM, CPU, DISK, pytgping)
    carbon = await make_carbon(text)
    captions = "**𝐏ιиɢιиɢ...**"
    await message.reply_photo((carbon), caption=captions,
    reply_markup=InlineKeyboardMarkup(
            [
                [
            InlineKeyboardButton(
                text=_["S_B_5"],
                url=f"https://t.me/{app.username}?startgroup=true",
            )
        
        ],
        [
            InlineKeyboardButton(
                text=_["CHT"], url=f"https://t.me/{SUPPORT_CHAT}",
            ),
            InlineKeyboardButton(
                text=_["NET"], url=f"https://t.me/{SUPPORT_CHANNEL}",
            )
        ],
        [
            InlineKeyboardButton(
                text=_["S_B_12"], url=f"https://t.me/{app.username}?start=help"
            )
        ],
    ]
    ),
        )
    await response.delete()


@app.on_callback_query(filters.regex("^close_data"))
async def close_callback(_, query):
    chat_id = query.message.chat.id
    await query.message.delete()


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_17"
__help__ = """
🔻 /ping ➠ ᴄʜᴇᴄᴋs ᴛʜᴇ ʙᴏᴛ ᴘɪɴɢ, ᴘᴏɴɢ ᴀɴᴅ sʏsᴛᴇᴍ sᴛᴀᴛs ɪɴ ʀᴇᴀʟ-ᴛɪᴍᴇ
"""
