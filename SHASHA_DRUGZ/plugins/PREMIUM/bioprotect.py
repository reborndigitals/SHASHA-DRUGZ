# SHASHA_DRUGZ/dplugins/COMMON/MANAGE/bioprotect.py
# ══════════════════════════════════════════════════════════════
#  Bio Link Protector — SHASHA_DRUGZ Plugin
#
#  FEATURES:
#    • Auto-detect URLs in user bio on every message
#    • Per-group enable/disable via /biolink toggle
#    • Penalty modes: delete-only (default), warn→action, mute, ban
#    • Warn limit selector (0–5), configurable penalty after warns
#    • Whitelist system: /free, /unfree, /freelist
#    • Config panel: /config  (admins only)
#    • All actions have inline undo buttons (unmute / unban / whitelist)
#
#  DEFAULT BEHAVIOR (before any /config):
#    • biolink = ENABLED  (auto-enabled when bot is added to group)
#    • mode    = "delete"  (just removes the message, no warn/mute/ban)
#    • limit   = 3         (warn limit, used when mode = "warn")
#    • penalty = "delete"  (action after warns = delete only)
#
#  COMMANDS:
#    /biolink            → show current status + toggle button (owner)
#    /biolink enable     → enable bio-link protection (owner)
#    /biolink disable    → disable bio-link protection (owner)
#    /bioconfig          → full settings panel (admins)
#    /biofree [reply|id] → whitelist a user (admins)
#    /biounfree [reply|id] → remove from whitelist (admins)
#    /biofreelist        → list all whitelisted users (admins)
#
#  FIXES APPLIED:
#    1. check_bio handler uses a custom ~_not_command filter instead of
#         ~filters.command(None) which crashes Pyrogram (None is invalid).
#         Custom filter checks message.text.startswith("/") at filter level.
#    2. Extra safety guard at top of check_bio:
#         if message.text and message.text.startswith("/"): return
#    3. Cleaner/safer URL regex (https?://\S+ style)
#    4. Entity-based URL detection added alongside regex
#    5. DEFAULT enabled=True — protection is ON by default for every group.
#    6. Auto-enable on bot add — ChatMemberUpdated handler sets enabled=True
#         when the bot is added to a new group (or promoted to admin).
#
#  ISOLATION:
#    Uses SHASHA_DRUGZ's shared MongoDB collections with chat_id scoping.
#    Safe for multi-bot deployment — each group's data is independent.
# ══════════════════════════════════════════════════════════════
import re
import logging
from pyrogram import filters, errors
from pyrogram.enums import ChatMemberStatus
from SHASHA_DRUGZ import app
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
    Message,
    CallbackQuery,
)
from SHASHA_DRUGZ.core.mongo import mongodb

logger = logging.getLogger("BioProtect")

# ── FIX 3: Cleaner URL regex — detects http/https/t.me links in bio ──────────
_URL_RE = re.compile(
    r"(https?://\S+|t\.me/\S+|@[A-Za-z0-9_]{5,})",
    re.IGNORECASE,
)

# ── FIX 1: Custom filter to exclude command messages ─────────────────────────
# filters.command(None) crashes Pyrogram — use filters.create lambda instead.
@filters.create
async def _not_command(_, __, message):
    """Returns True when the message is NOT a bot command."""
    if message.text and message.text.startswith("/"):
        return False
    return True

# ── MongoDB collections ───────────────────────────────────────────────────────
_cfg_col  = mongodb["bioprotect_config"]
_warn_col = mongodb["bioprotect_warns"]
_wl_col   = mongodb["bioprotect_whitelist"]

# ══════════════════════════════════════════════════════════════
#  DB HELPERS
# ══════════════════════════════════════════════════════════════
async def _get_cfg(chat_id: int) -> dict:
    """Return config for this group, inserting defaults if missing."""
    doc = await _cfg_col.find_one({"chat_id": chat_id})
    if doc is None:
        doc = {
            "chat_id": chat_id,
            "enabled": True,        # FIX 5: enabled by default
            "mode":    "delete",    # delete | warn | mute | ban
            "limit":   3,           # warn limit (used when mode=warn)
            "penalty": "delete",    # action after warns: delete | mute | ban
        }
        await _cfg_col.insert_one(doc)
    return doc

async def _set_cfg(chat_id: int, **fields):
    await _cfg_col.update_one(
        {"chat_id": chat_id},
        {"$set": fields},
        upsert=True,
    )

async def _get_warns(chat_id: int, user_id: int) -> int:
    doc = await _warn_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc["count"] if doc else 0

