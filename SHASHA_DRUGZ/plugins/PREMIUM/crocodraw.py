# ================================================================
#   CROCODRAW GAME MODULE  —  SHASHA_DRUGZ  v2.0
#   File: SHASHA_DRUGZ/plugins/GAMES/crocodraw.py
#
#   FLOW
#   ────
#   1. /crocodraw → "🎨 Wanna be a DRAWER?" button appears
#   2. Anyone taps it → becomes drawer, round starts
#   3. Drawer controls (popup-only — word never shown in group):
#        🖼 Show Word  → private alert (drawer only)
#        🔀 New Word   → swap word in popup (drawer only)
#        💡 Give Hint  → reveals letters publicly (penalty for guesser)
#        ⏭ Skip Round → drawer / admin only
#        🛑 Stop Game  → starter / admin only
#   4. All group members type guesses freely — no /join needed
#   5. Correct guess → image card + full stats card sent to group
#   6. Drawer earns ARTIST coins every successful round
#   7. Auto-hints at 60s and 30s remaining
#   8. Inline hint countdown bar on round message
#
#   COMMANDS:
#     /crocodraw       → start game
#     /crocodrawend    → end game
#     /crocodrawtop    → leaderboard (Overall · Monthly · Weekly · This Chat · My Rank)
#     /crocodrawrank   → my rank & profile
#     /crocodrawrules  → game rules
#     /crocodrawhelp   → full help + title progression
#
#   TITLE TRACKS:
#     Guesser Track  — unlocked by total coins earned
#     Artist Track   — unlocked by total words drawn
#
#   SCORING:
#     Guesser  → 50 base + up to 40 speed bonus + streak bonus
#     Artist   → 35 coins + 15 XP per successful round
#     Hint penalty → -5 coins per hint from winner's reward
#
#   HANDLER GROUPS:
#     group=-1  → check_guess (runs before chatbot / reactionbot)
#     group=0   → /commands (default)
#
#   DATA RESETS ON RESTART: NO — all data persisted in MongoDB.
#   (Only in-memory game state resets on restart, not scores.)
# ================================================================

import asyncio
import os
import random
import re as _re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import get_collection

# ================================================================
# ASSETS
# ================================================================
_TEMPLATE  = "SHASHA_DRUGZ/assets/shasha/fastlywrite.png"
_FONT_PATH = "SHASHA_DRUGZ/assets/Sprintura Demo.otf"
_executor  = ThreadPoolExecutor(max_workers=4)

# ================================================================
# MONGODB COLLECTIONS
# ================================================================
score_col = get_collection("crocodraw_scores")
meta_col  = get_collection("crocodraw_meta")

# ================================================================
# TITLE SYSTEM — GUESSER TRACK  (by total coins)
# ================================================================
GUESSER_TITLES = [
    (0,      "🐣",  "ꜰʀᴇsʜ ɢᴜᴇssᴇʀ"),
    (100,    "🖌️",  "sᴋᴇᴛᴄʜ ɴᴇᴡʙɪᴇ"),
    (300,    "🔍",  "sʜᴀʀᴘ ᴇʏᴇ"),
    (600,    "🧠",  "ᴡᴏʀᴅ ʜᴜɴᴛᴇʀ"),
    (1000,   "⚡",  "ǫᴜɪᴄᴋ ɢᴜᴇssᴇʀ"),
    (2000,   "🎯",  "ʙᴜʟʟsᴇʏᴇ"),
    (3500,   "🔥",  "ʜᴏᴛ sᴛʀᴇᴀᴋ"),
    (5000,   "💎",  "ᴅɪᴀᴍᴏɴᴅ ᴇʏᴇ"),
    (8000,   "🦁",  "ᴀʀᴛ ʟɪᴏɴ"),
    (12000,  "👑",  "ᴅʀᴀᴡ ᴋɪɴɢ"),
    (18000,  "🌟",  "ʟᴇɢᴇɴᴅ"),
    (25000,  "💫",  "ᴍʏᴛʜɪᴄ"),
    (35000,  "🚀",  "ɢᴀʟᴀxʏ ʙʀᴀɪɴ"),
    (50000,  "🏆",  "ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ"),
]

# ================================================================
# TITLE SYSTEM — ARTIST TRACK  (by words_drawn)
# ================================================================
ARTIST_TITLES = [
    (0,    "✏️",  "sʜʏ sᴋᴇᴛᴄʜᴇʀ"),
    (5,    "🖊️",  "ᴄᴀsᴜᴀʟ ᴅᴏᴏᴅʟᴇʀ"),
    (15,   "🖌️",  "ᴄʀᴇᴀᴛɪᴠᴇ ᴘᴀɪɴᴛᴇʀ"),
    (30,   "🎭",  "sᴋɪʟʟᴇᴅ ɪʟʟᴜsᴛʀᴀᴛᴏʀ"),
    (50,   "🌊",  "ꜰʟᴜᴇɴᴛ ᴀʀᴛɪsᴛ"),
    (80,   "⚔️",  "sᴛʀᴀᴛᴇɢɪᴄ ᴅʀᴀᴡᴇʀ"),
    (120,  "🎓",  "ᴍᴀsᴛᴇʀ ᴀʀᴛɪsᴛ"),
    (180,  "🧙",  "ᴅʀᴀᴡ ᴡɪᴢᴀʀᴅ"),
    (260,  "🦅",  "ᴠɪsɪᴏɴ ᴇᴀɢʟᴇ"),
    (360,  "👑",  "ᴀʀᴛ ᴋɪɴɢ"),
    (500,  "🌟",  "ʟᴇɢᴇɴᴅᴀʀʏ ᴀʀᴛɪsᴛ"),
    (700,  "💫",  "ᴍʏᴛʜɪᴄ ᴘᴀɪɴᴛᴇʀ"),
    (1000, "🏆",  "ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ ᴀʀᴛɪsᴛ"),
]

# ─── title helpers ───────────────────────────────────────────
def get_guesser_title(coins: int) -> tuple[str, str]:
    result = GUESSER_TITLES[0][1], GUESSER_TITLES[0][2]
    for min_c, emoji, name in GUESSER_TITLES:
        if coins >= min_c:
            result = emoji, name
    return result

def get_artist_title(words_drawn: int) -> tuple[str, str]:
    result = ARTIST_TITLES[0][1], ARTIST_TITLES[0][2]
    for min_w, emoji, name in ARTIST_TITLES:
        if words_drawn >= min_w:
            result = emoji, name
    return result

def get_display_title(coins: int, words_drawn: int) -> str:
    """Return the higher-prestige title between the two tracks."""
    ge, gn = get_guesser_title(coins)
    ae, an = get_artist_title(words_drawn)
    g_tier = sum(1 for min_c, _, _ in GUESSER_TITLES if coins >= min_c) - 1
    a_tier = sum(1 for min_w, _, _ in ARTIST_TITLES if words_drawn >= min_w) - 1
    a_scaled = a_tier * len(GUESSER_TITLES) / max(len(ARTIST_TITLES), 1)
    if a_scaled >= g_tier:
        return f"{ae} {an}"
    return f"{ge} {gn}"

def _next_guesser_title(coins: int) -> str | None:
    for min_c, emoji, name in GUESSER_TITLES:
        if coins < min_c:
            return f"{emoji} {name} ᴀᴛ {min_c} ᴄᴏɪɴs"
    return None

def _next_artist_title(words_drawn: int) -> str | None:
    for min_w, emoji, name in ARTIST_TITLES:
        if words_drawn < min_w:
            return f"{emoji} {name} ᴀᴛ {min_w} ᴡᴏʀᴅs"
    return None

