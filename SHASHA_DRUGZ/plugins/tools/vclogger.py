import asyncio
from logging import getLogger
from typing import Dict, Set
import random

from pyrogram import filters
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
PREFIXES = ["/", "!", "%", ",", "", ".", "@", "#"]

# --- Database Functions ---

async def load_vc_logger_status():
    try:
        cursor = vcloggerdb.find({})
        enabled_chats = []
        async for doc in cursor:
            chat_id = doc["chat_id"]
            status = doc["status"]
            vc_logging_status[chat_id] = status
            if status:
                enabled_chats.append(chat_id)
        
        for chat_id in enabled_chats:
            asyncio.create_task(check_and_monitor_vc(chat_id))
        
        LOGGER.info(f"VC Logger: Loaded {len(enabled_chats)} chats.")
    except Exception as e:
        LOGGER.error(f"VC Logger Load Error: {e}")

async def save_vc_logger_status(chat_id: int, status: bool):
    try:
        await vcloggerdb.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "status": status}},
            upsert=True
        )
    except Exception as e:
        LOGGER.error(f"VC Logger Save Error: {e}")

async def get_vc_logger_status(chat_id: int) -> bool:
    if chat_id in vc_logging_status:
        return vc_logging_status[chat_id]
    
    try:
        doc = await vcloggerdb.find_one({"chat_id": chat_id})
        if doc:
            status = doc["status"]
            vc_logging_status[chat_id] = status
            return status
    except Exception as e:
        LOGGER.error(f"Error getting VC status: {e}")
    
    return False

# --- Helper Functions ---

def to_small_caps(text):
    mapping = {
        "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ꜰ","g":"ɢ","h":"ʜ","i":"ɪ","j":"ᴊ",
        "k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ","q":"ǫ","r":"ʀ","s":"s","t":"ᴛ",
        "u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x","y":"ʏ","z":"ᴢ",
        "A":"ᴀ","B":"ʙ","C":"ᴄ","D":"ᴅ","E":"ᴇ","F":"ꜰ","G":"ɢ","H":"ʜ","I":"ɪ","J":"ᴊ",
        "K":"ᴋ","L":"ʟ","M":"ᴍ","N":"ɴ","O":"ᴏ","P":"ᴘ","Q":"ǫ","R":"ʀ","S":"s","T":"ᴛ",
        "U":"ᴜ","V":"ᴠ","W":"ᴡ","X":"x","Y":"ʏ","Z":"ᴢ"
    }
    return "".join(mapping.get(c,c) for c in text)

async def delete_after_delay(message, delay):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except:
        pass

# --- Core Logic ---

async def get_group_call_participants(userbot, peer):
    try:
        full_chat = await userbot.invoke(functions.channels.GetFullChannel(channel=peer))
        if not hasattr(full_chat.full_chat, 'call') or not full_chat.full_chat.call:
            return []
        call = full_chat.full_chat.call
        participants = await userbot.invoke(functions.phone.GetGroupParticipants(
            call=call, ids=[], sources=[], offset="", limit=100
        ))
        return participants.participants
    except Exception as e:
        error_msg = str(e).upper()
        if "420" in error_msg:
            return []
        if any(x in error_msg for x in ["GROUPCALL_NOT_FOUND", "CALL_NOT_FOUND", "NO_GROUPCALL"]):
            return []
        return []

async def monitor_vc_chat(chat_id):
    try:
        userbot = await get_assistant(chat_id)
        if not userbot:
            LOGGER.warning(f"monitor_vc_chat: No assistant for chat {chat_id}, stopping monitor.")
            return

        while chat_id in active_vc_chats and await get_vc_logger_status(chat_id):
            try:
                peer = await userbot.resolve_peer(chat_id)
                participants_list = await get_group_call_participants(userbot, peer)
                new_users = set()
                
                for p in participants_list:
                    if hasattr(p, 'peer') and hasattr(p.peer, 'user_id'):
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
                LOGGER.debug(f"monitor_vc_chat error in chat {chat_id}: {e}")
            
            await asyncio.sleep(5)
    except Exception as e:
        LOGGER.error(f"monitor_vc_chat fatal error for chat {chat_id}: {e}")
        if chat_id in active_vc_chats:
            active_vc_chats.discard(chat_id)

async def check_and_monitor_vc(chat_id):
    if not await get_vc_logger_status(chat_id):
        return
    try:
        userbot = await get_assistant(chat_id)
        if not userbot:
            LOGGER.warning(f"No assistant available for chat {chat_id}, disabling VC logger to avoid repeated failures.")
            vc_logging_status[chat_id] = False
            await save_vc_logger_status(chat_id, False)
            return
        if chat_id not in active_vc_chats:
            active_vc_chats.add(chat_id)
            asyncio.create_task(monitor_vc_chat(chat_id))
    except Exception as e:
        LOGGER.error(f"Error in VC Monitor setup for chat {chat_id}: {e}")
        if chat_id in active_vc_chats:
            active_vc_chats.discard(chat_id)

# --- Event Handlers (Join/Leave) ---

