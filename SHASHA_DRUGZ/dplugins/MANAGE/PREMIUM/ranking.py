import asyncio
import datetime
import time
from typing import Dict, List, Tuple, Optional
from zoneinfo import ZoneInfo

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from motor.motor_asyncio import AsyncIOMotorClient

from SHASHA_DRUGZ import app
from config import (
    MONGO_DB_URI,
    RANKING_PIC,
    AUTOPOST_TIME_HOUR,
    AUTOPOST_TIME_MINUTE,
)

# -------------------------------------------------------------------
# DEFAULT POST TIME (Fallback 21:00 IST)
# -------------------------------------------------------------------
try:
    POST_HOUR = int(AUTOPOST_TIME_HOUR)
    POST_MINUTE = int(AUTOPOST_TIME_MINUTE)
except Exception:
    POST_HOUR = 21
    POST_MINUTE = 0

TZ = ZoneInfo("Asia/Kolkata")

# -------------------------------------------------------------------
# DB SETUP (motor async)
# -------------------------------------------------------------------
mongo = AsyncIOMotorClient(MONGO_DB_URI)

try:
    db = mongo.get_default_database()
except:
    db = mongo["heartbeatlead"]   # fallback db name
ranking_db = db["ranking"]
autopost_db = db["ranking_autoposts"]  # stores chats where auto-post is enabled

# -------------------------------------------------------------------
# TODAY COUNTS (RAM)
# -------------------------------------------------------------------
_today_counts: Dict[int, Dict[int, int]] = {}
_today_lock = asyncio.Lock()
_last_reset_date: Optional[datetime.date] = None

_USERNAME_CACHE: Dict[int, Tuple[str, float]] = {}
_USERNAME_CACHE_TTL = 3600  # 1 hour


# -------------------------------------------------------------------
# DB HELPERS
# -------------------------------------------------------------------
async def db_inc_user_messages(user_id: int) -> None:
    try:
        await ranking_db.update_one(
            {"_id": user_id},
            {"$inc": {"total_messages": 1, "weekly_messages": 1, "monthly_messages": 1}},
            upsert=True,
        )
    except Exception as e:
        print(f"[ranking] db_inc_user_messages error: {e}")


