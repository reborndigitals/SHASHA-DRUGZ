# SHASHA_DRUGZ/dplugins/COMMON/PREMIUM/setbotinfo.py
# =====================================================================
# FULLY ISOLATED PER-BOT SETTINGS MODULE
# =====================================================================
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from SHASHA_DRUGZ.core.mongo import raw_mongodb
from SHASHA_DRUGZ.utils.bot_settings import apply_to_config_and_invalidate
from config import ADMINS_ID, API_ID, API_HASH

print("[setbotinfo] MODULE LOADED — isolated per-bot settings")

# ── Collection helper ─────────────────────────────────────────────────────────
def _col(bot_id: int):
    return raw_mongodb[f"bot_{bot_id}_settings"]

# ── Bot-id helper ─────────────────────────────────────────────────────────────
async def _bot_id(client: Client) -> int:
    if client.me is None:
        me = await client.get_me()
        return me.id
    return client.me.id

# ── Auto-register on first use ────────────────────────────────────────────────
async def _ensure_registered(client: Client):
    bid = await _bot_id(client)
    col = _col(bid)
    if await col.find_one({"_id": "config"}) is None:
        deploy_doc = await raw_mongodb.deploy_bots.find_one({"bot_id": bid})
        owner = deploy_doc["owner_id"] if deploy_doc else None
        me = client.me or await client.get_me()
        await col.insert_one({
            "_id":              "config",
            "bot_id":           bid,
            "bot_username":     me.username,
            "owner_id":         owner,
            "start_message":    None,
            "start_image":      None,
            "ping_image":       None,
            "must_join":        {"link": None, "enabled": False},
            "auto_gcast":       {"enabled": False, "message": None},
            "update_channel":   None,
            "support_chat":     None,
            "logging":          False,
            "log_channel":      None,
            "assistant_mode":   None,
            "assistant_string": None,
            "assistant_multi":  [],
            "string_session":   None,
        })
        await apply_to_config_and_invalidate(bid)

# ── Owner validation ──────────────────────────────────────────────────────────
async def _validate_owner(client: Client, user_id: int) -> bool:
    if user_id in ADMINS_ID:
        return True
    bid = await _bot_id(client)
    deploy_doc = await raw_mongodb.deploy_bots.find_one({"bot_id": bid})
    if deploy_doc and deploy_doc.get("owner_id") == user_id:
        return True
    cfg = await _col(bid).find_one({"_id": "config"})
    if cfg:
        owner = cfg.get("owner_id")
        if isinstance(owner, list):
            return user_id in owner
        return owner == user_id
    return False

# ── Core DB write + cache refresh ─────────────────────────────────────────────
async def _update(bot_id: int, fields: dict):
    await _col(bot_id).update_one(
        {"_id": "config"},
        {"$set": fields},
        upsert=True,
    )
    await apply_to_config_and_invalidate(bot_id)

# ── Assistant reload helper ───────────────────────────────────────────────────
# Key fix: The old code tried to find an `assistants` dict keyed by bot_id,
# but `assistants` in the codebase is a list of ints (1..5) for the main
# userbot pool. Deployed bots need their OWN per-bot-id assistant client
# stored separately in a dedicated registry.
#
# Solution:
#   1. Keep a module-level dict  _DEPLOYED_ASSISTANTS: {bot_id: Client}
#   2. Patch `get_assistant` in database.py at runtime so that when a
#      chat_id's assigned assistant number maps to a bot_id that has a
#      custom client in _DEPLOYED_ASSISTANTS, that client is returned.
#   3. On /setassistant we start the new Pyrogram Client, store it in
#      _DEPLOYED_ASSISTANTS[bot_id], and update assistantdict so every
#      chat served by this deployed bot immediately uses the new client.
# ─────────────────────────────────────────────────────────────────────────────

# Registry: bot_id (int) -> Pyrogram Client (the custom assistant)
_DEPLOYED_ASSISTANTS: dict = {}

