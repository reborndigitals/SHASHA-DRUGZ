# ================================================================
#   GUESS MOVIE GAME MODULE  —  SHASHA_DRUGZ  v1.0
#   File: SHASHA_DRUGZ/plugins/GAMES/guessmoviegame.py
#
#   FIXES APPLIED:
#   1. FIX TEXT HINT BUG: "if mode in hints" blocked text hints from
#      being given more than once. Text has 4 progressive clues — they
#      were unreachable after the first. Fix: allow "text" mode to repeat.
#      → if mode != "text" and mode in hints:
#
#   2. FIX ASYNCIO TASK BUG: asyncio.get_event_loop().create_task() at
#      module import time silently fails because the event loop isn't
#      running yet. Periodic score reset NEVER ran.
#      Fix: lazy-init with a guard flag, triggered on first /gmovie call.
#
#   3. FIX IMPORT BUG: aq_markup and stream_markup were imported INSIDE
#      _play_movie_song(). If the import fails mid-execution, song play
#      crashes with ImportError. Fix: moved to top-level imports.
#
#   4. FIX REDUNDANT IMPORT BUG: "from SHASHA_DRUGZ.misc import db as _db"
#      was imported twice inside _play_movie_song() when db is already
#      imported at module level. Removed inline imports, use module-level db.
#
#   5. MINOR: Removed unused search_url variable in _fetch_and_blur_poster.
# ================================================================
import asyncio
import io
import os
import random
import re as _re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.call import SHASHA
from SHASHA_DRUGZ.core.mongo import get_collection
from SHASHA_DRUGZ.misc import db                          # module-level db (FIX 4)
from SHASHA_DRUGZ.utils.database import (
    add_served_chat,
    get_assistant,
    is_active_chat,
)
from SHASHA_DRUGZ.utils.stream.queue import put_queue
from SHASHA_DRUGZ.utils.thumbnails import get_thumb
# FIX 3: moved from inside _play_movie_song to top-level imports
from SHASHA_DRUGZ.utils.inline import aq_markup, stream_markup
# YouTube integration
from SHASHA_DRUGZ.platforms.Youtube import (
    YouTubeAPI,
    download_song,
)
from youtubesearchpython.__future__ import VideosSearch
# ================================================================
# ASSETS
# ================================================================
_FONT_PATH = "SHASHA_DRUGZ/assets/Sprintura Demo.otf"
_executor  = ThreadPoolExecutor(max_workers=4)
# ================================================================
# MONGODB
# ================================================================
score_col = get_collection("movie_game_scores")
meta_col  = get_collection("movie_game_meta")
# ================================================================
# FIX 2: Lazy-init guard for periodic reset task
# ================================================================
_reset_task_started = False

async def _ensure_reset_task():
    """Start the periodic score reset task once, safely after the loop is running."""
    global _reset_task_started
    if not _reset_task_started:
        _reset_task_started = True
        asyncio.create_task(_reset_periodic())

# ================================================================
# TITLE SYSTEM
# ================================================================
GUESSER_TITLES = [
    (0,      "🎬",  "ꜰɪʟᴍ ɴᴇᴡʙɪᴇ"),
    (100,    "🍿",  "ᴘᴏᴘᴄᴏʀɴ ᴋɪᴅ"),
    (300,    "🎞",  "ᴍᴏᴠɪᴇ ʙᴜꜰꜰ"),
    (600,    "🎭",  "sᴄᴇɴᴇ ᴅᴇᴛᴇᴄᴛᴏʀ"),
    (1000,   "⚡",  "ǫᴜɪᴄᴋ ᴘʟᴏᴛ"),
    (2000,   "🎯",  "ᴅɪʀᴇᴄᴛᴏʀ's ᴘɪᴄᴋ"),
    (3500,   "🔥",  "ʙᴏx ᴏꜰꜰɪᴄᴇ ʜɪᴛ"),
    (5000,   "💎",  "ᴄɪɴᴇᴍᴀ ɢᴇᴍ"),
    (8000,   "🦁",  "ꜱᴄʀᴇᴇɴ ʟɪᴏɴ"),
    (12000,  "👑",  "ᴍᴏᴠɪᴇ ᴋɪɴɢ"),
    (18000,  "🌟",  "ʟᴇɢᴇɴᴅ ᴏꜰ ᴄɪɴᴇᴍᴀ"),
    (25000,  "💫",  "ᴍʏᴛʜɪᴄ ᴅɪʀᴇᴄᴛᴏʀ"),
    (35000,  "🚀",  "ɢᴀʟᴀxʏ ᴘʀᴏᴅᴜᴄᴇʀ"),
    (50000,  "🏆",  "ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ ᴏꜰ ᴄɪɴᴇᴍᴀ"),
]
HOST_TITLES = [
    (0,    "🎤",  "sʜʏ ʜɪɴᴛᴇʀ"),
    (5,    "💬",  "ᴄᴀsᴜᴀʟ ʜᴏsᴛ"),
    (15,   "🗣️",  "ꜰɪʟᴍ ɴᴀʀʀᴀᴛᴏʀ"),
    (30,   "🎭",  "ꜱᴄᴇɴᴇ ᴍᴀᴋᴇʀ"),
    (50,   "🌊",  "ꜰʟᴜᴇɴᴛ ʜᴏsᴛ"),
    (80,   "⚔️",  "ᴘʀᴏ ᴅɪʀᴇᴄᴛᴏʀ"),
    (120,  "🎓",  "ꜱᴛᴀʀ ᴘʀᴏᴅᴜᴄᴇʀ"),
    (180,  "🧙",  "ᴄɪɴᴇᴍᴀ ᴡɪᴢᴀʀᴅ"),
    (260,  "🦅",  "ᴇᴀɢʟᴇ ᴇʏᴇ ʜᴏsᴛ"),
    (360,  "👑",  "ᴍᴏᴠɪᴇ ʜᴏsᴛ ᴋɪɴɢ"),
    (500,  "🌟",  "ʟᴇɢᴇɴᴅᴀʀʏ ʜᴏsᴛ"),
    (700,  "💫",  "ᴍʏᴛʜɪᴄ ɴᴀʀʀᴀᴛᴏʀ"),
    (1000, "🏆",  "ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ ʜᴏsᴛ"),
]
def get_guesser_title(coins: int) -> tuple:
    result = GUESSER_TITLES[0][1], GUESSER_TITLES[0][2]
    for min_c, emoji, name in GUESSER_TITLES:
        if coins >= min_c:
            result = emoji, name
    return result
def get_host_title(words_hosted: int) -> tuple:
    result = HOST_TITLES[0][1], HOST_TITLES[0][2]
    for min_w, emoji, name in HOST_TITLES:
        if words_hosted >= min_w:
            result = emoji, name
    return result
def get_display_title(coins: int, words_hosted: int) -> str:
    ge, gn = get_guesser_title(coins)
    he, hn = get_host_title(words_hosted)
    g_tier = sum(1 for c, _, _ in GUESSER_TITLES if coins >= c) - 1
    h_tier = sum(1 for w, _, _ in HOST_TITLES if words_hosted >= w) - 1
    h_scaled = h_tier * len(GUESSER_TITLES) / max(len(HOST_TITLES), 1)
    if h_scaled >= g_tier:
        return f"{he} {hn}"
    return f"{ge} {gn}"
def _next_guesser_title(coins: int):
    for min_c, emoji, name in GUESSER_TITLES:
        if coins < min_c:
            return f"{emoji} {name} ᴀᴛ {min_c} ᴄᴏɪɴs"
    return None
def _next_host_title(words_hosted: int):
    for min_w, emoji, name in HOST_TITLES:
        if words_hosted < min_w:
            return f"{emoji} {name} ᴀᴛ {min_w} ᴍᴏᴠɪᴇs"
    return None
