# ╔══════════════════════════════════════════════════════════════════════╗
# ║          LIFE GAMES MODULE — SHASHA_DRUGZ BOT                        ║
# ║          Single-file plugin · MongoDB persistent storage             ║
# ║                                                                      ║
# ║  NON-SLASH COMMAND FIX:                                              ║
# ║  All aliases (bbet/Bbet/BBET, ppay/Ppay/PPAY, etc.) now work        ║
# ║  via filters.text & manual text matching — fully reliable.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

import os
import re
import random
import asyncio
import time
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus
from SHASHA_DRUGZ import app

try:
    from config import MONGO_DB_URI as MONGO_URL
    from SHASHA_DRUGZ.misc import SUDOERS as _SUDOERS_RAW
    SUDOERS = {int(x) for x in _SUDOERS_RAW}
except Exception:
    MONGO_URL = os.environ.get("MONGO_URL", "")
    SUDOERS   = set()

try:
    from config import OWNER_ID
    OWNER_ID = int(OWNER_ID)
except Exception:
    OWNER_ID = 0

# ─────────────────────────────────────────────────────────────────
#  MONGODB SETUP
# ─────────────────────────────────────────────────────────────────
from pymongo import MongoClient

_mongo        = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
_db           = _mongo["lifegames_db"]
users_col     = _db["users"]
cooldowns_col = _db["cooldowns"]
groups_col    = _db["groups"]
loans_col     = _db["loans"]

users_col.create_index("user_id",  unique=True)
cooldowns_col.create_index([("user_id", 1), ("cmd", 1)], unique=True)
groups_col.create_index("chat_id", unique=True)

# ─────────────────────────────────────────────────────────────────
#  FIX — async wrapper so sync pymongo never blocks the loop
# ─────────────────────────────────────────────────────────────────
_loop = asyncio.get_event_loop()

async def _run(fn, *args):
    return await _loop.run_in_executor(None, fn, *args)

# ─────────────────────────────────────────────────────────────────
#  GAME CONSTANTS
# ─────────────────────────────────────────────────────────────────
SLOT_ICONS     = ["🍒", "🍋", "🍉", "⭐", "💎", "7️⃣"]
LEVEL_XP_TABLE = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500, 5500, 7000]

JOBS = {
    "hacker": {"emoji": "💻", "bonus_type": "steal_chance", "bonus_val": 15, "salary": 3000000},
    "banker": {"emoji": "🏦", "bonus_type": "daily_bonus",  "bonus_val": 10, "salary": 2500000},
    "police": {"emoji": "👮", "bonus_type": "protection",   "bonus_val": 20, "salary": 2000000},
    "thief":  {"emoji": "🕵️", "bonus_type": "steal_chance", "bonus_val": 20, "salary": 1800000},
    "trader": {"emoji": "📈", "bonus_type": "shop_discount","bonus_val": 10, "salary": 3500000},
}

PETS = {
    "dog":    {"emoji": "🐶", "price": 100000000,  "power": 5},
    "cat":    {"emoji": "🐱", "price": 120000000,  "power": 7},
    "wolf":   {"emoji": "🐺", "price": 250000000,  "power": 15},
    "fox":    {"emoji": "🦊", "price": 300000000,  "power": 18},
    "dragon": {"emoji": "🐉", "price": 1000000000, "power": 40},
}

GUNS = {
    "pistol":  {"emoji": "🔫", "price": 150000000, "damage": 10},
    "shotgun": {"emoji": "🔫", "price": 300000000, "damage": 20},
    "rifle":   {"emoji": "🎯", "price": 500000000, "damage": 30},
    "sniper":  {"emoji": "🎯", "price": 800000000, "damage": 45},
}

ARMOR = {
    "helmet":        {"emoji": "⛑",  "price": 80000000,  "defense": 8},
    "vest":          {"emoji": "🦺", "price": 150000000, "defense": 15},
    "shield":        {"emoji": "🛡",  "price": 250000000, "defense": 25},
    "tactical_suit": {"emoji": "🥷", "price": 500000000, "defense": 40},
}

SOCIAL_EMOJIS = {"hug": "🤗", "kiss": "😘", "slap": "👋", "love": "❤️"}

# ============================================================
# 🖼️ LIFE GAME IMAGE ASSETS
# ============================================================
LIFE_ASSETS = {
    "win":  "SHASHA_DRUGZ/assets/shasha/win.jpeg",
    "loss": "SHASHA_DRUGZ/assets/shasha/loss.jpg",
}

# ─────────────────────────────────────────────────────────────────
#  SYNC DATABASE HELPERS
# ─────────────────────────────────────────────────────────────────
_DEFAULT_USER = {
    "coins": 500, "xp": 0, "level": 1,
    "partner": 0, "parent": 0, "sibling": 0,
    "job": "", "pet": "", "gun": "", "armor": "",
    "jail_until": 0,
    "bank": 0,
    "streak": 0,
}

def _get_user(uid: int) -> dict:
    doc = users_col.find_one({"user_id": uid})
    if not doc:
        doc = {"user_id": uid, **_DEFAULT_USER}
        users_col.insert_one(doc)
    missing = {k: v for k, v in _DEFAULT_USER.items() if k not in doc}
    if missing:
        users_col.update_one({"user_id": uid}, {"$set": missing})
        doc.update(missing)
    return doc

def _update_user(uid: int, fields: dict):
    users_col.update_one({"user_id": uid}, {"$set": fields}, upsert=True)

def _add_coins(uid: int, amount: int):
    users_col.update_one({"user_id": uid}, {"$inc": {"coins": amount}}, upsert=True)

def _remove_coins(uid: int, amount: int):
    users_col.update_one({"user_id": uid}, {"$inc": {"coins": -amount}}, upsert=True)

def _get_coins(uid: int) -> int:
    doc = users_col.find_one({"user_id": uid}, {"coins": 1})
    return doc["coins"] if doc else _DEFAULT_USER["coins"]

def _add_xp(uid: int, amount: int) -> int:
    user   = _get_user(uid)
    new_xp = user["xp"] + amount
    level  = user["level"]
    while level < len(LEVEL_XP_TABLE) - 1 and new_xp >= LEVEL_XP_TABLE[level]:
        level += 1
    _update_user(uid, {"xp": new_xp, "level": level})
    return level

def _check_cooldown(uid: int, cmd: str, seconds: int) -> int:
    now = int(time.time())
    rec = cooldowns_col.find_one({"user_id": uid, "cmd": cmd})
    if rec:
        elapsed = now - rec["timestamp"]
        if elapsed < seconds:
            return seconds - elapsed
        cooldowns_col.update_one({"user_id": uid, "cmd": cmd}, {"$set": {"timestamp": now}})
    else:
        cooldowns_col.insert_one({"user_id": uid, "cmd": cmd, "timestamp": now})
    return 0

def _get_top(mode: str) -> list:
    return list(users_col.find({}, {"user_id": 1, mode: 1}).sort(mode, -1).limit(10))

# ─────────────────────────────────────────────────────────────────
#  UTILITY HELPERS
# ─────────────────────────────────────────────────────────────────
def fmt_time(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h:  return f"{h}h {m}m"
    if m:  return f"{m}m {s}s"
    return f"{s}s"

def mention(user) -> str:
    name = (user.first_name or "User")[:20]
    return f"[{name}](tg://user?id={user.id})"

def calc_power(user: dict) -> int:
    base     = user.get("level", 1) * 5
    pet_pw   = PETS.get(user.get("pet", ""), {}).get("power", 0)
    gun_dmg  = GUNS.get(user.get("gun", ""), {}).get("damage", 0)
    armor_df = ARMOR.get(user.get("armor", ""), {}).get("defense", 0)
    luck     = random.randint(1, 30)
    return base + pet_pw + gun_dmg + armor_df + luck

def _parse_args(text: str) -> list:
    """Split text and return everything after the first word (the command/alias)."""
    parts = (text or "").strip().split()
    return parts[1:] if parts else []

async def is_admin(client, m: Message) -> bool:
    if not m.from_user:
        return False
    uid = m.from_user.id
    if uid == OWNER_ID or uid in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(m.chat.id, uid)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

async def _send_life_image(message, result_type: str, caption: str):
    path = LIFE_ASSETS.get(result_type)
    if path and os.path.isfile(path):
        try:
            await message.reply_photo(photo=path, caption=caption)
            return
        except Exception:
            pass
    await message.reply_text(caption)

# ─────────────────────────────────────────────────────────────────
#  CUSTOM FILTER FACTORY — matches any alias, case-sensitive list
#  Works for BOTH slash commands AND plain-text aliases reliably.
# ─────────────────────────────────────────────────────────────────
def _alias_filter(*aliases):
    """
    Returns a filter that matches when m.text (lowered or exact) starts
    with any of the provided aliases (case-sensitive as given).
    Handles both slash-command format and plain-text aliases.
    """
    pattern = re.compile(
        r"^(" + "|".join(re.escape(a) for a in aliases) + r")(\s|$)"
    )
    async def func(_, __, m: Message):
        txt = m.text or m.caption or ""
        return bool(pattern.match(txt))
    return filters.create(func)

# ─────────────────────────────────────────────────────────────────
#  INLINE KEYBOARD BUILDERS
# ─────────────────────────────────────────────────────────────────
def _shop_main_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔫 ᴀʀᴍᴏʀʏ",   callback_data="shop_armory"),
            InlineKeyboardButton("🐾 ᴘᴇᴛ sʜᴏᴘ", callback_data="shop_petshop"),
        ],
        [InlineKeyboardButton("🎒 ᴍʏ ɪɴᴠᴇɴᴛᴏʀʏ", callback_data="shop_inventory")],
    ])

