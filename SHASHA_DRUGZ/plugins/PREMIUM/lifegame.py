# ╔══════════════════════════════════════════════════════════════════════╗
# ║          LIFE GAMES MODULE — SHASHA_DRUGZ BOT                        ║
# ║          Single-file plugin · MongoDB persistent storage             ║
# ║                                                                      ║
# ║  FINAL FIX v3 — ROOT CAUSE SOLVED:                                  ║
# ║                                                                      ║
# ║  The no-slash commands (bbet, ppay, ssteal …) were being eaten       ║
# ║  by other modules that register catch-all / filters.text handlers   ║
# ║  in Pyrogram's default group 0.                                      ║
# ║                                                                      ║
# ║  FIX: every no-slash regex handler is registered in group=-1        ║
# ║  (higher priority than group 0).  Slash /command handlers stay       ║
# ║  in group 0 (default).  Both are combined per-command so only ONE   ║
# ║  function exists per feature.                                        ║
# ║                                                                      ║
# ║  Pattern used everywhere:                                            ║
# ║    @app.on_message(filters.command([...]))          # group 0        ║
# ║    @app.on_message(filters.regex(..., IGNORECASE),  # group -1       ║
# ║                    group=-1)                                         ║
# ║  Both decorators point to the SAME handler function.                 ║
# ║                                                                      ║
# ║  Cooldown system: FULLY REMOVED from all game commands.             ║
# ║  daily/work use lightweight in-memory dicts (no DB).                ║
# ╚══════════════════════════════════════════════════════════════════════╝

import os
import random
import asyncio
import time
import re
from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus

# ─────────────────────────────────────────────────────────────────
#  SHASHA_DRUGZ IMPORTS
# ─────────────────────────────────────────────────────────────────
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

_mongo     = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
_db        = _mongo["lifegames_db"]
users_col  = _db["users"]
groups_col = _db["groups"]
users_col.create_index("user_id", unique=True)
groups_col.create_index("chat_id", unique=True)

# ─────────────────────────────────────────────────────────────────
#  ASYNC WRAPPER — keeps sync pymongo off the event loop
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
    "hacker": {"emoji": "💻", "bonus_type": "steal_chance",  "bonus_val": 15, "salary": 3000000},
    "banker": {"emoji": "🏦", "bonus_type": "daily_bonus",   "bonus_val": 10, "salary": 2500000},
    "police": {"emoji": "👮", "bonus_type": "protection",    "bonus_val": 20, "salary": 2000000},
    "thief":  {"emoji": "🕵️", "bonus_type": "steal_chance",  "bonus_val": 20, "salary": 1800000},
    "trader": {"emoji": "📈", "bonus_type": "shop_discount", "bonus_val": 10, "salary": 3500000},
}
PETS = {
    "dog":    {"emoji": "🐶", "price": 100_000_000,  "power": 5},
    "cat":    {"emoji": "🐱", "price": 120_000_000,  "power": 7},
    "wolf":   {"emoji": "🐺", "price": 250_000_000,  "power": 15},
    "fox":    {"emoji": "🦊", "price": 300_000_000,  "power": 18},
    "dragon": {"emoji": "🐉", "price": 1_000_000_000,"power": 40},
}
GUNS = {
    "pistol":  {"emoji": "🔫", "price": 150_000_000, "damage": 10},
    "shotgun": {"emoji": "🔫", "price": 300_000_000, "damage": 20},
    "rifle":   {"emoji": "🎯", "price": 500_000_000, "damage": 30},
    "sniper":  {"emoji": "🎯", "price": 800_000_000, "damage": 45},
}
ARMOR = {
    "helmet":        {"emoji": "⛑",  "price":  80_000_000, "defense":  8},
    "vest":          {"emoji": "🦺", "price": 150_000_000, "defense": 15},
    "shield":        {"emoji": "🛡",  "price": 250_000_000, "defense": 25},
    "tactical_suit": {"emoji": "🥷", "price": 500_000_000, "defense": 40},
}
SOCIAL_EMOJIS = {"hug": "🤗", "kiss": "😘", "slap": "👋", "love": "❤️"}

LIFE_ASSETS = {
    "win":  "SHASHA_DRUGZ/assets/shasha/win.jpeg",
    "loss": "SHASHA_DRUGZ/assets/shasha/loss.jpg",
}

# ─────────────────────────────────────────────────────────────────
#  DATABASE HELPERS
# ─────────────────────────────────────────────────────────────────
_DEFAULT_USER = {
    "coins": 500, "xp": 0, "level": 1,
    "partner": 0, "parent": 0, "sibling": 0,
    "job": "", "pet": "", "gun": "", "armor": "",
    "jail_until": 0, "bank": 0, "streak": 0,
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
    pet_pw   = PETS.get(user.get("pet",   ""), {}).get("power",   0)
    gun_dmg  = GUNS.get(user.get("gun",   ""), {}).get("damage",  0)
    armor_df = ARMOR.get(user.get("armor",""), {}).get("defense", 0)
    luck     = random.randint(1, 30)
    return base + pet_pw + gun_dmg + armor_df + luck

def _parse_args(text: str) -> list:
    """Return tokens after the first word. Works for /cmd and plain alias."""
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
#  INLINE KEYBOARD BUILDERS
# ─────────────────────────────────────────────────────────────────
def _shop_main_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔫 ᴀʀᴍᴏʀʏ",    callback_data="shop_armory"),
            InlineKeyboardButton("🐾 ᴘᴇᴛ sʜᴏᴘ",  callback_data="shop_petshop"),
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
#  IN-MEMORY STATE
# ─────────────────────────────────────────────────────────────────
_pending_duels:    dict = {}
_active_giveaways: dict = {}
_daily_cooldowns:  dict = {}   # uid -> unix ts of last claim
_work_cooldowns:   dict = {}   # uid -> unix ts of last work

# ─────────────────────────────────────────────────────────────────
#  _rf() — shorthand for no-slash regex filter (always group filters.group)
# ─────────────────────────────────────────────────────────────────
def _rf(pattern: str):
    return filters.regex(pattern, re.IGNORECASE) & filters.group


# ═══════════════════════════════════════════════════════════════════
#
#  HANDLER REGISTRATION PATTERN (used for EVERY command):
#
#    async def _xxx_handler(client, m): ...   ← single implementation
#
#    @app.on_message(filters.command(["..."]) & filters.group)
#    async def xxx_slash(client, m):           ← /slash  (group 0)
#        await _xxx_handler(client, m)
#
#    @app.on_message(_rf(r"^(alias|word)\b"), group=-1)
#    async def xxx_noslash(client, m):         ← no-slash (group -1, higher priority)
#        await _xxx_handler(client, m)
#
#  group=-1 fires BEFORE group 0, so other-module catch-alls never
#  steal our no-slash messages.
#
# ═══════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────
#  PROFILE
# ──────────────────────────────────────────────────────────────────
async def _profile_handler(client, m: Message):
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

@app.on_message(filters.command(["lifeprofile"]) & filters.group)
async def profile_slash(client, m: Message):
    await _profile_handler(client, m)

@app.on_message(_rf(r"^(pprofile|profile)\b"), group=-1)
async def profile_noslash(client, m: Message):
    await _profile_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  BALANCE
# ──────────────────────────────────────────────────────────────────
async def _balance_handler(client, m: Message):
    coins = await _run(_get_coins, m.from_user.id)
    await m.reply(f"<blockquote>💰 ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: **{coins:,}** ᴄᴏɪɴs</blockquote>")

@app.on_message(filters.command(["lifebalance"]) & filters.group)
async def balance_slash(client, m: Message):
    await _balance_handler(client, m)

@app.on_message(_rf(r"^(bbalance|balance)\b"), group=-1)
async def balance_noslash(client, m: Message):
    await _balance_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  DAILY  (24h in-memory cooldown — kept for game balance)
# ──────────────────────────────────────────────────────────────────
async def _daily_handler(client, m: Message):
    uid  = m.from_user.id
    now  = int(time.time())
    last = _daily_cooldowns.get(uid, 0)
    wait = 86400 - (now - last)
    if wait > 0:
        return await m.reply(f"<blockquote>⏳ ᴄᴏᴍᴇ ʙᴀᴄᴋ ɪɴ **{fmt_time(wait)}**</blockquote>")
    _daily_cooldowns[uid] = now
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

@app.on_message(filters.command(["lifedaily"]) & filters.group)
async def daily_slash(client, m: Message):
    await _daily_handler(client, m)

@app.on_message(_rf(r"^(ddaily|daily)\b"), group=-1)
async def daily_noslash(client, m: Message):
    await _daily_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  LEADERBOARD
# ──────────────────────────────────────────────────────────────────
async def _top_handler(client, m: Message):
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
        lines.append(
            f"<blockquote>{badge} [{doc['user_id']}](tg://user?id={doc['user_id']}) — {val:,}</blockquote>"
        )
    await m.reply(
        f"<blockquote>🏆 **ᴛᴏᴘ ᴘʟᴀʏᴇʀs — {modes[mode]}**</blockquote>\n"
        f"<blockquote>━━━━━━━━━━━━━━━━━━━━</blockquote>\n" + "\n".join(lines),
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["lifetop"]) & filters.group)
async def top_slash(client, m: Message):
    await _top_handler(client, m)

