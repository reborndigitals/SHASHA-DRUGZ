import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.enums import ChatMemberStatus, ChatType
from pymongo import MongoClient

# -------------------- Application client -------------------- #
#try:
#    from SHASHA_DRUGZ import app
#except Exception:
#    try:
#        from main import app
#    except Exception:
#        raise RuntimeError("Could not import Pyrogram Client as 'app'.")

# -------------------- MongoDB & Config setup -------------------- #
try:
    from config import MONGO_DB_URI as MONGO_URL
    from SHASHA_DRUGZ.misc import SUDOERS
except Exception:
    MONGO_URL = os.environ.get(
        "MONGO_URL",
        "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority"
    )
    SUDOERS = []

try:
    from config import OWNER_ID
except:
    OWNER_ID = 0

# -------------------- SUDOERS SANITIZATION (FIX CRASH) -------------------- #
# Ensure SUDOERS only contains Integers (IDs), removing any objects/strings
SUDO_IDS = []
if SUDOERS:
    for item in SUDOERS:
        if isinstance(item, int):
            SUDO_IDS.append(item)
        elif hasattr(item, 'id'):  # If it's a User object
            SUDO_IDS.append(item.id)
SUDO_IDS.append(OWNER_ID)
SUDO_IDS = list(set(SUDO_IDS)) # Remove duplicates

# -------------------- Database Setup -------------------- #
mongo = MongoClient(MONGO_URL)
db = mongo.get_database("SHASHA_DRUGZ_db")

chatai_coll = db.get_collection("chatai")
status_coll = db.get_collection("chatbot_status")
BLOCK_COLL = db.get_collection("blocked_words")  # GLOBAL BLOCKLIST

# Runtime Caches
replies_cache = []
blocklist_users = {}
message_counts = {}

# ================= DEFAULT BLOCKED WORDS ================= #
DEFAULT_BLOCKED = [
    "sex", "porn", "nude", "boob", "boobs", "dick", "cock", "penis", "vagina",
    "nipples", "xxx", "porno", "cum", "masturbate", "erotic", "adult", "playboy",
    "hentai", "erotica", "fetish", "kink", "orgasm", "threesome", "xnxx",
    "xvideos", "xvideo", "pic", "nudepic",
    "punda", "koothi", "soothu", "sutthu", "mayiru", "olmari", "okka",
    "poolu", "olu", "sappu", "umbe", "kuththu", "thappu", "suthu", "paalu",
    "adangommala", "adangomala", "adangotha", "adangottha",
    "sunny", "call", "pm", "dm", "service", "ottha", "otta", "gommala",
    "hole", "inch", "ash", "sexchat", "onlyfans", "cams", "chatsex", "adultchat",
    "videochat", "sexting", "naked", "lingerie", "eroticvideo",
    "/start", "/help", "/play", "/vplay", "/end", "/playforce", "/vplayforce",
    "/skip", "/pause", "/seek", "/loop", "/ban", "fban", "/warn", "/mute",
    "/unban", "/unfban", "/newfed", "/chatfed", "/fedstat", "/myfeds",
    "💦", "💧", "🍑", "🍒", "🍆", "🥵", "🍌", "💋", "👅",
]

# ===================== INITIALIZE BLOCKLIST ===================== #
for w in DEFAULT_BLOCKED:
    if not BLOCK_COLL.find_one({"word": w.lower()}):
        BLOCK_COLL.insert_one({"word": w.lower()})


# ============================================================
#                BLOCKLIST FUNCTIONS (GLOBAL)
# ============================================================
def get_blocklist():
    try:
        data = BLOCK_COLL.find({})
        words = [x["word"].lower() for x in data]
        return list(set(words + DEFAULT_BLOCKED))
    except:
        return DEFAULT_BLOCKED


def add_block_word(word: str):
    word = word.lower().strip()
    if not BLOCK_COLL.find_one({"word": word}):
        BLOCK_COLL.insert_one({"word": word})
    # Remove existing replies that match this word
    chatai_coll.delete_many({"word": word})
    global replies_cache
    replies_cache = [x for x in replies_cache if x.get("word") != word]


def remove_block_word(word: str):
    word = word.lower().strip()
    BLOCK_COLL.delete_one({"word": word})


def list_block_words():
    return get_blocklist()


# ============================================================
#                      ADMIN HELPERS
# ============================================================
async def is_user_admin(client, chat_id: int, user_id: int) -> bool:
    if user_id in SUDO_IDS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def load_replies_cache():
    global replies_cache
    try:
        replies_cache = list(chatai_coll.find({}))
    except Exception:
        replies_cache = []


def get_reply_sync(word: str):
    global replies_cache
    if not replies_cache:
        try:
            replies_cache.extend(list(chatai_coll.find({})))
        except Exception:
            pass

    if not replies_cache:
        return None

    exact = [r for r in replies_cache if r.get("word") == (word or "")]
    candidates = exact if exact else replies_cache

    return random.choice(candidates) if candidates else None


