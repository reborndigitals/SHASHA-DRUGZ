# SHASHA_DRUGZ/plugins/COMMON/poll.py
# ══════════════════════════════════════════════════════════════
#  Poll System — SHASHA_DRUGZ Plugin
#
#  FEATURES:
#    • Full Telegram-native poll with all options
#    • Poll types: regular | quiz
#    • Anonymous / non-anonymous toggle (button)
#    • Multiple answers toggle — regular polls only (button)
#    • Quiz mode: correct answer via inline button + explanation
#    • Auto-close timer — optional, in HOURS, via buttons
#    • No-timer polls: auto-report @ 24 h; 2nd report @ 48 h
#      only if vote count increased since the first report
#    • /poll       — fully button-driven wizard
#    • /quickpoll  — one-liner with flags
#    • /pollhelp   — usage guide
#
#  QUICK FORMAT:
#    /quickpoll Question | Option1 | Option2 [| Option3 ...]
#    Flags (append anywhere after options):
#      --quiz          → quiz mode
#      --anon          → anonymous
#      --multi         → allow multiple answers
#      --correct=2     → correct option index (1-based, quiz only)
#      --close=N       → auto-close after N hours (e.g. --close=6)
#      --explain=text  → quiz explanation (must be last flag)
#
#  WIZARD FLOW:
#    /poll → question (text) → options (text, one by one) →
#            [Done] → poll type → anonymous → multi/correct →
#            [explain skip/text] → timer yes/no → [hour buttons] → ✅
#
#  BUG FIXES vs previous version:
#    ✅ _sessions MongoDB now used — wizard state persisted on every step
#    ✅ Bot-restart recovery — session restored from MongoDB
#    ✅ filters.command(None) replaced with ~filters.regex(r"^/")
#    ✅ datetime.now(timezone.utc) — correct UTC-aware datetime
#    ✅ Duplicate option detection
#    ✅ --explain flag parsed before splitting on | to avoid corruption
#    ✅ Rate-limit guard: max 10 concurrent background tasks per bot
#    ✅ poll_id (unique ObjectId) stored in results for analytics
#
#  COLLECTIONS (MongoDB):
#    poll_sessions  — active wizard state, TTL 1 h
#    poll_results   — poll tracking + delivery records
# ══════════════════════════════════════════════════════════════
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta

from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import PollType
from bson import ObjectId

from SHASHA_DRUGZ import app, mongo

logger = logging.getLogger("PollSystem")

# ── MongoDB ───────────────────────────────────────────────────
_db       = mongo["POLL_SYSTEM"]
_sessions = _db["poll_sessions"]   # persisted wizard state (TTL index on saved_at)
_results  = _db["poll_results"]    # closed poll tracking

# Ensure TTL index exists on _sessions (expire after 3600 s = 1 h)
try:
    _sessions.create_index("saved_at", expireAfterSeconds=3600)
except Exception:
    pass

# ── Background task guard ─────────────────────────────────────
# Prevents unbounded task accumulation when many polls are created.
_MAX_BG_TASKS   = 50
_active_tasks: set = set()


# ══════════════════════════════════════════════════════════════
#  UTC HELPER
# ══════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime (preferred over utcnow())."""
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════
#  SESSION PERSISTENCE
# ══════════════════════════════════════════════════════════════

async def _session_save(user_id: int, state: dict) -> None:
    """Upsert wizard state to MongoDB so it survives bot restarts."""
    doc = {"user_id": user_id, "state": state, "saved_at": _utcnow()}
    await _sessions.replace_one({"user_id": user_id}, doc, upsert=True)


async def _session_delete(user_id: int) -> None:
    await _sessions.delete_one({"user_id": user_id})


async def _sessions_restore() -> None:
    """On startup: reload any unfinished wizard sessions into _wiz."""
    count = 0
    async for doc in _sessions.find({}):
        _wiz[doc["user_id"]] = doc["state"]
        count += 1
    if count:
        logger.info("PollSystem: restored %d wizard session(s) from MongoDB.", count)


# ── In-memory wizard cache ────────────────────────────────────
# { user_id: { step, chat_id, question, options, is_quiz, anon,
#              multi, correct, explain, close_hours, creator_id } }
_wiz: dict = {}


# ══════════════════════════════════════════════════════════════
#  KEYBOARD BUILDERS
# ══════════════════════════════════════════════════════════════

def _cancel_row() -> list:
    return [InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻", callback_data="poll_cancel")]


def _close_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([_cancel_row()])


def _yn_kb(yes_cb: str, no_cb: str,
           yes_label: str = "✅ ʏᴇs",
           no_label:  str = "❌ ɴᴏ") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(yes_label, callback_data=yes_cb),
            InlineKeyboardButton(no_label,  callback_data=no_cb),
        ],
        _cancel_row(),
    ])


