# SHASHA_DRUGZ/dplugins/COMMON/PREMIUM/setbotinfo.py
# =====================================================================
# FULLY ISOLATED PER-BOT SETTINGS MODULE
#
# ASSISTANT CHANGE FIX (v3):
#   The previous attempts failed because get_assistant() in database.py
#   works with integer numbers (1-5) that map to userbot.one/.two/etc.
#   We cannot inject a custom Pyrogram Client into that system directly.
#
#   CORRECT APPROACH:
#   1. We maintain a module-level dict: _CUSTOM_ASSISTANTS = {bot_id: Client}
#   2. We maintain a mapping: _CHAT_TO_BOT = {chat_id: bot_id}
#      This is populated from deploy_chats collection.
#   3. We patch database.get_assistant ONCE so that:
#      - It checks if chat_id is in _CHAT_TO_BOT
#      - If yes, checks if that bot_id has a custom client in _CUSTOM_ASSISTANTS
#      - If yes, returns the custom client directly
#      - Otherwise falls through to original logic
#   4. On /setassistant:
#      - Start new Pyrogram Client with the string session
#      - Store in _CUSTOM_ASSISTANTS[bot_id]
#      - Populate _CHAT_TO_BOT for all chats from deploy_chats
#      - The patch handles the rest transparently
#
#   This works because pytgcalls calls get_assistant(chat_id) to get the
#   userbot that joins voice chats. By intercepting at that exact point
#   and returning our custom client, the voice call uses our assistant.
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

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM ASSISTANT REGISTRY
# _CUSTOM_ASSISTANTS: {bot_id (int): pyrogram.Client}
# _CHAT_TO_BOT:       {chat_id (int): bot_id (int)}
# ─────────────────────────────────────────────────────────────────────────────
_CUSTOM_ASSISTANTS: dict = {}   # bot_id -> Client
_CHAT_TO_BOT: dict = {}         # chat_id -> bot_id
_GET_ASSISTANT_PATCHED = False


def _patch_get_assistant_once():
    """
    Monkey-patch database.get_assistant exactly once.
    After patching, any call to get_assistant(chat_id) will:
      1. Check if chat_id is served by a deployed bot that has a custom assistant
      2. If yes, return that custom client directly
      3. Otherwise, fall through to the original function
    """
    global _GET_ASSISTANT_PATCHED
    if _GET_ASSISTANT_PATCHED:
        return

    try:
        import SHASHA_DRUGZ.utils.database as _db

        _original = _db.get_assistant

        async def _patched_get_assistant(chat_id: int):
            # Check if this chat belongs to a deployed bot with a custom assistant
            bot_id = _CHAT_TO_BOT.get(chat_id)
            if bot_id is not None:
                custom_client = _CUSTOM_ASSISTANTS.get(bot_id)
                if custom_client is not None:
                    try:
                        # Make sure the client is still connected
                        if custom_client.is_connected:
                            return custom_client
                        else:
                            # Client disconnected, remove it so we fall through
                            logging.warning(
                                f"[setbotinfo] Custom assistant for bot {bot_id} "
                                f"disconnected, falling back to pool"
                            )
                            _CUSTOM_ASSISTANTS.pop(bot_id, None)
                    except Exception:
                        _CUSTOM_ASSISTANTS.pop(bot_id, None)

            # Fall through to original logic (shared pool)
            return await _original(chat_id)

        _db.get_assistant = _patched_get_assistant
        _GET_ASSISTANT_PATCHED = True
        logging.info("[setbotinfo] get_assistant patched — custom assistants active")

    except Exception as e:
        logging.error(f"[setbotinfo] Failed to patch get_assistant: {e}")


