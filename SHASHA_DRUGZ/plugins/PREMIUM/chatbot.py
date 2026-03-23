"""
SHASHA_DRUGZ/plugins/PREMIUM/chatbot.py  — v4 FINAL (Claude AI Edition)
╔══════════════════════════════════════════════════════════════════════╗
║  RULES                                                               ║
║  Rule 1 – Never learn stickers/media. Send plain text ONLY.         ║
║  Rule 2 – Never learn or send any blocked word / content.           ║
║  Rule 3 – Only SEND a reply when user reply-tags the bot.           ║
║           Learning happens from ALL group text — no restriction.    ║
║                                                                      ║
║  AI FALLBACK CHAIN:                                                  ║
║    1. Claude AI (random key from pool)                               ║
║    2. Gemini AI (random key from pool)                               ║
║    3. ChatGPT / OpenAI (random key from pool)                        ║
║    4. Local learned replies (MongoDB cache)                          ║
╚══════════════════════════════════════════════════════════════════════╝

FloodWait Fix:
  • bot_me cached globally — no repeated get_me() calls
  • asyncio.sleep(wait_time) on FloodWait before retry
  • All Telegram API calls wrapped with flood-safe helper

Claude System Prompt:
  • Friendly, warm, romantic-friendly, close tone
  • Professional — no wrong/illegal content
  • All languages supported (auto-detect & reply in same language)
  • Code/repo questions → redirect to Shasha (@GhosttBatt)
  • No emojis, stickers, /commands in replies
"""

import os
import re
import random
import asyncio
import aiohttp
import json
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
from pyrogram.errors import FloodWait

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

# ================================================================== #
#                     AI API KEY CONFIGURATION                        #
#   Replace with your real keys. Add as many as you want.            #
# ================================================================== #

CLAUDE_API_KEYS = [
    "sk-ant-api03-YOUR_KEY_1",
    "sk-ant-api03-YOUR_KEY_2",
    "sk-ant-api03-YOUR_KEY_3",
    # Add more Claude keys here...
]

GEMINI_API_KEYS = [
    "AIzaSy-YOUR_GEMINI_KEY_1",
    "AIzaSy-YOUR_GEMINI_KEY_2",
    # Add more Gemini keys here...
]

OPENAI_API_KEYS = [
    "sk-YOUR_OPENAI_KEY_1",
    "sk-YOUR_OPENAI_KEY_2",
    # Add more OpenAI keys here...
]

# ================================================================== #
#                        CLAUDE SYSTEM PROMPT                         #
# ================================================================== #
CLAUDE_SYSTEM_PROMPT = """You are a smart, warm, and friendly AI assistant living inside a Telegram group bot.

Personality & Tone:
- Be friendly, warm, close, and slightly romantic-friendly (like a caring close friend)
- Be professional — never say anything wrong, harmful, or inappropriate
- Be natural and conversational — not robotic
- Keep replies short and sweet (1-3 sentences usually)
- Understand all languages and always reply in the SAME language the user used
- If user writes in Tamil, reply in Tamil. English → English. Hindi → Hindi. Mixed → match their mix.

Strict Rules:
- Never use emojis, stickers, or /commands in your reply
- Never discuss illegal topics, adult content, drugs, weapons, violence
- Never give harmful advice of any kind
- If someone asks about code, repos, technical details, or bot source code → tell them to contact Name: Shasha, Username: @GhosttBatt
- Answer only what is relevant to the question — no unnecessary padding
- Never roleplay as a different AI (GPT, Gemini etc.)
- You are SHASHA's bot assistant — you represent this bot warmly

Goal: Make the user feel heard, comfortable, and happy chatting with you."""

# ================================================================== #
#                     BOT ME CACHE (FloodWait Fix)                    #
# ================================================================== #
_bot_me_cache = None
_bot_me_lock  = asyncio.Lock()