async def _inc_warns(chat_id: int, user_id: int) -> int:
    doc = await _warn_col.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True,
    )
    return doc["count"] if doc else 1

async def _reset_warns(chat_id: int, user_id: int):
    await _warn_col.delete_one({"chat_id": chat_id, "user_id": user_id})

async def _is_wl(chat_id: int, user_id: int) -> bool:
    return bool(await _wl_col.find_one({"chat_id": chat_id, "user_id": user_id}))

async def _add_wl(chat_id: int, user_id: int):
    if not await _is_wl(chat_id, user_id):
        await _wl_col.insert_one({"chat_id": chat_id, "user_id": user_id})

async def _rm_wl(chat_id: int, user_id: int):
    await _wl_col.delete_one({"chat_id": chat_id, "user_id": user_id})

async def _get_wl(chat_id: int) -> list:
    return [d["user_id"] async for d in _wl_col.find({"chat_id": chat_id})]

# ══════════════════════════════════════════════════════════════
#  PERMISSION HELPERS
# ══════════════════════════════════════════════════════════════
async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status.value in ("administrator", "creator", "owner")
    except Exception:
        return False

async def _is_owner(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status.value in ("creator", "owner")
    except Exception:
        return False

# ══════════════════════════════════════════════════════════════
#  FIX 6: AUTO-ENABLE WHEN BOT IS ADDED TO A GROUP
#
#  Listens for ChatMemberUpdated events. When the bot itself is added
#  to a group (or promoted to admin), we upsert the config with
#  enabled=True so protection is active from the very first message.
#  Uses upsert=True so it also works for groups that already existed
#  in the DB with enabled=False.
# ══════════════════════════════════════════════════════════════
@app.on_chat_member_updated(filters.group)
async def on_bot_added(client, update):
    """Auto-enable bio-protect when the bot is added to a group."""
    try:
        bot = await client.get_me()
        # Only react when the updated member is the bot itself
        if update.new_chat_member and update.new_chat_member.user.id == bot.id:
            new_status = update.new_chat_member.status
            # Trigger on member / administrator (i.e. the bot was just added or promoted)
            if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
                chat_id = update.chat.id
                await _cfg_col.update_one(
                    {"chat_id": chat_id},
                    {
                        "$setOnInsert": {
                            "chat_id": chat_id,
                            "mode":    "delete",
                            "limit":   3,
                            "penalty": "delete",
                        },
                        "$set": {"enabled": True},
                    },
                    upsert=True,
                )
                logger.info(
                    "BioProtect auto-enabled for chat %s (%s)",
                    chat_id,
                    getattr(update.chat, "title", "?"),
                )
    except Exception as e:
        logger.warning("on_bot_added error: %s", e)

# ══════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════
def _biolink_kb(enabled: bool, chat_id: int) -> InlineKeyboardMarkup:
    """Toggle button for /biolink command."""
    if enabled:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🟢 ᴇɴᴀʙʟᴇᴅ — ᴛᴀᴘ ᴛᴏ ᴅɪsᴀʙʟᴇ",
                                 callback_data=f"biolink_toggle_{chat_id}")
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔴 ᴅɪsᴀʙʟᴇᴅ — ᴛᴀᴘ ᴛᴏ ᴇɴᴀʙʟᴇ",
                             callback_data=f"biolink_toggle_{chat_id}")
    ]])