@app.on_message(_rf(r"^(ttop|top)\b"), group=-1)
async def top_noslash(client, m: Message):
    await _top_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  SOCIAL ACTIONS
# ──────────────────────────────────────────────────────────────────
async def _social(m: Message, action: str):
    if not m.reply_to_message:
        return await m.reply(f"<blockquote>ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ {action} ᴛʜᴇᴍ!</blockquote>")
    target = m.reply_to_message.from_user
    emoji  = SOCIAL_EMOJIS.get(action, "✨")
    await m.reply(
        f"<blockquote>{emoji} **{mention(m.from_user)}** {action}ed **{mention(target)}**!</blockquote>",
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["lifehug"]) & filters.group)
async def hug_slash(client, m): await _social(m, "hug")
@app.on_message(_rf(r"^(hhug|hug)\b"), group=-1)
async def hug_noslash(client, m): await _social(m, "hug")

@app.on_message(filters.command(["lifekiss"]) & filters.group)
async def kiss_slash(client, m): await _social(m, "kiss")
@app.on_message(_rf(r"^(kkiss|kiss)\b"), group=-1)
async def kiss_noslash(client, m): await _social(m, "kiss")

@app.on_message(filters.command(["lifeslap"]) & filters.group)
async def slap_slash(client, m): await _social(m, "slap")
@app.on_message(_rf(r"^(sslap|slap)\b"), group=-1)
async def slap_noslash(client, m): await _social(m, "slap")

@app.on_message(filters.command(["lifelove"]) & filters.group)
async def love_slash(client, m): await _social(m, "love")
@app.on_message(_rf(r"^(llove|love)\b"), group=-1)
async def love_noslash(client, m): await _social(m, "love")


# ──────────────────────────────────────────────────────────────────
#  MARRY
# ──────────────────────────────────────────────────────────────────
async def _marry_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("💍 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴘʀᴏᴘᴏsᴇ!")
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴍᴀʀʀʏ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    u1 = await _run(_get_user, uid)
    u2 = await _run(_get_user, tid)
    if u1["partner"]:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ᴍᴀʀʀɪᴇᴅ!</blockquote>")
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

@app.on_message(filters.command(["lifemarry"]) & filters.group)
async def marry_slash(client, m): await _marry_handler(client, m)
@app.on_message(_rf(r"^(mmarry|marry)\b"), group=-1)
async def marry_noslash(client, m): await _marry_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  DIVORCE
# ──────────────────────────────────────────────────────────────────
async def _divorce_handler(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    if not u["partner"]:
        return await m.reply("<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴍᴀʀʀɪᴇᴅ!</blockquote>")
    await _run(_update_user, u["partner"], {"partner": 0})
    await _run(_update_user, uid, {"partner": 0})
    await m.reply("<blockquote>💔 ʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴅɪᴠᴏʀᴄᴇᴅ.</blockquote>")

@app.on_message(filters.command(["lifedivorce"]) & filters.group)
async def divorce_slash(client, m): await _divorce_handler(client, m)
@app.on_message(_rf(r"^(ddivorce|divorce)\b"), group=-1)
async def divorce_noslash(client, m): await _divorce_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  PARENT
# ──────────────────────────────────────────────────────────────────
async def _parent_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴀᴅᴏᴘᴛ ᴛʜᴇᴍ!")
    tid = m.reply_to_message.from_user.id
    await _run(_update_user, tid, {"parent": m.from_user.id})
    await m.reply(
        f"<blockquote>👨‍👧 **{mention(m.from_user)}** ʜᴀs ᴀᴅᴏᴘᴛᴇᴅ "
        f"**{mention(m.reply_to_message.from_user)}**!</blockquote>",
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["lifeparent"]) & filters.group)
async def parent_slash(client, m): await _parent_handler(client, m)
@app.on_message(_rf(r"^(pparent|parent)\b"), group=-1)
async def parent_noslash(client, m): await _parent_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  SIBLING
# ──────────────────────────────────────────────────────────────────
async def _sibling_handler(client, m: Message):
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

@app.on_message(filters.command(["lifesibling"]) & filters.group)
async def sibling_slash(client, m): await _sibling_handler(client, m)
@app.on_message(_rf(r"^(ssibling|sibling)\b"), group=-1)
async def sibling_noslash(client, m): await _sibling_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  STEAL
# ──────────────────────────────────────────────────────────────────
async def _steal_handler(client, m: Message):
    target_user = m.reply_to_message.from_user if m.reply_to_message else None
    if not target_user:
        return await m.reply("<blockquote>🕵️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ sᴛᴇᴀʟ ғʀᴏᴍ!</blockquote>")
    uid, tid = m.from_user.id, target_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ sᴛᴇᴀʟ ғʀᴏᴍ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    u   = await _run(_get_user, uid)
    now = int(time.time())
    if u.get("jail_until", 0) > now:
        return await m.reply(
            f"<blockquote>🚔 ɪɴ ᴊᴀɪʟ! ʀᴇʟᴇᴀsᴇ ɪɴ **{fmt_time(u['jail_until'] - now)}**</blockquote>"
        )
    victim_coins = await _run(_get_coins, tid)
    if victim_coins < 100:
        return await m.reply("<blockquote>❌ ᴛᴀʀɢᴇᴛ ᴛᴏᴏ ᴘᴏᴏʀ (< 100 ᴄᴏɪɴs)!</blockquote>")
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
        fine = random.randint(100, 300)
        await _run(_remove_coins, uid, fine)
        await _run(_update_user, uid, {"jail_until": now + 600})
        await m.reply(
            f"<blockquote>🚨 **ᴄᴀᴜɢʜᴛ!**</blockquote>\n"
            f"<blockquote>ғɪɴᴇ: **{fine}** ᴄᴏɪɴs\n"
            f"🚔 ᴊᴀɪʟᴇᴅ **10 ᴍɪɴᴜᴛᴇs**</blockquote>"
        )