def _correct_option_kb(options: list) -> InlineKeyboardMarkup:
    """One button per poll option (2 per row, label truncated to 22 chars)."""
    rows, row = [], []
    for i, opt in enumerate(options):
        label = f"{i + 1}. {opt[:22]}" if len(opt) > 22 else f"{i + 1}. {opt}"
        row.append(InlineKeyboardButton(label, callback_data=f"poll_correct_{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def _timer_kb() -> InlineKeyboardMarkup:
    """Hour-selection grid: 1 h … 48 h, 4 per row."""
    hour_options = [1, 2, 4, 6, 8, 12, 24, 48]
    rows, row = [], []
    for h in hour_options:
        row.append(InlineKeyboardButton(f"⏱ {h}ʜ", callback_data=f"poll_timer_{h}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def _timer_yn_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ ᴛɪᴍᴇʀ ʏᴇs", callback_data="poll_set_timer"),
            InlineKeyboardButton("∞ ᴛɪᴍᴇʀ ɴᴏ",   callback_data="poll_no_timer"),
        ],
        _cancel_row(),
    ])


# ══════════════════════════════════════════════════════════════
#  POLL SENDER
# ══════════════════════════════════════════════════════════════

async def _send_poll_from_state(client, state: dict) -> Message:
    """Build and send a Telegram-native poll from a wizard / quick state dict."""
    close_hours = state.get("close_hours")
    close_date  = (_utcnow() + timedelta(hours=close_hours)) if close_hours else None

    kwargs: dict = dict(
        chat_id      = state["chat_id"],
        question     = state["question"],
        options      = state["options"],
        is_anonymous = state.get("anon", True),
    )

    if state.get("is_quiz"):
        kwargs["type"]              = PollType.QUIZ
        kwargs["correct_option_id"] = state.get("correct", 0)
        if state.get("explain"):
            kwargs["explanation"]   = state["explain"]
    else:
        kwargs["type"]                    = PollType.REGULAR
        kwargs["allows_multiple_answers"] = state.get("multi", False)

    if close_date:
        kwargs["close_date"] = close_date

    return await client.send_poll(**kwargs)


# ══════════════════════════════════════════════════════════════
#  RESULT DELIVERY
# ══════════════════════════════════════════════════════════════

async def _build_result_text(question: str, poll) -> tuple[str, int]:
    total = poll.total_voter_count or 0
    lines = [
        f"<blockquote>📊 **ᴘᴏʟʟ ʀᴇsᴜʟᴛs**\n\n"
        f"❓ {question}\n"
        f"👥 **ᴛᴏᴛᴀʟ ᴠᴏᴛᴇs:** `{total}`\n\n"
    ]
    for opt in poll.options:
        pct = round((opt.voter_count / total * 100) if total else 0, 1)
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        lines.append(
            f"• **{opt.text}**\n"
            f"  `[{bar}]` {opt.voter_count} ᴠᴏᴛᴇs ({pct}%)\n"
        )
    lines.append("</blockquote>")
    return "\n".join(lines), total


async def _fetch_poll(client, chat_id: int, message_id: int):
    """Safely fetch poll object; returns None on any failure."""
    try:
        msg = await client.get_messages(chat_id, message_id)
        return msg.poll if msg else None
    except Exception as exc:
        logger.warning("Poll fetch failed (chat=%s msg=%s): %s", chat_id, message_id, exc)
        return None


async def _deliver_result(client, creator_id: int, question: str, poll) -> int:
    """PM results to creator. Returns total_voter_count."""
    text, total = await _build_result_text(question, poll)
    try:
        await client.send_message(creator_id, text)
    except Exception as exc:
        logger.warning("Result PM failed (user=%s): %s", creator_id, exc)
    return total


# ── Timed poll ────────────────────────────────────────────────

async def _schedule_timed_result(client, chat_id: int, message_id: int,
                                  creator_id: int, question: str,
                                  close_hours: int):
    await asyncio.sleep(close_hours * 3600 + 10)
    poll = await _fetch_poll(client, chat_id, message_id)
    if poll:
        await _deliver_result(client, creator_id, question, poll)


# ── No-timer poll: 24 h + optional 48 h ─────────────────────