def _armory_kb():
    rows = []
    for key, item in GUNS.items():
        rows.append([InlineKeyboardButton(
            f"{item['emoji']} {key.capitalize()}  💰{item['price']:,}",
            callback_data=f"buy_gun_{key}",
        )])
    for key, item in ARMOR.items():
        rows.append([InlineKeyboardButton(
            f"{item['emoji']} {key.replace('_',' ').title()}  💰{item['price']:,}",
            callback_data=f"buy_armor_{key}",
        )])
    rows.append([InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_main")])
    return InlineKeyboardMarkup(rows)

def _petshop_kb():
    rows = [
        [InlineKeyboardButton(
            f"{pet['emoji']} {key.capitalize()}  💰{pet['price']:,}",
            callback_data=f"buy_pet_{key}",
        )]
        for key, pet in PETS.items()
    ]
    rows.append([InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_main")])
    return InlineKeyboardMarkup(rows)

# ─────────────────────────────────────────────────────────────────
#  IN-MEMORY PENDING STATE
# ─────────────────────────────────────────────────────────────────
_pending_duels:    dict = {}
_active_giveaways: dict = {}
_pending_loans:    dict = {}

# ═══════════════════════════════════════════════════════════════
#  ALL HANDLERS — registered at MODULE LEVEL
# ═══════════════════════════════════════════════════════════════

# ────────────────────────────────────────────
#  PROFILE — /lifeprofile | pprofile
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifeprofile"]) | _alias_filter("pprofile", "Pprofile", "PPROFILE"))
    & filters.group
)
async def profile_cmd(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    pet = PETS.get(u["pet"], {})
    gun = GUNS.get(u["gun"], {})
    arm = ARMOR.get(u["armor"], {})
    job = JOBS.get(u["job"], {})
    partner_txt = (
        f"[{u['partner']}](tg://user?id={u['partner']})" if u["partner"] else "None"
    )
    await m.reply(
        f"<blockquote>👤 **ʟɪғᴇ ᴘʀᴏғɪʟᴇ**</blockquote>\n"
        f"<blockquote>━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 ᴄᴏɪɴs : **{u['coins']:,}**\n"
        f"🏦 ʙᴀɴᴋ  : **{u.get('bank',0):,}**\n"
        f"⭐ xᴘ    : **{u['xp']:,}**\n"
        f"📊 ʟᴇᴠᴇʟ : **{u['level']}**\n"
        f"🔥 sᴛʀᴇᴀᴋ: **{u.get('streak',0)}**</blockquote>\n"
        f"<blockquote>━━━━━━━━━━━━━━━━━━━━\n"
        f"❤️ ᴘᴀʀᴛɴᴇʀ : {partner_txt}\n"
        f"💼 ᴊᴏʙ     : {job.get('emoji','—')} {u['job'].capitalize() or 'None'}\n"
        f"🐾 ᴘᴇᴛ     : {pet.get('emoji','—')} {u['pet'].capitalize() or 'None'}\n"
        f"🔫 ɢᴜɴ     : {gun.get('emoji','—')} {u['gun'].capitalize() or 'None'}\n"
        f"🛡 ᴀʀᴍᴏʀ   : {arm.get('emoji','—')} {u['armor'].replace('_',' ').title() or 'None'}\n"
        f"⚔️ ᴘᴏᴡᴇʀ   : **{calc_power(u)}**</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  BALANCE — /lifebalance | bbalance
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifebalance"]) | _alias_filter("bbalance", "Bbalance", "BBALANCE"))
    & filters.group
)
async def balance_cmd(client, m: Message):
    coins = await _run(_get_coins, m.from_user.id)
    await m.reply(f"<blockquote>💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: **{coins:,}** ᴄᴏɪɴs</blockquote>")

# ────────────────────────────────────────────
#  DAILY — /lifedaily | ddaily
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifedaily"]) | _alias_filter("ddaily", "Ddaily", "DDAILY"))
    & filters.group
)
async def daily_cmd(client, m: Message):
    uid  = m.from_user.id
    wait = await _run(_check_cooldown, uid, "daily", 86400)
    if wait:
        return await m.reply(f"<blockquote>⏳ ᴄᴏᴍᴇ ʙᴀᴄᴋ ɪɴ **{fmt_time(wait)}**</blockquote>")
    u     = await _run(_get_user, uid)
    base  = random.randint(200, 500)
    bonus = 0
    if u["job"] == "banker":
        bonus = max(50, int(u["coins"] * 0.10))
    reward = base + bonus
    await _run(_add_coins, uid, reward)
    await _run(_add_xp, uid, 10)
    bonus_line = f"\n🏦 Banker bonus: **+{bonus}** coins" if bonus else ""
    await m.reply(
        f"<blockquote>🎁 **ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ ᴄʟᴀɪᴍᴇᴅ!**</blockquote>\n"
        f"<blockquote>💰 **+{reward}** ᴄᴏɪɴs{bonus_line}\n"
        f"⭐ **+10** xᴘ</blockquote>"
    )

# ────────────────────────────────────────────
#  LEADERBOARD — /lifetop | ttop
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifetop"]) | _alias_filter("ttop", "Ttop", "TTOP"))
    & filters.group
)
async def top_cmd(client, m: Message):
    args  = _parse_args(m.text)
    mode  = args[0].lower() if args else "coins"
    modes = {"coins": "💰 ᴄᴏɪɴs", "xp": "⭐ xᴘ", "level": "📊 ʟᴇᴠᴇʟ"}
    if mode not in modes:
        mode = "coins"
    data   = await _run(_get_top, mode)
    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    for i, doc in enumerate(data):
        badge = medals[i] if i < 3 else f"**{i+1}.**"
        val   = doc.get(mode, 0)
        lines.append(f"<blockquote>{badge} [{doc['user_id']}](tg://user?id={doc['user_id']}) — {val:,}</blockquote>")
    await m.reply(
        f"<blockquote>🏆 **ᴛᴏᴘ ᴘʟᴀʏᴇʀs — {modes[mode]}**</blockquote>\n"
        f"<blockquote>━━━━━━━━━━━━━━━━━━━━</blockquote>\n" + "\n".join(lines),
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  SOCIAL ACTIONS (shared helper)
# ────────────────────────────────────────────
async def _social(m: Message, action: str):
    if not m.reply_to_message:
        return await m.reply(f"<blockquote>ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ {action} ᴛʜᴇᴍ!</blockquote>")
    target = m.reply_to_message.from_user
    emoji  = SOCIAL_EMOJIS.get(action, "✨")
    await m.reply(
        f"<blockquote>{emoji} **{mention(m.from_user)}** {action}ed **{mention(target)}**!</blockquote>",
        disable_web_page_preview=True,
    )

@Client.on_message(
    (filters.command(["lifehug"]) | _alias_filter("hhug", "Hhug", "HHUG")) & filters.group
)
async def hug_cmd(client, m): await _social(m, "hug")

@Client.on_message(
    (filters.command(["lifekiss"]) | _alias_filter("kkiss", "Kkiss", "KKISS")) & filters.group
)
async def kiss_cmd(client, m): await _social(m, "kiss")

@Client.on_message(
    (filters.command(["lifeslap"]) | _alias_filter("sslap", "Sslap", "SSLAP")) & filters.group
)
async def slap_cmd(client, m): await _social(m, "slap")

@Client.on_message(
    (filters.command(["lifelove"]) | _alias_filter("llove", "Llove", "LLOVE")) & filters.group
)
async def love_cmd(client, m): await _social(m, "love")

# ────────────────────────────────────────────
#  MARRY — /lifemarry | mmarry
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifemarry"]) | _alias_filter("mmarry", "Mmarry", "MMARRY"))
    & filters.group
)
async def marry_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("💍 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴘʀᴏᴘᴏsᴇ!")
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴀʀʀʏ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    u1 = await _run(_get_user, uid)
    u2 = await _run(_get_user, tid)
    if u1["partner"]:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ᴍᴀʀʀɪᴇᴅ! ᴜsᴇ /lifedivorce ғɪʀsᴛ.</blockquote>")
    if u2["partner"]:
        return await m.reply("<blockquote>❌ ᴛʜᴀᴛ ᴘᴇʀsᴏɴ ɪs ᴀʟʀᴇᴀᴅʏ ᴍᴀʀʀɪᴇᴅ!</blockquote>")
    await _run(_update_user, uid, {"partner": tid})
    await _run(_update_user, tid, {"partner": uid})
    await _run(_add_xp, uid, 20)
    await _run(_add_xp, tid, 20)
    await m.reply(
        f"<blockquote>💍 **{mention(m.from_user)}** and "
        f"**{mention(m.reply_to_message.from_user)}** ᴀʀᴇ ɴᴏᴡ ᴍᴀʀʀɪᴇᴅ! 💕</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  DIVORCE — /lifedivorce | ddivorce
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifedivorce"]) | _alias_filter("ddivorce", "Ddivorce", "DDIVORCE"))
    & filters.group
)
async def divorce_cmd(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    if not u["partner"]:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴍᴀʀʀɪᴇᴅ!</blockquote>")
    await _run(_update_user, u["partner"], {"partner": 0})
    await _run(_update_user, uid, {"partner": 0})
    await m.reply("<blockquote>💔 ʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴅɪᴠᴏʀᴄᴇᴅ.</blockquote>")

# ────────────────────────────────────────────
#  PARENT — /lifeparent | pparent
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifeparent"]) | _alias_filter("pparent", "Pparent", "PPARENT"))
    & filters.group
)
async def parent_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴀᴅᴏᴘᴛ ᴛʜᴇᴍ!")
    tid = m.reply_to_message.from_user.id
    await _run(_update_user, tid, {"parent": m.from_user.id})
    await m.reply(
        f"<blockquote>👨‍👧 **{mention(m.from_user)}** ʜᴀs ᴀᴅᴏᴘᴛᴇᴅ "
        f"**{mention(m.reply_to_message.from_user)}**!</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  SIBLING — /lifesibling | ssibling
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifesibling"]) | _alias_filter("ssibling", "Ssibling", "SSIBLING"))
    & filters.group
)
async def sibling_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ʙᴇᴄᴏᴍᴇ sɪʙʟɪɴɢs!")
    uid, tid = m.from_user.id, m.reply_to_message.from_user.id
    await _run(_update_user, uid, {"sibling": tid})
    await _run(_update_user, tid, {"sibling": uid})
    await m.reply(
        f"<blockquote>👫 **{mention(m.from_user)}** ᴀɴᴅ "
        f"**{mention(m.reply_to_message.from_user)}** ᴀʀᴇ ɴᴏᴡ sɪʙʟɪɴɢs!</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  STEAL — /steal | ssteal | Ssteal | SSTEAL
#  ROB   — /rob   | rrob | Rrob | RROB
# ────────────────────────────────────────────
@Client.on_message(
    (
        filters.command(["steal", "rob"])
        | _alias_filter("ssteal", "Ssteal", "SSTEAL", "rrob", "Rrob", "RROB")
    )
    & filters.group
)
async def steal_cmd(client, m: Message):
    target_user = m.reply_to_message.from_user if m.reply_to_message else None
    if not target_user:
        return await m.reply("<blockquote>🕵️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ sᴛᴇᴀʟ ғʀᴏᴍ ᴛʜᴇᴍ!</blockquote>")
    uid, tid = m.from_user.id, target_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ sᴛᴇᴀʟ ғʀᴏᴍ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    u   = await _run(_get_user, uid)
    now = int(time.time())
    if u.get("jail_until", 0) > now:
        return await m.reply(
            f"<blockquote>🚔 ʏᴏᴜ'ʀᴇ ɪɴ ᴊᴀɪʟ! ʀᴇʟᴇᴀsᴇ ɪɴ **{fmt_time(u['jail_until'] - now)}**</blockquote>"
        )
    wait = await _run(_check_cooldown, uid, "steal", 1800)
    if wait:
        return await m.reply(f"<blockquote>⏳ sᴛᴇᴀʟ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**</blockquote>")
    victim_coins = await _run(_get_coins, tid)
    if victim_coins < 100:
        return await m.reply("<blockquote>❌ ᴛᴀʀɢᴇᴛ ʜᴀs ғᴇᴡᴇʀ ᴛʜᴀɴ 100 ᴄᴏɪɴs, ɴᴏᴛ ᴡᴏʀᴛʜ ɪᴛ!</blockquote>")
    chance = 40
    if u.get("job") == "thief":  chance += 20
    if u.get("job") == "hacker": chance += 15
    victim = await _run(_get_user, tid)
    if victim.get("job") == "police": chance -= 20
    chance = max(10, min(chance, 80))
    if random.randint(1, 100) <= chance:
        stolen = int(victim_coins * random.uniform(0.10, 0.25))
        await _run(_remove_coins, tid, stolen)
        await _run(_add_coins, uid, stolen)
        await _run(_add_xp, uid, 15)
        await m.reply(
            f"<blockquote>🕵️ **ʜᴇɪsᴛ sᴜᴄᴄᴇssғᴜʟ!**</blockquote>\n"
            f"<blockquote>{mention(m.from_user)} sᴛᴏʟᴇ **{stolen:,}** ᴄᴏɪɴs "
            f"ғʀᴏᴍ {mention(target_user)}! 💸</blockquote>",
            disable_web_page_preview=True,
        )
    else:
        fine       = random.randint(100, 300)
        jail_until = now + 600
        await _run(_remove_coins, uid, fine)
        await _run(_update_user, uid, {"jail_until": jail_until})
        await m.reply(
            f"<blockquote>🚨 **ᴄᴀᴜɢʜᴛ ʀᴇᴅ-ʜᴀɴᴅᴇᴅ!**</blockquote>\n"
            f"<blockquote>ғɪɴᴇ: **{fine}** ᴄᴏɪɴs ᴅᴇᴅᴜᴄᴛᴇᴅ\n"
            f"🚔 ᴊᴀɪʟᴇᴅ ғᴏʀ **10 ᴍɪɴᴜᴛᴇs**</blockquote>"
        )

# ────────────────────────────────────────────
#  DUEL — /duel | dduel | Dduel | DDUEL
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["duel"]) | _alias_filter("dduel", "Dduel", "DDUEL"))
    & filters.group
)
async def duel_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("<blockquote>⚔️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴄʜᴀʟʟᴇɴɢᴇ ᴛʜᴇᴍ!</blockquote>\n<blockquote>ᴜsᴀɢᴇ: /duel <amount></blockquote>")
    args = _parse_args(m.text)
    try:
        bet = int(args[0]) if args else 0
        if bet < 50:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>⚔️ ᴜsᴀɢᴇ: `/duel <amount>` — ʀᴇᴘʟʏ ᴛᴏ ʏᴏᴜʀ ᴛᴀʀɢᴇᴛ</blockquote>")
    uid, tid = m.from_user.id, m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ᴅᴜᴇʟ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    if await _run(_get_coins, uid) < bet:
        return await m.reply("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!")
    if await _run(_get_coins, tid) < bet:
        return await m.reply("<blockquote>❌ ʏᴏᴜʀ ᴏᴘᴘᴏɴᴇɴᴛ ᴅᴏᴇsɴ'ᴛ ʜᴀᴠᴇ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    key = f"{uid}_{tid}_{int(time.time())}"
    _pending_duels[key] = {"bet": bet, "challenger": uid, "target": tid, "ts": time.time()}
    await m.reply(
        f"<blockquote>⚔️ **ᴅᴜᴇʟ ᴄʜᴀʟʟᴇɴɢᴇ!**</blockquote>\n"
        f"<blockquote>🥊 {mention(m.from_user)} ᴠs {mention(m.reply_to_message.from_user)}\n"
        f"💰 sᴛᴀᴋᴇ: **{bet:,}** ᴄᴏɪɴs ᴇᴀᴄʜ</blockquote>\n\n"
        f"<blockquote>{m.reply_to_message.from_user.first_name}, ᴅᴏ ʏᴏᴜ ᴀᴄᴄᴇᴘᴛ?</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🍏 ᴀᴄᴄᴇᴘᴛ",  callback_data=f"duel_accept_{key}"),
            InlineKeyboardButton("🍎 ᴅᴇᴄʟɪɴᴇ", callback_data=f"duel_decline_{key}"),
        ]]),
        disable_web_page_preview=True,
    )