async def db_get_top(field: str = "total_messages", limit: int = 10) -> List[dict]:
    try:
        cursor = ranking_db.find({}, {field: 1}).sort(field, -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        print(f"[ranking] db_get_top error: {e}")
        return []


async def db_get_top_user(field: str = "weekly_messages") -> Optional[dict]:
    """Return the top user document for the given field or None."""
    try:
        doc = await ranking_db.find_one({}, sort=[(field, -1)])
        return doc
    except Exception as e:
        print(f"[ranking] db_get_top_user error: {e}")
        return None


async def db_reset_field(field: str) -> None:
    try:
        await ranking_db.update_many({}, {"$set": {field: 0}})
        print(f"[ranking] RESET {field}")
    except Exception as e:
        print(f"[ranking] db_reset_field error: {e}")


async def db_get_user_counts(user_id: int) -> Tuple[int, int, int]:
    try:
        doc = await ranking_db.find_one(
            {"_id": user_id},
            {"total_messages": 1, "weekly_messages": 1, "monthly_messages": 1},
        )
        if not doc:
            return 0, 0, 0
        return (
            int(doc.get("total_messages", 0)),
            int(doc.get("weekly_messages", 0)),
            int(doc.get("monthly_messages", 0)),
        )
    except Exception as e:
        print(f"[ranking] db_get_user_counts error: {e}")
        return 0, 0, 0


async def db_get_rank_for_field(user_id: int, field: str) -> int:
    try:
        doc = await ranking_db.find_one({"_id": user_id}, {field: 1})
        user_val = int(doc.get(field, 0)) if doc else 0
        greater = await ranking_db.count_documents({field: {"$gt": user_val}})
        return greater + 1
    except Exception as e:
        print(f"[ranking] db_get_rank_for_field error: {e}")
        return 0


async def autopost_enable(chat_id: int, post_weekly: bool = True, post_monthly: bool = True) -> None:
    try:
        await autopost_db.update_one(
            {"_id": chat_id},
            {"$set": {"enabled": True, "post_weekly": post_weekly, "post_monthly": post_monthly, "hour": POST_HOUR, "minute": POST_MINUTE}},
            upsert=True,
        )
    except Exception as e:
        print(f"[ranking] autopost_enable error: {e}")


async def autopost_disable(chat_id: int) -> None:
    try:
        await autopost_db.delete_one({"_id": chat_id})
    except Exception as e:
        print(f"[ranking] autopost_disable error: {e}")


async def autopost_list() -> List[int]:
    try:
        docs = await autopost_db.find({"enabled": True}).to_list(length=1000)
        return [d["_id"] for d in docs]
    except Exception as e:
        print(f"[ranking] autopost_list error: {e}")
        return []


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def ist_now() -> datetime.datetime:
    return datetime.datetime.now(TZ)


def reset_today_if_needed():
    global _today_counts, _last_reset_date
    now_date = ist_now().date()
    if _last_reset_date != now_date:
        _today_counts = {}
        _last_reset_date = now_date


async def resolve_name(user_id: int) -> str:
    try:
        entry = _USERNAME_CACHE.get(user_id)
        now_ts = time.time()

        if entry:
            name, exp = entry
            if now_ts < exp:
                return name

        try:
            u = await app.get_users(user_id)
        except Exception:
            _USERNAME_CACHE[user_id] = (str(user_id), now_ts + _USERNAME_CACHE_TTL)
            return str(user_id)

        name = None
        if getattr(u, "first_name", None):
            name = u.first_name
            if getattr(u, "last_name", None):
                name = f"{name} {u.last_name}"
        elif getattr(u, "username", None):
            name = u.username

        if not name:
            name = str(user_id)

        _USERNAME_CACHE[user_id] = (name, now_ts + _USERNAME_CACHE_TTL)
        return name

    except Exception as e:
        print(f"[ranking] resolve_name error: {e}")
        return str(user_id)


def format_leaderboard(title: str, items: List[Tuple[str, int]]) -> str:
    lines = [f"<blockquote><b>📈 {title}</b></blockquote>"]
    if not items:
        return "\n".join(lines + ["<blockquote>No entries yet.</blockquote>"])

    for i, (name, count) in enumerate(items, 1):
        if len(name) > 30:
            name = name[:27] + "..."
        crown = " 🏆" if i == 1 else ""
        lines.append(f"<blockquote><b>{i}.</b> {name}{crown} — <code>{count}</code></blockquote>")
    return "\n".join(lines)


# -------------------------------------------------------------------
# WATCHERS (FIXED REGEX)
# -------------------------------------------------------------------
# FIX: Added [!/.\#] to ignore all command prefixes, not just /
@Client.on_message(filters.group & filters.text & ~filters.regex(r"^[/!\.#%,\@\$]"), group=9999)
async def watcher_global(client: Client, message: Message):
    try:
        if message.from_user:
            await db_inc_user_messages(message.from_user.id)
    except Exception as e:
        print(f"[ranking] watcher_global error: {e}")


@Client.on_message(filters.group & filters.text & ~filters.regex(r"^[/!\.#%,\@\$]"), group=10000)
async def watcher_today(client: Client, message: Message):
    try:
        if not message.from_user:
            return

        reset_today_if_needed()
        cid = message.chat.id
        uid = message.from_user.id

        async with _today_lock:
            if cid not in _today_counts:
                _today_counts[cid] = {}
            _today_counts[cid][uid] = _today_counts[cid].get(uid, 0) + 1
    except Exception as e:
        print(f"[ranking] watcher_today error: {e}")


# -------------------------------------------------------------------
# COMMANDS
# -------------------------------------------------------------------
@Client.on_message(filters.command("today") & filters.group)
async def cmd_today(client: Client, message: Message):
    try:
        chat_id = message.chat.id
        reset_today_if_needed()

        async with _today_lock:
            chat_counts = _today_counts.get(chat_id, {})

        if not chat_counts:
            return await message.reply_text("No data available for today.")

        pairs = sorted(chat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        items = [(await resolve_name(uid), cnt) for uid, cnt in pairs]

        text = format_leaderboard("Leaderboard Today", items)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Overall", callback_data="overall")],
                [InlineKeyboardButton("Monthly", callback_data="monthly"),
                 InlineKeyboardButton("Weekly", callback_data="weekly")],
            ]
        )

        try:
            await message.reply_photo(RANKING_PIC, caption=text, reply_markup=kb)
        except:
            await message.reply_text(text, reply_markup=kb)

    except Exception as e:
        print(f"[ranking] cmd_today error: {e}")


