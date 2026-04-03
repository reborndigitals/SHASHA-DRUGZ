# SHASHA_DRUGZ/dplugins/COMMON/MANAGE/bioprotect.py
# ══════════════════════════════════════════════════════════════
#  Bio Link Protector — SHASHA_DRUGZ Plugin
# ══════════════════════════════════════════════════════════════

import re
import asyncio
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

_URL_RE = re.compile(
    r"(https?://\S+|t\.me/\S+|@[A-Za-z0-9_]{5,})",
    re.IGNORECASE,
)

# ── DB Collections ────────────────────────────────────────────
_cfg_col  = mongodb["bioprotect_config"]
_warn_col = mongodb["bioprotect_warns"]
_wl_col   = mongodb["bioprotect_whitelist"]


# ── DB Helpers ────────────────────────────────────────────────
async def _get_cfg(chat_id: int) -> dict:
    doc = await _cfg_col.find_one({"chat_id": chat_id})
    if doc is None:
        doc = {
            "chat_id": chat_id,
            "enabled": True,
            "mode":    "delete",
            "limit":   3,
            "penalty": "delete",
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
    # find_one_and_update with upsert returns the OLD doc before increment on first insert
    # so if doc is None it means it was just created with count=1
    return (doc["count"] + 1) if doc else 1


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


# ── Permission Helpers ────────────────────────────────────────
async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


async def _is_owner(client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status == ChatMemberStatus.OWNER
    except Exception:
        return False


# ── Auto-enable on bot add ────────────────────────────────────
@app.on_chat_member_updated(filters.group)
async def on_bot_added(client, update):
    try:
        bot = await client.get_me()
        if update.new_chat_member and update.new_chat_member.user.id == bot.id:
            new_status = update.new_chat_member.status
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
                    chat_id, getattr(update.chat, "title", "?")
                )
    except Exception as e:
        logger.warning("on_bot_added error: %s", e)


# ── Keyboard Builders ─────────────────────────────────────────
def _biolink_kb(enabled: bool, chat_id: int) -> InlineKeyboardMarkup:
    if enabled:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🟢 ᴇɴᴀʙʟᴇᴅ — ᴛᴀᴘ ᴛᴏ ᴅɪsᴀʙʟᴇ",
                callback_data=f"biolink_toggle_{chat_id}"
            )
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔴 ᴅɪsᴀʙʟᴇᴅ — ᴛᴀᴘ ᴛᴏ ᴇɴᴀʙʟᴇ",
            callback_data=f"biolink_toggle_{chat_id}"
        )
    ]])


def _config_main_kb(mode: str, penalty: str) -> InlineKeyboardMarkup:
    def _m(label, key):
        return InlineKeyboardButton(
            f"🍏 {label}" if mode == key else label,
            callback_data=f"bp_mode_{key}"
        )
    return InlineKeyboardMarkup([
        [_m("ᴅᴇʟᴇᴛᴇ ᴏɴʟʏ", "delete"), _m("ᴡᴀʀɴ", "warn")],
        [_m("ᴍᴜᴛᴇ", "mute"),           _m("ʙᴀɴ", "ban")],
        [InlineKeyboardButton("⚙️ ᴡᴀʀɴ ʟɪᴍɪᴛ", callback_data="bp_warn_limit")],
        [InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",    callback_data="bp_close")],
    ])


def _warn_limit_kb(current: int) -> InlineKeyboardMarkup:
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
        [
            InlineKeyboardButton("◀ ʙᴀᴄᴋ",      callback_data="bp_back"),
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close"),
        ],
    ])


def _after_penalty_kb(penalty: str) -> InlineKeyboardMarkup:
    def _p(label, key):
        return InlineKeyboardButton(
            f"🍏 {label}" if penalty == key else label,
            callback_data=f"bp_penalty_{key}"
        )
    return InlineKeyboardMarkup([
        [_p("ᴅᴇʟᴇᴛᴇ", "delete"), _p("ᴍᴜᴛᴇ", "mute"), _p("ʙᴀɴ", "ban")],
        [
            InlineKeyboardButton("◀ ʙᴀᴄᴋ",      callback_data="bp_back"),
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻", callback_data="bp_close"),
        ],
    ])


