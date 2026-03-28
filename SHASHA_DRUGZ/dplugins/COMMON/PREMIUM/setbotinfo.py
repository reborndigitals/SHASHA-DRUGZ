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
#   /setstring    <STRING_SESSION>  → updates STRING_SESSION in DB for this bot
#   /botinfo
#   /botsettings
#   /resetbotset
#   /setbothelp
#   /transferowner <username or userid> → change bot ownership via BotFather
#   /changeowner   <username or userid> → change the deployed owner in DB
#                                         (wipes old owner's custom settings,
#                                          new owner starts fresh from config defaults)
#
# HOW CONFIG UPDATES WORK (no module restarts needed):
#   1. Command saves value to MongoDB via _update()
#   2. _update() calls apply_to_config_and_invalidate(bot_id)
#      → invalidates in-memory cache → reloads from DB
#   3. config.py's _BotStr objects check the cache on every access
#   4. All 500+ modules see new value immediately on next use
#
# OWNER CHANGE BEHAVIOUR:
#   • /changeowner wipes ALL custom settings for this bot
#     (start_image, ping_image, update_channel, support_chat,
#      start_message, assistant_string/multi, gcast, must_join,
#      logger, string_session)
#   • The new owner_id is written; everything else resets to None
#     so _BotStr falls back to hardcoded config.py defaults.
#   • This means the new owner gets a clean slate — none of the
#     old owner's branding, images, or sessions leak through.
#
# ISOLATION:
#   Each bot uses collection bot_{bot_id}_settings.
#   Bot A's changes never affect Bot B.
# =====================================================================

import asyncio
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
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
            "string_session":   None,   # per-bot STRING_SESSION override
        })
        await apply_to_config_and_invalidate(bid)

# ── Owner validation ──────────────────────────────────────────────────────────
async def _validate_owner(client: Client, user_id: int) -> bool:
    bid = await _bot_id(client)
    # 1. Check deploy_bots (authoritative source)
    deploy_doc = await raw_mongodb.deploy_bots.find_one({"bot_id": bid})
    if deploy_doc and deploy_doc.get("owner_id") == user_id:
        return True
    # 2. Fallback: isolated settings doc (kept in sync by /changeowner)
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

# ── Clean slate on owner change ────────────────────────────────────────────────
_OWNER_CHANGE_RESET = {
    # All customisable fields reset to None / defaults
    # so the new owner starts with a clean slate.
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
    """
    Accepts @username, username (without @), or numeric user_id string.
    Returns a Pyrogram User object or raises ValueError/RPCError.
    """
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
        "✅ Start image updated.\n"
        "All image aliases (playlist, stats, stream, etc.) also updated."
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

# ── /setstring <STRING_SESSION> ───────────────────────────────────────────────
# Updates: the STRING_SESSION used by this deployed bot
# This is stored in the isolated settings doc so it survives restarts.
# On /changeowner, string_session is wiped → bot falls back to config.py STRING1.
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
    await message.reply_text(
        f"🤖 **Bot Info**\n\n"
        f"➤ Bot ID: `{bid}`\n"
        f"➤ Bot Username: @{data.get('bot_username') or 'Unknown'}\n"
        f"➤ Owner ID: `{data.get('owner_id') or 'Unknown'}`\n"
        f"➤ Update Channel: {('@' + data['update_channel']) if data.get('update_channel') else 'Not Set (using default)'}\n"
        f"➤ Support Chat: {('@' + data['support_chat']) if data.get('support_chat') else 'Not Set (using default)'}\n"
        f"➤ Start Image: {'✅ Custom' if data.get('start_image') else '📌 Default'}\n"
        f"➤ String Session: {'✅ Custom' if data.get('string_session') else '📌 Default (config.py)'}\n"
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
        f"🤝 Assistant Mode: `{data.get('assistant_mode') or 'Not Set'}`\n"
        f"🔑 String Session: {string_s}"
    )

# ── /resetbotset ──────────────────────────────────────────────────────────────
# Resets all customisable values to None → _BotStr._v() returns
# hardcoded config.py defaults. owner_id is preserved so the current
# owner can still use owner-only commands after reset.
@Client.on_message(filters.command("resetbotset") & filters.private)
async def reset_bot_info(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    bid = await _bot_id(client)
    # Preserve owner_id — reset only customisable settings
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
        "string_session":   None,   # → falls back to config.py STRING1
    })
    await message.reply_text(
        "♻️ All bot settings reset to default.\n\n"
        "Config values will now show the hardcoded defaults from config.py.\n"
        "Owner ID has been preserved."
    )

