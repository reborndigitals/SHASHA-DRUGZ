"""
SHASHA_DRUGZ/plugins/PREMIUM/chatbot.py  — v3 FINAL

╔══════════════════════════════════════════════════════════════════╗
║  RULES                                                           ║
║  Rule 1 – Never learn stickers/media. Send plain text ONLY.     ║
║  Rule 2 – Never learn or send any blocked word / content.       ║
║  Rule 3 – Only SEND a reply when user reply-tags the bot.       ║
║           Learning happens from ALL group text — no restriction. ║
╚══════════════════════════════════════════════════════════════════╝

Learning sources (all Rule-filtered, persistent across restarts):
  • Any user reply to ANY other user   → (replied msg  → reply)
  • Sequential chat messages           → (prev msg → next msg, ≤90 s)

Reply engine (multi-strategy scored):
  1. Exact match
  2. Stored trigger is a substring of the query  (+0.25 boost)
  3. Query is a substring of the stored trigger  (+0.10 boost)
  4. Jaccard token-overlap score ≥ 0.30
  → Picks randomly from the top-3 scorers (adds natural variety)
"""

import os
import re
import random
from collections import defaultdict
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
from pymongo import MongoClient, ASCENDING

# ------------------------------------------------------------------ #
#                        Application client                           #
# ------------------------------------------------------------------ #
try:
    from SHASHA_DRUGZ import app
except Exception:
    try:
        from main import app
    except Exception:
        raise RuntimeError("Could not import Pyrogram Client as 'app'.")

# ------------------------------------------------------------------ #
#                      MongoDB / Config setup                         #
# ------------------------------------------------------------------ #
try:
    from config import MONGO_DB_URI as MONGO_URL
    from SHASHA_DRUGZ.misc import SUDOERS
except Exception:
    MONGO_URL = os.environ.get(
        "MONGO_URL",
        "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/"
        "?retryWrites=true&w=majority",
    )
    SUDOERS = []

try:
    from config import OWNER_ID
except Exception:
    OWNER_ID = 0

# ------------------------------------------------------------------ #
#            SUDOERS SANITISATION — integers only                     #
# ------------------------------------------------------------------ #
SUDO_IDS = []
for _s in (SUDOERS or []):
    if isinstance(_s, int):
        SUDO_IDS.append(_s)
    elif hasattr(_s, "id"):
        SUDO_IDS.append(_s.id)
if OWNER_ID:
    SUDO_IDS.append(OWNER_ID)
SUDO_IDS = list(set(SUDO_IDS))

# ------------------------------------------------------------------ #
#                         Database setup                              #
# ------------------------------------------------------------------ #
_mongo  = MongoClient(MONGO_URL)
_db     = _mongo.get_database("SHASHA_DRUGZ_db")

chatai_coll = _db.get_collection("chatai")
status_coll = _db.get_collection("chatbot_status")
BLOCK_COLL  = _db.get_collection("blocked_words")

# Indexes for fast lookups at scale
try:
    chatai_coll.create_index([("word", ASCENDING)])
    chatai_coll.create_index([("kind", ASCENDING)])
    chatai_coll.create_index([("created_at", ASCENDING)])
except Exception:
    pass

# ------------------------------------------------------------------ #
#  In-memory caches (rebuilt from MongoDB on every start)            #
# ------------------------------------------------------------------ #
replies_cache  = []                # list[dict]  — learned pairs
_spam_blocked  = {}                # {user_id: unblock_datetime}
_msg_counts    = {}                # {user_id: {"count": int, "last_time": datetime}}
_last_msg      = defaultdict(dict) # {chat_id: {"text", "user_id", "ts"}}

# ================================================================== #
#                       DEFAULT BLOCKED WORDS                         #
# ================================================================== #
DEFAULT_BLOCKED = [
    # English adult / sexual
    "sex", "porn", "nude", "boob", "boobs", "dick", "cock", "penis", "vagina",
    "nipples", "xxx", "porno", "cum", "masturbate", "erotic", "adult", "playboy",
    "hentai", "erotica", "fetish", "kink", "orgasm", "threesome", "xnxx",
    "xvideos", "xvideo", "pic", "nudepic",
    # Tamil / regional
    "punda", "koothi", "soothu", "sutthu", "mayiru", "olmari", "okka",
    "poolu", "olu", "sappu", "umbe", "kuththu", "thappu", "suthu", "paalu",
    "adangommala", "adangomala", "adangotha", "adangottha",
    "sunny", "call", "pm", "dm", "service", "ottha", "otta", "gommala",
    # Adult platforms / services
    "hole", "inch", "ash", "sexchat", "onlyfans", "cams", "chatsex",
    "adultchat", "videochat", "sexting", "naked", "lingerie", "eroticvideo",
    # Bot commands — must never be learned
    "/start", "/help", "/play", "/vplay", "/end", "/playforce", "/vplayforce",
    "/skip", "/pause", "/seek", "/loop", "/ban", "fban", "/warn", "/mute",
    "/unban", "/unfban", "/newfed", "/chatfed", "/fedstat", "/myfeds",
    # Suggestive emoji
    "💦", "💧", "🍑", "🍒", "🍆", "🥵", "🍌", "💋", "👅",
]