async def save_reply(original: Message, reply: Message):
    try:
        if not original or not original.text or not reply.text:
            return

        bl = get_blocklist()
        # Check if the text contains any blocked word
        if any(re.search(rf"{re.escape(w)}", original.text, flags=re.IGNORECASE) for w in bl):
            return

        # Always save only text
        data = {
            "word": original.text,
            "text": reply.text,
            "kind": "text",
            "created_at": datetime.utcnow()
        }

        exists = chatai_coll.find_one({"word": data["word"], "text": data["text"]})
        if not exists:
            chatai_coll.insert_one(data)
            replies_cache.append(data)

    except Exception as e:
        print("[chatbot] save_reply ERROR:", e)


# ============================================================
#             BLOCKLIST SUDO COMMANDS
# ============================================================
@Client.on_message(filters.command("addblock", prefixes=["/", "!", "."]) & filters.user(SUDO_IDS))
async def addblock_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/addblock word1 word2 ...\n/addblock /regex/i")

    text = message.text.split(None, 1)[1].strip()
    added_words = []
    errors = []

    for w in text.split():
        w = w.strip()
        if not w:
            continue
        if w.startswith("/") and w.count("/") >= 2:
            try:
                parts = w.rsplit("/", 1)
                pattern = parts[0][1:]
                flags = 0
                if "i" in parts[1].lower(): flags |= re.IGNORECASE
                re.compile(pattern, flags=flags)
                add_block_word(w)
                added_words.append(w)
            except Exception:
                errors.append(w)
        else:
            add_block_word(w)
            added_words.append(w)

    reply_text = ""
    if added_words:
        reply_text += "🚫 Added to blocklist:\n" + "\n".join(f"• {w}" for w in added_words) + "\n"
    if errors:
        reply_text += "⚠️ Failed to add:\n" + "\n".join(f"• {w}" for w in errors)
    await message.reply_text(reply_text)


@Client.on_message(filters.command("rmblock", prefixes=["/", "!", "."]) & filters.user(SUDO_IDS))
async def rmblock_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /rmblock <word or regex>")

    text = message.text.split(None, 1)[1].strip()
    remove_block_word(text)
    await message.reply_text(f"🧹 Removed from blocklist: **{text}**")


@Client.on_message(filters.command("listblock", prefixes=["/", "!", "."]) & filters.user(SUDO_IDS))
async def listblock_cmd(client, message):
    words = list_block_words()
    if not words:
        return await message.reply_text("📭 Blocklist is empty.")
    
    # Send in chunks if too long
    chunk = "🚫 **Global Blocked Words:**\n"
    for w in words:
        if len(chunk) + len(w) > 4000:
            await message.reply_text(chunk)
            chunk = ""
        chunk += f"• `{w}`\n"
    if chunk:
        await message.reply_text(chunk)


# ============================================================
#                      UI KEYBOARD
# ============================================================
def chatbot_keyboard(is_enabled: bool):
    if is_enabled:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("🍎 𝐃ɪsᴀʙʟᴇ", callback_data="cb_disable")]]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🍏 𝐄ɴᴀʙʟᴇ", callback_data="cb_enable")]]
    )


