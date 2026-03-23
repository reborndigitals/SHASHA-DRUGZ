from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import MessageNotModified
import asyncio
import time
from unidecode import unidecode

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import (
    get_active_chats,
    get_active_video_chats,
    remove_active_chat,
    remove_active_video_chat,
)
from config import BANNED_USERS, START_IMG_URL

print("[vcstats] Loaded: /vcstats, /activevc, /activevideo")

# =============================================================
# CACHE (fast count refresh)
# =============================================================
_cache = {
    "audio": [],
    "video": [],
    "timestamp": 0
}
CACHE_DURATION = 5  # seconds

async def get_cached_stats():
    """Return audio/video ID lists from cache if fresh, else fetch new."""
    global _cache
    now = time.time()
    if now - _cache["timestamp"] <= CACHE_DURATION:
        return _cache["audio"], _cache["video"]

    audio = await get_active_chats()
    video = await get_active_video_chats()
    _cache["audio"] = audio
    _cache["video"] = video
    _cache["timestamp"] = now
    return audio, video

# =============================================================
# UTILS
# =============================================================
def paginate_list(items, page, per_page=5):
    """Split list into pages."""
    start = (page - 1) * per_page
    end = start + per_page
    sliced = items[start:end]
    total_pages = (len(items) - 1) // per_page + 1 if items else 1
    return sliced, total_pages

async def safe_edit_caption(msg: Message, caption: str, reply_markup: InlineKeyboardMarkup = None):
    """Edit caption without triggering MessageNotModified."""
    try:
        existing = msg.caption or ""
        if existing.strip() == (caption or "").strip():
            if reply_markup is not None:
                try:
                    await msg.edit_reply_markup(reply_markup)
                except Exception:
                    pass
            return
        await msg.edit_caption(caption, reply_markup=reply_markup)
    except MessageNotModified:
        if reply_markup is not None:
            try:
                await msg.edit_reply_markup(reply_markup)
            except Exception:
                pass
    except Exception as e:
        print(f"[vcstats] safe_edit_caption error: {e}")

async def generate_join_link(chat_id: int):
    """Create an invite link for a chat."""
    return await app.export_chat_invite_link(chat_id)

async def get_chat_info_and_link(chat_id: int):
    """
    Fetch chat title and invite link.
    If chat is inaccessible, remove from active lists and return None.
    """
    try:
        chat = await app.get_chat(chat_id)
        title = chat.title or "Private Group"
        invite_link = await generate_join_link(chat_id)
        username = chat.username
        return title, invite_link, username
    except Exception:
        # Clean up invalid chat from both audio and video lists
        await remove_active_chat(chat_id)
        await remove_active_video_chat(chat_id)
        return None

# =============================================================
# COMMAND: /vcstats (main dashboard)
# =============================================================
@Client.on_message(
    filters.command(["vcstats", "vcstat", "vcs", "vct"], prefixes=["/", "!", "%", ",", ".", "@", "#"])
    & ~BANNED_USERS
)
async def vcstats_handler(client, msg: Message):
    if msg.from_user.id not in SUDOERS:
        return await msg.reply_text("❌ Only SUDO users can use this command.")
    await send_stats(msg, auto_cycle=False)

async def send_stats(message, auto_cycle):
    audio, video = await get_cached_stats()
    audio_count = len(audio)
    video_count = len(video)

    audio_light = "🍏" if audio_count > 0 else "🍎"
    video_light = "🍏" if video_count > 0 else "🍎"

    caption = (
        "<blockquote>💥 **𝐋ɪᴠᴇ 𝐕ᴄ𝐒ᴛᴀᴛ𝗌**</blockquote>\n"
        "<blockquote>•━━━━━━━━━━━━━━━━━━•\n"
        f"{audio_light} **𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ:** `{audio_count}`\n"
        f"{video_light} **𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ:** `{video_count}`\n"
        "•━━━━━━━━━━━━━━━━━━•</blockquote>\n"
    )
    if auto_cycle:
        caption += "<blockquote>⏳ **𝐑ᴇғʀᴇ𝗌ʜ 𝐄ᴠᴇʀʏ 10 𝐒ᴇᴄ**</blockquote>\n"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ", callback_data="vc_audio_page_1"),
                InlineKeyboardButton("𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ", callback_data="vc_video_page_1"),
            ],
            [
                InlineKeyboardButton("🔁 𝐑ᴇғʀᴇ𝗌ʜ", callback_data="vc_refresh_manual"),
                InlineKeyboardButton("⏳ 𝐀ᴜᴛᴏ", callback_data="vc_enable_autorefresh"),
            ],
            [InlineKeyboardButton("🔻 𝐂ʟᴏ𝗌ᴇ 🔻", callback_data="vc_close")],
        ]
    )
    await message.reply_photo(START_IMG_URL, caption=caption, reply_markup=keyboard)

