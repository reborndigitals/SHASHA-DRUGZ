import asyncio
from logging import getLogger
from typing import Dict, Set
import random

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.raw import functions

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.core.mongo import mongodb

LOGGER = getLogger(__name__)

# --- Global State ---
vc_active_users: Dict[int, Set[int]] = {}
active_vc_chats: Set[int] = set()
vc_logging_status: Dict[int, bool] = {}

# --- Database Collection ---
vcloggerdb = mongodb.vclogger

# --- Config ---
PREFIXES = ["/", "!", "%", ",", ".", "@", "#"]


# ════════════════════════════════════════════
# DATABASE FUNCTIONS
# ════════════════════════════════════════════

async def load_vc_logger_status():
    """Load all VC logger statuses from DB and start monitors for enabled chats."""
    try:
        enabled_chats = []
        async for doc in vcloggerdb.find({}):
            chat_id = doc.get("chat_id")
            status = doc.get("status", False)
            if chat_id is None:
                continue
            vc_logging_status[chat_id] = status
            if status:
                enabled_chats.append(chat_id)

        for chat_id in enabled_chats:
            asyncio.create_task(check_and_monitor_vc(chat_id))

        LOGGER.info(f"VC Logger: Loaded {len(enabled_chats)} active chat(s).")
    except Exception as e:
        LOGGER.error(f"VC Logger load_vc_logger_status error: {e}")


async def save_vc_logger_status(chat_id: int, status: bool):
    """Persist VC logger status for a chat."""
    try:
        await vcloggerdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "status": status}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.error(f"VC Logger save_vc_logger_status error for {chat_id}: {e}")


async def get_vc_logger_status(chat_id: int) -> bool:
    """Return the current VC logger status for a chat (cached or from DB).
    Defaults to True (enabled) if no record exists for the chat."""
    if chat_id in vc_logging_status:
        return vc_logging_status[chat_id]
    try:
        doc = await vcloggerdb.find_one({"chat_id": chat_id})
        if doc:
            status = doc.get("status", True)
            vc_logging_status[chat_id] = status
            return status
    except Exception as e:
        LOGGER.error(f"get_vc_logger_status error for {chat_id}: {e}")
    # No DB record found — default to enabled
    vc_logging_status[chat_id] = True
    return True


# ════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════

def to_small_caps(text: str) -> str:
    mapping = {
        "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
        "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
        "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
        "s": "s", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
        "y": "ʏ", "z": "ᴢ",
        "A": "ᴀ", "B": "ʙ", "C": "ᴄ", "D": "ᴅ", "E": "ᴇ", "F": "ꜰ",
        "G": "ɢ", "H": "ʜ", "I": "ɪ", "J": "ᴊ", "K": "ᴋ", "L": "ʟ",
        "M": "ᴍ", "N": "ɴ", "O": "ᴏ", "P": "ᴘ", "Q": "ǫ", "R": "ʀ",
        "S": "s", "T": "ᴛ", "U": "ᴜ", "V": "ᴠ", "W": "ᴡ", "X": "x",
        "Y": "ʏ", "Z": "ᴢ",
    }
    return "".join(mapping.get(c, c) for c in text)


async def delete_after_delay(message: Message, delay: int):
    """Delete a message after `delay` seconds."""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass  # Message may already be deleted


# ════════════════════════════════════════════
# CORE LOGIC
# ════════════════════════════════════════════

async def get_group_call_participants(userbot, peer):
    """Fetch current VC participants via raw API. Returns list (empty if no VC)."""
    try:
        full_chat = await userbot.invoke(
            functions.channels.GetFullChannel(channel=peer)
        )
        if not hasattr(full_chat.full_chat, "call") or not full_chat.full_chat.call:
            return []
        call = full_chat.full_chat.call
        participants = await userbot.invoke(
            functions.phone.GetGroupParticipants(
                call=call, ids=[], sources=[], offset="", limit=100
            )
        )
        return participants.participants
    except Exception as e:
        err = str(e).upper()
        # Flood wait or no call — these are expected, don't log as errors
        if any(
            x in err
            for x in ["420", "GROUPCALL_NOT_FOUND", "CALL_NOT_FOUND", "NO_GROUPCALL"]
        ):
            return []
        LOGGER.debug(f"get_group_call_participants unexpected error: {e}")
        return []