# ================================================================
# MOVIE DATABASE
# ================================================================
MOVIES = {
    "tamil": [
        {
            "name": "Vikram",
            "year": 2022,
            "director": "Lokesh Kanagaraj",
            "text_hints": [
                "ᴀ 2022 ᴀᴄᴛɪᴏɴ ꜰɪʟᴍ ᴡɪᴛʜ ᴋᴀᴍᴀʟ ʜᴀᴀsᴀɴ",
                "ᴀ ᴄᴏᴘ ᴏɴ ᴀ ᴍɪssɪᴏɴ ᴛᴏ sᴛᴏᴘ ᴍᴀsᴋᴇᴅ ᴋɪʟʟᴇʀs",
                "ꜰᴀᴊᴀ ꜱᴀᴍᴀᴜɴᴅᴇʀ ᴅɪʀᴇᴄᴛᴇᴅ ʙʏ ʟᴋ",
                "ᴠɪᴊᴀʏ ꜱᴇᴛʜᴜᴘᴀᴛʜɪ ᴀɴᴅ ꜰᴀʜᴀᴅ ꜰᴀᴀꜱɪʟ ᴀʟꜱᴏ ꜱᴛᴀʀ",
            ],
            "emoji_puzzle": "💪🕵️🎭🔫 = ?",
            "dialogue": '"ᴠɪᴋʀᴀᴍ... ᴠɪᴋʀᴀᴍ ᴠᴇᴛᴛᴜᴠᴇᴛᴛᴜ ᴠᴀᴅᴀɪ ᴋᴀᴀꜱᴜ!"',
            "songs": ["Vikram Climax BGM", "Pathala Pathala", "Rolex Theme Vikram"],
            "image_search": "Vikram 2022 Tamil movie poster",
        },
        {
            "name": "Jailer",
            "year": 2023,
            "director": "Nelson Dilipkumar",
            "text_hints": [
                "ᴀ ʀᴇᴛɪʀᴇᴅ ᴊᴀɪʟᴇʀ ᴄᴏᴍᴇs ʙᴀᴄᴋ ꜰᴏʀ ʜɪꜱ ꜱᴏɴ",
                "2023 ʀᴀᴊɪɴɪᴋᴀɴᴛʜ ʙʟᴏᴄᴋʙᴜꜱᴛᴇʀ",
                "ɴᴇʟꜱᴏɴ ᴅɪʟɪᴘᴋᴜᴍᴀʀ ᴅɪʀᴇᴄᴛᴇᴅ",
                "ꜰᴀᴍᴏᴜꜱ ꜰᴏʀ ᴘᴏʟɪᴠᴀʟᴀᴠᴀɴ ꜱᴏɴɢ",
            ],
            "emoji_puzzle": "👴🔒🏢🦁 = ?",
            "dialogue": '"ᴡʜᴏ ᴀʀᴇ ʏᴏᴜ? ɪ ᴀᴍ ᴛʜᴇ ᴊᴀɪʟᴇʀ."',
            "songs": ["Jailer Title Track", "Kavaalaa", "Hukum"],
            "image_search": "Jailer 2023 Rajinikanth Tamil movie poster",
        },
        {
            "name": "Leo",
            "year": 2023,
            "director": "Lokesh Kanagaraj",
            "text_hints": [
                "ᴀ ᴄᴀꜰᴇ ᴏᴡɴᴇʀ ʜɪᴅᴇꜱ ᴀ ᴅᴀʀᴋ ᴘᴀꜱᴛ",
                "2023 ᴛᴀᴍɪʟ ꜰɪʟᴍ ᴡɪᴛʜ ᴠɪᴊᴀʏ",
                "ʟᴏᴋᴇꜱʜ ᴄɪɴᴇᴍᴀ ᴜɴɪᴠᴇʀꜱᴇ ᴘᴀʀᴛ",
                "ꜱᴀɴꜰʀᴀɴꜱɪꜱᴄᴏ ꜱᴇᴛᴛɪɴɢ",
            ],
            "emoji_puzzle": "🦁☕🔪🌊 = ?",
            "dialogue": '"ɪ ᴅɪᴅɴ\'ᴛ ᴄᴏᴍᴇ ʜᴇʀᴇ ᴛᴏ ʙᴇ ᴛʜᴇ ʙᴏꜱꜱ. ɪ ᴄᴀᴍᴇ ᴛᴏ ꜱᴀᴠᴇ ᴍʏ ꜰᴀᴍɪʟʏ."',
            "songs": ["Leo Title Track", "Naa Ready", "Aalaporaan Thamizhan"],
            "image_search": "Leo 2023 Vijay Tamil movie poster",
        },
        {
            "name": "Enthiran",
            "year": 2010,
            "director": "Shankar",
            "text_hints": [
                "ᴀ ꜱᴄɪᴇɴᴛɪꜱᴛ ᴄʀᴇᴀᴛᴇꜱ ᴀɴ ᴀɴᴅʀᴏɪᴅ ʀᴏʙᴏᴛ",
                "ʀᴀᴊɪɴɪᴋᴀɴᴛʜ ᴘʟᴀʏꜱ ᴅᴜᴀʟ ʀᴏʟᴇ",
                "ꜱʜᴀɴᴋᴀʀ ᴅɪʀᴇᴄᴛᴇᴅ ᴍᴇɢᴀ ʙᴜᴅɢᴇᴛ",
                "ᴄᴏɪɴᴄɪᴅᴇɴᴄᴇꜱ ᴀʀᴇ ɴᴏᴛ ᴀ ᴄᴏɪɴᴄɪᴅᴇɴᴄᴇ",
            ],
            "emoji_puzzle": "🤖❤️🔬👨‍🔬 = ?",
            "dialogue": '"ᴍᴀɴɪᴛʜᴀɴᴜᴋᴋᴜ ᴇᴍᴏꜱʜᴀɴ ɪʀᴜᴋᴋᴜ... ʀᴏʙᴏᴛᴜᴋᴋᴜ ɪʟʟᴀ."',
            "songs": ["Kilimanjaro", "Boom Boom", "Kadhal Anukkal"],
            "image_search": "Enthiran 2010 Rajinikanth Tamil movie poster",
        },
        {
            "name": "Kaithi",
            "year": 2019,
            "director": "Lokesh Kanagaraj",
            "text_hints": [
                "ᴀ ᴘʀɪꜱᴏɴᴇʀ ʀᴇʟᴇᴀꜱᴇᴅ ᴀꜰᴛᴇʀ 10 ʏᴇᴀʀꜱ",
                "ᴄᴀʀᴛʜɪ ʟᴇᴅ ɴᴏ ꜱᴏɴɢꜱ ᴀᴄᴛɪᴏɴ ꜰɪʟᴍ",
                "ɴᴏ ʜᴇʀᴏɪɴᴇ ɴᴏ ꜱᴏɴɢꜱ ᴘᴜʀᴇ ᴀᴄᴛɪᴏɴ",
                "ᴏɴᴇ ɴɪɢʜᴛ ᴄᴏᴘ ᴅʀᴜɢ ᴄᴏɴꜰʟɪᴄᴛ",
            ],
            "emoji_puzzle": "🔓🌙🚗💊 = ?",
            "dialogue": '"ᴇɴɴᴏᴅᴀ ᴘᴀꜱᴀɴɢᴀ... ᴇɴɢᴇ?"',
            "songs": ["Kaithi BGM Theme", "Kaithi Mass Entry BGM"],
            "image_search": "Kaithi 2019 Karthi Tamil movie poster",
        },
        {
            "name": "Mersal",
            "year": 2017,
            "director": "Atlee",
            "text_hints": [
                "ᴀᴛʟᴇᴇ ᴅɪʀᴇᴄᴛᴇᴅ ᴛʜʀɪʟʟᴇʀ ᴡɪᴛʜ ᴠɪᴊᴀʏ",
                "ᴛʜʀᴇᴇ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ᴘʟᴀʏᴇᴅ ʙʏ ᴏɴᴇ ʜᴇʀᴏ",
                "ᴅᴏᴄᴛᴏʀ ᴠꜱ ᴅᴏᴄᴛᴏʀ ᴛʜᴇᴍᴇ",
                "ᴀʟᴀɪᴘᴀʏᴜᴛʜᴇʏ ʜᴇʀᴏ ꜱᴏɴɢ ᴡᴀꜱ ᴀ ʙɪɢ ʜɪᴛ",
            ],
            "emoji_puzzle": "⚡👨‍⚕️🎩3️⃣ = ?",
            "dialogue": '"ᴏʀᴜ ɴᴀᴀʟ ᴋᴇᴛᴘᴀᴀ... ᴍᴇʀꜱᴀʟ ᴀᴀɪᴅᴜᴠᴇɴ!"',
            "songs": ["Mersal Arasan", "Naerae Naerae", "Yaaradi"],
            "image_search": "Mersal 2017 Vijay Tamil movie poster",
        },
        {
            "name": "Master",
            "year": 2021,
            "director": "Lokesh Kanagaraj",
            "text_hints": [
                "ᴀ ᴘʀᴏꜰ ꜱᴇɴᴛ ᴛᴏ ᴊᴜᴠᴇɴɪʟᴇ ᴄᴀᴍᴘ",
                "ᴠɪᴊᴀʏ ᴠꜱ ᴠɪᴊᴀʏ ꜱᴇᴛʜᴜᴘᴀᴛʜɪ",
                "ᴄᴏᴠɪᴅ ᴘᴀɴᴅᴇᴍɪᴄ ʀᴇʟᴇᴀꜱᴇ ʜɪᴛ",
                "ᴀɴᴀʟᴅʜᴀɴ ᴛʜᴀᴍɪᴢʜᴀɴ ꜱᴏɴɢ ᴡᴇɴᴛ ᴠɪʀᴀʟ",
            ],
            "emoji_puzzle": "👨‍🏫🧒🔫🍺 = ?",
            "dialogue": '"ɴᴀᴀɴ ꜱᴏʟʟɪᴅᴜᴠᴇɴ... ᴀᴀɴᴀ ᴄᴏʀʀᴇᴄᴛ ᴀ ꜱᴏʟʟɪᴅᴜᴠᴇɴ!"',
            "songs": ["Kutti Story", "Aanandha Thandavam", "Master Title Track"],
            "image_search": "Master 2021 Vijay Tamil movie poster",
        },
        {
            "name": "Vettaiyan",
            "year": 2024,
            "director": "TJ Gnanavel",
            "text_hints": [
                "ᴀ ᴠᴇᴛᴇʀᴀɴ ᴄᴏᴘ ᴡɪᴛʜ ᴇɴᴄᴏᴜɴᴛᴇʀ ᴛʜᴇᴍᴇ",
                "ʀᴀᴊɪɴɪᴋᴀɴᴛʜ 2024 ꜰɪʟᴍ",
                "ᴀᴍɪᴛᴀʙʜ ʙᴀᴄʜᴄʜᴀɴ ꜱᴛᴀʀꜱ ᴀʟꜱᴏ",
                "ᴛɪɢᴇʀ ᴠᴇʀꜱᴜꜱ ʜᴜɴᴛᴇʀ ɪᴅᴇᴀ",
            ],
            "emoji_puzzle": "🐅🔫👮🎯 = ?",
            "dialogue": '"ᴀᴠᴀɴ ᴘᴀʀᴜᴠᴀᴛʜᴜᴋᴜ ᴍᴜɴɴᴀᴅɪ ᴛᴀɴɢᴀɪ ᴘᴀʀᴜᴠᴀɴ."',
            "songs": ["Vettaiyan Theme", "Thanimai"],
            "image_search": "Vettaiyan 2024 Rajinikanth Tamil movie poster",
        },
    ],
    "hindi": [
        {
            "name": "Pathaan",
            "year": 2023,
            "director": "Siddharth Anand",
            "text_hints": [
                "ꜱᴘʏ ᴀᴄᴛɪᴏɴ ᴡɪᴛʜ ꜱʜᴀʜʀᴜᴋʜ ᴋʜᴀɴ",
                "ɪɴᴅɪᴀɴ ɪɴᴛᴇʟʟɪɢᴇɴᴄᴇ ᴀɢᴇɴᴛ",
                "ᴅɪᴘɪᴋᴀ ᴘᴀᴅᴜᴋᴏɴᴇ ᴀɴᴅ ᴊᴏʜɴ ᴀʙʀᴀʜᴀᴍ ꜱᴛᴀʀ",
                "ʙᴇꜱʜʀᴀᴍ ʀᴀɴɢ ꜱᴏɴɢ ᴡᴀꜱ ᴄᴏɴᴛʀᴏᴠᴇʀꜱɪᴀʟ",
            ],
            "emoji_puzzle": "🕵️🇮🇳💣🔫 = ?",
            "dialogue": '"ᴅᴀʀ ᴋᴇ ᴀᴀɢᴇ ᴊᴇᴇᴛ ʜᴀɪ!"',
            "songs": ["Besharam Rang", "Jhoome Jo Pathaan", "Pathaan Title Track"],
            "image_search": "Pathaan 2023 Shah Rukh Khan Hindi movie poster",
        },
        {
            "name": "Animal",
            "year": 2023,
            "director": "Sandeep Reddy Vanga",
            "text_hints": [
                "ᴀ ꜱᴏɴ'ꜱ ᴅᴀʀᴋ ʟᴏᴠᴇ ꜰᴏʀ ʜɪꜱ ꜰᴀᴛʜᴇʀ",
                "ʀᴀɴʙɪʀ ᴋᴀᴘᴏᴏʀ ᴘʟᴀʏꜱ ᴀ ᴅᴀɴɢᴇʀᴏᴜꜱ ᴍᴀɴ",
                "ꜱᴀɴᴅᴇᴇᴘ ʀᴇᴅᴅʏ ᴠᴀɴɢᴀ ᴅɪʀᴇᴄᴛᴇᴅ",
                "ᴡᴇᴡᴀɴʜ ᴄᴏɴᴛʀᴏᴠᴇʀꜱɪᴀʟ ʟᴏᴠᴇ ꜱᴛᴏʀʏ",
            ],
            "emoji_puzzle": "🐾👨‍👦💢🔫 = ?",
            "dialogue": '"ᴊᴏ ᴛᴇʀᴀ ʜᴀɪ... ᴡᴏ ᴍᴇʀᴀ ʜᴀɪ."',
            "songs": ["Arjan Vailly", "Satranga", "Hua Main"],
            "image_search": "Animal 2023 Ranbir Kapoor Hindi movie poster",
        },
        {
            "name": "Jawan",
            "year": 2023,
            "director": "Atlee",
            "text_hints": [
                "ꜱʜᴀʜʀᴜᴋʜ ᴋʜᴀɴ ᴀᴛʟᴇᴇ ᴋᴏʟʟᴀʙᴏʀᴀᴛɪᴏɴ",
                "ᴀ ᴊᴀɪʟ ᴡᴀʀᴅᴇɴ ᴡɪᴛʜ ꜱᴇᴄʀᴇᴛꜱ",
                "ᴅᴇᴇᴘɪᴋᴀ ᴘᴀᴅᴜᴋᴏɴᴇ ᴄᴀᴍᴇᴏ",
                "ʜɪɢʜᴇꜱᴛ ɢʀᴏꜱꜱɪɴɢ ʙᴏʟʟʏᴡᴏᴏᴅ ᴏꜰ 2023",
            ],
            "emoji_puzzle": "⚔️👮🔒🌊 = ?",
            "dialogue": '"ᴇᴋ ʙᴀᴀʀ ᴊᴏ ᴍᴀɪɴɴᴇ ᴋᴏᴍᴍɪᴛᴍᴇɴᴛ ᴅᴇ ᴅɪ..."',
            "songs": ["Not Ramaiya Vastavaiya", "Zinda Banda", "Chaleya"],
            "image_search": "Jawan 2023 Shah Rukh Khan Hindi movie poster",
        },
        {
            "name": "Kabir Singh",
            "year": 2019,
            "director": "Sandeep Reddy Vanga",
            "text_hints": [
                "ᴀ ᴅᴏᴄᴛᴏʀ ꜱᴘɪʀᴀʟꜱ ɪɴᴛᴏ ꜱᴇʟꜰ-ᴅᴇꜱᴛʀᴜᴄᴛɪᴏɴ",
                "ꜱʜᴀʜɪᴅ ᴋᴀᴘᴏᴏʀ'ꜱ ɪᴄᴏɴɪᴄ ʀᴏʟᴇ",
                "ʀᴇᴍᴀᴋᴇ ᴏꜰ ᴀʀᴊᴜɴ ʀᴇᴅᴅʏ",
                "ᴛᴜᴍ ʜɪ ᴀᴀɴᴀ ꜱᴏɴɢ ʜɪᴛ",
            ],
            "emoji_puzzle": "👨‍⚕️💔🍺🔥 = ?",
            "dialogue": '"ᴊʜᴜᴋᴀ ɴᴀʜɪ... ᴋᴀʙɪʀ ꜱɪɴɢʜ ᴋᴀʙʜɪ ᴊʜᴜᴋᴀ ɴᴀʜɪ!"',
            "songs": ["Tujhe Kitna Chahne Lage", "Bekhayali", "Mere Sohneya"],
            "image_search": "Kabir Singh 2019 Shahid Kapoor Hindi movie poster",
        },
        {
            "name": "RRR",
            "year": 2022,
            "director": "SS Rajamouli",
            "text_hints": [
                "ꜱꜱ ʀᴀᴊᴀᴍᴏᴜʟɪ ᴅɪʀᴇᴄᴛᴇᴅ ᴇᴘɪᴄ",
                "ᴛᴡᴏ ʟᴇɢᴇɴᴅᴀʀʏ ꜰʀᴇᴇᴅᴏᴍ ꜰɪɢʜᴛᴇʀꜱ",
                "ɴᴛʀ ᴀɴᴅ ʀᴀᴍ ᴄʜᴀʀᴀɴ ᴀᴄᴛᴇᴅ",
                "ɴᴀᴀᴛᴜ ɴᴀᴀᴛᴜ ᴡᴏɴ ᴏꜱᴄᴀʀ",
            ],
            "emoji_puzzle": "🔥💧🤝🇮🇳⚔️ = ?",
            "dialogue": '"ᴅᴏꜱᴛɪ ᴋʜᴏᴏɴ ꜱᴇ ʟɪᴋʜɪ ᴊᴀᴛɪ ʜᴀɪ."',
            "songs": ["Naatu Naatu", "Dosti", "Komuram Bheemudo"],
            "image_search": "RRR 2022 NTR Ram Charan movie poster",
        },
    ],
    "english": [
        {
            "name": "Avengers: Endgame",
            "year": 2019,
            "director": "Russo Brothers",
            "text_hints": [
                "ᴛʜᴇ ᴜʟᴛɪᴍᴀᴛᴇ ꜱᴜᴘᴇʀʜᴇʀᴏ ꜱʜᴏᴡᴅᴏᴡɴ",
                "ᴛɪᴍᴇ ᴛʀᴀᴠᴇʟ ᴛᴏ ᴜɴᴅᴏ ᴛʜᴇ ꜱɴᴀᴘ",
                "ᴍᴄᴜ ʙɪɢɢᴇꜱᴛ ʙᴏx ᴏꜰꜰɪᴄᴇ ʜɪᴛ",
                "3 ʜᴏᴜʀꜱ ᴏꜰ ᴇᴘɪᴄ ᴄɪɴᴇᴍᴀ",
            ],
            "emoji_puzzle": "⏰💎🦸🏆🌌 = ?",
            "dialogue": '"I am Iron Man."',
            "songs": ["Portals Theme Avengers", "Avengers Theme Orchestra", "I Am Iron Man"],
            "image_search": "Avengers Endgame 2019 movie poster",
        },
        {
            "name": "Inception",
            "year": 2010,
            "director": "Christopher Nolan",
            "text_hints": [
                "ᴅʀᴇᴀᴍꜱ ᴡɪᴛʜɪɴ ᴅʀᴇᴀᴍꜱ",
                "ʟᴇᴏɴᴀʀᴅᴏ ᴅɪᴄᴀᴘʀɪᴏ ᴍᴀꜱᴛᴇʀᴘɪᴇᴄᴇ",
                "ꜱᴘɪɴɴɪɴɢ ᴛᴏᴘ ᴇɴᴅɪɴɢ",
                "ᴄʜʀɪꜱᴛᴏᴘʜᴇʀ ɴᴏʟᴀɴ 2010",
            ],
            "emoji_puzzle": "💤🌀🧠🔫⏱ = ?",
            "dialogue": '"You\'re waiting for a train..."',
            "songs": ["Time Hans Zimmer", "Dream Is Collapsing", "528491"],
            "image_search": "Inception 2010 Leonardo DiCaprio movie poster",
        },
        {
            "name": "The Dark Knight",
            "year": 2008,
            "director": "Christopher Nolan",
            "text_hints": [
                "ᴛʜᴇ ɢʀᴇᴀᴛᴇꜱᴛ ꜱᴜᴘᴇʀʜᴇʀᴏ ᴍᴏᴠɪᴇ ᴇᴠᴇʀ",
                "ʜᴇᴀᴛʜ ʟᴇᴅɢᴇʀ'ꜱ ɪᴄᴏɴɪᴄ ᴊᴏᴋᴇʀ",
                "ɢᴏᴛʜᴀᴍ ᴄɪᴛʏ ɪɴ ᴄʜᴀᴏꜱ",
                "ᴄʜʀɪꜱᴛɪᴀɴ ʙᴀʟᴇ ᴀꜱ ʙᴀᴛᴍᴀɴ",
            ],
            "emoji_puzzle": "🦇🃏🌃🔥💀 = ?",
            "dialogue": '"Why so serious?"',
            "songs": ["Dark Knight Theme Hans Zimmer", "Why So Serious", "Batman Dark Knight OST"],
            "image_search": "The Dark Knight 2008 Joker Batman movie poster",
        },
        {
            "name": "Interstellar",
            "year": 2014,
            "director": "Christopher Nolan",
            "text_hints": [
                "ᴀ ꜰᴀᴛʜᴇʀ ᴛʀᴀᴠᴇʟꜱ ᴛʜʀᴏᴜɢʜ ᴀ ᴡᴏʀᴍʜᴏʟᴇ",
                "ᴍᴀᴛᴛ ᴅᴀᴍᴏɴ ʜɪᴅᴅᴇɴ ꜱᴜʀᴘʀɪꜱᴇ",
                "ʙʟᴀᴄᴋ ʜᴏʟᴇ ꜱᴄɪᴇɴᴄᴇ",
                "ʜᴀɴꜱ ᴢɪᴍᴍᴇʀ ᴏʀɢᴀɴ ᴍᴜꜱɪᴄ",
            ],
            "emoji_puzzle": "🚀🌌⏱👨‍👧🕳 = ?",
            "dialogue": '"Do not go gentle into that good night."',
            "songs": ["Cornfield Chase Hans Zimmer", "Stay Interstellar", "No Time For Caution"],
            "image_search": "Interstellar 2014 Matthew McConaughey movie poster",
        },
        {
            "name": "Spider-Man: No Way Home",
            "year": 2021,
            "director": "Jon Watts",
            "text_hints": [
                "ᴛʜʀᴇᴇ ꜱᴘɪᴅᴇʀᴍᴇɴ ɪɴ ᴏɴᴇ ꜰɪʟᴍ",
                "ᴅᴏᴄᴛᴏʀ ꜱᴛʀᴀɴɢᴇ ᴏᴘᴇɴꜱ ᴍᴜʟᴛɪᴠᴇʀꜱᴇ",
                "ᴛᴏᴍ ʜᴏʟʟᴀɴᴅ'ꜱ ʙɪɢɢᴇꜱᴛ ꜰɪʟᴍ",
                "ʀᴇᴜɴɪᴏɴ ᴏꜰ ᴀʟʟ ꜱᴘɪᴅᴇʏ ᴠɪʟʟᴀɪɴꜱ",
            ],
            "emoji_puzzle": "🕷×3️⃣🌀🦸‍♂️ = ?",
            "dialogue": '"With great power comes great responsibility."',
            "songs": ["Spider-Man No Way Home Theme", "Friendly Neighborhood", "Spiderman OST 2021"],
            "image_search": "Spider-Man No Way Home 2021 movie poster",
        },
    ],
}
# ================================================================
# GAME STATE  (in-memory, per chat)
# ================================================================
games: dict = {}
# ================================================================
# REWARDS CONFIG
# ================================================================
BASE_COINS        = 60
FAST_BONUS        = 25      # ≤ 15s
HOST_COINS        = 40
HOST_XP           = 20
GUESSER_XP        = 30
STREAK_THRESHOLD  = 3
STREAK_BONUS      = 20
# ================================================================
# BLUR REVEAL LEVELS
# ================================================================
BLUR_LEVELS = [
    ("🌫 ᴠᴇʀʏ ʙʟᴜʀʀᴇᴅ ᴘᴏꜱᴛᴇʀ", 20),
    ("🌁 ꜱʟɪɢʜᴛʟʏ ᴄʟᴇᴀʀᴇʀ", 14),
    ("🖼 ᴍᴏʀᴇ ᴠɪꜱɪʙʟᴇ", 8),
    ("📸 ᴀʟᴍᴏꜱᴛ ᴄʟᴇᴀʀ", 3),
    ("✅ ꜰᴜʟʟ ɪᴍᴀɢᴇ", 0),
]
# ================================================================
# DATABASE HELPERS
# ================================================================
async def _add_score(chat_id, user, role, coins, xp, elapsed, movie_name) -> dict:
    now = datetime.utcnow()
    doc = await score_col.find_one({"chat_id": chat_id, "user_id": user.id})
    if not doc:
        new_doc = {
            "chat_id":        chat_id,
            "user_id":        user.id,
            "name":           user.first_name,
            "coins":          coins,
            "xp":             xp,
            "today":          coins,
            "weekly":         coins,
            "monthly":        coins,
            "movies_guessed": 1 if role == "guesser" else 0,
            "movies_hosted":  1 if role == "host" else 0,
            "streak":         0,
            "updated":        now,
        }
        await score_col.insert_one(new_doc)
        return new_doc
    upd = {
        "$inc": {
            "coins": coins, "xp": xp,
            "today": coins, "weekly": coins, "monthly": coins,
        },
        "$set": {"name": user.first_name, "updated": now},
    }
    if role == "guesser":
        upd["$inc"]["movies_guessed"] = 1
    else:
        upd["$inc"]["movies_hosted"] = 1
    await score_col.update_one({"_id": doc["_id"]}, upd)
    updated = dict(doc)
    for k, v in upd["$inc"].items():
        updated[k] = updated.get(k, 0) + v
    updated.update(upd.get("$set", {}))
    return updated
