# SHASHA_DRUGZ/plugins/bot/start.py
from time import time
import asyncio
import random

import httpx
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
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

# ─── Assistant join error types ──────────────────────────────────────────────
from pyrogram.errors import (
    FloodWait,
    UserAlreadyParticipant,
    InviteHashExpired,
    InviteHashInvalid,
)

# ─── Animation module (separated) ────────────────────────────────────────────
from SHASHA_DRUGZ.plugins.PREMIUM.start_anim import (
    send_sticker_with_effect,
    run_start_animation,
)

# ══════════════════════════════════════════════════════════════════════════════
#  ANTI-SPAM
# ══════════════════════════════════════════════════════════════════════════════
user_last_message_time: dict = {}
user_command_count:     dict = {}
SPAM_THRESHOLD      = 2
SPAM_WINDOW_SECONDS = 5

# ══════════════════════════════════════════════════════════════════════════════
#  ASSISTANT JOIN HELPERS
# ══════════════════════════════════════════════════════════════════════════════
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds


async def has_invite_permission(chat_id: int) -> bool:
    try:
        bot    = await app.get_me()
        member = await app.get_chat_member(chat_id, bot.id)
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            return False
        if not member.privileges.can_invite_users:
            return False
        return True
    except Exception:
        return False


async def get_available_assistant(chat_id: int):
    try:
        return await get_assistant(chat_id)
    except Exception:
        return None


async def join_assistant(chat_id: int):
    userbot = await get_available_assistant(chat_id)
    if not userbot:
        return False, "No assistant available"

    # ✅ Already joined check
    try:
        member = await app.get_chat_member(chat_id, userbot.id)
        if member:
            return True, "Already in group"
    except Exception:
        pass

    # ✅ Username join
    try:
        chat = await app.get_chat(chat_id)
        if chat.username:
            await userbot.join_chat(chat.username)
            return True, "Joined via username"
    except UserAlreadyParticipant:
        return True, "Already in group"
    except Exception as e:
        print("Username join fail:", e)

    # ✅ Invite link join
    try:
        if not await has_invite_permission(chat_id):
            return False, "Bot needs invite permission"
        link = await app.export_chat_invite_link(chat_id)
        await asyncio.sleep(1)
        await userbot.join_chat(link)
        return True, "Joined via invite"
    except UserAlreadyParticipant:
        return True, "Already in group"
    except (InviteHashExpired, InviteHashInvalid):
        return False, "Invite link invalid"
    except Exception as e:
        print("Invite join fail:", e)

    return False, "Join failed"


async def auto_retry_join(chat_id: int) -> bool:
    for i in range(MAX_RETRIES):
        try:
            success, msg = await join_assistant(chat_id)
            if success:
                print(f"[ASSISTANT JOINED] {chat_id} → {msg}")
                return True
            print(f"[RETRY {i + 1}] {msg}")
            await asyncio.sleep(RETRY_DELAY)
        except FloodWait as e:
            print(f"[FLOODWAIT] Sleeping {e.value}s")
            await asyncio.sleep(e.value)
        except Exception as e:
            print("Retry error:", e)
            await asyncio.sleep(5)
    print(f"[FAILED] Assistant join failed in {chat_id}")
    return False


async def instant_assistant_join(chat_id: int) -> None:
    asyncio.create_task(auto_retry_join(chat_id))


async def ensure_assistant_joined(message: Message) -> None:
    chat_id = message.chat.id
    try:
        userbot = await get_assistant(chat_id)
    except Exception:
        await message.reply_text("❌ Assistant not available.")
        return

    msg = await message.reply_text(
        f"🔍 **Checking [Assistant](tg://openmessage?user_id={userbot.id})...**"
    )

    # Always kick off background retry
    asyncio.create_task(auto_retry_join(chat_id))

    # Check if already joined
    try:
        await app.get_chat_member(chat_id, userbot.id)
        await msg.edit_text(
            f"✅ **[Assistant](tg://openmessage?user_id={userbot.id}) already in this group.**"
        )
        return
    except Exception:
        pass

    # Attempt immediate join
    success, result = await join_assistant(chat_id)
    if success:
        await msg.edit_text(
            f"✅ **[Assistant](tg://openmessage?user_id={userbot.id}) joined successfully!**"
        )
    else:
        await msg.edit_text(
            f"⚠️ **{result}**\n🔄 Retrying in background..."
        )


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

    # ── Anti-spam ─────────────────────────────────────────────────────────────
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

    # ── /start param handlers ─────────────────────────────────────────────────
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
            m     = await message.reply_text("🔎")
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
    # Ensure app.username is populated before private_panel() builds buttons
    try:
        if not app.username:
            await app.get_me()
    except Exception:
        pass

    # Run full-screen animation (sticker + effect + ding dong + starting text)
    await run_start_animation(message)

    # Final welcome photo
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
    # Ensure assistant present when /start is used in a group
    await ensure_assistant_joined(message)


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
                except Exception:
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

                # Ensure assistant joined (with UI feedback)
                await ensure_assistant_joined(message)
                # Extra: fire-and-forget background retry
                await instant_assistant_join(message.chat.id)

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
