# SHASHA_DRUGZ/plugins/PREMIUM/deploy.py
import re
import os
import logging
import asyncio
import uuid
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Set, Optional
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler, InlineQueryHandler
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery
)
from pyrogram.errors.exceptions.bad_request_400 import AccessTokenExpired, AccessTokenInvalid
from pyrogram.errors import MessageNotModified
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import mongodb, raw_mongodb
from SHASHA_DRUGZ.core.isolation import set_bot_context, _owner_cache as _iso_cache
from config import (
    API_ID, API_HASH, OWNER_ID, DEPLOY_LOGGER,
    ADMINS_ID, UPI_ID, DEFAULT_QR_PATH, BOT_TOKEN
)
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.bot_settings import apply_to_config, evict_bot_cache
from SHASHA_DRUGZ.mongo.deploydb import (
    ensure_indexes,
    save_deploy_session, get_deploy_session, clear_deploy_session,
    save_deployed_bot, get_deployed_bot_by_token, get_deployed_bot_by_id,
    get_deployed_bot_by_username, get_deployed_bots_by_user, get_all_deployed_bots,
    update_deployed_bot, delete_deployed_bot, get_expired_bots, get_bots_expiring_soon,
    create_pending_payment, get_pending_payment, update_pending_payment,
    delete_pending_payment, deploy_bots_col,
    create_refund, get_refund,
    add_served_chat_deploy, add_served_user_deploy,
    is_deploy_owner, cleanup_expired_bot
)
from SHASHA_DRUGZ.utils.invoice import generate_invoice

os.makedirs("deploy_sessions", exist_ok=True)

# ─── Time helpers ─────────────────────────────────────────────────────────────
def ist_now():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def to_ist(utc_dt):
    return utc_dt + timedelta(hours=5, minutes=30)

# ─── Runtime registry ─────────────────────────────────────────────────────────
DEPLOYED_CLIENTS: Dict[int, Client] = {}
DEPLOYED_BOTS: set = set()
BOT_ALLOWED_PLUGINS: Dict[int, Set[str]] = {}
BOT_OWNERS: Dict[int, int] = {}

# ─── Constants ────────────────────────────────────────────────────────────────
MODULES_PATH = "SHASHA_DRUGZ/dplugins"
COMMON_PATH  = "COMMON"

AUTO_BOT_TYPES = {
    "REACTION":   {"path": "REACTION", "price": 100, "display": "ʀᴇᴀᴄᴛɪᴏɴ ʙᴏᴛ"},
    "CHAT":       {"path": "CHAT",     "price": 250, "display": "ᴄʜᴀᴛ ʙᴏᴛ"},
    "MUSIC":      {"path": "MUSIC",    "price": 450, "display": "ᴍᴜsɪᴄ ʙᴏᴛ"},
    "MANAGEMENT": {"path": "MANAGE",   "price": 650, "display": "ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ʙᴏᴛ"},
    "PRO-BOTS":   {"path": "PRO-BOTS", "price": 899, "display": "ᴘʀᴏ ʙᴏᴛs"},    
    "GAME":       {"path": "GAMES",    "price": 1999, "display": "ɢᴀᴍᴇ ʙᴏᴛ"},
}

AUTO_COMBOS = {
    "CHAT+REACTION":              {"bots": ["CHAT","REACTION"],               "price": 299,  "display": "ᴄʜᴀᴛ+ʀᴇᴀᴄᴛɪᴏɴ"},
    "MUSIC+CHAT":                 {"bots": ["MUSIC","CHAT"],                  "price": 599,  "display": "ᴍᴜsɪᴄ+ᴄʜᴀᴛ"},
    "MANAGEMENT+MUSIC":           {"bots": ["MANAGEMENT","MUSIC"],            "price": 799,  "display": "ᴍᴀɴᴀɢᴇᴍᴇɴᴛ+ᴍᴜsɪᴄ"},
    "MUSIC+PRO-BOTS+":            {"bots": ["MUSIC","PRO-BOTS"],              "price": 999,  "display": "ᴍᴜsɪᴄ+ᴘʀᴏ"},
    "MANAGEMENT+PRO-BOTS":        {"bots": ["MANAGEMENT","PRO-BOTS"],         "price": 1199,  "display": "ᴍᴀɴᴀɢᴇᴍᴇɴᴛ+ᴘʀᴏ"},
    "MUSIC+MANAGEMENT+PRO-BOTS+": {"bots": ["MUSIC","MANAGEMENT","PRO-BOTS"], "price": 1499,  "display": "ᴍᴜsɪᴄ+ᴍᴀɴᴀɢᴇᴍᴇɴᴛ+ᴘʀᴏ"},
    "MUSIC+GAMES":                {"bots": ["MUSIC","GAMES"],                 "price": 2299,  "display": "ᴍᴜsɪᴄ+ᴄʜᴀᴛ"},
}

# ─── Plugin helpers ────────────────────────────────────────────────────────────
def get_plugins_from_folder(folder_name: str) -> List[str]:
    folder_path = os.path.join(MODULES_PATH, folder_name)
    plugins = []
    if not os.path.isdir(folder_path):
        return plugins
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".py") and not file.startswith("_"):
                rel = os.path.relpath(os.path.join(root, file), MODULES_PATH)
                plugins.append(rel.replace(os.sep, ".")[:-3])
    return plugins

COMMON_PLUGINS   = get_plugins_from_folder(COMMON_PATH)
AUTO_BOT_PLUGINS = {n: get_plugins_from_folder(i["path"]) for n, i in AUTO_BOT_TYPES.items()}
AUTO_COMBO_PLUGINS = {}
for _cn, _ci in AUTO_COMBOS.items():
    _ps = set()
    for _b in _ci["bots"]:
        _ps.update(AUTO_BOT_PLUGINS.get(_b, []))
    AUTO_COMBO_PLUGINS[_cn] = list(_ps)

MANUAL_MODULES_MAP: Dict[str, List[str]] = {}
MODULE_PRICES: Dict[str, int] = {}
MODULE_TO_TYPE: Dict[str, str] = {}

def load_manual_modules_map():
    global MANUAL_MODULES_MAP, MODULE_PRICES, MODULE_TO_TYPE
    mm, pr, tm = {}, {}, {}
    for root, _, files in os.walk(MODULES_PATH):
        for file in files:
            if not file.endswith(".py") or file.startswith("_"):
                continue
            fp  = os.path.join(root, file)
            rp  = os.path.relpath(fp, MODULES_PATH)
            pn  = rp.replace(os.sep, ".")[:-3]
            fld = rp.split(os.sep)[0]
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                mn_m = re.search(r'MOD_NAME\s*=\s*["\']([^"\']+)["\']', content)
                mn   = mn_m.group(1) if mn_m else file[:-3]
                pm   = re.search(r'MOD_PRICE\s*=\s*["\']?(\d+)["\']?', content)
                if pm:
                    pr[mn] = int(pm.group(1))
                    tm[mn] = fld
                    mm.setdefault(mn, []).append(pn)
            except Exception as e:
                logging.exception(f"Error reading {fp}: {e}")
    MANUAL_MODULES_MAP = mm
    MODULE_PRICES      = pr
    MODULE_TO_TYPE     = tm

def get_plugins_for_manual_modules(module_names: List[str]) -> List[str]:
    p = []
    for n in module_names:
        p.extend(MANUAL_MODULES_MAP.get(n, []))
    return list(set(p))

# ─── Full bot data cleanup ─────────────────────────────────────────────────────
async def cleanup_bot_data(bot_id: int):
    """
    Drop ALL bot_{id}_* collections and wipe chats/users rows.
    Also calls evict_bot_cache(bot_id) so stale settings never
    leak to a future redeploy of the same bot_id.
    """
    try:
        prefix = f"bot_{bot_id}_"
        for col_name in await raw_mongodb.list_collection_names():
            if col_name.startswith(prefix):
                await raw_mongodb.drop_collection(col_name)
                logging.info(f"[cleanup] Dropped: {col_name}")
    except Exception as e:
        logging.error(f"[cleanup] drop failed for {bot_id}: {e}")
    try:
        await raw_mongodb.deploy_chats.delete_many({"bot_id": bot_id})
        await raw_mongodb.deploy_users.delete_many({"bot_id": bot_id})
    except Exception as e:
        logging.error(f"[cleanup] chats/users wipe failed for {bot_id}: {e}")
    # evict settings cache so stale data never leaks
    evict_bot_cache(bot_id)

# ─── ISOLATION ────────────────────────────────────────────────────────────────
def _register_isolation_handlers(bot_client: Client, bot_id: int, owner_id: Optional[int]):
    async def _ctx_message(client: Client, message: Message):
        set_bot_context(bot_id, owner_id)
    async def _ctx_callback(client: Client, cq: CallbackQuery):
        set_bot_context(bot_id, owner_id)
    async def _ctx_inline(client: Client, iq):
        set_bot_context(bot_id, owner_id)
    bot_client.add_handler(MessageHandler(_ctx_message,  filters.all), group=-1000)
    bot_client.add_handler(CallbackQueryHandler(_ctx_callback, filters.all), group=-1000)
    bot_client.add_handler(InlineQueryHandler(_ctx_inline, filters.all), group=-1000)
    logging.info(f"[isolation] Registered context handlers for bot {bot_id}")

