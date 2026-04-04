import asyncio
import time
from logging import getLogger

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.raw import functions
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from unidecode import unidecode

from config import BANNED_USERS, START_IMG_URL
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import (
    get_active_chats,
    get_active_video_chats,
    remove_active_chat,
    remove_active_video_chat,
)

LOGGER = getLogger(__name__)
print("[vcstats] Loaded: /vcstats, /activevc, /activevideo")


# ════════════════════════════════════════════
# REAL-TIME LIVE VC DETECTION
# ════════════════════════════════════════════

async def is_vc_actually_active(chat_id: int) -> bool:
    """
    Check if there is an ACTUAL live group call in a chat right now
    using the raw Telegram API. This is the ground truth — not the DB.
    """
    try:
        full = await app.invoke(
            functions.channels.GetFullChannel(
                channel=await app.resolve_peer(chat_id)
            )
        )
        call = getattr(full.full_chat, "call", None)
        return call is not None
    except Exception as e:
        LOGGER.debug(f"is_vc_actually_active error for {chat_id}: {e}")
        return False


async def get_live_active_chats():
    """
    Cross-reference DB active chats with real Telegram API.
    Returns only chats where a live VC is actually running.
    Stale DB entries (bot left but DB not cleaned) are auto-removed.
    """
    db_audio = await get_active_chats()
    db_video = await get_active_video_chats()

    # Combine and deduplicate all tracked chats
    all_chat_ids = list(set(db_audio + db_video))

    live_audio = []
    live_video = []

    async def check_chat(chat_id):
        alive = await is_vc_actually_active(chat_id)
        if alive:
            if chat_id in db_audio:
                live_audio.append(chat_id)
            if chat_id in db_video:
                live_video.append(chat_id)
        else:
            # VC is gone — clean up stale DB entries silently
            if chat_id in db_audio:
                await remove_active_chat(chat_id)
            if chat_id in db_video:
                await remove_active_video_chat(chat_id)
            LOGGER.debug(f"Removed stale VC entry for chat {chat_id}")

    # Run all checks concurrently for speed
    await asyncio.gather(*[check_chat(cid) for cid in all_chat_ids], return_exceptions=True)

    return live_audio, live_video


# ════════════════════════════════════════════
# CACHE (avoid hammering API on every button press)
# ════════════════════════════════════════════

_cache = {
    "audio": [],
    "video": [],
    "timestamp": 0,
}
CACHE_DURATION = 10  # seconds


async def get_cached_stats(force_refresh: bool = False):
    """Return live audio/video ID lists. Refreshes from real API if cache is stale."""
    global _cache
    now = time.time()
    if not force_refresh and (now - _cache["timestamp"]) <= CACHE_DURATION:
        return _cache["audio"], _cache["video"]

    audio, video = await get_live_active_chats()
    _cache["audio"] = audio
    _cache["video"] = video
    _cache["timestamp"] = now
    return audio, video


# ════════════════════════════════════════════
# UTILS
# ════════════════════════════════════════════

def paginate_list(items, page, per_page=5):
    """Split list into pages. Returns (page_items, total_pages)."""
    start = (page - 1) * per_page
    end = start + per_page
    sliced = items[start:end]
    total_pages = max(1, (len(items) - 1) // per_page + 1) if items else 1
    return sliced, total_pages


async def safe_edit_caption(
    msg: Message,
    caption: str,
    reply_markup: InlineKeyboardMarkup = None,
):
    """Edit caption safely without triggering MessageNotModified."""
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
        LOGGER.debug(f"safe_edit_caption error: {e}")


async def get_chat_info_and_link(chat_id: int):
    """
    Fetch chat title and invite link.
    Returns (title, invite_link, username) or None if chat is inaccessible.
    """
    try:
        chat = await app.get_chat(chat_id)
        title = chat.title or "Private Group"
        username = chat.username
        try:
            invite_link = await app.export_chat_invite_link(chat_id)
        except Exception:
            invite_link = f"https://t.me/{username}" if username else None
        return title, invite_link, username
    except Exception as e:
        LOGGER.debug(f"get_chat_info_and_link error for {chat_id}: {e}")
        await remove_active_chat(chat_id)
        await remove_active_video_chat(chat_id)
        return None


def build_main_keyboard(auto: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🎧 𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ", callback_data="vc_audio_page_1"),
            InlineKeyboardButton("🎥 𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ", callback_data="vc_video_page_1"),
        ],
        [
            InlineKeyboardButton("🔁 𝐑ᴇғʀᴇ𝗌ʜ", callback_data="vc_refresh_manual"),
            InlineKeyboardButton("⏳ 𝐀ᴜᴛᴏ", callback_data="vc_enable_autorefresh"),
        ],
        [InlineKeyboardButton("🔻 𝐂ʟᴏ𝗌ᴇ 🔻", callback_data="vc_close")],
    ]
    if auto:
        rows[1] = [InlineKeyboardButton("🛑 𝐒ᴛᴏᴘ 𝐀ᴜᴛᴏ", callback_data="vc_stop_autorefresh")]
    return InlineKeyboardMarkup(rows)