@Client.on_message(filters.command("ranking") & filters.group)
async def cmd_ranking(client: Client, message: Message):
    try:
        top = await db_get_top("total_messages", 10)
        if not top:
            return await message.reply_text("No ranking data available.")

        items = [(await resolve_name(row["_id"]), row.get("total_messages", 0)) for row in top]

        text = format_leaderboard("Leaderboard (Global)", items)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Today", callback_data="today")],
                [InlineKeyboardButton("Monthly", callback_data="monthly"),
                 InlineKeyboardButton("Weekly", callback_data="weekly")],
            ]
        )

        try:
            await message.reply_photo(RANKING_PIC, caption=text, reply_markup=kb)
        except:
            await message.reply_text(text, reply_markup=kb)

    except Exception as e:
        print(f"[ranking] cmd_ranking error: {e}")


@Client.on_message(filters.command("myrank") & filters.group)
async def cmd_myrank(client: Client, message: Message):
    try:
        uid = message.from_user.id
        total, weekly, monthly = await db_get_user_counts(uid)
        rank_total = await db_get_rank_for_field(uid, "total_messages")
        rank_weekly = await db_get_rank_for_field(uid, "weekly_messages")
        rank_monthly = await db_get_rank_for_field(uid, "monthly_messages")

        text = (
            f"<blockquote><b>📊 Your Rank</b></blockquote>\n"
            f"<blockquote>• Global: <b>#{rank_total}</b> — <code>{total}</code> msgs</blockquote>\n"
            f"<blockquote>• Weekly: <b>#{rank_weekly}</b> — <code>{weekly}</code> msgs</blockquote>\n"
            f"<blockquote>• Monthly: <b>#{rank_monthly}</b> — <code>{monthly}</code> msgs</blockquote>"
        )
        await message.reply_text(text)

    except Exception as e:
        print(f"[ranking] cmd_myrank error: {e}")


@Client.on_message(filters.command("weeklyrank") & filters.group)
async def cmd_weekly(client: Client, message: Message):
    try:
        top = await db_get_top("weekly_messages", 10)
        if not top:
            return await message.reply_text("No weekly data.")

        items = [(await resolve_name(row["_id"]), row.get("weekly_messages", 0)) for row in top]
        text = format_leaderboard("Leaderboard (Weekly)", items)

        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Today", callback_data="today")],
                [InlineKeyboardButton("Overall", callback_data="overall"),
                 InlineKeyboardButton("Monthly", callback_data="monthly")],
            ]
        )

        try:
            await message.reply_photo(RANKING_PIC, caption=text, reply_markup=kb)
        except:
            await message.reply_text(text, reply_markup=kb)

    except Exception as e:
        print(f"[ranking] cmd_weekly error: {e}")