async def _get_rank(chat_id, user_id) -> int:
    doc = await score_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        return 0
    return await score_col.count_documents(
        {"chat_id": chat_id, "coins": {"$gt": doc.get("coins", 0)}}
    ) + 1
async def _get_top(chat_id, field="coins") -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines, i = [], 0
    async for u in score_col.find({"chat_id": chat_id}).sort(field, -1).limit(10):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        val   = u.get(field, 0)
        title = get_display_title(u.get("coins", 0), u.get("movies_hosted", 0))
        lines.append(
            f"{medal} **{u['name']}**  {title}\n"
            f"    💰 {val} ᴄᴏɪɴꜱ  🎬 {u.get('movies_guessed', 0)} ᴍᴏᴠɪᴇꜱ"
        )
        i += 1
    return "\n".join(lines) if lines else "ɴᴏ ᴘʟᴀʏᴇʀꜱ ʏᴇᴛ."
async def _reset_periodic():
    """Periodically reset daily/weekly/monthly scores. Runs as a background task."""
    while True:
        try:
            now = datetime.utcnow()
            meta = await meta_col.find_one({"_id": "reset_meta"}) or {}
            today_str   = now.strftime("%Y-%m-%d")
            weekly_str  = f"{now.year}-W{now.isocalendar()[1]:02d}"
            monthly_str = now.strftime("%Y-%m")
            if meta.get("day") != today_str:
                await score_col.update_many({}, {"$set": {"today": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"day": today_str}}, upsert=True)
            if meta.get("week") != weekly_str:
                await score_col.update_many({}, {"$set": {"weekly": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"week": weekly_str}}, upsert=True)
            if meta.get("month") != monthly_str:
                await score_col.update_many({}, {"$set": {"monthly": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"month": monthly_str}}, upsert=True)
        except Exception as e:
            print(f"[moviegame] reset error: {e}")
        await asyncio.sleep(3600)
