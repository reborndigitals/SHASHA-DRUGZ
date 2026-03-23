import asyncio
import os
import time
import aiohttp
import random
from pathlib import Path
from typing import Union, Optional
from PIL import Image, ImageDraw, ImageFont

from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.extraction import extract_user

print("[info_userid] info, userinfo, me, id")

# ----------------------------------------------------------------------------------
# Anti-spam mechanism (from info.py)
# ----------------------------------------------------------------------------------
user_last_message_time = {}
user_command_count = {}
SPAM_THRESHOLD = 2
SPAM_WINDOW_SECONDS = 5

# ----------------------------------------------------------------------------------
# Constants for userinfo image generation
# ----------------------------------------------------------------------------------
random_photo = [
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
    "https://graph.org/file/ffdb1be822436121cf5fd.png",
]

bg_path = "SHASHA_DRUGZ/assets/userinfo.png"
font_path = "SHASHA_DRUGZ/assets/hiroko.ttf"

get_font = lambda font_size, font_path: ImageFont.truetype(font_path, font_size)
resize_text = (
    lambda text_size, text: (text[:text_size] + "...").upper()
    if len(text) > text_size
    else text.upper()
)

INFO_TEXT = """**
☆ . * ● ¸ . ✦ .★　° :. ★ * • ○ ° ★ ★

⊰●⊱┈─★💕 𝐔𖾗𖽞𖽷 𝐈𖽡ꜰ𖽙 🦋  ★─┈⊰●⊱

➽───────────────────❥

💕 𝐈𖽴 🦋  {}

💕 𝐅𖽹𖽷𖾗𖾓 𝐍𖽖𖽧𖽞 🦋  {}

💕 𝐋𖽖𖾗𖾓 𝐍𖽖𖽧𖽞 🦋  {}

💕 𝐔𖾗𖽞𖽷𖽡𖽖𖽧𖽞 🦋  {}

💕 𝐌𖽞𖽡𖾓𖽹𖽙𖽡 🦋  {}

💕 𝐋𖽖𖾗𖾓 𝐒𖽞𖽞𖽡 🦋  {}

💕 𝐃𖽝 𝐈𖽴 🦋  {}

💕 𝐁𖽹𖽙 🦋  {}

➽───────────────────❥

☆ . * ● ¸ . ✦ .★　° :. ★ * • ○ ° ★**
"""

# ----------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------
async def get_userinfo_img(
    bg_path: str,
    font_path: str,
    user_id: Union[int, str],
    profile_path: Optional[str] = None
):
    bg = Image.open(bg_path)

    if profile_path:
        img = Image.open(profile_path)
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.pieslice([(0, 0), img.size], 0, 360, fill=255)

        circular_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        circular_img.paste(img, (0, 0), mask)
        resized = circular_img.resize((400, 400))
        bg.paste(resized, (440, 160), resized)

    img_draw = ImageDraw.Draw(bg)
    img_draw.text(
        (529, 627),
        text=str(user_id).upper(),
        font=get_font(46, font_path),
        fill=(255, 255, 255),
    )

    path = f"./userinfo_img_{user_id}.png"
    bg.save(path)
    return path


async def userstatus(user_id):
    try:
        user = await app.get_users(user_id)
        x = user.status
        if x == enums.UserStatus.RECENTLY:
            return "Recently."
        elif x == enums.UserStatus.LAST_WEEK:
            return "Last week."
        elif x == enums.UserStatus.LONG_AGO:
            return "Long time ago."
        elif x == enums.UserStatus.OFFLINE:
            return "Offline."
        elif x == enums.UserStatus.ONLINE:
            return "Online."
    except:
        return "**sᴏᴍᴇᴛʜɪɴɢ ᴡʀᴏɴɢ ʜᴀᴘᴘᴇɴᴇᴅ !**"


# ----------------------------------------------------------------------------------
# Command: /info or /userinfo
# ----------------------------------------------------------------------------------
@Client.on_message(filters.command(["info", "userinfo"], prefixes=["/", "!", "%", ",", "", ".", "@", "#"]))
async def userinfo(client: Client, message: Message):
    user_id = message.from_user.id
    current_time = time.time()

    # Anti-spam
    last_message_time = user_last_message_time.get(user_id, 0)
    if current_time - last_message_time < SPAM_WINDOW_SECONDS:
        user_last_message_time[user_id] = current_time
        user_command_count[user_id] = user_command_count.get(user_id, 0) + 1
        if user_command_count[user_id] > SPAM_THRESHOLD:
            hu = await message.reply_text(f"**{message.from_user.mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ ᴅᴏ sᴘᴀᴍ, ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**")
            await asyncio.sleep(3)
            await hu.delete()
            return
    else:
        user_command_count[user_id] = 1
        user_last_message_time[user_id] = current_time

    chat_id = message.chat.id

    # Determine target user
    target_user = None
    if not message.reply_to_message and len(message.command) == 2:
        # /info username or id
        try:
            identifier = message.text.split(None, 1)[1].strip()
            target_user = await app.get_users(identifier)
        except Exception as e:
            await message.reply_text(str(e))
            return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user
    else:
        target_user = message.from_user

    if not target_user:
        return

    try:
        user_info = await app.get_chat(target_user.id)
        user = target_user
        status = await userstatus(user.id)
        id = user_info.id
        dc_id = getattr(user, "dc_id", 1)
        first_name = user_info.first_name
        last_name = user_info.last_name if user_info.last_name else "No last name"
        username = user_info.username if user_info.username else "No Username"
        mention = user.mention
        bio = user_info.bio if user_info.bio else "No bio set"

        if user.photo:
            photo = await app.download_media(user.photo.big_file_id)
            welcome_photo = await get_userinfo_img(
                bg_path=bg_path,
                font_path=font_path,
                user_id=user.id,
                profile_path=photo,
            )
        else:
            welcome_photo = random.choice(random_photo)

        await app.send_photo(
            chat_id,
            photo=welcome_photo,
            caption=INFO_TEXT.format(
                id, first_name, last_name, username, mention, status, dc_id, bio
            ),
            reply_to_message_id=message.id,
        )

        # Clean up downloaded photo if any
        if user.photo and os.path.exists(photo):
            os.remove(photo)
        if os.path.exists(f"./userinfo_img_{user.id}.png"):
            os.remove(f"./userinfo_img_{user.id}.png")

    except Exception as e:
        await message.reply_text(str(e))