# ================================================================
# WORD LIST  (250 + words across 10 categories)
# ================================================================
WORDS = [
    # animals
    "tiger", "elephant", "penguin", "giraffe", "dolphin", "cheetah", "kangaroo",
    "gorilla", "crocodile", "flamingo", "octopus", "chameleon", "peacock",
    "porcupine", "hedgehog", "parrot", "chimpanzee", "rhinoceros", "hippopotamus",
    "meerkat", "wolverine", "platypus", "narwhal", "axolotl", "capybara",
    "jellyfish", "seahorse", "starfish", "pangolin", "ocelot", "tapir",
    "mantis shrimp", "mimic octopus", "blobfish", "quokka",
    # food & drinks
    "pizza", "burger", "sushi", "pancake", "chocolate", "strawberry", "pineapple",
    "avocado", "popcorn", "milkshake", "sandwich", "omelette", "barbecue",
    "dumpling", "burrito", "croissant", "lasagna", "cheesecake", "ramen", "taco",
    "waffle", "pretzel", "tiramisu", "macaron", "churros", "donut",
    "nachos", "spaghetti", "fondue", "paella", "tempura", "baklava",
    "cotton candy", "bubble tea", "hot dog", "ice cream",
    # technology
    "computer", "smartphone", "keyboard", "satellite", "microchip",
    "bluetooth", "headphones", "television", "calculator", "microscope",
    "telescope", "robot", "battery", "projector", "hoverboard", "drone",
    "smartwatch", "hologram", "supercomputer", "joystick", "webcam", "router",
    "3d printer", "virtual reality", "solar panel",
    # nature
    "volcano", "rainbow", "waterfall", "avalanche", "hurricane", "thunder",
    "glacier", "earthquake", "tornado", "tsunami", "desert", "jungle", "meadow",
    "canyon", "coral", "aurora", "stalactite", "whirlpool", "mangrove", "tundra",
    "geyser", "lagoon", "savanna", "archipelago", "quicksand",
    # sports & games
    "football", "basketball", "badminton", "gymnastics", "skateboard", "parachute",
    "swimming", "archery", "wrestling", "marathon", "karate", "volleyball",
    "cricket", "surfing", "bobsled", "fencing", "curling", "polo", "lacrosse",
    "snowboard", "triathlon", "javelin", "weightlifting", "parkour",
    # transport
    "airplane", "helicopter", "spaceship", "motorcycle", "bicycle", "ambulance",
    "hovercraft", "sailboat", "rickshaw", "monorail", "gondola", "bulldozer",
    "tractor", "zeppelin", "catamaran", "hydrofoil", "segway", "submarine",
    "cable car", "hot air balloon", "rickshaw",
    # everyday objects
    "umbrella", "backpack", "compass", "lantern", "blanket", "thermometer",
    "binoculars", "dictionary", "envelope", "scissors", "hourglass", "periscope",
    "boomerang", "hammock", "kaleidoscope", "abacus", "sundial",
    "piggy bank", "alarm clock", "fire extinguisher", "magnifying glass",
    # professions
    "doctor", "architect", "astronaut", "firefighter", "detective", "photographer",
    "chef", "scientist", "journalist", "librarian", "mechanic", "surgeon",
    "carpenter", "locksmith", "taxidermist", "sommelier", "cartographer",
    "acrobat", "ventriloquist", "archaeologist", "beekeeper",
    # places
    "hospital", "library", "museum", "stadium", "lighthouse", "cathedral",
    "marketplace", "laboratory", "observatory", "aquarium", "planetarium",
    "waterpark", "bookstore", "igloo", "skyscraper", "colosseum", "pagoda",
    "treehouse", "windmill", "underground cave",
    # actions / concepts
    "dancing", "painting", "singing", "dreaming", "laughing", "cooking",
    "writing", "reading", "climbing", "sleeping", "thinking", "building",
    "exploring", "juggling", "meditating", "skydiving", "hibernating",
    "moonwalking", "somersault", "tightrope walking", "time travel",
]

# ================================================================
# IN-MEMORY GAME STATE  (per chat, cleared on restart — by design)
# ================================================================
games: dict[int, dict] = {}

# ================================================================
# REWARDS CONFIG
# ================================================================
BASE_COINS       = 50
FAST_BONUS       = 25   # ≤ 10 s
ULTRA_BONUS      = 15   # ≤  5 s  (stacked with FAST_BONUS)
ARTIST_COINS     = 35
ARTIST_XP        = 15
GUESSER_XP       = 25
STREAK_THRESHOLD = 3
STREAK_BONUS     = 20
HINT_PENALTY     = 5    # deducted per hint from guesser reward
ROUND_TIME       = 90   # seconds per round

# ================================================================
# IMAGE GENERATOR  (only sent on correct guess)
# ================================================================
def _generate_word_image(word: str) -> str | None:
    try:
        img           = Image.open(_TEMPLATE).convert("RGBA")
        width, height = img.size
        draw          = ImageDraw.Draw(img)

        ta_start = int(width * 0.55)
        ta_width = width - ta_start - 50

        font_size = 550
        font = None
        while font_size > 80:
            try:
                font = ImageFont.truetype(_FONT_PATH, font_size)
            except Exception:
                font = ImageFont.load_default()
                break
            bbox = draw.textbbox((0, 0), word.upper(), font=font)
            if (bbox[2] - bbox[0]) < ta_width:
                break
            font_size -= 30
        if font is None:
            font = ImageFont.load_default()

        display = word.upper()
        bbox    = draw.textbbox((0, 0), display, font=font)
        tw, th  = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = ta_start + (ta_width - tw) // 2
        y = (height - th) // 2

        first = display[0]
        rest  = display[1:]
        bf    = draw.textbbox((0, 0), first, font=font)
        fw    = bf[2] - bf[0]
        draw.text((x,      y), first, font=font, fill=(255, 180, 0),   stroke_width=8, stroke_fill=(0, 0, 0))
        draw.text((x + fw, y), rest,  font=font, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))

        footer = "🎨 ᴄᴏᴄᴏᴅʀᴀᴡ  |  @HeartBeat_Offi"
        try:
            ff = ImageFont.truetype(_FONT_PATH, 20)
        except Exception:
            ff = ImageFont.load_default()
        bff = draw.textbbox((0, 0), footer, font=ff)
        fx  = ta_start + (ta_width - (bff[2] - bff[0])) // 2
        fy  = y + th + 40
        draw.text((fx, fy), footer, font=ff, fill=(220, 220, 220))

        path = f"/tmp/crocodraw_{random.randint(10000, 99999)}.png"
        img.save(path)
        return path
    except Exception as e:
        print(f"[crocodraw] image gen error: {e}")
        return None

async def _make_image(word: str) -> str | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _generate_word_image, word)

# ================================================================
# DATABASE HELPERS
# ================================================================
def _period_keys() -> dict:
    n = datetime.utcnow()
    return {
        "today":   n.strftime("%Y-%m-%d"),
        "weekly":  f"{n.year}-W{n.isocalendar()[1]:02d}",
        "monthly": n.strftime("%Y-%m"),
    }