# ─── Bot helpers ──────────────────────────────────────────────────────────────
async def set_bot_commands_and_description(bot_token: str, bot_username: str):
    commands = [
        {"command": "start",  "description": "Start the bot"},
        {"command": "help",   "description": "Get help"},
        {"command": "play",   "description": "Play music"},
        {"command": "pause",  "description": "Pause playback"},
        {"command": "resume", "description": "Resume playback"},
        {"command": "skip",   "description": "Skip current track"},
        {"command": "end",    "description": "Stop playback"},
        {"command": "ping",   "description": "Check bot status"},
        {"command": "id",     "description": "Get ID"},
    ]
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/setMyCommands",
            json={"commands": commands}, timeout=5
        )
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/setMyDescription",
            data={"description": "Deployed via @SHASHA_DRUGZ"}, timeout=5
        )
    except Exception as e:
        logging.error(f"set commands failed for {bot_username}: {e}")

async def _safe_edit(msg, text: str, reply_markup=None, **kwargs):
    try:
        await msg.edit_text(text, reply_markup=reply_markup, **kwargs)
    except MessageNotModified:
        pass
    except Exception as e:
        logging.warning(f"[deploy] edit failed: {e}")

async def _edit_approval_msg(msg, text: str, reply_markup=None):
    """
    Edit the admin approval message (which may be a photo OR a plain text
    message depending on whether a screenshot was attached).
    Always attaches the reply_markup regardless of message type.
    """
    if msg.photo or msg.document or msg.video or msg.audio or msg.voice:
        try:
            await msg.edit_caption(text, reply_markup=reply_markup)
            return
        except MessageNotModified:
            try:
                await msg.edit_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass
            return
        except Exception as e:
            logging.warning(f"[edit_approval] edit_caption failed: {e}")
    else:
        try:
            await msg.edit_text(text, reply_markup=reply_markup)
            return
        except MessageNotModified:
            try:
                await msg.edit_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass
            return
        except Exception as e:
            logging.warning(f"[edit_approval] edit_text failed: {e}")
    try:
        await msg.edit_reply_markup(reply_markup=reply_markup)
    except Exception:
        pass

async def _get_user_bot_client(user_id: int) -> Optional[Client]:
    bot_doc = await deploy_bots_col.find_one(
        {"owner_id": user_id, "status": "active"}
    )
    if bot_doc:
        bid = bot_doc.get("bot_id")
        if bid and bid in DEPLOYED_CLIENTS:
            return DEPLOYED_CLIENTS[bid]
    return None

async def _send_to_user(client: Client, user_id: int, text: str, **kwargs):
    bot_client = await _get_user_bot_client(user_id)
    if bot_client:
        try:
            await bot_client.send_message(user_id, text, **kwargs)
            return
        except Exception as e:
            logging.warning(f"[_send_to_user] deployed bot send failed for {user_id}: {e}")
    await client.send_message(user_id, text, **kwargs)

# ─── Keyboards ────────────────────────────────────────────────────────────────
def deploy_mode_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪄 ᴀᴜᴛᴏ-ᴅᴇᴘʟᴏʏ",   callback_data="deploy_mode_auto"),
         InlineKeyboardButton("✨ ᴍᴀɴᴜᴀʟ-ᴅᴇᴘʟᴏʏ", callback_data="deploy_mode_manual")],
        [InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻",       callback_data="deploy_cancel")]
    ])

def type_selection_kb():
    kb = [[InlineKeyboardButton(t, callback_data=f"deploy_type_{t}")] for t in AUTO_BOT_TYPES]
    kb.append([InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻", callback_data="deploy_cancel")])
    return InlineKeyboardMarkup(kb)

def modules_kb(selected_type, enabled_modules, original_modules=None):
    folder = AUTO_BOT_TYPES.get(selected_type, {}).get("path", selected_type)
    mods   = [n for n, t in MODULE_TO_TYPE.items() if t == folder]
    kb = []
    for m in mods:
        price = MODULE_PRICES.get(m, 0)
        if original_modules and m in original_modules:
            st, cb = "🔒", "noop"
        else:
            st = "🍏" if m in enabled_modules else "🍎"
            cb = f"deploy_toggle_{m}"
        kb.append([InlineKeyboardButton(f"{st} {m} (₹{price})", callback_data=cb)])
    kb.append([InlineKeyboardButton("➕ ᴀᴅᴅ-ᴍᴏᴅᴜʟᴇ",       callback_data="deploy_add_module")])
    kb.append([InlineKeyboardButton("🔻 ʙᴀᴄᴋ ᴛᴏ ᴛʏᴘᴇs 🔻", callback_data="deploy_back_to_types")])
    return InlineKeyboardMarkup(kb)

def auto_main_kb(selected_bundles):
    kb = []
    for name, info in AUTO_BOT_TYPES.items():
        st = "✅" if name in selected_bundles else "☑️"
        kb.append([InlineKeyboardButton(
            f"{st} {info['display']} (₹{info['price']})",
            callback_data=f"auto_toggle_{name}"
        )])
    kb.append([InlineKeyboardButton("🎲 ᴄᴏᴍʙᴏ",     callback_data="auto_show_combos")])
    kb.append([InlineKeyboardButton("🚀 ɢᴏ ᴅᴇᴘʟᴏʏ", callback_data="auto_go_payment")])
    kb.append([InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻",  callback_data="deploy_cancel")])
    return InlineKeyboardMarkup(kb)

def auto_combo_kb(selected_bundles):
    kb = []
    for cn, ci in AUTO_COMBOS.items():
        st = "✅" if cn in selected_bundles else "☑️"
        kb.append([InlineKeyboardButton(
            f"{st} {ci['display']} (₹{ci['price']})",
            callback_data=f"auto_combo_toggle_{cn}"
        )])
    kb.append([InlineKeyboardButton("🚀 ɢᴏ ᴅᴇᴘʟᴏʏ",         callback_data="auto_go_payment")])
    kb.append([InlineKeyboardButton("⏪ ʙᴀᴄᴋ ᴛᴏ ʙᴏᴛ ᴛʏᴘᴇs", callback_data="auto_back_to_main")])
    kb.append([InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻",           callback_data="deploy_cancel")])
    return InlineKeyboardMarkup(kb)

def payment_method_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 ᴘᴀʏ ᴜᴘɪ", callback_data="deploy_pay_upi"),
         InlineKeyboardButton("📷 ᴘᴀʏ ǫʀ",  callback_data="deploy_pay_qr")],
        [InlineKeyboardButton("🔻 ʙᴀᴄᴋ 🔻",  callback_data="deploy_back_to_modules")]
    ])

def numeric_keypad_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="num_1"),
         InlineKeyboardButton("2", callback_data="num_2"),
         InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"),
         InlineKeyboardButton("5", callback_data="num_5"),
         InlineKeyboardButton("6", callback_data="num_6")],
        [InlineKeyboardButton("7", callback_data="num_7"),
         InlineKeyboardButton("8", callback_data="num_8"),
         InlineKeyboardButton("9", callback_data="num_9")],
        [InlineKeyboardButton("0", callback_data="num_0"),
         InlineKeyboardButton(".", callback_data="num_dot"),
         InlineKeyboardButton("❌", callback_data="num_clear")],
        [InlineKeyboardButton("🔻 ✅ ᴄᴏɴғɪʀᴍ", callback_data="num_confirm")]
    ])

def admin_review_kb(payment_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ᴀᴘᴘʀᴏᴠᴇ", callback_data=f"admin_approve_{payment_id}"),
         InlineKeyboardButton("❌ ʀᴇᴊᴇᴄᴛ",  callback_data=f"admin_reject_{payment_id}")],
        [InlineKeyboardButton("💸 ʀᴇғᴜɴᴅ",  callback_data=f"admin_refund_{payment_id}")]
    ])

def admin_connection_kb(user_id: int, is_connected: bool):
    if is_connected:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔌 ᴅɪsᴄᴏɴɴᴇᴄᴛ",   callback_data=f"admin_disconnect_{user_id}"),
            InlineKeyboardButton("💬 sᴇɴᴅ ᴍᴇssᴀɢᴇ", callback_data=f"admin_message_{user_id}")
        ]])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔌 ᴄᴏɴɴᴇᴄᴛ",       callback_data=f"admin_connect_{user_id}"),
        InlineKeyboardButton("💬 sᴇɴᴅ ᴍᴇssᴀɢᴇ", callback_data=f"admin_message_{user_id}")
    ]])

def renew_kb(bot_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 ʀᴇɴᴇᴡ",           callback_data=f"renew_{bot_id}"),
        InlineKeyboardButton("📦 ᴜᴘᴅᴀᴛᴇ ᴍᴏᴅᴜʟᴇs", callback_data=f"update_modules_{bot_id}")
    ]])

def cancel_button_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻", callback_data="deploy_cancel")
    ]])

DEPLOY_PROMPT = (
    "<blockquote>**🤖 ʙᴏᴛ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ**</blockquote>\n"
    "<blockquote>ᴘʟᴇᴀsᴇ sᴇɴᴅ ʏᴏᴜʀ **ʙᴏᴛ ᴛᴏᴋᴇɴ** ɴᴏᴡ.\n\n"
    "📌 ɢᴇᴛ ɪᴛ ғʀᴏᴍ @BotFather\n"
    "📌 ғᴏʀᴍᴀᴛ: `123456789:ABCdefGhIJKlmNoPQRstu`</blockquote>"
)