async def _reload_assistant(bot_id: int, string_session: str) -> bool:
    """
    Start a new Pyrogram userbot client from the given string session and
    register it as the assistant for all chats that belong to this deployed bot.

    Strategy
    --------
    1. Start the new Client with the string session.
    2. Store it in _DEPLOYED_ASSISTANTS[bot_id].
    3. Find every chat_id in deploy_chats that belongs to this bot_id.
    4. Overwrite assistantdict[chat_id] with a sentinel value (bot_id as a
       negative int, since real assistant numbers are 1-5 and bot_ids are
       large positive ints) so `get_assistant` knows to look in
       _DEPLOYED_ASSISTANTS instead of the shared pool.
    5. Monkey-patch get_assistant in database.py once so it handles the
       sentinel correctly — the patch is idempotent.

    Returns True on success, False on failure.
    """
    global _DEPLOYED_ASSISTANTS

    # ── Step 1: start the new client ─────────────────────────────────────────
    try:
        new_client = Client(
            name=f"assistant_{bot_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=string_session,
            no_updates=True,
        )
        await new_client.start()
        me = await new_client.get_me()
        logging.info(f"[setbotinfo] New assistant for bot {bot_id}: @{me.username} ({me.id})")
    except Exception as e:
        logging.error(f"[setbotinfo] Could not start new assistant client for bot {bot_id}: {e}")
        return False

    # ── Step 2: stop old custom assistant if any ──────────────────────────────
    old_client = _DEPLOYED_ASSISTANTS.get(bot_id)
    if old_client is not None:
        try:
            await old_client.stop()
            logging.info(f"[setbotinfo] Stopped old custom assistant for bot {bot_id}")
        except Exception as e:
            logging.warning(f"[setbotinfo] Could not stop old custom assistant for {bot_id}: {e}")

    _DEPLOYED_ASSISTANTS[bot_id] = new_client

    # ── Step 3: patch database.get_assistant once ─────────────────────────────
    _patch_get_assistant()

    # ── Step 4: update assistantdict for all chats served by this bot ─────────
    try:
        import SHASHA_DRUGZ.utils.database as _db

        # Sentinel: we store -bot_id in assistantdict so get_assistant can
        # distinguish it from the normal pool values (1-5).
        sentinel = -bot_id

        served = await raw_mongodb.deploy_chats.find(
            {"bot_id": bot_id}, {"chat_id": 1}
        ).to_list(length=None)

        for row in served:
            chat_id = row.get("chat_id")
            if chat_id:
                _db.assistantdict[chat_id] = sentinel
                # Also persist so it survives restarts:
                await _db.assdb.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"assistant": sentinel}},
                    upsert=True,
                )

        logging.info(
            f"[setbotinfo] Updated assistantdict for {len(served)} chats "
            f"(bot {bot_id}) → sentinel {sentinel}"
        )
    except Exception as e:
        logging.warning(
            f"[setbotinfo] Could not update assistantdict for bot {bot_id}: {e}\n"
            "New assistant is stored and will be used for new chats."
        )

    return True


_get_assistant_patched = False

def _patch_get_assistant():
    """
    Monkey-patch database.get_assistant once so it handles sentinel values
    (negative bot_ids stored by _reload_assistant).

    The patch is transparent when no custom assistant is registered.
    """
    global _get_assistant_patched
    if _get_assistant_patched:
        return

    try:
        import SHASHA_DRUGZ.utils.database as _db

        _original_get_assistant = _db.get_assistant

        async def _patched_get_assistant(chat_id: int):
            # Check in-memory dict first (fastest path)
            assistant_val = _db.assistantdict.get(chat_id)

            # If it's a sentinel (negative value), look in _DEPLOYED_ASSISTANTS
            if assistant_val is not None and isinstance(assistant_val, int) and assistant_val < 0:
                real_bot_id = -assistant_val
                custom = _DEPLOYED_ASSISTANTS.get(real_bot_id)
                if custom is not None:
                    return custom
                # Sentinel present but client gone (e.g. after restart without
                # re-calling _reload_assistant) — fall through to normal logic
                del _db.assistantdict[chat_id]

            # Also check DB in case the sentinel was persisted but not in memory
            dbassistant = await _db.assdb.find_one({"chat_id": chat_id})
            if dbassistant:
                val = dbassistant["assistant"]
                if isinstance(val, int) and val < 0:
                    real_bot_id = -val
                    custom = _DEPLOYED_ASSISTANTS.get(real_bot_id)
                    if custom is not None:
                        _db.assistantdict[chat_id] = val  # re-cache
                        return custom
                    # Stale sentinel in DB — remove it and fall through
                    await _db.assdb.delete_one({"chat_id": chat_id})

            # Normal path
            return await _original_get_assistant(chat_id)

        _db.get_assistant = _patched_get_assistant
        _get_assistant_patched = True
        logging.info("[setbotinfo] get_assistant patched to support custom deployed assistants")

    except Exception as e:
        logging.error(f"[setbotinfo] Failed to patch get_assistant: {e}")


# ── Clean slate reset (used ONLY by /resetbotset) ─────────────────────────────
_OWNER_CHANGE_RESET = {
    "start_message":    None,
    "start_image":      None,
    "ping_image":       None,
    "must_join":        {"link": None, "enabled": False},
    "auto_gcast":       {"enabled": False, "message": None},
    "update_channel":   None,
    "support_chat":     None,
    "logging":          False,
    "log_channel":      None,
    "assistant_mode":   None,
    "assistant_string": None,
    "assistant_multi":  [],
    "string_session":   None,
}

# ── Resolve user from username or user_id string ──────────────────────────────
async def _resolve_user(client: Client, target: str):
    target = target.strip().lstrip("@")
    try:
        user_id = int(target)
        return await client.get_users(user_id)
    except ValueError:
        return await client.get_users(target)

# ═════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