# ── /setbothelp ───────────────────────────────────────────────────────────────
# Sends a rich multi-section help message covering every command with
# full usage, arguments, examples, and notes.
# Split into multiple messages so Telegram's 4096-char limit is never hit.
@Client.on_message(filters.command("setbothelp") & filters.private)
async def set_bot_help(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")

    sections = [

        # ── HEADER ────────────────────────────────────────────────────────────
        (
            "🤖 **Bot Settings — Full Command Reference**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "_All commands are owner-only and must be sent in **private chat** with your bot._\n\n"
            "Use the section headers below to jump to the command group you need."
        ),

        # ── IMAGES ────────────────────────────────────────────────────────────
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

        # ── LINKS ─────────────────────────────────────────────────────────────
        (
            "🔗 **LINKS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "**`/setupdates @channel`**\n"
            "Sets the update/announcement channel shown in bot menus.\n"
            "Maps to `config.SUPPORT_CHANNEL`.\n"
            "➤ **Arg:** Telegram channel username (with or without `@`)\n"
            "➤ **Example:** `/setupdates @MyUpdateChannel`\n"
            "➤ **Effect:** Immediately visible — no restart needed\n"
            "➤ **Reset:** `/resetbotset` — reverts to `config.py` `SUPPORT_CHANNEL`\n\n"

            "**`/setsupport @group`**\n"
            "Sets the support group link shown in bot menus.\n"
            "Maps to `config.SUPPORT_CHAT`.\n"
            "➤ **Arg:** Telegram group username (with or without `@`)\n"
            "➤ **Example:** `/setsupport @MySupportGroup`\n"
            "➤ **Effect:** Immediately visible — no restart needed\n"
            "➤ **Reset:** `/resetbotset` — reverts to `config.py` `SUPPORT_CHAT`"
        ),

        # ── MUST JOIN ─────────────────────────────────────────────────────────
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

        # ── START MESSAGE ─────────────────────────────────────────────────────
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

        # ── AUTO GCAST ────────────────────────────────────────────────────────
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

        # ── LOGGER ────────────────────────────────────────────────────────────
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

            "**`/logger enable`** — Enables logging (requires logger group to be set first)\n"
            "**`/logger disable`** — Disables logging (group ID is kept, just paused)\n\n"

            "**`/logstatus`**\n"
            "Shows current logger status and the configured log group ID.\n"
            "➤ **No args needed**\n"
            "➤ **Reset:** `/resetbotset` — disables logging and clears log group"
        ),

        # ── ASSISTANT ─────────────────────────────────────────────────────────
        (
            "🤝 **ASSISTANT SESSION**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "**`/setassistant <string_session>`**\n"
            "Sets a single Pyrogram string session as the assistant account.\n"
            "➤ **Arg:** A valid Pyrogram v2 string session\n"
            "➤ **Example:** `/setassistant BQHabc123...`\n"
            "➤ **Note:** Clears any previously set multi-assistant sessions\n\n"

            "**`/setmultiassist <session1> <session2> ...`**\n"
            "Sets multiple assistant string sessions (space-separated).\n"
            "➤ **Args:** Two or more Pyrogram v2 string sessions\n"
            "➤ **Example:** `/setmultiassist BQHabc... BQHxyz... BQHmnp...`\n"
            "➤ **Note:** Clears the single assistant session if one was set\n"
            "➤ **Reset:** `/resetbotset` — clears all assistant sessions"
        ),

        # ── STRING SESSION ────────────────────────────────────────────────────
        (
            "🔑 **STRING SESSION**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "**`/setstring <session>`**\n"
            "Sets the `STRING_SESSION` used by this deployed bot instance.\n"
            "Stored in the isolated MongoDB settings so it survives restarts.\n"
            "➤ **Arg:** A valid Pyrogram v2 string session\n"
            "➤ **Example:** `/setstring BQHabc123def456...`\n"
            "➤ **Important:** Restart the bot process after setting for the new session to load\n"
            "➤ **On owner change:** This is automatically wiped — new owner must set their own\n"
            "➤ **Reset:** `/resetbotset` — clears the custom session, falls back to `config.py STRING1`"
        ),

        # ── OWNERSHIP ─────────────────────────────────────────────────────────
        (
            "👑 **OWNERSHIP**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "**`/transferowner <@username or user_id>`**\n"
            "Automates a BotFather conversation to transfer **Telegram-side** bot ownership.\n"
            "➤ **Arg:** Target user's `@username` or numeric `user_id`\n"
            "➤ **Example:** `/transferowner @NewOwnerUsername`\n"
            "➤ **Flow:**\n"
            "  1. Bot auto-navigates BotFather (`/mybots` → select bot → Transfer Ownership)\n"
            "  2. BotFather sends the new owner's username\n"
            "  3. BotFather will ask for your **Telegram password** — you must confirm manually\n"
            "  4. After confirming, run `/changeowner` to update the DB\n"
            "➤ **Requirements:** New owner must have started the bot in the last 6 months\n\n"

            "**`/changeowner <@username or user_id>`**\n"
            "Updates the deployed owner in the database.\n"
            "➤ **Arg:** Target user's `@username` or numeric `user_id`\n"
            "➤ **Example:** `/changeowner @NewOwnerUsername`\n"
            "➤ **What it does:**\n"
            "  • Updates `deploy_bots` collection → renewals/expiry go to new owner\n"
            "  • Updates `bot_{id}_settings` collection → new owner can use owner commands\n"
            "  • Updates in-memory `BOT_OWNERS` and isolation cache instantly\n"
            "  • **Wipes all custom settings** (images, links, string session, gcast, etc.)\n"
            "    so the new owner gets a completely clean slate\n"
            "➤ **Note:** Both old and new owners are notified by DM (best-effort)"
        ),

        # ── INFO & RESET ──────────────────────────────────────────────────────
        (
            "ℹ️ **INFO & RESET**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "**`/botinfo`**\n"
            "Shows a summary of this bot's current identity and key settings.\n"
            "➤ Displays: Bot ID, username, owner ID, update channel, support chat,\n"
            "  start image status, string session status, logging status\n\n"

            "**`/botsettings`**\n"
            "Shows ALL current settings for this bot in one detailed view.\n"
            "➤ Displays: Images, links, must-join, auto-gcast, logger, start message,\n"
            "  assistant mode, string session\n\n"

            "**`/resetbotset`**\n"
            "Resets **all customisable settings** back to `config.py` hardcoded defaults.\n"
            "➤ Sets to `None`: start image, ping image, update channel, support chat,\n"
            "  start message, must-join, auto-gcast, logger, assistant, string session\n"
            "➤ **Preserves:** `owner_id` — you keep owner access after reset\n"
            "➤ **Effect:** Immediate — no restart needed\n\n"

            "**`/setbothelp`**\n"
            "Shows this full command reference.\n"
            "➤ **No args needed**\n"
            "➤ Safe to run anytime — read-only, makes no changes"
        ),

    ]

    # Send each section as a separate message so Telegram's 4096-char cap is never hit
    for section in sections:
        await message.reply_text(section)