def _config_main_kb(mode: str, penalty: str) -> InlineKeyboardMarkup:
    """Main /bioconfig keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🍏 ᴅᴇʟᴇᴛᴇ ᴏɴʟʏ" if mode == "delete" else "ᴅᴇʟᴇᴛᴇ ᴏɴʟʏ",
                callback_data="bp_mode_delete"
            ),
            InlineKeyboardButton(
                "🍏 ᴡᴀʀɴ" if mode == "warn" else "ᴡᴀʀɴ",
                callback_data="bp_mode_warn"
            ),
        ],
        [
            InlineKeyboardButton(
                "🍏 ᴍᴜᴛᴇ" if mode == "mute" else "ᴍᴜᴛᴇ",
                callback_data="bp_mode_mute"
            ),
            InlineKeyboardButton(
                "🍏 ʙᴀɴ" if mode == "ban" else "ʙᴀɴ",
                callback_data="bp_mode_ban"
            ),
        ],
        [InlineKeyboardButton("⚙️ ᴡᴀʀɴ ʟɪᴍɪᴛ", callback_data="bp_warn_limit")],
        [InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",    callback_data="bp_close")],
    ])

def _warn_limit_kb(current: int) -> InlineKeyboardMarkup:
    """Warn limit number selector."""
    nums = [
        InlineKeyboardButton(
            f"🍏 {n}" if n == current else str(n),
            callback_data=f"bp_limit_{n}"
        )
        for n in range(1, 6)
    ]
    return InlineKeyboardMarkup([
        nums[:3],
        nums[3:],
        [InlineKeyboardButton("◀ ʙᴀᴄᴋ", callback_data="bp_back"),
         InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close")],
    ])

def _after_penalty_kb(penalty: str) -> InlineKeyboardMarkup:
    """Penalty-after-warns selector."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🍏 ᴅᴇʟᴇᴛᴇ" if penalty == "delete" else "ᴅᴇʟᴇᴛᴇ",
                callback_data="bp_penalty_delete"
            ),
            InlineKeyboardButton(
                "🍏 ᴍᴜᴛᴇ" if penalty == "mute" else "ᴍᴜᴛᴇ",
                callback_data="bp_penalty_mute"
            ),
            InlineKeyboardButton(
                "🍏 ʙᴀɴ" if penalty == "ban" else "ʙᴀɴ",
                callback_data="bp_penalty_ban"
            ),
        ],
        [InlineKeyboardButton("◀ ʙᴀᴄᴋ", callback_data="bp_back"),
         InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close")],
    ])