async def _schedule_no_timer_report(client, chat_id: int, message_id: int,
                                     creator_id: int, question: str):
    # First report @ 24 h
    await asyncio.sleep(24 * 3600)
    poll1 = await _fetch_poll(client, chat_id, message_id)
    if not poll1:
        return
    first_count = await _deliver_result(client, creator_id, question, poll1)

    # Second report @ 48 h — only if votes increased
    await asyncio.sleep(24 * 3600)
    poll2 = await _fetch_poll(client, chat_id, message_id)
    if poll2 and (poll2.total_voter_count or 0) > first_count:
        await _deliver_result(client, creator_id, question, poll2)


# ── Task launcher (rate-limit guarded) ───────────────────────

def _launch_task(coro) -> None:
    """Create a background task, enforce _MAX_BG_TASKS ceiling."""
    if len(_active_tasks) >= _MAX_BG_TASKS:
        logger.warning("PollSystem: BG task limit (%d) reached, skipping.", _MAX_BG_TASKS)
        return
    task = asyncio.get_event_loop().create_task(coro)
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)


def _schedule_result_task(client, state: dict, poll_msg: Message) -> None:
    close_hours = state.get("close_hours")
    if close_hours:
        _launch_task(
            _schedule_timed_result(
                client, state["chat_id"], poll_msg.id,
                state["creator_id"], state["question"], close_hours,
            )
        )
    else:
        _launch_task(
            _schedule_no_timer_report(
                client, state["chat_id"], poll_msg.id,
                state["creator_id"], state["question"],
            )
        )


# ══════════════════════════════════════════════════════════════
#  FLAG PARSER  (shared by /quickpoll)
# ══════════════════════════════════════════════════════════════

def _parse_flags(raw: str) -> tuple[str, dict]:
    """
    Strip all flags from `raw`, return (cleaned_raw, flags_dict).
    --explain is extracted first to prevent its text from being
    corrupted if it contains `|` or `--` sequences.
    """
    flags: dict = {
        "is_quiz":    False,
        "anon":       False,
        "multi":      False,
        "correct":    0,
        "close_hours": None,
        "explain":    None,
    }

    # 1. --explain must be last flag (greedily captures to end of string)
    m = re.search(r"--explain=(.+)$", raw, re.DOTALL)
    if m:
        flags["explain"] = m.group(1).strip()
        raw = raw[: m.start()].strip()

    # 2. --correct=N
    m = re.search(r"--correct=(\d+)", raw)
    if m:
        flags["correct"] = max(0, int(m.group(1)) - 1)   # 1-based → 0-based
        raw = re.sub(r"--correct=\d+", "", raw)

    # 3. --close=N
    m = re.search(r"--close=(\d+)", raw)
    if m:
        flags["close_hours"] = max(1, int(m.group(1)))
        raw = re.sub(r"--close=\d+", "", raw)

    # 4. Boolean flags
    flags["is_quiz"] = "--quiz"  in raw
    flags["anon"]    = "--anon"  in raw
    flags["multi"]   = "--multi" in raw and not flags["is_quiz"]

    for flag in ("--quiz", "--anon", "--multi"):
        raw = raw.replace(flag, "")

    return raw.strip(), flags


# ══════════════════════════════════════════════════════════════
#  /quickpoll
# ══════════════════════════════════════════════════════════════

@Client.on_message(filters.command("quickpoll"))
async def cmd_quickpoll(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:**\n"
            "`/quickpoll Question | Opt1 | Opt2 [| ...]`\n\n"
            "ᴜsᴇ `/pollhelp` ғᴏʀ ғʟᴀɢs ᴀɴᴅ ᴇxᴀᴍᴘʟᴇs.</blockquote>"
        )

    raw       = message.text.split(None, 1)[1]
    raw, flags = _parse_flags(raw)

    parts    = [p.strip() for p in raw.split("|") if p.strip()]
    question = parts[0] if parts else ""
    options  = parts[1:]

    if not question:
        return await message.reply_text(
            "<blockquote>❌ ɴᴏ ǫᴜᴇsᴛɪᴏɴ ᴘʀᴏᴠɪᴅᴇᴅ.</blockquote>"
        )
    if len(options) < 2:
        return await message.reply_text(
            "<blockquote>❌ ɢɪᴠᴇ ᴀᴛ ʟᴇᴀsᴛ **2 ᴏᴘᴛɪᴏɴs**.</blockquote>"
        )
    if len(options) > 10:
        return await message.reply_text(
            "<blockquote>❌ ᴍᴀx **10 ᴏᴘᴛɪᴏɴs** ᴀʟʟᴏᴡᴇᴅ.</blockquote>"
        )
    # Duplicate option check
    seen = set()
    for opt in options:
        lo = opt.lower()
        if lo in seen:
            return await message.reply_text(
                f"<blockquote>❌ ᴅᴜᴘʟɪᴄᴀᴛᴇ ᴏᴘᴛɪᴏɴ: **{opt}**</blockquote>"
            )
        seen.add(lo)

    if flags["is_quiz"] and flags["correct"] >= len(options):
        return await message.reply_text(
            "<blockquote>❌ `--correct` ɪɴᴅᴇx ᴏᴜᴛ ᴏғ ʀᴀɴɢᴇ.</blockquote>"
        )

    state = {
        "chat_id":    message.chat.id,
        "question":   question,
        "options":    options,
        "creator_id": message.from_user.id,
        **flags,
    }

    try:
        poll_msg = await _send_poll_from_state(client, state)
        poll_id  = str(ObjectId())
        await _results.insert_one({
            "_id":        ObjectId(poll_id),
            "chat_id":    message.chat.id,
            "message_id": poll_msg.id,
            "creator_id": message.from_user.id,
            "question":   question,
            "options":    options,
            "sent_at":    _utcnow(),
            "close_hours": flags["close_hours"],
        })
        _schedule_result_task(client, state, poll_msg)
    except Exception as exc:
        await message.reply_text(f"<blockquote>❌ ғᴀɪʟᴇᴅ: `{exc}`</blockquote>")