# ================================================================
# ADMIN CHECK
# ================================================================
async def _is_admin(chat_id, user_id) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False
# ================================================================
# IMAGE BLUR/REVEAL HELPERS
# ================================================================
async def _fetch_and_blur_poster(query: str, blur_radius: int) -> bytes | None:
    """Generate a placeholder blurred poster image (no external API needed)."""
    try:
        # FIX 5: removed unused search_url variable
        img = Image.new("RGB", (400, 560), color=(30, 30, 50))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(_FONT_PATH, 24)
        except Exception:
            font = ImageFont.load_default()
        for y in range(0, 560, 80):
            for x in range(0, 400, 80):
                draw.text((x + 20, y + 20), "🎬", font=font, fill=(80, 80, 120))
        draw.text((120, 240), "GUESS\nTHE\nMOVIE", font=font, fill=(200, 200, 255))
        if blur_radius > 0:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"[moviegame] blur error: {e}")
        return None
async def _send_blurred_image(chat_id: int, query: str, blur_radius: int, caption: str):
    """Send a blurred/revealed image to the chat."""
    try:
        img_bytes = await _fetch_and_blur_poster(query, blur_radius)
        if img_bytes:
            buf = io.BytesIO(img_bytes)
            buf.name = "poster.png"
            await app.send_photo(chat_id, photo=buf, caption=caption)
    except Exception as e:
        print(f"[moviegame] send image error: {e}")
# ================================================================
# AUDIO HINT HELPER
# ================================================================
async def _play_song_hint(chat_id: int, song_name: str, movie_name: str):
    """Search and play a short song clip as voice chat hint."""
    try:
        results = VideosSearch(f"{song_name} {movie_name} song", limit=1)
        data = await results.next()
        if not data or not data.get("result"):
            return
        result = data["result"][0]
        vidid  = result["id"]
        title  = result["title"]
        dur    = result.get("duration", "0:30")
        link   = f"https://www.youtube.com/watch?v={vidid}"
        file_path = await download_song(link)
        if not file_path:
            return
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id, chat_id, file_path, f"🎵 {title} [Hint]",
                dur, "Movie Game", vidid, 0, "audio"
            )
        else:
            try:
                await SHASHA.join_call(chat_id, chat_id, file_path, video=None)
                db[chat_id] = []         # FIX 4: use module-level db
                await put_queue(
                    chat_id, chat_id, file_path,
                    f"🎵 {title} [Hint]", dur, "Movie Game",
                    vidid, 0, "audio"
                )
            except Exception as e:
                print(f"[moviegame] vc join error for hint: {e}")
        await app.send_message(
            chat_id,
            f"🎵 **ᴀᴜᴅɪᴏ ʜɪɴᴛ ᴘʟᴀʏɪɴɢ!**\n`{title}`\nɢᴜᴇꜱꜱ ᴛʜᴇ ᴍᴏᴠɪᴇ ꜰʀᴏᴍ ᴛʜɪꜱ ꜱᴏɴɢ!"
        )
    except Exception as e:
        print(f"[moviegame] audio hint error: {e}")
