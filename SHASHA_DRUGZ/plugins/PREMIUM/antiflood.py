# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  SHASHA_DRUGZ — Approval + CleanService + AntiFlood Module               ║
# ║  FINAL FIXED VERSION                                                      ║
# ║                                                                           ║
# ║  KEY FIXES:                                                               ║
# ║  1. Approved users + Admins are fully exempt from ALL restrictions        ║
# ║     (approval-enforcement, locks, antiflood) via shared is_exempt()       ║
# ║  2. enforce_approval: only runs when approval is STRICTLY True            ║
# ║     — no truthy-value bug, no accidental deletes                          ║
# ║  3. flood_checker: only runs when flood is STRICTLY enabled               ║
# ║     + limit is set — hard guard prevents false triggers                   ║
# ║  4. Normal messages from regular users are NEVER deleted unless:          ║
# ║     • approval ON + user unapproved, OR                                   ║
# ║     • flood limit exceeded (flood ON), OR                                 ║
# ║     • a specific active lock matches the message type                     ║
# ║  5. lock_enforcer (locks.py) must import is_exempt() from this file       ║
# ║     so approved users bypass locks too                                    ║
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

# ─── MongoDB Setup ────────────────────────────────────────────────────────────
mongo        = AsyncIOMotorClient(MONGO_DB_URI)
_db          = mongo["SHASHA_DRUGZ"]
approval_col = _db["approval"]
settings_col = _db["settings"]
flood_col    = _db["flood"]

# ─── In-memory flood tracker ──────────────────────────────────────────────────
_flood_cache: dict[tuple, list] = defaultdict(list)


# ═════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# (is_exempt is exported — import it in locks.py to skip approved users there)
# ═════════════════════════════════════════════════════════════════════════════

async def _is_admin(client, chat_id: int, user_id: int) -> bool:
    """True if user is SUDOER, group admin, or owner."""
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


async def _is_approved(chat_id: int, user_id: int) -> bool:
    """True if user has been /approve-d in this chat."""
    doc = await approval_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc is not None  # strict None check — not just falsy


async def _is_approval_on(chat_id: int) -> bool:
    """
    True ONLY when approval mode is explicitly set to boolean True in DB.
    `is True` prevents truthy-value bugs (e.g. 1, "on", "true").
    """
    data = await settings_col.find_one({"chat_id": chat_id})
    return data is not None and data.get("approval") is True


async def _is_cleanservice_on(chat_id: int) -> bool:
    """True ONLY when cleanservice is explicitly set to boolean True in DB."""
    data = await settings_col.find_one({"chat_id": chat_id})
    return data is not None and data.get("cleanservice") is True


async def _get_flood_settings(chat_id: int) -> tuple:
    """Return (limit: int|None, enabled: bool)."""
    data = await flood_col.find_one({"chat_id": chat_id})
    if data:
        return data.get("limit"), (data.get("enabled") is True)
    return None, False


