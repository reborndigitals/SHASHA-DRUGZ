# SHASHA_DRUGZ/dplugins/COMMON/bot/start.py
import time
from time import time
import asyncio
from pyrogram.errors import UserAlreadyParticipant, UserNotParticipant, PeerIdInvalid
import random
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from youtubesearchpython.__future__ import VideosSearch
import config
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
from SHASHA_DRUGZ.utils.inline import first_page, dprivate_panel, dstart_panel
from config import BANNED_USERS, SHASHA_PICS
from strings import get_string
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.bot_settings import get_start_image, get_start_message

# ── Spam guard ───────────────────────────────────────────────────────────────
user_last_message_time = {}
user_command_count = {}
SPAM_THRESHOLD = 2
SPAM_WINDOW_SECONDS = 5


def _is_spam(user_id: int) -> bool:
    current_time = time()
    last = user_last_message_time.get(user_id, 0)
    if current_time - last < SPAM_WINDOW_SECONDS:
        user_last_message_time[user_id] = current_time
        user_command_count[user_id] = user_command_count.get(user_id, 0) + 1
        return user_command_count[user_id] > SPAM_THRESHOLD
    else:
        user_command_count[user_id] = 1
        user_last_message_time[user_id] = current_time
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  ASSISTANT JOIN HELPER
#
#  THE ROOT FIX:
#  All get_chat_member / create_chat_invite_link / export_chat_invite_link
#  calls now use `client` (the deployed bot with admin rights in the group),
#  NOT `app` (the main bot which has no rights in the group).
#
#  The old code used `app` everywhere, so permission checks always returned
#  False even though the deployed bot had full admin rights, causing the
#  false "make me admin" message every single time.
# ─────────────────────────────────────────────────────────────────────────────
async def _ensure_assistant_joined(client: Client, chat_id: int) -> tuple[bool, str]:
    """
    Ensure the assistant userbot is a member of the group.
    Uses `client` (the deployed bot) for all Telegram API calls.

    Returns (success: bool, message_for_group: str).
    Empty string = no message needed (silent success or silent skip).
    """
    try:
        userbot = await get_assistant(chat_id)
    except Exception:
        return False, ""

    assistant_id = userbot.id

    # ── Check current membership using the DEPLOYED BOT (client), not app ────
    status = None
    try:
        member = await client.get_chat_member(chat_id, assistant_id)
        status = member.status
    except UserNotParticipant:
        status = None
    except Exception:
        # last resort: try app
        try:
            member = await app.get_chat_member(chat_id, assistant_id)
            status = member.status
        except UserNotParticipant:
            status = None
        except Exception:
            status = None

    # Any "in the chat" status → nothing to do
    if status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,  # in chat, just limited — do NOT try to rejoin
    ):
        return True, ""

    # Banned → assistant_guard.py handles this, skip here
    if status == ChatMemberStatus.BANNED:
        return False, ""

    # ── Not in chat → try to join ─────────────────────────────────────────────

    # Method A: join via public @username (no extra permission needed)
    try:
        chat = await client.get_chat(chat_id)
        if getattr(chat, "username", None):
            await userbot.join_chat(chat.username)
            return True, ""
    except UserAlreadyParticipant:
        return True, ""
    except Exception:
        pass

    # Method B: generate invite link using CLIENT (deployed bot has admin rights)
    invite_link = None
    try:
        link_obj = await client.create_chat_invite_link(chat_id)
        invite_link = link_obj.invite_link
    except Exception:
        try:
            invite_link = await client.export_chat_invite_link(chat_id)
        except Exception:
            pass

    if invite_link:
        try:
            await asyncio.sleep(1)
            await userbot.join_chat(invite_link)
            return True, ""
        except UserAlreadyParticipant:
            return True, ""
        except Exception:
            pass

    # Genuinely failed — only show the error message now
    return False, (
        f"**Please make me admin with 'Invite Users' permission so I can invite my "
        f"[Assistant](tg://openmessage?user_id={assistant_id}) to this group.**"
    )