@Client.on_callback_query(filters.regex(r"^duel_(accept|decline)_(.+)$"))
async def duel_response(client, q: CallbackQuery):
    action = q.matches[0].group(1)
    key    = q.matches[0].group(2)
    duel   = _pending_duels.get(key)
    if not duel:
        return await q.answer("⌛ ᴛʜɪs ᴅᴜᴇʟ ʜᴀs ᴇxᴘɪʀᴇᴅ!", show_alert=True)
    if q.from_user.id != duel["target"]:
        return await q.answer("❌ ᴛʜɪs ᴄʜᴀʟʟᴇɴɢᴇ ɪsɴ'ᴛ ғᴏʀ ʏᴏᴜ!", show_alert=True)
    if time.time() - duel["ts"] > 90:
        _pending_duels.pop(key, None)
        return await q.answer("⌛ ᴅᴜᴇʟ ᴇxᴘɪʀᴇᴅ (90s ᴛɪᴍᴇᴏᴜᴛ)!", show_alert=True)
    _pending_duels.pop(key, None)
    if action == "decline":
        return await q.message.edit("❌ ᴅᴜᴇʟ ᴡᴀs ᴅᴇᴄʟɪɴᴇᴅ.")
    uid1, uid2, bet = duel["challenger"], duel["target"], duel["bet"]
    u1, u2   = await _run(_get_user, uid1), await _run(_get_user, uid2)
    p1, p2   = calc_power(u1), calc_power(u2)
    if p1 >= p2:
        winner_id, loser_id, wp, lp = uid1, uid2, p1, p2
    else:
        winner_id, loser_id, wp, lp = uid2, uid1, p2, p1
    await _run(_add_coins, winner_id, bet)
    await _run(_remove_coins, loser_id, bet)
    await _run(_add_xp, winner_id, 25)
    try:
        w           = await client.get_chat_member(q.message.chat.id, winner_id)
        winner_name = w.user.first_name
    except Exception:
        winner_name = str(winner_id)
    await q.message.edit(
        f"<blockquote>⚔️ **ᴅᴜᴇʟ ʀᴇsᴜʟᴛ!**</blockquote>\n"
        f"<blockquote>🏆 ᴡɪɴɴᴇʀ: [{winner_name}](tg://user?id={winner_id})\n"
        f"💪 ᴘᴏᴡᴇʀ: **{wp}** vs {lp}\n"
        f"💰 ᴘʀɪᴢᴇ: **{bet:,}** ᴄᴏɪɴs\n"
        f"⭐ +25 xᴘ</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  BOWLING — /lifebowling | bbowling | Bbowling | BBOWLING
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifebowling"]) | _alias_filter("bbowling", "Bbowling", "BBOWLING"))
    & filters.group
)
async def bowling_cmd(client, m: Message):
    args = _parse_args(m.text)
    try:
        bet = int(args[0])
        if bet < 10:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎳 ᴜsᴀɢᴇ: `/lifebowling <amount>`</blockquote>")
    uid = m.from_user.id
    if await _run(_get_coins, uid) < bet:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    wait = await _run(_check_cooldown, uid, "bowling", 30)
    if wait:
        return await m.reply(f"<blockquote>⏳ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**</blockquote>")
    dice_msg = await m.reply_dice(emoji="🎳")
    score    = dice_msg.dice.value
    await asyncio.sleep(3)
    if score == 6:
        prize  = bet * 3
        await _run(_add_coins, uid, prize)
        result = f"<blockquote>🎳 **sᴛʀɪᴋᴇ!** ᴘᴇʀғᴇᴄᴛ sᴄᴏʀᴇ!\n💰 ᴡᴏɴ **{prize:,}** ᴄᴏɪɴs 🎉</blockquote>"
    elif score >= 4:
        prize  = int(bet * 1.5)
        await _run(_add_coins, uid, prize - bet)
        result = f"<blockquote>🎳 sᴄᴏʀᴇ: **{score}/6** — ɴɪᴄᴇ sʜᴏᴛ!\n💰 ᴡᴏɴ **{prize:,}** ᴄᴏɪɴs</blockquote>"
    else:
        await _run(_remove_coins, uid, bet)
        result = f"<blockquote>🎳 sᴄᴏʀᴇ: **{score}/6** — ɢᴜᴛᴛᴇʀʙᴀʟʟ!\n💸 ʟᴏsᴛ **{bet:,}** ᴄᴏɪɴs</blockquote>"
    await m.reply(result)

