# SHASHA_DRUGZ/plugins/vctools.py

from SHASHA_DRUGZ.utils.decorators.language import language
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from SHASHA_DRUGZ import app
from config import OWNER_ID

import aiohttp
import re


# -------------------- VC STARTED -------------------- #
@Client.on_message(filters.service & filters.video_chat_started, group=-1)
@language
async def brah(client, msg: Message, lang):
    #print("🔥 VC START TRIGGERED")  # DEBUG: confirm handler runs
    await msg.reply(lang["VC_START"])


# -------------------- VC ENDED -------------------- #
@Client.on_message(filters.service & filters.video_chat_ended, group=-1)
@language
async def brah2(client, msg: Message, lang):
    #print("🔥 VC END TRIGGERED")    # DEBUG: confirm handler runs
    await msg.reply(lang["VC_END"])


# -------------------- VC MEMBERS INVITED -------------------- #
@Client.on_message(filters.service & filters.video_chat_members_invited, group=-1)
@language
async def brah3(client, message: Message, lang):
    #print("🔥 VC INVITE TRIGGERED")  # DEBUG: confirm handler runs
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
        # Use the client parameter (which is the same as app) to get invite link
        invite_link = await client.export_chat_invite_link(message.chat.id)
        add_link = f"https://t.me/{client.me.username}?startgroup=true"

        await message.reply(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text=lang["VC_BUTTON"], url=add_link)],
            ])
        )
    except Exception as e:
        print(f"Error in VC invite handler: {e}")


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
async def search(client, message: Message):
    msg = await message.reply("Searching...")

    async with aiohttp.ClientSession() as session:
        start = 1
        query = message.text.split()[1] if len(message.text.split()) > 1 else ""
        if not query:
            await msg.edit("Please provide a search query.")
            return

        url = (
            "https://content-customsearch.googleapis.com/customsearch/v1"
            f"?cx=ec8db9e1f9e41e65e"
            f"&q={query}"
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
                await msg.edit("No results found!")
                return

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

            # Create inline buttons for pagination using Pyrogram syntax
            prev_and_next_btns = [
                [
                    InlineKeyboardButton(
                        "▶️ Next ▶️",
                        callback_data=f"next {start+10} {query}"
                    )
                ]
            ]

            await msg.edit(
                result,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(prev_and_next_btns) if prev_and_next_btns else None
            )
MOD_TYPE = "MUSIC"
MOD_NAME = "VcInviteCard"
MOD_PRICE = "30"