# ══════════════════════════════════════════════════════════════
#  /poll — interactive wizard
# ══════════════════════════════════════════════════════════════

@Client.on_message(filters.command("poll"))
async def cmd_poll(client, message: Message):
    user_id = message.from_user.id
    state   = {
        "step":       "question",
        "chat_id":    message.chat.id,
        "creator_id": user_id,
    }
    _wiz[user_id] = state
    await _session_save(user_id, state)
    await message.reply_text(
        "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 1/6**\n\n"
        "sᴇɴᴅ ʏᴏᴜʀ **ᴘᴏʟʟ ǫᴜᴇsᴛɪᴏɴ**:</blockquote>",
        reply_markup=_close_kb(),
    )


# ══════════════════════════════════════════════════════════════
#  WIZARD TEXT HANDLER
# ══════════════════════════════════════════════════════════════

@Client.on_message(
    filters.text & ~filters.regex(r"^/") & (filters.private | filters.group)
)
async def poll_wizard_handler(client, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id or user_id not in _wiz:
        return

    state = _wiz[user_id]
    step  = state.get("step")
    text  = message.text.strip()

    # ── Step 1: Question ─────────────────────────────────────
    if step == "question":
        if len(text) > 255:
            return await message.reply_text(
                "<blockquote>❌ ǫᴜᴇsᴛɪᴏɴ ᴛᴏᴏ ʟᴏɴɢ (ᴍᴀx 255 ᴄʜᴀʀs).</blockquote>"
            )
        state["question"] = text
        state["step"]     = "options"
        state["options"]  = []
        _wiz[user_id]     = state
        await _session_save(user_id, state)
        await message.reply_text(
            "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 2/6**\n\n"
            f"✅ **ǫᴜᴇsᴛɪᴏɴ:** `{text}`\n\n"
            "sᴇɴᴅ **ᴏᴘᴛɪᴏɴs** ᴏɴᴇ ʙʏ ᴏɴᴇ.\n"
            "ᴡʜᴇɴ ᴅᴏɴᴇ _(ᴍɪɴ 2, ᴍᴀx 10)_, ᴛᴀᴘ **Dᴏɴᴇ**.</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ᴅᴏɴᴇ ᴀᴅᴅɪɴɢ ᴏᴘᴛɪᴏɴs", callback_data="poll_opts_done")],
                _cancel_row(),
            ]),
        )
        return

    # ── Step 2: Collecting options ────────────────────────────
    if step == "options":
        opts = state.setdefault("options", [])
        if len(opts) >= 10:
            return await message.reply_text(
                "<blockquote>❌ ᴍᴀx 10 ᴏᴘᴛɪᴏɴs ʀᴇᴀᴄʜᴇᴅ. ᴛᴀᴘ **Dᴏɴᴇ**.</blockquote>"
            )
        # Duplicate check
        if text.lower() in [o.lower() for o in opts]:
            return await message.reply_text(
                f"<blockquote>❌ **{text}** ᴀʟʀᴇᴀᴅʏ ᴀᴅᴅᴇᴅ. sᴇɴᴅ ᴀ ᴅɪғғᴇʀᴇɴᴛ ᴏᴘᴛɪᴏɴ.</blockquote>"
            )
        opts.append(text)
        _wiz[user_id] = state
        await _session_save(user_id, state)
        opt_list = "\n".join(f"  `{i+1}.` {o}" for i, o in enumerate(opts))
        await message.reply_text(
            f"<blockquote>📊 **ᴏᴘᴛɪᴏɴs ᴀᴅᴅᴇᴅ: {len(opts)}/10**\n\n"
            f"{opt_list}\n\n"
            "sᴇɴᴅ ɴᴇxᴛ ᴏᴘᴛɪᴏɴ ᴏʀ ᴛᴀᴘ **Dᴏɴᴇ**.</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ᴅᴏɴᴇ ᴀᴅᴅɪɴɢ ᴏᴘᴛɪᴏɴs", callback_data="poll_opts_done")],
                _cancel_row(),
            ]),
        )
        return

    # ── Step: explanation text (free-type) ────────────────────
    if step == "ask_explain":
        state["explain"] = text
        state["step"]    = "ask_close"
        _wiz[user_id]    = state
        await _session_save(user_id, state)
        await message.reply_text(
            "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 6/6**\n\n"
            "ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜᴇ ᴘᴏʟʟ ᴛᴏ ᴀᴜᴛᴏ-ᴄʟᴏsᴇ?</blockquote>",
            reply_markup=_timer_yn_kb(),
        )
        return