@app.on_message(filters.command(["steal"]) & filters.group)
async def steal_slash(client, m): await _steal_handler(client, m)
@app.on_message(_rf(r"^(ssteal|steal)\b"), group=-1)
async def steal_noslash(client, m): await _steal_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  DUEL
# ──────────────────────────────────────────────────────────────────
async def _duel_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply(
            "<blockquote>⚔️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴄʜᴀʟʟᴇɴɢᴇ!\n"
            "ᴜsᴀɢᴇ: duel &lt;amount&gt;</blockquote>"
        )
    args = _parse_args(m.text)
    try:
        bet = int(args[0]) if args else 0
        if bet < 50:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>⚔️ ᴜsᴀɢᴇ: `duel <amount>` (ᴍɪɴ 50)</blockquote>")
    uid, tid = m.from_user.id, m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ᴅᴜᴇʟ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    if await _run(_get_coins, uid) < bet:
        return await m.reply("❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!")
    if await _run(_get_coins, tid) < bet:
        return await m.reply("<blockquote>❌ ᴏᴘᴘᴏɴᴇɴᴛ ʜᴀs ɴᴏ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
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

@app.on_message(filters.command(["duel"]) & filters.group)
async def duel_slash(client, m): await _duel_handler(client, m)
@app.on_message(_rf(r"^(dduel|duel)\b"), group=-1)
async def duel_noslash(client, m): await _duel_handler(client, m)

@app.on_callback_query(filters.regex(r"^duel_(accept|decline)_(.+)$"))
async def duel_response(client, q: CallbackQuery):
    action = q.matches[0].group(1)
    key    = q.matches[0].group(2)
    duel   = _pending_duels.get(key)
    if not duel:
        return await q.answer("⌛ ᴅᴜᴇʟ ᴇxᴘɪʀᴇᴅ!", show_alert=True)
    if q.from_user.id != duel["target"]:
        return await q.answer("❌ ɴᴏᴛ ʏᴏᴜʀ ᴄʜᴀʟʟᴇɴɢᴇ!", show_alert=True)
    if time.time() - duel["ts"] > 90:
        _pending_duels.pop(key, None)
        return await q.answer("⌛ ᴅᴜᴇʟ ᴇxᴘɪʀᴇᴅ (90s)!", show_alert=True)
    _pending_duels.pop(key, None)
    if action == "decline":
        return await q.message.edit("❌ ᴅᴜᴇʟ ᴅᴇᴄʟɪɴᴇᴅ.")
    uid1, uid2, bet = duel["challenger"], duel["target"], duel["bet"]
    u1, u2 = await _run(_get_user, uid1), await _run(_get_user, uid2)
    p1, p2 = calc_power(u1), calc_power(u2)
    if p1 >= p2:
        winner_id, loser_id, wp, lp = uid1, uid2, p1, p2
    else:
        winner_id, loser_id, wp, lp = uid2, uid1, p2, p1
    await _run(_add_coins, winner_id, bet)
    await _run(_remove_coins, loser_id, bet)
    await _run(_add_xp, winner_id, 25)
    try:
        w = await client.get_chat_member(q.message.chat.id, winner_id)
        winner_name = w.user.first_name
    except Exception:
        winner_name = str(winner_id)
    await q.message.edit(
        f"<blockquote>⚔️ **ᴅᴜᴇʟ ʀᴇsᴜʟᴛ!**</blockquote>\n"
        f"<blockquote>🏆 [{winner_name}](tg://user?id={winner_id})\n"
        f"💪 ᴘᴏᴡᴇʀ: **{wp}** vs {lp}\n"
        f"💰 ᴘʀɪᴢᴇ: **{bet:,}** ᴄᴏɪɴs · ⭐ +25 xᴘ</blockquote>",
        disable_web_page_preview=True,
    )


# ──────────────────────────────────────────────────────────────────
#  BOWLING
# ──────────────────────────────────────────────────────────────────
async def _bowling_handler(client, m: Message):
    args = _parse_args(m.text)
    try:
        bet = int(args[0])
        if bet < 10:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎳 ᴜsᴀɢᴇ: `bowling <amount>` (ᴍɪɴ 10)</blockquote>")
    uid = m.from_user.id
    if await _run(_get_coins, uid) < bet:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    dice_msg = await m.reply_dice(emoji="🎳")
    score    = dice_msg.dice.value
    await asyncio.sleep(3)
    if score == 6:
        prize = bet * 3
        await _run(_add_coins, uid, prize)
        result = f"<blockquote>🎳 **sᴛʀɪᴋᴇ!**\n💰 ᴡᴏɴ **{prize:,}** ᴄᴏɪɴs 🎉</blockquote>"
    elif score >= 4:
        prize = int(bet * 1.5)
        await _run(_add_coins, uid, prize - bet)
        result = f"<blockquote>🎳 sᴄᴏʀᴇ: **{score}/6**\n💰 ᴡᴏɴ **{prize:,}** ᴄᴏɪɴs</blockquote>"
    else:
        await _run(_remove_coins, uid, bet)
        result = f"<blockquote>🎳 sᴄᴏʀᴇ: **{score}/6** — ɢᴜᴛᴛᴇʀʙᴀʟʟ!\n💸 ʟᴏsᴛ **{bet:,}** ᴄᴏɪɴs</blockquote>"
    await m.reply(result)

@app.on_message(filters.command(["lifebowling"]) & filters.group)
async def bowling_slash(client, m): await _bowling_handler(client, m)
@app.on_message(_rf(r"^(bbowling|bowling)\b"), group=-1)
async def bowling_noslash(client, m): await _bowling_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  SLOTS
# ──────────────────────────────────────────────────────────────────
async def _slots_handler(client, m: Message):
    args = _parse_args(m.text)
    try:
        bet = int(args[0])
        if bet < 10:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎰 ᴜsᴀɢᴇ: `slots <amount>` (ᴍɪɴ 10)</blockquote>")
    uid = m.from_user.id
    if await _run(_get_coins, uid) < bet:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    msg = await m.reply(f"<blockquote>🎰 sᴘɪɴɴɪɴɢ...\n💰 ʙᴇᴛ: **{bet:,}**</blockquote>")
    for _ in range(4):
        r = [random.choice(SLOT_ICONS) for _ in range(3)]
        await msg.edit(
            f"<blockquote>🎰 **ʟɪғᴇ sʟᴏᴛs**\n\n"
            f"┃ {r[0]} ┃ {r[1]} ┃ {r[2]} ┃\n\n"
            f"💰 Bet: {bet:,}\n🔄 sᴘɪɴɴɪɴɢ...</blockquote>"
        )
        await asyncio.sleep(0.7)
    r    = [random.choice(SLOT_ICONS) for _ in range(3)]
    body = f"<blockquote>🎰 **ʟɪғᴇ sʟᴏᴛs**\n\n┃ {r[0]} ┃ {r[1]} ┃ {r[2]} ┃</blockquote>\n\n"
    if r[0] == r[1] == r[2]:
        prize = bet * 5
        await _run(_add_coins, uid, prize)
        await _run(_add_xp, uid, 30)
        body += f"<blockquote>🎉 **ᴊᴀᴄᴋᴘᴏᴛ!** ᴛʀɪᴘʟᴇ {r[0]}\n💰 ᴡᴏɴ **{prize:,}** · ⭐ +30 xᴘ</blockquote>"
    elif r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
        prize = int(bet * 1.5)
        await _run(_add_coins, uid, prize - bet)
        await _run(_add_xp, uid, 10)
        body += f"<blockquote>✨ **ᴛᴡᴏ ᴏғ ᴀ ᴋɪɴᴅ!**\n💰 ᴡᴏɴ **{prize:,}** · ⭐ +10 xᴘ</blockquote>"
    else:
        await _run(_remove_coins, uid, bet)
        body += f"<blockquote>💀 **ɴᴏ ᴍᴀᴛᴄʜ!**\n💸 ʟᴏsᴛ **{bet:,}** ᴄᴏɪɴs</blockquote>"
    await msg.edit(body)

@app.on_message(filters.command(["sslots", "slots"]) & filters.group)
async def slots_slash(client, m): await _slots_handler(client, m)
@app.on_message(_rf(r"^(sslots|slots)\b"), group=-1)
async def slots_noslash(client, m): await _slots_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  JOB
# ──────────────────────────────────────────────────────────────────
async def _job_handler(client, m: Message):
    uid  = m.from_user.id
    u    = await _run(_get_user, uid)
    args = _parse_args(m.text)
    if not args:
        lines = [
            f"{ji['emoji']} **{name.capitalize()}** — {ji['salary']:,} ᴄᴏɪɴs/ᴅᴀʏ"
            for name, ji in JOBS.items()
        ]
        current = ""
        if u["job"]:
            ji = JOBS[u["job"]]
            current = f"\n\n<blockquote>✅ ᴄᴜʀʀᴇɴᴛ: {ji['emoji']} **{u['job'].capitalize()}**</blockquote>"
        return await m.reply(
            "<blockquote>💼 **ᴀᴠᴀɪʟᴀʙʟᴇ ᴊᴏʙs**</blockquote>\n"
            "<blockquote>━━━━━━━━━━━━━━\n"
            + "\n".join(lines)
            + "\n\n📝 ᴜsᴇ: `job <ɴᴀᴍᴇ>`</blockquote>"
            + current
        )
    job_name = args[0].lower()
    if job_name not in JOBS:
        return await m.reply("<blockquote>❌ ᴜɴᴋɴᴏᴡɴ ᴊᴏʙ.</blockquote>")
    await _run(_update_user, uid, {"job": job_name})
    ji = JOBS[job_name]
    await m.reply(
        f"<blockquote>✅ ʏᴏᴜ ᴀʀᴇ ɴᴏᴡ ᴀ **{job_name.capitalize()}** {ji['emoji']}</blockquote>\n"
        f"<blockquote>💰 sᴀʟᴀʀʏ: **{ji['salary']:,}** / 4ʜ\n"
        f"🎯 ʙᴏɴᴜs: +{ji['bonus_val']}% {ji['bonus_type'].replace('_', ' ')}</blockquote>"
    )

@app.on_message(filters.command(["lifejob"]) & filters.group)
async def job_slash(client, m): await _job_handler(client, m)
@app.on_message(_rf(r"^(jjob|job)\b"), group=-1)
async def job_noslash(client, m): await _job_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  WORK  (in-memory 4h cooldown)
# ──────────────────────────────────────────────────────────────────
async def _work_handler(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    if not u["job"]:
        return await m.reply("<blockquote>❌ ɴᴏ ᴊᴏʙ! ᴜsᴇ `job` ᴛᴏ ᴘɪᴄᴋ ᴏɴᴇ.</blockquote>")
    now  = int(time.time())
    last = _work_cooldowns.get(uid, 0)
    wait = 14400 - (now - last)
    if wait > 0:
        return await m.reply(f"<blockquote>⏳ ᴡᴏʀᴋ ᴄᴏᴏʟᴅᴏᴡɴ: **{fmt_time(wait)}**</blockquote>")
    _work_cooldowns[uid] = now
    ji     = JOBS[u["job"]]
    salary = max(50, ji["salary"] + random.randint(-50, 100))
    await _run(_add_coins, uid, salary)
    await _run(_add_xp, uid, 20)
    await m.reply(
        f"<blockquote>💼 {ji['emoji']} ᴡᴏʀᴋᴇᴅ ᴀs **{u['job'].capitalize()}**</blockquote>\n"
        f"<blockquote>💰 ᴇᴀʀɴᴇᴅ: **{salary:,}** · ⭐ +20 xᴘ</blockquote>"
    )

@app.on_message(filters.command(["lifework"]) & filters.group)
async def work_slash(client, m): await _work_handler(client, m)
@app.on_message(_rf(r"^(wwork|work)\b"), group=-1)
async def work_noslash(client, m): await _work_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  FIGHT
# ──────────────────────────────────────────────────────────────────
async def _fight_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("<blockquote>⚔️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ғɪɢʜᴛ!</blockquote>")
    uid, tid = m.from_user.id, m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ғɪɢʜᴛ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    u1, u2 = await _run(_get_user, uid), await _run(_get_user, tid)
    p1, p2 = calc_power(u1), calc_power(u2)
    msg = await m.reply(
        f"<blockquote>⚔️ **ғɪɢʜᴛ!**\n"
        f"🥊 {mention(m.from_user)} ({p1})\nᴠs\n"
        f"🥊 {mention(m.reply_to_message.from_user)} ({p2})\n"
        f"⚡ ᴄᴀʟᴄᴜʟᴀᴛɪɴɢ...</blockquote>",
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
        f"<blockquote>⚔️ **ʀᴇsᴜʟᴛ**\n"
        f"🏆 **{winner_name}** ᴡɪɴs!\n"
        f"💪 {p1} ᴠs {p2}\n"
        f"💰 **{reward:,}** coins · ⭐ +20 xᴘ</blockquote>"
    )

@app.on_message(filters.command(["lifefight"]) & filters.group)
async def fight_slash(client, m): await _fight_handler(client, m)
@app.on_message(_rf(r"^(ffight|fight)\b"), group=-1)
async def fight_noslash(client, m): await _fight_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  GIVEAWAY
# ──────────────────────────────────────────────────────────────────
async def _end_giveaway(key: str, host_uid: int, amount: int, reply_msg):
    await asyncio.sleep(60)
    giveaway = _active_giveaways.pop(key, None)
    if not giveaway:
        return
    if giveaway["participants"]:
        winner_id = random.choice(giveaway["participants"])
        await _run(_add_coins, winner_id, amount)
        await reply_msg.reply(
            f"<blockquote>🎊 **ɢɪᴠᴇᴀᴡᴀʏ ᴇɴᴅᴇᴅ!**\n"
            f"🏆 [{winner_id}](tg://user?id={winner_id})\n"
            f"💰 **{amount:,}** ᴄᴏɪɴs</blockquote>",
            disable_web_page_preview=True,
        )
    else:
        await _run(_add_coins, host_uid, amount)
        await reply_msg.reply("<blockquote>😔 ɴᴏ ᴘᴀʀᴛɪᴄɪᴘᴀɴᴛs. ᴄᴏɪɴs ʀᴇᴛᴜʀɴᴇᴅ.</blockquote>")
    try:
        await reply_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

async def _giveaway_handler(client, m: Message):
    args = _parse_args(m.text)
    try:
        amount = int(args[0])
        if amount < 100:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎁 ᴜsᴀɢᴇ: `giveaway <amount>` (ᴍɪɴ 100)</blockquote>")
    uid = m.from_user.id
    if await _run(_get_coins, uid) < amount:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    await _run(_remove_coins, uid, amount)
    key = f"{m.chat.id}_{m.id}"
    _active_giveaways[key] = {"amount": amount, "host": uid, "participants": []}
    sent = await m.reply(
        f"<blockquote>🎉 **ɢɪᴠᴇᴀᴡᴀʏ sᴛᴀʀᴛᴇᴅ!**\n"
        f"💰 ᴘʀɪᴢᴇ: **{amount:,}** ᴄᴏɪɴs\n"
        f"👤 ʜᴏsᴛ: {mention(m.from_user)}\n"
        f"⏰ **60 sᴇᴄᴏɴᴅs**</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎁 ᴊᴏɪɴ", callback_data=f"giveaway_join_{key}")
        ]]),
        disable_web_page_preview=True,
    )
    asyncio.create_task(_end_giveaway(key, uid, amount, sent))