async def monitor_vc_chat(chat_id: int):
    """
    Background task: polls VC participants every 5s for a chat.
    Stops automatically when logging is disabled or chat leaves active set.
    """
    LOGGER.info(f"VC monitor started for chat {chat_id}")
    try:
        userbot = await get_assistant(chat_id)
        if not userbot:
            LOGGER.warning(
                f"monitor_vc_chat: No assistant for chat {chat_id}. Stopping monitor."
            )
            active_vc_chats.discard(chat_id)
            return

        while chat_id in active_vc_chats and await get_vc_logger_status(chat_id):
            try:
                peer = await userbot.resolve_peer(chat_id)
                participants_list = await get_group_call_participants(userbot, peer)

                new_users: Set[int] = set()
                for p in participants_list:
                    if hasattr(p, "peer") and hasattr(p.peer, "user_id"):
                        new_users.add(p.peer.user_id)

                current_users = vc_active_users.get(chat_id, set())
                joined = new_users - current_users
                left = current_users - new_users

                if joined or left:
                    tasks = []
                    for user_id in joined:
                        tasks.append(handle_user_join(chat_id, user_id, userbot))
                    for user_id in left:
                        tasks.append(handle_user_leave(chat_id, user_id, userbot))
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

                vc_active_users[chat_id] = new_users

            except Exception as e:
                LOGGER.debug(f"monitor_vc_chat poll error in chat {chat_id}: {e}")

            await asyncio.sleep(5)

    except Exception as e:
        LOGGER.error(f"monitor_vc_chat fatal error for chat {chat_id}: {e}")
    finally:
        # Always clean up on exit
        active_vc_chats.discard(chat_id)
        vc_active_users.pop(chat_id, None)
        LOGGER.info(f"VC monitor stopped for chat {chat_id}")


async def check_and_monitor_vc(chat_id: int):
    """
    Start a VC monitor task for a chat if not already running.
    Validates assistant availability before starting.
    """
    if not await get_vc_logger_status(chat_id):
        return

    if chat_id in active_vc_chats:
        return  # Already monitoring

    try:
        userbot = await get_assistant(chat_id)
        if not userbot:
            LOGGER.warning(
                f"check_and_monitor_vc: No assistant for chat {chat_id}. "
                f"Auto-disabling VC logger."
            )
            vc_logging_status[chat_id] = False
            await save_vc_logger_status(chat_id, False)
            return

        active_vc_chats.add(chat_id)
        asyncio.create_task(monitor_vc_chat(chat_id))

    except Exception as e:
        LOGGER.error(f"check_and_monitor_vc error for chat {chat_id}: {e}")
        active_vc_chats.discard(chat_id)


# ════════════════════════════════════════════
# JOIN / LEAVE HANDLERS
# ════════════════════════════════════════════

async def handle_user_join(chat_id: int, user_id: int, userbot):
    try:
        user = await userbot.get_users(user_id)
        name = (user.first_name or "Someone").strip()
        mention = f'<a href="tg://user?id={user_id}"><b>{to_small_caps(name)}</b></a>'
        messages = [
            f"🎤 {mention} <b>ᴊᴜsᴛ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ᴠᴄ – ʟᴇᴛ's ᴍᴀᴋᴇ ɪᴛ ʟɪᴠᴇʟʏ! 🎶</b>",
            f"✨ {mention} <b>ɪs ɴᴏᴡ ɪɴ ᴛʜᴇ ᴠᴄ – ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 💫</b>",
            f"🎵 {mention} <b>ʜᴀs ᴊᴏɪɴᴇᴅ – ʟᴇᴛ's ʀᴏᴄᴋ ᴛʜɪs ᴠɪʙᴇ! 🔥</b>",
        ]
        sent = await app.send_message(
            chat_id, random.choice(messages), parse_mode="html"
        )
        asyncio.create_task(delete_after_delay(sent, 10))
    except Exception as e:
        LOGGER.debug(f"handle_user_join error for user {user_id} in chat {chat_id}: {e}")


async def handle_user_leave(chat_id: int, user_id: int, userbot):
    try:
        user = await userbot.get_users(user_id)
        name = (user.first_name or "Someone").strip()
        mention = f'<a href="tg://user?id={user_id}"><b>{to_small_caps(name)}</b></a>'
        messages = [
            f"👋 {mention} <b>ʟᴇғᴛ ᴛʜᴇ ᴠᴄ – ʜᴏᴘᴇ ᴛᴏ sᴇᴇ ʏᴏᴜ ʙᴀᴄᴋ sᴏᴏɴ! 🌟</b>",
            f"🚪 {mention} <b>sᴛᴇᴘᴘᴇᴅ ᴏᴜᴛ – ᴅᴏɴ'ᴛ ᴛᴀᴋᴇ ᴛᴏᴏ ʟᴏɴɢ! 💖</b>",
            f"✌️ {mention} <b>sᴀɪᴅ ɢᴏᴏᴅʙʏᴇ – ᴄᴏᴍᴇ ʙᴀᴄᴋ sᴏᴏɴ! 🎶</b>",
        ]
        sent = await app.send_message(
            chat_id, random.choice(messages), parse_mode="html"
        )
        asyncio.create_task(delete_after_delay(sent, 10))
    except Exception as e:
        LOGGER.debug(f"handle_user_leave error for user {user_id} in chat {chat_id}: {e}")


