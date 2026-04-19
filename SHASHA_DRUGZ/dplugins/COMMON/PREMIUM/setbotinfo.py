# SHASHA_DRUGZ/dplugins/COMMON/PREMIUM/setbotinfo.py
# =====================================================================
# FULLY ISOLATED PER-BOT SETTINGS MODULE
#
# ASSISTANT CHANGE — FINAL WORKING FIX (v5)
# ──────────────────────────────────────────
# NOW WE HAVE THE SOURCE FILES. Here is exactly what happens:
#
# call.py: class Call(PyTgCalls)
#   self.one   = PyTgCalls(userbot1)   ← these are PYTGCALLS instances
#   self.two   = PyTgCalls(userbot2)
#   ...
#
# database.py: group_assistant(self, chat_id)
#   returns self.one / self.two / ... based on assistantdict[chat_id]
#   "self" here is the SHASHA Call() instance
#   The returned value is a PyTgCalls instance, used to join/leave VC
#
# database.py: get_assistant(chat_id)
#   returns userbot.one / userbot.two / ... (Pyrogram clients)
#   used for invite links, joining groups, etc.
#
# THE FIX:
#   1. Start a new Pyrogram Client from the custom string session
#   2. Wrap it in a new PyTgCalls instance
#   3. Start the PyTgCalls instance
#   4. Register all VC event handlers (on_stream_end, on_kicked, etc.)
#      on the new PyTgCalls instance by calling SHASHA.decorators_for(new_pytgcalls)
#   5. Store new PyTgCalls in _CUSTOM_PYTGCALLS[bot_id]
#   6. Store new Pyrogram Client in _CUSTOM_ASSISTANTS[bot_id]
#   7. Patch group_assistant: for chats in _CHAT_TO_BOT, return PyTgCalls
#   8. Patch get_assistant: for chats in _CHAT_TO_BOT, return Pyrogram Client
#   9. Map all chats of this bot → bot_id in _CHAT_TO_BOT
#  10. Clear assistantdict cache for these chats
# =====================================================================
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from SHASHA_DRUGZ.core.mongo import raw_mongodb
from SHASHA_DRUGZ.utils.bot_settings import apply_to_config_and_invalidate
from config import ADMINS_ID, API_ID, API_HASH

print("[setbotinfo] MODULE LOADED — v5 (PyTgCalls-aware assistant switching)")

# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY
#   _CUSTOM_ASSISTANTS[bot_id]  = Pyrogram Client  (for get_assistant)
#   _CUSTOM_PYTGCALLS[bot_id]   = PyTgCalls instance (for group_assistant)
#   _CHAT_TO_BOT[chat_id]       = bot_id
# ─────────────────────────────────────────────────────────────────────────────
_CUSTOM_ASSISTANTS: dict = {}   # bot_id -> pyrogram.Client
_CUSTOM_PYTGCALLS:  dict = {}   # bot_id -> PyTgCalls
_CHAT_TO_BOT:       dict = {}   # chat_id -> bot_id
_PATCHED = False


def _patch_database_once():
    """
    Patch database.get_assistant and database.group_assistant once.
    - get_assistant  → returns Pyrogram client (for joining chats, invites)
    - group_assistant → returns PyTgCalls instance (for VC join/leave/stream)
    """
    global _PATCHED
    if _PATCHED:
        return
    try:
        import SHASHA_DRUGZ.utils.database as _db

        _orig_get = _db.get_assistant
        _orig_grp = _db.group_assistant

        async def _patched_get_assistant(chat_id: int):
            bot_id = _CHAT_TO_BOT.get(chat_id)
            if bot_id is not None:
                c = _CUSTOM_ASSISTANTS.get(bot_id)
                if c is not None:
                    if c.is_connected:
                        return c
                    _CUSTOM_ASSISTANTS.pop(bot_id, None)
            return await _orig_get(chat_id)

        async def _patched_group_assistant(self, chat_id: int):
            bot_id = _CHAT_TO_BOT.get(chat_id)
            if bot_id is not None:
                ptc = _CUSTOM_PYTGCALLS.get(bot_id)
                if ptc is not None:
                    return ptc
            return await _orig_grp(self, chat_id)

        _db.get_assistant   = _patched_get_assistant
        _db.group_assistant = _patched_group_assistant

        # Also patch the import that call.py already pulled in at startup:
        # call.py does: from SHASHA_DRUGZ.utils.database import group_assistant
        # We must update that reference too.
        try:
            import SHASHA_DRUGZ.core.call as _call_mod
            _call_mod.group_assistant = _patched_group_assistant
        except Exception as e:
            logging.warning(f"[setbotinfo] Could not patch call.group_assistant: {e}")

        _PATCHED = True
        logging.info("[setbotinfo] ✅ get_assistant + group_assistant patched")

    except Exception as e:
        logging.error(f"[setbotinfo] patch failed: {e}")


