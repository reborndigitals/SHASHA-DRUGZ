from SHASHA_DRUGZ.utils.decorators.language import language
from pyrogram import Client, filters
from pyrogram.types import Message
from SHASHA_DRUGZ import app
from config import OWNER_ID
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import aiohttp
import re
from pyrogram.types import InlineKeyboardButton as Button


# -------------------- VC STARTED -------------------- #
@Client.on_message(filters.video_chat_started)
@language
async def brah(client, msg: Message, lang):
    await msg.reply(lang["VC_START"])


# -------------------- VC ENDED -------------------- #
@Client.on_message(filters.video_chat_ended)
@language
async def brah2(client, msg: Message, lang):
    await msg.reply(lang["VC_END"])


# -------------------- VC MEMBERS INVITED -------------------- #
@Client.on_message(filters.video_chat_members_invited)
@language
async def brah3(client, message: Message, lang):
    app = message._client

    text = (
        f"<blockquote>**нɛʏ, {message.from_user.mention}**</blockquote>"
        f"<blockquote>{lang['VC_INVITE']}</blockquote>\n"
    )

    for user in message.video_chat_members_invited.users:
        try:
            text += f"[{user.first_name}](tg://user?id={user.id}) "
        except:
            pass

    try:
        invite_link = await app.export_chat_invite_link(message.chat.id)
        add_link = f"https://t.me/{app.username}?startgroup=true"

        await message.reply(
            f"\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text=lang["VC_BUTTON"], url=add_link)],
            ])
        )
    except Exception as e:
        print(f"Error: {e}")


# -------------------- MATH -------------------- #
@Client.on_message(filters.command("math", prefixes="/"))
def calculate_math(client, message: Message):
    try:
        expression = message.text.split("/math ", 1)[1]
    except IndexError:
        return message.reply("ɪɴᴠᴀʟɪᴅ ᴇxᴘʀᴇssɪᴏɴ")

    try:
        result = eval(expression)
        response = f"ᴛʜᴇ ʀᴇsᴜʟᴛ ɪs : {result}"
    except:
        response = "ɪɴᴠᴀʟɪᴅ ᴇxᴘʀᴇssɪᴏɴ"

    message.reply(response)


# -------------------- SEARCH -------------------- #
@Client.on_message(filters.command(["spg"], ["/", "!", "."]))
async def search(event):
    msg = await event.reply("Searching...")

    async with aiohttp.ClientSession() as session:
        start = 1

        url = (
            "https://content-customsearch.googleapis.com/customsearch/v1"
            f"?cx=ec8db9e1f9e41e65e"
            f"&q={event.text.split()[1]}"
            f"&key=AIzaSyAa8yy0GdcGPHdtD083HiGGx_S0vMPScDM"
            f"&start={start}"
        )

        async with session.get(
            url,
            headers={"x-referer": "https://explorer.apis.google.com"}
        ) as r:

            response = await r.json()
            result = ""

            if not response.get("items"):
                return await msg.edit("No results found!")

            for item in response["items"]:
                title = item["title"]
                link = item["link"]

                if "/s" in link:
                    link = link.replace("/s", "")

                elif re.search(r'\/\d', link):
                    link = re.sub(r'\/\d', "", link)

                if "?" in link:
                    link = link.split("?")[0]

                if link in result:
                    continue

                result += f"{title}\n{link}\n\n"

            prev_and_next_btns = [
                Button.inline(
                    "▶️Next▶️",
                    data=f"next {start+10} {event.text.split()[1]}"
                )
            ]

            await msg.edit(
                result,
                link_preview=False,
                buttons=prev_and_next_btns
            )


MOD_TYPE = "MUSIC"
MOD_NAME = "VcInviteCard"
MOD_PRICE = "30"
