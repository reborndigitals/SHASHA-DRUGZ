# SHASHA_DRUGZ/plugins/PREMIUM/chatfight.py
# SHASHA_DRUGZ/plugins/PREMIUM/chatfight.py
# ══════════════════════════════════════════════════════════════
#  ChatFight — SHASHA_DRUGZ Premium Plugin
#
#  FEATURES:
#    • Per-user message-count based level system
#    • Daily & overall message counters shown in /cfstats
#    • Level-up announcements with auto rank titles
#    • Coin reward system (bonus coins on level-up & milestones)
#    • Group-wide leaderboard (/cfrank)
#    • Group message milestone announcements
#    • Auto roles: Top 1 / Top 3 / Top 10 badge titles
#    • Admin toggle: /chatfight on|off
#    • Admin reset: /cfreset (group stats) | /cfreset @user (single user)
#    • User stats: /cfstats [reply|@user] — defaults to self
#    • Group stats: /msgcount
#    • Milestone toggle: /milestone on|off
#
#  LEVEL THRESHOLDS (based on personal message count):
#    Level 1  :   10 messages
#    Level 2  :  110 messages  (+100 from lvl 1)
#    Level 3  :  610 messages  (+500 from lvl 2)
#    Level 4  : 1110 messages  (+500 from lvl 3)
#    Level N≥3: 110 + (N-2)*500 messages total
#
#  XP FORMULA (cosmetic, still tracked):
#    Base XP per message  : 2 XP
#    Bonus XP (random)    : 0–3 XP
#
#  COIN REWARDS:
#    Level-up             : level * 10 coins
#    Milestone hit        : 50 coins to the triggering user
#
#  AUTO ROLES (title shown in leaderboard & stats):
#    🥇 ᴄʜᴀᴛ ᴋɪɴɢ        → rank 1
#    🥈 ᴇʟɪᴛᴇ ᴄʜᴀᴛᴛᴇʀ    → rank 2–3
#    🥉 ᴛᴏᴘ ᴍᴇᴍʙᴇʀ       → rank 4–10
#    💬 ᴍᴇᴍʙᴇʀ           → rank 11+
#
#  COLLECTIONS (MongoDB):
#    chatfight_users   — per-user XP/level/coins/msg_count/daily inside a group
#    chatfight_groups  — per-group message count / milestone config
#
#  COMMANDS:
#    /chatfight [on|off]   → enable / disable the plugin (admins)
#    /cfstats [reply|@u]   → show XP, level, coins, rank, msg counts for a user
#    /cfrank               → group leaderboard (top 10)
#    /cfreset [@user]      → reset group stats OR single user stats (admins)
#    /msgcount             → group message count + milestone info
#    /milestone [on|off]   → toggle milestone announcements (admins)
# ══════════════════════════════════════════════════════════════
import random
import logging
from datetime import date
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB_URI
from SHASHA_DRUGZ import app

logger = logging.getLogger("ChatFight")

# ── MongoDB setup ─────────────────────────────────────────────────────────────
mongo   = AsyncIOMotorClient(MONGO_DB_URI)
db      = mongo["SHASHA_DRUGZ"]
u_col   = db["chatfight_users"]   # { chat_id, user_id, xp, level, coins, msg_count, daily_msgs, daily_date }
g_col   = db["chatfight_groups"]  # { _id: chat_id, count, last_milestone, enabled, milestone_enabled }

# ── Constants ─────────────────────────────────────────────────────────────────
XP_PER_MSG      = 2
XP_BONUS_MAX    = 3     # random 0..XP_BONUS_MAX added per message
COINS_PER_LEVEL = 10    # multiplied by new level
COINS_MILESTONE = 50    # flat reward for triggering user on milestone

MILESTONES = [
    100, 500, 1000, 1500, 2000, 2500, 3000,
    5000, 10000, 15000, 20000, 25000,
    30000, 40000, 50000,
]