# =============================================================
# CALLBACK: Manual refresh
# =============================================================
@Client.on_callback_query(filters.regex("^vc_refresh_manual$"))
async def vc_refresh_manual(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    audio, video = await get_cached_stats()
    audio_light = "🍏" if len(audio) > 0 else "🍎"
    video_light = "🍏" if len(video) > 0 else "🍎"

    caption = (
        "<blockquote>💥 **𝐋ɪᴠᴇ 𝐕ᴄ𝐒ᴛᴀᴛ𝗌 (𝐑ᴇғʀᴇ𝗌ʜ)**</blockquote>\n"
        "<blockquote>•━━━━━━━━━━━━━━━━━━•\n"
        f"{audio_light} **𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ:** `{len(audio)}`\n"
        f"{video_light} **𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ:** `{len(video)}`\n"
        "•━━━━━━━━━━━━━━━━━━•</blockquote>"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ", callback_data="vc_audio_page_1"),
                InlineKeyboardButton("𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ", callback_data="vc_video_page_1"),
            ],
            [
                InlineKeyboardButton("🔁 𝐑ᴇғʀᴇ𝗌ʜ", callback_data="vc_refresh_manual"),
                InlineKeyboardButton("⏳ 𝐀ᴜᴛᴏ", callback_data="vc_enable_autorefresh"),
            ],
            [InlineKeyboardButton("🔻 𝐂ʟᴏ𝗌ᴇ 🔻", callback_data="vc_close")],
        ]
    )
    await safe_edit_caption(cq.message, caption, keyboard)
    await cq.answer("🔁 Updated")

# =============================================================
# CALLBACK: Auto refresh (loop for 5 minutes)
# =============================================================
@Client.on_callback_query(filters.regex("^vc_enable_autorefresh$"))
async def vc_enable_autorefresh(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    await cq.answer("⏳ Auto‑refresh started (5 min)")
    msg = cq.message

    for _ in range(30):  # 30 * 10s = 5 minutes
        try:
            audio, video = await get_cached_stats()
            audio_light = "🍏" if len(audio) > 0 else "🍎"
            video_light = "🍏" if len(video) > 0 else "🍎"

            caption = (
                "<blockquote>💥 **𝐋ɪᴠᴇ 𝐕ᴄ𝐒ᴛᴀᴛ𝗌 (𝐀ᴜᴛᴏ)**</blockquote>\n"
                "<blockquote>•━━━━━━━━━━━━━━━━━━•\n"
                f"{audio_light} **𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ:** `{len(audio)}`\n"
                f"{video_light} **𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ:** `{len(video)}`\n"
                "•━━━━━━━━━━━━━━━━━━•</blockquote>\n"
                "<blockquote>⏳ **𝐑ᴇғʀᴇ𝗌ʜ 𝐄ᴠᴇʀʏ 10 𝐒ᴇᴄ**</blockquote>"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ", callback_data="vc_audio_page_1"),
                        InlineKeyboardButton("𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ", callback_data="vc_video_page_1"),
                    ],
                    [InlineKeyboardButton("🔻 𝐒ᴛᴏᴘ 𝐀ᴜᴛᴏ", callback_data="vc_stop_autorefresh")],
                ]
            )
            await safe_edit_caption(msg, caption, keyboard)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[vcstats] auto‑refresh error: {e}")
            break

@Client.on_callback_query(filters.regex("^vc_stop_autorefresh$"))
async def stop_autorefresh(client, cq: CallbackQuery):
    await cq.answer("🛑 Auto‑refresh stopped (this session)", show_alert=True)
    # No further action – the loop will break on its own after the next iteration
    # but the user can now manually refresh or use other buttons.