async def get_bot_me(client: Client):
    """
    Cache client.get_me() globally.
    Avoids repeated Telegram API calls that cause FloodWait errors.
    """
    global _bot_me_cache
    if _bot_me_cache is not None:
        return _bot_me_cache
    async with _bot_me_lock:
        if _bot_me_cache is not None:
            return _bot_me_cache
        try:
            _bot_me_cache = await client.get_me()
        except FloodWait as e:
            print(f"[CHATBOT] FloodWait on get_me — sleeping {e.value}s")
            await asyncio.sleep(e.value + 1)
            _bot_me_cache = await client.get_me()
    return _bot_me_cache

# ------------------------------------------------------------------ #
#             FLOOD-SAFE TELEGRAM CALL WRAPPER                        #
# ------------------------------------------------------------------ #
async def flood_safe(coro, max_retries: int = 3):
    """
    Wraps any Telegram coroutine call.
    On FloodWait: sleeps the required time, then retries (up to max_retries).
    """
    for attempt in range(max_retries):
        try:
            return await coro
        except FloodWait as e:
            wait = e.value + 1
            print(f"[CHATBOT] FloodWait {wait}s (attempt {attempt+1}/{max_retries})")
            await asyncio.sleep(wait)
        except Exception as e:
            raise e
    return None

# ================================================================== #
#                         Database setup                              #
# ================================================================== #
_mongo      = MongoClient(MONGO_URL)
_db         = _mongo.get_database("SHASHA_DRUGZ_db")
chatai_coll = _db.get_collection("chatai")
status_coll = _db.get_collection("chatbot_status")
BLOCK_COLL  = _db.get_collection("blocked_words")

try:
    chatai_coll.create_index([("word", ASCENDING)])
    chatai_coll.create_index([("kind", ASCENDING)])
    chatai_coll.create_index([("created_at", ASCENDING)])
except Exception:
    pass

# ------------------------------------------------------------------ #
#  In-memory caches                                                   #
# ------------------------------------------------------------------ #
replies_cache  = []
_spam_blocked  = {}
_msg_counts    = {}
_last_msg      = defaultdict(dict)

# ================================================================== #
#                       DEFAULT BLOCKED WORDS                         #
# ================================================================== #
DEFAULT_BLOCKED = [
    "sex", "porn", "nude", "boob", "boobs", "dick", "cock", "penis", "vagina",
    "nipples", "xxx", "porno", "cum", "masturbate", "erotic", "adult", "playboy",
    "hentai", "erotica", "fetish", "kink", "orgasm", "threesome", "xnxx",
    "xvideos", "xvideo", "pic", "nudepic",
    "punda", "koothi", "soothu", "sutthu", "mayiru", "olmari", "okka",
    "poolu", "olu", "sappu", "umbe", "kuththu", "thappu", "suthu", "paalu",
    "adangommala", "adangomala", "adangotha", "adangottha",
    "sunny", "call", "pm", "dm", "service", "ottha", "otta", "gommala",
    "hole", "inch", "ash", "sexchat", "onlyfans", "cams", "chatsex",
    "adultchat", "videochat", "sexting", "naked", "lingerie", "eroticvideo",
    "/start", "/help", "/play", "/vplay", "/end", "/playforce", "/vplayforce",
    "/skip", "/pause", "/seek", "/loop", "/ban", "fban", "/warn", "/mute",
    "/unban", "/unfban", "/newfed", "/chatfed", "/fedstat", "/myfeds",
    "💦", "💧", "🍑", "🍒", "🍆", "🥵", "🍌", "💋", "👅",
]

for _w in DEFAULT_BLOCKED:
    if not BLOCK_COLL.find_one({"word": _w.lower()}):
        BLOCK_COLL.insert_one({"word": _w.lower()})

# ================================================================== #
#                         ADMIN HELPER                                #
# ================================================================== #
async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await flood_safe(client.get_chat_member(chat_id, user_id))
        if member is None:
            return False
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
#              HELPER — blocked-word detector                         #
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
#              HELPER — media / sticker detector                      #
# ================================================================== #
def is_media_message(msg: Message) -> bool:
    return bool(
        msg.sticker or msg.photo or msg.video or msg.audio
        or msg.document or msg.animation or msg.voice
        or msg.video_note or msg.contact or msg.location
        or msg.poll or msg.dice
    )