# ────────────────────────────────────────────
#  SLOTS — /sslots | sslots | Sslots | SSLOTS
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["sslots", "slots"]) | _alias_filter("sslots", "Sslots", "SSLOTS"))
    & filters.group
)
async def slots_cmd(client, m: Message):
    args = _parse_args(m.text)
    try:
        bet = int(args[0])
        if bet < 10:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎰 ᴜsᴀɢᴇ: `/sslots <amount>`  (ᴍɪɴ 10)</blockquote>")
    uid = m.from_user.id
    if await _run(_get_coins, uid) < bet:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    wait = await _run(_check_cooldown, uid, "slots", 10)
    if wait:
        return await m.reply(f"⏳ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**")
    msg = await m.reply(f"<blockquote>🎰 sᴘɪɴɴɪɴɢ...\n💰 ʙᴇᴛ: **{bet:,}**</blockquote>")
    for _ in range(4):
        r = [random.choice(SLOT_ICONS) for _ in range(3)]
        await msg.edit(
            f"<blockquote>🎰 **ʟɪғᴇ sʟᴏᴛs**</blockquote>\n\n"
            f"<blockquote>┃ {r[0]} ┃ {r[1]} ┃ {r[2]} ┃\n\n"
            f"💰 Bet: {bet:,}\n🔄 sᴘɪɴɴɪɴɢ...</blockquote>"
        )
        await asyncio.sleep(0.7)
    r    = [random.choice(SLOT_ICONS) for _ in range(3)]
    body = f"<blockquote>🎰 **ʟɪғᴇ sʟᴏᴛs**\n\n┃ {r[0]} ┃ {r[1]} ┃ {r[2]} ┃</blockquote>\n\n"
    if r[0] == r[1] == r[2]:
        prize = bet * 5
        await _run(_add_coins, uid, prize)
        await _run(_add_xp, uid, 30)
        body += f"<blockquote>🎉 **ᴊᴀᴄᴋᴘᴏᴛ!** ᴛʀɪᴘʟᴇ {r[0]}\n💰 ᴡᴏɴ **{prize:,}** ᴄᴏɪɴs\n⭐ +30 xᴘ</blockquote>"
    elif r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
        prize = int(bet * 1.5)
        await _run(_add_coins, uid, prize - bet)
        await _run(_add_xp, uid, 10)
        body += f"<blockquote>✨ **ᴛᴡᴏ ᴏғ ᴀ ᴋɪɴᴅ!**\n💰 ᴡᴏɴ **{prize:,}** ᴄᴏɪɴs\n⭐ +10 xᴘ</blockquote>"
    else:
        await _run(_remove_coins, uid, bet)
        body += f"<blockquote>💀 **ɴᴏ ᴍᴀᴛᴄʜ!**\n💸 ʟᴏsᴛ **{bet:,}** ᴄᴏɪɴs</blockquote>"
    await msg.edit(body)

# ────────────────────────────────────────────
#  JOB — /lifejob | jjob | Jjob | JJOB
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifejob"]) | _alias_filter("jjob", "Jjob", "JJOB"))
    & filters.group
)
async def job_cmd(client, m: Message):
    uid  = m.from_user.id
    u    = await _run(_get_user, uid)
    args = _parse_args(m.text)
    if not args:
        lines   = [
            f"{ji['emoji']} **{name.capitalize()}** — {ji['salary']} ᴄᴏɪɴs/ᴅᴀʏ"
            for name, ji in JOBS.items()
        ]
        current = ""
        if u["job"]:
            ji      = JOBS[u["job"]]
            current = f"\n\n<blockquote>✅ ᴄᴜʀʀᴇɴᴛ: {ji['emoji']} **{u['job'].capitalize()}**</blockquote>"
        return await m.reply(
            "<blockquote>💼 **ᴀᴠᴀɪʟᴀʙʟᴇ ᴊᴏʙs**</blockquote>\n<blockquote>━━━━━━━━━━━━━━\n"
            + "\n".join(lines)
            + "\n\n📝 ᴜsᴇ: `/lifejob <ᴊᴏʙɴᴀᴍᴇ>`</blockquote>"
            + current
        )
    job_name = args[0].lower()
    if job_name not in JOBS:
        return await m.reply("<blockquote>❌ ᴜɴᴋɴᴏᴡɴ ᴊᴏʙ. ᴜsᴇ `/lifejob` ᴛᴏ sᴇᴇ ᴛʜᴇ ʟɪsᴛ.</blockquote>")
    if u["job"] and u["job"] != job_name:
        wait = await _run(_check_cooldown, uid, "job_change", 86400)
        if wait:
            return await m.reply(f"<blockquote>⏳ ᴊᴏʙ ᴄʜᴀɴɢᴇ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**</blockquote>")
    await _run(_update_user, uid, {"job": job_name})
    ji = JOBS[job_name]
    await m.reply(
        f"<blockquote>✅ ʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴀ **{job_name.capitalize()}** {ji['emoji']}</blockquote>\n"
        f"<blockquote>💰 sᴀʟᴀʀʏ: **{ji['salary']}** ᴄᴏɪɴs / 4ʜ\n"
        f"🎯 ʙᴏɴᴜs: +{ji['bonus_val']}% {ji['bonus_type'].replace('_', ' ')}</blockquote>"
    )