# ============================================================
#                    CHATBOT SETTINGS
# ============================================================
@Client.on_message(filters.command(["chatbot", "chat"], prefixes=["/", "!", "", "%", ",", ".", "@", "#"]) & filters.group)
async def chatbot_settings_group(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_user_admin(client, chat_id, user_id):
        return await message.reply_text("❌ Only admins can manage chatbot settings.")
    
    doc = status_coll.find_one({"chat_id": chat_id})
    enabled = not doc or doc.get("status") == "enabled"
    txt = (
        "<blockquote>**🥂 𝐂ʜᴀᴛʙᴏᴛ 𝐒ᴇᴛᴛɪɴɢs**</blockquote>\n"
        f"<blockquote>𝐂ᴜʀʀᴇɴᴛ 𝐒ᴛᴀᴛᴜs: **{'🍏 𝐄ɴᴀʙʟᴇᴅ' if enabled else '🍎 𝐃ɪsᴀʙʟᴇᴅ'}**</blockquote>\n"
    )
    await message.reply_text(txt, reply_markup=chatbot_keyboard(enabled))


# New handler for /chatbot in private – simple info message
@Client.on_message(filters.command(["chatbot", "chat"], prefixes=["/", "!", "", "%", ",", ".", "@", "#"]) & filters.private)
async def chatbot_settings_private_info(client, message):
    await message.reply_text("🤖 Chatbot only works in groups.\nUse this command inside a group to manage settings.")


@Client.on_callback_query(filters.regex("^cb_(enable|disable)$"))
async def chatbot_toggle_cb(client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    uid = cq.from_user.id

    # ❌ Prevent private toggle
    if cq.message.chat.type == ChatType.PRIVATE:
        return await cq.answer("Chatbot works only in groups.", show_alert=True)

    # Only group admins can toggle
    if not await is_user_admin(client, chat_id, uid):
        return await cq.answer("Only admins can do this.", show_alert=True)

    if cq.data == "cb_enable":
        status_coll.update_one(
            {"chat_id": chat_id},
            {"$set": {"status": "enabled"}},
            upsert=True
        )
        await cq.message.edit_text(
            "**🍏 Chatbot Enabled!**",
            reply_markup=chatbot_keyboard(True)
        )
        await cq.answer("Enabled")
    else:
        status_coll.update_one(
            {"chat_id": chat_id},
            {"$set": {"status": "disabled"}},
            upsert=True
        )
        await cq.message.edit_text(
            "**🍎 Chatbot Disabled!**",
            reply_markup=chatbot_keyboard(False)
        )
        await cq.answer("Disabled")


# ============================================================
#                        RESET COMMAND
# ============================================================
@Client.on_message(filters.command("chatbot", prefixes=["/", "!", "."]) & filters.regex("reset"))
async def chatbot_reset(client, message):
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if not await is_user_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admins can do this.")
            
    chatai_coll.delete_many({})
    replies_cache.clear()
    await message.reply_text("✅ All replies cleared.")


# ============================================================
#                   LEARNING BOT REPLIES (GROUPS ONLY)
# ============================================================
@Client.on_message(filters.reply & filters.group, group=98)
async def learn_reply(client, message):
    if not message.reply_to_message or not message.text:
        return
    bot = await client.get_me()
    if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
        await save_reply(message.reply_to_message, message)


# ============================================================
#                 MAIN CHATBOT HANDLER (GROUP 100, GROUPS ONLY)
# ============================================================
@Client.on_message(
    filters.incoming & ~filters.me & filters.group,
    group=100
)
async def chatbot_handler(client, message: Message):
    if message.edit_date or not message.from_user or not message.text:
        return

    # 1. CRITICAL: Ignore Commands
    if message.text and message.text.strip().startswith(("/", "!", ".", "#", "$", "%", ",", "@")):
        return await message.continue_propagation()

    user_id = message.from_user.id
    chat_id = message.chat.id
    now = datetime.utcnow()
    global blocklist_users, message_counts

    # ---------------- SPAM PROTECTION ----------------
    blocklist_users = {u: t for u, t in blocklist_users.items() if t > now}

    mc = message_counts.get(user_id)
    if not mc:
        message_counts[user_id] = {"count": 1, "last_time": now}
    else:
        diff = (now - mc["last_time"]).total_seconds()
        mc["count"] = mc["count"] + 1 if diff <= 3 else 1
        mc["last_time"] = now
        if mc["count"] >= 6:
            blocklist_users[user_id] = now + timedelta(minutes=1)
            message_counts.pop(user_id, None)
            try: await message.reply_text("⛔ Blocked 1 minute for spam.")
            except: pass
            return

    if user_id in blocklist_users:
        return

    # ---------------- ENABLED CHECK ----------------
    s = status_coll.find_one({"chat_id": chat_id})
    if s and s.get("status") == "disabled":
        return

    # ---------------- BLOCKLIST CHECK ----------------
    blocked_words = get_blocklist()
    for w in blocked_words:
        try:
            if w.startswith("/") and w.count("/") >= 2:
                parts = w.rsplit("/", 1)
                pattern = parts[0][1:]
                flags = 0
                if "i" in parts[1].lower(): flags |= re.IGNORECASE
                if re.search(pattern, message.text, flags=flags):
                    return
            else:
                if w.lower() in message.text.lower():
                    return
        except re.error:
            if w.lower() in message.text.lower():
                return

    # ---------------- REPLY LOGIC ----------------
    should = False
    
    # 1. Reply to messages replying to the bot
    if message.reply_to_message:
        bot = await client.get_me()
        if message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot.id:
            should = True
    
    # 2. Reply if keywords used
    elif "chatbot" in message.text.lower() or "chat bot" in message.text.lower():
        should = True

    if not should:
        return

    # ---------------- SEND RESPONSE ----------------
    r = get_reply_sync(message.text)
    response = r.get("text", "") if r else "I don't understand. 🤔"

    try:
        await message.reply_text(response)
    except Exception:
        pass


__menu__ = "CMD_CHAT"
__mod_name__ = "H_B_9"
__help__ = """
🔻 /chatbot <on/off> - ᴄʜᴀᴛʙᴏᴛ ɪꜱ ᴏɴ ᴏʀ ᴏꜰꜰ ɪɴ ɢʀᴏᴜᴘ
"""

MOD_TYPE = "CHATandREACT"
MOD_NAME = "ChatBot"
MOD_PRICE = "200"