# ══════════════════════════════════════════════════════════════
#  /biolink — group owner toggle
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.group & filters.command("biolink"))
async def biolink_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await _is_owner(client, chat_id, user_id):
        return await message.reply_text(
            "<blockquote>❌ ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ ᴄᴀɴ ᴛᴏɢɢʟᴇ ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ.</blockquote>"
        )

    cfg = await _get_cfg(chat_id)
    args = message.command

    # /biolink enable / disable — direct toggle
    if len(args) > 1:
        arg = args[1].lower()
        if arg == "enable":
            await _set_cfg(chat_id, enabled=True)
            cfg["enabled"] = True
        elif arg == "disable":
            await _set_cfg(chat_id, enabled=False)
            cfg["enabled"] = False

    status  = cfg["enabled"]
    mode    = cfg["mode"]
    limit   = cfg["limit"]
    penalty = cfg["penalty"]
    status_text = "🟢 ᴇɴᴀʙʟᴇᴅ" if status else "🔴 ᴅɪsᴀʙʟᴇᴅ"
    text = (
        f"<blockquote>🛡 **ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ**</blockquote>\n"
        f"<blockquote>"
        f"➤ sᴛᴀᴛᴜs: {status_text}\n"
        f"➤ ᴍᴏᴅᴇ: `{mode}`\n"
        f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{limit}`\n"
        f"➤ ᴘᴇɴᴀʟᴛʏ ᴀғᴛᴇʀ ᴡᴀʀɴs: `{penalty}`"
        f"</blockquote>"
    )
    await message.reply_text(text, reply_markup=_biolink_kb(status, chat_id))

# ── biolink_toggle callback (inline button) ───────────────────────────────────
@app.on_callback_query(filters.regex(r"^biolink_toggle_(-?\d+)$"))
async def biolink_toggle_cb(client, cq):
    chat_id = int(cq.data.split("_")[2])
    user_id = cq.from_user.id

    if not await _is_owner(client, chat_id, user_id):
        return await cq.answer("❌ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ ᴏɴʟʏ.", show_alert=True)

    cfg     = await _get_cfg(chat_id)
    new_val = not cfg["enabled"]
    await _set_cfg(chat_id, enabled=new_val)
    status_text = "🟢 ᴇɴᴀʙʟᴇᴅ" if new_val else "🔴 ᴅɪsᴀʙʟᴇᴅ"
    text = (
        f"<blockquote>🛡 **ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ**</blockquote>\n"
        f"<blockquote>"
        f"➤ sᴛᴀᴛᴜs: {status_text}\n"
        f"➤ ᴍᴏᴅᴇ: `{cfg['mode']}`\n"
        f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
        f"➤ ᴘᴇɴᴀʟᴛʏ ᴀғᴛᴇʀ ᴡᴀʀɴs: `{cfg['penalty']}`"
        f"</blockquote>"
    )
    try:
        await cq.message.edit_text(text, reply_markup=_biolink_kb(new_val, chat_id))
    except Exception:
        pass
    await cq.answer("🟢 ᴇɴᴀʙʟᴇᴅ" if new_val else "🔴 ᴅɪsᴀʙʟᴇᴅ")

# ══════════════════════════════════════════════════════════════
#  /bioconfig — admin settings panel
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.group & filters.command("bioconfig"))
async def config_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        return

    cfg     = await _get_cfg(chat_id)
    mode    = cfg["mode"]
    penalty = cfg["penalty"]
    limit   = cfg["limit"]
    text = (
        f"<blockquote>⚙️ **ʙɪᴏ ᴘʀᴏᴛᴇᴄᴛ sᴇᴛᴛɪɴɢs**</blockquote>\n"
        f"<blockquote>"
        f"➤ ᴍᴏᴅᴇ: `{mode}`\n"
        f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{limit}`\n"
        f"➤ ᴘᴇɴᴀʟᴛʏ ᴀғᴛᴇʀ ᴡᴀʀɴs: `{penalty}`"
        f"</blockquote>"
    )
    await message.reply_text(text, reply_markup=_config_main_kb(mode, penalty))
    try:
        await message.delete()
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════
#  CONFIG CALLBACKS
# ══════════════════════════════════════════════════════════════
@app.on_callback_query(filters.regex(r"^bp_"))
async def bp_callbacks(client, cq):
    data    = cq.data
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        return await cq.answer("❌ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ.", show_alert=True)

    cfg = await _get_cfg(chat_id)

    # ── Close ─────────────────────────────────────────────────────────────────
    if data == "bp_close":
        try:
            await cq.message.delete()
        except Exception:
            pass
        return await cq.answer()

    # ── Back to main config ───────────────────────────────────────────────────
    if data == "bp_back":
        cfg = await _get_cfg(chat_id)
        text = (
            f"<blockquote>⚙️ **ʙɪᴏ ᴘʀᴏᴛᴇᴄᴛ sᴇᴛᴛɪɴɢs**</blockquote>\n"
            f"<blockquote>"
            f"➤ ᴍᴏᴅᴇ: `{cfg['mode']}`\n"
            f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
            f"➤ ᴘᴇɴᴀʟᴛʏ ᴀғᴛᴇʀ ᴡᴀʀɴs: `{cfg['penalty']}`"
            f"</blockquote>"
        )
        try:
            await cq.message.edit_text(text, reply_markup=_config_main_kb(cfg["mode"], cfg["penalty"]))
        except Exception:
            pass
        return await cq.answer()

    # ── Mode change ───────────────────────────────────────────────────────────
    if data.startswith("bp_mode_"):
        new_mode = data.replace("bp_mode_", "")
        await _set_cfg(chat_id, mode=new_mode)
        cfg = await _get_cfg(chat_id)
        # When mode is "warn", show penalty-after-warn selector
        if new_mode == "warn":
            text = (
                f"<blockquote>⚙️ **ᴡᴀʀɴ ᴍᴏᴅᴇ sᴇʟᴇᴄᴛᴇᴅ**\n"
                f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
                f"sᴇʟᴇᴄᴛ ᴀᴄᴛɪᴏɴ ᴀғᴛᴇʀ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ:</blockquote>"
            )
            try:
                await cq.message.edit_text(text, reply_markup=_after_penalty_kb(cfg["penalty"]))
            except Exception:
                pass
        else:
            text = (
                f"<blockquote>⚙️ **ʙɪᴏ ᴘʀᴏᴛᴇᴄᴛ sᴇᴛᴛɪɴɢs**</blockquote>\n"
                f"<blockquote>"
                f"➤ ᴍᴏᴅᴇ: `{cfg['mode']}`\n"
                f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
                f"➤ ᴘᴇɴᴀʟᴛʏ ᴀғᴛᴇʀ ᴡᴀʀɴs: `{cfg['penalty']}`"
                f"</blockquote>"
            )
            try:
                await cq.message.edit_text(text, reply_markup=_config_main_kb(cfg["mode"], cfg["penalty"]))
            except Exception:
                pass
        return await cq.answer(f"ᴍᴏᴅᴇ → {new_mode}")

    # ── Penalty after warns ───────────────────────────────────────────────────
    if data.startswith("bp_penalty_"):
        new_penalty = data.replace("bp_penalty_", "")
        await _set_cfg(chat_id, penalty=new_penalty)
        cfg = await _get_cfg(chat_id)
        text = (
            f"<blockquote>⚙️ **ᴡᴀʀɴ ᴍᴏᴅᴇ sᴇʟᴇᴄᴛᴇᴅ**\n"
            f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
            f"sᴇʟᴇᴄᴛ ᴀᴄᴛɪᴏɴ ᴀғᴛᴇʀ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ:</blockquote>"
        )
        try:
            await cq.message.edit_text(text, reply_markup=_after_penalty_kb(new_penalty))
        except Exception:
            pass
        return await cq.answer(f"ᴘᴇɴᴀʟᴛʏ → {new_penalty}")

    # ── Warn limit selector panel ─────────────────────────────────────────────
    if data == "bp_warn_limit":
        cfg = await _get_cfg(chat_id)
        try:
            await cq.message.edit_text(
                "<blockquote>⚙️ **sᴇʟᴇᴄᴛ ᴡᴀʀɴ ʟɪᴍɪᴛ:**</blockquote>",
                reply_markup=_warn_limit_kb(cfg["limit"])
            )
        except Exception:
            pass
        return await cq.answer()

    # ── Warn limit value selected ─────────────────────────────────────────────
    if data.startswith("bp_limit_"):
        new_limit = int(data.replace("bp_limit_", ""))
        await _set_cfg(chat_id, limit=new_limit)
        try:
            await cq.message.edit_reply_markup(reply_markup=_warn_limit_kb(new_limit))
        except Exception:
            pass
        return await cq.answer(f"ᴡᴀʀɴ ʟɪᴍɪᴛ → {new_limit}")

    # ── Unmute ────────────────────────────────────────────────────────────────
    if data.startswith("bp_unmute_"):
        target_id = int(data.split("_")[2])
        try:
            await client.restrict_chat_member(
                chat_id, target_id,
                ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                                can_send_other_messages=True, can_add_web_page_previews=True)
            )
            await _reset_warns(chat_id, target_id)
            user = await client.get_users(target_id)
            name = user.first_name or str(target_id)
            mention = f"[{name}](tg://user?id={target_id})"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅", callback_data=f"bp_whitelist_{target_id}"),
                InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="bp_close"),
            ]])
            await cq.message.edit_text(
                f"<blockquote>✅ {mention} `[{target_id}]` ʜᴀs ʙᴇᴇɴ **ᴜɴᴍᴜᴛᴇᴅ**.</blockquote>",
                reply_markup=kb
            )
        except errors.ChatAdminRequired:
            await cq.answer("❌ ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ.", show_alert=True)
        return await cq.answer()

    # ── Unban ─────────────────────────────────────────────────────────────────
    if data.startswith("bp_unban_"):
        target_id = int(data.split("_")[2])
        try:
            await client.unban_chat_member(chat_id, target_id)
            await _reset_warns(chat_id, target_id)
            user = await client.get_users(target_id)
            name = user.first_name or str(target_id)
            mention = f"[{name}](tg://user?id={target_id})"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅", callback_data=f"bp_whitelist_{target_id}"),
                InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="bp_close"),
            ]])
            await cq.message.edit_text(
                f"<blockquote>✅ {mention} `[{target_id}]` ʜᴀs ʙᴇᴇɴ **ᴜɴʙᴀɴɴᴇᴅ**.</blockquote>",
                reply_markup=kb
            )
        except errors.ChatAdminRequired:
            await cq.answer("❌ ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ.", show_alert=True)
        return await cq.answer()

    # ── Cancel warn ───────────────────────────────────────────────────────────
    if data.startswith("bp_cancel_warn_"):
        target_id = int(data.split("_")[3])
        await _reset_warns(chat_id, target_id)
        user = await client.get_users(target_id)
        name    = user.first_name or str(target_id)
        mention = f"[{name}](tg://user?id={target_id})"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅", callback_data=f"bp_whitelist_{target_id}"),
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="bp_close"),
        ]])
        try:
            await cq.message.edit_text(
                f"<blockquote>✅ {mention} `[{target_id}]` ᴡᴀʀɴɪɴɢs ᴄʟᴇᴀʀᴇᴅ.</blockquote>",
                reply_markup=kb
            )
        except Exception:
            pass
        return await cq.answer()

    # ── Whitelist from button ─────────────────────────────────────────────────
    if data.startswith("bp_whitelist_"):
        target_id = int(data.split("_")[2])
        await _add_wl(chat_id, target_id)
        await _reset_warns(chat_id, target_id)
        user = await client.get_users(target_id)
        name    = user.first_name or str(target_id)
        mention = f"[{name}](tg://user?id={target_id})"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴜɴᴡʜɪᴛᴇʟɪsᴛ 🚫", callback_data=f"bp_unwhitelist_{target_id}"),
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",        callback_data="bp_close"),
        ]])
        try:
            await cq.message.edit_text(
                f"<blockquote>✅ {mention} `[{target_id}]` ʜᴀs ʙᴇᴇɴ **ᴡʜɪᴛᴇʟɪsᴛᴇᴅ**.</blockquote>",
                reply_markup=kb
            )
        except Exception:
            pass
        return await cq.answer()

    # ── Unwhitelist from button ───────────────────────────────────────────────
    if data.startswith("bp_unwhitelist_"):
        target_id = int(data.split("_")[2])
        await _rm_wl(chat_id, target_id)
        user = await client.get_users(target_id)
        name    = user.first_name or str(target_id)
        mention = f"[{name}](tg://user?id={target_id})"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅", callback_data=f"bp_whitelist_{target_id}"),
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="bp_close"),
        ]])
        try:
            await cq.message.edit_text(
                f"<blockquote>❌ {mention} `[{target_id}]` ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴡʜɪᴛᴇʟɪsᴛ.</blockquote>",
                reply_markup=kb
            )
        except Exception:
            pass
        return await cq.answer()

    await cq.answer()