# ────────────────────────────────────────────
#  WORK — /lifework | wwork | Wwork | WWORK
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifework"]) | _alias_filter("wwork", "Wwork", "WWORK"))
    & filters.group
)
async def work_cmd(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    if not u["job"]:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀ ᴊᴏʙ! ᴜsᴇ `/lifejob` ᴛᴏ ᴘɪᴄᴋ ᴏɴᴇ.</blockquote>")
    wait = await _run(_check_cooldown, uid, "work", 14400)
    if wait:
        return await m.reply(f"<blockquote>⏳ ᴡᴏʀᴋ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**</blockquote>")
    ji     = JOBS[u["job"]]
    salary = ji["salary"] + random.randint(-50, 100)
    salary = max(50, salary)
    await _run(_add_coins, uid, salary)
    await _run(_add_xp, uid, 20)
    await m.reply(
        f"<blockquote>💼 {ji['emoji']} ʏᴏᴜ ᴡᴏʀᴋᴇᴅ ᴀs ᴀ **{u['job'].capitalize()}**</blockquote>\n"
        f"<blockquote>💰 ᴇᴀʀɴᴇᴅ: **{salary:,}** ᴄᴏɪɴs\n"
        f"⭐ +20 xᴘ</blockquote>"
    )

# ────────────────────────────────────────────
#  FIGHT — /lifefight | ffight | Ffight | FFIGHT
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifefight"]) | _alias_filter("ffight", "Ffight", "FFIGHT"))
    & filters.group
)
async def fight_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("<blockquote>⚔️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ғɪɢʜᴛ ᴛʜᴇᴍ!</blockquote>")
    uid, tid = m.from_user.id, m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ғɪɢʜᴛ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    wait = await _run(_check_cooldown, uid, "fight", 300)
    if wait:
        return await m.reply(f"<blockquote>⏳ ғɪɢʜᴛ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**</blockquote>")
    u1, u2 = await _run(_get_user, uid), await _run(_get_user, tid)
    p1, p2 = calc_power(u1), calc_power(u2)
    msg = await m.reply(
        f"<blockquote>⚔️ **ғɪɢʜᴛ ɪɴɪᴛɪᴀᴛᴇᴅ!**</blockquote>\n"
        f"<blockquote>🥊 {mention(m.from_user)} **({p1} power)**\n"
        f"ᴠs\n"
        f"🥊 {mention(m.reply_to_message.from_user)} **({p2} power)**</blockquote>\n\n"
        f"<blockquote>⚡ ᴄᴀʟᴄᴜʟᴀᴛɪɴɢ ᴏᴜᴛᴄᴏᴍᴇ...</blockquote>",
        disable_web_page_preview=True,
    )
    await asyncio.sleep(2)
    reward = random.randint(100, 300)
    if p1 >= p2:
        await _run(_add_coins, uid, reward)
        await _run(_add_xp, uid, 20)
        winner_name = m.from_user.first_name
    else:
        await _run(_add_coins, tid, reward)
        await _run(_add_xp, tid, 20)
        winner_name = m.reply_to_message.from_user.first_name
    await msg.edit(
        f"<blockquote>⚔️ **ғɪɢʜᴛ ʀᴇsᴜʟᴛ**</blockquote>\n"
        f"<blockquote>🏆 **{winner_name}** ᴡɪɴs!\n"
        f"💪 ᴘᴏᴡᴇʀ: {p1} ᴠs {p2}\n"
        f"💰 ʀᴇᴡᴀʀᴅ: **{reward:,}** coins\n"
        f"⭐ +20 xᴘ</blockquote>"
    )

# ────────────────────────────────────────────
#  GIVEAWAY — /lifegiveaway | ggiveaway | Ggiveaway | GGIVEAWAY
# ────────────────────────────────────────────
async def _end_giveaway(key: str, host_uid: int, amount: int, reply_msg):
    await asyncio.sleep(60)
    giveaway = _active_giveaways.pop(key, None)
    if not giveaway:
        return
    if giveaway["participants"]:
        winner_id = random.choice(giveaway["participants"])
        await _run(_add_coins, winner_id, amount)
        await reply_msg.reply(
            f"<blockquote>🎊 **ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ!**</blockquote>\n"
            f"<blockquote>🏆 ᴡɪɴɴᴇʀ: [{winner_id}](tg://user?id={winner_id})\n"
            f"💰 ᴘʀɪᴢᴇ: **{amount:,}** ᴄᴏɪɴs</blockquote>",
            disable_web_page_preview=True,
        )
    else:
        await _run(_add_coins, host_uid, amount)
        await reply_msg.reply("<blockquote>😔 ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ ᴡɪᴛʜ ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs. ᴄᴏɪɴs ʀᴇᴛᴜʀɴᴇᴅ.</blockquote>")
    try:
        await reply_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@Client.on_message(
    (filters.command(["lifegiveaway"]) | _alias_filter("ggiveaway", "Ggiveaway", "GGIVEAWAY"))
    & filters.group
)
async def giveaway_cmd(client, m: Message):
    args = _parse_args(m.text)
    try:
        amount = int(args[0])
        if amount < 100:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎁 ᴜsᴀɢᴇ: `/lifegiveaway <amount>` (min 100)</blockquote>")
    uid = m.from_user.id
    if await _run(_get_coins, uid) < amount:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    await _run(_remove_coins, uid, amount)
    key = f"{m.chat.id}_{m.id}"
    _active_giveaways[key] = {"amount": amount, "host": uid, "participants": []}
    sent = await m.reply(
        f"<blockquote>🎉 **ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!**</blockquote>\n"
        f"<blockquote>💰 ᴘʀɪᴢᴇ: **{amount:,}** ᴄᴏɪɴs\n"
        f"👤 ʜᴏsᴛ: {mention(m.from_user)}\n"
        f"⏰ ᴇɴᴅs ɪɴ **60 sᴇᴄᴏɴᴅs**</blockquote>\n\n"
        f"<blockquote>ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴇɴᴛᴇʀ!</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎁 ᴊᴏɪɴ ɢɪᴠᴇᴀᴡᴀʏ", callback_data=f"giveaway_join_{key}")
        ]]),
        disable_web_page_preview=True,
    )
    asyncio.create_task(_end_giveaway(key, uid, amount, sent))

@Client.on_callback_query(filters.regex(r"^giveaway_join_(.+)$"))
async def giveaway_join_cb(client, q: CallbackQuery):
    key = q.matches[0].group(1)
    ga  = _active_giveaways.get(key)
    if not ga:
        return await q.answer("⌛ ᴛʜɪs ɢɪᴠᴇᴀᴡᴀʏ ʜᴀs ᴀʟʀᴇᴀᴅʏ ᴇɴᴅᴇᴅ!", show_alert=True)
    uid = q.from_user.id
    if uid in ga["participants"]:
        return await q.answer("✅ ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ᴇɴᴛᴇʀᴇᴅ!", show_alert=True)
    ga["participants"].append(uid)
    await q.answer(f"✅ ᴇɴᴛᴇʀᴇᴅ! ᴛᴏᴛᴀʟ: {len(ga['participants'])}", show_alert=True)

# ────────────────────────────────────────────
#  SHOP — /lifeshop | sshop | Sshop | SSHOP
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifeshop"]) | _alias_filter("sshop", "Sshop", "SSHOP"))
    & filters.group
)
async def shop_cmd(client, m: Message):
    await m.reply("<blockquote>🛒 **ʟɪғᴇ ɢᴀᴍᴇs sʜᴏᴘ**\nᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ:</blockquote>", reply_markup=_shop_main_kb())

@Client.on_callback_query(filters.regex(r"^shop_main$"))
async def shop_main_cb(client, q: CallbackQuery):
    await q.message.edit("<blockquote>🛒 **ʟɪғᴇ ɢᴀᴍᴇs sʜᴏᴘ**\nᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ:</blockquote>", reply_markup=_shop_main_kb())

@Client.on_callback_query(filters.regex(r"^shop_armory$"))
async def shop_armory_cb(client, q: CallbackQuery):
    await q.message.edit("<blockquote>🔫 **ᴀʀᴍᴏʀʏ sʜᴏᴘ**</blockquote>\n<blockquote>ᴄʜᴏᴏsᴇ ᴀ ᴡᴇᴀᴘᴏɴ ᴏʀ ɢᴇᴀʀ:</blockquote>", reply_markup=_armory_kb())

@Client.on_callback_query(filters.regex(r"^shop_petshop$"))
async def shop_petshop_cb(client, q: CallbackQuery):
    await q.message.edit("<blockquote>🐾 **ᴘᴇᴛ sʜᴏᴘ**</blockquote>\n<blockquote>ᴄʜᴏᴏsᴇ ᴀ ᴘᴇᴛ:</blockquote>", reply_markup=_petshop_kb())

@Client.on_callback_query(filters.regex(r"^buy_gun_(.+)$"))
async def buy_gun_cb(client, q: CallbackQuery):
    key  = q.matches[0].group(1)
    item = GUNS.get(key)
    if not item:
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ ɪᴛᴇᴍ!", show_alert=True)
    uid, coins = q.from_user.id, await _run(_get_coins, q.from_user.id)
    if coins < item["price"]:
        return await q.answer(f"❌ ɴᴇᴇᴅ {item['price']:,}. ʏᴏᴜ ʜᴀᴠᴇ {coins:,}.", show_alert=True)
    await _run(_remove_coins, uid, item["price"])
    await _run(_update_user, uid, {"gun": key})
    await q.answer(f"✅ {key.capitalize()} equipped!", show_alert=True)
    await q.message.edit(
        f"<blockquote>✅ **ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!**</blockquote>\n"
        f"<blockquote>{item['emoji']} **{key.capitalize()}** ᴇǫᴜɪᴘᴘᴇᴅ!\n"
        f"⚔️ ᴅᴀᴍᴀɢᴇ: **+{item['damage']}**\n"
        f"💰 ᴘᴀɪᴅ: {item['price']:,} ᴄᴏɪɴs</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅ ʙᴀᴄᴋ ᴛᴏ ᴀʀᴍᴏʀʏ", callback_data="shop_armory")
        ]]),
    )