# ================================================================
# SONG PLAYER AFTER CORRECT GUESS
# ================================================================
async def _play_movie_song(chat_id: int, song_name: str, movie_data: dict, user_name: str):
    """Play a selected movie song in voice chat."""
    try:
        search_query = f"{song_name} {movie_data['name']} {movie_data['year']}"
        results = VideosSearch(search_query, limit=1)
        data = await results.next()
        if not data or not data.get("result"):
            await app.send_message(chat_id, f"❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ꜰɪɴᴅ `{song_name}` ᴏɴ ʏᴏᴜᴛᴜʙᴇ.")
            return
        result  = data["result"][0]
        vidid   = result["id"]
        title   = result["title"]
        dur     = result.get("duration", "0:00")
        link    = f"https://www.youtube.com/watch?v={vidid}"
        loading_msg = await app.send_message(
            chat_id,
            f"⏳ **ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ:** `{song_name}`\nᴡᴀɪᴛ ᴀ ᴍᴏᴍᴇɴᴛ..."
        )
        file_path = await download_song(link)
        if not file_path:
            await loading_msg.edit_text("❌ ᴅᴏᴡɴʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ. ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.")
            return
        try:
            img = await get_thumb(vidid)
        except Exception:
            img = None
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id, chat_id, file_path, title, dur,
                user_name, vidid, 0, "audio"
            )
            # FIX 3: aq_markup now imported at top level — no inline import needed
            btn = aq_markup(None, chat_id)
            position = len(db.get(chat_id) or []) - 1  # FIX 4: use module-level db
            await loading_msg.delete()
            if img:
                await app.send_photo(
                    chat_id, photo=img,
                    caption=(
                        f"✅ **ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ!**\n"
                        f"🎵 **{title}**\n"
                        f"🎬 {movie_data['name']} ({movie_data['year']})\n"
                        f"📌 ᴘᴏꜱɪᴛɪᴏɴ: #{position}\n"
                        f"👤 ʀᴇǫᴜᴇꜱᴛᴇᴅ ʙʏ: {user_name}"
                    ),
                    reply_markup=InlineKeyboardMarkup(btn),
                )
            else:
                await app.send_message(
                    chat_id,
                    f"✅ **ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ!**\n🎵 **{title}**\n📌 #{position}",
                    reply_markup=InlineKeyboardMarkup(btn),
                )
        else:
            db[chat_id] = []            # FIX 4: use module-level db
            await SHASHA.join_call(chat_id, chat_id, file_path, video=None, image=img)
            await put_queue(
                chat_id, chat_id, file_path, title, dur,
                user_name, vidid, 0, "audio", forceplay=False
            )
            # FIX 3: stream_markup now imported at top level — no inline import needed
            btn = stream_markup(None, vidid, chat_id)
            await loading_msg.delete()
            if img:
                await app.send_photo(
                    chat_id, photo=img,
                    caption=(
                        f"🎶 **ɴᴏᴡ ᴘʟᴀʏɪɴɢ!**\n"
                        f"🎵 **{title}**\n"
                        f"🎬 {movie_data['name']} ({movie_data['year']})\n"
                        f"👤 ʀᴇǫᴜᴇꜱᴛᴇᴅ ʙʏ: {user_name}"
                    ),
                    reply_markup=InlineKeyboardMarkup(btn),
                )
            else:
                await app.send_message(
                    chat_id,
                    f"🎶 **ɴᴏᴡ ᴘʟᴀʏɪɴɢ:** `{song_name}`\n🎬 {movie_data['name']}",
                )
    except Exception as e:
        print(f"[moviegame] play song error: {e}")
        await app.send_message(chat_id, f"❌ ᴇʀʀᴏʀ ᴘʟᴀʏɪɴɢ ꜱᴏɴɢ: {str(e)[:100]}")
# ================================================================
# SONG LIST KEYBOARD (shown after correct guess)
# ================================================================
def _song_list_kb(chat_id: int, songs: list, movie_name: str) -> InlineKeyboardMarkup:
    buttons = []
    for i, song in enumerate(songs):
        buttons.append([
            InlineKeyboardButton(
                f"🎵 {song[:35]}",
                callback_data=f"movg_song_{chat_id}_{i}",
            )
        ])
    buttons.append([
        InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ", callback_data=f"movg_close_{chat_id}"),
    ])
    return InlineKeyboardMarkup(buttons)
# ================================================================
# INLINE KEYBOARDS
# ================================================================
def _lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 ᴛᴀᴍɪʟ",   callback_data="movg_lang_tamil"),
            InlineKeyboardButton("🎭 ʜɪɴᴅɪ",   callback_data="movg_lang_hindi"),
            InlineKeyboardButton("🎞 ᴇɴɢʟɪꜱʜ", callback_data="movg_lang_english"),
        ],
        [
            InlineKeyboardButton("🔀 ʀᴀɴᴅᴏᴍ", callback_data="movg_lang_random"),
        ],
    ])
def _timeout_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ 30ꜱ",  callback_data=f"movg_time_{lang}_30"),
            InlineKeyboardButton("⏱ 60ꜱ",  callback_data=f"movg_time_{lang}_60"),
            InlineKeyboardButton("⏳ 120ꜱ", callback_data=f"movg_time_{lang}_120"),
            InlineKeyboardButton("🕐 300ꜱ", callback_data=f"movg_time_{lang}_300"),
        ],
    ])
def _hint_mode_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 ᴛᴇxᴛ ʜɪɴᴛ",     callback_data=f"movg_hint_text_{chat_id}"),
            InlineKeyboardButton("🧩 ᴇᴍᴏᴊɪ ᴘᴜᴢᴢʟᴇ",  callback_data=f"movg_hint_emoji_{chat_id}"),
        ],
        [
            InlineKeyboardButton("💬 ᴅɪᴀʟᴏɢᴜᴇ",      callback_data=f"movg_hint_dialogue_{chat_id}"),
            InlineKeyboardButton("🖼 ɪᴍᴀɢᴇ ʜɪɴᴛ",    callback_data=f"movg_hint_image_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🎵 ᴀᴜᴅɪᴏ ʜɪɴᴛ",    callback_data=f"movg_hint_audio_{chat_id}"),
        ],
        [
            InlineKeyboardButton("⏭ ꜱᴋɪᴘ ʀᴏᴜɴᴅ",    callback_data=f"movg_skip_{chat_id}"),
            InlineKeyboardButton("🛑 ꜱᴛᴏᴘ ɢᴀᴍᴇ",     callback_data=f"movg_stop_{chat_id}"),
        ],
    ])
def _host_game_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 +ᴛᴇxᴛ ʜɪɴᴛ",    callback_data=f"movg_morehint_text_{chat_id}"),
            InlineKeyboardButton("🧩 +ᴇᴍᴏᴊɪ",        callback_data=f"movg_morehint_emoji_{chat_id}"),
        ],
        [
            InlineKeyboardButton("💬 +ᴅɪᴀʟᴏɢᴜᴇ",    callback_data=f"movg_morehint_dialogue_{chat_id}"),
            InlineKeyboardButton("🖼 +ɪᴍᴀɢᴇ",        callback_data=f"movg_morehint_image_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🎵 +ᴀᴜᴅɪᴏ",        callback_data=f"movg_morehint_audio_{chat_id}"),
        ],
        [
            InlineKeyboardButton("⏭ ꜱᴋɪᴘ",          callback_data=f"movg_skip_{chat_id}"),
            InlineKeyboardButton("🛑 ꜱᴛᴏᴘ",          callback_data=f"movg_stop_{chat_id}"),
        ],
    ])
def _top_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 ᴍʏ ʀᴀɴᴋ",    callback_data=f"movg_myrank_{chat_id}"),
            InlineKeyboardButton("🌍 ᴀʟʟ ᴛɪᴍᴇ",   callback_data=f"movg_lb_global_{chat_id}"),
        ],
        [
            InlineKeyboardButton("📅 ᴛᴏᴅᴀʏ",       callback_data=f"movg_lb_today_{chat_id}"),
            InlineKeyboardButton("📆 ᴡᴇᴇᴋʟʏ",     callback_data=f"movg_lb_weekly_{chat_id}"),
            InlineKeyboardButton("🗓 ᴍᴏɴᴛʜʟʏ",    callback_data=f"movg_lb_monthly_{chat_id}"),
        ],
    ])
# ================================================================
# GAME ENGINE
# ================================================================
async def _timeout_handler(chat_id: int, movie_name: str, round_num: int, timeout: int):
    """Handle round timeout — reveal answer."""
    await asyncio.sleep(timeout)
    game = games.get(chat_id)
    if not game:
        return
    if game.get("movie", {}).get("name") != movie_name or game.get("round") != round_num:
        return
    if game.get("blur_task") and not game["blur_task"].done():
        game["blur_task"].cancel()
    game["movie"] = None
    try:
        await app.send_message(
            chat_id,
            f"⏰ **ᴛɪᴍᴇ ᴜᴘ!**\n\n"
            f"🎬 ᴛʜᴇ ᴍᴏᴠɪᴇ ᴡᴀꜱ: **{movie_name}**\n\n"
            f"🎮 ᴡʜᴏ ᴡᴀɴᴛꜱ ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ʜᴏꜱᴛ?",
            reply_markup=_become_host_kb(chat_id),
        )
    except Exception as e:
        print(f"[moviegame] timeout msg error: {e}")
async def _blur_reveal_loop(chat_id: int, movie_data: dict, round_num: int):
    """Progressive blur reveal every 10 seconds."""
    for label, blur_radius in BLUR_LEVELS:
        await asyncio.sleep(10)
        game = games.get(chat_id)
        if not game or game.get("round") != round_num:
            return
        if game.get("movie") is None:
            return
        await _send_blurred_image(
            chat_id,
            movie_data.get("image_search", movie_data["name"] + " movie poster"),
            blur_radius,
            f"{label}\n🎬 ɢᴜᴇꜱꜱ ᴛʜᴇ ᴍᴏᴠɪᴇ!"
        )
def _become_host_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Wanna be a HOST?", callback_data=f"movg_behost_{chat_id}"),
    ]])
async def _start_round(chat_id: int, host_uid: int, host_mention: str,
                       language: str, timeout: int):
    game = games.get(chat_id)
    if not game:
        return
    if game.get("timer_task") and not game["timer_task"].done():
        game["timer_task"].cancel()
    if game.get("blur_task") and not game["blur_task"].done():
        game["blur_task"].cancel()
    lang_movies = MOVIES.get(language, [])
    used = game.get("used_movies", set())
    available = [m for m in lang_movies if m["name"] not in used]
    if not available:
        game["used_movies"] = set()
        available = lang_movies
    movie = random.choice(available)
    game["used_movies"] = used | {movie["name"]}
    game["movie"]      = movie
    game["host"]       = host_uid
    game["start_time"] = time.time()
    game["round"]      = game.get("round", 0) + 1
    game["language"]   = language
    game["timeout"]    = timeout
    game["hints_given"] = []
    round_num          = game["round"]
    try:
        msg = await app.send_message(
            chat_id,
            f"<blockquote>🎬 **ᴍᴏᴠɪᴇ ɢᴜᴇꜱꜱ — ʀᴏᴜɴᴅ {round_num}**</blockquote>\n"
            f"<blockquote>"
            f"🎤 **ʜᴏꜱᴛ:** {host_mention}\n"
            f"🌐 **ʟᴀɴɢ:** {language.upper()}\n"
            f"⏱ **ᴛɪᴍᴇ:** {timeout}ꜱ\n\n"
            f"👁 ʜᴏꜱᴛ: ᴛᴀᴘ ᴀ ʜɪɴᴛ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ɢɪᴠᴇ ᴄʟᴜᴇꜱ!\n"
            f"✍️ **ᴇᴠᴇʀʏᴏɴᴇ ᴇʟꜱᴇ:** ᴛʏᴘᴇ ᴛʜᴇ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ!</blockquote>",
            reply_markup=_hint_mode_kb(chat_id),
        )
        game["round_msg_id"] = msg.id
    except Exception as e:
        print(f"[moviegame] start_round error: {e}")
    task = asyncio.create_task(
        _timeout_handler(chat_id, movie["name"], round_num, timeout)
    )
    game["timer_task"] = task