@Client.on_message(filters.command("monthlyrank") & filters.group)
async def cmd_monthly(client: Client, message: Message):
    try:
        top = await db_get_top("monthly_messages", 10)
        if not top:
            return await message.reply_text("No monthly data.")

        items = [(await resolve_name(row["_id"]), row.get("monthly_messages", 0)) for row in top]
        text = format_leaderboard("Leaderboard (Monthly)", items)

        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Today", callback_data="today")],
                [InlineKeyboardButton("Overall", callback_data="overall"),
                 InlineKeyboardButton("Weekly", callback_data="weekly")],
            ]
        )

        try:
            await message.reply_photo(RANKING_PIC, caption=text, reply_markup=kb)
        except:
            await message.reply_text(text, reply_markup=kb)

    except Exception as e:
        print(f"[ranking] cmd_monthly error: {e}")


# Auto-post enable/disable commands (admins only)
@Client.on_message(filters.command("autopost_on") & filters.group)
async def cmd_autopost_on(client: Client, message: Message):
    try:
        # admin check
        chat_id = message.chat.id
        user_id = message.from_user.id
        member = await app.get_chat_member(chat_id, user_id)
        if member.status not in ("administrator", "creator"):
            return await message.reply_text("Only group admins can enable auto-post.")

        await autopost_enable(chat_id)
        await message.reply_text("Auto-post enabled for this group. Weekly & Monthly winners will be posted automatically.")
    except Exception as e:
        print(f"[ranking] cmd_autopost_on error: {e}")


@Client.on_message(filters.command("autopost_off") & filters.group)
async def cmd_autopost_off(client: Client, message: Message):
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        member = await app.get_chat_member(chat_id, user_id)
        if member.status not in ("administrator", "creator"):
            return await message.reply_text("Only group admins can disable auto-post.")

        await autopost_disable(chat_id)
        await message.reply_text("Auto-post disabled for this group.")
    except Exception as e:
        print(f"[ranking] cmd_autopost_off error: {e}")


@Client.on_callback_query(filters.regex("^today$"))
async def cb_today(_, q: CallbackQuery):
    try:
        cid = q.message.chat.id
        reset_today_if_needed()

        async with _today_lock:
            chat_counts = _today_counts.get(cid, {})

        if not chat_counts:
            return await q.answer("No data!", show_alert=True)

        pairs = sorted(chat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        items = [(await resolve_name(uid), cnt) for uid, cnt in pairs]

        text = format_leaderboard("Leaderboard Today", items)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Overall", callback_data="overall")],
                [InlineKeyboardButton("Monthly", callback_data="monthly"),
                 InlineKeyboardButton("Weekly", callback_data="weekly")],
            ]
        )

        await _safe_edit(q, text, kb)

    except Exception as e:
        print(f"[ranking] cb_today error: {e}")


@Client.on_callback_query(filters.regex("^overall$"))
async def cb_overall(_, q: CallbackQuery):
    try:
        top = await db_get_top("total_messages", 10)
        items = [(await resolve_name(row["_id"]), row.get("total_messages", 0)) for row in top]

        text = format_leaderboard("Leaderboard (Global)", items)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Today", callback_data="today")],
                [InlineKeyboardButton("Monthly", callback_data="monthly"),
                 InlineKeyboardButton("Weekly", callback_data="weekly")],
            ]
        )

        await _safe_edit(q, text, kb)

    except Exception as e:
        print(f"[ranking] cb_overall error: {e}")


@Client.on_callback_query(filters.regex("^monthly$"))
async def cb_monthly(_, q: CallbackQuery):
    try:
        top = await db_get_top("monthly_messages", 10)
        items = [(await resolve_name(row["_id"]), row.get("monthly_messages", 0)) for row in top]

        text = format_leaderboard("Leaderboard (Monthly)", items)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Today", callback_data="today")],
                [InlineKeyboardButton("Overall", callback_data="overall"),
                 InlineKeyboardButton("Weekly", callback_data="weekly")],
            ]
        )

        await _safe_edit(q, text, kb)

    except Exception as e:
        print(f"[ranking] cb_monthly error: {e}")


