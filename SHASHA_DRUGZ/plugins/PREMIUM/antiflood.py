# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SHASHA_DRUGZ — Approval + CleanService + AntiFlood                      ║
# ║  FULL REWRITE                                                             ║
# ║                                                                           ║
# ║  EXACT RULES:                                                             ║
# ║  1. Normal message (no feature ON)          → NEVER deleted              ║
# ║  2. Admin / SUDOER                          → exempt from everything     ║
# ║  3. Approved user                           → exempt from locks+flood    ║
# ║  4. Approval ON + user NOT approved         → message deleted            ║
# ║  5. Flood ON + limit hit + NOT exempt       → delete + mute 60s         ║
# ║  6. Lock active + msg matches + NOT exempt  → delete                    ║
# ║  7. Commands (/)                            → NEVER deleted              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

import time
from pyrogram import filters
from pyrogram.types import Message, ChatPermissions
from pyrogram.enums import ChatMemberStatus
from collections import defaultdict
from config import MONGO_DB_URI, BANNED_USERS
from motor.motor_asyncio import AsyncIOMotorClient
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS

# ─── MongoDB ──────────────────────────────────────────────────────────────────
mongo        = AsyncIOMotorClient(MONGO_DB_URI)
_db          = mongo["SHASHA_DRUGZ"]
approval_col = _db["approval"]
settings_col = _db["settings"]
flood_col    = _db["flood"]

# ─── In-memory flood tracker ──────────────────────────────────────────────────
_flood_cache: dict[tuple, list] = defaultdict(list)


# ═════════════════════════════════════════════════════════════════════════════
# CORE HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    """True if SUDOER, group admin, or owner."""
    if user_id in SUDOERS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def _is_approved(chat_id: int, user_id: int) -> bool:
    """True if user was /approved in this chat."""
    doc = await approval_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc is not None


async def _is_approval_on(chat_id: int) -> bool:
    """Returns True ONLY when approval is stored as boolean True."""
    data = await settings_col.find_one({"chat_id": chat_id})
    if data is None:
        return False
    return data.get("approval") is True          # strict — not just truthy


async def _is_cleanservice_on(chat_id: int) -> bool:
    data = await settings_col.find_one({"chat_id": chat_id})
    if data is None:
        return False
    return data.get("cleanservice") is True


async def _get_flood_settings(chat_id: int) -> tuple:
    """Returns (limit: int|None, enabled: bool)."""
    data = await flood_col.find_one({"chat_id": chat_id})
    if data:
        return data.get("limit"), (data.get("enabled") is True)
    return None, False


async def is_exempt(client, chat_id: int, user_id: int) -> bool:
    """
    Single exemption check used by ALL enforcement handlers.
    Exempt = SUDOER OR admin/owner OR approved user.
    Approved users are whitelisted — locks + flood do NOT apply to them.
    """
    if user_id in SUDOERS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        if m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except Exception:
        pass
    return await _is_approved(chat_id, user_id)


# ═════════════════════════════════════════════════════════════════════════════
# APPROVAL COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("approval") & filters.group & ~BANNED_USERS)
async def cmd_approval(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")

    args = message.command
    if len(args) < 2:
        on = await _is_approval_on(message.chat.id)
        return await message.reply_text(
            f"**» Approval Mode:** {'**ON** ✅' if on else '**OFF** ❌'}"
        )

    arg = args[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/approval on` or `/approval off`")

    enabled = arg == "on"
    await settings_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"approval": enabled}}, upsert=True
    )
    if enabled:
        await message.reply_text(
            "**» Approval Mode: ON ✅**\n"
            "Only approved users can send messages.\n"
            "Use /approve (reply) to approve."
        )
    else:
        await message.reply_text("**» Approval Mode: OFF ❌**\nAll users can chat freely.")


@app.on_message(filters.command("approve") & filters.group & ~BANNED_USERS)
async def cmd_approve(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can approve users.**")

    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» User not found.**")

    if not user:
        return await message.reply_text("**» Reply to a user or give username/ID.**")
    if await _is_approved(message.chat.id, user.id):
        return await message.reply_text(f"**» {user.mention} is already approved.**")

    await approval_col.update_one(
        {"chat_id": message.chat.id, "user_id": user.id},
        {"$set": {"name": user.first_name}},
        upsert=True,
    )
    await message.reply_text(
        f"**» ✅ {user.mention} approved.**\n"
        "They bypass all locks and flood limits."
    )


@app.on_message(filters.command("unapprove") & filters.group & ~BANNED_USERS)
async def cmd_unapprove(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can unapprove.**")

    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» User not found.**")

    if not user:
        return await message.reply_text("**» Reply to a user or give username/ID.**")

    result = await approval_col.delete_one({"chat_id": message.chat.id, "user_id": user.id})
    if result.deleted_count:
        await message.reply_text(f"**» ❌ {user.mention} unapproved.**")
    else:
        await message.reply_text(f"**» {user.mention} was not approved.**")


@app.on_message(filters.command("approved") & filters.group & ~BANNED_USERS)
async def cmd_approved_list(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can view this.**")

    entries = [doc async for doc in approval_col.find({"chat_id": message.chat.id})]
    if not entries:
        return await message.reply_text("**» No approved users.**")

    lines = ["**» ✅ Approved Users:**\n"]
    for i, doc in enumerate(entries, 1):
        uid  = doc["user_id"]
        name = doc.get("name", "Unknown")
        lines.append(f"**{i}.** [{name}](tg://user?id={uid}) — `{uid}`")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


# ═════════════════════════════════════════════════════════════════════════════
# APPROVAL ENFORCEMENT  (group=3)
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.group & ~filters.service & ~BANNED_USERS, group=3)
async def enforce_approval(client, message: Message):
    """
    DELETE only when:
      • approval is strictly ON
      • sender is a real non-bot user
      • message is not a command
      • user is NOT exempt (not admin, not approved)

    In every other situation → return immediately, message untouched.
    """
    # Not a real user
    if not message.from_user or message.from_user.is_bot:
        return

    # Commands must always pass
    if message.text and message.text.startswith("/"):
        return

    # ── KEY GUARD: if approval is NOT strictly True → do nothing ─────────────
    # This was the main bug — truthy DB values caused this to run when OFF
    if not await _is_approval_on(message.chat.id):
        return

    # Exempt (admin / approved) → pass
    if await is_exempt(client, message.chat.id, message.from_user.id):
        return

    # Unapproved user + approval ON → delete
    try:
        await message.delete()
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
# CLEAN SERVICE
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("cleanservice") & filters.group & ~BANNED_USERS)
async def cmd_cleanservice(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")

    if len(message.command) < 2:
        on = await _is_cleanservice_on(message.chat.id)
        return await message.reply_text(
            f"**» Clean Service:** {'**ON** 🧹' if on else '**OFF** ❌'}"
        )

    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/cleanservice on` or `/cleanservice off`")

    enabled = arg == "on"
    await settings_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"cleanservice": enabled}}, upsert=True
    )
    if enabled:
        await message.reply_text("**» 🧹 Clean Service: ON**\nJoin/leave messages auto-deleted.")
    else:
        await message.reply_text("**» ❌ Clean Service: OFF**")