async def is_exempt(client, chat_id: int, user_id: int) -> bool:
    """
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    CENTRAL EXEMPTION CHECK — single source of truth.
    Import and call this in locks.py as well.

    Returns True  →  user is completely immune to:
        • enforce_approval (this file)
        • flood_checker    (this file)
        • lock_enforcer    (locks.py)

    Exempt if:  SUDOER  OR  admin/owner  OR  approved user
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return True
    except Exception:
        pass
    if await _is_approved(chat_id, user_id):
        return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
# ✅  APPROVAL SYSTEM — Commands
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("approval") & filters.group & ~BANNED_USERS)
async def toggle_approval(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")

    if len(message.command) < 2:
        state  = await _is_approval_on(message.chat.id)
        status = "**ON** ✅" if state else "**OFF** ❌"
        return await message.reply_text(f"**» Approval Mode:** {status}")

    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/approval on` or `/approval off`")

    enabled = (arg == "on")
    await settings_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"approval": enabled}},
        upsert=True,
    )
    if enabled:
        await message.reply_text(
            "**» Approval Mode: ON ✅**\n\n"
            "Only approved users can send messages.\n"
            "Use /approve (reply) to approve someone."
        )
    else:
        await message.reply_text(
            "**» Approval Mode: OFF ❌**\n\nAll users can send messages freely."
        )


@app.on_message(filters.command("approve") & filters.group & ~BANNED_USERS)
async def approve_user(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can approve users.**")

    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» Could not find that user.**")

    if not user:
        return await message.reply_text("**» Reply to a user or provide a username/ID.**")

    if await _is_approved(message.chat.id, user.id):
        return await message.reply_text(f"**» {user.mention} is already approved.**")

    await approval_col.update_one(
        {"chat_id": message.chat.id, "user_id": user.id},
        {"$set": {"name": user.first_name}},
        upsert=True,
    )
    await message.reply_text(
        f"**» ✅ Approved:** {user.mention}\n"
        f"They can now send messages freely — bypasses flood & locks."
    )


@app.on_message(filters.command("unapprove") & filters.group & ~BANNED_USERS)
async def unapprove_user(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can unapprove users.**")

    user = None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
    elif len(message.command) > 1:
        try:
            user = await client.get_users(message.command[1])
        except Exception:
            return await message.reply_text("**» Could not find that user.**")

    if not user:
        return await message.reply_text("**» Reply to a user or provide a username/ID.**")

    result = await approval_col.delete_one({"chat_id": message.chat.id, "user_id": user.id})
    if result.deleted_count:
        await message.reply_text(f"**» ❌ Unapproved:** {user.mention}")
    else:
        await message.reply_text(f"**» {user.mention} was not approved.**")


@app.on_message(filters.command("approved") & filters.group & ~BANNED_USERS)
async def list_approved(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can view approved users.**")

    entries = [doc async for doc in approval_col.find({"chat_id": message.chat.id})]
    if not entries:
        return await message.reply_text("**» No approved users in this group.**")

    lines = ["**» ✅ Approved Users:**\n"]
    for i, doc in enumerate(entries, 1):
        uid  = doc["user_id"]
        name = doc.get("name", "Unknown")
        lines.append(f"**{i}.** [{name}](tg://user?id={uid}) — `{uid}`")
    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


# ═════════════════════════════════════════════════════════════════════════════
# ✅  APPROVAL ENFORCEMENT  (group=3, runs before flood checker at group=6)
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.group & ~filters.service & ~BANNED_USERS, group=3)
async def enforce_approval(client, message: Message):
    """
    DELETE only when ALL of these are true:
      • sender is a real user (not bot)
      • message is not a command (admins must be able to use /approve etc.)
      • approval mode is STRICTLY ON  ← main bug fix
      • user is NOT exempt (not admin, not approved)

    Every other case: return immediately, message passes untouched.
    """
    # 1. Skip bots
    if not message.from_user or message.from_user.is_bot:
        return

    # 2. Never delete commands — needed for admin management
    if message.text and message.text.startswith("/"):
        return

    # 3. ── HARD GUARD ── approval must be boolean True
    #    If approval is OFF (False, None, missing) → return immediately.
    #    This was the root bug: old code did `if not approval_on: return`
    #    but approval_on could be a truthy non-True value.
    if not await _is_approval_on(message.chat.id):
        return

    # 4. Exempt users (admin / approved) always pass
    if await is_exempt(client, message.chat.id, message.from_user.id):
        return

    # 5. Unapproved user + approval ON → delete
    try:
        await message.delete()
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
# 🧹  CLEAN SERVICE
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("cleanservice") & filters.group & ~BANNED_USERS)
async def cleanservice_toggle(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")

    if len(message.command) < 2:
        state  = await _is_cleanservice_on(message.chat.id)
        status = "**ON** 🧹" if state else "**OFF** ❌"
        return await message.reply_text(f"**» Clean Service:** {status}")

    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/cleanservice on` or `/cleanservice off`")

    enabled = (arg == "on")
    await settings_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"cleanservice": enabled}},
        upsert=True,
    )
    if enabled:
        await message.reply_text(
            "**» 🧹 Clean Service: ON**\n\nJoin / leave messages will be auto-deleted."
        )
    else:
        await message.reply_text(
            "**» ❌ Clean Service: OFF**\n\nJoin / leave messages will be visible."
        )


@app.on_message(filters.new_chat_members)
async def auto_delete_join(_, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass


@app.on_message(filters.left_chat_member)
async def auto_delete_leave(_, message: Message):
    if await _is_cleanservice_on(message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════════════
# ⚙️  ANTI-FLOOD — Commands
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("antiflood") & filters.group & ~BANNED_USERS)
async def set_antiflood(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")

    if len(message.command) < 2:
        limit, enabled = await _get_flood_settings(message.chat.id)
        status   = "**ON** ✅" if enabled else "**OFF** ❌"
        lim_text = str(limit) if limit else "Not set"
        return await message.reply_text(
            f"**» Flood Protection:** {status}\n"
            f"**» Message Limit:** `{lim_text}` per 10 sec"
        )

    try:
        limit = int(message.command[1])
        if limit < 1:
            raise ValueError
    except ValueError:
        return await message.reply_text(
            "**» Provide a valid number > 0.**\nExample: `/antiflood 5`"
        )

    await flood_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"limit": limit}},
        upsert=True,
    )
    await message.reply_text(
        f"**» ⚙️ Flood limit set to `{limit}` messages per 10 seconds.**\n"
        f"Use `/flood on` to activate protection."
    )


@app.on_message(filters.command("flood") & filters.group & ~BANNED_USERS)
async def toggle_flood(client, message: Message):
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("**» Only admins can use this command.**")

    if len(message.command) < 2:
        _, enabled = await _get_flood_settings(message.chat.id)
        status = "**ON** ✅" if enabled else "**OFF** ❌"
        return await message.reply_text(f"**» Flood Protection:** {status}")

    arg = message.command[1].lower()
    if arg not in ("on", "off"):
        return await message.reply_text("**» Usage:** `/flood on` or `/flood off`")

    enabled = (arg == "on")
    limit, _ = await _get_flood_settings(message.chat.id)

    if enabled and not limit:
        return await message.reply_text(
            "**» Set a flood limit first.**\nExample: `/antiflood 5`"
        )

    await flood_col.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"enabled": enabled}},
        upsert=True,
    )

    if enabled:
        await message.reply_text(
            f"**» ✅ Flood Protection: ON**\n"
            f"Users sending more than `{limit}` messages in 10 sec will be muted for 60 sec."
        )
    else:
        # Clear in-memory cache for this chat on disable
        for k in [k for k in _flood_cache if k[0] == message.chat.id]:
            del _flood_cache[k]
        await message.reply_text("**» ❌ Flood Protection: OFF**")


# ═════════════════════════════════════════════════════════════════════════════
# ⚙️  FLOOD CHECKER  (group=6, runs after approval enforcement at group=3)
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.group & ~filters.service & ~BANNED_USERS, group=6)
async def flood_checker(client, message: Message):
    """
    Mute + delete ONLY when ALL of these are true:
      • sender is a real user (not bot)
      • message is not a command
      • flood is STRICTLY enabled (enabled is True)  ← main bug fix
      • limit is configured
      • user is NOT exempt (not admin, not approved)  ← approved-user fix
      • user exceeded the message limit within 10 seconds

    Every other case: return immediately. Message passes untouched.
    """
    # 1. Skip bots
    if not message.from_user or message.from_user.is_bot:
        return

    # 2. Commands always pass
    if message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    limit, enabled = await _get_flood_settings(chat_id)

    # 3. ── HARD GUARD ── flood must be boolean True AND limit must be set
    #    If flood is OFF → return immediately. Never touch any message.
    if enabled is not True or not limit:
        return

    # 4. Exempt users (admin / approved) are completely immune
    if await is_exempt(client, chat_id, user_id):
        return

    # 5. Track message timestamps in memory (sliding 10-second window)
    now = time.time()
    key = (chat_id, user_id)
    _flood_cache[key] = [t for t in _flood_cache[key] if now - t < 10]
    _flood_cache[key].append(now)

    # 6. Under limit → message passes untouched
    if len(_flood_cache[key]) <= limit:
        return

    # 7. Over limit → delete flooded message + mute 60 sec
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
            f"**» ⚠️ {message.from_user.mention} muted for 60 seconds — flooding.**",
        )
        # Reset cache so consecutive messages after mute don't re-trigger
        _flood_cache[key] = []
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# MODULE META
# ─────────────────────────────────────────────────────────────────────────────
__menu__     = "CMD_MANAGE"
__mod_name__ = "H_B_89"
__help__ = """
✅ **APPROVAL**
🔻 /approval on|off — enable / disable approval mode
🔻 /approve — reply to a user to approve them (bypasses flood & locks)
🔻 /unapprove — reply to remove approval
🔻 /approved — list all approved users

🧹 **CLEAN SERVICE**
🔻 /cleanservice on|off — auto-delete join / leave messages

⚙️ **ANTI-FLOOD**
🔻 /antiflood <number> — set flood limit (messages per 10 sec)
🔻 /flood on|off — enable / disable flood protection

📌 **Approved users + admins are immune to ALL restrictions.**
"""
