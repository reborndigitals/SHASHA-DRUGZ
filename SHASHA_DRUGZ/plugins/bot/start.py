from time import time
import asyncio
import random
import httpx

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ChatType
from youtubesearchpython.__future__ import VideosSearch

import config
from config import BANNED_USERS, GREET, MENTION_USERNAMES, START_REACTIONS, SHASHA_PICS
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import _boot_
from SHASHA_DRUGZ.utils import bot_up_time
from SHASHA_DRUGZ.plugins.sudo.sudoers import sudoers_list
from SHASHA_DRUGZ.utils.database import (
    add_served_chat,
    add_served_user,
    blacklisted_chats,
    get_lang,
    is_banned_user,
    is_on_off,
)
from SHASHA_DRUGZ.utils.decorators.language import LanguageStart
from SHASHA_DRUGZ.utils.formatters import get_readable_time
from SHASHA_DRUGZ.utils.inline import first_page, private_panel, start_panel
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.extraction import extract_user
from strings import get_string

# ══════════════════════════════════════════════════════════════════════════════
#  START STICKERS
# ══════════════════════════════════════════════════════════════════════════════
START_STICKERS = [
    "CAACAgUAAxkBAAIKDGm80g_znNZjQLXko2KEZM1nr0qEAAKyCAACjfw5Vwmuqla3_0AwHgQ",
    "CAACAgUAAxkBAAIKDWm80hS0mpeZOgABlTG9UNpjvZI1WgACTgwAAiJJMFc40-Yhki2wlB4E",
    "CAACAgUAAxkBAAIKDmm80hnC_EQGNXEgg8bmiCWE32XLAALGCAAC0v05V82aflzlC23sHgQ",
    "CAACAgUAAxkBAAIKD2m80iHXNRg0a4YBB0Maz42ng4qTAAJxDAACyE0xV6aQfPRMeUokHgQ",
    "CAACAgUAAxkBAAIKEGm80iwLSwNsqJS6oiaK4qSfIekqAAIqCwACRA85V3w-iuqpGDgIHgQ",
    "CAACAgUAAxkBAAIKEWm80jUmiL-rSOgsVbvwGNoisya4AAJJDQACE6w5V--cufZUktLVHgQ",
    "CAACAgUAAxkBAAIKFmm80nwIlTijORY4AZPvzJN-uLW0AAKTDwAC8Bo4V2-xyEBcNmShHgQ",
    "CAACAgUAAxkBAAIKF2m80osFfSdFLU-i5rod-FsD4o1uAAL8CQACVOkwV5SIz-4RtYj2HgQ",
    "CAACAgUAAxkBAAIKGGm80pDOhtCP8mXTonXUlOLZ9mQzAALUCwACc045VwWrfNtzzpHvHgQ",
    "CAACAgUAAxkBAAIKG2m80qzrJSaBtSoAAasJasyuJ8X5VQACNwoAApLnMFfso_6k-QJv-x4E",
]

# ══════════════════════════════════════════════════════════════════════════════
#  EFFECT IDs  (sticker மட்டும்)
# ══════════════════════════════════════════════════════════════════════════════
PRIMARY_EFFECTS = [
    "5159385139981059251",   # ❤️  Hearts
    "5066970843586925436",   # 🔥 Flame
    "5070445174516318631",   # 🎉 Confetti
    "5104841245755180586",   # 😂 Laugh
    "5107584321108051015",   # 😍 Love Eyes
    "5104841245755180587",   # 😮 Wow
    "5107584321108051016",   # 😢 Sad
    "5104841245755180588",   # 👏 Clap
    "5107584321108051017",   # 🤯 Mind Blow
    "5046509860389126442",   # 💥 Explosion
    "5046589136895476101",   # ⚡ Lightning
    "5046589136895476102",   # 💫 Sparkle
    "5046589136895476103",   # 🌈 Rainbow
    "5046589136895476104",   # 🎶 Music
    "5046589136895476105",   # 🎯 Target
    "5046589136895476107",   # 💎 Diamond
    "5046589136895476108",   # 🚀 Rocket
    "5046589136895476109",   # 🌀 Spiral
    "5046589136895476110",   # 🌟 Star
]

SAFE_EFFECTS = [
    "5159385139981059251",   # ❤️  Hearts
    "5107584321108051014",   # 👍 Like
    "5070445174516318631",   # 🎉 Confetti
    "5066970843586925436",   # 🔥 Flame
]

BOT_API_URL = f"https://api.telegram.org/bot{config.BOT_TOKEN}"

# ══════════════════════════════════════════════════════════════════════════════
#  ANTI-SPAM
# ══════════════════════════════════════════════════════════════════════════════
user_last_message_time: dict = {}
user_command_count:     dict = {}
SPAM_THRESHOLD      = 2
SPAM_WINDOW_SECONDS = 5