@app.on_message(filters.command(["lifegiveaway"]) & filters.group)
async def giveaway_slash(client, m): await _giveaway_handler(client, m)
@app.on_message(_rf(r"^(ggiveaway|giveaway)\b"), group=-1)
async def giveaway_noslash(client, m): await _giveaway_handler(client, m)

@app.on_callback_query(filters.regex(r"^giveaway_join_(.+)$"))
async def giveaway_join_cb(client, q: CallbackQuery):
    key = q.matches[0].group(1)
    ga  = _active_giveaways.get(key)
    if not ga:
        return await q.answer("⌛ ᴇɴᴅᴇᴅ!", show_alert=True)
    uid = q.from_user.id
    if uid in ga["participants"]:
        return await q.answer("✅ ᴀʟʀᴇᴀᴅʏ ᴇɴᴛᴇʀᴇᴅ!", show_alert=True)
    ga["participants"].append(uid)
    await q.answer(f"✅ ᴇɴᴛᴇʀᴇᴅ! ᴛᴏᴛᴀʟ: {len(ga['participants'])}", show_alert=True)


# ──────────────────────────────────────────────────────────────────
#  SHOP + CALLBACKS
# ──────────────────────────────────────────────────────────────────
async def _shop_handler(client, m: Message):
    await m.reply(
        "<blockquote>🛒 **ʟɪғᴇ sʜᴏᴘ**\nᴄʜᴏᴏsᴇ:</blockquote>",
        reply_markup=_shop_main_kb(),
    )