@Client.on_callback_query(filters.regex(r"^buy_armor_(.+)$"))
async def buy_armor_cb(client, q: CallbackQuery):
    key  = q.matches[0].group(1)
    item = ARMOR.get(key)
    if not item:
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ ɪᴛᴇᴍ!", show_alert=True)
    uid, coins = q.from_user.id, await _run(_get_coins, q.from_user.id)
    if coins < item["price"]:
        return await q.answer(f"❌ ɴᴇᴇᴅ {item['price']:,}. ʏᴏᴜ ʜᴀᴠᴇ {coins:,}.", show_alert=True)
    await _run(_remove_coins, uid, item["price"])
    await _run(_update_user, uid, {"armor": key})
    display = key.replace("_", " ").title()
    await q.answer(f"✅ {display} ᴇǫᴜɪᴘᴘᴇᴅ!", show_alert=True)
    await q.message.edit(
        f"<blockquote>✅ **ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!**</blockquote>\n"
        f"<blockquote>{item['emoji']} **{display}** ᴇǫᴜɪᴘᴘᴇᴅ!\n"
        f"🛡 ᴅᴇғᴇɴsᴇ: **+{item['defense']}**\n"
        f"💰 ᴘᴀɪᴅ: {item['price']:,} ᴄᴏɪɴs</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅ ʙᴀᴄᴋ ᴛᴏ ᴀʀᴍᴏʀʏ", callback_data="shop_armory")
        ]]),
    )

@Client.on_callback_query(filters.regex(r"^buy_pet_(.+)$"))
async def buy_pet_cb(client, q: CallbackQuery):
    key  = q.matches[0].group(1)
    item = PETS.get(key)
    if not item:
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ ᴘᴇᴛ!", show_alert=True)
    uid, coins = q.from_user.id, await _run(_get_coins, q.from_user.id)
    if coins < item["price"]:
        return await q.answer(f"❌ ɴᴇᴇᴅ {item['price']:,}. ʏᴏᴜ ʜᴀᴠᴇ {coins:,}.", show_alert=True)
    await _run(_remove_coins, uid, item["price"])
    await _run(_update_user, uid, {"pet": key})
    await q.answer(f"✅ {key.capitalize()} ɪs ʏᴏᴜʀ pet now!", show_alert=True)
    await q.message.edit(
        f"<blockquote>✅ **ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!**</blockquote>\n"
        f"<blockquote>{item['emoji']} **{key.capitalize()}** ɪs ɴᴏᴡ ʏᴏᴜʀ ᴘᴇᴛ!\n"
        f"💪 ʙᴀᴛᴛʟᴇ ᴘᴏᴡᴇʀ: **+{item['power']}**\n"
        f"💰 ᴘᴀɪᴅ: {item['price']:,} ᴄᴏɪɴs</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅ ʙᴀᴄᴋ ᴛᴏ ᴘᴇᴛ sʜᴏᴘ", callback_data="shop_petshop")
        ]]),
    )

@Client.on_callback_query(filters.regex(r"^shop_inventory$"))
async def shop_inventory_cb(client, q: CallbackQuery):
    uid = q.from_user.id
    u   = await _run(_get_user, uid)
    pet = PETS.get(u["pet"], {})
    gun = GUNS.get(u["gun"], {})
    arm = ARMOR.get(u["armor"], {})
    def row(emoji, label, stat_key, stat_val):
        return emoji + " **" + label + "**" + (f" (+{stat_val} {stat_key})" if stat_val else "")
    await q.message.edit(
        f"🎒 **ʏᴏᴜʀ ʟᴏᴀᴅᴏᴜᴛ**\n━━━━━━━━━━━━━━━━\n"
        + row(pet.get("emoji","❌"), u["pet"].capitalize() or "No Pet",   "power",   pet.get("power",0) if u["pet"] else 0) + "\n"
        + row(gun.get("emoji","❌"), u["gun"].capitalize() or "No Gun",   "damage",  gun.get("damage",0) if u["gun"] else 0) + "\n"
        + row(arm.get("emoji","❌"), u["armor"].replace("_"," ").title() or "No Armor", "defense", arm.get("defense",0) if u["armor"] else 0) + "\n"
        + f"━━━━━━━━━━━━━━━━\n⚔️ ᴛᴏᴛᴀʟ ʙᴀᴛᴛʟᴇ ᴘᴏᴡᴇʀ: **{calc_power(u)}**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_main")]]),
    )

# ────────────────────────────────────────────
#  INVENTORY — /lifeinventory | iinventory
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifeinventory"]) | _alias_filter("iinventory", "Iinventory", "IINVENTORY"))
    & filters.group
)
async def inventory_cmd(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    pet = PETS.get(u["pet"], {})
    gun = GUNS.get(u["gun"], {})
    arm = ARMOR.get(u["armor"], {})
    await m.reply(
        f"🎒 **ʏᴏᴜʀ ʟᴏᴀᴅᴏᴜᴛ**\n━━━━━━━━━━━━━━━━\n"
        f"🐾 ᴘᴇᴛ   : {pet.get('emoji','❌')} **{u['pet'].capitalize() or 'None'}**"
        + (f" (+{pet['power']} power)" if u["pet"] else "") + "\n"
        f"🔫 ɢᴜɴ   : {gun.get('emoji','❌')} **{u['gun'].capitalize() or 'None'}**"
        + (f" (+{gun['damage']} dmg)" if u["gun"] else "") + "\n"
        f"🛡 ᴀʀᴍᴏʀ : {arm.get('emoji','❌')} **{u['armor'].replace('_',' ').title() or 'None'}**"
        + (f" (+{arm['defense']} def)" if u["armor"] else "") + "\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚔️ ʙᴀᴛᴛʟᴇ ᴘᴏᴡᴇʀ : **{calc_power(u)}**\n"
        f"💼 ᴊᴏʙ          : {JOBS.get(u['job'],{}).get('emoji','❌')} "
        f"**{u['job'].capitalize() or 'None'}**"
    )

# ────────────────────────────────────────────
#  SETTINGS — /lifesettings | ssettings
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifesettings"]) | _alias_filter("ssettings", "Ssettings", "SSETTINGS"))
    & filters.group
)
async def settings_cmd(client, m: Message):
    if not await is_admin(client, m):
        return await m.reply("<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ!</blockquote>")
    cid        = m.chat.id
    cfg        = groups_col.find_one({"chat_id": cid}) or {}
    games_on   = cfg.get("games_enabled",  True)
    betting_on = cfg.get("betting_enabled", True)
    await m.reply(
        "<blockquote>⚙️ **ʟɪғᴇ ɢᴀᴍᴇs sᴇᴛᴛɪɴɢs**</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"🎮 ɢᴀᴍᴇs: {'✅ ᴏɴ' if games_on else '❌ ᴏғғ'}",
                callback_data=f"setting_games_{cid}",
            )],
            [InlineKeyboardButton(
                f"🎲 ʙᴇᴛᴛɪɴɢ: {'✅ ᴏɴ' if betting_on else '❌ ᴏғғ'}",
                callback_data=f"setting_betting_{cid}",
            )],
        ]),
    )

@Client.on_callback_query(filters.regex(r"^setting_(games|betting)_(-?\d+)$"))
async def settings_toggle_cb(client, q: CallbackQuery):
    setting = q.matches[0].group(1)
    chat_id = int(q.matches[0].group(2))
    db_key  = f"{setting}_enabled"
    current = (groups_col.find_one({"chat_id": chat_id}) or {}).get(db_key, True)
    new_val = not current
    groups_col.update_one({"chat_id": chat_id}, {"$set": {db_key: new_val}}, upsert=True)
    status = "✅ ᴇɴᴀʙʟᴇᴅ" if new_val else "❌ ᴅɪsᴀʙʟᴇᴅ"
    await q.answer(f"{status} {setting}!", show_alert=True)

# ────────────────────────────────────────────
#  ENABLE / DISABLE — admin only
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifeenable"]) | _alias_filter("eenable", "Eenable", "EENABLE"))
    & filters.group
)
async def enable_cmd(client, m: Message):
    if not await is_admin(client, m):
        return await m.reply("❌ ᴀᴅᴍɪɴs ᴏɴʟʏ!")
    groups_col.update_one({"chat_id": m.chat.id}, {"$set": {"games_enabled": True}}, upsert=True)
    await m.reply("<blockquote>✅ ʟɪғᴇ ɢᴀᴍᴇs **ᴇɴᴀʙʟᴇᴅ** ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ!</blockquote>")

@Client.on_message(
    (filters.command(["lifedisable"]) | _alias_filter("ddisable", "Ddisable", "DDISABLE"))
    & filters.group
)
async def disable_cmd(client, m: Message):
    if not await is_admin(client, m):
        return await m.reply("<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ!</blockquote>")
    groups_col.update_one({"chat_id": m.chat.id}, {"$set": {"games_enabled": False}}, upsert=True)
    await m.reply("<blockquote>❌ ʟɪғᴇ ɢᴀᴍᴇs **ᴅɪsᴀʙʟᴇᴅ** ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ!</blockquote>")