async def handle_user_join(chat_id, user_id, userbot):
    try:
        user = await userbot.get_users(user_id)
        name = user.first_name or "Someone"
        mention = f'<a href="tg://user?id={user_id}"><b>{to_small_caps(name)}</b></a>'
        messages = [
            f"🎤 {mention} <b>ᴊᴜsᴛ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ᴠᴄ – ʟᴇᴛ's ᴍᴀᴋᴇ ɪᴛ ʟɪᴠᴇʟʏ! 🎶</b>",
            f"✨ {mention} <b>ɪs ɴᴏᴡ ɪɴ ᴛʜᴇ ᴠᴄ – ᴡᴇʟᴄᴏᴍᴇ ᴀʙᴏᴀʀᴅ! 💫</b>",
            f"🎵 {mention} <b>ʜᴀs ᴊᴏɪɴᴇᴅ – ʟᴇᴛ's ʀᴏᴄᴋ ᴛʜɪs ᴠɪʙᴇ! 🔥</b>",
        ]
        sent_msg = await app.send_message(chat_id, random.choice(messages))
        asyncio.create_task(delete_after_delay(sent_msg, 10))
    except:
        pass

async def handle_user_leave(chat_id, user_id, userbot):
    try:
        user = await userbot.get_users(user_id)
        name = user.first_name or "Someone"
        mention = f'<a href="tg://user?id={user_id}"><b>{to_small_caps(name)}</b></a>'
        messages = [
            f"👋 {mention} <b>ʟᴇғᴛ ᴛʜᴇ ᴠᴄ – ʜᴏᴘᴇ ᴛᴏ sᴇᴇ ʏᴏᴜ ʙᴀᴄᴋ sᴏᴏɴ! 🌟</b>",
            f"🚪 {mention} <b>sᴛᴇᴘᴘᴇᴅ ᴏᴜᴛ – ᴅᴏɴ'ᴛ ᴛᴀᴋᴇ ᴛᴏᴏ ʟᴏɴɢ! 💖</b>",
            f"✌️ {mention} <b>sᴀɪᴅ ɢᴏᴏᴅʙʏᴇ – ᴄᴏᴍᴇ ʙᴀᴄᴋ sᴏᴏɴ! 🎶</b>",
        ]
        sent_msg = await app.send_message(chat_id, random.choice(messages))
        asyncio.create_task(delete_after_delay(sent_msg, 10))
    except:
        pass

# --- Command Handler ---

@app.on_message(filters.command("vclogger", prefixes=PREFIXES) & filters.group)
async def vclogger_command(_, message: Message):
    chat_id = message.chat.id
    args = message.text.split()
    status = await get_vc_logger_status(chat_id)

    prefix_ui = ", ".join([f"<b>{p}vclogger</b>" for p in ["/", "!"]])
    current_state_ui = to_small_caps(str(status if status is not None else "Not Set"))

    if len(args) == 1:
        text = (
            f"📌 <b>VC Logger Status:</b> <b>{current_state_ui}</b>\n\n"
            f"Usage: {prefix_ui} <b>[on|off]</b>"
        )
        await message.reply(text, disable_web_page_preview=True)
    elif len(args) == 2:
        arg = args[1].lower()
        if arg in ["on", "enable", "yes"]:
            vc_logging_status[chat_id] = True
            await save_vc_logger_status(chat_id, True)
            await message.reply(
                f"✅ <b>VC Logging Enabled</b>",
                disable_web_page_preview=True
            )
            asyncio.create_task(check_and_monitor_vc(chat_id))
        elif arg in ["off", "disable", "no"]:
            vc_logging_status[chat_id] = False
            await save_vc_logger_status(chat_id, False)
            await message.reply(
                f"🚫 <b>VC Logging Disabled</b>",
                disable_web_page_preview=True
            )
            active_vc_chats.discard(chat_id)
            vc_active_users.pop(chat_id, None)
        else:
            await message.reply("❌ Invalid option. Use **on** or **off**.")

# --- Auto Start ---
@app.on_message(filters.command("reload_vclog", prefixes=PREFIXES) & filters.user(123456789))
async def manual_reload(client, message):
    await load_vc_logger_status()
    await message.reply("Reloaded VC Log status.")

# Attempt to load immediately if event loop is running
loop = asyncio.get_event_loop()
if loop.is_running():
    loop.create_task(load_vc_logger_status())

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_61"
__help__ = """
🔻 /vclogger ➠ ᴍᴀɴᴀɢᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ʟᴏɢɢɪɴɢ ᴏɴ ᴀ ɢʀᴏᴜᴘ
     • /vclogger on → ᴇɴᴀʙʟᴇ ᴠᴄ ʟᴏɢɢɪɴɢ
     • /vclogger off → ᴅɪsᴀʙʟᴇ ᴠᴄ ʟᴏɢɢɪɴɢ

🔻 /reload_vclog ➠ ʀᴇʟᴏᴀᴅ ᴠᴄ ʟᴏɢɢᴇʀ sᴛᴀᴛᴜs ᴍᴀɴᴜᴀʟʟʏ (ᴏɴʟʏ ʙᴏᴛ ᴏᴡɴᴇʀ)
"""