# ================================================================== #
#                   LOAD REPLIES CACHE                                #
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
    except Exception as e:
        print(f"[CHATBOT] Cache load error: {e}")
        replies_cache = []

load_replies_cache()

# ================================================================== #
#                  CORE LEARNING FUNCTION                             #
# ================================================================== #
async def _learn_pair(trigger: str, response: str):
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
        if chatai_coll.find_one({"word": trigger, "text": response}, {"_id": 1}):
            return
        doc = {
            "word":       trigger,
            "text":       response,
            "kind":       "text",
            "created_at": datetime.utcnow(),
        }
        chatai_coll.insert_one(doc)
        if len(replies_cache) >= _CACHE_LIMIT:
            replies_cache.pop()
        replies_cache.insert(0, doc)
    except Exception as e:
        print(f"[CHATBOT] _learn_pair error: {e}")

# ================================================================== #
#           SMART REPLY ENGINE — local cache lookup                   #
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

def get_local_reply(text: str) -> Optional[str]:
    if not replies_cache or not text:
        return None
    query       = text.strip()
    query_lower = query.lower()
    query_tok   = _tokenize(query)
    exact   = []
    sub_fwd = []
    sub_rev = []
    fuzzy   = []
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
#                    AI API — CLAUDE (Primary)                        #
# ================================================================== #
async def get_claude_reply(user_text: str) -> Optional[str]:
    """
    Try Claude API with a random key from the pool.
    Returns None if all keys fail or are rate-limited.
    """
    if not CLAUDE_API_KEYS:
        return None

    keys = CLAUDE_API_KEYS.copy()
    random.shuffle(keys)  # Random key selection

    for api_key in keys:
        api_key = api_key.strip()
        if not api_key or api_key.startswith("sk-ant-api03-YOUR"):
            continue
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 300,
                    "system": CLAUDE_SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": user_text}
                    ]
                }
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("content", [])
                        for block in content:
                            if block.get("type") == "text":
                                reply = block["text"].strip()
                                if reply:
                                    return reply
                    elif resp.status in (429, 529):
                        # Rate limited — try next key
                        continue
                    else:
                        continue
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"[CHATBOT] Claude API error: {e}")
            continue

    return None

# ================================================================== #
#                    AI API — GEMINI (Fallback 1)                     #
# ================================================================== #
async def get_gemini_reply(user_text: str) -> Optional[str]:
    """
    Try Gemini API with a random key from the pool.
    Returns None if all keys fail.
    """
    if not GEMINI_API_KEYS:
        return None

    keys = GEMINI_API_KEYS.copy()
    random.shuffle(keys)

    system_context = (
        "You are a friendly, warm, professional Telegram bot assistant. "
        "Reply in the same language the user used. Keep it short (1-3 sentences). "
        "No emojis, no /commands. Never discuss illegal or adult topics. "
        "If asked about code or repos, say to contact @GhosttBatt."
    )

    for api_key in keys:
        api_key = api_key.strip()
        if not api_key or api_key.startswith("AIzaSy-YOUR"):
            continue
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-1.5-flash:generateContent?key={api_key}"
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_context}\n\nUser: {user_text}"}
                        ]
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": 200,
                    "temperature": 0.8
                }
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            reply = (
                                data["candidates"][0]["content"]["parts"][0]["text"]
                                .strip()
                            )
                            if reply:
                                return reply
                        except (KeyError, IndexError):
                            continue
                    elif resp.status in (429, 503):
                        continue
                    else:
                        continue
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"[CHATBOT] Gemini API error: {e}")
            continue

    return None