# Seed into DB once
for _w in DEFAULT_BLOCKED:
    if not BLOCK_COLL.find_one({"word": _w.lower()}):
        BLOCK_COLL.insert_one({"word": _w.lower()})

# ================================================================== #
#                         ADMIN HELPER                                #
# ================================================================== #
async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

# ================================================================== #
#                       BLOCKLIST HELPERS                             #
# ================================================================== #
def get_blocklist():
    try:
        db_words = [x["word"].lower() for x in BLOCK_COLL.find({})]
        return list(set(db_words + [w.lower() for w in DEFAULT_BLOCKED]))
    except Exception:
        return [w.lower() for w in DEFAULT_BLOCKED]


def add_block_word(word: str):
    word = word.lower().strip()
    if not BLOCK_COLL.find_one({"word": word}):
        BLOCK_COLL.insert_one({"word": word})
    try:
        pat = re.escape(word)
        chatai_coll.delete_many({"$or": [
            {"word": {"$regex": pat, "$options": "i"}},
            {"text": {"$regex": pat, "$options": "i"}},
        ]})
    except Exception:
        chatai_coll.delete_many({"word": word})
    global replies_cache
    replies_cache = [
        x for x in replies_cache
        if word not in x.get("word", "").lower()
        and word not in x.get("text", "").lower()
    ]


def remove_block_word(word: str):
    BLOCK_COLL.delete_one({"word": word.lower().strip()})


def list_block_words():
    return get_blocklist()

# ================================================================== #
#              HELPER — blocked-word detector  (Rule 2)               #
# ================================================================== #
def contains_blocked_word(text: str, blocked_words: list) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    for w in blocked_words:
        try:
            if w.startswith("/") and w.count("/") >= 2:
                parts   = w.rsplit("/", 1)
                pattern = parts[0][1:]
                flags   = re.IGNORECASE if "i" in parts[1].lower() else 0
                if re.search(pattern, text, flags):
                    return True
            else:
                if re.search(re.escape(w), text_lower, re.IGNORECASE):
                    return True
        except re.error:
            if w.lower() in text_lower:
                return True
    return False

# ================================================================== #
#              HELPER — command-like string detector                  #
# ================================================================== #
_CMD_PREFIXES = frozenset("/!#$%@.,_+=~`^&*\\|<>?-")

def is_command_like(text: str) -> bool:
    s = (text or "").strip()
    return bool(s) and s[0] in _CMD_PREFIXES

# ================================================================== #
#              HELPER — media / sticker detector  (Rule 1)            #
# ================================================================== #
def is_media_message(msg: Message) -> bool:
    return bool(
        msg.sticker or msg.photo or msg.video or msg.audio
        or msg.document or msg.animation or msg.voice
        or msg.video_note or msg.contact or msg.location
        or msg.poll or msg.dice
    )

# ================================================================== #
#   LOAD REPLIES CACHE — rebuilds from MongoDB on every (re)start     #
# ================================================================== #
_CACHE_LIMIT = 80_000

def load_replies_cache():
    global replies_cache
    try:
        cursor = (
            chatai_coll
            .find({"kind": "text"}, {"_id": 0, "word": 1, "text": 1, "created_at": 1})
            .sort("created_at", -1)
            .limit(_CACHE_LIMIT)
        )
        replies_cache = list(cursor)
        #print(f"[CHATBOT] ✅ Loaded {len(replies_cache)} learned replies from MongoDB.")
    except Exception as e:
        print(f"[CHATBOT] ❌ Cache load error: {e}")
        replies_cache = []

load_replies_cache()

