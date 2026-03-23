# SHASHA_DRUGZ/dplugins/COMMON/PREMIUM/setbotinfo.py
# =====================================================================
# FULLY ISOLATED PER-BOT SETTINGS MODULE
#
# COMMANDS:
#   /setstartimg  <url>         → config.START_IMG_URL + all image aliases
#   /setpingimg   <url>         → config.PING_IMG_URL
#   /setupdates   @channel      → config.SUPPORT_CHANNEL
#   /setsupport   @group        → config.SUPPORT_CHAT
#   /setmustjoin  @channel      → enables must-join for this bot
#   /mustjoin     enable|disable
#   /autogcast    enable|disable
#   /setgcastmsg  <message>
#   /gcaststatus
#   /logger       enable|disable
#   /setlogger    -100xxxxxxxxxx → config.LOG_GROUP_ID / LOGGER_ID
#   /logstatus
#   /setstartmsg  <text>
#   /setassistant <session>
#   /setmultiassist <s1> <s2> ...
#   /botinfo
#   /botsettings
#   /resetbotset
#   /setbothelp
#
# HOW CONFIG UPDATES WORK (no module restarts needed):
#   1. Command saves value to MongoDB via _update()
#   2. _update() calls apply_to_config_and_invalidate(bot_id)
#      → invalidates in-memory cache → reloads from DB
#   3. config.py's _BotStr objects check the cache on every access
#   4. All 500+ modules see new value immediately on next use
#
# ISOLATION:
#   Each bot uses collection bot_{bot_id}_settings.
#   Bot A's changes never affect Bot B.
# =====================================================================
from pyrogram import Client, filters
from pyrogram.types import Message
from SHASHA_DRUGZ.core.mongo import raw_mongodb
from SHASHA_DRUGZ.utils.bot_settings import apply_to_config_and_invalidate

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
        })
        await apply_to_config_and_invalidate(bid)


# ── Owner validation ──────────────────────────────────────────────────────────
async def _validate_owner(client: Client, user_id: int) -> bool:
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
    """
    Write fields to this bot's isolated MongoDB collection,
    then immediately refresh the in-memory cache.
    All _BotStr / _BotInt objects in config.py will return the
    new values on the very next access — no module restart needed.
    """
    await _col(bot_id).update_one(
        {"_id": "config"},
        {"$set": fields},
        upsert=True,
    )
    await apply_to_config_and_invalidate(bot_id)


# ═════════════════════════════════════════════════════════════════════════════
#  COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

# ── /setstartimg <url> ────────────────────────────────────────────────────────
# Updates: config.START_IMG_URL + ALL image aliases (PLAYLIST_IMG_URL,
# STATS_IMG_URL, STREAM_IMG_URL, YOUTUBE_IMG_URL, etc.) — all point to
# the same "start_image" db key so one command updates everything.
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
        f"✅ Start image updated.\n"
        f"All image aliases (playlist, stats, stream, etc.) also updated."
    )


# ── /setpingimg <url> ─────────────────────────────────────────────────────────
# Updates: config.PING_IMG_URL
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
# Updates: config.SUPPORT_CHANNEL
@Client.on_message(filters.command("setupdates") & filters.private)
async def set_update_channel(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setupdates @channelusername`\n\n"
            "Updates config.SUPPORT_CHANNEL for this bot."
        )
    channel = message.command[1].strip().lstrip("@")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"update_channel": channel})
    await message.reply_text(f"✅ Update channel set to `@{channel}`")


# ── /setsupport @group ────────────────────────────────────────────────────────
# Updates: config.SUPPORT_CHAT
@Client.on_message(filters.command("setsupport") & filters.private)
async def set_support(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/setsupport @groupusername`\n\n"
            "Updates config.SUPPORT_CHAT for this bot."
        )
    support = message.command[1].strip().lstrip("@")
    bid = await _bot_id(client)
    await _ensure_registered(client)
    await _update(bid, {"support_chat": support})
    await message.reply_text(f"✅ Support chat set to `@{support}`")


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
# Updates: config.MUST_JOIN (via _MustJoinStr dynamic resolution)
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
    # Toggle if no argument
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
# Updates: config.AUTO_GCAST
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
# Updates: config.AUTO_GCAST_MSG
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
# Updates: config.LOG_GROUP_ID and config.LOGGER_ID via _BotInt
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
    await _update(bid, {
        "assistant_mode":   "single",
        "assistant_string": message.command[1],
        "assistant_multi":  [],
    })
    await message.reply_text("✅ Assistant string session updated.")


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
    await message.reply_text(f"✅ {len(sessions)} assistant session(s) added.")


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
    await message.reply_text(
        f"🤖 **Bot Info**\n\n"
        f"➤ Bot ID: `{bid}`\n"
        f"➤ Bot Username: @{data.get('bot_username') or 'Unknown'}\n"
        f"➤ Update Channel: {('@' + data['update_channel']) if data.get('update_channel') else 'Not Set (using default)'}\n"
        f"➤ Support Chat: {('@' + data['support_chat']) if data.get('support_chat') else 'Not Set (using default)'}\n"
        f"➤ Start Image: {'✅ Custom' if data.get('start_image') else '📌 Default'}\n"
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
        f"🤝 Assistant Mode: `{data.get('assistant_mode') or 'Not Set'}`"
    )