@Client.on_callback_query(filters.regex("^weekly$"))
async def cb_weekly(_, q: CallbackQuery):
    try:
        top = await db_get_top("weekly_messages", 10)
        items = [(await resolve_name(row["_id"]), row.get("weekly_messages", 0)) for row in top]

        text = format_leaderboard("Leaderboard (Weekly)", items)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Today", callback_data="today")],
                [InlineKeyboardButton("Overall", callback_data="overall"),
                 InlineKeyboardButton("Monthly", callback_data="monthly")],
            ]
        )

        await _safe_edit(q, text, kb)

    except Exception as e:
        print(f"[ranking] cb_weekly error: {e}")


# -------------------------------------------------------------------
# SAFE EDIT (Fix for photo caption vs text)
# -------------------------------------------------------------------
async def _safe_edit(query: CallbackQuery, text: str, kb):
    try:
        if query.message.photo:
            return await query.message.edit_caption(caption=text, reply_markup=kb)
        else:
            return await query.message.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await query.answer("Unable to update!", show_alert=True)
        except:
            pass


# -------------------------------------------------------------------
# AUTO RESET + AUTO POST SCHEDULER (Weekly + Monthly)
# -------------------------------------------------------------------
async def _compose_winner_message(period: str, user_name: str, count: int) -> str:
    if period == "weekly":
        title = "🏆 𝗪𝗘𝗘𝗞𝗟𝗬 𝗪𝗜𝗡𝗡𝗘𝗥 🏆"
    else:
        title = "🏆 𝗠𝗢𝗡𝗧𝗛𝗟𝗬 𝗟𝗘𝗚𝗘𝗡𝗗 🏆"

    msg = (
        f"{title}\n\n"
        f"Congratulations <b>{user_name}</b> 🎉\n\n"
        f"You are the top performer this {period}!\n"
        f"Total: <b>{count}</b> messages\n\n"
        f"Keep shining!"
    )
    return msg


async def _send_winner_to_chat(chat_id: int, period: str):
    try:
        field = "weekly_messages" if period == "weekly" else "monthly_messages"
        top = await db_get_top_user(field)
        if not top or int(top.get(field, 0)) == 0:
            return

        uid = top.get("_id")
        count = int(top.get(field, 0))
        name = await resolve_name(uid)
        # Add crown emoji for top user in composed message and also mark in title
        msg = await _compose_winner_message(period, name + " 🏆", count)

        try:
            await app.send_photo(chat_id, RANKING_PIC, caption=msg, parse_mode="html")
        except Exception:
            try:
                await app.send_message(chat_id, msg, parse_mode="html")
            except Exception as e:
                print(f"[ranking] failed to send winner to {chat_id}: {e}")

    except Exception as e:
        print(f"[ranking] _send_winner_to_chat error: {e}")


async def ranking_scheduler():
    while True:
        now = ist_now()

        # Reset times (non-post): keep reset at 00:01 IST
        try:
            if now.weekday() == 0 and now.hour == 0 and now.minute == 1:
                await db_reset_field("weekly_messages")
                print("[ranking] weekly reset done")

            if now.day == 1 and now.hour == 0 and now.minute == 1:
                await db_reset_field("monthly_messages")
                print("[ranking] monthly reset done")
        except Exception as e:
            print(f"[ranking] error during reset check: {e}")

        # Auto-post times (configurable via AUTOPOST_TIME_* in config)
        try:
            # At configured POST_HOUR:POST_MINUTE, send weekly winners (on Monday) and monthly winners (on 1st)
            if now.hour == POST_HOUR and now.minute == POST_MINUTE:
                # Weekly post (only on Monday)
                if now.weekday() == 0:
                    chats = await autopost_list()
                    for cid in chats:
                        await _send_winner_to_chat(cid, "weekly")

                # Monthly post (only on 1st)
                if now.day == 1:
                    chats = await autopost_list()
                    for cid in chats:
                        await _send_winner_to_chat(cid, "monthly")

        except Exception as e:
            print(f"[ranking] error during autopost: {e}")

        await asyncio.sleep(60)  # check every 1 minute