# ================================================================
# COMMANDS
# ================================================================
@Client.on_message(filters.command(["gmovie", "guessmovie"]) & filters.group)
async def cmd_guessmovie(_, m: Message):
    chat_id = m.chat.id
    # FIX 2: Start periodic reset task lazily on first /gmovie — loop is running here
    await _ensure_reset_task()
    if chat_id in games:
        return await m.reply(
            "⚠️ **ɢᴀᴍᴇ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!**\n"
            "ᴜꜱᴇ /stopmoviegame ᴛᴏ ᴇɴᴅ ɪᴛ ꜰɪʀꜱᴛ."
        )
    games[chat_id] = {
        "host":         None,
        "movie":        None,
        "start_time":   time.time(),
        "round":        0,
        "timer_task":   None,
        "blur_task":    None,
        "round_msg_id": None,
        "streak":       {},
        "started_by":   m.from_user.id,
        "used_movies":  set(),
        "language":     None,
        "timeout":      60,
        "hints_given":  [],
    }
    await add_served_chat(chat_id)
    await m.reply(
        f"<blockquote>🎬 **ɢᴜᴇꜱꜱ ᴛʜᴇ ᴍᴏᴠɪᴇ ɢᴀᴍᴇ!**</blockquote>\n"
        f"<blockquote>"
        f"👤 **ꜱᴛᴀʀᴛᴇᴅ ʙʏ:** {m.from_user.mention}\n\n"
        f"📋 **ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:**\n"
        f"1️⃣ ꜱᴇʟᴇᴄᴛ ᴀ ʟᴀɴɢᴜᴀɢᴇ ʙᴇʟᴏᴡ\n"
        f"2️⃣ ꜱᴇᴛ ᴛɪᴍᴇᴏᴜᴛ ᴅᴜʀᴀᴛɪᴏɴ\n"
        f"3️⃣ ꜱᴏᴍᴇᴏɴᴇ ᴛᴀᴘꜱ **🎬 Wanna be a HOST?**\n"
        f"4️⃣ ʜᴏꜱᴛ ᴘɪᴄᴋꜱ ᴀ ʜɪɴᴛ ᴛʏᴘᴇ (ᴛᴇxᴛ/ᴇᴍᴏᴊɪ/ɪᴍᴀɢᴇ/ᴀᴜᴅɪᴏ)\n"
        f"5️⃣ ᴇᴠᴇʀʏᴏɴᴇ ᴛʏᴘᴇꜱ ᴛʜᴇ ᴍᴏᴠɪᴇ ɴᴀᴍᴇ\n"
        f"6️⃣ ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇꜱꜱ → ꜱᴏɴɢ ʟɪꜱᴛ → ᴘɪᴄᴋ ᴀ ꜱᴏɴɢ → ᴠᴄ ᴘʟᴀʏ!\n\n"
        f"🌐 **ꜱᴇʟᴇᴄᴛ ʟᴀɴɢᴜᴀɢᴇ:**</blockquote>",
        reply_markup=_lang_kb(),
    )
@Client.on_message(filters.command(["stopmoviegame", "gmoviestop"]) & filters.group)
async def cmd_stop_movie(_, m: Message):
    chat_id = m.chat.id
    if chat_id not in games:
        return await m.reply("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.")
    uid  = m.from_user.id
    game = games[chat_id]
    if uid != game.get("started_by") and not await _is_admin(chat_id, uid):
        return await m.reply("❌ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ ꜱᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴ ᴄᴀɴ ꜱᴛᴏᴘ.")
    movie = (game.get("movie") or {}).get("name", "?")
    if game.get("timer_task") and not game["timer_task"].done():
        game["timer_task"].cancel()
    if game.get("blur_task") and not game["blur_task"].done():
        game["blur_task"].cancel()
    games.pop(chat_id, None)
    await m.reply(
        f"🛑 **ɢᴀᴍᴇ ꜱᴛᴏᴘᴘᴇᴅ!**\n"
        f"🎬 ᴛʜᴇ ᴍᴏᴠɪᴇ ᴡᴀꜱ: **{movie}**\n"
        f"ᴜꜱᴇ /gmovie ᴛᴏ ꜱᴛᴀʀᴛ ᴀɢᴀɪɴ."
    )
@Client.on_message(filters.command("movietop") & filters.group)
async def cmd_movietop(_, m: Message):
    chat_id = m.chat.id
    top = await _get_top(chat_id, "coins")
    await m.reply(
        f"<blockquote>🏆 **ᴍᴏᴠɪᴇ ɢᴀᴍᴇ ᴛᴏᴘ 10** — ᴛʜɪꜱ ɢʀᴏᴜᴘ</blockquote>\n"
        f"<blockquote>{top}</blockquote>",
        reply_markup=_top_kb(chat_id),
    )
@Client.on_message(filters.command("mymovrank") & filters.group)
async def cmd_mymovrank(_, m: Message):
    chat_id = m.chat.id
    uid     = m.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await m.reply(
            "📊 ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!\nᴜꜱᴇ /gmovie ᴛᴏ ꜱᴛᴀʀᴛ ᴀ ɢᴀᴍᴇ."
        )
    coins      = data.get("coins", 0)
    xp         = data.get("xp", 0)
    hosted     = data.get("movies_hosted", 0)
    guessed    = data.get("movies_guessed", 0)
    rank       = await _get_rank(chat_id, uid)
    ge, gn     = get_guesser_title(coins)
    he, hn     = get_host_title(hosted)
    display    = get_display_title(coins, hosted)
    next_g     = _next_guesser_title(coins)
    next_h     = _next_host_title(hosted)
    next_block = ""
    if next_g:
        next_block += f"\n🎯 ɴᴇxᴛ ɢᴜᴇꜱꜱᴇʀ: {next_g}"
    if next_h:
        next_block += f"\n🎯 ɴᴇxᴛ ʜᴏꜱᴛ: {next_h}"
    await m.reply(
        f"<blockquote>📊 **ᴍʏ ᴍᴏᴠɪᴇ ɢᴀᴍᴇ ʀᴀɴᴋ**</blockquote>\n"
        f"<blockquote>"
        f"{'━'*22}\n"
        f"🏅 **ʀᴀɴᴋ:**              #{rank}\n"
        f"🎖 **ᴛɪᴛʟᴇ:**             {display}\n"
        f"{'━'*22}\n"
        f"💰 **ᴛᴏᴛᴀʟ ᴄᴏɪɴꜱ:**      {coins}\n"
        f"⭐ **ᴛᴏᴛᴀʟ xᴘ:**         {xp}\n"
        f"📅 **ᴛᴏᴅᴀʏ:**             {data.get('today', 0)}\n"
        f"📆 **ᴡᴇᴇᴋʟʏ:**            {data.get('weekly', 0)}\n"
        f"🗓 **ᴍᴏɴᴛʜʟʏ:**           {data.get('monthly', 0)}\n"
        f"{'━'*22}\n"
        f"🎬 **ᴍᴏᴠɪᴇꜱ ɢᴜᴇꜱꜱᴇᴅ:**   {guessed}\n"
        f"🎤 **ᴍᴏᴠɪᴇꜱ ʜᴏꜱᴛᴇᴅ:**    {hosted}\n"
        f"{'━'*22}\n"
        f"{ge} **{gn}**\n"
        f"{he} **{hn}**"
        f"{next_block}</blockquote>",
        reply_markup=_top_kb(chat_id),
    )