# ── /setstartimg <url> ────────────────────────────────────────────────────────
@Client.on_message(filters.command("setstartimg") & filters.private)
async def set_start_image(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setstartimg https://image-url.jpg`\n\n"
            "Updates the start image for this bot.\n"
            "Also updates playlist, stats, stream, youtube, spotify images."
        )
    url = message.command[1].strip()
    if not url.startswith("http"):
        return await message.reply_text("❌ Invalid image URL. Must start with `http`.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"start_image": url})
    await message.reply_text(
        "✅ Start image updated.\n"
        "All image aliases (playlist, stats, stream, etc.) also updated."
    )

# ── /setpingimg <url> ─────────────────────────────────────────────────────────
@Client.on_message(filters.command("setpingimg") & filters.private)
async def set_ping_image(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setpingimg https://image-url.jpg`"
        )
    url = message.command[1].strip()
    if not url.startswith("http"):
        return await message.reply_text("❌ Invalid image URL. Must start with `http`.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"ping_image": url})
    await message.reply_text("✅ Ping image updated.")

# ── /setupdates @channel ──────────────────────────────────────────────────────
@Client.on_message(filters.command("setupdates") & filters.private)
async def set_update_channel(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setupdates @channelusername`\n\n"
            "Updates config.SUPPORT_CHANNEL for this bot."
        )
    raw = message.command[1].strip()
    if raw.startswith("https://t.me/"):
        channel = raw[len("https://t.me/"):]
    elif raw.startswith("http"):
        channel = raw
    else:
        channel = raw.lstrip("@")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"update_channel": channel})
    await message.reply_text(
        f"✅ Update channel set to `@{channel}`\n\n"
        f"Resolved URL: `https://t.me/{channel}`\n"
        f"Takes effect immediately — no restart needed."
    )

# ── /setsupport @group ────────────────────────────────────────────────────────
@Client.on_message(filters.command("setsupport") & filters.private)
async def set_support(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setsupport @groupusername`\n\n"
            "Updates config.SUPPORT_CHAT for this bot."
        )
    raw = message.command[1].strip()
    if raw.startswith("https://t.me/"):
        support = raw[len("https://t.me/"):]
    elif raw.startswith("http"):
        support = raw
    else:
        support = raw.lstrip("@")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"support_chat": support})
    await message.reply_text(
        f"✅ Support chat set to `@{support}`\n\n"
        f"Resolved URL: `https://t.me/{support}`\n"
        f"Takes effect immediately — no restart needed."
    )

# ── /setstartmsg <text> ───────────────────────────────────────────────────────
@Client.on_message(filters.command("setstartmsg") & filters.private)
async def set_start_message(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/setstartmsg Welcome {mention}! to {bot}`\n\n"
            "Supported placeholders: `{mention}` `{bot}`"
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    new_msg = message.text.split(None, 1)[1]
    await _update(bid, {"start_message": new_msg})
    await message.reply_text("✅ Start message updated.")

# ── /setmustjoin @channel ─────────────────────────────────────────────────────
@Client.on_message(filters.command("setmustjoin") & filters.private)
async def set_must_join(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setmustjoin @channel`\n\n"
            "Sets the must-join channel and enables it."
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    link = message.command[1].strip().lstrip("@")
    await _update(bid, {
        "must_join.link":    link,
        "must_join.enabled": True,
    })
    await message.reply_text(f"✅ Must Join set to `@{link}` and enabled.")

# ── /mustjoin enable | disable ────────────────────────────────────────────────
@Client.on_message(filters.command("mustjoin") & filters.private)
async def toggle_must_join(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    args = message.command
    if len(args) == 2 and args[1].lower() in ("enable", "disable"):
        new_status = args[1].lower() == "enable"
        data = await _col(bid).find_one({"_id": "config"})
        if new_status and not (data or {}).get("must_join", {}).get("link"):
            return await message.reply_text(
                "❌ No Must Join link set.\nUse `/setmustjoin @channel` first."
            )
        await _update(bid, {"must_join.enabled": new_status})
        return await message.reply_text(
            "✅ Must Join Enabled." if new_status else "❌ Must Join Disabled."
        )
    data = await _col(bid).find_one({"_id": "config"})
    mj = (data or {}).get("must_join") or {}
    if not mj.get("link"):
        return await message.reply_text(
            "❌ No Must Join link set.\nUse `/setmustjoin @channel` first."
        )
    new_status = not mj.get("enabled", False)
    await _update(bid, {"must_join.enabled": new_status})
    await message.reply_text(
        "✅ Must Join Enabled." if new_status else "❌ Must Join Disabled."
    )

# ── /autogcast enable | disable ───────────────────────────────────────────────
@Client.on_message(filters.command("autogcast") & filters.private)
async def toggle_auto_gcast(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    args = message.command
    if len(args) < 2 or args[1].lower() not in ("enable", "disable"):
        return await message.reply_text(
            "**Usage:** `/autogcast enable` or `/autogcast disable`"
        )
    new_status = args[1].lower() == "enable"
    await _update(bid, {"auto_gcast.enabled": new_status})
    await message.reply_text(
        "✅ Auto Gcast **Enabled**." if new_status else "❌ Auto Gcast **Disabled**."
    )

# ── /setgcastmsg <message> ────────────────────────────────────────────────────
@Client.on_message(filters.command("setgcastmsg") & filters.private)
async def set_gcast_msg(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/setgcastmsg Your broadcast message here`\n\n"
            "Supports HTML formatting."
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    gcast_msg = message.text.split(None, 1)[1]
    await _update(bid, {"auto_gcast.message": gcast_msg})
    preview = gcast_msg[:200] + ("..." if len(gcast_msg) > 200 else "")
    await message.reply_text(
        f"✅ Auto Gcast message updated.\n\n**Preview:**\n{preview}"
    )

# ── /gcaststatus ──────────────────────────────────────────────────────────────
@Client.on_message(filters.command("gcaststatus") & filters.private)
async def gcast_status(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No settings found. Use `/botsettings` first.")
    ag = data.get("auto_gcast") or {}
    msg_preview = ag.get("message") or "Not Set"
    if len(msg_preview) > 200:
        msg_preview = msg_preview[:200] + "..."
    await message.reply_text(
        f"📢 **Auto Gcast Status**\n\n"
        f"➤ Status: {'✅ Enabled' if ag.get('enabled') else '❌ Disabled'}\n"
        f"➤ Message:\n`{msg_preview}`"
    )

# ── /logger enable | disable ──────────────────────────────────────────────────
@Client.on_message(filters.command("logger") & filters.private)
async def toggle_logger(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2 or message.command[1].lower() not in ("enable", "disable"):
        return await message.reply_text(
            "**Usage:** `/logger enable` or `/logger disable`"
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    status = message.command[1].lower() == "enable"
    await _update(bid, {"logging": status})
    await message.reply_text(
        "✅ Logging Enabled." if status else "❌ Logging Disabled."
    )

# ── /setlogger -100xxxxxxxxxx ─────────────────────────────────────────────────
@Client.on_message(filters.command("setlogger") & filters.private)
async def set_logger(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setlogger -100xxxxxxxxxx`\n\n"
            "Sets the log group. Bot must be admin in the group."
        )
    try:
        group_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid Group ID.")
    if not str(group_id).startswith("-100"):
        return await message.reply_text("❌ Logger must be a supergroup ID starting with `-100`.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    try:
        await client.send_message(group_id, "✅ Logging activated for this bot.")
        await _update(bid, {"log_channel": group_id, "logging": True})
        await message.reply_text(f"✅ Logger group set to `{group_id}`")
    except Exception:
        await message.reply_text(
            "❌ Bot can't send messages to this group.\n"
            "Make sure the bot is admin in the group."
        )

# ── /logstatus ────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("logstatus") & filters.private)
async def log_status(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No settings found.")
    await message.reply_text(
        f"📜 **Logger Status**\n\n"
        f"➤ Status: {'✅ Enabled' if data.get('logging') else '❌ Disabled'}\n"
        f"➤ Log Group: `{data.get('log_channel') or 'Not Set'}`"
    )

# ── /setassistant <string_session> ───────────────────────────────────────────
@Client.on_message(filters.command("setassistant") & filters.private)
async def set_assistant(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setassistant <string_session>`"
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    session_str = message.command[1].strip()

    # Step 1: Save to DB and refresh cache
    await _update(bid, {
        "assistant_mode":   "single",
        "assistant_string": session_str,
        "assistant_multi":  [],
    })

    # Step 2: Immediately reload the assistant userbot
    status_msg = await message.reply_text("⏳ Saving and reloading assistant userbot...")
    reload_ok = await _reload_assistant(bid, session_str)

    if reload_ok:
        await status_msg.edit_text(
            "✅ Assistant string session updated and reloaded.\n\n"
            "The new assistant is now active — no restart needed."
        )
    else:
        await status_msg.edit_text(
            "✅ Assistant string session saved to database.\n\n"
            "⚠️ Live reload failed (see logs). The new session will be used "
            "after the next bot restart, or once the assistant is re-initialized."
        )

# ── /setmultiassist <str1> <str2> ... ────────────────────────────────────────
@Client.on_message(filters.command("setmultiassist") & filters.private)
async def set_multi_assistant(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/setmultiassist <str1> <str2> ...`"
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    sessions = message.command[1:]

    await _update(bid, {
        "assistant_mode":   "multi",
        "assistant_string": None,
        "assistant_multi":  sessions,
    })

    status_msg = await message.reply_text(
        f"⏳ Saving {len(sessions)} session(s) and reloading assistant..."
    )

    # Reload using the first session as primary
    reload_ok = await _reload_assistant(bid, sessions[0])
    if reload_ok:
        await status_msg.edit_text(
            f"✅ {len(sessions)} assistant session(s) saved and primary assistant reloaded.\n\n"
            "No restart needed."
        )
    else:
        await status_msg.edit_text(
            f"✅ {len(sessions)} assistant session(s) saved to database.\n\n"
            "⚠️ Live reload failed. Will take effect after next restart."
        )

# ── /setstring <STRING_SESSION> ───────────────────────────────────────────────
@Client.on_message(filters.command("setstring") & filters.private)
async def set_string_session(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setstring <Pyrogram_StringSession>`\n\n"
            "Sets the STRING_SESSION for this deployed bot."
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"string_session": message.command[1].strip()})
    await message.reply_text(
        "✅ String session updated.\n\n"
        "⚠️ Restart your bot process for the new session to take effect."
    )

# ── /botinfo ──────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("botinfo") & filters.private)
async def bot_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No data found.")
    custom_assistant = bid in _DEPLOYED_ASSISTANTS
    await message.reply_text(
        f"🤖 **Bot Info**\n\n"
        f"➤ Bot ID: `{bid}`\n"
        f"➤ Bot Username: @{data.get('bot_username') or 'Unknown'}\n"
        f"➤ Owner ID: `{data.get('owner_id') or 'Unknown'}`\n"
        f"➤ Update Channel: {('@' + data['update_channel']) if data.get('update_channel') else 'Not Set (using default)'}\n"
        f"➤ Support Chat: {('@' + data['support_chat']) if data.get('support_chat') else 'Not Set (using default)'}\n"
        f"➤ Start Image: {'✅ Custom' if data.get('start_image') else '📌 Default'}\n"
        f"➤ String Session: {'✅ Custom' if data.get('string_session') else '📌 Default (config.py)'}\n"
        f"➤ Assistant: {'✅ Custom (live)' if custom_assistant else ('✅ Saved (restart needed)' if data.get('assistant_string') or data.get('assistant_multi') else '📌 Default pool')}\n"
        f"➤ Logging: {'✅ Enabled' if data.get('logging') else '❌ Disabled'}"
    )

# ── /botsettings ──────────────────────────────────────────────────────────────
@Client.on_message(filters.command("botsettings") & filters.private)
async def bot_settings_cmd(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No data found.")
    mj  = data.get("must_join")  or {}
    ag  = data.get("auto_gcast") or {}
    start_img = data.get("start_image") or "Default (not customized)"
    ping_img  = data.get("ping_image")  or "Default (not customized)"
    if len(start_img) > 55: start_img = start_img[:52] + "..."
    if len(ping_img)  > 55: ping_img  = ping_img[:52]  + "..."
    gcast_msg = ag.get("message") or "Default (not customized)"
    if len(gcast_msg) > 80: gcast_msg = gcast_msg[:77] + "..."
    update_ch = (f"@{data['update_channel']}") if data.get("update_channel") else "Default"
    support   = (f"@{data['support_chat']}")   if data.get("support_chat")   else "Default"
    string_s  = "✅ Custom" if data.get("string_session") else "📌 Default (config.py)"
    ass_mode  = data.get("assistant_mode") or "Not Set"
    custom_assistant = bid in _DEPLOYED_ASSISTANTS
    if custom_assistant:
        ass_str = "✅ Live (custom assistant active)"
    elif data.get("assistant_string") or data.get("assistant_multi"):
        ass_str = "✅ Saved (restart to apply)"
    else:
        ass_str = "📌 Default pool"
    await message.reply_text(
        f"⚙️ **Bot Settings** — `{bid}`\n\n"
        f"🖼 **Images**\n"
        f"  ➤ Start Image: `{start_img}`\n"
        f"  ➤ Ping Image:  `{ping_img}`\n\n"
        f"🔗 **Links**\n"
        f"  ➤ Update Channel: {update_ch}\n"
        f"  ➤ Support Chat:   {support}\n\n"
        f"🚪 **Must Join**\n"
        f"  ➤ Status: {'✅ Enabled' if mj.get('enabled') else '❌ Disabled'}\n"
        f"  ➤ Link: {('@' + mj['link']) if mj.get('link') else 'Not Set'}\n\n"
        f"📢 **Auto Gcast**\n"
        f"  ➤ Status:  {'✅ Enabled' if ag.get('enabled') else '❌ Disabled'}\n"
        f"  ➤ Message: `{gcast_msg}`\n\n"
        f"📜 **Logger**\n"
        f"  ➤ Status:    {'✅ Enabled' if data.get('logging') else '❌ Disabled'}\n"
        f"  ➤ Log Group: `{data.get('log_channel') or 'Not Set'}`\n\n"
        f"📝 Start Message: {'✅ Custom' if data.get('start_message') else '📌 Not Set'}\n"
        f"🤝 Assistant Mode: `{ass_mode}` — {ass_str}\n"
        f"🔑 String Session: {string_s}"
    )

# ── /resetbotset ──────────────────────────────────────────────────────────────
@Client.on_message(filters.command("resetbotset") & filters.private)
async def reset_bot_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _update(bid, {
        "start_message":    None,
        "start_image":      None,
        "ping_image":       None,
        "must_join":        {"link": None, "enabled": False},
        "auto_gcast":       {"enabled": False, "message": None},
        "update_channel":   None,
        "support_chat":     None,
        "logging":          False,
        "log_channel":      None,
        "assistant_mode":   None,
        "assistant_string": None,
        "assistant_multi":  [],
        "string_session":   None,
    })
    # Also remove custom assistant client if present
    old = _DEPLOYED_ASSISTANTS.pop(bid, None)
    if old:
        try:
            await old.stop()
        except Exception:
            pass
    await message.reply_text(
        "♻️ All bot settings reset to default.\n\n"
        "Config values will now show the hardcoded defaults from config.py.\n"
        "Owner ID has been preserved."
    )

# ── /setbothelp ───────────────────────────────────────────────────────────────
@Client.on_message(filters.command("setbothelp") & filters.private)
async def set_bot_help(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    sections = [
        (
            "🤖 **Bot Settings — Full Command Reference**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "_All commands are owner-only and must be sent in **private chat** with your bot._\n\n"
            "Use the section headers below to jump to the command group you need."
        ),
        (
            "🖼 **IMAGES**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setstartimg <url>`**\n"
            "Sets the start image for your bot.\n"
            "Also updates every image alias in one shot:\n"
            "`PLAYLIST_IMG_URL`, `STATS_IMG_URL`, `STREAM_IMG_URL`,\n"
            "`YOUTUBE_IMG_URL`, `SPOTIFY_ARTIST_IMG_URL`,\n"
            "`SPOTIFY_ALBUM_IMG_URL`, `SPOTIFY_PLAYLIST_IMG_URL`,\n"
            "`TELEGRAM_AUDIO_URL`, `TELEGRAM_VIDEO_URL`, `SOUNCLOUD_IMG_URL`\n"
            "➤ **Arg:** Full image URL (must start with `https://`)\n"
            "➤ **Example:** `/setstartimg https://files.catbox.moe/abc123.jpg`\n"
            "➤ **Reset:** `/resetbotset` — reverts to `config.py` default\n\n"
            "**`/setpingimg <url>`**\n"
            "Sets the image shown when someone uses the `/ping` command.\n"
            "➤ **Arg:** Full image URL (must start with `https://`)\n"
            "➤ **Example:** `/setpingimg https://files.catbox.moe/xyz789.png`\n"
            "➤ **Reset:** `/resetbotset` — reverts to `config.py` default"
        ),
        (
            "🔗 **LINKS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setupdates @channel`**\n"
            "Sets the update/announcement channel shown in bot menus.\n"
            "Maps to `config.SUPPORT_CHANNEL`.\n"
            "➤ **Arg:** Telegram channel username (with or without `@`), or full `https://t.me/` URL\n"
            "➤ **Example:** `/setupdates @MyUpdateChannel`\n"
            "➤ **Effect:** Immediately visible — no restart needed\n"
            "➤ **Reset:** `/resetbotset` — reverts to `config.py` `SUPPORT_CHANNEL`\n\n"
            "**`/setsupport @group`**\n"
            "Sets the support group link shown in bot menus.\n"
            "Maps to `config.SUPPORT_CHAT`.\n"
            "➤ **Arg:** Telegram group username (with or without `@`), or full `https://t.me/` URL\n"
            "➤ **Example:** `/setsupport @MySupportGroup`\n"
            "➤ **Effect:** Immediately visible — no restart needed\n"
            "➤ **Reset:** `/resetbotset` — reverts to `config.py` `SUPPORT_CHAT`"
        ),
        (
            "🚪 **MUST JOIN**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setmustjoin @channel`**\n"
            "Forces users to join a channel before using the bot.\n"
            "Sets the channel AND automatically enables the feature.\n"
            "➤ **Arg:** Channel username (with or without `@`)\n"
            "➤ **Example:** `/setmustjoin @MyChannel`\n"
            "➤ **Note:** Bot must be an admin in the channel to verify membership\n\n"
            "**`/mustjoin enable`** — Enables the must-join check\n"
            "**`/mustjoin disable`** — Disables the must-join check\n"
            "**`/mustjoin`** _(no args)_ — Toggles the current state\n"
            "➤ **Note:** You must set a channel with `/setmustjoin` first before enabling\n"
            "➤ **Reset:** `/resetbotset` — disables must-join and clears the channel"
        ),
        (
            "📝 **START MESSAGE**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setstartmsg <text>`**\n"
            "Sets a custom welcome message sent when users start the bot.\n"
            "➤ **Arg:** Any text, supports HTML formatting and placeholders\n"
            "➤ **Placeholders:**\n"
            "  • `{mention}` — replaced with the user's clickable name\n"
            "  • `{bot}` — replaced with the bot's display name\n"
            "➤ **Example:**\n"
            "  `/setstartmsg 👋 Welcome {mention}! I'm {bot}, ready to serve.`\n"
            "➤ **Reset:** `/resetbotset` — reverts to the module's default start message"
        ),
        (
            "📢 **AUTO GCAST (Broadcast)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/autogcast enable`** — Enables automatic broadcasts\n"
            "**`/autogcast disable`** — Disables automatic broadcasts\n\n"
            "**`/setgcastmsg <message>`**\n"
            "Sets the message that will be auto-broadcast.\n"
            "➤ **Arg:** Any text, supports HTML formatting\n"
            "➤ **Example:**\n"
            "  `/setgcastmsg 🎵 <b>New update available!</b> Check /help`\n\n"
            "**`/gcaststatus`**\n"
            "Shows the current gcast status and a 200-character preview of the message.\n"
            "➤ **No args needed**\n"
            "➤ **Reset:** `/resetbotset` — disables gcast and clears the message"
        ),
        (
            "📜 **LOGGER**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setlogger -100xxxxxxxxxx`**\n"
            "Sets the supergroup where bot activity logs are sent.\n"
            "Maps to `config.LOG_GROUP_ID` and `config.LOGGER_ID`.\n"
            "➤ **Arg:** Supergroup ID (must start with `-100`)\n"
            "➤ **Example:** `/setlogger -1001234567890`\n"
            "➤ **Requirement:** Bot must be admin with send-message permission in that group\n"
            "➤ **Note:** Also automatically enables logging\n\n"
            "**`/logger enable`** — Enables logging\n"
            "**`/logger disable`** — Disables logging\n\n"
            "**`/logstatus`** — Shows current logger status\n"
            "➤ **Reset:** `/resetbotset` — disables logging and clears log group"
        ),
        (
            "🤝 **ASSISTANT SESSION**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setassistant <string_session>`**\n"
            "Sets a single Pyrogram string session as the assistant account.\n"
            "➤ **Arg:** A valid Pyrogram v2 string session\n"
            "➤ **Example:** `/setassistant BQHabc123...`\n"
            "➤ **Effect:** Saves to DB AND immediately reloads the assistant — no restart needed\n"
            "➤ **How it works:** Starts a new Pyrogram Client with your session, stores it in\n"
            "   a per-bot registry, and patches `get_assistant` so all voice calls use it\n"
            "➤ **Note:** Clears any previously set multi-assistant sessions\n\n"
            "**`/setmultiassist <session1> <session2> ...`**\n"
            "Sets multiple assistant string sessions (space-separated).\n"
            "➤ **Args:** Two or more Pyrogram v2 string sessions\n"
            "➤ **Example:** `/setmultiassist BQHabc... BQHxyz...`\n"
            "➤ **Effect:** Saves to DB AND immediately reloads primary assistant\n"
            "➤ **Reset:** `/resetbotset` — stops custom assistant and clears all sessions"
        ),
        (
            "🔑 **STRING SESSION**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setstring <session>`**\n"
            "Sets the `STRING_SESSION` used by this deployed bot instance.\n"
            "Stored in the isolated MongoDB settings so it survives restarts.\n"
            "➤ **Arg:** A valid Pyrogram v2 string session\n"
            "➤ **Example:** `/setstring BQHabc123def456...`\n"
            "➤ **Important:** Restart the bot process after setting for the new session to load\n"
            "➤ **Reset:** `/resetbotset` — clears the custom session, falls back to `config.py STRING1`"
        ),
        (
            "👑 **OWNERSHIP**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/transferowner <@username or user_id>`**\n"
            "Automates a BotFather conversation to transfer **Telegram-side** bot ownership.\n"
            "➤ You will need to confirm with your **Telegram password** in @BotFather\n"
            "➤ After confirming, run `/changeowner` to update the DB\n\n"
            "**`/changeowner <@username or user_id>`**\n"
            "Updates the deployed owner in the database.\n"
            "➤ Updates deploy_bots, bot settings, BOT_OWNERS, isolation cache\n"
            "➤ **All custom settings are preserved** — nothing is reset\n"
            "➤ Use `/resetbotset` explicitly if you want a clean slate"
        ),
        (
            "ℹ️ **INFO & RESET**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/botinfo`** — Key settings summary\n"
            "**`/botsettings`** — Full settings view\n"
            "**`/resetbotset`** — Reset all settings to config.py defaults (preserves owner_id)\n"
            "**`/setbothelp`** — This help message"
        ),
    ]
    for section in sections:
        await message.reply_text(section)

# ── /transferowner <username or userid> ───────────────────────────────────────
@Client.on_message(filters.command("transferowner") & filters.private)
async def transfer_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/transferowner <@username or user_id>`\n\n"
            "⚠️ This transfers **Telegram-side** bot ownership via BotFather.\n"
            "The new owner must have started this bot at least once in the last 6 months.\n"
            "You will need to confirm with your **Telegram password** in @BotFather."
        )
    target_raw = message.command[1].strip()
    try:
        target_user = await _resolve_user(client, target_raw)
    except Exception as e:
        return await message.reply_text(
            f"❌ Could not resolve user `{target_raw}`.\nError: `{e}`"
        )
    target_username = target_user.username
    if not target_username:
        return await message.reply_text(
            f"❌ User [{target_user.first_name}](tg://user?id={target_user.id}) has no username.\n"
            "BotFather requires a @username to transfer ownership."
        )
    bid = await _bot_id(client)
    me  = client.me or await client.get_me()
    bot_username = me.username or str(bid)
    status_msg = await message.reply_text(
        f"🔄 Initiating BotFather ownership transfer...\n"
        f"Bot: @{bot_username} → New Owner: @{target_username}\n\n"
        "Please wait..."
    )
    BOTFATHER_ID = 93372553
    async def _wait_botfather(timeout: int = 20) -> str:
        loop = asyncio.get_event_loop()
        fut  = loop.create_future()
        async def _bf_handler(c: Client, m: Message):
            if (
                m.from_user
                and m.from_user.id == BOTFATHER_ID
                and not fut.done()
            ):
                fut.set_result(m.text or "")
        h_ref = client.add_handler(
            MessageHandler(_bf_handler, filters.user(BOTFATHER_ID) & filters.private),
            group=999
        )
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            try:
                client.remove_handler(*h_ref)
            except Exception:
                pass
    try:
        await client.send_message(BOTFATHER_ID, "/mybots")
        reply1 = await _wait_botfather(20)  # noqa: F841
        await client.send_message(BOTFATHER_ID, f"@{bot_username}")
        reply2 = await _wait_botfather(20)  # noqa: F841
        await client.send_message(BOTFATHER_ID, "Transfer Ownership")
        reply3 = await _wait_botfather(20)
        reply3_lower = reply3.lower()
        if any(w in reply3_lower for w in ("sorry", "can't", "cannot", "error", "fail")):
            await status_msg.edit_text(
                f"❌ BotFather rejected the transfer request.\n\n"
                f"BotFather said:\n`{reply3}`"
            )
            return
        await client.send_message(BOTFATHER_ID, f"@{target_username}")
        reply4 = await _wait_botfather(20)
        reply4_lower = reply4.lower()
        if any(w in reply4_lower for w in ("password", "confirm", "verification", "enter")):
            await status_msg.edit_text(
                f"⚠️ **BotFather requires your Telegram password to complete the transfer.**\n\n"
                f"Please open @BotFather now and enter your **Telegram account password** "
                f"to confirm the ownership transfer of @{bot_username} to @{target_username}.\n\n"
                f"BotFather said:\n`{reply4}`\n\n"
                f"✅ After confirming, run:\n"
                f"`/changeowner @{target_username}`"
            )
        elif any(w in reply4_lower for w in ("sorry", "can't", "cannot", "error", "fail", "invalid")):
            await status_msg.edit_text(
                f"❌ BotFather rejected @{target_username} as new owner.\n\n"
                f"BotFather said:\n`{reply4}`"
            )
        else:
            await status_msg.edit_text(
                f"ℹ️ BotFather responded:\n`{reply4}`\n\n"
                f"If the transfer completed, run:\n"
                f"`/changeowner @{target_username}`"
            )
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "❌ **BotFather did not respond in time.**\n\n"
            f"Please complete the ownership transfer manually via @BotFather,\n"
            f"then run: `/changeowner @{target_username}`"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ BotFather automation failed: `{e}`\n\n"
            f"Please transfer manually via @BotFather, then run:\n"
            f"`/changeowner @{target_username}`"
        )

# ── /changeowner <username or userid> ────────────────────────────────────────
@Client.on_message(filters.command("changeowner") & filters.private)
async def change_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/changeowner <@username or user_id>`\n\n"
            "Updates the deployed owner in the database.\n"
            "✅ All custom bot settings are **fully preserved** — nothing is reset."
        )
    target_raw = message.command[1].strip()
    try:
        target_user = await _resolve_user(client, target_raw)
    except Exception as e:
        return await message.reply_text(
            f"❌ Could not resolve user `{target_raw}`.\nError: `{e}`"
        )
    new_owner_id   = target_user.id
    new_owner_name = target_user.first_name or str(new_owner_id)
    bid = await _bot_id(client)
    await _ensure_registered(client)
    deploy_doc = await raw_mongodb.deploy_bots.find_one({"bot_id": bid})
    if not deploy_doc:
        return await message.reply_text(
            "❌ No deploy record found for this bot.\n"
            "The isolated settings owner_id will still be updated."
        )
    old_owner_id = deploy_doc.get("owner_id")
    if old_owner_id == new_owner_id:
        return await message.reply_text(
            f"⚠️ [`{new_owner_name}`](tg://user?id={new_owner_id}) is already the owner of this bot."
        )
    me = client.me or await client.get_me()
    bot_username = me.username or str(bid)
    await raw_mongodb.deploy_bots.update_one(
        {"bot_id": bid},
        {"$set": {
            "owner_id":   new_owner_id,
            "owner_name": new_owner_name,
        }}
    )
    await _update(bid, {"owner_id": new_owner_id})
    try:
        from SHASHA_DRUGZ.plugins.PREMIUM.deploy import BOT_OWNERS
        BOT_OWNERS[bid] = new_owner_id
    except (ImportError, Exception):
        pass
    try:
        from SHASHA_DRUGZ.core.isolation import _owner_cache as _iso_cache
        _iso_cache[bid] = new_owner_id
    except (ImportError, Exception):
        pass
    if old_owner_id and old_owner_id != new_owner_id:
        try:
            await client.send_message(
                old_owner_id,
                f"⚠️ **Ownership of @{bot_username} has been transferred.**\n\n"
                f"New Owner: [{new_owner_name}](tg://user?id={new_owner_id}) (`{new_owner_id}`)\n\n"
                f"You no longer have owner access to this bot."
            )
        except Exception:
            pass
    try:
        await client.send_message(
            new_owner_id,
            f"🎉 **You are now the owner of @{bot_username}!**\n\n"
            f"Use `/botsettings` to view all current bot settings.\n"
            f"Use `/resetbotset` if you want to start with a clean slate."
        )
    except Exception:
        pass
    await message.reply_text(
        f"✅ **Owner changed successfully!**\n\n"
        f"➤ Bot: @{bot_username}\n"
        f"➤ Old Owner: `{old_owner_id or 'Unknown'}`\n"
        f"➤ New Owner: [{new_owner_name}](tg://user?id={new_owner_id}) (`{new_owner_id}`)\n\n"
        f"✅ **All custom settings preserved** — nothing was reset.\n\n"
        f"Updated:\n"
        f"• `deploy_bots` collection ✅\n"
        f"• `bot_{bid}_settings` collection ✅ (owner_id only)\n"
        f"• In-memory BOT_OWNERS cache ✅\n"
        f"• Isolation owner cache ✅"
    )

# ═════════════════════════════════════════════════════════════════════════════
#  MODULE METADATA
# ═════════════════════════════════════════════════════════════════════════════
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_74"
__help__ = """
**🤖 Bot Settings Commands** _(Owner only, Private chat)_
/setbothelp - SHOW ALL COMMANDS & USAGE
"""

MOD_TYPE = "TOOLS"
MOD_NAME = "BotEdit"
MOD_PRICE = "0"