# ================================================================== #
#                  CORE LEARNING FUNCTION                             #
# ================================================================== #
async def _learn_pair(trigger: str, response: str):
    """
    Save (trigger → response) to MongoDB if all rules pass.
    Persists across bot restarts automatically.
    """
    try:
        trigger  = (trigger  or "").strip()
        response = (response or "").strip()

        if not trigger or not response:
            return
        if len(trigger) < 2 or len(response) < 2:
            return

        bl = get_blocklist()
        if contains_blocked_word(trigger, bl) or contains_blocked_word(response, bl):
            return
        if is_command_like(trigger) or is_command_like(response):
            return

        # Skip duplicates
        if chatai_coll.find_one({"word": trigger, "text": response}, {"_id": 1}):
            return

        doc = {
            "word":       trigger,
            "text":       response,
            "kind":       "text",
            "created_at": datetime.utcnow(),
        }
        chatai_coll.insert_one(doc)

        # Keep RAM cache bounded — newest at front
        if len(replies_cache) >= _CACHE_LIMIT:
            replies_cache.pop()
        replies_cache.insert(0, doc)

    except Exception as e:
        print(f"[CHATBOT] _learn_pair error: {e}")

# ================================================================== #
#           SMART REPLY ENGINE — multi-strategy scored lookup         #
# ================================================================== #
_STOPWORDS = frozenset({
    "the","a","an","is","it","in","on","at","to","of","and","or","for",
    "with","that","this","i","you","he","she","we","they","my","your",
    "me","him","her","us","them","da","la","le","de","what","how","why",
    "when","where","who","do","did","does","are","was","were","be","been",
    "have","has","had","will","would","could","should","can","may",
    "என","என்","நான்","நீ","enna","epdi","hii","hlo","saptaya",
})