# ================================================================
# GUESS HANDLER  —  group=-1
# ================================================================
@Client.on_message(
    filters.incoming
    & filters.text
    & filters.group
    & ~filters.command(
        ["gmovie", "guessmovie", "stopmoviegame", "gmoviestop",
         "movietop", "mymovrank"]
    )
    & ~filters.via_bot,
    group=-1,
)
async def check_movie_guess(_, m: Message):
    chat_id = m.chat.id
    if chat_id not in games:
        m.continue_propagation()
        return
    game = games[chat_id]
    movie = game.get("movie")
    if not movie:
        m.continue_propagation()
        return
    if m.from_user and m.from_user.id == game.get("host"):
        m.continue_propagation()
        return
    typed = (m.text or "").strip().lower()
    answer = movie["name"].lower()
    def normalize(s):
        s = _re.sub(r"[^a-z0-9 ]", "", s.lower())
        return s.strip()
    if normalize(typed) != normalize(answer):
        m.continue_propagation()
        return
    # ── CORRECT GUESS ────────────────────────────────────────────
    elapsed   = time.time() - game["start_time"]
    uid       = m.from_user.id
    if game.get("timer_task") and not game["timer_task"].done():
        game["timer_task"].cancel()
    if game.get("blur_task") and not game["blur_task"].done():
        game["blur_task"].cancel()
    game["movie"] = None
    coins       = BASE_COINS
    xp          = GUESSER_XP
    bonus_lines = []
    if elapsed <= 15:
        coins += FAST_BONUS
        bonus_lines.append(f"⚡ ꜰᴀꜱᴛ ʙᴏɴᴜꜱ: +**{FAST_BONUS}** ᴄᴏɪɴꜱ")
    streak = game.get("streak", {})
    streak[uid] = streak.get(uid, 0) + 1
    game["streak"] = streak
    if streak[uid] % STREAK_THRESHOLD == 0:
        coins += STREAK_BONUS
        bonus_lines.append(f"🔥 ꜱᴛʀᴇᴀᴋ x**{streak[uid]}**: +**{STREAK_BONUS}** ᴄᴏɪɴꜱ")
    mins, secs = divmod(int(elapsed), 60)
    updated_doc   = await _add_score(chat_id, m.from_user, "guesser", coins, xp, elapsed, movie["name"])
    rank          = await _get_rank(chat_id, uid)
    new_coins     = updated_doc.get("coins", coins)
    new_hosted    = updated_doc.get("movies_hosted", 0)
    display_title = get_display_title(new_coins, new_hosted)
    ge, gn        = get_guesser_title(new_coins)
    old_ge, _     = get_guesser_title(new_coins - coins)
    title_upgraded = old_ge != ge
    host_uid    = game.get("host")
    host_line   = ""
    if host_uid and host_uid != uid:
        try:
            host_user = await app.get_users(host_uid)
            host_doc  = await _add_score(
                chat_id, host_user, "host",
                HOST_COINS, HOST_XP, elapsed, movie["name"]
            )
            h_coins   = host_doc.get("coins", HOST_COINS)
            h_hosted  = host_doc.get("movies_hosted", 1)
            h_title   = get_display_title(h_coins, h_hosted)
            host_line = (
                f"\n\n🎤 **ʜᴏꜱᴛ:** {host_user.mention}  {h_title}\n"
                f"   +**{HOST_COINS}** ᴄᴏɪɴꜱ  ⭐ +**{HOST_XP}** xᴘ"
            )
        except Exception as e:
            print(f"[moviegame] host reward error: {e}")
    bonus_block  = ("\n" + "\n".join(bonus_lines)) if bonus_lines else ""
    title_line   = (
        f"\n🎖 **ᴛɪᴛʟᴇ ᴜᴘɢʀᴀᴅᴇ!**  {ge} {gn} 🎉"
        if title_upgraded else f"\n🎖 {display_title}"
    )
    win_caption = (
        f"<blockquote>🎉 **ᴄᴏʀʀᴇᴄᴛ!**  {m.from_user.mention}</blockquote>\n"
        f"<blockquote>"
        f"🎬 **ᴍᴏᴠɪᴇ:**   {movie['name']} ({movie['year']})\n"
        f"🎥 **ᴅɪʀᴇᴄᴛᴏʀ:** {movie['director']}\n"
        f"⏱ **ᴛɪᴍᴇ:**    {mins}ᴍ {secs}ꜱ\n"
        f"🏅 **ʀᴀɴᴋ:**    #{rank}\n"
        f"💰 +**{coins}** ᴄᴏɪɴꜱ  ⭐ +**{xp}** xᴘ"
        f"{bonus_block}"
        f"{title_line}"
        f"{host_line}</blockquote>"
    )
    await m.reply(win_caption)
    await asyncio.sleep(1)
    songs = movie.get("songs", [])
    if songs and chat_id in games:
        games[chat_id]["pending_songs"]  = songs
        games[chat_id]["pending_movie"]  = movie
        games[chat_id]["pending_user"]   = m.from_user.first_name
        song_text = "\n".join(f"🎵 {s}" for s in songs)
        await app.send_message(
            chat_id,
            f"<blockquote>🎶 **ꜱᴏɴɢꜱ ꜰʀᴏᴍ {movie['name']}**</blockquote>\n"
            f"<blockquote>{song_text}\n\n"
            f"👆 ᴛᴀᴘ ᴀ ꜱᴏɴɢ ᴛᴏ ᴘʟᴀʏ ɪɴ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ!</blockquote>",
            reply_markup=_song_list_kb(chat_id, songs, movie["name"]),
        )
    await asyncio.sleep(5)
    if chat_id in games:
        try:
            await app.send_message(
                chat_id,
                f"🎬 ʀᴏᴜɴᴅ **{game['round']}** ᴅᴏɴᴇ!\n"
                f"ᴡʜᴏ ᴡᴀɴᴛꜱ ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ʜᴏꜱᴛ?",
                reply_markup=_become_host_kb(chat_id),
            )
        except Exception as e:
            print(f"[moviegame] next host btn error: {e}")
# ================================================================
# CALLBACK QUERIES
# ================================================================
@Client.on_callback_query(filters.regex(r"^movg_lang_(.+)$"))
async def cb_lang(_, q):
    lang = q.data.split("_", 2)[2]
    chat_id = q.message.chat.id
    if chat_id not in games:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    if q.from_user.id != games[chat_id].get("started_by") and not await _is_admin(chat_id, q.from_user.id):
        return await q.answer("❌ ᴏɴʟʏ ꜱᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴ ᴄᴀɴ ꜱᴇᴛ ʟᴀɴɢᴜᴀɢᴇ.", show_alert=True)
    if lang == "random":
        lang = random.choice(["tamil", "hindi", "english"])
    games[chat_id]["language"] = lang
    await q.answer(f"✅ {lang.upper()} ꜱᴇʟᴇᴄᴛᴇᴅ!")
    try:
        await q.message.edit_text(
            f"<blockquote>🌐 **ʟᴀɴɢᴜᴀɢᴇ:** {lang.upper()}</blockquote>\n"
            f"<blockquote>⏱ **ꜱᴇʟᴇᴄᴛ ᴛɪᴍᴇᴏᴜᴛ ᴅᴜʀᴀᴛɪᴏɴ:**</blockquote>",
            reply_markup=_timeout_kb(lang),
        )
    except Exception:
        pass
@Client.on_callback_query(filters.regex(r"^movg_time_(.+)_(\d+)$"))
async def cb_timeout(_, q):
    m2      = _re.match(r"^movg_time_(.+)_(\d+)$", q.data)
    lang    = m2.group(1)
    timeout = int(m2.group(2))
    chat_id = q.message.chat.id
    if chat_id not in games:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    games[chat_id]["timeout"]  = timeout
    games[chat_id]["language"] = lang
    await q.answer(f"✅ {timeout}ꜱ ꜱᴇᴛ!")
    try:
        await q.message.edit_text(
            f"<blockquote>🎬 **ɢᴀᴍᴇ ꜱᴇᴛᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇ!**</blockquote>\n"
            f"<blockquote>"
            f"🌐 ʟᴀɴɢ: **{lang.upper()}**\n"
            f"⏱ ᴛɪᴍᴇ: **{timeout}ꜱ**\n\n"
            f"👇 ᴛᴀᴘ ᴛᴏ ʙᴇᴄᴏᴍᴇ ᴛʜᴇ ꜰɪʀꜱᴛ ʜᴏꜱᴛ!</blockquote>",
            reply_markup=_become_host_kb(chat_id),
        )
    except Exception:
        pass
@Client.on_callback_query(filters.regex(r"^movg_behost_(-?\d+)$"))
async def cb_behost(_, q):
    chat_id = int(q.data.split("_")[2])
    if chat_id not in games:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    game = games[chat_id]
    if game.get("movie"):
        return await q.answer("⚠️ ᴀ ʀᴏᴜɴᴅ ɪꜱ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ!", show_alert=True)
    lang    = game.get("language") or "tamil"
    timeout = game.get("timeout") or 60
    uid     = q.from_user.id
    mention = q.from_user.mention
    data = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    he, hn = get_host_title(data.get("movies_hosted", 0) if data else 0)
    await q.answer(f"✅ ʏᴏᴜ ᴀʀᴇ ᴛʜᴇ ʜᴏꜱᴛ! {he}", show_alert=False)
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _start_round(chat_id, uid, mention, lang, timeout)
@Client.on_callback_query(filters.regex(r"^movg_hint_(text|emoji|dialogue|image|audio)_(-?\d+)$"))
async def cb_hint_first(_, q):
    m2      = _re.match(r"^movg_hint_(text|emoji|dialogue|image|audio)_(-?\d+)$", q.data)
    mode    = m2.group(1)
    chat_id = int(m2.group(2))
    await _handle_hint(q, chat_id, mode, replace_kb=True)
@Client.on_callback_query(filters.regex(r"^movg_morehint_(text|emoji|dialogue|image|audio)_(-?\d+)$"))
async def cb_hint_more(_, q):
    m2      = _re.match(r"^movg_morehint_(text|emoji|dialogue|image|audio)_(-?\d+)$", q.data)
    mode    = m2.group(1)
    chat_id = int(m2.group(2))
    await _handle_hint(q, chat_id, mode, replace_kb=False)
async def _handle_hint(q, chat_id: int, mode: str, replace_kb: bool):
    """Common hint handler for both first and additional hints."""
    game = games.get(chat_id)
    if not game or not game.get("movie"):
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴏᴜɴᴅ.", show_alert=True)
    if q.from_user.id != game.get("host"):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ʜᴏꜱᴛ ᴄᴀɴ ɢɪᴠᴇ ʜɪɴᴛꜱ.", show_alert=True)
    movie   = game["movie"]
    hints   = game.get("hints_given", [])
    # FIX 1: Allow "text" mode to repeat — it has 4 progressive clues to reveal.
    # Only block non-text modes from being given more than once.
    if mode != "text" and mode in hints:
        return await q.answer(f"⚠️ {mode.upper()} ʜɪɴᴛ ᴀʟʀᴇᴀᴅʏ ɢɪᴠᴇɴ!", show_alert=True)
    hints.append(mode)
    game["hints_given"] = hints
    await q.answer(f"✅ {mode.upper()} ʜɪɴᴛ ꜱᴇɴᴅɪɴɢ!")
    try:
        if replace_kb:
            await q.message.edit_reply_markup(reply_markup=_host_game_kb(chat_id))
    except Exception:
        pass
    if mode == "text":
        hint_list   = movie.get("text_hints", [])
        given_count = sum(1 for h in hints if h == "text")   # how many text hints so far
        idx         = min(given_count - 1, len(hint_list) - 1)
        hint_text   = hint_list[idx] if hint_list else "ɴᴏ ʜɪɴᴛ"
        await app.send_message(
            chat_id,
            f"<blockquote>📝 **ᴛᴇxᴛ ʜɪɴᴛ #{given_count}**</blockquote>\n"
            f"<blockquote>💡 {hint_text}</blockquote>"
        )
    elif mode == "emoji":
        await app.send_message(
            chat_id,
            f"<blockquote>🧩 **ᴇᴍᴏᴊɪ ᴘᴜᴢᴢʟᴇ**</blockquote>\n"
            f"<blockquote>{movie.get('emoji_puzzle', '🎬 = ?')}\n\n"
            f"🤔 ᴡʜᴀᴛ ᴍᴏᴠɪᴇ ᴅᴏ ᴛʜᴇꜱᴇ ᴇᴍᴏᴊɪꜱ ʀᴇᴘʀᴇꜱᴇɴᴛ?</blockquote>"
        )
    elif mode == "dialogue":
        await app.send_message(
            chat_id,
            f"<blockquote>💬 <b>Famous Dialogue</b></blockquote>\n"
            f"<blockquote>{movie.get('dialogue', '...')}\n\n"
            f"🎬 From which movie is this?</blockquote>"
        )
    elif mode == "image":
        round_num = game["round"]
        blur_task = asyncio.create_task(
            _blur_reveal_loop(chat_id, movie, round_num)
        )
        game["blur_task"] = blur_task
        await _send_blurred_image(
            chat_id,
            movie.get("image_search", movie["name"] + " movie poster"),
            20,
            f"🌫 **ɪᴍᴀɢᴇ ʜɪɴᴛ** — ᴠᴇʀʏ ʙʟᴜʀʀᴇᴅ\nɪᴍᴀɢᴇ ᴡɪʟʟ ꜰᴀᴅᴇ ɪɴ ᴇᴠᴇʀʏ 10ꜱ..."
        )
    elif mode == "audio":
        songs = movie.get("songs", [])
        if songs:
            hint_song = random.choice(songs)
            await _play_song_hint(chat_id, hint_song, movie["name"])
        else:
            await q.answer("ɴᴏ ᴀᴜᴅɪᴏ ᴀᴠᴀɪʟᴀʙʟᴇ ꜰᴏʀ ᴛʜɪꜱ ᴍᴏᴠɪᴇ!", show_alert=True)