# ── /biolink command ──────────────────────────────────────────
@app.on_message(filters.group & filters.command("biolink"))
async def biolink_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await _is_owner(client, chat_id, user_id):
        return await message.reply_text(
            "<blockquote>❌ ᴏɴʟʏ ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ ᴄᴀɴ ᴛᴏɢɢʟᴇ ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ.</blockquote>"
        )

    cfg  = await _get_cfg(chat_id)
    args = message.command

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


# ── Toggle callback ───────────────────────────────────────────
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


# ── /bioconfig command ────────────────────────────────────────
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


# ── bp_ callbacks ─────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^bp_"))
async def bp_callbacks(client, cq):
    data    = cq.data
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        return await cq.answer("❌ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ.", show_alert=True)

    cfg = await _get_cfg(chat_id)

    # ── close ──
    if data == "bp_close":
        try:
            await cq.message.delete()
        except Exception:
            pass
        return await cq.answer()

    # ── back ──
    if data == "bp_back":
        cfg  = await _get_cfg(chat_id)
        text = (
            f"<blockquote>⚙️ **ʙɪᴏ ᴘʀᴏᴛᴇᴄᴛ sᴇᴛᴛɪɴɢs**</blockquote>\n"
            f"<blockquote>"
            f"➤ ᴍᴏᴅᴇ: `{cfg['mode']}`\n"
            f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
            f"➤ ᴘᴇɴᴀʟᴛʏ ᴀғᴛᴇʀ ᴡᴀʀɴs: `{cfg['penalty']}`"
            f"</blockquote>"
        )
        try:
            await cq.message.edit_text(
                text, reply_markup=_config_main_kb(cfg["mode"], cfg["penalty"])
            )
        except Exception:
            pass
        return await cq.answer()

    # ── mode select ──
    if data.startswith("bp_mode_"):
        new_mode = data.replace("bp_mode_", "")
        await _set_cfg(chat_id, mode=new_mode)
        cfg = await _get_cfg(chat_id)

        if new_mode == "warn":
            text = (
                f"<blockquote>⚙️ **ᴡᴀʀɴ ᴍᴏᴅᴇ sᴇʟᴇᴄᴛᴇᴅ**\n"
                f"➤ ᴡᴀʀɴ ʟɪᴍɪᴛ: `{cfg['limit']}`\n"
                f"sᴇʟᴇᴄᴛ ᴀᴄᴛɪᴏɴ ᴀғᴛᴇʀ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ:</blockquote>"
            )
            try:
                await cq.message.edit_text(
                    text, reply_markup=_after_penalty_kb(cfg["penalty"])
                )
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
                await cq.message.edit_text(
                    text, reply_markup=_config_main_kb(cfg["mode"], cfg["penalty"])
                )
            except Exception:
                pass
        return await cq.answer(f"ᴍᴏᴅᴇ → {new_mode}")

    # ── penalty select ──
    if data.startswith("bp_penalty_"):
        new_penalty = data.replace("bp_penalty_", "")
        await _set_cfg(chat_id, penalty=new_penalty)
        cfg  = await _get_cfg(chat_id)
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

    # ── warn limit menu ──
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

    # ── set warn limit ──
    if data.startswith("bp_limit_"):
        new_limit = int(data.replace("bp_limit_", ""))
        await _set_cfg(chat_id, limit=new_limit)
        try:
            await cq.message.edit_reply_markup(reply_markup=_warn_limit_kb(new_limit))
        except Exception:
            pass
        return await cq.answer(f"ᴡᴀʀɴ ʟɪᴍɪᴛ → {new_limit}")

    # ── unmute ──
    if data.startswith("bp_unmute_"):
        target_id = int(data.split("_")[2])
        try:
            await client.restrict_chat_member(
                chat_id, target_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                )
            )
            await _reset_warns(chat_id, target_id)
            user    = await client.get_chat(target_id)
            name    = user.first_name or str(target_id)
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

    # ── unban ──
    if data.startswith("bp_unban_"):
        target_id = int(data.split("_")[2])
        try:
            await client.unban_chat_member(chat_id, target_id)
            await _reset_warns(chat_id, target_id)
            user    = await client.get_chat(target_id)
            name    = user.first_name or str(target_id)
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

    # ── cancel warn ──
    if data.startswith("bp_cancel_warn_"):
        target_id = int(data.split("_")[3])
        await _reset_warns(chat_id, target_id)
        user    = await client.get_chat(target_id)
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

    # ── whitelist ──
    if data.startswith("bp_whitelist_"):
        target_id = int(data.split("_")[2])
        await _add_wl(chat_id, target_id)
        await _reset_warns(chat_id, target_id)
        user    = await client.get_chat(target_id)
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

    # ── unwhitelist ──
    if data.startswith("bp_unwhitelist_"):
        target_id = int(data.split("_")[2])
        await _rm_wl(chat_id, target_id)
        user    = await client.get_chat(target_id)
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