def _tokenize(text: str):
    words = re.findall(r"[^\W\d_]{2,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}

def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def get_reply_for(text: str) -> Optional[str]:
    """
    Multi-strategy scored reply lookup.

    Priority:
      1. Exact match (case-insensitive)              → random from all exact matches
      2. Stored trigger is substring of query        → best scorer
      3. Query is substring of stored trigger        → best scorer
      4. Jaccard token overlap ≥ 0.30               → best scorer
    Returns None when nothing matches.
    """
    if not replies_cache or not text:
        return None

    query       = text.strip()
    query_lower = query.lower()
    query_tok   = _tokenize(query)

    exact    = []
    sub_fwd  = []   # (score, item)
    sub_rev  = []
    fuzzy    = []

    for item in replies_cache:
        word = item.get("word", "")
        if not word:
            continue
        word_lower = word.lower()
        word_tok   = _tokenize(word)
        score      = _jaccard(query_tok, word_tok)

        if word_lower == query_lower:
            exact.append(item)
        elif word_lower in query_lower:
            sub_fwd.append((score + 0.25, item))
        elif query_lower in word_lower:
            sub_rev.append((score + 0.10, item))
        elif score >= 0.30:
            fuzzy.append((score, item))

    def _pick(lst):
        if not lst:
            return None
        lst.sort(key=lambda x: x[0], reverse=True)
        return random.choice(lst[:3])[1].get("text")

    if exact:
        return random.choice(exact).get("text")
    return _pick(sub_fwd) or _pick(sub_rev) or _pick(fuzzy)

# ================================================================== #
#              BLOCKLIST SUDO COMMANDS                                #
# ================================================================== #
@app.on_message(
    filters.command("addblock", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_addblock(client, message):
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:**\n`/addblock word1 word2`\n`/addblock /regex/i`"
        )
    raw           = message.text.split(None, 1)[1].strip()
    added, errors = [], []
    for token in raw.split():
        token = token.strip()
        if not token:
            continue
        if token.startswith("/") and token.count("/") >= 2:
            try:
                parts = token.rsplit("/", 1)
                flags = re.IGNORECASE if "i" in parts[1].lower() else 0
                re.compile(parts[0][1:], flags)
                add_block_word(token)
                added.append(token)
            except re.error:
                errors.append(token)
        else:
            add_block_word(token)
            added.append(token)
    lines = []
    if added:
        lines.append("<blockquote>🚫 **ᴀᴅᴅᴇᴅ:**\n" + "\n".join(f"• `{w}`</blockquote>" for w in added))
    if errors:
        lines.append("<blockquote>⚠️ **ɪɴᴠᴀʟɪᴅ ʀᴇɢᴇx:**\n" + "\n".join(f"• `{w}`</blockquote>" for w in errors))
    await message.reply_text("\n\n".join(lines) if lines else "ɴᴏᴛʜɪɴɢ ᴄʜᴀɴɢᴇᴅ.")


@app.on_message(
    filters.command("rmblock", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_rmblock(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/rmblock <word>`")
    word = message.text.split(None, 1)[1].strip()
    remove_block_word(word)
    await message.reply_text(f"<blockquote>🧹 ʀᴇᴍᴏᴠᴇᴅ: `{word}`</blockquote>")


@app.on_message(
    filters.command("listblock", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_listblock(client, message):
    words = list_block_words()
    if not words:
        return await message.reply_text("<blockquote>📭 ʙʟᴏᴄᴋʟɪsᴛ ɪs ᴇᴍᴘᴛʏ.</blockquote>")
    header = "<blockquote>🚫 **ɢʟᴏʙᴀʟ ʙʟᴏᴄᴋᴇᴅ ᴡᴏʀᴅs:**</blockquote>\n"
    chunk  = header
    for w in sorted(words):
        line = f"• `{w}`\n"
        if len(chunk) + len(line) > 4000:
            await message.reply_text(chunk)
            chunk = header
        chunk += line
    if chunk.strip() != header.strip():
        await message.reply_text(chunk)

# ================================================================== #
#                           UI KEYBOARD                               #
# ================================================================== #
def chatbot_keyboard(is_enabled: bool):
    if is_enabled:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("🍎 𝐃ɪsᴀʙʟᴇ", callback_data="cb_disable")]]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🍏 𝐄ɴᴀʙʟᴇ", callback_data="cb_enable")]]
    )

# ================================================================== #
#                     /chatbot  SETTINGS COMMAND                      #
# ================================================================== #
@app.on_message(
    filters.command(["chatbot", "chat"], prefixes=["/", "!", ".", "%", ",", "@", "#"])
    & filters.group
)
async def chatbot_settings_group(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    if not user_id or not await is_user_admin(client, chat_id, user_id):
        return await message.reply_text("<blockquote>❌ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴄʜᴀᴛʙᴏᴛ sᴇᴛᴛɪɴɢs.</blockquote>")
    doc     = status_coll.find_one({"chat_id": chat_id})
    enabled = not doc or doc.get("status") == "enabled"
    txt = (
        "<blockquote><b>🥂 𝐂ʜᴀᴛʙᴏᴛ 𝐒ᴇᴛᴛɪɴɢs</b></blockquote>\n"
        f"<blockquote>𝐂ᴜʀʀᴇɴᴛ 𝐒ᴛᴀᴛᴜs: "
        f"<b>{'🍏 𝐄ɴᴀʙʟᴇᴅ' if enabled else '🍎 𝐃ɪsᴀʙʟᴇᴅ'}</b></blockquote>"
    )
    await message.reply_text(txt, reply_markup=chatbot_keyboard(enabled))


@app.on_message(
    filters.command(["chatbot", "chat"], prefixes=["/", "!", ".", "%", ",", "@", "#"])
    & filters.private
)
async def chatbot_settings_private_info(client, message):
    await message.reply_text(
        "<blockquote>🤖 ᴄʜᴀᴛʙᴏᴛ ᴏɴʟʏ ᴡᴏʀᴋs ɪɴ ɢʀᴏᴜᴘs.</blockquote>\n"
        "<blockquote>ᴜsᴇ `/chatbot` ɪɴsɪᴅᴇ ᴀ ɢʀᴏᴜᴘ ᴛᴏ ᴍᴀɴᴀɢᴇ sᴇᴛᴛɪɴɢs.</blockquote>"
    )

# ================================================================== #
#                      TOGGLE CALLBACK                                #
# ================================================================== #
@app.on_callback_query(filters.regex(r"^cb_(enable|disable)$"))
async def chatbot_toggle_cb(client, cq: CallbackQuery):
    if cq.message.chat.type == ChatType.PRIVATE:
        return await cq.answer("Chatbot works only in groups.", show_alert=True)
    chat_id = cq.message.chat.id
    uid     = cq.from_user.id
    if not await is_user_admin(client, chat_id, uid):
        return await cq.answer("Only admins can do this.", show_alert=True)
    if cq.data == "cb_enable":
        status_coll.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "enabled"}}, upsert=True
        )
        await cq.message.edit_text("**🍏 ᴄʜᴀᴛʙᴏᴛ ᴇɴᴀʙʟᴇᴅ!**", reply_markup=chatbot_keyboard(True))
        await cq.answer("ᴇɴᴀʙʟᴇᴅ ✅")
    else:
        status_coll.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "disabled"}}, upsert=True
        )
        await cq.message.edit_text("**🍎 ᴄʜᴀᴛʙᴏᴛ ᴅɪsᴀʙʟᴇᴅ!**", reply_markup=chatbot_keyboard(False))
        await cq.answer("ᴅɪsᴀʙʟᴇᴅ ✅")

# ================================================================== #
#              /chatreset — wipe all learned replies  (SUDO)          #
# ================================================================== #
@app.on_message(
    filters.command(["chatreset", "resetchat"], prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_chatbot_reset(client, message):
    chatai_coll.delete_many({})
    replies_cache.clear()
    await message.reply_text("✅ ᴀʟʟ ʟᴇᴀʀɴᴇᴅ ʀᴇᴘʟɪᴇs ʜᴀᴠᴇ ʙᴇᴇɴ ᴄʟᴇᴀʀᴇᴅ.")

# ================================================================== #
#              /chatstats — knowledge-base stats  (SUDO)              #
# ================================================================== #
@app.on_message(
    filters.command("chatstats", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_chatstats(client, message):
    total = chatai_coll.count_documents({"kind": "text"})
    await message.reply_text(
        f"<blockquote>📊 **ᴄʜᴀᴛʙᴏᴛ ᴋɴᴏᴡʟᴇᴅɢᴇ ʙᴀsᴇ**</blockquote>\n"
        f"<blockquote>• ʟᴇᴀʀɴᴇᴅ ᴘᴀɪʀs ɪɴ ᴅʙ : `{total}`\n"
        f"• ɪɴ-ᴍᴇᴍᴏʀʏ ᴄᴀᴄʜᴇ     : `{len(replies_cache)}`</blockquote>"
    )

# ================================================================== #
#  LEARNING HANDLER 1 — any user reply to any user  (group 97)       #
#  Learns: (replied-to text) → (reply text)                          #
# ================================================================== #
@app.on_message(filters.reply & filters.group, group=97)
async def handler_learn_from_replies(client, message: Message):
    """
    Learn from EVERY reply chain in the group, not just replies to the bot.
    This is the richest and fastest way to build the knowledge base.
    """
    if not message.from_user or not message.reply_to_message:
        return
    if is_media_message(message) or is_media_message(message.reply_to_message):
        return
    if not message.text or not message.reply_to_message.text:
        return

    bot = await client.get_me()
    if message.from_user.id == bot.id:          # Don't learn bot's own replies
        return

    await _learn_pair(message.reply_to_message.text, message.text)


# ================================================================== #
#  LEARNING HANDLER 2 — sequential messages  (group 96)              #
#  Learns: (previous msg) → (next msg from different user, ≤90 s)   #
# ================================================================== #
@app.on_message(filters.group & filters.incoming & ~filters.me, group=96)
async def handler_learn_sequential(client, message: Message):
    """
    Passively watch conversation flow.
    When user B replies within 90 s of user A (different people),
    treat A's message as trigger and B's as the response.
    """
    if not message.from_user:
        return
    if is_media_message(message) or not message.text:
        return
    if is_command_like(message.text):
        return

    chat_id = message.chat.id
    now     = datetime.utcnow()
    prev    = _last_msg.get(chat_id)

    if (
        prev
        and prev.get("user_id") != message.from_user.id
        and prev.get("text")
        and (now - prev.get("ts", now)).total_seconds() <= 90
    ):
        await _learn_pair(prev["text"], message.text)

    _last_msg[chat_id] = {
        "text":    message.text.strip(),
        "user_id": message.from_user.id,
        "ts":      now,
    }

# ================================================================== #
#    MAIN CHATBOT REPLY HANDLER  (group 100, groups only)             #
#    Rule 3: ONLY sends a reply when user reply-tags the bot.         #
# ================================================================== #
@app.on_message(
    filters.incoming & ~filters.me & filters.group,
    group=100,
)
async def chatbot_handler(client, message: Message):
    # ── basic guards ────────────────────────────────────────────────
    if message.edit_date or not message.from_user or not message.text:
        return
    if is_command_like(message.text):
        return await message.continue_propagation()

    user_id = message.from_user.id
    chat_id = message.chat.id
    now     = datetime.utcnow()

    # ── spam protection ─────────────────────────────────────────────
    global _spam_blocked, _msg_counts
    _spam_blocked = {u: t for u, t in _spam_blocked.items() if t > now}

    mc = _msg_counts.get(user_id)
    if mc is None:
        _msg_counts[user_id] = {"count": 1, "last_time": now}
    else:
        diff = (now - mc["last_time"]).total_seconds()
        if diff <= 3:
            mc["count"] += 1
        else:
            mc["count"]     = 1
            mc["last_time"] = now
        if mc["count"] >= 6:
            _spam_blocked[user_id] = now + timedelta(minutes=1)
            _msg_counts.pop(user_id, None)
            try:
                await message.reply_text("⛔ Slow down! Muted for 1 minute.")
            except Exception:
                pass
            return

    if user_id in _spam_blocked:
        return

    # ── chatbot enabled check ───────────────────────────────────────
    s = status_coll.find_one({"chat_id": chat_id})
    if s and s.get("status") == "disabled":
        return

    # ── Rule 2 — skip messages containing blocked words ─────────────
    blocked_words = get_blocklist()
    if contains_blocked_word(message.text, blocked_words):
        return

    # ── Rule 3 — ONLY reply when user reply-tags the bot ────────────
    if not message.reply_to_message:
        return
    bot         = await client.get_me()
    replied_usr = message.reply_to_message.from_user
    if not replied_usr or replied_usr.id != bot.id:
        return

    # ── find the best learned reply ─────────────────────────────────
    response = get_reply_for(message.text)

    # Friendly varied fallbacks — no robotic "I don't understand" spam
    if not response:
        response = random.choice([
            "Hmm, interesting! Tell me more 🤔",
            "I'm still learning that one 😅",
            "Oh? Say more! 😊",
            "Didn't quite get that, try again? 🙃",
            "I'm growing my knowledge every day! 💬",
            "Still learning — keep talking! 👀",
        ])

    # ── Rule 2 final guard ───────────────────────────────────────────
    if contains_blocked_word(response, blocked_words):
        response = "I'm still learning! 😊"

    # ── Never send a command string ─────────────────────────────────
    if is_command_like(response):
        response = "I'm still learning! 😊"

    # ── Rule 1 — always plain text ───────────────────────────────────
    try:
        await message.reply_text(response)
    except Exception as e:
        print(f"[CHATBOT] reply error: {e}")


# ================================================================== #
#                          MODULE METADATA                            #
# ================================================================== #
__menu__     = "CMD_CHAT"
__mod_name__ = "H_B_9"
__help__     = """
🔻 /ᴄʜᴀᴛʙᴏᴛ — ꜱʜᴏᴡ ᴄʜᴀᴛʙᴏᴛ ꜱᴛᴀᴛᴜꜱ & ᴛᴏɢɢʟᴇ ᴏɴ/ᴏꜰꜰ (ᴀᴅᴍɪɴ)
🔻 /ᴄʜᴀᴛꜱᴛᴀᴛꜱ — ꜱʜᴏᴡ ʜᴏᴡ ᴍᴀɴʏ ʀᴇᴘʟɪᴇꜱ ᴛʜᴇ ʙᴏᴛ ʜᴀꜱ ʟᴇᴀʀɴᴇᴅ (ꜱᴜᴅᴏ)
🔻 /ᴄʜᴀᴛʀᴇꜱᴇᴛ — ᴡɪᴘᴇ ᴀʟʟ ʟᴇᴀʀɴᴇᴅ ʀᴇᴘʟɪᴇꜱ (ꜱᴜᴅᴏ)
🔻 /ᴀᴅᴅʙʟᴏᴄᴋ — ᴀᴅᴅ ᴡᴏʀᴅ(ꜱ) ᴛᴏ ɢʟᴏʙᴀʟ ʙʟᴏᴄᴋʟɪꜱᴛ (ꜱᴜᴅᴏ)
                ᴜꜱᴀɢᴇ: /ᴀᴅᴅʙʟᴏᴄᴋ ᴡᴏʀᴅ1 ᴡᴏʀᴅ2 ᴏʀ /ᴀᴅᴅʙʟᴏᴄᴋ /ʀᴇɢᴇx/ɪ
🔻 /ʀᴍʙʟᴏᴄᴋ — ʀᴇᴍᴏᴠᴇ ᴀ ᴡᴏʀᴅ ꜰʀᴏᴍ ʙʟᴏᴄᴋʟɪꜱᴛ (ꜱᴜᴅᴏ)
🔻 /ʟɪꜱᴛʙʟᴏᴄᴋ — ʟɪꜱᴛ ᴀʟʟ ʙʟᴏᴄᴋᴇᴅ ᴡᴏʀᴅꜱ (ꜱᴜᴅᴏ)
"""