# ── /start private ────────────────────────────────────────────────────────────
@Client.on_message(filters.command(["start"]) & filters.private & ~BANNED_USERS)
@LanguageStart
async def start_pm(client: Client, message: Message, _):
    user_id = message.from_user.id
    if _is_spam(user_id):
        hu = await message.reply_text(
            f"**{message.from_user.mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ ᴅᴏ sᴘᴀᴍ, "
            f"ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**"
        )
        await asyncio.sleep(3)
        await hu.delete()
        return

    await add_served_user(message.from_user.id)

    if len(message.text.split()) > 1:
        name = message.text.split(None, 1)[1]

        if name[0:4] == "help":
            keyboard = first_page(_)
            return await message.reply_photo(
                photo=config.START_IMG_URL,
                caption=_["help_1"].format(config.SUPPORT_CHAT),
                reply_markup=keyboard,
            )

        if name[0:3] == "sud":
            await sudoers_list(client=client, message=message, _=_)
            if await is_on_off(2):
                return await app.send_message(
                    chat_id=config.LOGGER_ID,
                    text=(
                        f"{message.from_user.mention} ᴊᴜsᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ "
                        f"ᴛᴏ ᴄʜᴇᴄᴋ <b>sᴜᴅᴏʟɪsᴛ</b>.\n\n"
                        f"<b>ᴜsᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n"
                        f"<b>ᴜsᴇʀɴᴀᴍᴇ :</b> @{message.from_user.username}"
                    ),
                )
            return

        if name[0:3] == "inf":
            m = await message.reply_text("🔎")
            query = str(name).replace("info_", "", 1)
            query = f"https://www.youtube.com/watch?v={query}"
            results = VideosSearch(query, limit=1)
            for result in (await results.next())["result"]:
                title = result["title"]
                duration = result["duration"]
                views = result["viewCount"]["short"]
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                channellink = result["channel"]["link"]
                channel = result["channel"]["name"]
                link = result["link"]
                published = result["publishedTime"]
            searched_text = _["start_6"].format(
                title, duration, views, published, channellink, channel,
                client.me.mention,
            )
            key = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(text="VIDEO", callback_data=f"downloadvideo {query}"),
                    InlineKeyboardButton(text="AUDIO", callback_data=f"downloadaudio {query}"),
                ],
                [
                    InlineKeyboardButton(text="🎧 sᴇᴇ ᴏɴ ʏᴏᴜᴛᴜʙᴇ 🎧", url=link),
                ],
            ])
            await m.delete()
            await client.send_photo(
                chat_id=message.chat.id,
                photo=thumbnail,
                caption=searched_text,
                reply_markup=key,
            )
            if await is_on_off(2):
                return await app.send_message(
                    chat_id=config.LOGGER_ID,
                    text=(
                        f"{message.from_user.mention} ᴊᴜsᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ "
                        f"ᴛᴏ ᴄʜᴇᴄᴋ <b>ᴛʀᴀᴄᴋ ɪɴғᴏʀᴍᴀᴛɪᴏɴ</b>.\n\n"
                        f"<b>ᴜsᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n"
                        f"<b>ᴜsᴇʀɴᴀᴍᴇ :</b> @{message.from_user.username}"
                    ),
                )
            return

    # Normal /start
    bot_id = client.me.id
    start_img = await get_start_image(bot_id)
    custom_msg = await get_start_message(bot_id)

    if custom_msg:
        caption = (
            custom_msg
            .replace("{mention}", message.from_user.mention)
            .replace("{bot}", client.me.mention)
        )
    else:
        caption = _["dstart_1"].format(message.from_user.mention, client.me.mention)

    out = await dprivate_panel(client, _, message.chat.id)
    await message.reply_photo(
        photo=start_img,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(out),
    )

    if await is_on_off(2):
        return await app.send_message(
            chat_id=config.LOGGER_ID,
            text=(
                f"{message.from_user.mention} ᴊᴜsᴛ sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ.\n\n"
                f"<b>ᴜsᴇʀ ɪᴅ :</b> <code>{message.from_user.id}</code>\n"
                f"<b>ᴜsᴇʀɴᴀᴍᴇ :</b> @{message.from_user.username}"
            ),
        )


# ── /start group ──────────────────────────────────────────────────────────────
@Client.on_message(filters.command(["start"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def start_gp(client: Client, message: Message, _):
    user_id = message.from_user.id
    if _is_spam(user_id):
        hu = await message.reply_text(
            f"**{message.from_user.mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ ᴅᴏ sᴘᴀᴍ, "
            f"ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**"
        )
        await asyncio.sleep(3)
        await hu.delete()
        return

    bot_id = client.me.id
    start_img = await get_start_image(bot_id)
    custom_msg = await get_start_message(bot_id)
    out = await dstart_panel(client, _, message.chat.id)
    BOT_UP = await bot_up_time()

    if custom_msg:
        caption = (
            custom_msg
            .replace("{mention}", message.from_user.mention)
            .replace("{bot}", client.me.mention)
        )
    else:
        caption = _["dstart_2"].format(message.from_user.mention, BOT_UP)

    await message.reply_photo(
        photo=start_img,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(out),
    )
    await add_served_chat(message.chat.id)

    # Assistant check — fully silent, uses client not app
    try:
        joined, join_msg = await _ensure_assistant_joined(client, message.chat.id)
        if join_msg:
            await message.reply_text(join_msg)
    except Exception:
        pass


# ── New member welcome ────────────────────────────────────────────────────────
@Client.on_message(filters.new_chat_members, group=-1)
async def welcome(client: Client, message: Message):
    for member in message.new_chat_members:
        try:
            language = await get_lang(message.chat.id)
            _ = get_string(language)

            if await is_banned_user(member.id):
                try:
                    await message.chat.ban_member(member.id)
                except Exception:
                    pass

            if member.id == client.me.id:
                if message.chat.type != ChatType.SUPERGROUP:
                    await message.reply_text(_["start_4"])
                    await client.leave_chat(message.chat.id)
                    return

                if message.chat.id in await blacklisted_chats():
                    await message.reply_text(
                        _["start_5"].format(
                            client.me.mention,
                            f"https://t.me/{client.me.username}?start=sudolist",
                            config.SUPPORT_CHAT,
                        ),
                        disable_web_page_preview=True,
                    )
                    await client.leave_chat(message.chat.id)
                    return

                start_img = await get_start_image(client.me.id)
                out = await dstart_panel(client, _, message.chat.id)

                # Assistant join — uses client for all API calls, not app
                try:
                    joined, join_msg = await _ensure_assistant_joined(client, message.chat.id)
                    if join_msg:
                        await message.reply_text(join_msg)
                except Exception:
                    pass

                await message.reply_photo(
                    random.choice(SHASHA_PICS),
                    caption=_["start_3"].format(
                        message.from_user.first_name,
                        client.me.mention,
                        message.chat.title,
                        client.me.mention,
                    ),
                    reply_markup=InlineKeyboardMarkup(out),
                )
                await add_served_chat(message.chat.id)
                await message.stop_propagation()

        except Exception as ex:
            print(ex)