async def _reload_assistant(bot_id: int, string_session: str) -> bool:
    """
    Start a Pyrogram Client from the given string session and register it
    as the custom assistant for all chats served by this deployed bot.

    Returns True on success, False on failure.
    """
    # Step 1: Start the new client
    try:
        new_client = Client(
            name=f"deployed_assistant_{bot_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=string_session,
            no_updates=True,
        )
        await new_client.start()
        me = await new_client.get_me()
        logging.info(
            f"[setbotinfo] Started custom assistant for bot {bot_id}: "
            f"@{me.username} ({me.id})"
        )
    except Exception as e:
        logging.error(
            f"[setbotinfo] Cannot start assistant client for bot {bot_id}: {e}"
        )
        return False

    # Step 2: Stop and replace any existing custom assistant for this bot
    old_client = _CUSTOM_ASSISTANTS.get(bot_id)
    if old_client is not None:
        try:
            await old_client.stop()
            logging.info(f"[setbotinfo] Stopped old custom assistant for bot {bot_id}")
        except Exception as ex:
            logging.warning(f"[setbotinfo] Could not stop old assistant: {ex}")

    _CUSTOM_ASSISTANTS[bot_id] = new_client

    # Step 3: Patch get_assistant (idempotent)
    _patch_get_assistant_once()

    # Step 4: Populate _CHAT_TO_BOT from deploy_chats so every chat served
    # by this bot routes to our new custom assistant
    try:
        rows = await raw_mongodb.deploy_chats.find(
            {"bot_id": bot_id}, {"chat_id": 1}
        ).to_list(length=None)

        count = 0
        for row in rows:
            cid = row.get("chat_id")
            if cid:
                _CHAT_TO_BOT[cid] = bot_id
                count += 1

        logging.info(
            f"[setbotinfo] Mapped {count} chats to custom assistant for bot {bot_id}"
        )
    except Exception as e:
        logging.warning(
            f"[setbotinfo] Could not map chats for bot {bot_id}: {e}\n"
            "New assistant will be used for new /play calls but not existing cached chats."
        )

    # Step 5: Also clear the assistantdict cache for these chats so the next
    # get_assistant call re-evaluates (hits our patch) instead of returning
    # the cached pool number
    try:
        import SHASHA_DRUGZ.utils.database as _db
        rows2 = await raw_mongodb.deploy_chats.find(
            {"bot_id": bot_id}, {"chat_id": 1}
        ).to_list(length=None)
        cleared = 0
        for row in rows2:
            cid = row.get("chat_id")
            if cid and cid in _db.assistantdict:
                del _db.assistantdict[cid]
                cleared += 1
        logging.info(f"[setbotinfo] Cleared assistantdict cache for {cleared} chats")
    except Exception as e:
        logging.warning(f"[setbotinfo] Could not clear assistantdict cache: {e}")

    return True


def register_chat_for_bot(chat_id: int, bot_id: int):
    """
    Call this whenever a new chat is added to a deployed bot so it gets
    routed to the custom assistant (if one is set).
    """
    if bot_id in _CUSTOM_ASSISTANTS:
        _CHAT_TO_BOT[chat_id] = bot_id


def unregister_chat(chat_id: int):
    """Remove chat from custom routing."""
    _CHAT_TO_BOT.pop(chat_id, None)


def unregister_bot(bot_id: int):
    """
    Remove all routing for a bot and stop its custom assistant.
    Call on bot expiry/removal.
    """
    to_remove = [cid for cid, bid in _CHAT_TO_BOT.items() if bid == bot_id]
    for cid in to_remove:
        _CHAT_TO_BOT.pop(cid, None)
    client = _CUSTOM_ASSISTANTS.pop(bot_id, None)
    if client is not None:
        try:
            asyncio.create_task(client.stop())
        except Exception:
            pass


# Apply patch at import time
_patch_get_assistant_once()


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