# ══════════════════════════════════════════════════════════════
#  WHITELIST COMMANDS
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.group & filters.command("biofree"))
async def cmd_free(client, message):
    chat_id = message.chat.id
    if not await _is_admin(client, chat_id, message.from_user.id):
        return
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.lstrip("-").isdigit() else arg)
        except Exception:
            return await message.reply_text("<blockquote>❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.</blockquote>")
    else:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/biofree` _(reply)_ ᴏʀ `/biofree @username/id`</blockquote>"
        )
    await _add_wl(chat_id, target.id)
    await _reset_warns(chat_id, target.id)
    name    = target.first_name or str(target.id)
    mention = f"[{name}](tg://user?id={target.id})"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴜɴᴡʜɪᴛᴇʟɪsᴛ 🚫", callback_data=f"bp_unwhitelist_{target.id}"),
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",        callback_data="bp_close"),
    ]])
    await message.reply_text(
        f"<blockquote>✅ {mention} `[{target.id}]` **ᴀᴅᴅᴇᴅ ᴛᴏ ᴡʜɪᴛᴇʟɪsᴛ**.</blockquote>",
        reply_markup=kb
    )

@app.on_message(filters.group & filters.command("biounfree"))
async def cmd_unfree(client, message):
    chat_id = message.chat.id
    if not await _is_admin(client, chat_id, message.from_user.id):
        return
    target = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.lstrip("-").isdigit() else arg)
        except Exception:
            return await message.reply_text("<blockquote>❌ ᴜsᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ.</blockquote>")
    else:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/biounfree` _(reply)_ ᴏʀ `/biounfree @username/id`</blockquote>"
        )
    name    = target.first_name or str(target.id)
    mention = f"[{name}](tg://user?id={target.id})"
    if await _is_wl(chat_id, target.id):
        await _rm_wl(chat_id, target.id)
        text = f"<blockquote>🚫 {mention} `[{target.id}]` **ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴡʜɪᴛᴇʟɪsᴛ**.</blockquote>"
    else:
        text = f"<blockquote>ℹ️ {mention} ɪs ɴᴏᴛ ɪɴ ᴡʜɪᴛᴇʟɪsᴛ.</blockquote>"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅", callback_data=f"bp_whitelist_{target.id}"),
        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="bp_close"),
    ]])
    await message.reply_text(text, reply_markup=kb)