async def _add_score(
    chat_id: int, user, role: str,
    coins: int, xp: int, elapsed: float, word: str,
) -> dict:
    """Upsert a player's score document and return the updated copy."""
    wpm = round((len(word) / 5) / (elapsed / 60), 2) if elapsed > 0 else 0.0
    now = datetime.utcnow()
    doc = await score_col.find_one({"chat_id": chat_id, "user_id": user.id})
    if not doc:
        new_doc = {
            "chat_id":       chat_id,
            "user_id":       user.id,
            "name":          user.first_name,
            "coins":         coins,
            "xp":            xp,
            "today":         coins,
            "weekly":        coins,
            "monthly":       coins,
            "words_guessed": 1 if role == "guesser" else 0,
            "words_drawn":   1 if role == "artist"  else 0,
            "best_speed":    wpm if role == "guesser" else 0.0,
            "streak":        0,
            "updated":       now,
        }
        await score_col.insert_one(new_doc)
        return new_doc
    else:
        upd: dict = {
            "$inc": {
                "coins": coins, "xp": xp,
                "today": coins, "weekly": coins, "monthly": coins,
            },
            "$set": {"name": user.first_name, "updated": now},
        }
        if role == "guesser":
            upd["$inc"]["words_guessed"] = 1
            if wpm > doc.get("best_speed", 0):
                upd["$set"]["best_speed"] = wpm
        else:
            upd["$inc"]["words_drawn"] = 1
        await score_col.update_one({"_id": doc["_id"]}, upd)
        # Merge for return value
        updated = dict(doc)
        for k, v in upd["$inc"].items():
            updated[k] = updated.get(k, 0) + v
        updated.update(upd.get("$set", {}))
        return updated

async def _get_chat_rank(chat_id: int, user_id: int) -> int:
    doc = await score_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        return 0
    return await score_col.count_documents(
        {"chat_id": chat_id, "coins": {"$gt": doc.get("coins", 0)}}
    ) + 1

async def _get_global_rank(user_id: int) -> int:
    """Rank across ALL chats by aggregated total coins."""
    pipeline = [
        {"$group": {"_id": "$user_id", "total": {"$sum": "$coins"}}},
        {"$sort": {"total": -1}},
    ]
    pos = 1
    async for doc in score_col.aggregate(pipeline):
        if doc["_id"] == user_id:
            return pos
        pos += 1
    return 0

async def _get_top_chat(chat_id: int, field: str, limit: int = 10) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines, i = [], 0
    async for u in score_col.find({"chat_id": chat_id}).sort(field, -1).limit(limit):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        val   = u.get(field, 0)
        spd   = u.get("best_speed", 0.0)
        title = get_display_title(u.get("coins", 0), u.get("words_drawn", 0))
        lines.append(
            f"{medal} **{u['name']}**  {title}\n"
            f"    💰 {val} ᴄᴏɪɴs  ⚡ {spd:.1f} ᴡᴘᴍ"
        )
        i += 1
    return "\n".join(lines) if lines else "ɴᴏ ᴘʟᴀʏᴇʀs ʏᴇᴛ."

async def _get_top_global(limit: int = 10) -> str:
    medals = ["🥇", "🥈", "🥉"]
    pipeline = [
        {"$group": {
            "_id":          "$user_id",
            "name":         {"$last": "$name"},
            "coins":        {"$sum": "$coins"},
            "words_drawn":  {"$sum": "$words_drawn"},
            "best_speed":   {"$max": "$best_speed"},
        }},
        {"$sort": {"coins": -1}},
        {"$limit": limit},
    ]
    lines, i = [], 0
    async for u in score_col.aggregate(pipeline):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        title = get_display_title(u.get("coins", 0), u.get("words_drawn", 0))
        lines.append(
            f"{medal} **{u['name']}**  {title}\n"
            f"    💰 {u['coins']} ᴄᴏɪɴs  ⚡ {u.get('best_speed', 0):.1f} ᴡᴘᴍ"
        )
        i += 1
    return "\n".join(lines) if lines else "ɴᴏ ᴘʟᴀʏᴇʀs ʏᴇᴛ."

# ─── periodic score reset (daily / weekly / monthly) ─────────
async def _reset_loop():
    while True:
        try:
            pk    = _period_keys()
            rmeta = await meta_col.find_one({"_id": "reset_meta"}) or {}
            if rmeta.get("day") != pk["today"]:
                await score_col.update_many({}, {"$set": {"today": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"day": pk["today"]}}, upsert=True)
            if rmeta.get("week") != pk["weekly"]:
                await score_col.update_many({}, {"$set": {"weekly": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"week": pk["weekly"]}}, upsert=True)
            if rmeta.get("month") != pk["monthly"]:
                await score_col.update_many({}, {"$set": {"monthly": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"month": pk["monthly"]}}, upsert=True)
        except Exception as e:
            print(f"[crocodraw] reset_loop error: {e}")
        await asyncio.sleep(3600)

try:
    asyncio.get_event_loop().create_task(_reset_loop())
except Exception:
    pass

# ================================================================
# HINT SYSTEM
# ================================================================
def _build_hint(word: str, reveal_count: int) -> str:
    """Return a masked version of the word with `reveal_count` letters shown."""
    chars = list(word)
    forced = {i for i, c in enumerate(chars) if c == " "}
    pool   = [i for i in range(len(chars)) if i not in forced]
    random.shuffle(pool)
    revealed = forced | set(pool[:reveal_count])
    parts = []
    for i, c in enumerate(chars):
        parts.append(c.upper() if i in revealed else "＿")
    return " ".join(parts)

def _word_blank(word: str) -> str:
    """Show only blanks + spaces, no letters."""
    return " ".join("＿" if c != " " else "  " for c in word)

# ================================================================
# INLINE KEYBOARDS
# ================================================================
def _kb_become_drawer(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎨 Wanna be a DRAWER?", callback_data=f"croco_draw_{chat_id}"),
    ]])

def _kb_drawer_controls(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖼 Show Word",  callback_data=f"croco_show_{chat_id}"),
            InlineKeyboardButton("🔀 New Word",   callback_data=f"croco_new_{chat_id}"),
        ],
        [
            InlineKeyboardButton("💡 Give Hint",  callback_data=f"croco_hint_{chat_id}"),
            InlineKeyboardButton("⏭ Skip Round",  callback_data=f"croco_skip_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🛑 Stop Game",  callback_data=f"croco_stop_{chat_id}"),
        ],
    ])

def _kb_top(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 Overall",   callback_data=f"croco_lb_overall_{chat_id}"),
            InlineKeyboardButton("📅 Weekly",    callback_data=f"croco_lb_weekly_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🗓 Monthly",   callback_data=f"croco_lb_monthly_{chat_id}"),
            InlineKeyboardButton("💬 This Chat", callback_data=f"croco_lb_chat_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🏅 My Rank",   callback_data=f"croco_myrank_{chat_id}"),
        ],
    ])

def _kb_rank(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Full Stats",   callback_data=f"croco_fullstats_{chat_id}"),
            InlineKeyboardButton("🎨 Artist Board", callback_data=f"croco_lb_artist_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🌍 Global Rank",  callback_data=f"croco_lb_overall_{chat_id}"),
            InlineKeyboardButton("🏆 Leaderboard",  callback_data=f"croco_lb_chat_{chat_id}"),
        ],
    ])

def _kb_back_to_top(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data=f"croco_lb_chat_{chat_id}"),
    ]])

# ================================================================
# ADMIN CHECK
# ================================================================
async def _is_admin(chat_id: int, user_id: int) -> bool:
    try:
        m = await app.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

# ================================================================
# ROUND ENGINE
# ================================================================
def _pick_word() -> str:
    return random.choice(WORDS)