def build_stats_caption(audio: list, video: list, mode: str = "") -> str:
    audio_count = len(audio)
    video_count = len(video)
    audio_light = "🍏" if audio_count > 0 else "🍎"
    video_light = "🍏" if video_count > 0 else "🍎"
    mode_tag = f" ({mode})" if mode else ""
    return (
        f"<blockquote>💥 <b>𝐋ɪᴠᴇ 𝐕ᴄ𝐒ᴛᴀᴛ𝗌{mode_tag}</b></blockquote>\n"
        f"<blockquote>•━━━━━━━━━━━━━━━━━━•\n"
        f"{audio_light} <b>𝐀ᴜᴅɪᴏ 𝐂ʜᴀᴛ:</b> <code>{audio_count}</code>\n"
        f"{video_light} <b>𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ:</b> <code>{video_count}</code>\n"
        f"•━━━━━━━━━━━━━━━━━━•</blockquote>"
    )


# ════════════════════════════════════════════
# COMMAND: /vcstats
# ════════════════════════════════════════════

@Client.on_message(
    filters.command(
        ["vcstats", "vcstat", "vcs", "vct"],
        prefixes=["/", "!", "%", ",", ".", "@", "#"],
    )
    & ~BANNED_USERS
)
async def vcstats_handler(client, msg: Message):
    if msg.from_user.id not in SUDOERS:
        return await msg.reply_text("❌ Only SUDO users can use this command.")

    wait = await msg.reply_text("⏳ Fetching live VC data...")
    audio, video = await get_cached_stats(force_refresh=True)
    caption = build_stats_caption(audio, video)
    keyboard = build_main_keyboard()

    try:
        await wait.delete()
    except Exception:
        pass

    await msg.reply_photo(
        START_IMG_URL,
        caption=caption,
        reply_markup=keyboard,
        #parse_mode="html",
    )