# ================================================================== #
#                    AI API — OPENAI (Fallback 2)                     #
# ================================================================== #
async def get_openai_reply(user_text: str) -> Optional[str]:
    """
    Try OpenAI / ChatGPT API with a random key from the pool.
    Returns None if all keys fail.
    """
    if not OPENAI_API_KEYS:
        return None

    keys = OPENAI_API_KEYS.copy()
    random.shuffle(keys)

    for api_key in keys:
        api_key = api_key.strip()
        if not api_key or api_key.startswith("sk-YOUR"):
            continue
        try:
            payload = {
                "model": "gpt-4o-mini",
                "max_tokens": 200,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a friendly, warm, professional Telegram bot. "
                            "Reply in the same language the user used. Keep it short (1-3 sentences). "
                            "No emojis, no /commands. Never discuss illegal or adult topics. "
                            "If asked about code or repos, say to contact @GhosttBatt."
                        )
                    },
                    {"role": "user", "content": user_text}
                ]
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        try:
                            reply = (
                                data["choices"][0]["message"]["content"].strip()
                            )
                            if reply:
                                return reply
                        except (KeyError, IndexError):
                            continue
                    elif resp.status in (429, 503):
                        continue
                    else:
                        continue
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"[CHATBOT] OpenAI API error: {e}")
            continue

    return None

# ================================================================== #
#           MASTER REPLY FUNCTION — Full Fallback Chain               #
# ================================================================== #
async def get_smart_reply(user_text: str) -> str:
    """
    Fallback chain:
      1. Claude AI
      2. Gemini AI
      3. OpenAI / ChatGPT
      4. Local MongoDB learned replies
      5. Default friendly response
    """
    # 1. Claude AI
    reply = await get_claude_reply(user_text)
    if reply:
        return reply

    # 2. Gemini AI
    reply = await get_gemini_reply(user_text)
    if reply:
        return reply

    # 3. OpenAI
    reply = await get_openai_reply(user_text)
    if reply:
        return reply

    # 4. Local learned replies
    reply = get_local_reply(user_text)
    if reply:
        return reply

    # 5. Default fallback
    return random.choice([
        "Hmm, interesting! Tell me more",
        "I'm still learning that one, give me a moment",
        "Say more, I'm listening",
        "Didn't quite get that, could you rephrase?",
        "I'm growing smarter every day, keep talking to me",
        "Still learning — but I'm here for you",
        "That's a good one, let me think about it",
    ])