# ── Role titles based on leaderboard rank ─────────────────────────────────────
def _rank_title(rank: int) -> str:
    if rank == 1:
        return "🥇 ᴄʜᴀᴛ ᴋɪɴɢ"
    if rank <= 3:
        return "🥈 ᴇʟɪᴛᴇ ᴄʜᴀᴛᴛᴇʀ"
    if rank <= 10:
        return "🥉 ᴛᴏᴘ ᴍᴇᴍʙᴇʀ"
    return "💬 ᴍᴇᴍʙᴇʀ"

# ── Message thresholds for levelling ─────────────────────────────────────────
def _msgs_for_level(level: int) -> int:
    """
    Total personal messages needed to REACH `level`.
      Level 0 → 0 msgs   (start)
      Level 1 → 10 msgs
      Level 2 → 110 msgs  (10 + 100)
      Level N≥3 → 110 + (N-2)*500
    """
    if level <= 0:
        return 0
    if level == 1:
        return 10
    if level == 2:
        return 110
    return 110 + (level - 2) * 500

def _level_from_msgs(msgs: int) -> int:
    """Derive current level from total personal message count."""
    level = 0
    while msgs >= _msgs_for_level(level + 1):
        level += 1
    return level

def _msgs_needed_for_next(level: int) -> int:
    """How many messages to go from `level` → `level + 1`."""
    if level == 0:
        return 10
    if level == 1:
        return 100
    return 500

# ── XP (cosmetic) ─────────────────────────────────────────────────────────────
def _xp_for_level(level: int) -> int:
    """Cosmetic XP watermark at each level boundary (kept for display)."""
    return _msgs_for_level(level) * (XP_PER_MSG + XP_BONUS_MAX // 2)

# ══════════════════════════════════════════════════════════════
#  DB HELPERS
# ══════════════════════════════════════════════════════════════
async def _get_group(chat_id: int) -> dict:
    doc = await g_col.find_one({"_id": chat_id})
    if not doc:
        doc = {
            "_id": chat_id,
            "count": 0,
            "last_milestone": 0,
            "enabled": True,
            "milestone_enabled": True,
        }
        await g_col.insert_one(doc)
    return doc

async def _set_group(chat_id: int, **fields):
    await g_col.update_one({"_id": chat_id}, {"$set": fields}, upsert=True)

async def _get_user(chat_id: int, user_id: int) -> dict:
    doc = await u_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if not doc:
        doc = {
            "chat_id":    chat_id,
            "user_id":    user_id,
            "xp":         0,
            "level":      0,
            "coins":      0,
            "msg_count":  0,   # total personal messages (used for levelling)
            "daily_msgs": 0,   # messages sent today
            "daily_date": "",  # YYYY-MM-DD of the last active day
        }
        await u_col.insert_one(doc)
    return doc

async def _update_user(chat_id: int, user_id: int, **fields):
    await u_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": fields},
        upsert=True,
    )

async def _get_rank(chat_id: int, user_id: int) -> int:
    """1-based rank of user in this group by msg_count descending."""
    user_doc = await _get_user(chat_id, user_id)
    user_msgs = user_doc.get("msg_count", 0)
    count = await u_col.count_documents({"chat_id": chat_id, "msg_count": {"$gt": user_msgs}})
    return count + 1

async def _get_leaderboard(chat_id: int, limit: int = 10) -> list:
    cursor = u_col.find({"chat_id": chat_id}).sort("msg_count", -1).limit(limit)
    return [doc async for doc in cursor]