# ═════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("setstartimg") & filters.private)
async def set_start_image(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setstartimg https://image-url.jpg`\n\n"
            "Updates the start image and all image aliases."
        )
    url = message.command[1].strip()
    if not url.startswith("http"):
        return await message.reply_text("❌ Invalid image URL. Must start with `http`.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"start_image": url})
    await message.reply_text("✅ Start image updated.")


@Client.on_message(filters.command("setpingimg") & filters.private)
async def set_ping_image(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/setpingimg https://image-url.jpg`")
    url = message.command[1].strip()
    if not url.startswith("http"):
        return await message.reply_text("❌ Invalid image URL.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"ping_image": url})
    await message.reply_text("✅ Ping image updated.")


@Client.on_message(filters.command("setupdates") & filters.private)
async def set_update_channel(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/setupdates @channelusername`")
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
    await message.reply_text(f"✅ Update channel set to `@{channel}`")


@Client.on_message(filters.command("setsupport") & filters.private)
async def set_support(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/setsupport @groupusername`")
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
    await message.reply_text(f"✅ Support chat set to `@{support}`")


@Client.on_message(filters.command("setstartmsg") & filters.private)
async def set_start_message(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/setstartmsg Welcome {mention}! to {bot}`"
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    new_msg = message.text.split(None, 1)[1]
    await _update(bid, {"start_message": new_msg})
    await message.reply_text("✅ Start message updated.")


@Client.on_message(filters.command("setmustjoin") & filters.private)
async def set_must_join(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/setmustjoin @channel`")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    link = message.command[1].strip().lstrip("@")
    await _update(bid, {"must_join.link": link, "must_join.enabled": True})
    await message.reply_text(f"✅ Must Join set to `@{link}` and enabled.")


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
            return await message.reply_text("❌ Use `/setmustjoin @channel` first.")
        await _update(bid, {"must_join.enabled": new_status})
        return await message.reply_text(
            "✅ Must Join Enabled." if new_status else "❌ Must Join Disabled."
        )
    data = await _col(bid).find_one({"_id": "config"})
    mj = (data or {}).get("must_join") or {}
    if not mj.get("link"):
        return await message.reply_text("❌ Use `/setmustjoin @channel` first.")
    new_status = not mj.get("enabled", False)
    await _update(bid, {"must_join.enabled": new_status})
    await message.reply_text(
        "✅ Must Join Enabled." if new_status else "❌ Must Join Disabled."
    )


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


@Client.on_message(filters.command("setgcastmsg") & filters.private)
async def set_gcast_msg(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/setgcastmsg Your message here`")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    gcast_msg = message.text.split(None, 1)[1]
    await _update(bid, {"auto_gcast.message": gcast_msg})
    preview = gcast_msg[:200] + ("..." if len(gcast_msg) > 200 else "")
    await message.reply_text(f"✅ Auto Gcast message updated.\n\n**Preview:**\n{preview}")


@Client.on_message(filters.command("gcaststatus") & filters.private)
async def gcast_status(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No settings found.")
    ag = data.get("auto_gcast") or {}
    msg_preview = ag.get("message") or "Not Set"
    if len(msg_preview) > 200:
        msg_preview = msg_preview[:200] + "..."
    await message.reply_text(
        f"📢 **Auto Gcast Status**\n\n"
        f"➤ Status: {'✅ Enabled' if ag.get('enabled') else '❌ Disabled'}\n"
        f"➤ Message:\n`{msg_preview}`"
    )


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
    await message.reply_text("✅ Logging Enabled." if status else "❌ Logging Disabled.")


@Client.on_message(filters.command("setlogger") & filters.private)
async def set_logger(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setlogger -100xxxxxxxxxx`"
        )
    try:
        group_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid Group ID.")
    if not str(group_id).startswith("-100"):
        return await message.reply_text("❌ Must be a supergroup ID starting with `-100`.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    try:
        await client.send_message(group_id, "✅ Logging activated for this bot.")
        await _update(bid, {"log_channel": group_id, "logging": True})
        await message.reply_text(f"✅ Logger group set to `{group_id}`")
    except Exception:
        await message.reply_text(
            "❌ Can't send to that group. Make sure this bot is admin there."
        )


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


# ── /setassistant — THE KEY COMMAND ──────────────────────────────────────────
@Client.on_message(filters.command("setassistant") & filters.private)
async def set_assistant_cmd(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setassistant <string_session>`\n\n"
            "Provide a valid Pyrogram v2 string session.\n"
            "The assistant will be switched immediately — no restart needed."
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    session_str = message.command[1].strip()

    # Save to DB
    await _update(bid, {
        "assistant_mode":   "single",
        "assistant_string": session_str,
        "assistant_multi":  [],
    })

    # Reload live
    status_msg = await message.reply_text("⏳ Starting new assistant userbot...")
    reload_ok = await _reload_assistant(bid, session_str)

    if reload_ok:
        try:
            new_client = _CUSTOM_ASSISTANTS.get(bid)
            me = await new_client.get_me()
            await status_msg.edit_text(
                f"✅ **Assistant switched successfully!**\n\n"
                f"New assistant: [{me.first_name}](tg://user?id={me.id}) (@{me.username or 'no username'})\n\n"
                f"All future `/play` commands will use this assistant.\n"
                f"No restart needed."
            )
        except Exception:
            await status_msg.edit_text(
                "✅ **Assistant switched successfully!**\n"
                "New assistant is now active — no restart needed."
            )
    else:
        await status_msg.edit_text(
            "❌ **Failed to start the assistant.**\n\n"
            "The session string was saved to the database.\n"
            "Please check:\n"
            "• The session string is valid (Pyrogram v2 format)\n"
            "• The account is not banned or terminated\n"
            "• Your API_ID and API_HASH match the session\n\n"
            "The new session will be used after bot restart."
        )


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
        f"⏳ Starting assistant from {len(sessions)} session(s)..."
    )

    reload_ok = await _reload_assistant(bid, sessions[0])
    if reload_ok:
        try:
            new_client = _CUSTOM_ASSISTANTS.get(bid)
            me = await new_client.get_me()
            await status_msg.edit_text(
                f"✅ **Assistant switched!**\n\n"
                f"Primary: [{me.first_name}](tg://user?id={me.id}) (@{me.username or 'no username'})\n"
                f"Sessions saved: {len(sessions)}\n\n"
                f"No restart needed."
            )
        except Exception:
            await status_msg.edit_text(
                f"✅ {len(sessions)} session(s) saved. Primary assistant active."
            )
    else:
        await status_msg.edit_text(
            f"❌ Failed to start from first session.\n"
            f"{len(sessions)} sessions saved. Will apply after restart."
        )


# ── /assistantinfo ────────────────────────────────────────────────────────────
@Client.on_message(filters.command("assistantinfo") & filters.private)
async def assistant_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)

    custom_client = _CUSTOM_ASSISTANTS.get(bid)
    if custom_client is not None:
        try:
            me = await custom_client.get_me()
            connected = custom_client.is_connected
            chat_count = sum(1 for v in _CHAT_TO_BOT.values() if v == bid)
            await message.reply_text(
                f"🤝 **Custom Assistant Active**\n\n"
                f"Account: [{me.first_name}](tg://user?id={me.id})\n"
                f"Username: @{me.username or 'None'}\n"
                f"User ID: `{me.id}`\n"
                f"Connected: {'✅ Yes' if connected else '❌ No'}\n"
                f"Serving {chat_count} chat(s)"
            )
        except Exception as e:
            await message.reply_text(
                f"⚠️ Custom assistant registered but error: `{e}`"
            )
    else:
        data = await _col(bid).find_one({"_id": "config"})
        has_saved = data and (data.get("assistant_string") or data.get("assistant_multi"))
        await message.reply_text(
            "📌 **Using Default Assistant Pool**\n\n"
            "No custom assistant is currently active.\n"
            + (
                "A session is saved in DB. Use `/setassistant <session>` again to activate it live."
                if has_saved else
                "Use `/setassistant <session>` to set a custom assistant."
            )
        )


@Client.on_message(filters.command("setstring") & filters.private)
async def set_string_session(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setstring <Pyrogram_StringSession>`"
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"string_session": message.command[1].strip()})
    await message.reply_text(
        "✅ String session updated.\n\n"
        "⚠️ Restart your bot process for the new session to take effect."
    )


@Client.on_message(filters.command("botinfo") & filters.private)
async def bot_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No data found.")
    custom_live = bid in _CUSTOM_ASSISTANTS
    await message.reply_text(
        f"🤖 **Bot Info**\n\n"
        f"➤ Bot ID: `{bid}`\n"
        f"➤ Bot Username: @{data.get('bot_username') or 'Unknown'}\n"
        f"➤ Owner ID: `{data.get('owner_id') or 'Unknown'}`\n"
        f"➤ Update Channel: {('@' + data['update_channel']) if data.get('update_channel') else 'Not Set'}\n"
        f"➤ Support Chat: {('@' + data['support_chat']) if data.get('support_chat') else 'Not Set'}\n"
        f"➤ Start Image: {'✅ Custom' if data.get('start_image') else '📌 Default'}\n"
        f"➤ String Session: {'✅ Custom' if data.get('string_session') else '📌 Default (config.py)'}\n"
        f"➤ Assistant: {'✅ Custom LIVE' if custom_live else ('💾 Saved (not live)' if data.get('assistant_string') else '📌 Default pool')}\n"
        f"➤ Logging: {'✅ Enabled' if data.get('logging') else '❌ Disabled'}\n\n"
        f"Use /assistantinfo for assistant account details."
    )


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
    start_img = data.get("start_image") or "Default"
    ping_img  = data.get("ping_image")  or "Default"
    if len(start_img) > 55: start_img = start_img[:52] + "..."
    if len(ping_img)  > 55: ping_img  = ping_img[:52]  + "..."
    gcast_msg = ag.get("message") or "Default"
    if len(gcast_msg) > 80: gcast_msg = gcast_msg[:77] + "..."
    update_ch = (f"@{data['update_channel']}") if data.get("update_channel") else "Default"
    support   = (f"@{data['support_chat']}")   if data.get("support_chat")   else "Default"
    string_s  = "✅ Custom" if data.get("string_session") else "📌 Default"
    ass_mode  = data.get("assistant_mode") or "Not Set"
    custom_live = bid in _CUSTOM_ASSISTANTS
    if custom_live:
        ass_str = "✅ Custom LIVE"
    elif data.get("assistant_string") or data.get("assistant_multi"):
        ass_str = "💾 Saved — run /setassistant to activate"
    else:
        ass_str = "📌 Default pool"
    await message.reply_text(
        f"⚙️ **Bot Settings** — `{bid}`\n\n"
        f"🖼 **Images**\n"
        f"  ➤ Start Image: `{start_img}`\n"
        f"  ➤ Ping Image: `{ping_img}`\n\n"
        f"🔗 **Links**\n"
        f"  ➤ Update Channel: {update_ch}\n"
        f"  ➤ Support Chat: {support}\n\n"
        f"🚪 **Must Join**\n"
        f"  ➤ Status: {'✅ Enabled' if mj.get('enabled') else '❌ Disabled'}\n"
        f"  ➤ Link: {('@' + mj['link']) if mj.get('link') else 'Not Set'}\n\n"
        f"📢 **Auto Gcast**\n"
        f"  ➤ Status: {'✅ Enabled' if ag.get('enabled') else '❌ Disabled'}\n"
        f"  ➤ Message: `{gcast_msg}`\n\n"
        f"📜 **Logger**\n"
        f"  ➤ Status: {'✅ Enabled' if data.get('logging') else '❌ Disabled'}\n"
        f"  ➤ Log Group: `{data.get('log_channel') or 'Not Set'}`\n\n"
        f"📝 Start Message: {'✅ Custom' if data.get('start_message') else '📌 Not Set'}\n"
        f"🤝 Assistant: `{ass_mode}` — {ass_str}\n"
        f"🔑 String Session: {string_s}"
    )


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
    unregister_bot(bid)
    await message.reply_text(
        "♻️ All bot settings reset to default.\n\n"
        "Custom assistant removed — using default pool again.\n"
        "Owner ID preserved."
    )


@Client.on_message(filters.command("setbothelp") & filters.private)
async def set_bot_help(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    sections = [
        (
            "🤖 **Bot Settings — Full Command Reference**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "_Owner-only. Must be sent in **private chat** with your bot._"
        ),
        (
            "🖼 **IMAGES**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setstartimg <url>`** — Sets start image + all aliases\n"
            "**`/setpingimg <url>`** — Sets ping command image\n"
            "➤ Reset: `/resetbotset`"
        ),
        (
            "🔗 **LINKS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setupdates @channel`** — Sets update channel\n"
            "**`/setsupport @group`** — Sets support group\n"
            "Takes effect immediately — no restart needed."
        ),
        (
            "🚪 **MUST JOIN**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setmustjoin @channel`** — Set channel + enable\n"
            "**`/mustjoin enable|disable`** — Toggle\n"
            "**`/mustjoin`** — Toggle (no args)"
        ),
        (
            "📝 **START MESSAGE**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setstartmsg <text>`**\n"
            "Placeholders: `{mention}` `{bot}`"
        ),
        (
            "📢 **AUTO GCAST**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/autogcast enable|disable`**\n"
            "**`/setgcastmsg <text>`**\n"
            "**`/gcaststatus`**"
        ),
        (
            "📜 **LOGGER**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setlogger -100xxxxxxxxxx`** — Bot must be admin in that group\n"
            "**`/logger enable|disable`**\n"
            "**`/logstatus`**"
        ),
        (
            "🤝 **ASSISTANT (VOICE CHAT)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setassistant <string_session>`**\n"
            "Switches the userbot that joins voice chats.\n"
            "➤ Takes effect **IMMEDIATELY** — no restart needed\n"
            "➤ The new assistant joins future voice calls\n"
            "➤ Must be a valid Pyrogram v2 session string\n\n"
            "**`/setmultiassist <s1> <s2> ...`** — Save multiple, use first as primary\n"
            "**`/assistantinfo`** — Show active assistant account\n"
            "➤ Reset: `/resetbotset`"
        ),
        (
            "🔑 **STRING SESSION**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setstring <session>`** — STRING_SESSION for bot process\n"
            "⚠️ Requires restart to apply."
        ),
        (
            "👑 **OWNERSHIP**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/transferowner <@user or id>`** — Transfer via BotFather\n"
            "**`/changeowner <@user or id>`** — Update owner in DB"
        ),
        (
            "ℹ️ **INFO & RESET**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/botinfo`** — Key settings summary\n"
            "**`/botsettings`** — Full settings view\n"
            "**`/assistantinfo`** — Current assistant details\n"
            "**`/resetbotset`** — Reset all to defaults (preserves owner)\n"
            "**`/setbothelp`** — This help"
        ),
    ]
    for section in sections:
        await message.reply_text(section)


@Client.on_message(filters.command("transferowner") & filters.private)
async def transfer_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/transferowner <@username or user_id>`\n\n"
            "Transfers Telegram-side ownership via BotFather.\n"
            "You need your Telegram password to confirm."
        )
    target_raw = message.command[1].strip()
    try:
        target_user = await _resolve_user(client, target_raw)
    except Exception as e:
        return await message.reply_text(f"❌ Could not resolve user.\nError: `{e}`")
    target_username = target_user.username
    if not target_username:
        return await message.reply_text("❌ User has no username. BotFather requires a @username.")
    bid = await _bot_id(client)
    me  = client.me or await client.get_me()
    bot_username = me.username or str(bid)
    status_msg = await message.reply_text(
        f"🔄 Initiating BotFather transfer: @{bot_username} → @{target_username}..."
    )
    BOTFATHER_ID = 93372553

    async def _wait_botfather(timeout: int = 20) -> str:
        loop = asyncio.get_event_loop()
        fut  = loop.create_future()
        async def _bf_handler(c: Client, m: Message):
            if m.from_user and m.from_user.id == BOTFATHER_ID and not fut.done():
                fut.set_result(m.text or "")
        h_ref = client.add_handler(
            MessageHandler(_bf_handler, filters.user(BOTFATHER_ID) & filters.private),
            group=999
        )
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            try: client.remove_handler(*h_ref)
            except Exception: pass

    try:
        await client.send_message(BOTFATHER_ID, "/mybots")
        await _wait_botfather(20)
        await client.send_message(BOTFATHER_ID, f"@{bot_username}")
        await _wait_botfather(20)
        await client.send_message(BOTFATHER_ID, "Transfer Ownership")
        reply3 = await _wait_botfather(20)
        if any(w in reply3.lower() for w in ("sorry", "can't", "cannot", "error", "fail")):
            await status_msg.edit_text(f"❌ BotFather rejected.\n\n`{reply3}`"); return
        await client.send_message(BOTFATHER_ID, f"@{target_username}")
        reply4 = await _wait_botfather(20)
        if any(w in reply4.lower() for w in ("password", "confirm", "verification", "enter")):
            await status_msg.edit_text(
                f"⚠️ **Enter your Telegram password in @BotFather to confirm.**\n\n"
                f"BotFather: `{reply4}`\n\nAfter confirming: `/changeowner @{target_username}`"
            )
        elif any(w in reply4.lower() for w in ("sorry", "can't", "cannot", "error", "fail", "invalid")):
            await status_msg.edit_text(f"❌ BotFather rejected @{target_username}.\n\n`{reply4}`")
        else:
            await status_msg.edit_text(
                f"ℹ️ BotFather: `{reply4}`\n\nIf done: `/changeowner @{target_username}`"
            )
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            f"❌ BotFather timeout.\nTransfer manually, then: `/changeowner @{target_username}`"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Error: `{e}`\nTransfer manually, then: `/changeowner @{target_username}`"
        )


@Client.on_message(filters.command("changeowner") & filters.private)
async def change_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/changeowner <@username or user_id>`\n\n"
            "Updates owner in DB. All settings preserved."
        )
    target_raw = message.command[1].strip()
    try:
        target_user = await _resolve_user(client, target_raw)
    except Exception as e:
        return await message.reply_text(f"❌ Could not resolve user.\nError: `{e}`")
    new_owner_id   = target_user.id
    new_owner_name = target_user.first_name or str(new_owner_id)
    bid = await _bot_id(client)
    await _ensure_registered(client)
    deploy_doc = await raw_mongodb.deploy_bots.find_one({"bot_id": bid})
    if not deploy_doc:
        return await message.reply_text("❌ No deploy record found.")
    old_owner_id = deploy_doc.get("owner_id")
    if old_owner_id == new_owner_id:
        return await message.reply_text(f"⚠️ `{new_owner_name}` is already the owner.")
    me = client.me or await client.get_me()
    bot_username = me.username or str(bid)
    await raw_mongodb.deploy_bots.update_one(
        {"bot_id": bid},
        {"$set": {"owner_id": new_owner_id, "owner_name": new_owner_name}}
    )
    await _update(bid, {"owner_id": new_owner_id})
    try:
        from SHASHA_DRUGZ.plugins.PREMIUM.deploy import BOT_OWNERS
        BOT_OWNERS[bid] = new_owner_id
    except Exception: pass
    try:
        from SHASHA_DRUGZ.core.isolation import _owner_cache as _iso_cache
        _iso_cache[bid] = new_owner_id
    except Exception: pass
    if old_owner_id and old_owner_id != new_owner_id:
        try:
            await client.send_message(
                old_owner_id,
                f"⚠️ Ownership of @{bot_username} transferred to "
                f"[{new_owner_name}](tg://user?id={new_owner_id})."
            )
        except Exception: pass
    try:
        await client.send_message(
            new_owner_id,
            f"🎉 You are now the owner of @{bot_username}!\n\nUse `/botsettings` to view settings."
        )
    except Exception: pass
    await message.reply_text(
        f"✅ **Owner changed!**\n\n"
        f"➤ Bot: @{bot_username}\n"
        f"➤ Old Owner: `{old_owner_id}`\n"
        f"➤ New Owner: [{new_owner_name}](tg://user?id={new_owner_id}) (`{new_owner_id}`)\n\n"
        f"All settings preserved ✅"
    )


async def _resolve_user(client: Client, target: str):
    target = target.strip().lstrip("@")
    try:
        return await client.get_users(int(target))
    except ValueError:
        return await client.get_users(target)


# ═════════════════════════════════════════════════════════════════════════════
#  MODULE METADATA
# ═════════════════════════════════════════════════════════════════════════════
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_74"
__help__ = """
**🤖 Bot Settings Commands** _(Owner only, Private chat)_
/setbothelp - SHOW ALL COMMANDS & USAGE
/assistantinfo - Show current assistant details
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "BotEdit"
MOD_PRICE = "0"