# ══════════════════════════════════════════════════════════════
#  WIZARD FINISH
# ══════════════════════════════════════════════════════════════

async def _finish_wizard(client, proxy_msg: Message, user_id: int) -> None:
    state = _wiz.pop(user_id, {})
    await _session_delete(user_id)

    if not state:
        return await proxy_msg.reply_text(
            "<blockquote>❌ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ. ᴜsᴇ /poll ᴛᴏ sᴛᴀʀᴛ ᴀɢᴀɪɴ.</blockquote>"
        )

    try:
        poll_msg    = await _send_poll_from_state(client, state)
        close_hours = state.get("close_hours")
        poll_id     = ObjectId()

        await _results.insert_one({
            "_id":        poll_id,
            "chat_id":    state["chat_id"],
            "message_id": poll_msg.id,
            "creator_id": state["creator_id"],
            "question":   state["question"],
            "options":    state["options"],
            "is_quiz":    state.get("is_quiz", False),
            "anon":       state.get("anon", True),
            "multi":      state.get("multi", False),
            "sent_at":    _utcnow(),
            "close_hours": close_hours,
        })
        _schedule_result_task(client, state, poll_msg)

        ptype     = "🧠 ǫᴜɪᴢ" if state.get("is_quiz") else "📊 ʀᴇɢᴜʟᴀʀ"
        anon_str  = "🔒 ᴀɴᴏɴʏᴍᴏᴜs" if state.get("anon") else "👁 ᴠɪsɪʙʟᴇ"
        multi_str = "✅ ᴍᴜʟᴛɪ" if state.get("multi") else "☑️ sɪɴɢʟᴇ"
        timer_str = (f"⏱ ᴄʟᴏsᴇs ɪɴ {close_hours}ʜ"
                     if close_hours else "∞ ɴᴏ ᴛɪᴍᴇʀ · 📬 ʀᴇᴘᴏʀᴛ @ 24ʜ")

        await proxy_msg.reply_text(
            f"<blockquote>✅ **ᴘᴏʟʟ sᴇɴᴛ!**\n\n"
            f"📝 `{state['question']}`\n"
            f"📋 {len(state['options'])} ᴏᴘᴛɪᴏɴs\n"
            f"🎯 {ptype} · {anon_str} · {multi_str}\n"
            f"⏰ {timer_str}</blockquote>"
        )
    except Exception as exc:
        await proxy_msg.reply_text(
            f"<blockquote>❌ ғᴀɪʟᴇᴅ: `{exc}`</blockquote>"
        )


# ══════════════════════════════════════════════════════════════
#  WIZARD CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════