# ══════════════════════════════════════════════════════════════
#  PERMISSION HELPERS
# ══════════════════════════════════════════════════════════════
async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status.value in ("administrator", "creator", "owner")
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════
#  MILESTONE HELPER
# ══════════════════════════════════════════════════════════════
def _get_next_milestone(current: int) -> int:
    if current < 50000:
        for m in MILESTONES:
            if current < m:
                return m
    return ((current // 10000) + 1) * 10000

# ══════════════════════════════════════════════════════════════
#  CORE MESSAGE HANDLER — XP + COINS + MILESTONE
# ══════════════════════════════════════════════════════════════
@Client.on_message(
    filters.group
    & filters.text
    & ~filters.service
    & ~filters.bot
    & ~filters.command([])
    & ~filters.regex(r"^[!/\.]")
)
async def on_message(client, message):
    # Hard safety check
    if not message.text:
        return
    if message.text.startswith(("/", "!", ".")):
        return
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # ── Group config check ────────────────────────────────────
    g_data = await _get_group(chat_id)
    if not g_data.get("enabled", True):
        return

    # ── Increment group message count ─────────────────────────
    new_count      = g_data["count"] + 1
    last_milestone = g_data.get("last_milestone", 0)
    next_milestone = _get_next_milestone(last_milestone)
    g_update       = {"count": new_count}

    milestone_hit = (
        new_count >= next_milestone
        and last_milestone < next_milestone
        and g_data.get("milestone_enabled", True)
    )

    if milestone_hit:
        g_update["last_milestone"] = next_milestone

    await g_col.update_one({"_id": chat_id}, {"$set": g_update})

    # ── User data ──────────────────────────────────────────────
    u_data    = await _get_user(chat_id, user_id)
    today_str = str(date.today())

    # Cosmetic XP
    gained_xp = XP_PER_MSG + random.randint(0, XP_BONUS_MAX)
    new_xp    = u_data["xp"] + gained_xp

    # Personal message count (drives levelling)
    new_msg_count = u_data.get("msg_count", 0) + 1

    # Daily message counter — reset if it's a new day
    if u_data.get("daily_date") == today_str:
        new_daily = u_data.get("daily_msgs", 0) + 1
    else:
        new_daily = 1

    # ── Level calculation (message-based) ─────────────────────
    old_level = u_data["level"]
    new_level = _level_from_msgs(new_msg_count)
    coins     = u_data["coins"]
    level_up  = new_level > old_level

    if level_up:
        coins += new_level * COINS_PER_LEVEL

    if milestone_hit:
        coins += COINS_MILESTONE

    await _update_user(
        chat_id, user_id,
        xp=new_xp,
        level=new_level,
        coins=coins,
        msg_count=new_msg_count,
        daily_msgs=new_daily,
        daily_date=today_str,
    )

    # ── Level-up announcement ─────────────────────────────────
    if level_up:
        user    = message.from_user
        name    = user.first_name or str(user_id)
        mention = f"[{name}](tg://user?id={user_id})"
        rank    = await _get_rank(chat_id, user_id)
        title   = _rank_title(rank)
        msgs_to_next = _msgs_needed_for_next(new_level)
        try:
            await message.reply_text(
                f"<blockquote>⚡ **ʟᴇᴠᴇʟ ᴜᴘ!** ⚡\n\n"
                f"👤 {mention}\n"
                f"🎖 **ʟᴇᴠᴇʟ:** `{old_level}` ➜ `{new_level}`\n"
                f"💬 **ᴛᴏᴛᴀʟ ᴍsɢs:** `{new_msg_count:,}`\n"
                f"✨ **xᴘ:** `{new_xp}`\n"
                f"🪙 **ᴄᴏɪɴs ᴇᴀʀɴᴇᴅ:** `+{new_level * COINS_PER_LEVEL}`\n"
                f"🏅 **ʀᴏʟᴇ:** {title}\n"
                f"🚀 **ɴᴇxᴛ ʟᴠʟ ɪɴ:** `{msgs_to_next:,}` ᴍsɢs</blockquote>"
            )
        except Exception:
            pass

    # ── Milestone announcement ────────────────────────────────
    if milestone_hit:
        user    = message.from_user
        name    = user.first_name or str(user_id)
        mention = f"[{name}](tg://user?id={user_id})"
        nm      = _get_next_milestone(next_milestone)
        try:
            await message.reply_text(
                f"<blockquote>🔥 **ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴀᴄʜᴇᴅ!** 🔥\n\n"
                f"💬 **{next_milestone:,}** ᴍᴇssᴀɢᴇs ᴄᴏᴍᴘʟᴇᴛᴇᴅ!\n"
                f"🎉 ᴛʀɪɢɢᴇʀᴇᴅ ʙʏ {mention}\n"
                f"🪙 **+{COINS_MILESTONE} ᴄᴏɪɴs** ʀᴇᴡᴀʀᴅᴇᴅ!\n\n"
                f"🚀 **ɴᴇxᴛ ᴛᴀʀɢᴇᴛ:** `{nm:,}`</blockquote>"
            )
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════
#  /chatfight — enable / disable plugin
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.group & filters.command("chatfight"))
async def cmd_chatfight(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        return await message.reply_text(
            "<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ.</blockquote>"
        )

    args = message.command
    if len(args) < 2:
        g = await _get_group(chat_id)
        status = "🟢 ᴇɴᴀʙʟᴇᴅ" if g.get("enabled", True) else "🔴 ᴅɪsᴀʙʟᴇᴅ"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="cf_close")
        ]])
        return await message.reply_text(
            f"<blockquote>⚔️ **ᴄʜᴀᴛғɪɢʜᴛ**\n\n"
            f"sᴛᴀᴛᴜs: {status}\n\n"
            f"ᴜsᴇ `/chatfight on` ᴏʀ `/chatfight off`</blockquote>",
            reply_markup=kb,
        )

    opt = args[1].lower()
    if opt == "on":
        await _set_group(chat_id, enabled=True)
        await message.reply_text("<blockquote>✅ ᴄʜᴀᴛғɪɢʜᴛ **ᴇɴᴀʙʟᴇᴅ**!</blockquote>")
    elif opt == "off":
        await _set_group(chat_id, enabled=False)
        await message.reply_text("<blockquote>❌ ᴄʜᴀᴛғɪɢʜᴛ **ᴅɪsᴀʙʟᴇᴅ**.</blockquote>")
    else:
        await message.reply_text(
            "<blockquote>ᴜsᴀɢᴇ: `/chatfight on` | `/chatfight off`</blockquote>"
        )