# ════════════════════════════════════════════
# CALLBACK: Manual Refresh
# ════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^vc_refresh_manual$"))
async def vc_refresh_manual(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    await cq.answer("🔁 Refreshing...")
    audio, video = await get_cached_stats(force_refresh=True)
    caption = build_stats_caption(audio, video, mode="Refreshed")
    await safe_edit_caption(cq.message, caption, build_main_keyboard())


# ════════════════════════════════════════════
# CALLBACK: Auto Refresh (5 minutes, 10s interval)
# ════════════════════════════════════════════

_auto_refresh_active: set = set()  # track which messages have auto-refresh running


@Client.on_callback_query(filters.regex("^vc_enable_autorefresh$"))
async def vc_enable_autorefresh(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    msg_id = cq.message.id
    if msg_id in _auto_refresh_active:
        return await cq.answer("⏳ Already running!", show_alert=True)

    await cq.answer("⏳ Auto‑refresh started for 5 minutes")
    _auto_refresh_active.add(msg_id)
    msg = cq.message

    for _ in range(30):  # 30 × 10s = 5 minutes
        if msg_id not in _auto_refresh_active:
            break
        try:
            audio, video = await get_cached_stats(force_refresh=True)
            caption = build_stats_caption(audio, video, mode="Auto")
            keyboard = build_main_keyboard(auto=True)
            await safe_edit_caption(msg, caption, keyboard)
        except Exception as e:
            LOGGER.debug(f"auto-refresh error: {e}")
            break
        await asyncio.sleep(10)

    _auto_refresh_active.discard(msg_id)

    # Restore normal keyboard after auto ends
    try:
        audio, video = await get_cached_stats()
        caption = build_stats_caption(audio, video)
        await safe_edit_caption(msg, caption, build_main_keyboard())
    except Exception:
        pass


@Client.on_callback_query(filters.regex("^vc_stop_autorefresh$"))
async def stop_autorefresh(client, cq: CallbackQuery):
    msg_id = cq.message.id
    _auto_refresh_active.discard(msg_id)
    await cq.answer("🛑 Auto‑refresh stopped", show_alert=True)


# ════════════════════════════════════════════
# CALLBACK: Close
# ════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^vc_close$"))
async def vc_close(client, cq: CallbackQuery):
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer("❌ Closed")


# ════════════════════════════════════════════
# CALLBACK: Audio Chat Pagination
# ════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^vc_audio_page_"))
async def audio_page(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    page = int(cq.data.split("_")[-1])
    audio, _ = await get_cached_stats()
    page_items, total_pages = paginate_list(audio, page, per_page=5)

    if not audio:
        text = "<b>🎧 No active audio chats right now.</b>"
        buttons = [[InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")]]
    else:
        text = f"<b>🎧 Active Audio Chats (Page {page}/{total_pages})</b>\n\n"
        chat_buttons = []

        for idx, cid in enumerate(page_items, 1):
            info = await get_chat_info_and_link(cid)
            if info is None:
                continue
            title, link, username = info
            display = unidecode(title).upper()
            if username:
                text += f"{idx}. <a href='https://t.me/{username}'>{display}</a> (<code>{cid}</code>)\n"
            else:
                text += f"{idx}. {display} (<code>{cid}</code>)\n"
            short_title = (title[:20] + "…") if len(title) > 20 else title
            if link:
                chat_buttons.append([InlineKeyboardButton(f"🔊 Join {short_title}", url=link)])

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⤌ Prev", callback_data=f"vc_audio_page_{page - 1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next ⤍", callback_data=f"vc_audio_page_{page + 1}"))
        if nav:
            chat_buttons.append(nav)
        chat_buttons.append([InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")])
        buttons = chat_buttons

    await safe_edit_caption(cq.message, text, InlineKeyboardMarkup(buttons))
    await cq.answer()


# ════════════════════════════════════════════
# CALLBACK: Video Chat Pagination
# ════════════════════════════════════════════

@Client.on_callback_query(filters.regex("^vc_video_page_"))
async def video_page(client, cq: CallbackQuery):
    if cq.from_user.id not in SUDOERS:
        return await cq.answer("❌ Unauthorized", show_alert=True)

    page = int(cq.data.split("_")[-1])
    _, video = await get_cached_stats()
    page_items, total_pages = paginate_list(video, page, per_page=5)

    if not video:
        text = "<b>🎥 No active video chats right now.</b>"
        buttons = [[InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")]]
    else:
        text = f"<b>🎥 Active Video Chats (Page {page}/{total_pages})</b>\n\n"
        chat_buttons = []

        for idx, cid in enumerate(page_items, 1):
            info = await get_chat_info_and_link(cid)
            if info is None:
                continue
            title, link, username = info
            display = unidecode(title).upper()
            if username:
                text += f"{idx}. <a href='https://t.me/{username}'>{display}</a> (<code>{cid}</code>)\n"
            else:
                text += f"{idx}. {display} (<code>{cid}</code>)\n"
            short_title = (title[:20] + "…") if len(title) > 20 else title
            if link:
                chat_buttons.append([InlineKeyboardButton(f"📺 Join {short_title}", url=link)])

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⤌ Prev", callback_data=f"vc_video_page_{page - 1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("Next ⤍", callback_data=f"vc_video_page_{page + 1}"))
        if nav:
            chat_buttons.append(nav)
        chat_buttons.append([InlineKeyboardButton("🔻 𝐁ᴀᴄᴋ", callback_data="vc_refresh_manual")])
        buttons = chat_buttons

    await safe_edit_caption(cq.message, text, InlineKeyboardMarkup(buttons))
    await cq.answer()


# ════════════════════════════════════════════
# LEGACY COMMANDS: /activevc and /activevideo
# ════════════════════════════════════════════

@Client.on_message(
    filters.command(
        ["activevc", "activevoice"],
        prefixes=["/", "!", "%", ",", ".", "@", "#"],
    )
    & SUDOERS
)
async def activevc_direct(client, message: Message):
    wait = await message.reply_text("⏳ Checking live audio chats...")
    audio, _ = await get_cached_stats(force_refresh=True)
    try:
        await wait.delete()
    except Exception:
        pass

    if not audio:
        return await message.reply_text("» ɴᴏ ᴀᴄᴛɪᴠᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛs ᴏɴ ᴛʜᴇ ʙᴏᴛ.")

    page_items, total_pages = paginate_list(audio, 1, per_page=5)
    text = f"<b>🎧 Active Audio Chats (Page 1/{total_pages})</b>\n\n"
    chat_buttons = []

    for cid in page_items:
        info = await get_chat_info_and_link(cid)
        if info is None:
            continue
        title, link, username = info
        display = unidecode(title).upper()
        if username:
            text += f"• <a href='https://t.me/{username}'>{display}</a> (<code>{cid}</code>)\n"
        else:
            text += f"• {display} (<code>{cid}</code>)\n"
        short_title = (title[:20] + "…") if len(title) > 20 else title
        if link:
            chat_buttons.append([InlineKeyboardButton(f"🔊 Join {short_title}", url=link)])

    if total_pages > 1:
        chat_buttons.append([InlineKeyboardButton("Next ⤍", callback_data="vc_audio_page_2")])
    chat_buttons.append([InlineKeyboardButton("📊 Main Stats", callback_data="vc_refresh_manual")])

    await message.reply_photo(
        START_IMG_URL,
        caption=text,
        reply_markup=InlineKeyboardMarkup(chat_buttons),
        #parse_mode="html",
    )


@Client.on_message(
    filters.command(
        ["activevideo", "activev"],
        prefixes=["/", "!", "%", ",", ".", "@", "#"],
    )
    & SUDOERS
)
async def activevideo_direct(client, message: Message):
    wait = await message.reply_text("⏳ Checking live video chats...")
    _, video = await get_cached_stats(force_refresh=True)
    try:
        await wait.delete()
    except Exception:
        pass

    if not video:
        return await message.reply_text("» ɴᴏ ᴀᴄᴛɪᴠᴇ ᴠɪᴅᴇᴏ ᴄʜᴀᴛs ᴏɴ ᴛʜᴇ ʙᴏᴛ.")

    page_items, total_pages = paginate_list(video, 1, per_page=5)
    text = f"<b>🎥 Active Video Chats (Page 1/{total_pages})</b>\n\n"
    chat_buttons = []

    for cid in page_items:
        info = await get_chat_info_and_link(cid)
        if info is None:
            continue
        title, link, username = info
        display = unidecode(title).upper()
        if username:
            text += f"• <a href='https://t.me/{username}'>{display}</a> (<code>{cid}</code>)\n"
        else:
            text += f"• {display} (<code>{cid}</code>)\n"
        short_title = (title[:20] + "…") if len(title) > 20 else title
        if link:
            chat_buttons.append([InlineKeyboardButton(f"📺 Join {short_title}", url=link)])

    if total_pages > 1:
        chat_buttons.append([InlineKeyboardButton("Next ⤍", callback_data="vc_video_page_2")])
    chat_buttons.append([InlineKeyboardButton("📊 Main Stats", callback_data="vc_refresh_manual")])

    await message.reply_photo(
        START_IMG_URL,
        caption=text,
        reply_markup=InlineKeyboardMarkup(chat_buttons),
        #parse_mode="html",
    )


# ════════════════════════════════════════════
# MODULE METADATA
# ════════════════════════════════════════════

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