# ────────────────────────────────────────────
#  RESET — /lifereset | rreset (owner/sudo only)
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifereset"]) | _alias_filter("rreset", "Rreset", "RRESET"))
    & filters.group
)
async def reset_cmd(client, m: Message):
    uid = m.from_user.id
    if uid != OWNER_ID and uid not in SUDOERS:
        return await m.reply("<blockquote>❌ ᴏᴡɴᴇʀ ᴏɴʟʏ!</blockquote>")
    if not m.reply_to_message:
        return await m.reply("<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ᴡʜᴏsᴇ ᴅᴀᴛᴀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʀᴇsᴇᴛ.</blockquote>")
    tid = m.reply_to_message.from_user.id
    users_col.delete_one({"user_id": tid})
    cooldowns_col.delete_many({"user_id": tid})
    _get_user(tid)
    await m.reply(
        f"<blockquote>✅ ᴅᴀᴛᴀ ʀᴇsᴇᴛ ғᴏʀ [{tid}](tg://user?id={tid})</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  ADD COINS — /lifeaddcoins | aaddcoins (owner/sudo only)
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifeaddcoins"]) | _alias_filter("aaddcoins", "Aaddcoins", "AADDCOINS"))
    & filters.group
)
async def addcoins_cmd(client, m: Message):
    uid = m.from_user.id
    if uid != OWNER_ID and uid not in SUDOERS:
        return await m.reply("<blockquote>❌ ᴏᴡɴᴇʀ ᴏɴʟʏ!</blockquote>")
    if not m.reply_to_message:
        return await m.reply("<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ!</blockquote>")
    args = _parse_args(m.text)
    try:
        amount = int(args[0])
    except (ValueError, IndexError):
        return await m.reply("<blockquote>ᴜsᴀɢᴇ: `/lifeaddcoins <amount>`</blockquote>")
    tid = m.reply_to_message.from_user.id
    await _run(_add_coins, tid, amount)
    await m.reply(
        f"<blockquote>✅ ᴀᴅᴅᴇᴅ **{amount:,}** ᴄᴏɪɴs ᴛᴏ {mention(m.reply_to_message.from_user)}</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  DEPOSIT — /deposit | deposit | Deposit | DEPOSIT
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["deposit"]) | _alias_filter("deposit", "Deposit", "DEPOSIT"))
    & filters.group
)
async def deposit_cmd(client, m: Message):
    args = _parse_args(m.text)
    uid = m.from_user.id
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except:
        return await m.reply("<blockquote>💰 ᴜsᴀɢᴇ: `/deposit <ᴀᴍᴏᴜɴᴛ>`</blockquote>")
    coins = await _run(_get_coins, uid)
    if coins < amount:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴡᴀʟʟᴇᴛ ᴄᴏɪɴs!</blockquote>")
    user = await _run(_get_user, uid)
    await _run(_remove_coins, uid, amount)
    await _run(_update_user, uid, {"bank": user.get("bank", 0) + amount})
    await m.reply(f"<blockquote>🏦 ᴅᴇᴘᴏsɪᴛᴇᴅ **{amount:,}** ᴄᴏɪɴs ᴛᴏ ʙᴀɴᴋ</blockquote>")

# ────────────────────────────────────────────
#  WITHDRAW — /withdraw | withdraw | Withdraw | WITHDRAW
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["withdraw"]) | _alias_filter("withdraw", "Withdraw", "WITHDRAW"))
    & filters.group
)
async def withdraw_cmd(client, m: Message):
    args = _parse_args(m.text)
    uid = m.from_user.id
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except:
        return await m.reply("<blockquote>💰 ᴜsᴀɢᴇ: `/withdraw <ᴀᴍᴏᴜɴᴛ>`</blockquote>")
    user = await _run(_get_user, uid)
    bank = user.get("bank", 0)
    if bank < amount:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ!</blockquote>")
    await _run(_update_user, uid, {"bank": bank - amount})
    await _run(_add_coins, uid, amount)
    await m.reply(f"<blockquote>🏦 ᴡɪᴛʜᴅʀᴀᴡɴ **{amount:,}** ᴄᴏɪɴs</blockquote>")

# ────────────────────────────────────────────
#  BET — /bet | bbet | Bbet | BBET
# ────────────────────────────────────────────
@Client.on_message(
    (
        filters.command(["bet"])
        | _alias_filter("bbet", "Bbet", "BBET")
    )
    & filters.group
)
async def bet_cmd(client, m: Message):
    args = _parse_args(m.text)
    uid = m.from_user.id
    try:
        amount = int(args[0])
        if amount < 10:
            raise ValueError
    except:
        return await m.reply("<blockquote>🎲 ᴜsᴀɢᴇ: `/bet <ᴀᴍᴏᴜɴᴛ>` (ᴍɪɴ 10)</blockquote>")
    coins = await _run(_get_coins, uid)
    if coins < amount:
        return await m.reply("❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!")
    wait = await _run(_check_cooldown, uid, "bet", 10)
    if wait:
        return await m.reply(f"<blockquote>⏳ ᴄᴏᴏʟᴅᴏᴡɴ: {fmt_time(wait)}</blockquote>")
    user_data = await _run(_get_user, uid)
    streak = user_data.get("streak", 0)
    if random.randint(1, 100) <= 45:
        win = amount * 2
        await _run(_add_coins, uid, win)
        streak += 1
        await _run(_update_user, uid, {"streak": streak})
        caption = (
            f"<blockquote>🎰 **{m.from_user.first_name}** ʜᴀs ʙᴇᴛ {amount} ᴄᴏɪɴs</blockquote>\n"
            f"<blockquote>✅ ᴏʜ ʏᴇᴀʜ! ʜᴇ ᴄᴀᴍᴇ ʙᴀᴄᴋ ʜᴏᴍᴇ ᴡɪᴛʜ **{win}** ᴄᴏɪɴs\n"
            f"🏆 ᴄᴏɴsᴇᴄᴜᴛɪᴠᴇ ᴡɪɴs: {streak}</blockquote>"
        )
        await _send_life_image(m, "win", caption)
    else:
        await _run(_remove_coins, uid, amount)
        streak = 0
        await _run(_update_user, uid, {"streak": streak})
        caption = (
            f"<blockquote>🎰 **{m.from_user.first_name}** ʜᴀs ʙᴇᴛ {amount} ᴄᴏɪɴs</blockquote>\n"
            f"<blockquote>❌ ᴏʜ ɴᴏ! ʜᴇ ᴄᴀᴍᴇ ʙᴀᴄᴋ ʜᴏᴍᴇ ᴡɪᴛʜᴏᴜᴛ **{amount}** ᴄᴏɪɴs</blockquote>"
        )
        await _send_life_image(m, "loss", caption)

# ────────────────────────────────────────────
#  PAY — /pay | ppay | Ppay | PPAY
#  Reply to a user to pay them.
#  - With amount:    /pay 500   → pay 500 coins
#  - Without amount: /pay       → pay your FULL wallet balance
# ────────────────────────────────────────────
@Client.on_message(
    (
        filters.command(["pay"])
        | _alias_filter("ppay", "Ppay", "PPAY")
    )
    & filters.group
)
async def pay_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply(
            "<blockquote>💸 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴘᴀʏ ᴛʜᴇᴍ!\n"
            "ᴜsᴀɢᴇ: `/pay <amount>` ᴏʀ `/pay` (ᴘᴀʏs ᴀʟʟ)</blockquote>"
        )
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ᴘᴀʏ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    args = _parse_args(m.text)
    sender_coins = await _run(_get_coins, uid)
    if sender_coins <= 0:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ᴄᴏɪɴs ᴛᴏ ᴘᴀʏ!</blockquote>")
    # If no amount given, pay full balance
    if not args:
        amount = sender_coins
    else:
        try:
            amount = int(args[0])
            if amount <= 0:
                raise ValueError
        except:
            return await m.reply("<blockquote>❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ!</blockquote>")
    if sender_coins < amount:
        return await m.reply(
            f"<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!\n"
            f"ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: **{sender_coins:,}**</blockquote>"
        )
    await _run(_remove_coins, uid, amount)
    await _run(_add_coins, tid, amount)
    await m.reply(
        f"<blockquote>💸 **ᴘᴀɪᴅ!**</blockquote>\n"
        f"<blockquote>{mention(m.from_user)} ᴘᴀɪᴅ **{amount:,}** ᴄᴏɪɴs "
        f"ᴛᴏ {mention(m.reply_to_message.from_user)}!</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  LOAN — /loan | lloan | Lloan | LLOAN
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["loan"]) | _alias_filter("lloan", "Lloan", "LLOAN"))
    & filters.group
)
async def loan_cmd(client, m: Message):
    if not m.reply_to_message:
        return await m.reply(
            "<blockquote>🤲 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ʀᴇǫᴜᴇsᴛ ᴀ ʟᴏᴀɴ!\n"
            "ᴜsᴀɢᴇ: `/loan <amount>`</blockquote>"
        )
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ʀᴇǫᴜᴇsᴛ ᴀ ʟᴏᴀɴ ғʀᴏᴍ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    args = _parse_args(m.text)
    if not args:
        await m.reply(
            f"<blockquote>🤲 {mention(m.from_user)} ɪs ᴀsᴋɪɴɢ {mention(m.reply_to_message.from_user)} ғᴏʀ ᴀ ʟᴏᴀɴ!\n"
            f"ʜᴏᴡ ᴍᴜᴄʜ ᴅᴏ ʏᴏᴜ ɴᴇᴇᴅ? ʀᴇᴘʟʏ ᴡɪᴛʜ: `/loan <amount>`</blockquote>",
            disable_web_page_preview=True,
        )
        return
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except:
        return await m.reply("<blockquote>❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ! ᴜsᴀɢᴇ: `/loan <amount>`</blockquote>")
    lender_coins = await _run(_get_coins, tid)
    key = f"loan_{uid}_{tid}_{int(time.time())}"
    _pending_loans[key] = {"borrower": uid, "lender": tid, "amount": amount, "ts": time.time()}
    await m.reply(
        f"<blockquote>🤲 **ʟᴏᴀɴ ʀᴇǫᴜᴇsᴛ**</blockquote>\n"
        f"<blockquote>{mention(m.from_user)} ɪs ᴀsᴋɪɴɢ {mention(m.reply_to_message.from_user)} "
        f"ғᴏʀ **{amount:,}** ᴄᴏɪɴs\n"
        f"💰 ʟᴇɴᴅᴇʀ ʙᴀʟᴀɴᴄᴇ: **{lender_coins:,}**</blockquote>\n\n"
        f"<blockquote>{m.reply_to_message.from_user.first_name}, ᴅᴏ ʏᴏᴜ ᴀɢʀᴇᴇ?</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ ɢɪᴠᴇ ʟᴏᴀɴ",   callback_data=f"loan_accept_{key}"),
            InlineKeyboardButton("❌ ᴅᴇᴄʟɪɴᴇ",      callback_data=f"loan_decline_{key}"),
        ]]),
        disable_web_page_preview=True,
    )