@app.on_message(filters.command(["lifeshop"]) & filters.group)
async def shop_slash(client, m): await _shop_handler(client, m)
@app.on_message(_rf(r"^(sshop|shop)\b"), group=-1)
async def shop_noslash(client, m): await _shop_handler(client, m)

@app.on_callback_query(filters.regex(r"^shop_main$"))
async def shop_main_cb(client, q: CallbackQuery):
    await q.message.edit("<blockquote>🛒 **ʟɪғᴇ sʜᴏᴘ**\nᴄʜᴏᴏsᴇ:</blockquote>", reply_markup=_shop_main_kb())

@app.on_callback_query(filters.regex(r"^shop_armory$"))
async def shop_armory_cb(client, q: CallbackQuery):
    await q.message.edit("<blockquote>🔫 **ᴀʀᴍᴏʀʏ**</blockquote>", reply_markup=_armory_kb())

@app.on_callback_query(filters.regex(r"^shop_petshop$"))
async def shop_petshop_cb(client, q: CallbackQuery):
    await q.message.edit("<blockquote>🐾 **ᴘᴇᴛ sʜᴏᴘ**</blockquote>", reply_markup=_petshop_kb())

@app.on_callback_query(filters.regex(r"^buy_gun_(.+)$"))
async def buy_gun_cb(client, q: CallbackQuery):
    key  = q.matches[0].group(1)
    item = GUNS.get(key)
    if not item:
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ!", show_alert=True)
    uid, coins = q.from_user.id, await _run(_get_coins, q.from_user.id)
    if coins < item["price"]:
        return await q.answer(f"❌ ɴᴇᴇᴅ {item['price']:,}. ʜᴀᴠᴇ {coins:,}.", show_alert=True)
    await _run(_remove_coins, uid, item["price"])
    await _run(_update_user, uid, {"gun": key})
    await q.answer(f"✅ {key.capitalize()} equipped!", show_alert=True)
    await q.message.edit(
        f"<blockquote>✅ {item['emoji']} **{key.capitalize()}** ᴇǫᴜɪᴘᴘᴇᴅ!\n"
        f"⚔️ +{item['damage']} ᴅᴀᴍᴀɢᴇ · 💰 {item['price']:,} ᴘᴀɪᴅ</blockquote>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_armory")]]),
    )

@app.on_callback_query(filters.regex(r"^buy_armor_(.+)$"))
async def buy_armor_cb(client, q: CallbackQuery):
    key  = q.matches[0].group(1)
    item = ARMOR.get(key)
    if not item:
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ!", show_alert=True)
    uid, coins = q.from_user.id, await _run(_get_coins, q.from_user.id)
    if coins < item["price"]:
        return await q.answer(f"❌ ɴᴇᴇᴅ {item['price']:,}. ʜᴀᴠᴇ {coins:,}.", show_alert=True)
    await _run(_remove_coins, uid, item["price"])
    await _run(_update_user, uid, {"armor": key})
    display = key.replace("_", " ").title()
    await q.answer(f"✅ {display} equipped!", show_alert=True)
    await q.message.edit(
        f"<blockquote>✅ {item['emoji']} **{display}** ᴇǫᴜɪᴘᴘᴇᴅ!\n"
        f"🛡 +{item['defense']} ᴅᴇғᴇɴsᴇ · 💰 {item['price']:,} ᴘᴀɪᴅ</blockquote>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_armory")]]),
    )