# ── /resetbotset ──────────────────────────────────────────────────────────────
# Resets all values to None → _BotStr._v() returns hardcoded config.py defaults
@Client.on_message(filters.command("resetbotset") & filters.private)
async def reset_bot_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    await _update(bid, {
        "start_message":    None,
        "start_image":      None,   # → START_IMG_URL reverts to config.py default
        "ping_image":       None,   # → PING_IMG_URL reverts to config.py default
        "must_join":        {"link": None, "enabled": False},
        "auto_gcast":       {"enabled": False, "message": None},
        "update_channel":   None,   # → SUPPORT_CHANNEL reverts to config.py default
        "support_chat":     None,   # → SUPPORT_CHAT reverts to config.py default
        "logging":          False,
        "log_channel":      None,   # → LOG_GROUP_ID reverts to config.py default
        "assistant_mode":   None,
        "assistant_string": None,
        "assistant_multi":  [],
    })
    await message.reply_text(
        "♻️ All bot settings reset to default.\n\n"
        "Config values will now show the hardcoded defaults from config.py."
    )


# ── /setbothelp ───────────────────────────────────────────────────────────────
@Client.on_message(filters.command("setbothelp") & filters.private)
async def set_bot_help(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    await message.reply_text(__help__)


# ═════════════════════════════════════════════════════════════════════════════
#  MODULE METADATA
# ═════════════════════════════════════════════════════════════════════════════
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_74"
__help__ = """
**🤖 Bot Settings Commands** _(Owner only, Private chat)_

**🖼 Images**
🔻 `/setstartimg <url>` ➠ Set start image (also updates playlist/stats/stream/youtube/spotify images)
🔻 `/setpingimg <url>` ➠ Set ping image

**🔗 Links**
🔻 `/setupdates @channel` ➠ Set update channel (config.SUPPORT\\_CHANNEL)
🔻 `/setsupport @group` ➠ Set support chat (config.SUPPORT\\_CHAT)

**🚪 Must Join**
🔻 `/setmustjoin @channel` ➠ Set must-join channel and enable it
🔻 `/mustjoin enable|disable` ➠ Toggle must-join on/off

**📢 Auto Gcast**
🔻 `/autogcast enable|disable` ➠ Toggle auto broadcast on/off
🔻 `/setgcastmsg <message>` ➠ Set auto broadcast message
🔻 `/gcaststatus` ➠ Show gcast status and message preview

**📜 Logger**
🔻 `/logger enable|disable` ➠ Toggle logging on/off
🔻 `/setlogger -100xxxxxx` ➠ Set log group (config.LOG\\_GROUP\\_ID)
🔻 `/logstatus` ➠ Show logger status

**📝 Messages**
🔻 `/setstartmsg <text>` ➠ Set custom start message _(use `{mention}` `{bot}`)_

**🤝 Assistant**
🔻 `/setassistant <session>` ➠ Set single assistant string session
🔻 `/setmultiassist <s1> <s2>` ➠ Set multiple assistant sessions

**ℹ️ Info & Reset**
🔻 `/botinfo` ➠ Show bot info
🔻 `/botsettings` ➠ Show all current settings
🔻 `/resetbotset` ➠ Reset all settings to default config values
🔻 `/setbothelp` ➠ Show this help message
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "BotEdit"
MOD_PRICE = "0"