# ══════════════════════════════════════════════════════════════
#  /cfstats — user XP / level / coins / rank / message counts
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.group & filters.command("cfstats"))
async def cmd_cfstats(client, message):
    chat_id = message.chat.id
    target  = None

    # resolve target: reply > arg > self
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(
                int(arg) if arg.lstrip("-").isdigit() else arg
            )
        except Exception:
            return await message.reply_text("<blockquote>❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.</blockquote>")
    else:
        target = message.from_user

    if not target:
        return

    user_id = target.id
    name    = target.first_name or str(user_id)
    mention = f"[{name}](tg://user?id={user_id})"

    u_data    = await _get_user(chat_id, user_id)
    xp        = u_data["xp"]
    level     = u_data["level"]
    coins     = u_data["coins"]
    msg_count = u_data.get("msg_count", 0)
    today_str = str(date.today())

    # Daily messages — reset counter display if it's a new day
    if u_data.get("daily_date") == today_str:
        daily_msgs = u_data.get("daily_msgs", 0)
    else:
        daily_msgs = 0

    rank  = await _get_rank(chat_id, user_id)
    title = _rank_title(rank)

    # Progress bar based on personal message count
    msgs_at_level      = _msgs_for_level(level)
    msgs_at_next_level = _msgs_for_level(level + 1)
    msgs_progress      = msg_count - msgs_at_level
    msgs_needed        = msgs_at_next_level - msgs_at_level
    bars               = int((msgs_progress / msgs_needed) * 10) if msgs_needed else 10
    bar_str            = "█" * bars + "░" * (10 - bars)
    msgs_to_next       = max(0, msgs_at_next_level - msg_count)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="cf_close")
    ]])
    await message.reply_text(
        f"<blockquote>⚔️ **ᴄʜᴀᴛғɪɢʜᴛ sᴛᴀᴛs**\n\n"
        f"👤 **ᴜsᴇʀ:** {mention}\n"
        f"🏅 **ʀᴏʟᴇ:** {title}\n"
        f"🏆 **ʀᴀɴᴋ:** `#{rank}`\n"
        f"🎖 **ʟᴇᴠᴇʟ:** `{level}`\n"
        f"✨ **xᴘ:** `{xp}`\n"
        f"🪙 **ᴄᴏɪɴs:** `{coins}`\n\n"
        f"💬 **ᴍᴇssᴀɢᴇs ᴛᴏᴅᴀʏ:** `{daily_msgs:,}`\n"
        f"📨 **ᴛᴏᴛᴀʟ ᴍᴇssᴀɢᴇs:** `{msg_count:,}`\n\n"
        f"📊 **ʟᴠʟ ᴘʀᴏɢʀᴇss:** `[{bar_str}]` {msgs_progress}/{msgs_needed} ᴍsɢs\n"
        f"🚀 **ɴᴇxᴛ ʟᴇᴠᴇʟ ɪɴ:** `{msgs_to_next:,}` ᴍᴏʀᴇ ᴍsɢs</blockquote>",
        reply_markup=kb,
    )