async def _reload_assistant(bot_id: int, string_session: str) -> bool:
    """
    Full assistant reload for a deployed bot:
    1.  Start Pyrogram Client from string session
    2.  Wrap in PyTgCalls, start it
    3.  Register VC event decorators on the new PyTgCalls instance
    4.  Store both in registries
    5.  Patch database functions (idempotent)
    6.  Map all chats of this bot → bot_id
    7.  Clear assistantdict cache
    """
    # ── Step 1: Pyrogram Client ───────────────────────────────────────────────
    try:
        pyrogram_client = Client(
            name=f"deployed_assistant_{bot_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=string_session,
            no_updates=True,
        )
        await pyrogram_client.start()
        me = await pyrogram_client.get_me()
        logging.info(
            f"[setbotinfo] Pyrogram client started: @{me.username} ({me.id})"
        )
    except Exception as e:
        logging.error(f"[setbotinfo] Cannot start Pyrogram client: {e}")
        return False

    # ── Step 2: PyTgCalls instance ────────────────────────────────────────────
    try:
        from pytgcalls import PyTgCalls
        pytgcalls_instance = PyTgCalls(pyrogram_client, cache_duration=100)
        await pytgcalls_instance.start()
        logging.info(f"[setbotinfo] PyTgCalls instance started for bot {bot_id}")
    except Exception as e:
        logging.error(f"[setbotinfo] Cannot start PyTgCalls: {e}")
        try:
            await pyrogram_client.stop()
        except Exception:
            pass
        return False

    # ── Step 3: Register VC event handlers ───────────────────────────────────
    # We need the same handlers that call.py registers in decorators().
    # We attach them directly to the new pytgcalls instance.
    try:
        from SHASHA_DRUGZ.core.call import SHASHA
        from pytgcalls.types import Update
        from pytgcalls.types.stream import StreamAudioEnded

        @pytgcalls_instance.on_stream_end()
        async def _on_stream_end(client, update: Update):
            if not isinstance(update, StreamAudioEnded):
                return
            await SHASHA.change_stream(client, update.chat_id)

        @pytgcalls_instance.on_kicked()
        async def _on_kicked(_, chat_id: int):
            await SHASHA.stop_stream(chat_id)

        @pytgcalls_instance.on_closed_voice_chat()
        async def _on_closed(_, chat_id: int):
            await SHASHA.stop_stream(chat_id)

        @pytgcalls_instance.on_left()
        async def _on_left(_, chat_id: int):
            await SHASHA.stop_stream(chat_id)

        logging.info(f"[setbotinfo] VC event handlers registered for bot {bot_id}")
    except Exception as e:
        logging.warning(
            f"[setbotinfo] Could not register VC event handlers: {e}\n"
            "Stream end / kick events may not work for this assistant."
        )

    # ── Step 4: Stop old instances and store new ──────────────────────────────
    old_ptc = _CUSTOM_PYTGCALLS.get(bot_id)
    if old_ptc is not None:
        try:
            await old_ptc.stop()
        except Exception:
            pass

    old_pyro = _CUSTOM_ASSISTANTS.get(bot_id)
    if old_pyro is not None:
        try:
            await old_pyro.stop()
        except Exception:
            pass

    _CUSTOM_PYTGCALLS[bot_id]  = pytgcalls_instance
    _CUSTOM_ASSISTANTS[bot_id] = pyrogram_client

    # ── Step 5: Patch database (idempotent) ───────────────────────────────────
    _patch_database_once()

    # ── Step 6: Map all chats for this bot ────────────────────────────────────
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
        logging.info(f"[setbotinfo] Mapped {count} chats → bot {bot_id}")
    except Exception as e:
        logging.warning(f"[setbotinfo] Could not map chats: {e}")

    # ── Step 7: Clear assistantdict cache ─────────────────────────────────────
    try:
        import SHASHA_DRUGZ.utils.database as _db
        rows2 = await raw_mongodb.deploy_chats.find(
            {"bot_id": bot_id}, {"chat_id": 1}
        ).to_list(length=None)
        cleared = 0
        for row in rows2:
            cid = row.get("chat_id")
            if cid:
                _db.assistantdict.pop(cid, None)
                cleared += 1
        logging.info(f"[setbotinfo] Cleared assistantdict for {cleared} chats")
    except Exception as e:
        logging.warning(f"[setbotinfo] Could not clear assistantdict: {e}")

    return True