# ════════════════════════════════════════════
# COMMAND HANDLERS
# ════════════════════════════════════════════

@Client.on_message(filters.command("vclogger", prefixes=PREFIXES) & filters.group)
async def vclogger_command(_, message: Message):
    chat_id = message.chat.id
    args = message.text.split()
    status = await get_vc_logger_status(chat_id)
    current_state_ui = to_small_caps("Enabled" if status else "Disabled")

    if len(args) == 1:
        text = (
            f"📌 <b>VC Logger Status:</b> <b>{current_state_ui}</b>\n\n"
            f"Usage: <b>/vclogger on</b> | <b>/vclogger off</b>"
        )
        await message.reply(text, parse_mode="html", disable_web_page_preview=True)

    elif len(args) >= 2:
        arg = args[1].lower()

        if arg in ("on", "enable", "yes"):
            vc_logging_status[chat_id] = True
            await save_vc_logger_status(chat_id, True)
            await message.reply(
                "✅ <b>VC Logging Enabled!</b>\n"
                "ɪ ᴡɪʟʟ ɴᴏᴡ ᴛʀᴀᴄᴋ ᴊᴏɪɴs & ʟᴇᴀᴠᴇs ɪɴ ᴛʜᴇ ᴠᴄ.",
                parse_mode="html",
                disable_web_page_preview=True,
            )
            asyncio.create_task(check_and_monitor_vc(chat_id))

        elif arg in ("off", "disable", "no"):
            vc_logging_status[chat_id] = False
            await save_vc_logger_status(chat_id, False)
            active_vc_chats.discard(chat_id)
            vc_active_users.pop(chat_id, None)
            await message.reply(
                "🚫 <b>VC Logging Disabled!</b>\n"
                "ɴᴏ ʟᴏɴɢᴇʀ ᴛʀᴀᴄᴋɪɴɢ ᴠᴄ ᴀᴄᴛɪᴠɪᴛʏ.",
                parse_mode="html",
                disable_web_page_preview=True,
            )

        else:
            await message.reply(
                "❌ <b>Invalid option.</b> Use <b>/vclogger on</b> or <b>/vclogger off</b>.",
                parse_mode="html",
            )


@Client.on_message(filters.command("reload_vclog", prefixes=PREFIXES) & filters.private)
async def manual_reload(_, message: Message):
    """
    Owner-only command to manually reload VC logger status from DB.
    Restrict this using your bot's owner filter from SHASHA_DRUGZ config.
    Replace `filters.private` with your actual owner filter if needed.
    """
    await load_vc_logger_status()
    await message.reply(
        "♻️ <b>VC Logger status reloaded from database!</b>",
        parse_mode="html",
    )


# ════════════════════════════════════════════
# AUTO START ON BOT READY
# ════════════════════════════════════════════

async def _startup_load():
    """
    Safely schedule DB load after the event loop is fully running.
    Called via app.loop.create_task() to avoid module-level loop issues.
    """
    await asyncio.sleep(3)  # Brief delay to let bot fully initialize
    await load_vc_logger_status()


# Hook into the running event loop safely — avoids DeprecationWarning in Python 3.10+
try:
    loop = asyncio.get_running_loop()
    loop.create_task(_startup_load())
except RuntimeError:
    # No running loop yet (module imported before bot starts) — safe to ignore.
    # load_vc_logger_status() will be called when the bot fires its first event,
    # or you can call it from your bot's on_startup handler instead.
    pass


# ════════════════════════════════════════════
# MODULE METADATA
# ════════════════════════════════════════════

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_61"
__help__ = """
🔻 /vclogger ➠ ᴍᴀɴᴀɢᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ʟᴏɢɢɪɴɢ ᴏɴ ᴀ ɢʀᴏᴜᴘ
     • /vclogger on  → ᴇɴᴀʙʟᴇ ᴠᴄ ʟᴏɢɢɪɴɢ
     • /vclogger off → ᴅɪsᴀʙʟᴇ ᴠᴄ ʟᴏɢɢɪɴɢ

🔻 /reload_vclog ➠ ʀᴇʟᴏᴀᴅ ᴠᴄ ʟᴏɢɢᴇʀ sᴛᴀᴛᴜs ᴍᴀɴᴜᴀʟʟʏ (ᴏɴʟʏ ʙᴏᴛ ᴏᴡɴᴇʀ)
"""

MOD_TYPE = "MUSIC"
MOD_NAME = "VC-Notice"
MOD_PRICE = "20"
