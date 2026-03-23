# SHASHA_DRUGZ/plugins/tools/welcome.py

import os
from logging import getLogger
from PIL import Image, ImageDraw, ImageFont, ImageChops
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from SHASHA_DRUGZ import app
from pyrogram import enums

LOGGER = getLogger(__name__)

# ensure download folder exists
os.makedirs("downloads", exist_ok=True)


# ---------------------------------------------------------

class WelDatabase:
    def __init__(self):
        self.data = {}

    async def find_one(self, chat_id):
        return chat_id in self.data

    async def add_wlcm(self, chat_id):
        if chat_id not in self.data:
            self.data[chat_id] = {"state": "on"}

    async def rm_wlcm(self, chat_id):
        if chat_id in self.data:
            del self.data[chat_id]


wlcm = WelDatabase()


# ---------------------------------------------------------

class temp:
    ME = None
    CURRENT = 2
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None


# ---------------------------------------------------------

def circle(pfp, size=(500, 500)):
    pfp = pfp.resize(size, Image.LANCZOS).convert("RGBA")

    bigsize = (pfp.size[0] * 3, pfp.size[1] * 3)
    mask = Image.new("L", bigsize, 0)

    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + bigsize, fill=255)

    mask = mask.resize(pfp.size, Image.LANCZOS)
    mask = ImageChops.darker(mask, pfp.split()[-1])

    pfp.putalpha(mask)

    return pfp


# ---------------------------------------------------------

def welcomepic(pic, user, chatname, user_id, uname):

    background = Image.open(
        "SHASHA_DRUGZ/assets/shasha/hb-welcome.jpg"
    ).convert("RGB")

    pfp = Image.open(pic).convert("RGBA")

    pfp = circle(pfp)
    pfp = pfp.resize((830, 840))

    draw = ImageDraw.Draw(background)

    font = ImageFont.truetype(
        "SHASHA_DRUGZ/assets/shasha/ArialReg.TTF", 140
    )

    draw.text((2000, 1080), f"{user}", fill=(201, 2, 2), font=font)
    draw.text((2000, 1280), f"{user_id}", fill=(201, 2, 2), font=font)
    draw.text((2000, 1510), f"{uname}", fill=(201, 2, 2), font=font)

    background.paste(pfp, (280, 390), pfp)

    output = f"downloads/welcome_{user_id}.jpg"
    background.save(output, "JPEG", quality=95)

    return output


# ---------------------------------------------------------

@app.on_message(filters.command("welcome") & ~filters.private)
async def auto_state(_, message):

    usage = "**Usage:**\n`/welcome on` or `/welcome off`"

    if len(message.command) == 1:
        return await message.reply_text(usage)

    chat_id = message.chat.id

    user = await app.get_chat_member(chat_id, message.from_user.id)

    if user.status not in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    ):
        return await message.reply_text(
            "Only admins can change welcome settings."
        )

    state = message.command[1].lower()

    A = await wlcm.find_one(chat_id)

    if state == "off":

        if A:
            return await message.reply_text(
                "Welcome messages already disabled."
            )

        await wlcm.add_wlcm(chat_id)

        await message.reply_text(
            f"Welcome messages disabled in {message.chat.title}"
        )

    elif state == "on":

        if not A:
            return await message.reply_text(
                "Welcome messages already enabled."
            )

        await wlcm.rm_wlcm(chat_id)

        await message.reply_text(
            f"Welcome messages enabled in {message.chat.title}"
        )

    else:
        await message.reply_text(usage)


# ---------------------------------------------------------

@app.on_chat_member_updated(filters.group, group=-3)
async def greet_new_member(_, member: ChatMemberUpdated):

    chat_id = member.chat.id

    if await wlcm.find_one(chat_id):
        return

    if not member.new_chat_member:
        return

    user = member.new_chat_member.user

    if not user:
        return

    count = await app.get_chat_members_count(chat_id)

    # profile photo
    try:
        if user.photo:
            pic = await app.download_media(user.photo.big_file_id)
        else:
            pic = "SHASHA_DRUGZ/assets/upic.png"
    except Exception:
        pic = "SHASHA_DRUGZ/assets/upic.png"

    # delete previous welcome
    if temp.MELCOW.get(f"welcome-{chat_id}"):

        try:
            await temp.MELCOW[f"welcome-{chat_id}"].delete()
        except Exception:
            pass

    username = f"@{user.username}" if user.username else "None"

    try:

        welcomeimg = welcomepic(
            pic,
            user.first_name,
            member.chat.title,
            user.id,
            username,
        )

        button_text = "⌯ ɴᴇᴡ ϻᴇᴍʙᴇʀ ⌯"
        add_button_text = "⌯ ᴋɪᴅɴᴧᴘ ϻᴇ ⌯"
        deep_link = f"tg://openmessage?user_id={user.id}"
        add_link = f"https://t.me/{app.username}?startgroup=true"

        temp.MELCOW[f"welcome-{member.chat.id}"] = await app.send_photo(
            member.chat.id,
            photo=welcomeimg,
            caption=f"""
<blockquote>**☆ . * ●¸ . ✦ .★°:. ★ * • ○ ° ★**
 
**{member.chat.title}**

**⊰●⊱┈─★ 𝑾𝑒𝑙𝑐𝑜𝑚𝑒 ★─┈⊰●⊱**</blockquote>\n
<blockquote>**➽────────────────❥**   

**🔻 𝐍ᴀᴍᴇ**    ➥ {user.mention}
**🔻 𝐈ᴅ**       ➥ {user.id}
**🔻 𝐔sᴇʀɴᴀᴍᴇ** ➥ @{user.username}
**🔻 𝐌ᴇᴍʙᴇʀ**   ➥ {count}

**➽────────────────❥**</blockquote>\n  
<blockquote>**☆ . * ●¸ . ✦ .★°:. ★ * • ○ ° ★**</blockquote>
""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(button_text, url=deep_link)],
                [InlineKeyboardButton(text=add_button_text, url=add_link)],
            ])
        )

    except Exception as e:
        LOGGER.error(e)


# ---------------------------------------------------------
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_1"
__help__ = """
🔻 /welcome on  ➠  ᴇɴᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /welcome off  ➠  ᴅɪsᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇssᴀɢᴇs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
"""