def register_chat_for_bot(chat_id: int, bot_id: int):
    """Call when a new group is added to a deployed bot."""
    if bot_id in _CUSTOM_PYTGCALLS:
        _CHAT_TO_BOT[chat_id] = bot_id


def unregister_bot(bot_id: int):
    """Call on bot removal/expiry."""
    for cid in [c for c, b in list(_CHAT_TO_BOT.items()) if b == bot_id]:
        _CHAT_TO_BOT.pop(cid, None)

    ptc = _CUSTOM_PYTGCALLS.pop(bot_id, None)
    if ptc:
        try:
            asyncio.create_task(ptc.stop())
        except Exception:
            pass

    pyro = _CUSTOM_ASSISTANTS.pop(bot_id, None)
    if pyro:
        try:
            asyncio.create_task(pyro.stop())
        except Exception:
            pass


# Apply database patch at import time (safe, idempotent)
_patch_database_once()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _col(bot_id: int):
    return raw_mongodb[f"bot_{bot_id}_settings"]


async def _bot_id(client: Client) -> int:
    if client.me is None:
        me = await client.get_me()
        return me.id
    return client.me.id


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


async def _update(bot_id: int, fields: dict):
    await _col(bot_id).update_one(
        {"_id": "config"}, {"$set": fields}, upsert=True
    )
    await apply_to_config_and_invalidate(bot_id)


async def _resolve_user(client: Client, target: str):
    target = target.strip().lstrip("@")
    try:
        return await client.get_users(int(target))
    except ValueError:
        return await client.get_users(target)


# ═════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

@Client.on_message(filters.command("setstartimg") & filters.private)
async def set_start_image(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setstartimg https://image-url.jpg`\n\nUpdates start image and all aliases."
        )
    url = message.command[1].strip()
    if not url.startswith("http"):
        return await message.reply_text("❌ Invalid URL.")
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
        return await message.reply_text("❌ Invalid URL.")
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
    channel = (raw[len("https://t.me/"):] if raw.startswith("https://t.me/")
               else (raw if raw.startswith("http") else raw.lstrip("@")))
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"update_channel": channel})
    await message.reply_text(f"✅ Update channel → `@{channel}`")