@app.on_callback_query(filters.regex(r"^buy_pet_(.+)$"))
async def buy_pet_cb(client, q: CallbackQuery):
    key  = q.matches[0].group(1)
    item = PETS.get(key)
    if not item:
        return await q.answer("❌ ɪɴᴠᴀʟɪᴅ!", show_alert=True)
    uid, coins = q.from_user.id, await _run(_get_coins, q.from_user.id)
    if coins < item["price"]:
        return await q.answer(f"❌ ɴᴇᴇᴅ {item['price']:,}. ʜᴀᴠᴇ {coins:,}.", show_alert=True)
    await _run(_remove_coins, uid, item["price"])
    await _run(_update_user, uid, {"pet": key})
    await q.answer(f"✅ {key.capitalize()} is your pet!", show_alert=True)
    await q.message.edit(
        f"<blockquote>✅ {item['emoji']} **{key.capitalize()}** ɪs ʏᴏᴜʀ ᴘᴇᴛ!\n"
        f"💪 +{item['power']} ᴘᴏᴡᴇʀ · 💰 {item['price']:,} ᴘᴀɪᴅ</blockquote>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_petshop")]]),
    )

@app.on_callback_query(filters.regex(r"^shop_inventory$"))
async def shop_inventory_cb(client, q: CallbackQuery):
    uid = q.from_user.id
    u   = await _run(_get_user, uid)
    pet = PETS.get(u["pet"], {})
    gun = GUNS.get(u["gun"], {})
    arm = ARMOR.get(u["armor"], {})
    def row(emoji, label, stat_key, stat_val):
        return emoji + " **" + label + "**" + (f" (+{stat_val} {stat_key})" if stat_val else "")
    await q.message.edit(
        f"🎒 **ʟᴏᴀᴅᴏᴜᴛ**\n━━━━━━━━━━━━━━━━\n"
        + row(pet.get("emoji","❌"), u["pet"].capitalize() or "No Pet",
              "power", pet.get("power",0) if u["pet"] else 0) + "\n"
        + row(gun.get("emoji","❌"), u["gun"].capitalize() or "No Gun",
              "damage", gun.get("damage",0) if u["gun"] else 0) + "\n"
        + row(arm.get("emoji","❌"), u["armor"].replace("_"," ").title() or "No Armor",
              "defense", arm.get("defense",0) if u["armor"] else 0) + "\n"
        + f"━━━━━━━━━━━━━━━━\n⚔️ ᴛᴏᴛᴀʟ ᴘᴏᴡᴇʀ: **{calc_power(u)}**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ ʙᴀᴄᴋ", callback_data="shop_main")]]),
    )


# ──────────────────────────────────────────────────────────────────
#  INVENTORY
# ──────────────────────────────────────────────────────────────────
async def _inventory_handler(client, m: Message):
    uid = m.from_user.id
    u   = await _run(_get_user, uid)
    pet = PETS.get(u["pet"], {})
    gun = GUNS.get(u["gun"], {})
    arm = ARMOR.get(u["armor"], {})
    await m.reply(
        f"🎒 **ʟᴏᴀᴅᴏᴜᴛ**\n━━━━━━━━━━━━━━━━\n"
        f"🐾 {pet.get('emoji','❌')} **{u['pet'].capitalize() or 'None'}**"
        + (f" (+{pet['power']} power)" if u["pet"] else "") + "\n"
        f"🔫 {gun.get('emoji','❌')} **{u['gun'].capitalize() or 'None'}**"
        + (f" (+{gun['damage']} dmg)" if u["gun"] else "") + "\n"
        f"🛡 {arm.get('emoji','❌')} **{u['armor'].replace('_',' ').title() or 'None'}**"
        + (f" (+{arm['defense']} def)" if u["armor"] else "") + "\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚔️ ᴘᴏᴡᴇʀ: **{calc_power(u)}**\n"
        f"💼 ᴊᴏʙ: {JOBS.get(u['job'],{}).get('emoji','❌')} **{u['job'].capitalize() or 'None'}**"
    )