@app.on_message(filters.new_chat_members)
async def auto_del_join(_, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass


@app.on_message(filters.left_chat_member)
async def auto_del_leave(_, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# ANTI-FLOOD COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("antiflood") & filters.group & ~BANNED_USERS)
async def cmd_antiflood(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")

    if len(message.command) < 2:
        limit, enabled = await _get_flood_settings(message.chat.id)
        status   = "**ON** ✅" if enabled else "**OFF** ❌"
        lim_text = str(limit) if limit else "Not set"
        return await message.reply_text(
            f"**» Flood Protection:** {status}\n"
            f"**» Limit:** `{lim_text}` msgs / 10 sec"
        )

    try:
        limit = int(message.command[1])
        if limit < 1:
            raise ValueError
    except ValueError:
        return await message.reply_text("**» Valid number > 0 needed.**\nEx: `/antiflood 5`")

    await flood_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"limit": limit}}, upsert=True
    )
    await message.reply_text(
        f"**» Flood limit set: `{limit}` msgs / 10 sec.**\nUse `/flood on` to enable."
    )


@app.on_message(filters.command("flood") & filters.group & ~BANNED_USERS)
async def cmd_flood_toggle(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this.**")

    if len(message.command) < 2:
        _, enabled = await _get_flood_settings(message.chat.id)
        return await message.reply_text(
            f"**» Flood Protection:** {'**ON** ✅' if enabled else '**OFF** ❌'}"
        )

    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/flood on` or `/flood off`")

    enabled = arg == "on"
    limit, _ = await _get_flood_settings(message.chat.id)

    if enabled and not limit:
        return await message.reply_text(
            "**» Set limit first.**\nEx: `/antiflood 5`"
        )

    await flood_col.update_one(
        {"chat_id": message.chat.id}, {"$set": {"enabled": enabled}}, upsert=True
    )

    if enabled:
        await message.reply_text(
            f"**» ✅ Flood Protection: ON**\n"
            f">`{limit}` msgs in 10 sec = 60s mute."
        )
    else:
        for k in [k for k in _flood_cache if k[0] == message.chat.id]:
            del _flood_cache[k]
        await message.reply_text("**» ❌ Flood Protection: OFF**")


# ═════════════════════════════════════════════════════════════════════════════
# FLOOD CHECKER  (group=6, after approval enforcement at group=3)
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.group & ~filters.service & ~BANNED_USERS, group=6)
async def flood_checker(client, message: Message):
    """
    Act ONLY when ALL conditions are true:
      1. Real non-bot user
      2. Not a command
      3. Flood is strictly enabled AND limit is set
      4. User is NOT exempt

    Otherwise → return immediately. Message untouched.
    """
    if not message.from_user or message.from_user.is_bot:
        return

    if message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    limit, enabled = await _get_flood_settings(chat_id)

    # ── HARD GUARD: flood must be boolean True + limit must exist ─────────────
    if enabled is not True or not limit:
        return

    # Exempt → pass
    if await is_exempt(client, chat_id, user_id):
        return

    # Sliding 10-second window
    now = time.time()
    key = (chat_id, user_id)
    _flood_cache[key] = [t for t in _flood_cache[key] if now - t < 10]
    _flood_cache[key].append(now)

    # Under limit → pass
    if len(_flood_cache[key]) <= limit:
        return

    # Over limit → delete + mute
    try:
        await message.delete()
    except Exception:
        pass

    try:
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=int(now) + 60,
        )
        await client.send_message(
            chat_id,
            f"**» ⚠️ {message.from_user.mention} muted 60s — flooding.**",
        )
        _flood_cache[key] = []
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_89"
__help__ = """
✅ **APPROVAL**
🔻 /approval on|off — approval mode on/off
🔻 /approve — reply to approve (bypasses locks + flood)
🔻 /unapprove — remove approval
🔻 /approved — list approved users

🧹 **CLEAN SERVICE**
🔻 /cleanservice on|off — auto-delete join/leave msgs

⚙️ **ANTI-FLOOD**
🔻 /antiflood <n> — set limit (msgs per 10s)
🔻 /flood on|off — enable/disable flood protection

📌 Admins + Approved users → immune to all restrictions.
"""