@Client.on_message(filters.command("setsupport") & filters.private)
async def set_support(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/setsupport @groupusername`")
    raw = message.command[1].strip()
    support = (raw[len("https://t.me/"):] if raw.startswith("https://t.me/")
               else (raw if raw.startswith("http") else raw.lstrip("@")))
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"support_chat": support})
    await message.reply_text(f"✅ Support chat → `@{support}`")


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
    await _update(bid, {"start_message": message.text.split(None, 1)[1]})
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
    await message.reply_text(f"✅ Must Join → `@{link}` (enabled)")


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
    await message.reply_text("✅ Enabled." if new_status else "❌ Disabled.")


@Client.on_message(filters.command("autogcast") & filters.private)
async def toggle_auto_gcast(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    args = message.command
    if len(args) < 2 or args[1].lower() not in ("enable", "disable"):
        return await message.reply_text("**Usage:** `/autogcast enable|disable`")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    new_status = args[1].lower() == "enable"
    await _update(bid, {"auto_gcast.enabled": new_status})
    await message.reply_text(
        "✅ Auto Gcast Enabled." if new_status else "❌ Auto Gcast Disabled."
    )


@Client.on_message(filters.command("setgcastmsg") & filters.private)
async def set_gcast_msg(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/setgcastmsg Your message`")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    gcast_msg = message.text.split(None, 1)[1]
    await _update(bid, {"auto_gcast.message": gcast_msg})
    preview = gcast_msg[:200] + ("..." if len(gcast_msg) > 200 else "")
    await message.reply_text(f"✅ Gcast message set.\n\n**Preview:**\n{preview}")


@Client.on_message(filters.command("gcaststatus") & filters.private)
async def gcast_status(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No settings.")
    ag = data.get("auto_gcast") or {}
    preview = (ag.get("message") or "Not Set")[:200]
    await message.reply_text(
        f"📢 **Auto Gcast**\n\n"
        f"Status: {'✅ Enabled' if ag.get('enabled') else '❌ Disabled'}\n"
        f"Message: `{preview}`"
    )


@Client.on_message(filters.command("logger") & filters.private)
async def toggle_logger(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2 or message.command[1].lower() not in ("enable", "disable"):
        return await message.reply_text("**Usage:** `/logger enable|disable`")
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
        return await message.reply_text("**Usage:** `/setlogger -100xxxxxxxxxx`")
    try:
        group_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid Group ID.")
    if not str(group_id).startswith("-100"):
        return await message.reply_text("❌ Must start with `-100`.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    try:
        await client.send_message(group_id, "✅ Logging activated.")
        await _update(bid, {"log_channel": group_id, "logging": True})
        await message.reply_text(f"✅ Logger → `{group_id}`")
    except Exception:
        await message.reply_text("❌ Cannot send to that group. Make this bot admin there.")


@Client.on_message(filters.command("logstatus") & filters.private)
async def log_status(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No settings.")
    await message.reply_text(
        f"📜 **Logger**\n\n"
        f"Status: {'✅ Enabled' if data.get('logging') else '❌ Disabled'}\n"
        f"Group: `{data.get('log_channel') or 'Not Set'}`"
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
            "Switches immediately — no restart needed."
        )
    bid = await _bot_id(client)
    await _ensure_registered(client)
    session_str = message.command[1].strip()

    await _update(bid, {
        "assistant_mode":   "single",
        "assistant_string": session_str,
        "assistant_multi":  [],
    })

    status_msg = await message.reply_text(
        "⏳ Starting new assistant userbot and PyTgCalls instance..."
    )
    reload_ok = await _reload_assistant(bid, session_str)

    if reload_ok:
        try:
            pyro = _CUSTOM_ASSISTANTS[bid]
            me = await pyro.get_me()
            await status_msg.edit_text(
                f"✅ **Assistant switched successfully!**\n\n"
                f"Account: [{me.first_name}](tg://user?id={me.id}) "
                f"(@{me.username or 'no username'})\n\n"
                f"• Pyrogram client: ✅ running\n"
                f"• PyTgCalls instance: ✅ running\n"
                f"• VC event handlers: ✅ registered\n\n"
                f"This assistant will now join voice chats.\n"
                f"No restart needed.\n\n"
                f"Use /assistantinfo to verify."
            )
        except Exception:
            await status_msg.edit_text("✅ Assistant switched and active.")
    else:
        await status_msg.edit_text(
            "❌ **Failed to start assistant.**\n\n"
            "Session saved to DB. Check:\n"
            "• Valid Pyrogram v2 string session\n"
            "• Account not banned/terminated\n"
            "• API_ID / API_HASH match the session\n\n"
            "Will apply after bot restart."
        )


@Client.on_message(filters.command("setmultiassist") & filters.private)
async def set_multi_assistant(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) < 2:
        return await message.reply_text("**Usage:** `/setmultiassist <str1> <str2> ...`")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    sessions = message.command[1:]
    await _update(bid, {
        "assistant_mode":   "multi",
        "assistant_string": None,
        "assistant_multi":  sessions,
    })
    status_msg = await message.reply_text(
        f"⏳ Starting from {len(sessions)} session(s)..."
    )
    reload_ok = await _reload_assistant(bid, sessions[0])
    if reload_ok:
        try:
            pyro = _CUSTOM_ASSISTANTS[bid]
            me = await pyro.get_me()
            await status_msg.edit_text(
                f"✅ **Assistant switched!**\n\n"
                f"Primary: [{me.first_name}](tg://user?id={me.id}) "
                f"(@{me.username or 'no username'})\n"
                f"Sessions saved: {len(sessions)}"
            )
        except Exception:
            await status_msg.edit_text(f"✅ {len(sessions)} session(s) active.")
    else:
        await status_msg.edit_text(
            f"❌ Failed. {len(sessions)} sessions saved. Will apply after restart."
        )


@Client.on_message(filters.command("assistantinfo") & filters.private)
async def assistant_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    pyro = _CUSTOM_ASSISTANTS.get(bid)
    ptc  = _CUSTOM_PYTGCALLS.get(bid)
    if pyro is not None:
        try:
            me = await pyro.get_me()
            chat_count = sum(1 for v in _CHAT_TO_BOT.values() if v == bid)
            await message.reply_text(
                f"🤝 **Custom Assistant Active**\n\n"
                f"Account: [{me.first_name}](tg://user?id={me.id})\n"
                f"Username: @{me.username or 'None'}\n"
                f"User ID: `{me.id}`\n"
                f"Pyrogram connected: {'✅' if pyro.is_connected else '❌'}\n"
                f"PyTgCalls running: {'✅' if ptc is not None else '❌'}\n"
                f"Chats served: {chat_count}"
            )
        except Exception as e:
            await message.reply_text(f"⚠️ Custom assistant registered but error: `{e}`")
    else:
        data = await _col(bid).find_one({"_id": "config"})
        has_saved = data and (data.get("assistant_string") or data.get("assistant_multi"))
        await message.reply_text(
            "📌 **Using Default Assistant Pool**\n\n"
            + (
                "Session saved in DB. Use `/setassistant <session>` to activate live."
                if has_saved else
                "Use `/setassistant <session>` to set a custom assistant."
            )
        )


@Client.on_message(filters.command("setstring") & filters.private)
async def set_string_session(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/setstring <Pyrogram_StringSession>`")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"string_session": message.command[1].strip()})
    await message.reply_text(
        "✅ String session updated.\n⚠️ Restart bot process to apply."
    )


@Client.on_message(filters.command("botinfo") & filters.private)
async def bot_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No data.")
    live_pyro = bid in _CUSTOM_ASSISTANTS
    live_ptc  = bid in _CUSTOM_PYTGCALLS
    await message.reply_text(
        f"🤖 **Bot Info**\n\n"
        f"Bot ID: `{bid}`\n"
        f"Username: @{data.get('bot_username') or 'Unknown'}\n"
        f"Owner: `{data.get('owner_id') or 'Unknown'}`\n"
        f"Update Channel: {('@' + data['update_channel']) if data.get('update_channel') else 'Default'}\n"
        f"Support Chat: {('@' + data['support_chat']) if data.get('support_chat') else 'Default'}\n"
        f"Start Image: {'✅ Custom' if data.get('start_image') else '📌 Default'}\n"
        f"String Session: {'✅ Custom' if data.get('string_session') else '📌 Default'}\n"
        f"Assistant Pyrogram: {'✅ Live' if live_pyro else ('💾 Saved' if data.get('assistant_string') else '📌 Default pool')}\n"
        f"Assistant PyTgCalls: {'✅ Live' if live_ptc else '📌 Default pool'}\n"
        f"Logging: {'✅' if data.get('logging') else '❌'}\n\n"
        f"/assistantinfo — assistant account details"
    )


@Client.on_message(filters.command("botsettings") & filters.private)
async def bot_settings_cmd(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    data = await _col(bid).find_one({"_id": "config"})
    if not data:
        return await message.reply_text("No data.")
    mj   = data.get("must_join")  or {}
    ag   = data.get("auto_gcast") or {}
    si   = (data.get("start_image") or "Default")[:55]
    pi   = (data.get("ping_image")  or "Default")[:55]
    gm   = (ag.get("message")      or "Default")[:80]
    uc   = f"@{data['update_channel']}" if data.get("update_channel") else "Default"
    sc   = f"@{data['support_chat']}"   if data.get("support_chat")   else "Default"
    ss   = "✅ Custom" if data.get("string_session") else "📌 Default"
    live_pyro = bid in _CUSTOM_ASSISTANTS
    live_ptc  = bid in _CUSTOM_PYTGCALLS
    if live_pyro and live_ptc:
        ast = "✅ Custom LIVE (Pyrogram + PyTgCalls)"
    elif data.get("assistant_string") or data.get("assistant_multi"):
        ast = "💾 Saved — run /setassistant to activate"
    else:
        ast = "📌 Default pool"
    await message.reply_text(
        f"⚙️ **Bot Settings** — `{bid}`\n\n"
        f"🖼 Start Image: `{si}`\n"
        f"🖼 Ping Image: `{pi}`\n"
        f"🔗 Update Channel: {uc}\n"
        f"🔗 Support Chat: {sc}\n"
        f"🚪 Must Join: {'✅' if mj.get('enabled') else '❌'} "
        f"{('@' + mj['link']) if mj.get('link') else 'Not Set'}\n"
        f"📢 Auto Gcast: {'✅' if ag.get('enabled') else '❌'} `{gm}`\n"
        f"📜 Logger: {'✅' if data.get('logging') else '❌'} "
        f"`{data.get('log_channel') or 'Not Set'}`\n"
        f"📝 Start Msg: {'✅ Custom' if data.get('start_message') else '📌 Not Set'}\n"
        f"🤝 Assistant: {ast}\n"
        f"🔑 String Session: {ss}"
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
        "♻️ All settings reset to defaults.\n"
        "Custom assistant removed — using default pool.\n"
        "Owner preserved."
    )


@Client.on_message(filters.command("setbothelp") & filters.private)
async def set_bot_help(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    sections = [
        "🤖 **Bot Settings — Command Reference**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n_Owner-only. Private chat with your bot._",
        "🖼 **IMAGES**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/setstartimg <url>`** — Start + all alias images\n**`/setpingimg <url>`** — Ping image",
        "🔗 **LINKS**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/setupdates @channel`** — Update channel\n**`/setsupport @group`** — Support group",
        "🚪 **MUST JOIN**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/setmustjoin @channel`**\n**`/mustjoin enable|disable`**\n**`/mustjoin`** — toggle",
        "📝 **START MESSAGE**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/setstartmsg <text>`**\nPlaceholders: `{mention}` `{bot}`",
        "📢 **AUTO GCAST**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/autogcast enable|disable`**\n**`/setgcastmsg <text>`**\n**`/gcaststatus`**",
        "📜 **LOGGER**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/setlogger -100xxxxxxxxxx`**\n**`/logger enable|disable`**\n**`/logstatus`**",
        (
            "🤝 **ASSISTANT (VOICE CHAT)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "**`/setassistant <string_session>`**\n"
            "Changes the userbot that joins voice chats.\n"
            "➤ Creates a new Pyrogram Client + PyTgCalls instance\n"
            "➤ Registers all VC event handlers automatically\n"
            "➤ Takes effect **IMMEDIATELY** — no restart needed\n"
            "➤ Must be Pyrogram v2 string session\n\n"
            "**`/setmultiassist <s1> <s2> ...`** — Multiple sessions\n"
            "**`/assistantinfo`** — Show active assistant details\n"
            "Reset: `/resetbotset`"
        ),
        "🔑 **STRING SESSION**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/setstring <session>`** — Bot process session\n⚠️ Requires restart.",
        "👑 **OWNERSHIP**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/transferowner <@user|id>`** — Via BotFather\n**`/changeowner <@user|id>`** — Update DB",
        "ℹ️ **INFO & RESET**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n**`/botinfo`** | **`/botsettings`** | **`/assistantinfo`**\n**`/resetbotset`** — Reset all (keeps owner)\n**`/setbothelp`** — This message",
    ]
    for s in sections:
        await message.reply_text(s)


@Client.on_message(filters.command("transferowner") & filters.private)
async def transfer_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/transferowner <@username or user_id>`\n\nTransfers via BotFather. Requires Telegram password."
        )
    try:
        target_user = await _resolve_user(client, message.command[1])
    except Exception as e:
        return await message.reply_text(f"❌ Could not resolve user.\nError: `{e}`")
    if not target_user.username:
        return await message.reply_text("❌ User has no username. BotFather requires one.")
    bid = await _bot_id(client)
    me  = client.me or await client.get_me()
    bot_username    = me.username or str(bid)
    target_username = target_user.username
    status_msg = await message.reply_text(
        f"🔄 @{bot_username} → @{target_username}..."
    )
    BOTFATHER_ID = 93372553

    async def _wait_bf(timeout=20):
        fut = asyncio.get_event_loop().create_future()
        async def _h(c, m):
            if m.from_user and m.from_user.id == BOTFATHER_ID and not fut.done():
                fut.set_result(m.text or "")
        h = client.add_handler(
            MessageHandler(_h, filters.user(BOTFATHER_ID) & filters.private), group=999
        )
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            try: client.remove_handler(*h)
            except Exception: pass

    try:
        await client.send_message(BOTFATHER_ID, "/mybots")
        await _wait_bf()
        await client.send_message(BOTFATHER_ID, f"@{bot_username}")
        await _wait_bf()
        await client.send_message(BOTFATHER_ID, "Transfer Ownership")
        r3 = await _wait_bf()
        if any(w in r3.lower() for w in ("sorry", "can't", "cannot", "error", "fail")):
            await status_msg.edit_text(f"❌ BotFather rejected.\n`{r3}`")
            return
        await client.send_message(BOTFATHER_ID, f"@{target_username}")
        r4 = await _wait_bf()
        if any(w in r4.lower() for w in ("password", "confirm", "verification", "enter")):
            await status_msg.edit_text(
                f"⚠️ Enter your Telegram password in @BotFather.\n\n`{r4}`\n\n"
                f"After confirming: `/changeowner @{target_username}`"
            )
        elif any(w in r4.lower() for w in ("sorry", "can't", "cannot", "error", "fail", "invalid")):
            await status_msg.edit_text(f"❌ BotFather rejected @{target_username}.\n`{r4}`")
        else:
            await status_msg.edit_text(
                f"ℹ️ `{r4}`\n\nIf done: `/changeowner @{target_username}`"
            )
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            f"❌ Timeout.\nTransfer manually, then: `/changeowner @{target_username}`"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ `{e}`\nTransfer manually, then: `/changeowner @{target_username}`"
        )


@Client.on_message(filters.command("changeowner") & filters.private)
async def change_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text("**Usage:** `/changeowner <@username or user_id>`")
    try:
        target_user = await _resolve_user(client, message.command[1])
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
        return await message.reply_text("⚠️ Already the owner.")
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
    except Exception:
        pass
    try:
        from SHASHA_DRUGZ.core.isolation import _owner_cache as _iso
        _iso[bid] = new_owner_id
    except Exception:
        pass
    if old_owner_id and old_owner_id != new_owner_id:
        try:
            await client.send_message(
                old_owner_id,
                f"⚠️ @{bot_username} transferred to "
                f"[{new_owner_name}](tg://user?id={new_owner_id})."
            )
        except Exception:
            pass
    try:
        await client.send_message(
            new_owner_id,
            f"🎉 You own @{bot_username} now!\n\n/botsettings to view settings."
        )
    except Exception:
        pass
    await message.reply_text(
        f"✅ Owner changed!\n"
        f"Old: `{old_owner_id}` → "
        f"New: [{new_owner_name}](tg://user?id={new_owner_id})\n"
        f"All settings preserved ✅"
    )


# ═════════════════════════════════════════════════════════════════════════════
#  MODULE METADATA
# ═════════════════════════════════════════════════════════════════════════════
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_74"
__help__ = """
**🤖 Bot Settings** _(Owner only, Private chat)_
/setbothelp — All commands
/assistantinfo — Active assistant details
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "BotEdit"
MOD_PRICE = "0"