@app.on_message(filters.command(["lifeinventory"]) & filters.group)
async def inventory_slash(client, m): await _inventory_handler(client, m)
@app.on_message(_rf(r"^(iinventory|inventory)\b"), group=-1)
async def inventory_noslash(client, m): await _inventory_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  SETTINGS  (admin)
# ──────────────────────────────────────────────────────────────────
async def _settings_handler(client, m: Message):
    if not await is_admin(client, m):
        return await m.reply("<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ!</blockquote>")
    cid        = m.chat.id
    cfg        = groups_col.find_one({"chat_id": cid}) or {}
    games_on   = cfg.get("games_enabled",  True)
    betting_on = cfg.get("betting_enabled", True)
    await m.reply(
        "<blockquote>⚙️ **sᴇᴛᴛɪɴɢs**</blockquote>",
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

@app.on_message(filters.command(["lifesettings"]) & filters.group)
async def settings_slash(client, m): await _settings_handler(client, m)
@app.on_message(_rf(r"^(ssettings|settings)\b"), group=-1)
async def settings_noslash(client, m): await _settings_handler(client, m)

@app.on_callback_query(filters.regex(r"^setting_(games|betting)_(-?\d+)$"))
async def settings_toggle_cb(client, q: CallbackQuery):
    setting = q.matches[0].group(1)
    chat_id = int(q.matches[0].group(2))
    db_key  = f"{setting}_enabled"
    current = (groups_col.find_one({"chat_id": chat_id}) or {}).get(db_key, True)
    new_val = not current
    groups_col.update_one({"chat_id": chat_id}, {"$set": {db_key: new_val}}, upsert=True)
    await q.answer(f"{'✅' if new_val else '❌'} {setting}!", show_alert=True)


# ──────────────────────────────────────────────────────────────────
#  ENABLE / DISABLE  (admin)
# ──────────────────────────────────────────────────────────────────
async def _enable_handler(client, m: Message):
    if not await is_admin(client, m):
        return await m.reply("❌ ᴀᴅᴍɪɴs ᴏɴʟʏ!")
    groups_col.update_one({"chat_id": m.chat.id}, {"$set": {"games_enabled": True}}, upsert=True)
    await m.reply("<blockquote>✅ ɢᴀᴍᴇs **ᴇɴᴀʙʟᴇᴅ**!</blockquote>")

async def _disable_handler(client, m: Message):
    if not await is_admin(client, m):
        return await m.reply("<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ!</blockquote>")
    groups_col.update_one({"chat_id": m.chat.id}, {"$set": {"games_enabled": False}}, upsert=True)
    await m.reply("<blockquote>❌ ɢᴀᴍᴇs **ᴅɪsᴀʙʟᴇᴅ**!</blockquote>")

@app.on_message(filters.command(["lifeenable"]) & filters.group)
async def enable_slash(client, m): await _enable_handler(client, m)
@app.on_message(_rf(r"^(eenable|enable)\b"), group=-1)
async def enable_noslash(client, m): await _enable_handler(client, m)

@app.on_message(filters.command(["lifedisable"]) & filters.group)
async def disable_slash(client, m): await _disable_handler(client, m)
@app.on_message(_rf(r"^(ddisable|disable)\b"), group=-1)
async def disable_noslash(client, m): await _disable_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  RESET  (owner/sudo)
# ──────────────────────────────────────────────────────────────────
async def _reset_handler(client, m: Message):
    uid = m.from_user.id
    if uid != OWNER_ID and uid not in SUDOERS:
        return await m.reply("<blockquote>❌ ᴏᴡɴᴇʀ ᴏɴʟʏ!</blockquote>")
    if not m.reply_to_message:
        return await m.reply("<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ᴛᴏ ʀᴇsᴇᴛ.</blockquote>")
    tid = m.reply_to_message.from_user.id
    users_col.delete_one({"user_id": tid})
    _get_user(tid)
    await m.reply(
        f"<blockquote>✅ ʀᴇsᴇᴛ [{tid}](tg://user?id={tid})</blockquote>",
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["lifereset"]) & filters.group)
async def reset_slash(client, m): await _reset_handler(client, m)
@app.on_message(_rf(r"^(rreset|reset)\b"), group=-1)
async def reset_noslash(client, m): await _reset_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  ADD COINS  (owner/sudo)
# ──────────────────────────────────────────────────────────────────
async def _addcoins_handler(client, m: Message):
    uid = m.from_user.id
    if uid != OWNER_ID and uid not in SUDOERS:
        return await m.reply("<blockquote>❌ ᴏᴡɴᴇʀ ᴏɴʟʏ!</blockquote>")
    if not m.reply_to_message:
        return await m.reply("<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ!</blockquote>")
    args = _parse_args(m.text)
    try:
        amount = int(args[0])
    except (ValueError, IndexError):
        return await m.reply("<blockquote>ᴜsᴀɢᴇ: `addcoins <amount>`</blockquote>")
    tid = m.reply_to_message.from_user.id
    await _run(_add_coins, tid, amount)
    await m.reply(
        f"<blockquote>✅ **{amount:,}** ᴄᴏɪɴs → {mention(m.reply_to_message.from_user)}</blockquote>",
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["lifeaddcoins"]) & filters.group)
async def addcoins_slash(client, m): await _addcoins_handler(client, m)
@app.on_message(_rf(r"^(aaddcoins|addcoins)\b"), group=-1)
async def addcoins_noslash(client, m): await _addcoins_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  DEPOSIT
# ──────────────────────────────────────────────────────────────────
async def _deposit_handler(client, m: Message):
    args = _parse_args(m.text)
    uid  = m.from_user.id
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>💰 ᴜsᴀɢᴇ: `deposit <amount>`</blockquote>")
    coins = await _run(_get_coins, uid)
    if coins < amount:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴡᴀʟʟᴇᴛ ᴄᴏɪɴs!</blockquote>")
    user = await _run(_get_user, uid)
    await _run(_remove_coins, uid, amount)
    await _run(_update_user, uid, {"bank": user.get("bank", 0) + amount})
    await m.reply(f"<blockquote>🏦 ᴅᴇᴘᴏsɪᴛᴇᴅ **{amount:,}** ᴄᴏɪɴs</blockquote>")

@app.on_message(filters.command(["deposit"]) & filters.group)
async def deposit_slash(client, m): await _deposit_handler(client, m)
@app.on_message(_rf(r"^deposit\b"), group=-1)
async def deposit_noslash(client, m): await _deposit_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  WITHDRAW
# ──────────────────────────────────────────────────────────────────
async def _withdraw_handler(client, m: Message):
    args = _parse_args(m.text)
    uid  = m.from_user.id
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>💰 ᴜsᴀɢᴇ: `withdraw <amount>`</blockquote>")
    user = await _run(_get_user, uid)
    bank = user.get("bank", 0)
    if bank < amount:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ!</blockquote>")
    await _run(_update_user, uid, {"bank": bank - amount})
    await _run(_add_coins, uid, amount)
    await m.reply(f"<blockquote>🏦 ᴡɪᴛʜᴅʀᴀᴡɴ **{amount:,}** ᴄᴏɪɴs</blockquote>")

@app.on_message(filters.command(["withdraw"]) & filters.group)
async def withdraw_slash(client, m): await _withdraw_handler(client, m)
@app.on_message(_rf(r"^withdraw\b"), group=-1)
async def withdraw_noslash(client, m): await _withdraw_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  BET  (NO cooldown)
# ──────────────────────────────────────────────────────────────────
async def _bet_handler(client, m: Message):
    args = _parse_args(m.text)
    uid  = m.from_user.id
    try:
        amount = int(args[0])
        if amount < 10:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>🎲 ᴜsᴀɢᴇ: `bet <amount>` (ᴍɪɴ 10)</blockquote>")
    coins = await _run(_get_coins, uid)
    if coins < amount:
        return await m.reply("❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!")
    user_data = await _run(_get_user, uid)
    streak    = user_data.get("streak", 0)
    if random.randint(1, 100) <= 45:
        win = amount * 2
        await _run(_add_coins, uid, win)
        streak += 1
        await _run(_update_user, uid, {"streak": streak})
        caption = (
            f"<blockquote>🎰 **{m.from_user.first_name}** ʙᴇᴛ {amount:,} ᴄᴏɪɴs</blockquote>\n"
            f"<blockquote>✅ ᴡᴏɴ **{win:,}** ᴄᴏɪɴs! 🏆 sᴛʀᴇᴀᴋ: {streak}</blockquote>"
        )
        await _send_life_image(m, "win", caption)
    else:
        await _run(_remove_coins, uid, amount)
        streak = 0
        await _run(_update_user, uid, {"streak": streak})
        caption = (
            f"<blockquote>🎰 **{m.from_user.first_name}** ʙᴇᴛ {amount:,} ᴄᴏɪɴs</blockquote>\n"
            f"<blockquote>❌ ʟᴏsᴛ **{amount:,}** ᴄᴏɪɴs</blockquote>"
        )
        await _send_life_image(m, "loss", caption)

@app.on_message(filters.command(["bet"]) & filters.group)
async def bet_slash(client, m): await _bet_handler(client, m)
@app.on_message(_rf(r"^(bbet|bet)\b"), group=-1)
async def bet_noslash(client, m): await _bet_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  ROB  (NO cooldown)
# ──────────────────────────────────────────────────────────────────
async def _rob_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("<blockquote>🔫 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ʀᴏʙ!</blockquote>")
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ʀᴏʙ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    victim_coins = await _run(_get_coins, tid)
    if victim_coins < 200:
        return await m.reply("<blockquote>❌ ᴛᴀʀɢᴇᴛ ᴛᴏᴏ ᴘᴏᴏʀ!</blockquote>")
    if random.randint(1, 100) <= 35:
        stolen = int(victim_coins * random.uniform(0.2, 0.4))
        await _run(_remove_coins, tid, stolen)
        await _run(_add_coins, uid, stolen)
        await m.reply(
            f"<blockquote>🔫 **sᴜᴄᴄᴇss!**\n💰 sᴛᴏʟᴇɴ: {stolen:,} ᴄᴏɪɴs</blockquote>"
        )
    else:
        fine = random.randint(200, 500)
        await _run(_remove_coins, uid, fine)
        await m.reply(
            f"<blockquote>🚨 **ғᴀɪʟᴇᴅ!**\n💸 ғɪɴᴇ: {fine:,} ᴄᴏɪɴs</blockquote>"
        )