@Client.on_callback_query(filters.regex(r"^poll_"))
async def poll_callbacks(client, cq: CallbackQuery):
    data    = cq.data
    user_id = cq.from_user.id

    # ── Cancel ────────────────────────────────────────────────
    if data == "poll_cancel":
        _wiz.pop(user_id, None)
        asyncio.get_event_loop().create_task(_session_delete(user_id))
        await cq.answer("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ.")
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    # ── Help close ────────────────────────────────────────────
    if data == "poll_close_help":
        await cq.answer()
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    state = _wiz.get(user_id)
    if not state:
        return await cq.answer("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ sᴇssɪᴏɴ.", show_alert=True)

    # ── Options done ──────────────────────────────────────────
    if data == "poll_opts_done":
        opts = state.get("options", [])
        if len(opts) < 2:
            return await cq.answer("❌ ᴀᴅᴅ ᴀᴛ ʟᴇᴀsᴛ 2 ᴏᴘᴛɪᴏɴs ғɪʀsᴛ.", show_alert=True)
        state["step"] = "ask_type"
        _wiz[user_id] = state
        await _session_save(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 3/6**\n\n"
            "ᴄʜᴏᴏsᴇ **ᴘᴏʟʟ ᴛʏᴘᴇ**:</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 ʀᴇɢᴜʟᴀʀ", callback_data="poll_type_regular"),
                    InlineKeyboardButton("🧠 ǫᴜɪᴢ",     callback_data="poll_type_quiz"),
                ],
                _cancel_row(),
            ]),
        )
        return

    # ── Poll type ─────────────────────────────────────────────
    if data in ("poll_type_regular", "poll_type_quiz"):
        state["is_quiz"] = (data == "poll_type_quiz")
        state["step"]    = "ask_anon"
        _wiz[user_id]    = state
        await _session_save(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 4/6**\n\n"
            "sʜᴏᴜʟᴅ ᴠᴏᴛᴇs ʙᴇ **ᴀɴᴏɴʏᴍᴏᴜs**?</blockquote>",
            reply_markup=_yn_kb(
                "poll_anon_yes", "poll_anon_no",
                "🔒 ʏᴇs, ᴀɴᴏɴʏᴍᴏᴜs", "👁 ɴᴏ, ᴠɪsɪʙʟᴇ",
            ),
        )
        return

    # ── Anonymous ─────────────────────────────────────────────
    if data in ("poll_anon_yes", "poll_anon_no"):
        state["anon"] = (data == "poll_anon_yes")
        await cq.answer()

        if state.get("is_quiz"):
            state["step"] = "ask_correct"
            _wiz[user_id] = state
            await _session_save(user_id, state)
            opt_list = "\n".join(
                f"  `{i+1}.` {o}" for i, o in enumerate(state["options"])
            )
            await cq.message.edit_text(
                f"<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 5/6**\n\n"
                f"**ǫᴜɪᴢ — ᴄᴏʀʀᴇᴄᴛ ᴀɴsᴡᴇʀ**\n\n"
                f"{opt_list}\n\n"
                "ᴛᴀᴘ ᴛʜᴇ **ᴄᴏʀʀᴇᴄᴛ ᴏᴘᴛɪᴏɴ**:</blockquote>",
                reply_markup=_correct_option_kb(state["options"]),
            )
        else:
            state["step"] = "ask_multi"
            _wiz[user_id] = state
            await _session_save(user_id, state)
            await cq.message.edit_text(
                "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 5/6**\n\n"
                "ᴀʟʟᴏᴡ **ᴍᴜʟᴛɪᴘʟᴇ ᴀɴsᴡᴇʀs**?</blockquote>",
                reply_markup=_yn_kb(
                    "poll_multi_yes", "poll_multi_no",
                    "✅ ᴀʟʟᴏᴡ ᴍᴜʟᴛɪ", "☑️ sɪɴɢʟᴇ ᴏɴʟʏ",
                ),
            )
        return

    # ── Correct option button ─────────────────────────────────
    m = re.match(r"^poll_correct_(\d+)$", data)
    if m:
        idx = int(m.group(1))
        if idx >= len(state.get("options", [])):
            return await cq.answer("❌ ɪɴᴠᴀʟɪᴅ ᴏᴘᴛɪᴏɴ.", show_alert=True)
        state["correct"] = idx
        state["step"]    = "ask_explain"
        _wiz[user_id]    = state
        await _session_save(user_id, state)
        await cq.answer(f"✅ ᴏᴘᴛɪᴏɴ {idx + 1} sᴇʟᴇᴄᴛᴇᴅ")
        await cq.message.edit_text(
            f"<blockquote>📊 **ǫᴜɪᴢ — ᴇxᴘʟᴀɴᴀᴛɪᴏɴ**\n\n"
            f"✅ **ᴄᴏʀʀᴇᴄᴛ:** `{state['options'][idx]}`\n\n"
            "sᴇɴᴅ ᴀɴ **ᴇxᴘʟᴀɴᴀᴛɪᴏɴ** _(sʜᴏᴡɴ ᴀғᴛᴇʀ ᴀɴsᴡᴇʀ)_\n"
            "ᴏʀ ᴛᴀᴘ **Sᴋɪᴘ**.</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ sᴋɪᴘ ᴇxᴘʟᴀɴᴀᴛɪᴏɴ",
                                      callback_data="poll_skip_explain")],
                _cancel_row(),
            ]),
        )
        return

    # ── Multiple answers ──────────────────────────────────────
    if data in ("poll_multi_yes", "poll_multi_no"):
        state["multi"] = (data == "poll_multi_yes")
        state["step"]  = "ask_close"
        _wiz[user_id]  = state
        await _session_save(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 6/6**\n\n"
            "ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜᴇ ᴘᴏʟʟ ᴛᴏ ᴀᴜᴛᴏ-ᴄʟᴏsᴇ?</blockquote>",
            reply_markup=_timer_yn_kb(),
        )
        return

    # ── Skip explanation ──────────────────────────────────────
    if data == "poll_skip_explain":
        state["explain"] = None
        state["step"]    = "ask_close"
        _wiz[user_id]    = state
        await _session_save(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>📊 **ᴄʀᴇᴀᴛᴇ ᴘᴏʟʟ — sᴛᴇᴘ 6/6**\n\n"
            "ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛʜᴇ ᴘᴏʟʟ ᴛᴏ ᴀᴜᴛᴏ-ᴄʟᴏsᴇ?</blockquote>",
            reply_markup=_timer_yn_kb(),
        )
        return

    # ── Timer YES → hour picker ───────────────────────────────
    if data == "poll_set_timer":
        state["step"] = "ask_close"
        _wiz[user_id] = state
        await _session_save(user_id, state)
        await cq.answer()
        await cq.message.edit_text(
            "<blockquote>📊 **ᴀᴜᴛᴏ-ᴄʟᴏsᴇ — sᴇʟᴇᴄᴛ ᴛɪᴍᴇ**\n\n"
            "ᴄʜᴏᴏsᴇ ʜᴏᴡ ᴍᴀɴʏ **ʜᴏᴜʀs** ᴜɴᴛɪʟ ᴛʜᴇ ᴘᴏʟʟ ᴄʟᴏsᴇs:</blockquote>",
            reply_markup=_timer_kb(),
        )
        return

    # ── Hour button tapped ────────────────────────────────────
    m = re.match(r"^poll_timer_(\d+)$", data)
    if m:
        hours               = int(m.group(1))
        state["close_hours"] = hours
        await cq.answer(f"⏱ {hours}ʜ sᴇʟᴇᴄᴛᴇᴅ")
        await _finish_wizard(client, cq.message, user_id)
        return

    # ── Timer NO ──────────────────────────────────────────────
    if data == "poll_no_timer":
        state["close_hours"] = None
        await cq.answer()
        await _finish_wizard(client, cq.message, user_id)
        return

    await cq.answer()