@Client.on_callback_query(filters.regex(r"^movg_skip_(-?\d+)$"))
async def cb_skip(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    uid = q.from_user.id
    if uid != game.get("host") and not await _is_admin(chat_id, uid):
        return await q.answer("❌ ᴏɴʟʏ ʜᴏꜱᴛ ᴏʀ ᴀᴅᴍɪɴ ᴄᴀɴ ꜱᴋɪᴘ.", show_alert=True)
    movie = (game.get("movie") or {}).get("name", "?")
    if game.get("timer_task") and not game["timer_task"].done():
        game["timer_task"].cancel()
    if game.get("blur_task") and not game["blur_task"].done():
        game["blur_task"].cancel()
    game["movie"] = None
    await q.answer("⏭ ꜱᴋɪᴘᴘᴇᴅ!")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await app.send_message(
        chat_id,
        f"⏭ **ꜱᴋɪᴘᴘᴇᴅ!**\n🎬 ᴛʜᴇ ᴍᴏᴠɪᴇ ᴡᴀꜱ **{movie}**\n\n"
        f"ᴡʜᴏ ᴡᴀɴᴛꜱ ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ʜᴏꜱᴛ?",
        reply_markup=_become_host_kb(chat_id),
    )
@Client.on_callback_query(filters.regex(r"^movg_stop_(-?\d+)$"))
async def cb_stop(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    uid = q.from_user.id
    if uid != game.get("started_by") and not await _is_admin(chat_id, uid):
        return await q.answer("❌ ᴏɴʟʏ ꜱᴛᴀʀᴛᴇʀ ᴏʀ ᴀᴅᴍɪɴ ᴄᴀɴ ꜱᴛᴏᴘ.", show_alert=True)
    movie = (game.get("movie") or {}).get("name", "?")
    if game.get("timer_task") and not game["timer_task"].done():
        game["timer_task"].cancel()
    if game.get("blur_task") and not game["blur_task"].done():
        game["blur_task"].cancel()
    games.pop(chat_id, None)
    await q.answer("🛑 ꜱᴛᴏᴘᴘᴇᴅ!")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await app.send_message(
        chat_id,
        f"🛑 **ɢᴀᴍᴇ ꜱᴛᴏᴘᴘᴇᴅ ʙʏ** {q.from_user.mention}\n"
        f"🎬 ᴛʜᴇ ᴍᴏᴠɪᴇ ᴡᴀꜱ: **{movie}**\n\n"
        f"ᴜꜱᴇ /gmovie ᴛᴏ ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ!"
    )
@Client.on_callback_query(filters.regex(r"^movg_song_(-?\d+)_(\d+)$"))
async def cb_song_select(_, q):
    m2      = _re.match(r"^movg_song_(-?\d+)_(\d+)$", q.data)
    chat_id = int(m2.group(1))
    idx     = int(m2.group(2))
    game    = games.get(chat_id)
    if not game:
        return await q.answer("⚠️ ɢᴀᴍᴇ ᴇɴᴅᴇᴅ.", show_alert=True)
    songs  = game.get("pending_songs", [])
    movie  = game.get("pending_movie", {})
    if not songs or idx >= len(songs):
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ ꜱᴏɴɢ.", show_alert=True)
    song_name = songs[idx]
    user_name = q.from_user.first_name
    await q.answer(f"🎵 ᴘʟᴀʏɪɴɢ: {song_name}")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _play_movie_song(chat_id, song_name, movie, user_name)
@Client.on_callback_query(filters.regex(r"^movg_close_(-?\d+)$"))
async def cb_close(_, q):
    await q.answer()
    try:
        await q.message.delete()
    except Exception:
        pass
@Client.on_callback_query(filters.regex(r"^movg_lb_(global|today|weekly|monthly)_(-?\d+)$"))
async def cb_leaderboard(_, q):
    m2      = _re.match(r"^movg_lb_(global|today|weekly|monthly)_(-?\d+)$", q.data)
    mode    = m2.group(1)
    chat_id = int(m2.group(2))
    FIELD_MAP = {
        "global":  ("coins",   "🌍 **ᴀʟʟ-ᴛɪᴍᴇ ᴛᴏᴘ 10**"),
        "today":   ("today",   "📅 **ᴛᴏᴅᴀʏ'ꜱ ᴛᴏᴘ 10**"),
        "weekly":  ("weekly",  "📆 **ᴡᴇᴇᴋʟʏ ᴛᴏᴘ 10**"),
        "monthly": ("monthly", "🗓 **ᴍᴏɴᴛʜʟʏ ᴛᴏᴘ 10**"),
    }
    field, title = FIELD_MAP[mode]
    top          = await _get_top(chat_id, field)
    await q.answer()
    try:
        await q.message.edit_text(
            f"<blockquote>{title}</blockquote>\n<blockquote>{top}</blockquote>",
            reply_markup=_top_kb(chat_id),
        )
    except Exception:
        pass
@Client.on_callback_query(filters.regex(r"^movg_myrank_(-?\d+)$"))
async def cb_myrank(_, q):
    chat_id = int(q.data.split("_")[2])
    uid     = q.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await q.answer("ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!", show_alert=True)
    coins   = data.get("coins", 0)
    hosted  = data.get("movies_hosted", 0)
    rank    = await _get_rank(chat_id, uid)
    display = get_display_title(coins, hosted)
    ge, gn  = get_guesser_title(coins)
    he, hn  = get_host_title(hosted)
    next_g  = _next_guesser_title(coins)
    next_h  = _next_host_title(hosted)
    next_block = ""
    if next_g:
        next_block += f"\n🎯 ɴᴇxᴛ ɢ: {next_g}"
    if next_h:
        next_block += f"\n🎯 ɴᴇxᴛ ʜ: {next_h}"
    await q.answer()
    try:
        await q.message.edit_text(
            f"<blockquote>📊 **ᴍʏ ꜱᴛᴀᴛꜱ** — {q.from_user.mention}</blockquote>\n"
            f"<blockquote>"
            f"🏅 **ʀᴀɴᴋ:**   #{rank}\n"
            f"🎖 **ᴛɪᴛʟᴇ:**  {display}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 **ᴄᴏɪɴꜱ:**  {coins}\n"
            f"⭐ **xᴘ:**     {data.get('xp', 0)}\n"
            f"📅 **ᴛᴏᴅᴀʏ:** {data.get('today', 0)}\n"
            f"📆 **ᴡᴇᴇᴋ:**  {data.get('weekly', 0)}\n"
            f"🗓 **ᴍᴏɴᴛʜ:** {data.get('monthly', 0)}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎬 **ɢᴜᴇꜱꜱᴇᴅ:**   {data.get('movies_guessed', 0)}\n"
            f"🎤 **ʜᴏꜱᴛᴇᴅ:**    {hosted}\n"
            f"━━━━━━━━━━━━━━\n"
            f"{ge} **{gn}**\n"
            f"{he} **{hn}**"
            f"{next_block}</blockquote>",
            reply_markup=_top_kb(chat_id),
        )
    except Exception:
        pass
# ================================================================
# MODULE META
# ================================================================
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_91"
__help__     = """
🎬 ᴍᴏᴠɪᴇ ɢᴜᴇꜱꜱ ɢᴀᴍᴇ
🔻 /gmovie ᴏʀ /guessmovie ➠ ꜱᴛᴀʀᴛ ɢᴀᴍᴇ
🔻 /stopmoviegame ➠ ꜱᴛᴏᴘ ɢᴀᴍᴇ
🔻 /movietop ➠ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /mymovrank ➠ ᴍʏ ʀᴀɴᴋ & ꜱᴛᴀᴛꜱ
💡 ʜɪɴᴛ ᴍᴏᴅᴇꜱ:
  📝 ᴛᴇxᴛ ʜɪɴᴛ
  🧩 ᴇᴍᴏᴊɪ ᴘᴜᴢᴢʟᴇ
  💬 ᴅɪᴀʟᴏɢᴜᴇ
  🖼 ɪᴍᴀɢᴇ (ʙʟᴜʀ ʀᴇᴠᴇᴀʟ)
  🎵 ᴀᴜᴅɪᴏ (ᴠᴄ ᴘʟᴀʏ)
🌐 ʟᴀɴɢᴜᴀɢᴇꜱ: ᴛᴀᴍɪʟ | ʜɪɴᴅɪ | ᴇɴɢʟɪꜱʜ | ʀᴀɴᴅᴏᴍ
⏱ ᴛɪᴍᴇᴏᴜᴛ: 30ꜱ | 60ꜱ | 120ꜱ | 300ꜱ
"""

MOD_TYPE = "GAMES"
MOD_NAME = "Movie-Guess"
MOD_PRICE = "400"