@app.on_message(filters.command(["rob"]) & filters.group)
async def rob_slash(client, m): await _rob_handler(client, m)
@app.on_message(_rf(r"^(rrob|rob)\b"), group=-1)
async def rob_noslash(client, m): await _rob_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  PAY  (NO cooldown)
# ──────────────────────────────────────────────────────────────────
async def _pay_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("<blockquote>💸 ʀᴇᴘʟʏ ᴛᴏ ᴜsᴇʀ ᴛᴏ ᴘᴀʏ!</blockquote>")
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ᴘᴀʏ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    args           = _parse_args(m.text)
    sender_balance = await _run(_get_coins, uid)
    if not args:
        amount = sender_balance
    else:
        try:
            amount = int(args[0])
            if amount <= 0:
                raise ValueError
        except (ValueError, IndexError):
            return await m.reply("<blockquote>💸 ᴜsᴀɢᴇ: `pay <amount>`</blockquote>")
    if sender_balance < amount:
        return await m.reply("<blockquote>❌ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!</blockquote>")
    await _run(_remove_coins, uid, amount)
    await _run(_add_coins, tid, amount)
    await m.reply(
        f"<blockquote>💸 **ᴘᴀɪᴅ!**\n"
        f"{mention(m.from_user)} ➜ {mention(m.reply_to_message.from_user)}\n"
        f"💰 {amount:,} ᴄᴏɪɴs</blockquote>",
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["pay"]) & filters.group)
async def pay_slash(client, m): await _pay_handler(client, m)
@app.on_message(_rf(r"^(ppay|pay)\b"), group=-1)
async def pay_noslash(client, m): await _pay_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  LOAN  (NO cooldown)
# ──────────────────────────────────────────────────────────────────
async def _loan_handler(client, m: Message):
    if not m.reply_to_message:
        return await m.reply("<blockquote>💰 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ʀᴇǫᴜᴇsᴛ ʟᴏᴀɴ!</blockquote>")
    uid = m.from_user.id
    tid = m.reply_to_message.from_user.id
    if uid == tid:
        return await m.reply("<blockquote>❌ ᴄᴀɴ'ᴛ ʀᴇǫᴜᴇsᴛ ғʀᴏᴍ ʏᴏᴜʀsᴇʟғ!</blockquote>")
    args = _parse_args(m.text)
    if not args:
        return await m.reply("<blockquote>💰 ᴜsᴀɢᴇ: `loan <amount>`</blockquote>")
    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError
    except (ValueError, IndexError):
        return await m.reply("<blockquote>❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ!</blockquote>")
    await m.reply(
        f"<blockquote>💰 **ʟᴏᴀɴ ʀᴇǫᴜᴇsᴛ!**\n"
        f"{mention(m.from_user)} ʀᴇǫᴜᴇsᴛs **{amount:,}** ᴄᴏɪɴs\n"
        f"ғʀᴏᴍ {mention(m.reply_to_message.from_user)}</blockquote>",
        disable_web_page_preview=True,
    )

@app.on_message(filters.command(["loan"]) & filters.group)
async def loan_slash(client, m): await _loan_handler(client, m)
@app.on_message(_rf(r"^(lloan|loan)\b"), group=-1)
async def loan_noslash(client, m): await _loan_handler(client, m)


# ──────────────────────────────────────────────────────────────────
#  HELP
# ──────────────────────────────────────────────────────────────────
async def _help_handler(client, m: Message):
    await m.reply(
        "<blockquote>🎮 **ʟɪғᴇ ɢᴀᴍᴇs — ᴄᴏᴍᴍᴀɴᴅ ʟɪsᴛ**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</blockquote>\n"
        "<blockquote>**👤 ᴘʀᴏғɪʟᴇ & ᴇᴄᴏɴᴏᴍʏ**\n"
        "`profile` · `balance` · `daily` · `inventory` · `top`</blockquote>\n"
        "<blockquote>**🏦 ʙᴀɴᴋ**\n"
        "`deposit <n>` · `withdraw <n>` · `bet <n>` · `rob` (reply)</blockquote>\n"
        "<blockquote>**🎮 ɢᴀᴍᴇs**\n"
        "`slots <n>` · `bowling <n>` · `duel <n>` (reply) · `fight` (reply)</blockquote>\n"
        "<blockquote>**💼 ᴊᴏʙs**\n"
        "`job` · `job <name>` · `work` · `steal` (reply) · `shop`</blockquote>\n"
        "<blockquote>**❤️ sᴏᴄɪᴀʟ**\n"
        "`hug` · `kiss` · `slap` · `love` · `marry` · `divorce`\n"
        "`parent` · `sibling`   (all need reply)</blockquote>\n"
        "<blockquote>**🎁 ᴏᴛʜᴇʀ**\n"
        "`giveaway <n>` · `pay <n>` (reply) · `loan <n>` (reply)</blockquote>\n"
        "<blockquote>**⚙️ ᴀᴅᴍɪɴ**\n"
        "`settings` · `enable` · `disable`\n"
        "`reset` (reply, owner) · `addcoins <n>` (reply, owner)</blockquote>\n"
        "<blockquote>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 ᴅᴏᴜʙʟᴇ-ʟᴇᴛᴛᴇʀ ᴀʟɪᴀsᴇs ᴀʟsᴏ ᴡᴏʀᴋ:\n"
        "`bbet` `ppay` `ssteal` `dduel` `sslots` …\n"
        "ᴀɴʏ ᴄᴀᴘɪᴛᴀʟɪsᴀᴛɪᴏɴ: `BET` `Bet` `BBET` ✅\n"
        "sʟᴀsʜ: `/bet` `/lifebowling` ✅</blockquote>"
    )

@app.on_message(filters.command(["lifehelp"]) & filters.group)
async def help_slash(client, m): await _help_handler(client, m)
@app.on_message(_rf(r"^(hhelp|lifehelp)\b"), group=-1)
async def help_noslash(client, m): await _help_handler(client, m)


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
🔻 /steal         ➠ ꜱᴛᴇᴀʟ
🔻 /duel          ➠ ᴅᴜᴇʟ
🔻 /sslots        ➠ ꜱʟᴏᴛꜱ
🔻 /lifebowling   ➠ ʙᴏᴡʟɪɴɢ
🔻 /lifegiveaway  ➠ ɢɪᴠᴇᴀᴡᴀʏ
🔻 /deposit       ➠ ᴅᴇᴘᴏꜱɪᴛ
🔻 /withdraw      ➠ ᴡɪᴛʜᴅʀᴀᴡ
🔻 /bet           ➠ ɢᴀᴍʙʟᴇ
🔻 /rob           ➠ ʀᴏʙ
🔻 /pay           ➠ ᴘᴀʏ
🔻 /loan          ➠ ʟᴏᴀɴ ʀᴇǫᴜᴇꜱᴛ
"""