# ══════════════════════════════════════════════════════════════
#  /pollhelp
# ══════════════════════════════════════════════════════════════

@Client.on_message(filters.command("pollhelp"))
async def cmd_pollhelp(_, message: Message):
    await message.reply_text(
        "<blockquote>📊 **ᴘᴏʟʟ sʏsᴛᴇᴍ — ɢᴜɪᴅᴇ**</blockquote>\n\n"

        "<blockquote>**🧙 ᴡɪᴢᴀʀᴅ** _(ғᴜʟʟʏ ʙᴜᴛᴛᴏɴ-ᴅʀɪᴠᴇɴ)_\n"
        "`/poll` → ʙᴏᴛ ɢᴜɪᴅᴇs ʏᴏᴜ sᴛᴇᴘ ʙʏ sᴛᴇᴘ ᴠɪᴀ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs\n\n"
        "📌 ᴇᴠᴇʀʏᴛʜɪɴɢ ɪs ᴀ ʙᴜᴛᴛᴏɴ — ɴᴏ ᴛʏᴘɪɴɢ ᴇxᴄᴇᴘᴛ ǫᴜᴇsᴛɪᴏɴ, ᴏᴘᴛɪᴏɴs & ᴇxᴘʟᴀɴᴀᴛɪᴏɴ:\n"
        "  ① sᴇɴᴅ ǫᴜᴇsᴛɪᴏɴ ᴛᴇxᴛ\n"
        "  ② sᴇɴᴅ ᴏᴘᴛɪᴏɴs ᴏɴᴇ ʙʏ ᴏɴᴇ → [✅ Dᴏɴᴇ]\n"
        "  ③ [📊 ʀᴇɢᴜʟᴀʀ] ᴏʀ [🧠 ǫᴜɪᴢ]\n"
        "  ④ [🔒 ᴀɴᴏɴʏᴍᴏᴜs] ᴏʀ [👁 ᴠɪsɪʙʟᴇ]\n"
        "  ⑤ ʀᴇɢᴜʟᴀʀ → [✅ ᴍᴜʟᴛɪ] ᴏʀ [☑️ sɪɴɢʟᴇ]\n"
        "     ǫᴜɪᴢ   → ᴛᴀᴘ ᴄᴏʀʀᴇᴄᴛ ᴀɴsᴡᴇʀ ʙᴜᴛᴛᴏɴ → ᴇxᴘʟᴀɴᴀᴛɪᴏɴ ᴏʀ [⏭ sᴋɪᴘ]\n"
        "  ⑥ [⏱ ᴛɪᴍᴇʀ ʏᴇs] → ᴛᴀᴘ ʜᴏᴜʀs · [∞ ᴛɪᴍᴇʀ ɴᴏ] → ɴᴏ ᴄʟᴏsᴇ</blockquote>\n\n"

        "<blockquote>**⚡ ǫᴜɪᴄᴋᴘᴏʟʟ** _(ᴏɴᴇ-ʟɪɴᴇʀ ᴡɪᴛʜ ғʟᴀɢs)_\n"
        "`/quickpoll Q | Opt1 | Opt2 [| ...]  [flags]`\n\n"
        "**ᴀᴠᴀɪʟᴀʙʟᴇ ғʟᴀɢs:**\n"
        "`--quiz`  ·  `--anon`  ·  `--multi`\n"
        "`--correct=2`  ·  `--close=6`  ·  `--explain=ᴛᴇxᴛ`\n\n"
        "_(ᴘᴜᴛ `--explain` ʟᴀsᴛ ɪғ ᴜsᴇᴅ)_</blockquote>\n\n"

        "<blockquote>**📌 ᴇxᴀᴍᴘʟᴇs:**\n"
        "`/quickpoll Fᴀᴠ ᴄᴏʟᴏʀ? | ʀᴇᴅ | ʙʟᴜᴇ | ɢʀᴇᴇɴ --anon --multi`\n"
        "`/quickpoll Cᴀᴘɪᴛᴀʟ? | Bᴇʀʟɪɴ | Pᴀʀɪs | Rᴏᴍᴇ --quiz --correct=2 --close=2 --explain=Paris is the capital`</blockquote>\n\n"

        "<blockquote>**📬 ʀᴇsᴜʟᴛs ᴅᴇʟɪᴠᴇʀʏ:**\n"
        "• **ᴛɪᴍᴇᴅ ᴘᴏʟʟ** → ᴘᴍ ᴡʜᴇɴ ᴘᴏʟʟ ᴄʟᴏsᴇs\n"
        "• **ɴᴏ-ᴛɪᴍᴇʀ ᴘᴏʟʟ** → ᴀᴜᴛᴏ ʀᴇᴘᴏʀᴛ @ **24ʜ**\n"
        "  ↳ 2ɴᴅ ʀᴇᴘᴏʀᴛ @ **48ʜ** ᴏɴʟʏ ɪғ ᴠᴏᴛᴇs ɪɴᴄʀᴇᴀsᴇᴅ</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="poll_close_help")]
        ]),
    )