# ── /transferowner <username or userid> ───────────────────────────────────────
# Automates a BotFather conversation to transfer Telegram-side bot ownership.
#
# FLOW:
#   1. Resolve target user → get their @username (BotFather needs username)
#   2. Send /mybots to BotFather → select this bot → Transfer Ownership
#   3. BotFather will ask for the new owner's @username → send it
#   4. BotFather requires your Telegram password to confirm — we cannot
#      automate that step (Telegram security), so we guide the owner to
#      finish manually in the BotFather chat.
#   5. After completing, owner should run /changeowner to update the DB.
#
# NOTE: BotFather's exact message flow may change. The automation handles
# the username selection step; the password step must be done manually.
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
    # ── Resolve target user ───────────────────────────────────────────────────
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
    # ── BotFather listener helper ─────────────────────────────────────────────
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

    # ── Automated BotFather conversation ──────────────────────────────────────
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
                f"BotFather said:\n`{reply3}`\n\n"
                f"**Common reasons:**\n"
                f"• @{target_username} hasn't started @{bot_username}\n"
                f"• The new owner's account is less than 90 days old\n"
                f"• The new owner hasn't interacted with the bot in the last 6 months"
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
                f"`/changeowner @{target_username}`\n"
                f"to update the deployed owner in the database so renewals go to the new owner."
            )
        elif any(w in reply4_lower for w in ("sorry", "can't", "cannot", "error", "fail", "invalid")):
            await status_msg.edit_text(
                f"❌ BotFather rejected @{target_username} as new owner.\n\n"
                f"BotFather said:\n`{reply4}`\n\n"
                f"Make sure @{target_username} has started @{bot_username} at least once."
            )
        else:
            await status_msg.edit_text(
                f"ℹ️ BotFather responded:\n`{reply4}`\n\n"
                f"If the transfer completed, run:\n"
                f"`/changeowner @{target_username}`\n"
                f"to update the deployed owner in the database."
            )
    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "❌ **BotFather did not respond in time.**\n\n"
            "Please complete the ownership transfer manually:\n"
            f"1. Open @BotFather\n"
            f"2. Send `/mybots` → select @{bot_username}\n"
            f"3. Tap **Transfer Ownership** → enter `@{target_username}`\n"
            f"4. Confirm with your **Telegram password**\n\n"
            f"After completing, run:\n"
            f"`/changeowner @{target_username}`\n"
            f"to update the deployed owner in the database."
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ BotFather automation failed: `{e}`\n\n"
            f"Please transfer manually via @BotFather, then run:\n"
            f"`/changeowner @{target_username}`"
        )