# ══════════════════════════════════════════════════════════════════════════════
#  BOT API HELPER
# ══════════════════════════════════════════════════════════════════════════════
async def _api_post(endpoint: str, payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(f"{BOT_API_URL}/{endpoint}", json=payload)
            return resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  DELAYED DELETE
#  Sticker-ஐ immediately delete பண்ணாம 3s delay கொடுக்கிறோம்.
#  Reason: raw httpx effect message-ஓட animated layer finish ஆகும் முன்னே
#  delete பண்ணினா Telegram client UI state mismatch ஆகுது —
#  அதுக்கு அப்புறம் வர்ற buttons clickable ஆகாது.
# ══════════════════════════════════════════════════════════════════════════════
async def delayed_delete(chat_id: int, message_id: int) -> None:
    await asyncio.sleep(3)
    await _api_post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


async def _delete_msg(chat_id: int, message_id: int) -> None:
    await _api_post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


# ══════════════════════════════════════════════════════════════════════════════
#  SEND STICKER + EFFECT
#  Fallback: primary (3 tries) → safe → sticker alone → None
# ══════════════════════════════════════════════════════════════════════════════
async def send_sticker_with_effect(chat_id: int) -> int | None:
    # Ensure app.username is populated before private_panel() builds buttons
    try:
        if not app.username:
            await app.get_me()
    except Exception:
        pass

    sticker_id   = random.choice(START_STICKERS)
    primary_pool = random.sample(PRIMARY_EFFECTS, min(3, len(PRIMARY_EFFECTS)))

    for effect_id in primary_pool:
        data = await _api_post("sendSticker", {
            "chat_id":           chat_id,
            "sticker":           sticker_id,
            "message_effect_id": effect_id,
        })
        if data.get("ok"):
            return data["result"]["message_id"]

    for effect_id in SAFE_EFFECTS:
        data = await _api_post("sendSticker", {
            "chat_id":           chat_id,
            "sticker":           sticker_id,
            "message_effect_id": effect_id,
        })
        if data.get("ok"):
            return data["result"]["message_id"]

    # Sticker alone — no effect fallback
    data = await _api_post("sendSticker", {
        "chat_id": chat_id,
        "sticker": sticker_id,
    })
    if data.get("ok"):
        return data["result"]["message_id"]

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  /start — PRIVATE
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["start"]) & filters.private & ~BANNED_USERS)
@LanguageStart
async def start_pm(client, message: Message, _):

    bot_mention  = app.mention
    user_mention = message.from_user.mention

    try:
        caption = _["start_2"].format(user_mention, bot_mention)
    except Exception:
        caption = f"Hello {user_mention}\n\nI am {bot_mention}"

    # Anti-spam
    user_id      = message.from_user.id
    current_time = time()
    last_time    = user_last_message_time.get(user_id, 0)

    if current_time - last_time < SPAM_WINDOW_SECONDS:
        user_last_message_time[user_id] = current_time
        user_command_count[user_id]     = user_command_count.get(user_id, 0) + 1
        if user_command_count[user_id] > SPAM_THRESHOLD:
            hu = await message.reply_text(
                f"**{user_mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ sᴘᴀᴍ, ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**"
            )
            await asyncio.sleep(3)
            await hu.delete()
            return
    else:
        user_command_count[user_id]     = 1
        user_last_message_time[user_id] = current_time

    await add_served_user(user_id)

    # /start param handlers
    if len(message.text.split()) > 1:
        name = message.text.split(None, 1)[1]

        if name.startswith("help"):
            keyboard = first_page(_)
            return await message.reply_photo(
                photo=config.START_IMG_URL,
                caption=_["help_1"].format(config.SUPPORT_CHAT),
                reply_markup=keyboard,
            )

        if name.startswith("sud"):
            await sudoers_list(client=client, message=message, _=_)
            return

        if name.startswith("inf"):
            m = await message.reply_text("🔎")
            query = name.replace("info_", "", 1)
            query = f"https://www.youtube.com/watch?v={query}"
            results = VideosSearch(query, limit=1)
            for result in (await results.next())["result"]:
                title       = result["title"]
                duration    = result["duration"]
                views       = result["viewCount"]["short"]
                thumbnail   = result["thumbnails"][0]["url"].split("?")[0]
                channellink = result["channel"]["link"]
                channel     = result["channel"]["name"]
                link        = result["link"]
                published   = result["publishedTime"]
            searched_text = _["start_6"].format(
                title, duration, views, published, channellink, channel, bot_mention
            )
            key = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="💕 𝐕𖽹𖽴𖽞𖽙 🦋",
                        callback_data=f"downloadvideo {query}",
                    ),
                    InlineKeyboardButton(
                        text="💕 𝐀𖽪𖽴𖽹𖽙 🦋",
                        callback_data=f"downloadaudio {query}",
                    ),
                ],
                [
                    InlineKeyboardButton(text="🎧 sᴇᴇ ᴏɴ ʏᴏᴜᴛᴜʙᴇ 🎧", url=link),
                ],
            ])
            await m.delete()
            await app.send_photo(
                chat_id=message.chat.id,
                photo=thumbnail,
                caption=searched_text,
                reply_markup=key,
            )
            return

    # ── Normal start flow ─────────────────────────────────────────────────────

    # Step A — Sticker + full-screen effect
    sticker_msg_id = await send_sticker_with_effect(message.chat.id)
    # FIX 1: Let the effect animation fully render before next message
    await asyncio.sleep(0.6)

    # Step B — Ding ding animation
    vip = await message.reply_text("**ᴅιиg ᴅσиg ꨄ︎❣️.....**")
    for dots in [".❣️....", "..❣️...", "...❣️..", "....❣️.", ".....❣️"]:
        await asyncio.sleep(0.1)
        await vip.edit_text(f"**ᴅιиg ᴅσиg ꨄ︎{dots}**")
    await asyncio.sleep(0.05)
    await vip.delete()

    # Step C — Starting animation
    vips = await message.reply_text("**⚡ѕ**")
    for step in ["⚡ѕт", "⚡ѕтα", "⚡ѕтαя", "⚡ѕтαят", "⚡ѕтαятι", "⚡ѕтαятιи", "⚡ѕтαятιиg"]:
        await vips.edit_text(f"**{step}**")
        await asyncio.sleep(0.02)
    await vips.delete()

    # Step D — FIX 2: delayed delete (background task, don't block UI)
    # Immediate delete breaks Telegram client UI state after effect animation.
    if sticker_msg_id:
        asyncio.create_task(delayed_delete(message.chat.id, sticker_msg_id))

    # Step E — FIX 3: small gap before final message so UI state is clean
    #await asyncio.sleep(0.5)

    out = private_panel(_)
    await message.reply_photo(
        photo=config.START_IMG_URL,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(out),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  /start — GROUP
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.command(["start"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def start_gp(client, message: Message, _):
    out    = start_panel(_)
    BOT_UP = await bot_up_time()
    await message.reply_photo(
        photo=config.START_IMG_URL,
        caption=_["start_1"].format(app.mention, BOT_UP),
        reply_markup=InlineKeyboardMarkup(out),
    )
    await add_served_chat(message.chat.id)


# ══════════════════════════════════════════════════════════════════════════════
#  WELCOME HANDLER (new chat members)
# ══════════════════════════════════════════════════════════════════════════════
@app.on_message(filters.new_chat_members, group=-1)
async def welcome(client, message: Message):
    for member in message.new_chat_members:
        try:
            language = await get_lang(message.chat.id)
            _ = get_string(language)

            # 🔴 Ban check
            if await is_banned_user(member.id):
                try:
                    await message.chat.ban_member(member.id)
                except:
                    pass

            # ✅ BOT ADDED
            if member.id == app.id:

                # ❌ Not supergroup
                if message.chat.type != ChatType.SUPERGROUP:
                    await message.reply_text(_["start_4"])
                    await app.leave_chat(message.chat.id)
                    return

                # ❌ Blacklisted
                if message.chat.id in await blacklisted_chats():
                    await message.reply_text(
                        _["start_5"].format(
                            app.mention,
                            f"https://t.me/{app.username}?start=sudolist",
                            config.SUPPORT_CHAT,
                        ),
                        disable_web_page_preview=True,
                    )
                    await app.leave_chat(message.chat.id)
                    return

                await add_served_chat(message.chat.id)

                # 🔥 ASSISTANT AUTO JOIN LOGIC
                try:
                    userbot = await get_assistant(message.chat.id)

                    # 1️⃣ First check already inside
                    try:
                        member_check = await app.get_chat_member(
                            message.chat.id, userbot.id
                        )
                        if member_check:
                            await message.reply_text(
                                f"✅ Assistant already in group."
                            )
                            return
                    except:
                        pass

                    # 2️⃣ Try username join (best method)
                    if message.chat.username:
                        try:
                            await userbot.join_chat(message.chat.username)
                            await message.reply_text(
                                f"✅ Assistant joined via username."
                            )
                            return
                        except Exception as e:
                            print("Username join failed:", e)

                    # 3️⃣ Try invite link
                    try:
                        invitelink = await app.export_chat_invite_link(
                            message.chat.id
                        )
                        await asyncio.sleep(1)
                        await userbot.join_chat(invitelink)

                        await message.reply_text(
                            f"✅ Assistant joined via invite link."
                        )
                        return
                    except Exception as e:
                        print("Invite link failed:", e)

                    # ❌ FINAL FAIL
                    await message.reply_text(
                        f"❌ Make me admin with invite permission to add assistant."
                    )

                except Exception as e:
                    print("Assistant join error:", e)

                # 🎉 Welcome UI
                await message.reply_photo(
                    random.choice(SHASHA_PICS),
                    caption=_["start_3"].format(
                        message.from_user.first_name,
                        app.mention,
                        message.chat.title,
                        app.mention,
                    ),
                    reply_markup=InlineKeyboardMarkup(start_panel(_)),
                )

                await message.stop_propagation()

        except Exception as ex:
            print("WELCOME ERROR:", ex)