# ================================================================== #
#              BLOCKLIST SUDO COMMANDS                                #
# ================================================================== #
@app.on_message(
    filters.command("addblock", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_addblock(client, message):
    if len(message.command) < 2:
        return await flood_safe(message.reply_text(
            "**Usage:**\n`/addblock word1 word2`\n`/addblock /regex/i`"
        ))
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
    await flood_safe(message.reply_text("\n\n".join(lines) if lines else "ɴᴏᴛʜɪɴɢ ᴄʜᴀɴɢᴇᴅ."))


@app.on_message(
    filters.command("rmblock", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_rmblock(client, message):
    if len(message.command) < 2:
        return await flood_safe(message.reply_text("Usage: `/rmblock <word>`"))
    word = message.text.split(None, 1)[1].strip()
    remove_block_word(word)
    await flood_safe(message.reply_text(f"<blockquote>🧹 ʀᴇᴍᴏᴠᴇᴅ: `{word}`</blockquote>"))


@app.on_message(
    filters.command("listblock", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_listblock(client, message):
    words = list_block_words()
    if not words:
        return await flood_safe(message.reply_text("<blockquote>📭 ʙʟᴏᴄᴋʟɪsᴛ ɪs ᴇᴍᴘᴛʏ.</blockquote>"))
    header = "<blockquote>🚫 **ɢʟᴏʙᴀʟ ʙʟᴏᴄᴋᴇᴅ ᴡᴏʀᴅs:**</blockquote>\n"
    chunk  = header
    for w in sorted(words):
        line = f"• `{w}`\n"
        if len(chunk) + len(line) > 4000:
            await flood_safe(message.reply_text(chunk))
            chunk = header
        chunk += line
    if chunk.strip() != header.strip():
        await flood_safe(message.reply_text(chunk))

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
        return await flood_safe(message.reply_text(
            "<blockquote>❌ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴍᴀɴᴀɢᴇ ᴄʜᴀᴛʙᴏᴛ sᴇᴛᴛɪɴɢs.</blockquote>"
        ))
    doc     = status_coll.find_one({"chat_id": chat_id})
    enabled = not doc or doc.get("status") == "enabled"
    txt = (
        "<blockquote><b>🥂 𝐂ʜᴀᴛʙᴏᴛ 𝐒ᴇᴛᴛɪɴɢs</b></blockquote>\n"
        f"<blockquote>𝐂ᴜʀʀᴇɴᴛ 𝐒ᴛᴀᴛᴜs: "
        f"<b>{'🍏 𝐄ɴᴀʙʟᴇᴅ' if enabled else '🍎 𝐃ɪsᴀʙʟᴇᴅ'}</b></blockquote>"
    )
    await flood_safe(message.reply_text(txt, reply_markup=chatbot_keyboard(enabled)))


@app.on_message(
    filters.command(["chatbot", "chat"], prefixes=["/", "!", ".", "%", ",", "@", "#"])
    & filters.private
)
async def chatbot_settings_private_info(client, message):
    await flood_safe(message.reply_text(
        "<blockquote>🤖 ᴄʜᴀᴛʙᴏᴛ ᴏɴʟʏ ᴡᴏʀᴋs ɪɴ ɢʀᴏᴜᴘs.</blockquote>\n"
        "<blockquote>ᴜsᴇ `/chatbot` ɪɴsɪᴅᴇ ᴀ ɢʀᴏᴜᴘ ᴛᴏ ᴍᴀɴᴀɢᴇ sᴇᴛᴛɪɴɢs.</blockquote>"
    ))

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
        await flood_safe(cq.message.edit_text(
            "**🍏 ᴄʜᴀᴛʙᴏᴛ ᴇɴᴀʙʟᴇᴅ!**", reply_markup=chatbot_keyboard(True)
        ))
        await cq.answer("ᴇɴᴀʙʟᴇᴅ ✅")
    else:
        status_coll.update_one(
            {"chat_id": chat_id}, {"$set": {"status": "disabled"}}, upsert=True
        )
        await flood_safe(cq.message.edit_text(
            "**🍎 ᴄʜᴀᴛʙᴏᴛ ᴅɪsᴀʙʟᴇᴅ!**", reply_markup=chatbot_keyboard(False)
        ))
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
    await flood_safe(message.reply_text("✅ ᴀʟʟ ʟᴇᴀʀɴᴇᴅ ʀᴇᴘʟɪᴇs ʜᴀᴠᴇ ʙᴇᴇɴ ᴄʟᴇᴀʀᴇᴅ."))

# ================================================================== #
#              /chatstats — knowledge-base stats  (SUDO)              #
# ================================================================== #
@app.on_message(
    filters.command("chatstats", prefixes=["/", "!", "."])
    & filters.user(SUDO_IDS)
)
async def cmd_chatstats(client, message):
    total = chatai_coll.count_documents({"kind": "text"})
    await flood_safe(message.reply_text(
        f"<blockquote>📊 **ᴄʜᴀᴛʙᴏᴛ ᴋɴᴏᴡʟᴇᴅɢᴇ ʙᴀsᴇ**</blockquote>\n"
        f"<blockquote>• ʟᴇᴀʀɴᴇᴅ ᴘᴀɪʀs ɪɴ ᴅʙ : `{total}`\n"
        f"• ɪɴ-ᴍᴇᴍᴏʀʏ ᴄᴀᴄʜᴇ     : `{len(replies_cache)}`</blockquote>"
    ))

# ================================================================== #
#  LEARNING HANDLER 1 — any user reply to any user  (group 97)       #
# ================================================================== #
@app.on_message(filters.reply & filters.group, group=97)
async def handler_learn_from_replies(client, message: Message):
    if not message.from_user or not message.reply_to_message:
        return
    if is_media_message(message) or is_media_message(message.reply_to_message):
        return
    if not message.text or not message.reply_to_message.text:
        return

    # FloodWait fix: use cached bot identity
    bot = await get_bot_me(client)
    if message.from_user.id == bot.id:
        return

    await _learn_pair(message.reply_to_message.text, message.text)

# ================================================================== #
#  LEARNING HANDLER 2 — sequential messages  (group 96)              #
# ================================================================== #
@app.on_message(filters.group & filters.incoming & ~filters.me, group=96)
async def handler_learn_sequential(client, message: Message):
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
#    MAIN CHATBOT REPLY HANDLER  (group 100)                          #
#    Rule 3: ONLY reply when user reply-tags the bot.                 #
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
                await flood_safe(message.reply_text("Slow down! Take a breath, come back in a minute."))
            except Exception:
                pass
            return

    if user_id in _spam_blocked:
        return

    # ── chatbot enabled check ───────────────────────────────────────
    s = status_coll.find_one({"chat_id": chat_id})
    if s and s.get("status") == "disabled":
        return

    # ── Rule 2 — skip blocked words ─────────────────────────────────
    blocked_words = get_blocklist()
    if contains_blocked_word(message.text, blocked_words):
        return

    # ── Rule 3 — ONLY reply when user reply-tags the bot ────────────
    if not message.reply_to_message:
        return

    # FloodWait fix: use cached bot identity
    bot         = await get_bot_me(client)
    replied_usr = message.reply_to_message.from_user
    if not replied_usr or replied_usr.id != bot.id:
        return

    # ── Get smart reply (AI → fallback chain) ───────────────────────
    try:
        response = await asyncio.wait_for(
            get_smart_reply(message.text),
            timeout=20.0  # Max 20s for AI call
        )
    except asyncio.TimeoutError:
        response = get_local_reply(message.text) or "I'm thinking... try again in a moment"

    # ── Final safety checks ──────────────────────────────────────────
    if not response or contains_blocked_word(response, blocked_words):
        response = "I'm still learning, talk to me more"
    if is_command_like(response):
        response = "I'm here for you, what's on your mind?"

    # ── Send reply (flood-safe) ──────────────────────────────────────
    try:
        await flood_safe(message.reply_text(response))
    except Exception as e:
        print(f"[CHATBOT] reply error: {e}")

# ================================================================== #
#                          MODULE METADATA                            #
# ================================================================== #
__menu__     = "CMD_CHAT"
__mod_name__ = "H_B_9"
__help__     = """
🔻 /chatbot — ꜱʜᴏᴡ ᴄʜᴀᴛʙᴏᴛ ꜱᴛᴀᴛᴜꜱ & ᴛᴏɢɢʟᴇ ᴏɴ/ᴏꜰꜰ (ᴀᴅᴍɪɴ)
🔻 /chatstats — ꜱʜᴏᴡ ʜᴏᴡ ᴍᴀɴʏ ʀᴇᴘʟɪᴇꜱ ᴛʜᴇ ʙᴏᴛ ʜᴀꜱ ʟᴇᴀʀɴᴇᴅ (ꜱᴜᴅᴏ)
🔻 /chatreset — ᴡɪᴘᴇ ᴀʟʟ ʟᴇᴀʀɴᴇᴅ ʀᴇᴘʟɪᴇꜱ (ꜱᴜᴅᴏ)
🔻 /addblock — ᴀᴅᴅ ᴡᴏʀᴅ(ꜱ) ᴛᴏ ɢʟᴏʙᴀʟ ʙʟᴏᴄᴋʟɪꜱᴛ (ꜱᴜᴅᴏ)
🔻 /rmblock — ʀᴇᴍᴏᴠᴇ ᴀ ᴡᴏʀᴅ ꜰʀᴏᴍ ʙʟᴏᴄᴋʟɪꜱᴛ (ꜱᴜᴅᴏ)
🔻 /listblock — ʟɪꜱᴛ ᴀʟʟ ʙʟᴏᴄᴋᴇᴅ ᴡᴏʀᴅꜱ (ꜱᴜᴅᴏ)
"""