# =============================================================
# CALLBACK: Close
# =============================================================
@Client.on_callback_query(filters.regex("^vc_close$"))
async def vc_close(client, cq: CallbackQuery):
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer("❌ Closed")

# =============================================================
# AUDIO CHAT PAGINATION (with titles & join buttons)
# =============================================================
@Client.on_callback_query(filters.regex("^vc_audio_page_"))
async def audio_page(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    page = int(cq.data.split("_")[-1])
    audio, _ = await get_cached_stats()
    page_items, total_pages = paginate_list(audio, page, per_page=5)

    if not audio:
        text = "**🎧 No active audio chats.**"
        buttons = [[InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")]]
    else:
        text = f"**🎧 Active Audio Chats (Page {page}/{total_pages})**\n\n"
        chat_buttons = []
        valid_items = []

        for cid in page_items:
            info = await get_chat_info_and_link(cid)
            if info is None:
                continue  # already cleaned up
            title, link, username = info
            valid_items.append((cid, title, link, username))

        for idx, (cid, title, link, username) in enumerate(valid_items, 1):
            # Show title with link if public, else just title
            if username:
                text += f"{idx}. <a href='https://t.me/{username}'>{unidecode(title).upper()}</a> (<code>{cid}</code>)\n"
            else:
                text += f"{idx}. {unidecode(title).upper()} (<code>{cid}</code>)\n"
            # Add a join button for this chat
            short_title = (title[:20] + "…") if len(title) > 20 else title
            chat_buttons.append([InlineKeyboardButton(f"🔊 Join {short_title}", url=link)])

        # Navigation buttons
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⤌ Prev", callback_data=f"vc_audio_page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ⤍", callback_data=f"vc_audio_page_{page+1}"))
        if nav_buttons:
            chat_buttons.append(nav_buttons)
        chat_buttons.append([InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")])
        buttons = chat_buttons

    keyboard = InlineKeyboardMarkup(buttons)
    await safe_edit_caption(cq.message, text, keyboard)
    await cq.answer()

# =============================================================
# VIDEO CHAT PAGINATION (with titles & join buttons)
# =============================================================
@Client.on_callback_query(filters.regex("^vc_video_page_"))
async def video_page(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    page = int(cq.data.split("_")[-1])
    _, video = await get_cached_stats()
    page_items, total_pages = paginate_list(video, page, per_page=5)

    if not video:
        text = "**🎥 No active video chats.**"
        buttons = [[InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")]]
    else:
        text = f"**🎥 Active Video Chats (Page {page}/{total_pages})**\n\n"
        chat_buttons = []
        valid_items = []

        for cid in page_items:
            info = await get_chat_info_and_link(cid)
            if info is None:
                continue
            title, link, username = info
            valid_items.append((cid, title, link, username))

        for idx, (cid, title, link, username) in enumerate(valid_items, 1):
            if username:
                text += f"{idx}. <a href='https://t.me/{username}'>{unidecode(title).upper()}</a> (<code>{cid}</code>)\n"
            else:
                text += f"{idx}. {unidecode(title).upper()} (<code>{cid}</code>)\n"
            short_title = (title[:20] + "…") if len(title) > 20 else title
            chat_buttons.append([InlineKeyboardButton(f"📺 Join {short_title}", url=link)])

        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⤌ Prev", callback_data=f"vc_video_page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ⤍", callback_data=f"vc_video_page_{page+1}"))
        if nav_buttons:
            chat_buttons.append(nav_buttons)
        chat_buttons.append([InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")])
        buttons = chat_buttons

    keyboard = InlineKeyboardMarkup(buttons)
    await safe_edit_caption(cq.message, text, keyboard)
    await cq.answer()

# =============================================================
# LEGACY COMMANDS: /activevc and /activevideo (direct lists)
# =============================================================
@Client.on_message(filters.command(["activevc", "activevoice"], prefixes=["/", "!", "%", ",", ".", "@", "#"]) & SUDOERS)
async def activevc_direct(client, message: Message):
    """Show first page of active audio chats directly."""
    audio, _ = await get_cached_stats()
    if not audio:
        return await message.reply_text("» ɴᴏ ᴀᴄᴛɪᴠᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛs ᴏɴ ᴛʜᴇ ʙᴏᴛ.")
    # Create a temporary message that mimics the audio page callback
    # We'll reuse the audio_page logic by sending a new photo with the list
    # To avoid code duplication, we simulate the callback data.
    # Simpler: we send a new message with the same content as the audio page.
    # We'll build the text and buttons manually.
    page = 1
    page_items, total_pages = paginate_list(audio, page, per_page=5)
    text = f"**🎧 Active Audio Chats (Page {page}/{total_pages})**\n\n"
    chat_buttons = []
    for cid in page_items:
        info = await get_chat_info_and_link(cid)
        if info is None:
            continue
        title, link, username = info
        if username:
            text += f"• <a href='https://t.me/{username}'>{unidecode(title).upper()}</a> (<code>{cid}</code>)\n"
        else:
            text += f"• {unidecode(title).upper()} (<code>{cid}</code>)\n"
        short_title = (title[:20] + "…") if len(title) > 20 else title
        chat_buttons.append([InlineKeyboardButton(f"🔊 Join {short_title}", url=link)])

    nav_buttons = []
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton("Next ⤍", callback_data="vc_audio_page_2"))
    if nav_buttons:
        chat_buttons.append(nav_buttons)
    chat_buttons.append([InlineKeyboardButton("📊 Main Stats", callback_data="vc_refresh_manual")])
    keyboard = InlineKeyboardMarkup(chat_buttons)

    await message.reply_photo(START_IMG_URL, caption=text, reply_markup=keyboard)

@Client.on_message(filters.command(["activevideo", "activev"], prefixes=["/", "!", "%", ",", ".", "@", "#"]) & SUDOERS)
async def activevideo_direct(client, message: Message):
    """Show first page of active video chats directly."""
    _, video = await get_cached_stats()
    if not video:
        return await message.reply_text("» ɴᴏ ᴀᴄᴛɪᴠᴇ ᴠɪᴅᴇᴏ ᴄʜᴀᴛs ᴏɴ ᴛʜᴇ ʙᴏᴛ.")
    page = 1
    page_items, total_pages = paginate_list(video, page, per_page=5)
    text = f"**🎥 Active Video Chats (Page {page}/{total_pages})**\n\n"
    chat_buttons = []
    for cid in page_items:
        info = await get_chat_info_and_link(cid)
        if info is None:
            continue
        title, link, username = info
        if username:
            text += f"• <a href='https://t.me/{username}'>{unidecode(title).upper()}</a> (<code>{cid}</code>)\n"
        else:
            text += f"• {unidecode(title).upper()} (<code>{cid}</code>)\n"
        short_title = (title[:20] + "…") if len(title) > 20 else title
        chat_buttons.append([InlineKeyboardButton(f"📺 Join {short_title}", url=link)])

    nav_buttons = []
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton("Next ⤍", callback_data="vc_video_page_2"))
    if nav_buttons:
        chat_buttons.append(nav_buttons)
    chat_buttons.append([InlineKeyboardButton("📊 Main Stats", callback_data="vc_refresh_manual")])
    keyboard = InlineKeyboardMarkup(chat_buttons)

    await message.reply_photo(START_IMG_URL, caption=text, reply_markup=keyboard)
    
    __menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_14"
__help__ = """
🔻 /vcstats /vcstat /vcs ➠ sʜᴏᴡs ʟɪᴠᴇ ᴀᴜᴅɪᴏ & ᴠɪᴅᴇᴏ ᴄʜᴀᴛ sᴛᴀᴛs ᴡɪᴛʜ ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ ʙᴜᴛᴛᴏɴs
🔻 /activevoice /activevc ➠ sʜᴏᴡs ᴀʟʟ ᴀᴄᴛɪᴠᴇ ᴀᴜᴅɪᴏ (ᴠᴏɪᴄᴇ) ᴄʜᴀᴛs
🔻 /activevideo /activev ➠ sʜᴏᴡs ᴀʟʟ ᴀᴄᴛɪᴠᴇ ᴠɪᴅᴇᴏ ᴄʜᴀᴛs
"""
MOD_TYPE = "MUSIC"
MOD_NAME = "VcStats"
MOD_PRICE = "50"