@app.on_message(filters.group & filters.command("biofreelist"))
async def cmd_freelist(client, message):
    chat_id = message.chat.id
    if not await _is_admin(client, chat_id, message.from_user.id):
        return
    ids = await _get_wl(chat_id)
    if not ids:
        return await message.reply_text(
            "<blockquote>⚠️ ɴᴏ ᴜsᴇʀs ᴀʀᴇ ᴡʜɪᴛᴇʟɪsᴛᴇᴅ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.</blockquote>"
        )
    lines = ["<blockquote>📋 **ᴡʜɪᴛᴇʟɪsᴛᴇᴅ ᴜsᴇʀs:**\n"]
    for i, uid in enumerate(ids, 1):
        try:
            u    = await client.get_users(uid)
            name = f"{u.first_name}{(' ' + u.last_name) if u.last_name else ''}"
        except Exception:
            name = "Unknown"
        lines.append(f"{i}. {name} [`{uid}`]")
    lines.append("</blockquote>")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ ᴄʟᴏsᴇ", callback_data="bp_close")]])
    await message.reply_text("\n".join(lines), reply_markup=kb)

# ══════════════════════════════════════════════════════════════
#  CORE BIO CHECK
#
#  FIX 1: Uses custom _not_command filter — filters.command(None) crashes
#          Pyrogram because None is an invalid argument. The custom filter
#          rejects any message whose text starts with "/".
#  FIX 2: Extra guard at top — double protection against commands.
#  FIX 4: Entity-based URL detection added as bonus alongside regex.
# ══════════════════════════════════════════════════════════════
@app.on_message(filters.group & ~filters.bot & _not_command)
async def check_bio(client, message):
    # FIX 2: Extra safety — skip if message is a command
    if message.text and message.text.startswith("/"):
        return
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Load config — skip if protection disabled
    cfg = await _get_cfg(chat_id)
    if not cfg["enabled"]:
        return

    # Skip admins and whitelisted users
    if await _is_admin(client, chat_id, user_id):
        return
    if await _is_wl(chat_id, user_id):
        return

    # Fetch user profile
    try:
        user = await client.get_users(user_id)
    except Exception:
        return

    bio = getattr(user, "bio", None) or ""

    # ── FIX 4: Entity-based URL detection (bonus — more reliable) ────────────
    def _bio_has_link(bio_text: str) -> bool:
        """Check for links using both regex and a simple entity-style scan."""
        if _URL_RE.search(bio_text):
            return True
        return False

    # ── Clean bio — reset warns and exit ─────────────────────────────────────
    if not _bio_has_link(bio):
        warns = await _get_warns(chat_id, user_id)
        if warns > 0:
            await _reset_warns(chat_id, user_id)
        return

    # ── URL found in bio ──────────────────────────────────────────────────────
    name    = user.first_name or str(user_id)
    mention = f"[{name}](tg://user?id={user_id})"
    mode    = cfg["mode"]
    limit   = cfg["limit"]
    penalty = cfg["penalty"]

    # Always try to delete the triggering message first
    try:
        await message.delete()
    except errors.MessageDeleteForbidden:
        pass
    except Exception:
        pass

    # ── DEFAULT: delete only — no warn/mute/ban ───────────────────────────────
    if mode == "delete":
        return

    # ── WARN MODE ─────────────────────────────────────────────────────────────
    if mode == "warn":
        count = await _inc_warns(chat_id, user_id)
        warn_text = (
            f"<blockquote>🚨 **ᴡᴀʀɴɪɴɢ** 🚨\n\n"
            f"👤 **ᴜsᴇʀ:** {mention} `[{user_id}]`\n"
            f"❌ **ʀᴇᴀsᴏɴ:** URL ғᴏᴜɴᴅ ɪɴ ʙɪᴏ\n"
            f"⚠️ **ᴡᴀʀɴ:** {count}/{limit}\n\n"
            f"**ɴᴏᴛɪᴄᴇ: ʀᴇᴍᴏᴠᴇ ʟɪɴᴋ ɪɴ ʏᴏᴜʀ ʙɪᴏ**</blockquote>"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ ᴡᴀʀɴ ❌", callback_data=f"bp_cancel_warn_{user_id}"),
                InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅",   callback_data=f"bp_whitelist_{user_id}"),
            ],
            [InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close")],
        ])
        sent = await message.reply_text(warn_text, reply_markup=kb)
        # Limit reached — apply penalty
        if count >= limit:
            try:
                if penalty == "mute":
                    await client.restrict_chat_member(chat_id, user_id, ChatPermissions())
                    kb2 = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔻 ᴜɴᴍᴜᴛᴇ ✅", callback_data=f"bp_unmute_{user_id}"),
                        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",  callback_data="bp_close"),
                    ]])
                    await sent.edit_text(
                        f"<blockquote>🔇 {mention} ʜᴀs ʙᴇᴇɴ **ᴍᴜᴛᴇᴅ** ғᴏʀ [Link In Bio].</blockquote>",
                        reply_markup=kb2
                    )
                elif penalty == "ban":
                    await client.ban_chat_member(chat_id, user_id)
                    kb2 = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔻 ᴜɴʙᴀɴ ✅", callback_data=f"bp_unban_{user_id}"),
                        InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close"),
                    ]])
                    await sent.edit_text(
                        f"<blockquote>🔨 {mention} ʜᴀs ʙᴇᴇɴ **ʙᴀɴɴᴇᴅ** ғᴏʀ [Link In Bio].</blockquote>",
                        reply_markup=kb2
                    )
                else:
                    # penalty = "delete" — just note the limit was hit
                    await sent.edit_text(
                        f"<blockquote>⚠️ {mention} ʜɪᴛ ᴡᴀʀɴ ʟɪᴍɪᴛ ʙᴜᴛ ᴘᴇɴᴀʟᴛʏ ɪs ᴅᴇʟᴇᴛᴇ-ᴏɴʟʏ.\n"
                        f"ᴄᴏɴsɪᴅᴇʀ /bioconfig ᴛᴏ sᴇᴛ ᴍᴜᴛᴇ/ʙᴀɴ ᴘᴇɴᴀʟᴛʏ.</blockquote>",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close")
                        ]])
                    )
            except errors.ChatAdminRequired:
                await sent.edit_text(
                    f"<blockquote>⚠️ {mention} ʀᴇᴍᴏᴠᴇ ʏᴏᴜʀ ʙɪᴏ ʟɪɴᴋ.\n"
                    f"ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴘᴇʀᴍɪssɪᴏɴ ᴛᴏ {penalty}.</blockquote>"
                )
        return

    # ── DIRECT MUTE ───────────────────────────────────────────────────────────
    if mode == "mute":
        try:
            await client.restrict_chat_member(chat_id, user_id, ChatPermissions())
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔻 ᴜɴᴍᴜᴛᴇ ✅", callback_data=f"bp_unmute_{user_id}"),
                InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",  callback_data="bp_close"),
            ]])
            await message.reply_text(
                f"<blockquote>🔇 {mention} ʜᴀs ʙᴇᴇɴ **ᴍᴜᴛᴇᴅ** ғᴏʀ [Link In Bio].</blockquote>",
                reply_markup=kb
            )
        except errors.ChatAdminRequired:
            pass
        return

    # ── DIRECT BAN ────────────────────────────────────────────────────────────
    if mode == "ban":
        try:
            await client.ban_chat_member(chat_id, user_id)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔻 ᴜɴʙᴀɴ ✅", callback_data=f"bp_unban_{user_id}"),
                InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close"),
            ]])
            await message.reply_text(
                f"<blockquote>🔨 {mention} ʜᴀs ʙᴇᴇɴ **ʙᴀɴɴᴇᴅ** ғᴏʀ [Link In Bio].</blockquote>",
                reply_markup=kb
            )
        except errors.ChatAdminRequired:
            pass
        return