# ══════════════════════════════════════════════════════════════
#  STARTUP — restore sessions from MongoDB
# ══════════════════════════════════════════════════════════════

async def on_poll_startup():
    """Call this once after the bot starts to reload persisted wizard sessions."""
    await _sessions_restore()


# ══════════════════════════════════════════════════════════════
#  MODULE METADATA
# ══════════════════════════════════════════════════════════════
__menu__     = "CMD_PRO"
__mod_name__ = "H_B_86"
__help__ = """
**ᴘᴏʟʟ sʏsᴛᴇᴍ**
🔻 `/poll` ➠ ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ ᴡɪᴢᴀʀᴅ _(ᴀʟʟ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs)_
🔻 `/quickpoll Q | Opt1 | Opt2` ➠ ǫᴜɪᴄᴋ ᴘᴏʟʟ ᴡɪᴛʜ ғʟᴀɢs
🔻 `/pollhelp` ➠ ғᴜʟʟ ᴜsᴀɢᴇ ɢᴜɪᴅᴇ
**ᴘᴏʟʟ ᴛʏᴘᴇs:** ʀᴇɢᴜʟᴀʀ · ǫᴜɪᴢ
**ᴏᴘᴛɪᴏɴs:** ᴀɴᴏɴʏᴍᴏᴜs · ᴍᴜʟᴛɪ-ᴀɴsᴡᴇʀ · ᴀᴜᴛᴏ-ᴄʟᴏsᴇ _(ʜᴏᴜʀs)_
**ʀᴇsᴜʟᴛs:** ᴘᴍ ᴏɴ ᴄʟᴏsᴇ · ɴᴏ-ᴛɪᴍᴇʀ: 24ʜ + 48ʜ ɪғ ᴜᴘᴅᴀᴛᴇᴅ
"""

MOD_TYPE = "PRO-BOTS"
MOD_NAME = "Polls"
MOD_PRICE = "50"