# ══════════════════════════════════════════════════════════════
#  /cfrank — group leaderboard (top 10)
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.group & filters.command("cfrank"))
async def cmd_cfrank(client, message):
    chat_id = message.chat.id
    top     = await _get_leaderboard(chat_id, limit=10)

    if not top:
        return await message.reply_text(
            "<blockquote>⚠️ ɴᴏ ᴅᴀᴛᴀ ʏᴇᴛ. sᴛᴀʀᴛ ᴄʜᴀᴛᴛɪɴɢ!</blockquote>"
        )

    lines = ["<blockquote>🏆 **ᴄʜᴀᴛғɪɢʜᴛ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**\n"]
    for i, doc in enumerate(top, 1):
        uid       = doc["user_id"]
        xp        = doc["xp"]
        lvl       = doc["level"]
        coins     = doc["coins"]
        msg_count = doc.get("msg_count", 0)
        title     = _rank_title(i)
        try:
            u    = await client.get_users(uid)
            name = u.first_name or str(uid)
        except Exception:
            name = str(uid)
        mention = f"[{name}](tg://user?id={uid})"
        lines.append(
            f"`{i:02}.` {title}\n"
            f"     {mention} — ʟᴠʟ `{lvl}` ❙ 💬 `{msg_count:,}` ❙ 🪙 `{coins}`\n"
        )
    lines.append("</blockquote>")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="cf_close")
    ]])
    await message.reply_text("\n".join(lines), reply_markup=kb)

# ══════════════════════════════════════════════════════════════
#  /cfreset — reset group or single user (admins only)
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.group & filters.command("cfreset"))
async def cmd_cfreset(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        return await message.reply_text("<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ.</blockquote>")

    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(
                int(arg) if arg.lstrip("-").isdigit() else arg
            )
        except Exception:
            return await message.reply_text("<blockquote>❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.</blockquote>")

    if target:
        # Reset single user
        await u_col.delete_one({"chat_id": chat_id, "user_id": target.id})
        name    = target.first_name or str(target.id)
        mention = f"[{name}](tg://user?id={target.id})"
        await message.reply_text(
            f"<blockquote>🗑 {mention} `[{target.id}]` sᴛᴀᴛs ʜᴀᴠᴇ ʙᴇᴇɴ **ʀᴇsᴇᴛ**.</blockquote>"
        )
    else:
        # Reset entire group
        await u_col.delete_many({"chat_id": chat_id})
        await g_col.update_one(
            {"_id": chat_id},
            {"$set": {"count": 0, "last_milestone": 0}},
            upsert=True,
        )
        await message.reply_text(
            "<blockquote>🗑 **ᴀʟʟ ɢʀᴏᴜᴘ sᴛᴀᴛs ʜᴀᴠᴇ ʙᴇᴇɴ ʀᴇsᴇᴛ.**</blockquote>"
        )

# ══════════════════════════════════════════════════════════════
#  /msgcount — group message count + milestone info
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.group & filters.command("msgcount"))
async def cmd_msgcount(client, message):
    chat_id = message.chat.id
    data    = await _get_group(chat_id)
    count   = data["count"]
    last_ms = data.get("last_milestone", 0)
    next_ms = _get_next_milestone(last_ms)
    ms_on   = "🟢 ᴇɴᴀʙʟᴇᴅ" if data.get("milestone_enabled", True) else "🔴 ᴅɪsᴀʙʟᴇᴅ"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="cf_close")
    ]])
    await message.reply_text(
        f"<blockquote>📊 **ɢʀᴏᴜᴘ sᴛᴀᴛs**\n\n"
        f"💬 **ᴛᴏᴛᴀʟ ᴍᴇssᴀɢᴇs:** `{count:,}`\n"
        f"🏁 **ʟᴀsᴛ ᴍɪʟᴇsᴛᴏɴᴇ:** `{last_ms:,}`\n"
        f"🎯 **ɴᴇxᴛ ᴍɪʟᴇsᴛᴏɴᴇ:** `{next_ms:,}`\n"
        f"🔔 **ᴍɪʟᴇsᴛᴏɴᴇ ᴀʟᴇʀᴛs:** {ms_on}</blockquote>",
        reply_markup=kb,
    )