async def _round_timer(chat_id: int, word: str, round_num: int):
    """90s timer that sends progressive hints at 60s and 30s marks."""
    # ── 30s elapsed → 60s remaining ──────────────────────────
    await asyncio.sleep(30)
    game = games.get(chat_id)
    if not game or game.get("word") != word or game.get("round") != round_num:
        return
    hint1 = _build_hint(word, max(1, len(word) // 4))
    try:
        await app.send_message(
            chat_id,
            f"<blockquote>⏳ **60 sᴇᴄᴏɴᴅs ʟᴇꜰᴛ!**\n"
            f"💡 **ʜɪɴᴛ:** `{hint1}`\n"
            f"_({len(word.replace(' ',''))} ʟᴇᴛᴛᴇʀs)_</blockquote>",
        )
    except Exception:
        pass

    # ── 60s elapsed → 30s remaining ──────────────────────────
    await asyncio.sleep(30)
    game = games.get(chat_id)
    if not game or game.get("word") != word or game.get("round") != round_num:
        return
    hint2 = _build_hint(word, max(2, len(word) // 2))
    try:
        await app.send_message(
            chat_id,
            f"<blockquote>🔥 **30 sᴇᴄᴏɴᴅs ʟᴇꜰᴛ!**\n"
            f"💡 **ʜɪɴᴛ:** `{hint2}`\n"
            f"_({len(word.replace(' ',''))} ʟᴇᴛᴛᴇʀs)_</blockquote>",
        )
    except Exception:
        pass

    # ── 90s elapsed → time up ────────────────────────────────
    await asyncio.sleep(30)
    game = games.get(chat_id)
    if not game:
        return
    if game.get("word") == word and game.get("round") == round_num:
        game["word"] = None
        try:
            await app.send_message(
                chat_id,
                f"<blockquote>⏭ **ᴛɪᴍᴇ ᴜᴘ!**\n"
                f"🎨 ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs  **{word.upper()}**\n\n"
                f"ɴᴇxᴛ ʀᴏᴜɴᴅ — ᴡʜᴏ ᴡᴀɴᴛs ᴛᴏ ᴅʀᴀᴡ?</blockquote>",
                reply_markup=_kb_become_drawer(chat_id),
            )
        except Exception as e:
            print(f"[crocodraw] timer expire error: {e}")

async def _start_round(chat_id: int, drawer_uid: int, drawer_mention: str):
    game = games.get(chat_id)
    if not game:
        return
    if game.get("task") and not game["task"].done():
        game["task"].cancel()

    word               = _pick_word()
    game["word"]       = word
    game["drawer"]     = drawer_uid
    game["start_time"] = time.time()
    game["round"]      = game.get("round", 0) + 1
    game["hint_count"] = 0
    blank              = _word_blank(word)

    try:
        msg = await app.send_message(
            chat_id,
            f"<blockquote>🎨 **ʀᴏᴜɴᴅ {game['round']} — ᴅʀᴀᴡ ɪᴛ!**</blockquote>\n"
            f"<blockquote>"
            f"✏️ **ᴅʀᴀᴡᴇʀ:** {drawer_mention}\n"
            f"⏱ **{ROUND_TIME}s** ᴛᴏ ɢᴜᴇss!\n\n"
            f"🖼 ᴅʀᴀᴡᴇʀ: ᴛᴀᴘ **Show Word** ᴛᴏ sᴇᴇ ʏᴏᴜʀ sᴇᴄʀᴇᴛ ᴡᴏʀᴅ (ᴘʀɪᴠᴀᴛᴇ).\n"
            f"📸 sᴇɴᴅ sᴛɪᴄᴋᴇʀs / ᴘʜᴏᴛᴏs / ᴇᴍᴏᴊɪs — ɴᴏ sᴘᴇʟʟɪɴɢ!\n"
            f"✍️ ᴇᴠᴇʀʏᴏɴᴇ ᴇʟsᴇ: ᴛʏᴘᴇ ʏᴏᴜʀ ɢᴜᴇss!\n\n"
            f"📝 **ᴡᴏʀᴅ:** `{blank}`  _({len(word)} ʟᴇᴛᴛᴇʀs)_</blockquote>",
            reply_markup=_kb_drawer_controls(chat_id),
        )
        game["round_msg_id"] = msg.id
    except Exception as e:
        print(f"[crocodraw] start_round msg error: {e}")

    game["task"] = asyncio.create_task(_round_timer(chat_id, word, game["round"]))

# ================================================================
# COMMANDS
# ================================================================

@app.on_message(filters.command("crocodraw") & filters.group)
async def cmd_crocodraw(_, m: Message):
    chat_id = m.chat.id
    if chat_id in games:
        return await m.reply(
            "<blockquote>⚠️ **ɢᴀᴍᴇ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!**\n"
            "ᴜsᴇ /crocodrawend ᴛᴏ ᴇɴᴅ ɪᴛ ꜰɪʀsᴛ.</blockquote>"
        )
    games[chat_id] = {
        "drawer":       None,
        "word":         None,
        "start_time":   time.time(),
        "round":        0,
        "task":         None,
        "round_msg_id": None,
        "streak":       {},
        "started_by":   m.from_user.id,
        "hint_count":   0,
        "total_rounds": 0,
    }
    await meta_col.update_one(
        {"_id": "chats"}, {"$addToSet": {"ids": chat_id}}, upsert=True
    )
    await m.reply(
        f"<blockquote>🎨 **ᴄᴏᴄᴏᴅʀᴀᴡ sᴛᴀʀᴛᴇᴅ!**</blockquote>\n"
        f"<blockquote>"
        f"👤 **sᴛᴀʀᴛᴇᴅ ʙʏ:** {m.from_user.mention}\n\n"
        f"📋 **ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:**\n"
        f"1️⃣ sᴏᴍᴇᴏɴᴇ ᴛᴀᴘs **🎨 Wanna be a DRAWER?**\n"
        f"2️⃣ ᴅʀᴀᴡᴇʀ ᴛᴀᴘs **🖼 Show Word** ᴛᴏ sᴇᴇ sᴇᴄʀᴇᴛ ᴡᴏʀᴅ\n"
        f"3️⃣ ᴅʀᴀᴡᴇʀ sᴇɴᴅs sᴛɪᴄᴋᴇʀs / ᴘʜᴏᴛᴏs ᴀs ᴠɪsᴜᴀʟ ʜɪɴᴛs\n"
        f"4️⃣ ᴇᴠᴇʀʏᴏɴᴇ ᴛʏᴘᴇs ᴛʜᴇɪʀ ɢᴜᴇss — ɴᴏ /join ɴᴇᴇᴅᴇᴅ!\n"
        f"5️⃣ ꜰɪʀsᴛ ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇss ᴡɪɴs ᴄᴏɪɴs + xᴘ + ᴛɪᴛʟᴇ!\n\n"
        f"🏆 /crocodrawtop · 🎖 /crocodrawrank · 📜 /crocodrawrules\n\n"
        f"👇 ᴛᴀᴘ ʙᴇʟᴏᴡ ᴛᴏ ʙᴇᴄᴏᴍᴇ ᴛʜᴇ ꜰɪʀsᴛ ᴅʀᴀᴡᴇʀ:</blockquote>",
        reply_markup=_kb_become_drawer(chat_id),
    )


@app.on_message(filters.command("crocodrawend") & filters.group)
async def cmd_crocodrawend(_, m: Message):
    chat_id = m.chat.id
    if chat_id not in games:
        return await m.reply("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.")
    uid  = m.from_user.id
    game = games[chat_id]
    if uid != game.get("started_by") and not await _is_admin(chat_id, uid):
        return await m.reply("❌ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ sᴛᴀʀᴛᴇʀ ᴏʀ ᴀɴ ᴀᴅᴍɪɴ ᴄᴀɴ sᴛᴏᴘ.")
    word = game.get("word") or "?"
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    games.pop(chat_id, None)
    await m.reply(
        f"<blockquote>🛑 **ɢᴀᴍᴇ sᴛᴏᴘᴘᴇᴅ!**\n"
        f"🎨 ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: **{word.upper()}**\n\n"
        f"ᴜsᴇ /crocodraw ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ.</blockquote>"
    )


@app.on_message(filters.command("crocodrawtop") & filters.group)
async def cmd_crocodrawtop(_, m: Message):
    chat_id = m.chat.id
    top     = await _get_top_chat(chat_id, "coins")
    await m.reply(
        f"<blockquote>🏆 **ᴄᴏᴄᴏᴅʀᴀᴡ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ** — ᴛʜɪs ɢʀᴏᴜᴘ</blockquote>\n"
        f"<blockquote>{top}</blockquote>",
        reply_markup=_kb_top(chat_id),
    )


@app.on_message(filters.command("crocodrawrank") & filters.group)
async def cmd_crocodrawrank(_, m: Message):
    chat_id = m.chat.id
    uid     = m.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await m.reply(
            "<blockquote>📊 ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!\n"
            "ᴜsᴇ /crocodraw ᴛᴏ sᴛᴀʀᴛ ᴀ ɢᴀᴍᴇ.</blockquote>"
        )
    coins       = data.get("coins", 0)
    xp          = data.get("xp", 0)
    words_drawn = data.get("words_drawn", 0)
    words_g     = data.get("words_guessed", 0)
    speed       = data.get("best_speed", 0.0)
    c_rank      = await _get_chat_rank(chat_id, uid)
    g_rank      = await _get_global_rank(uid)
    display     = get_display_title(coins, words_drawn)
    ge, gn      = get_guesser_title(coins)
    ae, an      = get_artist_title(words_drawn)
    next_g      = _next_guesser_title(coins)
    next_a      = _next_artist_title(words_drawn)
    next_block  = ""
    if next_g:
        next_block += f"\n🎯 ɴᴇxᴛ ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇ: {next_g}"
    if next_a:
        next_block += f"\n🎨 ɴᴇxᴛ ᴀʀᴛɪsᴛ ᴛɪᴛʟᴇ: {next_a}"

    await m.reply(
        f"<blockquote>🎨 **ᴍʏ ᴘʀᴏꜰɪʟᴇ** — {m.from_user.mention}</blockquote>\n"
        f"<blockquote>"
        f"{'━'*22}\n"
        f"🏅 **ᴄʜᴀᴛ ʀᴀɴᴋ:**      #{c_rank}\n"
        f"🌍 **ɢʟᴏʙᴀʟ ʀᴀɴᴋ:**    #{g_rank}\n"
        f"🎖 **ᴛɪᴛʟᴇ:**            {display}\n"
        f"{'━'*22}\n"
        f"💰 **ᴛᴏᴛᴀʟ ᴄᴏɪɴs:**     {coins}\n"
        f"⭐ **ᴛᴏᴛᴀʟ xᴘ:**        {xp}\n"
        f"📅 **ᴛᴏᴅᴀʏ:**            {data.get('today', 0)}\n"
        f"📆 **ᴡᴇᴇᴋʟʏ:**           {data.get('weekly', 0)}\n"
        f"🗓 **ᴍᴏɴᴛʜʟʏ:**          {data.get('monthly', 0)}\n"
        f"{'━'*22}\n"
        f"✅ **ᴡᴏʀᴅs ɢᴜᴇssᴇᴅ:**    {words_g}\n"
        f"🎨 **ᴡᴏʀᴅs ᴅʀᴀᴡɴ:**     {words_drawn}\n"
        f"⚡ **ʙᴇsᴛ sᴘᴇᴇᴅ:**       {speed:.2f} ᴡᴘᴍ\n"
        f"{'━'*22}\n"
        f"{ge} **ɢᴜᴇssᴇʀ:** {gn}\n"
        f"{ae} **ᴀʀᴛɪsᴛ:**  {an}"
        f"{next_block}</blockquote>",
        reply_markup=_kb_rank(chat_id),
    )


# ─── Rules constant (defined before use in /crocodrawrules) ────
_RULES_TEXT = (
    "<blockquote>🎨 **ᴄᴏᴄᴏᴅʀᴀᴡ — ɢᴀᴍᴇ ʀᴜʟᴇs**</blockquote>\n"
    "<blockquote>"
    "1️⃣  sᴏᴍᴇᴏɴᴇ ᴠᴏʟᴜɴᴛᴇᴇʀs ᴀs **ᴅʀᴀᴡᴇʀ** ʙʏ ᴛᴀᴘᴘɪɴɢ ᴛʜᴇ ʙᴜᴛᴛᴏɴ.\n"
    "2️⃣  ᴅʀᴀᴡᴇʀ ᴛᴀᴘs **🖼 Show Word** ᴛᴏ sᴇᴇ ᴛʜᴇ sᴇᴄʀᴇᴛ ᴡᴏʀᴅ (ᴘʀɪᴠᴀᴛᴇ ᴀʟᴇʀᴛ).\n"
    "3️⃣  ᴅʀᴀᴡᴇʀ sᴇɴᴅs sᴛɪᴄᴋᴇʀs / ᴘʜᴏᴛᴏs / ᴇᴍᴏᴊɪs ᴀs ᴠɪsᴜᴀʟ ʜɪɴᴛs.\n"
    "4️⃣  **❌ ᴄᴀɴɴᴏᴛ** ᴛʏᴘᴇ ᴏʀ sᴘᴇʟʟ ᴛʜᴇ ᴡᴏʀᴅ ᴀɴʏᴡʜᴇʀᴇ.\n"
    "5️⃣  ᴇᴠᴇʀʏᴏɴᴇ ᴇʟsᴇ ᴛʏᴘᴇs ᴛʜᴇɪʀ ɢᴜᴇss — ɴᴏ /join ɴᴇᴇᴅᴇᴅ.\n"
    "6️⃣  **ꜰɪʀsᴛ ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇss** → ᴡɪɴs ᴄᴏɪɴs + xᴘ + ᴡᴏʀᴅ ɪᴍᴀɢᴇ ᴄᴀʀᴅ.\n"
    "7️⃣  **ᴅʀᴀᴡᴇʀ** ᴇᴀʀɴs ʙᴏɴᴜs ᴄᴏɪɴs ᴀᴛ ᴇᴀᴄʜ sᴜᴄᴄᴇssꜰᴜʟ ʀᴏᴜɴᴅ.\n"
    "8️⃣  90 sᴇᴄᴏɴᴅs ᴘᴇʀ ʀᴏᴜɴᴅ — ᴀᴜᴛᴏ ʜɪɴᴛs ᴀᴛ 60s & 30s.\n"
    "9️⃣  **💡 ʜɪɴᴛ ʙᴜᴛᴛᴏɴ** ʀᴇᴠᴇᴀʟs ʟᴇᴛᴛᴇʀs (ᴅᴇᴅᴜᴄᴛs -5 ᴄᴏɪɴs ꜰʀᴏᴍ ᴡɪɴɴᴇʀ).\n"
    "🔟  **🔥 sᴛʀᴇᴀᴋ ʙᴏɴᴜs** ᴇᴠᴇʀʏ 3 ᴄᴏʀʀᴇᴄᴛ ɢᴜᴇssᴇs ɪɴ ᴀ ʀᴏᴡ!\n\n"
    f"💰 ɢᴜᴇssᴇʀ: **{BASE_COINS}** ᴄᴏɪɴs  |  ⚡ ꜰᴀsᴛ (≤10s): +**{FAST_BONUS}**  |  ᴜʟᴛʀᴀ (≤5s): +**{FAST_BONUS+ULTRA_BONUS}**\n"
    f"🎨 ᴅʀᴀᴡᴇʀ: +**{ARTIST_COINS}** ᴄᴏɪɴs  |  🔥 sᴛʀᴇᴀᴋ: +**{STREAK_BONUS}**  |  💡 ʜɪɴᴛ ᴘᴇɴᴀʟᴛʏ: -**{HINT_PENALTY}**/ʜɪɴᴛ\n\n"
    "🏅 **ᴛɪᴛʟᴇ sʏsᴛᴇᴍ:**\n"
    "  ᴇᴀʀɴ ᴄᴏɪɴs   → ᴜɴʟᴏᴄᴋ ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇs\n"
    "  ᴅʀᴀᴡ ᴡᴏʀᴅs  → ᴜɴʟᴏᴄᴋ ᴀʀᴛɪsᴛ ᴛɪᴛʟᴇs\n"
    "  🏆 ɢʀᴀɴᴅ ᴍᴀsᴛᴇʀ ɪs ᴛʜᴇ ᴜʟᴛɪᴍᴀᴛᴇ ᴛɪᴛʟᴇ!</blockquote>"
)


@app.on_message(filters.command(["crocodrawrules", "crocodrawrule"]) & filters.group)
async def cmd_rules(_, m: Message):
    await m.reply(_RULES_TEXT)


@app.on_message(filters.command("crocodrawhelp") & filters.group)
async def cmd_help(_, m: Message):
    g_lines = "\n".join(
        f"  {e} **{n}** — {c} ᴄᴏɪɴs"
        for c, e, n in GUESSER_TITLES
    )
    a_lines = "\n".join(
        f"  {e} **{n}** — {w} ᴡᴏʀᴅs"
        for w, e, n in ARTIST_TITLES
    )
    await m.reply(
        "<blockquote>🎨 **ᴄᴏᴄᴏᴅʀᴀᴡ — ʜᴇʟᴘ**</blockquote>\n"
        "<blockquote>"
        "▶️ **/crocodraw** — sᴛᴀʀᴛ ɢᴀᴍᴇ\n"
        "🛑 **/crocodrawend** — sᴛᴏᴘ ɢᴀᴍᴇ\n"
        "🏆 **/crocodrawtop** — ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ\n"
        "🎖 **/crocodrawrank** — ᴍʏ ʀᴀɴᴋ & ᴘʀᴏꜰɪʟᴇ\n"
        "📜 **/crocodrawrules** — ɢᴀᴍᴇ ʀᴜʟᴇs\n"
        "❓ **/crocodrawhelp** — ᴛʜɪs ᴍᴇɴᴜ</blockquote>\n\n"
        f"<blockquote>✅ **ɢᴜᴇssᴇʀ ᴛɪᴛʟᴇs** (ʙʏ ᴄᴏɪɴs)\n{g_lines}</blockquote>\n\n"
        f"<blockquote>🎨 **ᴀʀᴛɪsᴛ ᴛɪᴛʟᴇs** (ʙʏ ᴡᴏʀᴅs ᴅʀᴀᴡɴ)\n{a_lines}</blockquote>"
    )

# ================================================================
# GUESS HANDLER  —  group=-1  (before chatbot / reactionbot)
# ================================================================
@app.on_message(
    filters.incoming
    & filters.text
    & filters.group
    & ~filters.command([
        "crocodraw", "crocodrawend", "crocodrawtop",
        "crocodrawrank", "crocodrawrules", "crocodrawrule", "crocodrawhelp",
    ])
    & ~filters.via_bot,
    group=-1,
)
async def check_guess(_, m: Message):
    chat_id = m.chat.id
    if chat_id not in games:
        m.continue_propagation()
        return
    game = games[chat_id]
    word = game.get("word")
    if not word:
        m.continue_propagation()
        return
    # Drawer cannot guess their own word
    if m.from_user and m.from_user.id == game.get("drawer"):
        m.continue_propagation()
        return

    typed = (m.text or "").strip().lower()
    if typed != word.lower():
        m.continue_propagation()
        return

    # ── CORRECT GUESS ──────────────────────────────────────────
    elapsed = time.time() - game["start_time"]
    uid     = m.from_user.id

    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    game["word"]         = None
    game["total_rounds"] = game.get("total_rounds", 0) + 1

    # ── Coin + XP calculation ──────────────────────────────────
    coins       = BASE_COINS
    xp          = GUESSER_XP
    bonus_lines = []

    if elapsed <= 5:
        bonus = FAST_BONUS + ULTRA_BONUS
        coins += bonus
        bonus_lines.append(f"⚡ ᴜʟᴛʀᴀ ꜰᴀsᴛ (≤5s): +**{bonus}** ᴄᴏɪɴs")
    elif elapsed <= 10:
        coins += FAST_BONUS
        bonus_lines.append(f"⚡ ꜰᴀsᴛ ʙᴏɴᴜs (≤10s): +**{FAST_BONUS}** ᴄᴏɪɴs")

    # Hint penalty
    hint_count = game.get("hint_count", 0)
    if hint_count > 0:
        penalty = min(hint_count * HINT_PENALTY, 20)
        coins   = max(10, coins - penalty)
        bonus_lines.append(f"💡 ʜɪɴᴛ ᴘᴇɴᴀʟᴛʏ ×{hint_count}: -**{penalty}** ᴄᴏɪɴs")

    # Streak
    streak = game["streak"]
    streak[uid] = streak.get(uid, 0) + 1
    if streak[uid] % STREAK_THRESHOLD == 0:
        coins += STREAK_BONUS
        bonus_lines.append(f"🔥 sᴛʀᴇᴀᴋ ×**{streak[uid]}**: +**{STREAK_BONUS}** ᴄᴏɪɴs")

    wpm        = round((len(word) / 5) / (elapsed / 60), 2) if elapsed > 0 else 0.0
    mins, secs = divmod(int(elapsed), 60)

    updated_doc    = await _add_score(chat_id, m.from_user, "guesser", coins, xp, elapsed, word)
    c_rank         = await _get_chat_rank(chat_id, uid)
    new_coins      = updated_doc.get("coins", coins)
    new_words_d    = updated_doc.get("words_drawn", 0)
    display_title  = get_display_title(new_coins, new_words_d)
    ge, gn         = get_guesser_title(new_coins)
    old_ge, _      = get_guesser_title(new_coins - coins)
    title_upgraded = old_ge != ge

    # ── Reward drawer ──────────────────────────────────────────
    drawer_uid     = game.get("drawer")
    drawer_mention = ""
    drawer_title   = ""
    if drawer_uid and drawer_uid != uid:
        try:
            drawer_user    = await app.get_users(drawer_uid)
            drawer_mention = drawer_user.mention
            d_doc          = await _add_score(
                chat_id, drawer_user, "artist",
                ARTIST_COINS, ARTIST_XP, elapsed, word,
            )
            drawer_title   = get_display_title(
                d_doc.get("coins", ARTIST_COINS),
                d_doc.get("words_drawn", 1),
            )
        except Exception as e:
            print(f"[crocodraw] drawer reward error: {e}")

    bonus_block  = ("\n" + "\n".join(bonus_lines)) if bonus_lines else ""
    drawer_line  = (
        f"\n\n🎨 **ᴅʀᴀᴡᴇʀ:** {drawer_mention}  {drawer_title}\n"
        f"   +**{ARTIST_COINS}** ᴄᴏɪɴs  ⭐ +**{ARTIST_XP}** xᴘ"
        if drawer_mention else ""
    )
    title_line = (
        f"\n🎖 **ᴛɪᴛʟᴇ ᴜᴘɢʀᴀᴅᴇ!**  {ge} {gn} 🎉"
        if title_upgraded else f"\n🎖 {display_title}"
    )

    caption = (
        f"<blockquote>🎉 **ᴄᴏʀʀᴇᴄᴛ!**  {m.from_user.mention}</blockquote>\n"
        f"<blockquote>"
        f"🎨 **ᴡᴏʀᴅ:**   {word.upper()}\n"
        f"⏱ **ᴛɪᴍᴇ:**   {mins}ᴍ {secs}s\n"
        f"⚡ **sᴘᴇᴇᴅ:** {wpm:.2f} ᴡᴘᴍ\n"
        f"🏅 **ʀᴀɴᴋ:**   #{c_rank}\n"
        f"💰 +**{coins}** ᴄᴏɪɴs  ⭐ +**{xp}** xᴘ"
        f"{bonus_block}"
        f"{title_line}"
        f"{drawer_line}</blockquote>"
    )

    img_path = await _make_image(word)
    try:
        if img_path and os.path.exists(img_path):
            await m.reply_photo(img_path, caption=caption)
        else:
            await m.reply(caption)
    except Exception as e:
        print(f"[crocodraw] win photo error: {e}")
        try:
            await m.reply(caption)
        except Exception:
            pass
    finally:
        if img_path:
            try:
                os.remove(img_path)
            except Exception:
                pass

    await asyncio.sleep(4)
    if chat_id in games:
        try:
            await app.send_message(
                chat_id,
                f"<blockquote>🎨 ʀᴏᴜɴᴅ **{game['round']}** ᴅᴏɴᴇ!\n"
                f"ᴡʜᴏ ᴡᴀɴᴛs ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ᴅʀᴀᴡᴇʀ?</blockquote>",
                reply_markup=_kb_become_drawer(chat_id),
            )
        except Exception as e:
            print(f"[crocodraw] next-drawer btn error: {e}")

# ================================================================
# CALLBACK QUERIES
# ================================================================

# ── Become Drawer ─────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_draw_(-?\d+)$"))
async def cb_be_drawer(_, q):
    chat_id = int(q.data.split("_")[2])
    if chat_id not in games:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    game = games[chat_id]
    if game.get("word"):
        return await q.answer("⚠️ ᴀ ʀᴏᴜɴᴅ ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇss!", show_alert=True)
    uid    = q.from_user.id
    data   = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    ae, _  = get_artist_title(data.get("words_drawn", 0) if data else 0)
    await q.answer(f"✅ ʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴛʜᴇ ᴅʀᴀᴡᴇʀ! {ae}", show_alert=False)
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _start_round(chat_id, uid, q.from_user.mention)


# ── Show Word ─────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_show_(-?\d+)$"))
async def cb_show_word(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game or not game.get("word"):
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴏᴜɴᴅ.", show_alert=True)
    if q.from_user.id != game.get("drawer"):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴅʀᴀᴡᴇʀ ᴄᴀɴ sᴇᴇ ᴛʜᴇ ᴡᴏʀᴅ.", show_alert=True)
    word = game["word"]
    await q.answer(
        f"🎨 ʏᴏᴜʀ ᴡᴏʀᴅ ᴛᴏ ᴅʀᴀᴡ:\n\n  {word.upper()}\n\n"
        f"❌ ᴅᴏɴ'ᴛ ᴛʏᴘᴇ ᴏʀ sᴘᴇʟʟ ɪᴛ!\n"
        f"✅ sᴇɴᴅ sᴛɪᴄᴋᴇʀs / ᴘʜᴏᴛᴏs / ᴇᴍᴏᴊɪs.",
        show_alert=True,
    )


# ── New Word ──────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_new_(-?\d+)$"))
async def cb_new_word(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game or not game.get("word"):
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴏᴜɴᴅ.", show_alert=True)
    if q.from_user.id != game.get("drawer"):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴅʀᴀᴡᴇʀ ᴄᴀɴ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴡᴏʀᴅ.", show_alert=True)
    new_word           = _pick_word()
    game["word"]       = new_word
    game["start_time"] = time.time()
    game["hint_count"] = 0
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    game["task"] = asyncio.create_task(_round_timer(chat_id, new_word, game["round"]))
    await q.answer(
        f"🔀 ɴᴇᴡ ᴡᴏʀᴅ ᴛᴏ ᴅʀᴀᴡ:\n\n  {new_word.upper()}\n\n"
        f"❌ ᴅᴏɴ'ᴛ sᴘᴇʟʟ ɪᴛ!\n"
        f"✅ ᴅʀᴀᴡ ᴡɪᴛʜ sᴛɪᴄᴋᴇʀs / ᴘʜᴏᴛᴏs.",
        show_alert=True,
    )
    # Update round message with new blank
    blank = _word_blank(new_word)
    try:
        await q.message.edit_text(
            q.message.text.rsplit("\n", 1)[0] + f"\n\n📝 **ᴡᴏʀᴅ:** `{blank}`  _({len(new_word)} ʟᴇᴛᴛᴇʀs)_",
            reply_markup=_kb_drawer_controls(chat_id),
        )
    except Exception:
        pass


# ── Give Hint ─────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_hint_(-?\d+)$"))
async def cb_hint(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game or not game.get("word"):
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴏᴜɴᴅ.", show_alert=True)
    if q.from_user.id != game.get("drawer"):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ᴅʀᴀᴡᴇʀ ᴄᴀɴ ɢɪᴠᴇ ʜɪɴᴛs.", show_alert=True)
    word               = game["word"]
    game["hint_count"] = game.get("hint_count", 0) + 1
    hc                 = game["hint_count"]
    reveal             = min(hc, max(1, len(word) // 2))
    hint               = _build_hint(word, reveal)
    await q.answer(f"💡 ʜɪɴᴛ #{hc} ɢɪᴠᴇɴ! (-{HINT_PENALTY} ᴄᴏɪɴs ꜰʀᴏᴍ ᴡɪɴɴᴇʀ)", show_alert=False)
    try:
        await app.send_message(
            chat_id,
            f"<blockquote>💡 **ʜɪɴᴛ #{hc}** (ᴅʀᴀᴡᴇʀ ɢᴀᴠᴇ ᴀ ʜɪɴᴛ · -{HINT_PENALTY} ᴄᴏɪɴs ꜰʀᴏᴍ ᴡɪɴɴᴇʀ)\n"
            f"`{hint}`\n"
            f"_({len(word)} ʟᴇᴛᴛᴇʀs)_</blockquote>",
        )
    except Exception as e:
        print(f"[crocodraw] hint msg error: {e}")


# ── Skip Round ────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_skip_(-?\d+)$"))
async def cb_skip(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    uid = q.from_user.id
    if uid != game.get("drawer") and not await _is_admin(chat_id, uid):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ᴅʀᴀᴡᴇʀ ᴏʀ ᴀɴ ᴀᴅᴍɪɴ ᴄᴀɴ sᴋɪᴘ.", show_alert=True)
    word = game.get("word", "?")
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    game["word"] = None
    await q.answer("⏭ ʀᴏᴜɴᴅ sᴋɪᴘᴘᴇᴅ!")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await app.send_message(
            chat_id,
            f"<blockquote>⏭ **sᴋɪᴘᴘᴇᴅ!**  ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs **{word.upper()}**\n\n"
            f"🎨 ᴡʜᴏ ᴡᴀɴᴛs ᴛᴏ ʙᴇ ᴛʜᴇ ɴᴇxᴛ ᴅʀᴀᴡᴇʀ?</blockquote>",
            reply_markup=_kb_become_drawer(chat_id),
        )
    except Exception as e:
        print(f"[crocodraw] skip msg error: {e}")


# ── Stop Game ─────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_stop_(-?\d+)$"))
async def cb_stop(_, q):
    chat_id = int(q.data.split("_")[2])
    game    = games.get(chat_id)
    if not game:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.", show_alert=True)
    uid = q.from_user.id
    if uid != game.get("started_by") and not await _is_admin(chat_id, uid):
        return await q.answer("❌ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ sᴛᴀʀᴛᴇʀ ᴏʀ ᴀɴ ᴀᴅᴍɪɴ ᴄᴀɴ sᴛᴏᴘ.", show_alert=True)
    word = game.get("word", "?")
    if game.get("task") and not game["task"].done():
        game["task"].cancel()
    games.pop(chat_id, None)
    await q.answer("🛑 ɢᴀᴍᴇ sᴛᴏᴘᴘᴇᴅ!")
    try:
        await q.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await app.send_message(
            chat_id,
            f"<blockquote>🛑 **ɢᴀᴍᴇ sᴛᴏᴘᴘᴇᴅ ʙʏ** {q.from_user.mention}\n"
            f"🎨 ᴛʜᴇ ᴡᴏʀᴅ ᴡᴀs: **{word.upper()}**\n\n"
            f"ᴜsᴇ /crocodraw ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ!</blockquote>",
        )
    except Exception as e:
        print(f"[crocodraw] stop msg error: {e}")


# ── Leaderboard callbacks ─────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_lb_(overall|chat|weekly|monthly|artist)_(-?\d+)$"))
async def cb_leaderboard(_, q):
    m2      = _re.match(r"^croco_lb_(overall|chat|weekly|monthly|artist)_(-?\d+)$", q.data)
    mode    = m2.group(1)
    chat_id = int(m2.group(2))
    await q.answer()

    if mode == "overall":
        top   = await _get_top_global()
        title = "🌍 **ɢʟᴏʙᴀʟ ᴛᴏᴘ 10** (ᴀʟʟ ᴄʜᴀᴛs)"
    elif mode == "artist":
        top   = await _get_top_chat(chat_id, "words_drawn")
        title = "🎨 **ᴛᴏᴘ ᴀʀᴛɪsᴛs** — ᴛʜɪs ᴄʜᴀᴛ"
    else:
        FIELD_MAP = {
            "chat":    ("coins",   "💬 **ᴛʜɪs ᴄʜᴀᴛ ᴛᴏᴘ 10**"),
            "weekly":  ("weekly",  "📅 **ᴡᴇᴇᴋʟʏ ᴛᴏᴘ 10**"),
            "monthly": ("monthly", "🗓 **ᴍᴏɴᴛʜʟʏ ᴛᴏᴘ 10**"),
        }
        field, title = FIELD_MAP[mode]
        top          = await _get_top_chat(chat_id, field)

    try:
        await q.message.edit_text(
            f"<blockquote>{title}</blockquote>\n<blockquote>{top}</blockquote>",
            reply_markup=_kb_top(chat_id),
        )
    except Exception:
        pass


# ── My Rank callback ──────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_myrank_(-?\d+)$"))
async def cb_myrank(_, q):
    chat_id = int(q.data.split("_")[2])
    uid     = q.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await q.answer("ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!", show_alert=True)
    coins       = data.get("coins", 0)
    words_drawn = data.get("words_drawn", 0)
    c_rank      = await _get_chat_rank(chat_id, uid)
    g_rank      = await _get_global_rank(uid)
    display     = get_display_title(coins, words_drawn)
    ge, gn      = get_guesser_title(coins)
    ae, an      = get_artist_title(words_drawn)
    speed       = data.get("best_speed", 0.0)
    next_g      = _next_guesser_title(coins)
    next_a      = _next_artist_title(words_drawn)
    next_block  = ""
    if next_g:
        next_block += f"\n🎯 ɴᴇxᴛ ɢ: {next_g}"
    if next_a:
        next_block += f"\n🎨 ɴᴇxᴛ ᴀ: {next_a}"

    await q.answer()
    try:
        await q.message.edit_text(
            f"<blockquote>📊 **ᴍʏ sᴛᴀᴛs** — {q.from_user.mention}</blockquote>\n"
            f"<blockquote>"
            f"🏅 **ᴄʜᴀᴛ ʀᴀɴᴋ:** #{c_rank}  |  🌍 **ɢʟᴏʙᴀʟ:** #{g_rank}\n"
            f"🎖 **ᴛɪᴛʟᴇ:** {display}\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 **ᴄᴏɪɴs:** {coins}  |  ⭐ **xᴘ:** {data.get('xp', 0)}\n"
            f"📅 **ᴛᴏᴅᴀʏ:** {data.get('today', 0)}\n"
            f"📆 **ᴡᴇᴇᴋ:** {data.get('weekly', 0)}  |  🗓 **ᴍᴏɴᴛʜ:** {data.get('monthly', 0)}\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ **ɢᴜᴇssᴇᴅ:** {data.get('words_guessed', 0)}\n"
            f"🎨 **ᴅʀᴀᴡɴ:** {words_drawn}\n"
            f"⚡ **ʙᴇsᴛ sᴘᴇᴇᴅ:** {speed:.2f} ᴡᴘᴍ\n"
            f"━━━━━━━━━━━━━━\n"
            f"{ge} **{gn}**\n"
            f"{ae} **{an}**"
            f"{next_block}</blockquote>",
            reply_markup=_kb_top(chat_id),
        )
    except Exception:
        pass


# ── Full Stats callback ───────────────────────────────────────
@app.on_callback_query(filters.regex(r"^croco_fullstats_(-?\d+)$"))
async def cb_fullstats(_, q):
    chat_id = int(q.data.split("_")[2])
    uid     = q.from_user.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": uid})
    if not data:
        return await q.answer("ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!", show_alert=True)
    coins       = data.get("coins", 0)
    words_drawn = data.get("words_drawn", 0)
    c_rank      = await _get_chat_rank(chat_id, uid)
    g_rank      = await _get_global_rank(uid)
    ge, gn      = get_guesser_title(coins)
    ae, an      = get_artist_title(words_drawn)
    display     = get_display_title(coins, words_drawn)

    await q.answer()
    try:
        await q.message.edit_text(
            f"<blockquote>📊 **ꜰᴜʟʟ sᴛᴀᴛs** — {q.from_user.mention}</blockquote>\n"
            f"<blockquote>"
            f"{'━'*22}\n"
            f"🏅 ᴄʜᴀᴛ ʀᴀɴᴋ: **#{c_rank}**  |  🌍 ɢʟᴏʙᴀʟ: **#{g_rank}**\n"
            f"🎖 ᴛɪᴛʟᴇ: {display}\n"
            f"{'━'*22}\n"
            f"💰 ᴄᴏɪɴs: **{coins}**  |  ⭐ xᴘ: **{data.get('xp', 0)}**\n"
            f"📅 ᴛᴏᴅᴀʏ: **{data.get('today', 0)}**\n"
            f"📆 ᴡᴇᴇᴋ: **{data.get('weekly', 0)}**  |  🗓 ᴍᴏɴᴛʜ: **{data.get('monthly', 0)}**\n"
            f"{'━'*22}\n"
            f"✅ ᴡᴏʀᴅs ɢᴜᴇssᴇᴅ: **{data.get('words_guessed', 0)}**\n"
            f"🎨 ᴡᴏʀᴅs ᴅʀᴀᴡɴ: **{words_drawn}**\n"
            f"⚡ ʙᴇsᴛ sᴘᴇᴇᴅ: **{data.get('best_speed', 0.0):.2f}** ᴡᴘᴍ\n"
            f"{'━'*22}\n"
            f"{ge} ɢᴜᴇssᴇʀ: **{gn}**\n"
            f"{ae} ᴀʀᴛɪsᴛ: **{an}**</blockquote>",
            reply_markup=_kb_rank(chat_id),
        )
    except Exception:
        pass


# ================================================================
# MODULE META
# ================================================================
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_92"
__help__     = """
🔻 /crocodrawhelp ➠ ꜰᴜʟʟ ʜᴇʟᴘ + ᴛɪᴛʟᴇ ᴘʀᴏɢʀᴇssɪᴏɴ
🔻 /crocodraw ➠ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴄᴏᴄᴏᴅʀᴀᴡ ɢᴀᴍᴇ
🔻 /crocodrawend ➠ sᴛᴏᴘ ɢᴀᴍᴇ (sᴛᴀʀᴛᴇʀ / ᴀᴅᴍɪɴ)
🔻 /crocodrawtop ➠ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (Overall · Monthly · Weekly · Chat · My Rank)
🔻 /crocodrawrank ➠ ᴍʏ ʀᴀɴᴋ & ᴘʀᴏꜰɪʟᴇ
🔻 /crocodrawrules ➠ ɢᴀᴍᴇ ʀᴜʟᴇs
"""