# ─── /deploy ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("deploy") & filters.private)
async def deploy_command(client: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) >= 2:
        bot_token = message.command[1].strip()
        if not re.match(r'^\d+:[A-Za-z0-9_-]+$', bot_token):
            return await message.reply_text(
                "❌ ɪɴᴠᴀʟɪᴅ ᴛᴏᴋᴇɴ ғᴏʀᴍᴀᴛ.\n📌 `123456789:ABCdef...`",
                reply_markup=cancel_button_kb()
            )
        if await get_deployed_bot_by_token(bot_token):
            return await message.reply_text(
                "<blockquote>❌ ᴛʜɪs ᴛᴏᴋᴇɴ ɪs ᴀʟʀᴇᴀᴅʏ ᴅᴇᴘʟᴏʏᴇᴅ.\n"
                "ᴜsᴇ `/rmdeploy` ғɪʀsᴛ ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʀᴇ-ᴅᴇᴘʟᴏʏ.</blockquote>"
            )
        await save_deploy_session(user_id, {"token": bot_token, "step": "choose_mode"})
        return await message.reply_text(
            "<blockquote>**ᴄʜᴏᴏsᴇ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴍᴏᴅᴇ:**</blockquote>",
            reply_markup=deploy_mode_kb()
        )
    await save_deploy_session(user_id, {"step": "wait_token"})
    await message.reply_text(DEPLOY_PROMPT, reply_markup=cancel_button_kb())

# ─── Token listener ────────────────────────────────────────────────────────────
@app.on_message(filters.private & filters.text & ~filters.regex(r"^/"), group=15)
async def deploy_token_listener(client: Client, message: Message):
    user_id = message.from_user.id
    session = await get_deploy_session(user_id)
    if session.get("step") != "wait_token":
        return
    text = message.text.strip()
    if not re.match(r'^\d+:[A-Za-z0-9_-]+$', text):
        return await message.reply_text(
            "❌ ᴛʜᴀᴛ ᴅᴏᴇsɴ'ᴛ ʟᴏᴏᴋ ʟɪᴋᴇ ᴀ ᴠᴀʟɪᴅ ʙᴏᴛ ᴛᴏᴋᴇɴ.\n"
            "ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ /canceldeploy ᴛᴏ ᴀʙᴏʀᴛ.",
            reply_markup=cancel_button_kb()
        )
    if await get_deployed_bot_by_token(text):
        return await message.reply_text(
            "<blockquote>❌ ᴛʜɪs ᴛᴏᴋᴇɴ ɪs ᴀʟʀᴇᴀᴅʏ ᴅᴇᴘʟᴏʏᴇᴅ.\n"
            "ᴜsᴇ `/rmdeploy` ғɪʀsᴛ ɪғ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʀᴇ-ᴅᴇᴘʟᴏʏ.</blockquote>",
            reply_markup=cancel_button_kb()
        )
    try:
        resp = requests.get(f"https://api.telegram.org/bot{text}/getMe", timeout=5)
        if resp.status_code != 200:
            raise ValueError("bad token")
    except Exception:
        return await message.reply_text(
            "❌ ᴛᴏᴋᴇɴ ᴠᴀʟɪᴅᴀᴛɪᴏɴ ғᴀɪʟᴇᴅ. ᴄʜᴇᴄᴋ ᴛʜᴇ ᴛᴏᴋᴇɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.",
            reply_markup=cancel_button_kb()
        )
    await save_deploy_session(user_id, {"token": text, "step": "choose_mode"})
    await message.reply_text(
        "<blockquote>✅ **ᴛᴏᴋᴇɴ ᴠᴀʟɪᴅᴀᴛᴇᴅ!**</blockquote>\n"
        "<blockquote>**ᴄʜᴏᴏsᴇ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴍᴏᴅᴇ:**</blockquote>",
        reply_markup=deploy_mode_kb()
    )

@app.on_message(filters.command("canceldeploy") & filters.private)
async def cancel_deploy_command(client: Client, message: Message):
    await clear_deploy_session(message.from_user.id)
    await message.reply_text("<blockquote>✅ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.</blockquote>")