# ----------------------------------------------------------------------------------
# Command: /me – show own and chat id
# ----------------------------------------------------------------------------------
@Client.on_message(filters.command("me"))
def ids(client: Client, message: Message):
    reply = message.reply_to_message
    if reply:
        message.reply_text(
            f"ʏᴏᴜʀ ɪᴅ: {message.from_user.id}\n{reply.from_user.first_name}'s ɪᴅ: {reply.from_user.id}\nᴄʜᴀᴛ ɪᴅ: {message.chat.id}"
        )
    else:
        message.reply_text(
            f"ʏᴏᴜʀ ɪᴅ: {message.from_user.id}\nᴄʜᴀᴛ ɪᴅ: {message.chat.id}"
        )


# ----------------------------------------------------------------------------------
# Command: /id – show various ids
# ----------------------------------------------------------------------------------
@Client.on_message(filters.command('id'))
async def getid(client, message: Message):
    chat = message.chat
    your_id = message.from_user.id
    message_id = message.id
    reply = message.reply_to_message

    text = f"**[ᴍᴇssᴀɢᴇ ɪᴅ:]({message.link})** `{message_id}`\n"
    text += f"**[ʏᴏᴜʀ ɪᴅ:](tg://user?id={your_id})** `{your_id}`\n"

    if len(message.command) == 2:
        try:
            split = message.text.split(None, 1)[1].strip()
            user_id = (await client.get_users(split)).id
            text += f"**[ᴜsᴇʀ ɪᴅ:](tg://user?id={user_id})** `{user_id}`\n"
        except Exception:
            return await message.reply_text("ᴛʜɪs ᴜsᴇʀ ᴅᴏᴇsɴ'ᴛ ᴇxɪsᴛ.", quote=True)

    text += f"**[ᴄʜᴀᴛ ɪᴅ:](https://t.me/{chat.username})** `{chat.id}`\n\n"

    if (
        not getattr(reply, "empty", True)
        and not message.forward_from_chat
        and not reply.sender_chat
    ):
        text += f"**[ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ ɪᴅ:]({reply.link})** `{reply.id}`\n"
        text += f"**[ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ ɪᴅ:](tg://user?id={reply.from_user.id})** `{reply.from_user.id}`\n\n"

    if reply and reply.forward_from_chat:
        text += f"ᴛʜᴇ ғᴏʀᴡᴀʀᴅᴇᴅ ᴄʜᴀɴɴᴇʟ, {reply.forward_from_chat.title}, ʜᴀs ᴀɴ ɪᴅ ᴏғ `{reply.forward_from_chat.id}`\n\n"

    if reply and reply.sender_chat:
        text += f"ɪᴅ ᴏғ ᴛʜᴇ ʀᴇᴘʟɪᴇᴅ ᴄʜᴀᴛ/ᴄʜᴀɴɴᴇʟ, ɪs `{reply.sender_chat.id}`"

    await message.reply_text(
        text,
        disable_web_page_preview=True,
        parse_mode=ParseMode.DEFAULT,
    )


# ----------------------------------------------------------------------------------
# Module metadata (optional, for help menu)
# ----------------------------------------------------------------------------------
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_24"
__help__ = """
🔻 /info | /userinfo ➠ sʜᴏᴡs ᴅᴇᴛᴀɪʟs ᴀʙᴏᴜᴛ ᴀ ᴜsᴇʀ ᴏʀ ʏᴏᴜʀsᴇʟғ, ɪɴᴄʟᴜᴅɪɴɢ ɪᴅ, ɴᴀᴍᴇ, ᴜsᴇʀɴᴀᴍᴇ, sᴛᴀᴛᴜs, ᴅᴄ ɪᴅ, ᴀɴᴅ ʙɪᴏ
🔻 /me ➠ sʜᴏᴡs ʏᴏᴜʀ ɪᴅ ᴀɴᴅ ᴄʜᴀᴛ ɪᴅ. ɪғ ʀᴇᴘʟʏɪɴɢ, ɪᴛ ᴀʟsᴏ sʜᴏᴡs ʀᴇᴘʟɪᴇᴅ ᴜsᴇʀ ɪᴅ
🔻 /id ➠ sʜᴏᴡs ᴍᴇssᴀɢᴇ ɪᴅ, ʏᴏᴜʀ ɪᴅ, ᴜsᴇʀ ɪᴅ ᴏғ ᴛʜᴇ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ (ɪғ ᴀᴘᴘʟɪᴄᴀʙʟᴇ), ᴀɴᴅ ᴄʜᴀᴛ ɪᴅ. ᴀʟsᴏ sʜᴏᴡs ғᴏʀᴡᴀʀᴅᴇᴅ ᴄʜᴀɴɴᴇʟ ɪᴅ ɪғ ᴘʀᴇsᴇɴᴛ
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "UserID-Info"
MOD_PRICE = "20"