@Client.on_callback_query(filters.regex(r"^loan_(accept|decline)_(.+)$"))
async def loan_response(client, q: CallbackQuery):
    action = q.matches[0].group(1)
    key    = q.matches[0].group(2)
    loan   = _pending_loans.get(key)
    if not loan:
        return await q.answer("⌛ ᴛʜɪs ʟᴏᴀɴ ʀᴇǫᴜᴇsᴛ ʜᴀs ᴇxᴘɪʀᴇᴅ!", show_alert=True)
    if q.from_user.id != loan["lender"]:
        return await q.answer("❌ ᴛʜɪs ʀᴇǫᴜᴇsᴛ ɪsɴ'ᴛ ғᴏʀ ʏᴏᴜ!", show_alert=True)
    if time.time() - loan["ts"] > 120:
        _pending_loans.pop(key, None)
        return await q.answer("⌛ ʟᴏᴀɴ ʀᴇǫᴜᴇsᴛ ᴇxᴘɪʀᴇᴅ (2ᴍɪɴ ᴛɪᴍᴇᴏᴜᴛ)!", show_alert=True)
    _pending_loans.pop(key, None)
    if action == "decline":
        return await q.message.edit("<blockquote>❌ ʟᴏᴀɴ ᴅᴇᴄʟɪɴᴇᴅ.</blockquote>")
    uid, tid, amount = loan["borrower"], loan["lender"], loan["amount"]
    lender_coins = await _run(_get_coins, tid)
    if lender_coins < amount:
        return await q.message.edit("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs ᴛᴏ ɢɪᴠᴇ ᴛʜɪs ʟᴏᴀɴ!</blockquote>")
    await _run(_remove_coins, tid, amount)
    await _run(_add_coins, uid, amount)
    await q.message.edit(
        f"<blockquote>✅ **ʟᴏᴀɴ ɢɪᴠᴇɴ!**</blockquote>\n"
        f"<blockquote>💸 [{tid}](tg://user?id={tid}) ʟᴇɴᴛ **{amount:,}** ᴄᴏɪɴs "
        f"ᴛᴏ [{uid}](tg://user?id={uid})</blockquote>",
        disable_web_page_preview=True,
    )

# ────────────────────────────────────────────
#  HELP — /lifehelp | hhelp | Hhelp | HHELP
# ────────────────────────────────────────────
@Client.on_message(
    (filters.command(["lifehelp"]) | _alias_filter("hhelp", "Hhelp", "HHELP"))
    & filters.group
)
async def help_cmd(client, m: Message):
    await m.reply(
        "<blockquote>🎮 **ʟɪғᴇ ɢᴀᴍᴇs — ғᴜʟʟ ᴄᴏᴍᴍᴀɴᴅ ʟɪsᴛ**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n"
        "<blockquote>**👤 ᴘʀᴏғɪʟᴇ & ᴇᴄᴏɴᴏᴍʏ**\n"
        "`/lifeprofile`   or  `pprofile`\n"
        "`/lifebalance`   or  `bbalance`\n"
        "`/lifedaily`     or  `ddaily`\n"
        "`/lifeinventory` or  `iinventory`\n"
        "`/lifetop [coins|xp|level]`  or  `ttop`</blockquote>\n"
        "<blockquote>**🏦 ʙᴀɴᴋ & ᴛʀᴀɴsғᴇʀ**\n"
        "`/deposit <amount>`\n"
        "`/withdraw <amount>`\n"
        "`/pay <amount>` *(reply)*   or  `ppay` / `Ppay` / `PPAY`\n"
        "`/pay` *(no amount = full balance)* *(reply)*\n"
        "`/loan <amount>` *(reply)*  or  `lloan`</blockquote>\n"
        "<blockquote>**🎲 ɢᴀᴍʙʟɪɴɢ**\n"
        "`/bet <amount>`  or  `bbet` / `Bbet` / `BBET`\n"
        "`/sslots <amount>`      or  `sslots`\n"
        "`/lifebowling <amount>` or  `bbowling`\n"
        "`/duel <amount>`        or  `dduel`</blockquote>\n"
        "<blockquote>**⚔️ ᴄᴏᴍʙᴀᴛ**\n"
        "`/lifefight` *(reply)* or  `ffight`\n"
        "`/steal` *(reply)*     or  `ssteal` / `Ssteal` / `SSTEAL`\n"
        "`/rob` *(reply)*       or  `rrob`   *(same as steal)*</blockquote>\n"
        "<blockquote>**💼 ᴊᴏʙs & ᴡᴏʀᴋ**\n"
        "`/lifejob`           or  `jjob`\n"
        "`/lifejob <name>`    or  `jjob <name>`\n"
        "`/lifework`          or  `wwork`\n"
        "`/lifeshop`          or  `sshop`</blockquote>\n"
        "<blockquote>**❤️ sᴏᴄɪᴀʟ & ғᴀᴍɪʟʏ**\n"
        "`/lifehug`     or `hhug`\n"
        "`/lifekiss`    or `kkiss`\n"
        "`/lifeslap`    or `sslap`\n"
        "`/lifelove`    or `llove`\n"
        "`/lifemarry`   or `mmarry`\n"
        "`/lifedivorce` or `ddivorce`\n"
        "`/lifeparent`  or `pparent`\n"
        "`/lifesibling` or `ssibling`</blockquote>\n"
        "<blockquote>**🎁 ɢɪᴠᴇᴀᴡᴀʏ**\n"
        "`/lifegiveaway <amount>` or `ggiveaway`</blockquote>\n"
        "<blockquote>**⚙️ ᴀᴅᴍɪɴ**\n"
        "`/lifesettings` or `ssettings`\n"
        "`/lifeenable`   or `eenable`\n"
        "`/lifedisable`  or `ddisable`\n"
        "`/lifereset`  *(reply)*  or `rreset`\n"
        "`/lifeaddcoins <n>` *(reply)* or `aaddcoins <n>`</blockquote>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 **ɴᴏ sʟᴀsʜ ɴᴇᴇᴅᴇᴅ** — ᴊᴜsᴛ ᴛʏᴘᴇ ᴛʜᴇ ᴀʟɪᴀs!\n"
        "   ᴇxᴀᴍᴘʟᴇ: `sshop` · `ttop` · `ssteal` · `bbet 500` · `ppay 1000`</blockquote>"
    )

# ─────────────────────────────────────────────────────────────────
#  MODULE META
# ─────────────────────────────────────────────────────────────────
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_75"
__help__     = """
🔻 /lifehelp      ➠ ꜰᴜʟʟ ʜᴇʟᴘ
🔻 /lifeprofile   ➠ ᴘʀᴏꜰɪʟᴇ
🔻 /lifedaily     ➠ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
🔻 /lifetop       ➠ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /lifeshop      ➠ ꜱʜᴏᴘ
🔻 /lifejob       ➠ ᴊᴏʙ
🔻 /lifework      ➠ ᴡᴏʀᴋ
🔻 /steal         ➠ ꜱᴛᴇᴀʟ (ꜱꜱᴛᴇᴀʟ / ꜱꜱᴛᴇᴀʟ / ꜱꜱᴛᴇᴀʟ)
🔻 /rob           ➠ ʀᴏʙ (ꜱᴀᴍᴇ ᴀꜱ ꜱᴛᴇᴀʟ)
🔻 /bet           ➠ ʙᴇᴛ (ʙʙᴇᴛ / Bʙᴇᴛ / ʙʙᴇᴛ)
🔻 /pay           ➠ ᴘᴀʏ (ᴘᴘᴀʏ / Pᴘᴀʏ / ᴘᴘᴀʏ)
🔻 /loan          ➠ ʟᴏᴀɴ (ʟʟᴏᴀɴ)
🔻 /duel          ➠ ᴅᴜᴇʟ
🔻 /sslots        ➠ ꜱʟᴏᴛꜱ
🔻 /lifebowling   ➠ ʙᴏᴡʟɪɴɢ
🔻 /lifegiveaway  ➠ ɢɪᴠᴇᴀᴡᴀʏ
🔻 /deposit       ➠ ᴅᴇᴘᴏꜱɪᴛ ᴄᴏɪɴꜱ ᴛᴏ ʙᴀɴᴋ
🔻 /withdraw      ➠ ᴡɪᴛʜᴅʀᴀᴡ ꜰʀᴏᴍ ʙᴀɴᴋ
"""

MOD_TYPE = "GAMES"
MOD_NAME = "LifeGame"
MOD_PRICE = "250"