@app.on_message(filters.command("updatemodule") & filters.private)
async def updatemodule_command(client: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/updatemodule <bot_username or bot_token>`</blockquote>"
        )
    query = message.command[1].strip()
    bot   = await get_deployed_bot_by_token(query) or \
            await get_deployed_bot_by_username(query.lstrip('@'))
    if not bot:
        return await message.reply_text("<blockquote>❌ ʙᴏᴛ ɴᴏᴛ ғᴏᴜɴᴅ.</blockquote>")
    if bot["owner_id"] != user_id:
        return await message.reply_text("<blockquote>❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs ʙᴏᴛ.</blockquote>")
    await save_deploy_session(user_id, {
        "token":            bot["token"],
        "bot_id":           bot["bot_id"],
        "original_modules": bot.get("modules", []),
        "enabled_modules":  bot.get("modules", []).copy(),
        "step":             "select_type",
        "is_update":        True,
        "is_renewal":       False,
        "mode":             "manual"
    })
    await message.reply_text(
        f"<blockquote>**ᴜᴘᴅᴀᴛɪɴɢ @{bot['username']}**</blockquote>\n"
        "<blockquote>sᴇʟᴇᴄᴛ ᴀᴅᴅɪᴛɪᴏɴᴀʟ ᴍᴏᴅᴜʟᴇs:</blockquote>",
        reply_markup=type_selection_kb()
    )

# ─── noop ─────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex("^noop$"))
async def noop_callback(_, cq: CallbackQuery):
    await cq.answer("🔒 ᴛʜɪs ᴍᴏᴅᴜʟᴇ ɪs ᴀʟʀᴇᴀᴅʏ ᴘᴜʀᴄʜᴀsᴇᴅ.", show_alert=True)

# ─── Callback dispatcher ──────────────────────────────────────────────────────
@app.on_callback_query(
    filters.regex(r"^(deploy_|num_|admin_|renew_|update_modules_|auto_)"),
    group=5
)
async def deploy_callbacks(client: Client, cq: CallbackQuery):
    user_id = cq.from_user.id
    data    = cq.data
    session = await get_deploy_session(user_id)

    if data == "deploy_cancel":
        await clear_deploy_session(user_id)
        try: await cq.message.delete()
        except Exception: pass
        await client.send_message(user_id, "<blockquote>✅ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.</blockquote>")
        await cq.answer(); return

    if data == "deploy_mode_auto":
        await save_deploy_session(user_id, {"mode": "auto", "step": "auto_main", "selected_bundles": []})
        await _safe_edit(cq.message,
            "<blockquote>**🤖 ᴀᴜᴛᴏ ᴅᴇᴘʟᴏʏ**</blockquote>\n"
            "<blockquote>sᴇʟᴇᴄᴛ ᴛʜᴇ ʙᴏᴛ ᴛʏᴘᴇs ʏᴏᴜ ᴡᴀɴᴛ:</blockquote>",
            reply_markup=auto_main_kb([]))
        await cq.answer(); return

    if data == "deploy_mode_manual":
        await save_deploy_session(user_id, {"mode": "manual", "step": "select_type", "enabled_modules": []})
        await _safe_edit(cq.message,
            "<blockquote>**🛠️ ᴍᴀɴᴜᴀʟ ᴅᴇᴘʟᴏʏ**</blockquote>\n"
            "<blockquote>sᴇʟᴇᴄᴛ ᴍᴏᴅᴜʟᴇ ᴛʏᴘᴇ:</blockquote>",
            reply_markup=type_selection_kb())
        await cq.answer(); return

    if data.startswith("auto_toggle_"):
        bot_name = data.split("_", 2)[2]
        selected = session.get("selected_bundles", [])
        if bot_name in selected: selected.remove(bot_name)
        else: selected.append(bot_name)
        await save_deploy_session(user_id, {"selected_bundles": selected})
        try: await cq.message.edit_reply_markup(reply_markup=auto_main_kb(selected))
        except MessageNotModified: pass
        await cq.answer(); return

    if data == "auto_show_combos":
        selected = session.get("selected_bundles", [])
        await save_deploy_session(user_id, {"step": "auto_combo"})
        await _safe_edit(cq.message,
            "<blockquote>**🎲 ᴄᴏᴍʙᴏ sᴇʟᴇᴄᴛɪᴏɴ**</blockquote>",
            reply_markup=auto_combo_kb([b for b in selected if b in AUTO_COMBOS]))
        await cq.answer(); return

    if data == "auto_back_to_main":
        selected = session.get("selected_bundles", [])
        await save_deploy_session(user_id, {"step": "auto_main"})
        await _safe_edit(cq.message,
            "<blockquote>**🤖 ᴀᴜᴛᴏ ᴅᴇᴘʟᴏʏ**</blockquote>",
            reply_markup=auto_main_kb(selected))
        await cq.answer(); return

    if data.startswith("auto_combo_toggle_"):
        combo_name = data.split("_", 3)[3]
        selected   = session.get("selected_bundles", [])
        if combo_name in selected: selected.remove(combo_name)
        else: selected.append(combo_name)
        await save_deploy_session(user_id, {"selected_bundles": selected})
        try: await cq.message.edit_reply_markup(
                reply_markup=auto_combo_kb([b for b in selected if b in AUTO_COMBOS]))
        except MessageNotModified: pass
        await cq.answer(); return

    if data == "auto_go_payment":
        selected = session.get("selected_bundles", [])
        if not selected:
            await cq.answer("Please select at least one.", show_alert=True); return
        total, modules_set = 0, set(COMMON_PLUGINS)
        for item in selected:
            if item in AUTO_BOT_TYPES:
                total += AUTO_BOT_TYPES[item]["price"]
                modules_set.update(AUTO_BOT_PLUGINS.get(item, []))
            elif item in AUTO_COMBOS:
                total += AUTO_COMBOS[item]["price"]
                modules_set.update(AUTO_COMBO_PLUGINS.get(item, []))
        await save_deploy_session(user_id, {
            "step": "payment_summary", "total": total,
            "selected_bundles": selected, "auto_modules_set": list(modules_set)
        })
        summary = "\n".join(
            f"• {AUTO_BOT_TYPES[i]['display']} (₹{AUTO_BOT_TYPES[i]['price']})"
            if i in AUTO_BOT_TYPES else
            f"• {AUTO_COMBOS[i]['display']} (₹{AUTO_COMBOS[i]['price']})"
            for i in selected
        )
        await _safe_edit(cq.message,
            f"<blockquote>**sᴇʟᴇᴄᴛᴇᴅ:**\n{summary}\n\n**ᴛᴏᴛᴀʟ:** ₹{total}/ᴍᴏɴᴛʜ</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 ᴘᴀʏ ɴᴏᴡ",  callback_data="deploy_pay_now")],
                [InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴏʀᴇ", callback_data="auto_back_to_main")],
                [InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻", callback_data="deploy_cancel")]
            ]))
        await cq.answer(); return

    # admin_connect / disconnect / message BEFORE admin_ catch-all
    if data.startswith("admin_connect_"):
        await connect_admin_to_user(client, cq, user_id, int(data.split("_")[2])); return
    if data.startswith("admin_disconnect_"):
        await disconnect_admin_from_user(client, cq, user_id, int(data.split("_")[2])); return
    if data.startswith("admin_message_"):
        await prepare_admin_message(client, cq, user_id, int(data.split("_")[2])); return

    if data.startswith("deploy_type_"):
        st = data.split("_", 2)[2]
        await save_deploy_session(user_id, {"last_type": st})
        en = session.get("enabled_modules", [])
        og = session.get("original_modules") if session.get("is_update") else None
        await _safe_edit(cq.message,
            f"<blockquote>**ᴛʏᴘᴇ:** {st}</blockquote>\n<blockquote>sᴇʟᴇᴄᴛ ᴍᴏᴅᴜʟᴇs:</blockquote>",
            reply_markup=modules_kb(st, en, og))
        await cq.answer()
    elif data.startswith("deploy_toggle_"):
        mn = data.split("_", 2)[2]
        if session.get("is_update") and mn in session.get("original_modules", []):
            await cq.answer("🔒 ᴄᴀɴɴᴏᴛ ʀᴇᴍᴏᴠᴇ ᴇxɪsᴛɪɴɢ ᴍᴏᴅᴜʟᴇs.", show_alert=True); return
        en = session.get("enabled_modules", [])
        if mn in en: en.remove(mn)
        else: en.append(mn)
        await save_deploy_session(user_id, {"enabled_modules": en})
        st = session.get("last_type")
        og = session.get("original_modules") if session.get("is_update") else None
        try: await cq.message.edit_reply_markup(reply_markup=modules_kb(st, en, og))
        except MessageNotModified: pass
        await cq.answer()
    elif data == "deploy_back_to_types":
        await save_deploy_session(user_id, {"step": "select_type"})
        await _safe_edit(cq.message,
            "<blockquote>**sᴇʟᴇᴄᴛ ᴍᴏᴅᴜʟᴇ ᴛʏᴘᴇ:**</blockquote>",
            reply_markup=type_selection_kb())
        await cq.answer()
    elif data == "deploy_add_module":
        en        = session.get("enabled_modules", [])
        is_update = session.get("is_update", False)
        og        = session.get("original_modules", []) if is_update else []
        if not en:
            await cq.answer("Please enable at least one module.", show_alert=True); return
        if is_update:
            new_mods = [m for m in en if m not in og]
            if not new_mods:
                await cq.answer("No new modules selected.", show_alert=True); return
            total = sum(MODULE_PRICES.get(m, 0) for m in new_mods)
            ml    = "\n".join(f"• {m} (₹{MODULE_PRICES.get(m,0)})" for m in new_mods)
            text  = f"<blockquote>**ɴᴇᴡ ᴍᴏᴅᴜʟᴇs:**\n{ml}\n\n**ᴄᴏsᴛ:** ₹{total}</blockquote>"
        else:
            total = sum(MODULE_PRICES.get(m, 0) for m in en)
            ml    = "\n".join(f"• {m} (₹{MODULE_PRICES.get(m,0)})" for m in en)
            text  = f"<blockquote>**sᴇʟᴇᴄᴛᴇᴅ:**\n{ml}\n\n**ᴛᴏᴛᴀʟ:** ₹{total}/ᴍᴏɴᴛʜ</blockquote>"
        await save_deploy_session(user_id, {"step": "payment_summary", "total": total})
        await _safe_edit(cq.message, text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 ᴘᴀʏ ɴᴏᴡ",           callback_data="deploy_pay_now")],
                [InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴏʀᴇ ᴍᴏᴅᴜʟᴇs", callback_data="deploy_add_more")],
                [InlineKeyboardButton("🔻 ʙᴀᴄᴋ 🔻",            callback_data="deploy_back_to_modules")]
            ]))
        await cq.answer()
    elif data == "deploy_add_more":
        await save_deploy_session(user_id, {"step": "select_type"})
        await _safe_edit(cq.message,
            "<blockquote>**sᴇʟᴇᴄᴛ ᴀɴᴏᴛʜᴇʀ ᴍᴏᴅᴜʟᴇ ᴛʏᴘᴇ:**</blockquote>",
            reply_markup=type_selection_kb())
        await cq.answer()
    elif data == "deploy_back_to_modules":
        st = session.get("last_type")
        en = session.get("enabled_modules", [])
        og = session.get("original_modules") if session.get("is_update") else None
        if not st:
            await _safe_edit(cq.message, "<blockquote>sᴇʟᴇᴄᴛ ᴍᴏᴅᴜʟᴇ ᴛʏᴘᴇ:</blockquote>",
                              reply_markup=type_selection_kb())
        else:
            await _safe_edit(cq.message,
                f"<blockquote>**ᴛʏᴘᴇ:** {st}</blockquote>",
                reply_markup=modules_kb(st, en, original_modules=og))
        await cq.answer()
    elif data == "deploy_pay_now":
        await save_deploy_session(user_id, {"step": "payment_method"})
        await _safe_edit(cq.message,
            "<blockquote>**sᴇʟᴇᴄᴛ ᴘᴀʏᴍᴇɴᴛ ᴍᴇᴛʜᴏᴅ:**</blockquote>",
            reply_markup=payment_method_kb())
        await cq.answer(); return

    if data == "deploy_pay_upi":
        await save_deploy_session(user_id, {"payment_method": "upi"})
        caption = (f"<blockquote>ᴘᴀʏ ᴛᴏ ᴜᴘɪ: `{UPI_ID}`</blockquote>\n"
                   "<blockquote>ᴀғᴛᴇʀ ᴘᴀʏᴍᴇɴᴛ, sᴇɴᴅ sᴄʀᴇᴇɴsʜᴏᴛ.</blockquote>")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ ɪ ʜᴀᴠᴇ ᴘᴀɪᴅ", callback_data="deploy_have_paid")]])
        if os.path.exists(DEFAULT_QR_PATH):
            await cq.message.reply_photo(DEFAULT_QR_PATH, caption=caption, reply_markup=kb)
        else:
            await cq.message.reply_text(caption, reply_markup=kb)
        try: await cq.message.delete()
        except Exception: pass
        await cq.answer(); return

    if data == "deploy_pay_qr":
        await save_deploy_session(user_id, {"payment_method": "qr"})
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ ɪ ʜᴀᴠᴇ ᴘᴀɪᴅ", callback_data="deploy_have_paid")]])
        if os.path.exists(DEFAULT_QR_PATH):
            await cq.message.reply_photo(DEFAULT_QR_PATH,
                caption="<blockquote>sᴄᴀɴ ǫʀ ᴄᴏᴅᴇ ᴛᴏ ᴘᴀʏ. ᴛʜᴇɴ sᴇɴᴅ sᴄʀᴇᴇɴsʜᴏᴛ.</blockquote>",
                reply_markup=kb)
        else:
            await cq.message.reply_text(
                "<blockquote>ǫʀ ɴᴏᴛ ғᴏᴜɴᴅ. ᴜsᴇ ᴜᴘɪ.</blockquote>",
                reply_markup=payment_method_kb())
        try: await cq.message.delete()
        except Exception: pass
        await cq.answer(); return

    if data == "deploy_have_paid":
        await save_deploy_session(user_id, {"step": "waiting_screenshot"})
        await cq.message.reply_text(
            "<blockquote>📸 sᴇɴᴅ ᴀ sᴄʀᴇᴇɴsʜᴏᴛ ᴏғ ʏᴏᴜʀ ᴘᴀʏᴍᴇɴᴛ.</blockquote>")
        try: await cq.message.delete()
        except Exception: pass
        await cq.answer(); return

    if data.startswith("num_"):
        await handle_numeric_keypad(client, cq, user_id, session); return

    # admin_ catch-all LAST — approve/reject/refund only
    if data.startswith("admin_"):
        await handle_admin_callback(client, cq, user_id); return

    if data.startswith("renew_"):
        await handle_renew_cb(client, cq, user_id, int(data.split("_")[1])); return

    if data.startswith("update_modules_"):
        await handle_update_modules(client, cq, user_id, int(data.split("_")[2])); return

    await cq.answer()

# ─── Numeric keypad ────────────────────────────────────────────────────────────
async def handle_numeric_keypad(client, cq: CallbackQuery, user_id: int, session: dict):
    action      = cq.data.split("_", 1)[1]
    temp_amount = session.get("temp_amount", "")
    if action.isdigit():
        temp_amount += action
    elif action == "dot":
        if "." not in temp_amount: temp_amount += "."
    elif action == "clear":
        temp_amount = ""
    elif action == "confirm":
        if not temp_amount:
            await cq.answer("ᴇɴᴛᴇʀ ᴀɴ ᴀᴍᴏᴜɴᴛ", show_alert=True); return
        try:
            amount = float(temp_amount)
        except ValueError:
            await cq.answer("ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ.", show_alert=True); return
        total_expected = session.get("total")
        if amount != total_expected:
            await cq.answer(
                f"ᴀᴍᴏᴜɴᴛ ᴍɪsᴍᴀᴛᴄʜ. ᴇxᴘᴇᴄᴛᴇᴅ ₹{total_expected}.",
                show_alert=True); return
        pm         = session.get("payment_method")
        is_update  = session.get("is_update", False)
        is_renewal = session.get("is_renewal", False)
        mode       = session.get("mode", "manual")
        if mode == "auto":
            pd = {
                "user_id":          user_id,
                "username":         cq.from_user.username,
                "full_name":        cq.from_user.first_name,
                "token":            session["token"],
                "amount":           amount,
                "method":           pm,
                "proof":            session.get("screenshot_file_id"),
                "type":             "auto",
                "selected_bundles": session.get("selected_bundles", []),
                "modules_plugins":  session.get("auto_modules_set", []),
                "is_update":        is_update,
                "is_renewal":       is_renewal,
            }
        else:
            pd = {
                "user_id":    user_id,
                "username":   cq.from_user.username,
                "full_name":  cq.from_user.first_name,
                "token":      session["token"],
                "modules":    session.get("enabled_modules", []),
                "amount":     amount,
                "method":     pm,
                "proof":      session.get("screenshot_file_id"),
                "type":       "manual",
                "is_update":  is_update,
                "is_renewal": is_renewal,
            }
            if is_update or is_renewal:
                pd["bot_id"]           = session["bot_id"]
                pd["original_modules"] = session.get("original_modules", [])
        pid   = await create_pending_payment(user_id, pd)
        label = "Renewal" if is_renewal else ("Update" if is_update else "New")
        caption = (
            f"<blockquote>**{label} ᴘᴀʏᴍᴇɴᴛ**\n"
            f"👤 [{pd['full_name']}](tg://user?id={user_id}) | 🆔 `{user_id}`\n"
            f"💰 ₹{amount} | 💳 {pm.upper()} | 📦 {mode.upper()}\n"
            f"🤖 `{pd['token']}`</blockquote>"
        )
        if session.get("screenshot_file_id"):
            await client.send_photo(DEPLOY_LOGGER, session["screenshot_file_id"],
                                    caption=caption, reply_markup=admin_review_kb(pid))
        else:
            await client.send_message(DEPLOY_LOGGER, caption, reply_markup=admin_review_kb(pid))
        await _safe_edit(cq.message, "✅ ᴘᴀʏᴍᴇɴᴛ ʀᴇǫᴜᴇsᴛ sᴇɴᴛ. ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...")
        await save_deploy_session(user_id, {"temp_amount": ""}); return
    await save_deploy_session(user_id, {"temp_amount": temp_amount})
    await _safe_edit(cq.message,
        f"<blockquote>**ᴇɴᴛᴇʀ ᴀᴍᴏᴜɴᴛ ᴘᴀɪᴅ (₹):**</blockquote>\n\n`{temp_amount or '0'}`",
        reply_markup=numeric_keypad_kb())
    await cq.answer()

# ─── Screenshot handler ────────────────────────────────────────────────────────
@app.on_message(filters.photo & filters.private)
async def handle_screenshot(client: Client, message: Message):
    user_id = message.from_user.id
    session = await get_deploy_session(user_id)
    if session.get("step") != "waiting_screenshot":
        return
    await save_deploy_session(user_id, {
        "screenshot_file_id": message.photo.file_id,
        "step":               "enter_amount"
    })
    await message.reply_text(
        "<blockquote>**ᴇɴᴛᴇʀ ᴇxᴀᴄᴛ ᴀᴍᴏᴜɴᴛ ʏᴏᴜ ᴘᴀɪᴅ (₹):**</blockquote>",
        reply_markup=numeric_keypad_kb()
    )

# ─── Admin approval ────────────────────────────────────────────────────────────
async def handle_admin_callback(client, cq: CallbackQuery, admin_id: int):
    if admin_id not in ADMINS_ID and admin_id != OWNER_ID:
        await cq.answer("ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.", show_alert=True); return
    parts      = cq.data.split("_")
    action     = parts[1]
    payment_id = parts[2]
    payment    = await get_pending_payment(payment_id)
    if not payment:
        await cq.answer("ᴘᴀʏᴍᴇɴᴛ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True); return

    if action == "approve":
        await cq.answer("Processing...", show_alert=False)
        token      = payment["token"]
        is_update  = payment.get("is_update", False)
        is_renewal = payment.get("is_renewal", False)
        mode       = payment.get("type", "manual")

        # RENEWAL — only extend expiry, NEVER re-deploy
        if is_renewal:
            bot_id  = payment["bot_id"]
            old_bot = await get_deployed_bot_by_id(bot_id)
            if not old_bot:
                await cq.answer("ʙᴏᴛ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True); return
            cur_expiry = old_bot.get("expiry_date", datetime.utcnow())
            base       = cur_expiry if cur_expiry > datetime.utcnow() else datetime.utcnow()
            new_expiry = base + timedelta(days=30)
            await update_deployed_bot(bot_id, {
                "expiry_date":  new_expiry,
                "status":       "active",
                "warning_sent": False,
            })
            pdf = generate_invoice({
                "invoice_id":     str(uuid.uuid4())[:8],
                "User ID":        payment["user_id"],
                "Bot":            old_bot.get("username", ""),
                "Modules":        ", ".join(old_bot.get("modules", [])),
                "Amount":         f"₹{payment['amount']}",
                "Payment Method": payment["method"].upper(),
                "Payment Date":   ist_now().strftime("%d-%m-%Y %I:%M %p IST"),
                "Expiry Date":    to_ist(new_expiry).strftime("%d-%m-%Y %I:%M %p IST"),
            })
            try:
                await client.send_document(payment["user_id"], pdf,
                    caption="<blockquote>🧾 **ʀᴇɴᴇᴡᴀʟ ɪɴᴠᴏɪᴄᴇ** — ᴛʜᴀɴᴋ ʏᴏᴜ!</blockquote>")
            except Exception:
                pass
            await _send_to_user(client, payment["user_id"],
                f"<blockquote>✅ **ʙᴏᴛ ʀᴇɴᴇᴡᴇᴅ!**\n"
                f"ʙᴏᴛ: @{old_bot.get('username','')}\n"
                f"ɴᴇᴡ ᴇxᴘɪʀʏ: {to_ist(new_expiry).strftime('%d-%m-%Y %I:%M %p IST')}</blockquote>")
            await _edit_approval_msg(
                cq.message,
                f"<blockquote>🔄 ʀᴇɴᴇᴡᴇᴅ @{old_bot.get('username','')} | "
                f"₹{payment['amount']} | "
                f"ɴᴇᴡ ᴇxᴘɪʀʏ: {to_ist(new_expiry).strftime('%d-%m-%Y')}</blockquote>"
            )
            await delete_pending_payment(payment_id)
            await clear_deploy_session(payment["user_id"])
            return

        # Validate token (update + fresh deploy)
        try:
            resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if resp.status_code != 200: raise AccessTokenInvalid
            bi           = resp.json()["result"]
            bot_id       = bi["id"]
            bot_username = bi["username"]
        except Exception:
            await cq.answer("ɪɴᴠᴀʟɪᴅ ᴛᴏᴋᴇɴ.", show_alert=True)
            await _send_to_user(client, payment["user_id"], "❌ ɪɴᴠᴀʟɪᴅ ʙᴏᴛ ᴛᴏᴋᴇɴ.")
            await delete_pending_payment(payment_id); return

        if is_update:
            bot_id  = payment["bot_id"]
            old_bot = await get_deployed_bot_by_id(bot_id)
            if not old_bot:
                await cq.answer("ᴏʀɪɢɪɴᴀʟ ʙᴏᴛ ɴᴏᴛ ғᴏᴜɴᴅ.", show_alert=True); return
            old_modules     = old_bot.get("modules", [])
            incoming        = payment.get("modules", payment.get("modules_plugins", []))
            new_modules     = list(set(old_modules + incoming))
            new_plugins     = list(set(get_plugins_for_manual_modules(new_modules) + COMMON_PLUGINS))
            added_modules   = [m for m in incoming if m not in old_modules]
            added_cost      = sum(MODULE_PRICES.get(m, 0) for m in added_modules)
            old_renewal_amt = old_bot.get("renewal_amount", old_bot.get("payment_amount", 0))
            new_renewal_amt = old_renewal_amt + added_cost
            await update_deployed_bot(bot_id, {
                "modules":        new_modules,
                "plugins":        new_plugins,
                "renewal_amount": new_renewal_amt,
            })
            if bot_id in DEPLOYED_CLIENTS:
                try: await DEPLOYED_CLIENTS[bot_id].stop()
                except Exception: pass
                del DEPLOYED_CLIENTS[bot_id]
            DEPLOYED_BOTS.discard(bot_id)
            sdir = f"deploy_sessions/{bot_id}"; os.makedirs(sdir, exist_ok=True)
            bc = Client(name=f"deploy_{bot_id}", api_id=API_ID, api_hash=API_HASH,
                        bot_token=token, workdir=sdir,
                        plugins=dict(root="SHASHA_DRUGZ.dplugins", include=new_plugins))
            await bc.start()
            _register_isolation_handlers(bc, bot_id, old_bot["owner_id"])
            await apply_to_config(bot_id)
            DEPLOYED_CLIENTS[bot_id]    = bc
            DEPLOYED_BOTS.add(bot_id)
            BOT_ALLOWED_PLUGINS[bot_id] = set(new_plugins)
            BOT_OWNERS[bot_id]          = old_bot["owner_id"]
            _iso_cache[bot_id]          = old_bot["owner_id"]
            await _send_to_user(client, payment["user_id"],
                f"<blockquote>✅ ʙᴏᴛ @{bot_username} ᴜᴘᴅᴀᴛᴇᴅ!\n"
                f"ɴᴇᴡ ᴍᴏᴅᴜʟᴇs: {', '.join(added_modules) or 'none'}\n"
                f"ʀᴇɴᴇᴡᴀʟ ᴀᴍᴏᴜɴᴛ: ₹{new_renewal_amt}/ᴍᴏɴᴛʜ</blockquote>")
            await _edit_approval_msg(
                cq.message,
                f"✅ ᴜᴘᴅᴀᴛᴇᴅ @{bot_username} | ʀᴇɴᴇᴡᴀʟ=₹{new_renewal_amt}"
            )
        else:
            # FRESH DEPLOY PATH
            if mode == "auto":
                ap     = list(set(payment.get("modules_plugins", []) + COMMON_PLUGINS))
                dm     = []
                for item in payment.get("selected_bundles", []):
                    if item in AUTO_BOT_TYPES:  dm.append(AUTO_BOT_TYPES[item]["display"])
                    elif item in AUTO_COMBOS:   dm.append(AUTO_COMBOS[item]["display"])
                bundle = "+".join(payment.get("selected_bundles", []))
            else:
                ap     = list(set(get_plugins_for_manual_modules(payment.get("modules", [])) + COMMON_PLUGINS))
                dm     = payment.get("modules", [])
                bundle = "manual"
            sdir = f"deploy_sessions/{bot_id}"; os.makedirs(sdir, exist_ok=True)
            bc = Client(name=f"deploy_{bot_id}", api_id=API_ID, api_hash=API_HASH,
                        bot_token=token, workdir=sdir,
                        plugins=dict(root="SHASHA_DRUGZ.dplugins", include=ap))
            await bc.start()
            bot_me       = await bc.get_me()
            bot_id       = bot_me.id
            bot_username = bot_me.username
            _register_isolation_handlers(bc, bot_id, payment["user_id"])
            await apply_to_config(bot_id)
            await set_bot_commands_and_description(token, bot_username)
            expiry = datetime.utcnow() + timedelta(days=30)
            await save_deployed_bot({
                "bot_id":         bot_id,
                "token":          token,
                "username":       bot_username,
                "name":           bot_me.first_name,
                "owner_id":       payment["user_id"],
                "owner_name":     payment["full_name"],
                "modules":        dm,
                "plugins":        ap,
                "bundle":         bundle,
                "expiry_date":    expiry,
                "payment_amount": payment["amount"],
                "renewal_amount": payment["amount"],
                "payment_method": payment["method"],
                "payment_date":   datetime.utcnow(),
                "status":         "active",
                "warning_sent":   False,
            })
            DEPLOYED_CLIENTS[bot_id]    = bc
            DEPLOYED_BOTS.add(bot_id)
            BOT_ALLOWED_PLUGINS[bot_id] = set(ap)
            BOT_OWNERS[bot_id]          = payment["user_id"]
            _iso_cache[bot_id]          = payment["user_id"]
            pdf = generate_invoice({
                "invoice_id":     str(uuid.uuid4())[:8],
                "User ID":        payment["user_id"],
                "Bot":            bot_username,
                "Modules":        ", ".join(dm),
                "Amount":         f"₹{payment['amount']}",
                "Payment Method": payment["method"].upper(),
                "Payment Date":   ist_now().strftime("%d-%m-%Y %I:%M %p IST"),
                "Expiry Date":    to_ist(expiry).strftime("%d-%m-%Y %I:%M %p IST"),
            })
            try:
                await client.send_document(payment["user_id"], pdf,
                    caption="<blockquote>🧾 **ɪɴᴠᴏɪᴄᴇ** — ᴛʜᴀɴᴋ ʏᴏᴜ!</blockquote>")
            except Exception:
                pass
            await _send_to_user(client, payment["user_id"],
                f"<blockquote>✅ **ʙᴏᴛ ᴅᴇᴘʟᴏʏᴇᴅ!**\n"
                f"ʙᴏᴛ: @{bot_username}\n"
                f"ᴇxᴘɪʀᴇs: {to_ist(expiry).strftime('%d-%m-%Y %I:%M %p IST')}</blockquote>")
            ud  = await raw_mongodb.deploy_users.find_one({"_id": payment["user_id"]})
            isc = bool(ud and ud.get("connected_to_admin") == admin_id)
            await _edit_approval_msg(
                cq.message,
                f"<blockquote>✅ ᴅᴇᴘʟᴏʏᴇᴅ @{bot_username} | ₹{payment['amount']}</blockquote>",
                reply_markup=admin_connection_kb(payment["user_id"], isc)
            )
        await delete_pending_payment(payment_id)
        await clear_deploy_session(payment["user_id"])

    elif action == "reject":
        await cq.answer("Rejected.", show_alert=False)
        await _send_to_user(client, payment["user_id"],
            "<blockquote>❌ ᴘᴀʏᴍᴇɴᴛ ʀᴇᴊᴇᴄᴛᴇᴅ. ᴄᴏɴᴛᴀᴄᴛ sᴜᴘᴘᴏʀᴛ.</blockquote>")
        await _edit_approval_msg(cq.message, "❌ Rejected.")
        await delete_pending_payment(payment_id)
        await clear_deploy_session(payment["user_id"])

    elif action == "refund":
        await cq.answer("Refund processing...", show_alert=False)
        await create_refund({
            "payment_id":  payment_id,
            "user_id":     payment["user_id"],
            "amount":      payment["amount"],
            "method":      payment["method"],
            "bot_token":   payment["token"],
            "refunded_at": ist_now(),
            "status":      "refunded"
        })
        bot = await get_deployed_bot_by_token(payment["token"])
        if bot:
            bid = bot["bot_id"]
            if bid in DEPLOYED_CLIENTS:
                try: await DEPLOYED_CLIENTS[bid].stop()
                except Exception: pass
                DEPLOYED_CLIENTS.pop(bid, None)
            DEPLOYED_BOTS.discard(bid)
            BOT_ALLOWED_PLUGINS.pop(bid, None)
            BOT_OWNERS.pop(bid, None)
            _iso_cache.pop(bid, None)
            await delete_deployed_bot(bid)
            await cleanup_bot_data(bid)   # evict_bot_cache called inside here
        await _send_to_user(client, payment["user_id"],
            f"<blockquote>💸 ʀᴇғᴜɴᴅ ₹{payment['amount']} ᴘʀᴏᴄᴇssᴇᴅ.</blockquote>")
        await _edit_approval_msg(cq.message, "💸 Refunded.")
        await delete_pending_payment(payment_id)
        await clear_deploy_session(payment["user_id"])

# ─── Expiry checker ────────────────────────────────────────────────────────────
async def expiry_checker():
    while True:
        try:
            for bot in await get_expired_bots():
                bid = bot["bot_id"]
                if bid in DEPLOYED_CLIENTS:
                    try: await DEPLOYED_CLIENTS[bid].stop()
                    except Exception: pass
                    del DEPLOYED_CLIENTS[bid]
                DEPLOYED_BOTS.discard(bid)
                BOT_ALLOWED_PLUGINS.pop(bid, None)
                BOT_OWNERS.pop(bid, None)
                _iso_cache.pop(bid, None)
                await cleanup_expired_bot(bid)
                await cleanup_bot_data(bid)   # evict_bot_cache called inside here
                await app.send_message(bot["owner_id"],
                    f"<blockquote>⚠️ ʙᴏᴛ @{bot['username']} ᴇxᴘɪʀᴇᴅ ᴀɴᴅ ʀᴇᴍᴏᴠᴇᴅ.\n"
                    f"ᴅᴇᴘʟᴏʏ ᴀɢᴀɪɴ ᴛᴏ ʀᴇsᴛᴀʀᴛ ғʀᴇsʜ.</blockquote>")
                for admin in ADMINS_ID:
                    await app.send_message(admin, f"⚠️ @{bot['username']} expired & wiped.")
                await app.send_message(DEPLOY_LOGGER, f"⚠️ @{bot['username']} expired & cleaned.")
            for bot in await get_bots_expiring_soon(days=2):
                if bot.get("warning_sent"):
                    continue
                days_left = max((bot["expiry_date"] - datetime.utcnow()).days, 0)
                await app.send_message(bot["owner_id"],
                    f"<blockquote>🔔 ʙᴏᴛ @{bot['username']} ᴇxᴘɪʀᴇs ɪɴ {days_left} ᴅᴀʏ(s). ʀᴇɴᴇᴡ ɴᴏᴡ!</blockquote>",
                    reply_markup=renew_kb(bot["bot_id"]))
                await update_deployed_bot(bot["bot_id"], {"warning_sent": True})
        except Exception:
            logging.exception("expiry checker error")
        await asyncio.sleep(3600)

# ─── handle_renew_cb ──────────────────────────────────────────────────────────
async def handle_renew_cb(client, cq: CallbackQuery, user_id: int, bot_id: int):
    bot = await get_deployed_bot_by_id(bot_id)
    if not bot or bot["owner_id"] != user_id:
        await cq.answer("ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.", show_alert=True); return
    renewal_total = bot.get("renewal_amount", bot.get("payment_amount", 0))
    await save_deploy_session(user_id, {
        "token":           bot["token"],
        "enabled_modules": bot.get("modules", []),
        "step":            "payment_summary",
        "total":           renewal_total,
        "is_renewal":      True,
        "is_update":       False,
        "bot_id":          bot_id,
        "mode":            "manual"
    })
    ml = "\n".join(f"• {m}" for m in bot.get("modules", []))
    await cq.message.reply_text(
        f"<blockquote>**🔄 ʀᴇɴᴇᴡ @{bot['username']}**\n\n"
        f"{ml}\n\n"
        f"**ʀᴇɴᴇᴡᴀʟ ᴀᴍᴏᴜɴᴛ:** ₹{renewal_total}/ᴍᴏɴᴛʜ\n\n"
        f"ᴘʀᴏᴄᴇᴇᴅ?</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💥 ᴘᴀʏ ɴᴏᴡ",  callback_data="deploy_pay_now")],
            [InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻", callback_data="deploy_cancel")]
        ]))
    try: await cq.message.delete()
    except Exception: pass
    await cq.answer()

@app.on_message(filters.command("renew"))
async def renew_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>**ᴜsᴀɢᴇ:** `/renew <bot_username>`</blockquote>")
    bot = await get_deployed_bot_by_username(message.command[1].lstrip('@'))
    if not bot or bot["owner_id"] != message.from_user.id:
        return await message.reply_text("ɴᴏᴛ ғᴏᴜɴᴅ ᴏʀ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ɪᴛ.")
    user_id       = message.from_user.id
    bot_id        = bot["bot_id"]
    renewal_total = bot.get("renewal_amount", bot.get("payment_amount", 0))
    await save_deploy_session(user_id, {
        "token":           bot["token"],
        "enabled_modules": bot.get("modules", []),
        "step":            "payment_summary",
        "total":           renewal_total,
        "is_renewal":      True,
        "is_update":       False,
        "bot_id":          bot_id,
        "mode":            "manual"
    })
    ml = "\n".join(f"• {m}" for m in bot.get("modules", []))
    await message.reply_text(
        f"<blockquote>**🔄 ʀᴇɴᴇᴡ @{bot['username']}**\n\n"
        f"{ml}\n\n"
        f"**ʀᴇɴᴇᴡᴀʟ ᴀᴍᴏᴜɴᴛ:** ₹{renewal_total}/ᴍᴏɴᴛʜ\n\n"
        f"ᴘʀᴏᴄᴇᴇᴅ?</blockquote>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💥 ᴘᴀʏ ɴᴏᴡ",  callback_data="deploy_pay_now")],
            [InlineKeyboardButton("🔻 ᴄᴀɴᴄᴇʟ 🔻", callback_data="deploy_cancel")]
        ]))

# ─── handle_update_modules ────────────────────────────────────────────────────
async def handle_update_modules(client, cq, user_id: int, bot_id: int):
    bot = await get_deployed_bot_by_id(bot_id)
    if not bot or bot["owner_id"] != user_id:
        await cq.answer("ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.", show_alert=True); return
    await save_deploy_session(user_id, {
        "token":            bot["token"],
        "enabled_modules":  bot.get("modules", []).copy(),
        "original_modules": bot.get("modules", []),
        "step":             "select_type",
        "is_update":        True,
        "is_renewal":       False,
        "bot_id":           bot_id,
        "mode":             "manual"
    })
    await cq.message.reply_text(
        "<blockquote>sᴇʟᴇᴄᴛ ɴᴇᴡ ᴍᴏᴅᴜʟᴇ ᴛʏᴘᴇ:</blockquote>",
        reply_markup=type_selection_kb())
    try: await cq.message.delete()
    except Exception: pass
    await cq.answer()

# ─── Admin connection helpers ──────────────────────────────────────────────────
async def connect_admin_to_user(client, cq: CallbackQuery, admin_id: int, target_id: int):
    if admin_id not in ADMINS_ID and admin_id != OWNER_ID:
        await cq.answer("Unauthorized.", show_alert=True); return
    await raw_mongodb.deploy_users.update_one(
        {"_id": target_id}, {"$set": {"connected_to_admin": admin_id}}, upsert=True)
    try:
        await cq.message.edit_reply_markup(
            reply_markup=admin_connection_kb(target_id, True))
    except (MessageNotModified, Exception): pass
    await cq.answer("✅ ᴄᴏɴɴᴇᴄᴛᴇᴅ.", show_alert=True)

async def disconnect_admin_from_user(client, cq: CallbackQuery, admin_id: int, target_id: int):
    if admin_id not in ADMINS_ID and admin_id != OWNER_ID:
        await cq.answer("Unauthorized.", show_alert=True); return
    await raw_mongodb.deploy_users.update_one(
        {"_id": target_id}, {"$set": {"connected_to_admin": None}})
    try:
        await cq.message.edit_reply_markup(
            reply_markup=admin_connection_kb(target_id, False))
    except (MessageNotModified, Exception): pass
    await cq.answer("✅ ᴅɪsᴄᴏɴɴᴇᴄᴛᴇᴅ.", show_alert=True)

async def prepare_admin_message(client, cq: CallbackQuery, admin_id: int, target_id: int):
    if admin_id not in ADMINS_ID and admin_id != OWNER_ID:
        await cq.answer("Unauthorized.", show_alert=True); return
    await raw_mongodb.admin_sessions.update_one(
        {"admin_id": admin_id}, {"$set": {"message_target": target_id}}, upsert=True)
    await cq.message.reply_text(
        f"<blockquote>✏️ sᴇɴᴅ ʏᴏᴜʀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴜsᴇʀ `{target_id}` ɴᴏᴡ.</blockquote>")
    await cq.answer()

# ─── Message forwarding ────────────────────────────────────────────────────────
@app.on_message(
    filters.private & filters.user(ADMINS_ID) & filters.text & ~filters.regex(r"^/"),
    group=10
)
async def forward_admin_to_user(client: Client, message: Message):
    admin_id = message.from_user.id
    session  = await raw_mongodb.admin_sessions.find_one({"admin_id": admin_id})
    if not (session and session.get("message_target")):
        return
    target = session["message_target"]
    await _send_to_user(
        client, target,
        f"<blockquote>**📨 ᴍᴇssᴀɢᴇ ғʀᴏᴍ sᴜᴘᴘᴏʀᴛ:**\n\n{message.text}</blockquote>"
    )
    await raw_mongodb.admin_sessions.update_one(
        {"admin_id": admin_id}, {"$set": {"message_target": None}})
    await message.reply_text("✅ ᴍᴇssᴀɢᴇ sᴇɴᴛ ᴛᴏ ᴜsᴇʀ.")

@app.on_message(
    filters.private & ~filters.user(ADMINS_ID) & filters.text & ~filters.regex(r"^/"),
    group=10
)
async def forward_user_to_admin(client: Client, message: Message):
    uid = message.from_user.id
    deploy_session = await get_deploy_session(uid)
    if deploy_session.get("step"):
        return
    ud = await raw_mongodb.deploy_users.find_one({"_id": uid})
    if not (ud and ud.get("connected_to_admin")):
        return
    await client.send_message(
        ud["connected_to_admin"],
        f"<blockquote>**📩 ᴍᴇssᴀɢᴇ ғʀᴏᴍ "
        f"[{message.from_user.first_name}](tg://user?id={uid}) (`{uid}`):**\n\n"
        f"{message.text}</blockquote>"
    )
    await message.reply_text("✅ ᴍᴇssᴀɢᴇ sᴇɴᴛ ᴛᴏ sᴜᴘᴘᴏʀᴛ.")

# ─── User commands ─────────────────────────────────────────────────────────────
@app.on_message(filters.command("mybots"))
async def my_bots(client: Client, message: Message):
    bots = await get_deployed_bots_by_user(message.from_user.id)
    if not bots:
        return await message.reply_text("ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴅᴇᴘʟᴏʏᴇᴅ ᴀɴʏ ʙᴏᴛs ʏᴇᴛ.")
    text = f"<blockquote>**ʏᴏᴜʀ ᴅᴇᴘʟᴏʏᴇᴅ ʙᴏᴛs ({len(bots)}):**</blockquote>\n\n"
    for b in bots:
        exp  = to_ist(b["expiry_date"]).strftime("%d-%m-%Y")
        ramt = b.get("renewal_amount", b.get("payment_amount", 0))
        text += (f"<blockquote>• @{b['username']}\n"
                 f"  ᴇxᴘɪʀᴇs: {exp} | ʀᴇɴᴇᴡᴀʟ: ₹{ramt}/ᴍᴏɴᴛʜ</blockquote>\n")
    await message.reply_text(text)

@app.on_message(filters.command("deployed") & SUDOERS)
async def list_all_deployed(client: Client, message: Message):
    bots = await get_all_deployed_bots()
    if not bots:
        return await message.reply_text("No bots deployed.")
    text = f"**Total: {len(bots)}**\n\n"
    for b in bots:
        text += (f"• @{b['username']} — {b['owner_id']} — "
                 f"{to_ist(b['expiry_date']).strftime('%d-%m-%Y')}\n")
    await message.reply_text(text)

@app.on_message(filters.command("rmdeploy"))
async def remove_deployed_bot_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "<blockquote>ᴜsᴀɢᴇ: `/rmdeploy <token or @username>`</blockquote>")
    q   = message.command[1].strip()
    bot = await get_deployed_bot_by_token(q) or await get_deployed_bot_by_username(q.lstrip('@'))
    if not bot:
        return await message.reply_text("Bot not found.")
    uid = message.from_user.id
    if bot["owner_id"] != uid and uid not in SUDOERS and uid != OWNER_ID:
        return await message.reply_text("ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs ʙᴏᴛ.")
    bid = bot["bot_id"]
    if bid in DEPLOYED_CLIENTS:
        try: await DEPLOYED_CLIENTS[bid].stop()
        except Exception: pass
        del DEPLOYED_CLIENTS[bid]
    DEPLOYED_BOTS.discard(bid)
    BOT_ALLOWED_PLUGINS.pop(bid, None)
    BOT_OWNERS.pop(bid, None)
    _iso_cache.pop(bid, None)
    await delete_deployed_bot(bid)
    await cleanup_bot_data(bid)   # evict_bot_cache called inside here
    await message.reply_text(
        f"<blockquote>✅ ʙᴏᴛ @{bot['username']} ʀᴇᴍᴏᴠᴇᴅ ᴀɴᴅ ᴀʟʟ ᴅᴀᴛᴀ ᴡɪᴘᴇᴅ.</blockquote>")

@app.on_message(filters.command("rmalldeploy") & filters.user(OWNER_ID))
async def remove_all_deployed(client: Client, message: Message):
    await message.reply_text("⚠️ ʀᴇᴍᴏᴠᴇ ᴀʟʟ ᴅᴇᴘʟᴏʏᴇᴅ ʙᴏᴛs?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_rmalldeploy"),
            InlineKeyboardButton("❌ Cancel",  callback_data="cancel_rmalldeploy")
        ]]))

@app.on_callback_query(filters.regex("^(confirm_rmalldeploy|cancel_rmalldeploy)$"))
async def confirm_rmalldeploy_cb(_, cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID:
        await cq.answer("Unauthorized.", show_alert=True); return
    if cq.data == "confirm_rmalldeploy":
        all_bots    = await deploy_bots_col.find({}, {"bot_id": 1}).to_list(length=None)
        all_bot_ids = [b["bot_id"] for b in all_bots]
        for bc in list(DEPLOYED_CLIENTS.values()):
            try: await bc.stop()
            except Exception: pass
        DEPLOYED_CLIENTS.clear(); DEPLOYED_BOTS.clear()
        BOT_ALLOWED_PLUGINS.clear(); BOT_OWNERS.clear(); _iso_cache.clear()
        # wipe the entire settings cache in one shot
        from SHASHA_DRUGZ.utils.bot_settings import _cache as _settings_cache
        _settings_cache.clear()
        await deploy_bots_col.delete_many({})
        await raw_mongodb.deploy_chats.delete_many({})
        await raw_mongodb.deploy_users.delete_many({})
        for bid in all_bot_ids:
            await cleanup_bot_data(bid)
        try: await cq.message.edit_text("✅ All bots removed and all data wiped.")
        except MessageNotModified: pass
    else:
        try: await cq.message.edit_text("Cancelled.")
        except MessageNotModified: pass
    await cq.answer()

# ─── Earnings dashboard ────────────────────────────────────────────────────────
@app.on_message(filters.command("earnings") & filters.user(ADMINS_ID + [OWNER_ID]))
async def admin_earnings_dashboard(client, message):
    now = ist_now()
    ts  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ms  = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    bots    = await deploy_bots_col.find().to_list(length=None)
    refunds = await raw_mongodb.deploy_refunds.find().to_list(length=None)
    te = td = tm_e = ac = ex_c = 0
    msp = defaultdict(float); usp = defaultdict(float)
    ref = sum(r["amount"] for r in refunds)
    for b in bots:
        a  = b.get("payment_amount", 0); pd = b.get("payment_date")
        te += a
        msp[b.get("payment_method", "unknown")] += a
        usp[b.get("owner_id")] += a
        if pd:
            pd = to_ist(pd)
            if pd >= ts: td   += a
            if pd >= ms: tm_e += a
        if b.get("status") == "active": ac   += 1
        else:                           ex_c += 1
    top  = sorted(usp.items(), key=lambda x: x[1], reverse=True)[:5]
    ttxt = "\n".join(f"• `{u}` → ₹{a}" for u, a in top) or "—"
    mtxt = "\n".join(f"• {m.upper()} → ₹{a}" for m, a in msp.items()) or "—"
    await message.reply_text(
        "<blockquote>📊 **ᴇᴀʀɴɪɴɢs**</blockquote>\n"
        f"<blockquote>💰 ᴛᴏᴛᴀʟ: ₹{te} | 💸 ʀᴇғᴜɴᴅ: ₹{ref} | ✅ ɴᴇᴛ: ₹{te-ref}\n"
        f"📅 ᴛᴏᴅᴀʏ: ₹{td} | 🗓️ ᴍᴏɴᴛʜ: ₹{tm_e}\n"
        f"🤖 ᴀᴄᴛɪᴠᴇ: {ac} | ⌛ ᴇxᴘɪʀᴇᴅ: {ex_c}\n\n"
        f"💳 ᴍᴇᴛʜᴏᴅs:\n{mtxt}\n\n👑 ᴛᴏᴘ:\n{ttxt}\n\n"
        f"🕒 {now.strftime('%d-%m-%Y %I:%M %p IST')}</blockquote>")

# ─── Restart on startup ────────────────────────────────────────────────────────
async def restart_bots():
    global DEPLOYED_CLIENTS, DEPLOYED_BOTS, BOT_ALLOWED_PLUGINS, BOT_OWNERS
    logging.info("Restarting all deployed bots...")
    bots = await deploy_bots_col.find({"status": "active"}).to_list(length=None)
    n = 1
    for bot in bots:
        token  = bot["token"]
        bot_id = bot["bot_id"]
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if r.status_code != 200:
                await update_deployed_bot(bot_id, {"status": "revoked"}); continue
        except Exception as e:
            logging.error(f"Token error {token}: {e}"); continue
        ap     = bot.get("plugins", [])
        common = COMMON_PLUGINS
        if ap:
            ap = list(set(ap + common))
        else:
            if "bundle" in bot and bot["bundle"] != "manual":
                ps = set(common)
                for p in bot["bundle"].split("+"):
                    ps.update(AUTO_BOT_PLUGINS.get(p, []))
                    ps.update(AUTO_COMBO_PLUGINS.get(p, []))
                ap = list(ps)
            else:
                ap = list(set(get_plugins_for_manual_modules(bot.get("modules", [])) + common))
        try:
            sdir = f"deploy_sessions/{bot_id}"; os.makedirs(sdir, exist_ok=True)
            bc = Client(name=f"deploy_{bot_id}", api_id=API_ID, api_hash=API_HASH,
                        bot_token=token, workdir=sdir,
                        plugins=dict(root="SHASHA_DRUGZ.dplugins", include=ap))
            await bc.start()
            logging.info(f"Bot {n} started: @{bot.get('username','?')}"); n += 1
            bm = await bc.get_me()
            _register_isolation_handlers(bc, bm.id, bot["owner_id"])
            await apply_to_config(bm.id)
            DEPLOYED_CLIENTS[bm.id]    = bc
            DEPLOYED_BOTS.add(bm.id)
            BOT_ALLOWED_PLUGINS[bm.id] = set(ap)
            BOT_OWNERS[bm.id]          = bot["owner_id"]
            _iso_cache[bm.id]          = bot["owner_id"]
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Failed to start @{bot.get('username','?')}: {e}")
    try: await app.send_message(DEPLOY_LOGGER, "✅ ᴀʟʟ ᴅᴇᴘʟᴏʏᴇᴅ ʙᴏᴛs ʀᴇsᴛᴀʀᴛᴇᴅ!")
    except Exception as e: logging.error(f"Restart log failed: {e}")

# ─── /start deploy ────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex("^deploy_start$"))
async def deploy_start_cb(_, cq: CallbackQuery):
    await save_deploy_session(cq.from_user.id, {"step": "wait_token"})
    await cq.message.reply_text(DEPLOY_PROMPT, reply_markup=cancel_button_kb())
    await cq.answer()

@app.on_message(filters.command("start") & filters.regex(r"^/start deploy") & filters.private)
async def start_deploy(client: Client, message: Message):
    await save_deploy_session(message.from_user.id, {"step": "wait_token"})
    await message.reply_text(DEPLOY_PROMPT, reply_markup=cancel_button_kb())

# ─── Plugin permission helpers ────────────────────────────────────────────────
def is_module_allowed(client: Client, module_name: str) -> bool:
    bid = client.me.id if client.me else None
    return module_name in BOT_ALLOWED_PLUGINS.get(bid, set())

def is_bot_owner(client: Client, user_id: int) -> bool:
    bid = client.me.id if client.me else None
    return BOT_OWNERS.get(bid) == user_id

# ─── Load on startup ──────────────────────────────────────────────────────────
load_manual_modules_map()