# ── /biofree ──────────────────────────────────────────────────
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
            target = await client.get_users(
                int(arg) if arg.lstrip("-").isdigit() else arg
            )
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


# ── /biounfree ────────────────────────────────────────────────
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
            target = await client.get_users(
                int(arg) if arg.lstrip("-").isdigit() else arg
            )
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


# ── /biofreelist ──────────────────────────────────────────────
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
            u    = await client.get_chat(uid)
            name = f"{u.first_name}{(' ' + u.last_name) if u.last_name else ''}"
        except Exception:
            name = "Unknown"
        lines.append(f"{i}. {name} [`{uid}`]")
    lines.append("</blockquote>")

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ ᴄʟᴏsᴇ", callback_data="bp_close")]])
    await message.reply_text("\n".join(lines), reply_markup=kb)


# ── Core: check every group message for bio links ─────────────
@app.on_message(filters.group & ~filters.bot & ~filters.service, group=1)
async def check_bio(client, message):
    # Skip commands
    if message.text and message.text.startswith("/"):
        return
    # Must have a real user sender
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    cfg = await _get_cfg(chat_id)
    if not cfg["enabled"]:
        return

    if await _is_admin(client, chat_id, user_id):
        return

    if await _is_wl(chat_id, user_id):
        return

    # ── FIX: use get_chat() not get_users() ──
    # get_users() calls GetUsers which does NOT return the bio.
    # get_chat() on a user calls GetFullUser which DOES return the bio.
    try:
        user = await client.get_chat(user_id)
    except Exception:
        return

    bio = user.bio or ""

    if not _URL_RE.search(bio):
        # Clean up leftover warns if user removed their bio link
        if await _get_warns(chat_id, user_id) > 0:
            await _reset_warns(chat_id, user_id)
        return

    # Bio has a link — take action
    name    = user.first_name or str(user_id)
    mention = f"[{name}](tg://user?id={user_id})"
    mode    = cfg["mode"]
    limit   = cfg["limit"]
    penalty = cfg["penalty"]

    async def _delete_msg():
        try:
            await message.delete()
        except Exception:
            pass

    async def _send_bio_report():
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔻 ᴡʜɪᴛᴇʟɪsᴛ ✅", callback_data=f"bp_whitelist_{user_id}"),
            InlineKeyboardButton("🔻 ᴄʟᴏsᴇ 🔻",      callback_data="bp_close"),
        ]])
        try:
            await message.reply_text(
                f"<blockquote>🚨 {mention}\n\n"
                f"❌ **ʀᴇᴍᴏᴠᴇ ʏᴏᴜʀ ʙɪᴏ ʟɪɴᴋ**\n\n"
                f"ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ᴡᴀs ᴅᴇʟᴇᴛᴇᴅ ʙᴇᴄᴀᴜsᴇ ʏᴏᴜʀ ʙɪᴏ ᴄᴏɴᴛᴀɪɴs ᴀ ʟɪɴᴋ.</blockquote>",
                reply_markup=kb
            )
        except Exception:
            pass

    # ── DELETE mode (default) ──
    if mode == "delete":
        await asyncio.gather(_delete_msg(), _send_bio_report())
        return

    # All other modes: delete first
    await _delete_msg()

    # ── WARN mode ──
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
                    # penalty == "delete" — no escalation action
                    await sent.edit_text(
                        f"<blockquote>⚠️ {mention} ʜɪᴛ ᴡᴀʀɴ ʟɪᴍɪᴛ ʙᴜᴛ ᴘᴇɴᴀʟᴛʏ ɪs ᴅᴇʟᴇᴛᴇ-ᴏɴʟʏ.\n"
                        f"ᴜsᴇ /bioconfig ᴛᴏ sᴇᴛ ᴍᴜᴛᴇ/ʙᴀɴ ᴘᴇɴᴀʟᴛʏ.</blockquote>",
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

    # ── MUTE mode ──
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

    # ── BAN mode ──
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


__menu__     = "CMD_PRO"
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