# ══════════════════════════════════════════════════════════════
#  /milestone — toggle milestone announcements
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.group & filters.command("milestone"))
async def cmd_milestone(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        return await message.reply_text("<blockquote>❌ ᴀᴅᴍɪɴs ᴏɴʟʏ.</blockquote>")

    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>ᴜsᴀɢᴇ: `/milestone on` | `/milestone off`</blockquote>"
        )

    opt = message.command[1].lower()
    if opt == "on":
        await _set_group(chat_id, milestone_enabled=True)
        await message.reply_text("<blockquote>✅ ᴍɪʟᴇsᴛᴏɴᴇ ᴀʟᴇʀᴛs **ᴇɴᴀʙʟᴇᴅ**!</blockquote>")
    elif opt == "off":
        await _set_group(chat_id, milestone_enabled=False)
        await message.reply_text("<blockquote>❌ ᴍɪʟᴇsᴛᴏɴᴇ ᴀʟᴇʀᴛs **ᴅɪsᴀʙʟᴇᴅ**.</blockquote>")
    else:
        await message.reply_text(
            "<blockquote>ᴜsᴀɢᴇ: `/milestone on` | `/milestone off`</blockquote>"
        )

# ══════════════════════════════════════════════════════════════
#  SHARED CLOSE CALLBACK
# ══════════════════════════════════════════════════════════════
@Client.on_callback_query(filters.regex(r"^cf_close$"))
async def cf_close(client, cq):
    try:
        await cq.message.delete()
    except Exception:
        pass
    await cq.answer()

# ══════════════════════════════════════════════════════════════
#  MODULE METADATA
# ══════════════════════════════════════════════════════════════
__menu__     = "CMD_PRO"
__mod_name__ = ""
__help__ = """
**ᴛᴏɢɢʟᴇ (ᴀᴅᴍɪɴs):**
🔻 `/chatfight on` ➠ ᴇɴᴀʙʟᴇ ᴄʜᴀᴛғɪɢʜᴛ
🔻 `/chatfight off` ➠ ᴅɪsᴀʙʟᴇ ᴄʜᴀᴛғɪɢʜᴛ

**sᴛᴀᴛs:**
🔻 `/cfstats` ➠ ʏᴏᴜʀ xᴘ, ʟᴇᴠᴇʟ, ᴄᴏɪɴs, ʀᴀɴᴋ & ᴍsɢ ᴄᴏᴜɴᴛs
🔻 `/cfstats @user` ➠ ᴀɴᴏᴛʜᴇʀ ᴜsᴇʀ's sᴛᴀᴛs
🔻 `/cfrank` ➠ ɢʀᴏᴜᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ᴛᴏᴘ 10)
🔻 `/msgcount` ➠ ᴛᴏᴛᴀʟ ᴍᴇssᴀɢᴇs + ᴍɪʟᴇsᴛᴏɴᴇ ɪɴғᴏ

**ᴀᴅᴍɪɴ:**
🔻 `/cfreset` ➠ ʀᴇsᴇᴛ ᴀʟʟ ɢʀᴏᴜᴘ sᴛᴀᴛs
🔻 `/cfreset @user` ➠ ʀᴇsᴇᴛ ᴏɴᴇ ᴜsᴇʀ's sᴛᴀᴛs
🔻 `/milestone on/off` ➠ ᴛᴏɢɢʟᴇ ᴍɪʟᴇsᴛᴏɴᴇ ᴀʟᴇʀᴛs
"""

MOD_TYPE = "PRO-BOTS"
MOD_NAME = "ChatFight"
MOD_PRICE = "70"