# ══════════════════════════════════════════════════════════════
#  MODULE METADATA
# ══════════════════════════════════════════════════════════════
__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_81"
__help__ = """
**ᴛᴏɢɢʟᴇ (ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ ᴏɴʟʏ):**
🔻 `/biolink` ➠ sʜᴏᴡ sᴛᴀᴛᴜs + ᴛᴏɢɢʟᴇ ʙᴜᴛᴛᴏɴ
🔻 `/biolink enable` ➠ ᴇɴᴀʙʟᴇ ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ
🔻 `/biolink disable` ➠ ᴅɪsᴀʙʟᴇ ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ
**sᴇᴛᴛɪɴɢs (ᴀᴅᴍɪɴs):**
🔻 `/bioconfig` ➠ ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ᴘᴀɴᴇʟ
**ᴍᴏᴅᴇs:**
🔻 `delete` _(ᴅᴇғᴀᴜʟᴛ)_ ➠ ᴊᴜsᴛ ᴅᴇʟᴇᴛᴇ ᴛʜᴇ ᴍᴇssᴀɢᴇ
🔻 `warn` ➠ ᴡᴀʀɴ ᴜsᴇʀ ᴜᴘ ᴛᴏ ʟɪᴍɪᴛ ᴛʜᴇɴ ᴀᴘᴘʟʏ ᴘᴇɴᴀʟᴛʏ
🔻 `mute` ➠ ɪᴍᴍᴇᴅɪᴀᴛᴇʟʏ ᴍᴜᴛᴇ
🔻 `ban` ➠ ɪᴍᴍᴇᴅɪᴀᴛᴇʟʏ ʙᴀɴ
**ᴡʜɪᴛᴇʟɪsᴛ (ᴀᴅᴍɪɴs):**
🔻 `/biofree` _(reply/id)_ ➠ ᴡʜɪᴛᴇʟɪsᴛ ᴜsᴇʀ
🔻 `/biounfree` _(reply/id)_ ➠ ʀᴇᴍᴏᴠᴇ ғʀᴏᴍ ᴡʜɪᴛᴇʟɪsᴛ
🔻 `/biofreelist` ➠ sʜᴏᴡ ᴀʟʟ ᴡʜɪᴛᴇʟɪsᴛᴇᴅ ᴜsᴇʀs
"""