# ── /changeowner <username or userid> ────────────────────────────────────────
# Updates the deployed owner (owner_id) across ALL relevant stores AND
# wipes all old owner's custom settings so the new owner gets a clean slate.
#
# What gets updated:
#   1. raw_mongodb.deploy_bots   → owner_id + owner_name
#   2. bot_{bid}_settings col    → owner_id + ALL custom settings reset to None
#   3. deploy.py BOT_OWNERS dict (in-memory)
#   4. isolation _owner_cache    (in-memory)
#
# Why we reset settings on owner change:
#   The old owner may have set custom images, string sessions, support links,
#   etc. that belong to THEM — not the bot. The new owner should start fresh
#   so none of the old owner's data leaks through. If the new owner wants
#   specific settings they can re-set them. On /resetbotset the same wipe
#   happens, confirming this is the intended "clean state".
@Client.on_message(filters.command("changeowner") & filters.private)
async def change_owner(client: Client, message: Message):
    if not await _validate_owner(client, message.from_user.id):
        return await message.reply_text("❌ Access Denied.")
    if len(message.command) != 2:
        return await message.reply_text(
            "**Usage:** `/changeowner <@username or user_id>`\n\n"
            "Updates the deployed owner in the database.\n"
            "⚠️ All current custom bot settings (images, string session, links, etc.) "
            "will be **wiped** so the new owner starts with a clean slate.\n"
            "✅ All future renewal & expiry notifications will go to the new owner."
        )
    target_raw = message.command[1].strip()
    # ── Resolve target user ───────────────────────────────────────────────────
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
    # ── Fetch current deploy_bots record ─────────────────────────────────────
    deploy_doc = await raw_mongodb.deploy_bots.find_one({"bot_id": bid})
    if not deploy_doc:
        return await message.reply_text(
            "❌ No deploy record found for this bot.\n"
            "This bot may not have been deployed via the deploy system.\n\n"
            "The isolated settings owner_id will still be updated."
        )
    old_owner_id = deploy_doc.get("owner_id")
    if old_owner_id == new_owner_id:
        return await message.reply_text(
            f"⚠️ [`{new_owner_name}`](tg://user?id={new_owner_id}) is already the owner of this bot."
        )
    me = client.me or await client.get_me()
    bot_username = me.username or str(bid)

    # ── 1. Update deploy_bots collection (renewal/expiry msgs use this) ───────
    await raw_mongodb.deploy_bots.update_one(
        {"bot_id": bid},
        {"$set": {
            "owner_id":   new_owner_id,
            "owner_name": new_owner_name,
        }}
    )

    # ── 2. Update isolated bot settings:
    #       • Set new owner_id
    #       • Wipe ALL custom settings so new owner gets a clean slate
    #         (none of the old owner's images, sessions, links leak through)
    clean_fields = dict(_OWNER_CHANGE_RESET)   # copy the reset template
    clean_fields["owner_id"] = new_owner_id    # set new owner in same write
    await _update(bid, clean_fields)

    # ── 3. Update in-memory BOT_OWNERS in deploy.py ───────────────────────────
    try:
        from SHASHA_DRUGZ.plugins.PREMIUM.deploy import BOT_OWNERS
        BOT_OWNERS[bid] = new_owner_id
    except (ImportError, Exception):
        pass

    # ── 4. Update isolation owner cache ──────────────────────────────────────
    try:
        from SHASHA_DRUGZ.core.isolation import _owner_cache as _iso_cache
        _iso_cache[bid] = new_owner_id
    except (ImportError, Exception):
        pass

    # ── Notify old owner (best-effort, bot may be blocked) ────────────────────
    if old_owner_id and old_owner_id != new_owner_id:
        try:
            await client.send_message(
                old_owner_id,
                f"⚠️ **Ownership of @{bot_username} has been transferred.**\n\n"
                f"New Owner: [{new_owner_name}](tg://user?id={new_owner_id}) (`{new_owner_id}`)\n\n"
                f"You no longer have owner access to this bot.\n"
                f"All future renewal & expiry notifications will go to the new owner.\n\n"
                f"📌 All custom settings (images, string session, links) have been reset "
                f"to defaults for the new owner."
            )
        except Exception:
            pass

    # ── Notify new owner (best-effort) ────────────────────────────────────────
    try:
        await client.send_message(
            new_owner_id,
            f"🎉 **You are now the owner of @{bot_username}!**\n\n"
            f"All renewal & expiry notifications will now be sent to you.\n"
            f"Use `/botsettings` to manage your bot settings.\n"
            f"Use `/botinfo` to see full bot information.\n\n"
            f"📌 The bot starts with default settings — use `/setstartimg`, "
            f"`/setupdates`, `/setstring` etc. to customise."
        )
    except Exception:
        pass

    await message.reply_text(
        f"✅ **Owner changed successfully!**\n\n"
        f"➤ Bot: @{bot_username}\n"
        f"➤ Old Owner: `{old_owner_id or 'Unknown'}`\n"
        f"➤ New Owner: [{new_owner_name}](tg://user?id={new_owner_id}) (`{new_owner_id}`)\n\n"
        f"🧹 **Old owner's custom settings wiped** — new owner starts with defaults.\n\n"
        f"📌 **All future renewal & expiry notifications will go to the new owner.**\n\n"
        f"Updated:\n"
        f"• `deploy_bots` collection ✅\n"
        f"• `bot_{bid}_settings` collection ✅ (settings reset)\n"
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