# Start scheduler safely
try:
    asyncio.create_task(ranking_scheduler())
    print("[ranking] Scheduler started")
except Exception as e:
    print(f"[ranking] Scheduler start error: {e}")


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_43"
__help__ = """
🔻 /ranking ➠ ꜱʜᴏᴡꜱ ɢʟᴏʙᴀʟ ʀᴀɴᴋɪɴɢ ʙᴀꜱᴇᴅ ᴏɴ ᴛᴏᴛᴀʟ ᴍᴇꜱꜱᴀɢᴇꜱ.
🔻 /today ➠ ꜱʜᴏᴡꜱ ᴛᴏᴅᴀʏ’ꜱ ɢʀᴏᴜᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ᴛᴏᴘ ᴍᴇꜱꜱᴀɢᴇ ꜱᴇɴᴅᴇʀꜱ).
🔻 /myrank ➠ ꜱʜᴏᴡꜱ ʏᴏᴜʀ ᴘᴇʀꜱᴏɴᴀʟ ʀᴀɴᴋ (ɢʟᴏʙᴀʟ / ᴡᴇᴇᴋʟʏ / ᴍᴏɴᴛʜʟʏ).
🔻 /weeklyrank ➠ ꜱʜᴏᴡꜱ ᴡᴇᴇᴋʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ʀᴇꜱᴇᴛꜱ ᴇᴠᴇʀʏ ᴍᴏɴᴅᴀʏ).
🔻 /monthlyrank ➠ ꜱʜᴏᴡꜱ ᴍᴏɴᴛʜʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ʀᴇꜱᴇᴛꜱ ᴏɴ ᴇᴀᴄʜ ᴍᴏɴᴛʜ 1ꜱᴛ).

🔻 /autopost_on ➠ ᴇɴᴀʙʟᴇꜱ ᴀᴜᴛᴏ ᴘᴏꜱᴛɪɴɢ ᴏꜰ ᴡᴇᴇᴋʟʏ & ᴍᴏɴᴛʜʟʏ ᴡɪɴɴᴇʀꜱ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
🔻 /autopost_off ➠ ᴅɪꜱᴀʙʟᴇꜱ ᴀᴜᴛᴏ ᴘᴏꜱᴛɪɴɢ ᴏꜰ ʀᴀɴᴋɪɴɢ ᴡɪɴɴᴇʀꜱ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).

🔻 (ᴀᴜᴛᴏ) ➠ ᴄᴏᴜɴᴛꜱ ᴇᴀᴄʜ ᴜꜱᴇʀ’ꜱ ᴍᴇꜱꜱᴀɢᴇꜱ ɪɴ ɢʀᴏᴜᴘꜱ.
🔻 (ᴀᴜᴛᴏ) ➠ ʀᴇꜱᴇᴛꜱ ᴡᴇᴇᴋʟʏ ᴄᴏᴜɴᴛꜱ ᴇᴠᴇʀʏ ᴍᴏɴᴅᴀʏ (00:01 ɪꜱᴛ).
🔻 (ᴀᴜᴛᴏ) ➠ ʀᴇꜱᴇᴛꜱ ᴍᴏɴᴛʜʟʏ ᴄᴏᴜɴᴛꜱ ᴏɴ ᴇᴀᴄʜ ᴍᴏɴᴛʜ 1ꜱᴛ (00:01 ɪꜱᴛ).
🔻 (ᴀᴜᴛᴏ) ➠ ᴘᴏꜱᴛꜱ ᴡᴇᴇᴋʟʏ & ᴍᴏɴᴛʜʟʏ ᴡɪɴɴᴇʀꜱ ᴀᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ ᴛɪᴍᴇ.
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Ranking"
MOD_PRICE = "100"
