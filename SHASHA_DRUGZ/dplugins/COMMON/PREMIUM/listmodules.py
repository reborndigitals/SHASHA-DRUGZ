# SHASHA_DRUGZ/dplugins/PREMIUM/listmodules.py
import os
import re
from pyrogram import Client, filters
from pyrogram.types import Message
from config import ADMINS_ID
from SHASHA_DRUGZ.mongo.deploydb import get_deployed_bot_by_id

PLUGINS_PATH = "SHASHA_DRUGZ/dplugins"

# ─── Scanners ─────────────────────────────────────────────────────────────────

def scan_modules_from_path(path: str):
    """
    Return all modules that define MOD_NAME from a specific subdirectory.
    price = 0 if MOD_PRICE is missing or "0".
    """
    modules = []
    seen    = set()
    if not os.path.isdir(path):
        return modules
    for root, _, files in os.walk(path):
        for file in files:
            if not file.endswith(".py") or file.startswith("_"):
                continue
            fpath = os.path.join(root, file)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                name_m = re.search(r'MOD_NAME\s*=\s*[\'"](.+?)[\'"]', content)
                if not name_m:
                    continue
                name = name_m.group(1)
                if name in seen:
                    continue
                seen.add(name)
                price_m = re.search(r'MOD_PRICE\s*=\s*[\'"]?(\d+)[\'"]?', content)
                price   = int(price_m.group(1)) if price_m else 0
                modules.append({"name": name, "price": price})
            except Exception:
                continue
    return sorted(modules, key=lambda x: x["price"])


def scan_all_modules():
    """
    Return ALL modules that define MOD_NAME.
    price = 0 if MOD_PRICE is missing or "0".
    """
    return scan_modules_from_path(PLUGINS_PATH)


# ─── Formatters ───────────────────────────────────────────────────────────────

def fmt_with_price(modules):
    """Name + price column."""
    if not modules:
        return "_No modules found._"
    lines = []
    for m in modules:
        price = "FREE" if m["price"] == 0 else f"₹{m['price']}/ᴍᴏɴᴛʜ"
        lines.append(f"• **{m['name']}** — `{price}`")
    return "\n".join(lines)


def fmt_without_price(modules):
    """Name only, no price."""
    if not modules:
        return "_No modules found._"
    return "\n".join(f"• **{m['name']}**" for m in modules)


def _split_text(text: str, limit: int = 4000):
    """Split long text at newlines so each chunk is under limit."""
    chunks, current = [], ""
    for line in text.split("\n"):
        candidate = (current + "\n" + line) if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def _send(message: Message, text: str):
    """Send, splitting if > 4000 chars."""
    if len(text) <= 4000:
        await message.reply_text(text)
    else:
        for chunk in _split_text(text):
            await message.reply_text(chunk)


async def _resolve_bot(client: Client):
    """Return the deploy record for THIS bot client, or None."""
    me = client.me or await client.get_me()
    return await get_deployed_bot_by_id(me.id)


# ─────────────────────────────────────────────────────────────────────────────
# /modules  /listmodules
# → List ALL available modules WITH price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command(["modules", "listmodules"]))
async def list_all_modules_with_price(client: Client, message: Message):
    modules = scan_all_modules()
    free    = sum(1 for m in modules if m["price"] == 0)
    paid    = len(modules) - free
    text = (
        "📦 **ᴀᴠᴀɪʟᴀʙʟᴇ ᴍᴏᴅᴜʟᴇs & ᴘʀɪᴄᴇʟɪsᴛ**\n\n"
        f"{fmt_with_price(modules)}\n\n"
        f"📊 ᴛᴏᴛᴀʟ: `{len(modules)}` | ғʀᴇᴇ: `{free}` | ᴘᴀɪᴅ: `{paid}`\n"
        "🧾 ᴘʀɪᴄᴇs ᴀʀᴇ ᴍᴏɴᴛʜʟʏ."
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /plugins
# → List ALL available modules WITHOUT price (names only)
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("plugins"))
async def list_all_plugins_no_price(client: Client, message: Message):
    modules = scan_all_modules()
    text = (
        "🔌 **ᴀʟʟ ᴀᴠᴀɪʟᴀʙʟᴇ ᴘʟᴜɢɪɴs / ᴍᴏᴅᴜʟᴇs**\n\n"
        f"{fmt_without_price(modules)}\n\n"
        f"📊 ᴛᴏᴛᴀʟ ᴍᴏᴅᴜʟᴇs: `{len(modules)}`"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /mymodules
# → Show ONLY this deployed bot's enabled modules WITH price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("mymodules"))
async def list_my_modules_with_price(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in ADMINS_ID:
        modules = scan_all_modules()
        return await _send(message,
            "📦 **ᴀʟʟ ᴍᴏᴅᴜʟᴇs — ᴀᴅᴍɪɴ ᴠɪᴇᴡ (ᴡɪᴛʜ ᴘʀɪᴄᴇ)**\n\n"
            f"{fmt_with_price(modules)}"
        )
    bot = await _resolve_bot(client)
    if not bot:
        return await message.reply_text(
            "<blockquote>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋs ᴏɴʟʏ ɪɴsɪᴅᴇ ᴀ ᴅᴇᴘʟᴏʏᴇᴅ ʙᴏᴛ.</blockquote>"
        )
    if bot["owner_id"] != user_id:
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴛʜᴇ ᴏᴡɴᴇʀ ᴏғ ᴛʜɪs ʙᴏᴛ.</blockquote>"
        )
    enabled_names = set(bot.get("modules", []))
    if not enabled_names:
        return await message.reply_text(
            "<blockquote>⚠️ ɴᴏ ᴍᴏᴅᴜʟᴇs ᴇɴᴀʙʟᴇᴅ ᴏɴ ᴛʜɪs ʙᴏᴛ ʏᴇᴛ.</blockquote>"
        )
    all_mods      = scan_all_modules()
    owned         = [m for m in all_mods if m["name"] in enabled_names]
    monthly_cost  = sum(m["price"] for m in owned)
    expiry        = bot.get("expiry_date")
    expiry_str    = expiry.strftime("%d-%m-%Y %I:%M %p IST") if expiry else "N/A"
    text = (
        f"<blockquote>📦 **ʏᴏᴜʀ ᴇɴᴀʙʟᴇᴅ ᴍᴏᴅᴜʟᴇs — ᴡɪᴛʜ ᴘʀɪᴄᴇ**\n"
        f"🤖 ʙᴏᴛ: @{bot.get('username', 'unknown')}\n"
        f"📊 ᴛᴏᴛᴀʟ: `{len(owned)}` ᴍᴏᴅᴜʟᴇs</blockquote>\n\n"
        f"{fmt_with_price(owned)}\n\n"
        f"<blockquote>💰 ᴍᴏɴᴛʜʟʏ ᴄᴏsᴛ: ₹{monthly_cost}\n"
        f"⏰ ᴇxᴘɪʀᴇs: {expiry_str}</blockquote>"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /myplugins
# → Show ONLY this deployed bot's enabled modules WITHOUT price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("myplugins"))
async def list_my_plugins_no_price(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in ADMINS_ID:
        modules = scan_all_modules()
        return await _send(message,
            "🔌 **ᴀʟʟ ᴘʟᴜɢɪɴs — ᴀᴅᴍɪɴ ᴠɪᴇᴡ (ɴᴏ ᴘʀɪᴄᴇ)**\n\n"
            f"{fmt_without_price(modules)}\n\n"
            f"📊 ᴛᴏᴛᴀʟ: `{len(modules)}`"
        )
    bot = await _resolve_bot(client)
    if not bot:
        return await message.reply_text(
            "<blockquote>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋs ᴏɴʟʏ ɪɴsɪᴅᴇ ᴀ ᴅᴇᴘʟᴏʏᴇᴅ ʙᴏᴛ.</blockquote>"
        )
    if bot["owner_id"] != user_id:
        return await message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴛʜᴇ ᴏᴡɴᴇʀ ᴏғ ᴛʜɪs ʙᴏᴛ.</blockquote>"
        )
    enabled_names = set(bot.get("modules", []))
    if not enabled_names:
        return await message.reply_text(
            "<blockquote>⚠️ ɴᴏ ᴍᴏᴅᴜʟᴇs ᴇɴᴀʙʟᴇᴅ ᴏɴ ᴛʜɪs ʙᴏᴛ ʏᴇᴛ.</blockquote>"
        )
    all_mods   = scan_all_modules()
    owned      = [m for m in all_mods if m["name"] in enabled_names]
    expiry     = bot.get("expiry_date")
    expiry_str = expiry.strftime("%d-%m-%Y %I:%M %p IST") if expiry else "N/A"
    text = (
        f"<blockquote>🔌 **ᴀᴄᴛɪᴠᴇ ᴘʟᴜɢɪɴs — ɴᴏ ᴘʀɪᴄᴇ**\n"
        f"🤖 ʙᴏᴛ: @{bot.get('username', 'unknown')}\n"
        f"📊 ᴛᴏᴛᴀʟ: `{len(owned)}` ᴍᴏᴅᴜʟᴇs\n"
        f"⏰ ᴇxᴘɪʀᴇs: {expiry_str}</blockquote>\n\n"
        f"{fmt_without_price(owned)}"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /probots
# → List PRO-BOTS modules WITHOUT price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("probots"))
async def list_probots_no_price(client: Client, message: Message):
    path    = os.path.join(PLUGINS_PATH, "PRO-BOTS")
    modules = scan_modules_from_path(path)
    text = (
        "<blockquoat>🤖 **ᴘʀᴏ-ʙᴏᴛs ᴍᴏᴅᴜʟᴇs**</blockquoat>"
        f"<blockquoat>{fmt_without_price(modules)}</blockquoat>"
        f"<blockquoat>📊 ᴛᴏᴛᴀʟ ᴍᴏᴅᴜʟᴇs: `{len(modules)}`</blockquoat>"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /probotsprice
# → List PRO-BOTS modules WITH price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("probotsprice"))
async def list_probots_with_price(client: Client, message: Message):
    path    = os.path.join(PLUGINS_PATH, "PRO-BOTS")
    modules = scan_modules_from_path(path)
    free    = sum(1 for m in modules if m["price"] == 0)
    paid    = len(modules) - free
    text = (
        "<blockquoat>🤖 **ᴘʀᴏ-ʙᴏᴛs ᴍᴏᴅᴜʟᴇs & ᴘʀɪᴄᴇʟɪsᴛ**</blockquoat>"
        f"<blockquoat>{fmt_with_price(modules)}</blockquoat>"
        f"<blockquoat>📊 ᴛᴏᴛᴀʟ: `{len(modules)}` | ғʀᴇᴇ: `{free}` | ᴘᴀɪᴅ: `{paid}`</blockquoat>"
        "<blockquoat>🧾 ᴘʀɪᴄᴇs ᴀʀᴇ ᴍᴏɴᴛʜʟʏ.</blockquoat>"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /manage
# → List MANAGE modules WITHOUT price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("manage"))
async def list_manage_no_price(client: Client, message: Message):
    path    = os.path.join(PLUGINS_PATH, "MANAGE")
    modules = scan_modules_from_path(path)
    text = (
        "<blockquoat>⚙️ **ᴍᴀɴᴀɢᴇ ᴍᴏᴅᴜʟᴇs**</blockquoat>"
        f"<blockquoat>{fmt_without_price(modules)}</blockquoat>"
        f"<blockquoat>📊 ᴛᴏᴛᴀʟ ᴍᴏᴅᴜʟᴇs: `{len(modules)}`</blockquoat>"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /manageprice
# → List MANAGE modules WITH price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("manageprice"))
async def list_manage_with_price(client: Client, message: Message):
    path    = os.path.join(PLUGINS_PATH, "MANAGE")
    modules = scan_modules_from_path(path)
    free    = sum(1 for m in modules if m["price"] == 0)
    paid    = len(modules) - free
    text = (
        "<blockquoat>⚙️ **ᴍᴀɴᴀɢᴇ ᴍᴏᴅᴜʟᴇs & ᴘʀɪᴄᴇʟɪsᴛ**</blockquoat>"
        f"<blockquoat>{fmt_with_price(modules)}</blockquoat>"
        f"<blockquoat>📊 ᴛᴏᴛᴀʟ: `{len(modules)}` | ғʀᴇᴇ: `{free}` | ᴘᴀɪᴅ: `{paid}`</blockquoat>"
        "<blockquoat>🧾 ᴘʀɪᴄᴇs ᴀʀᴇ ᴍᴏɴᴛʜʟʏ.</blockquoat>"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /games
# → List GAMES modules WITHOUT price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("games"))
async def list_games_no_price(client: Client, message: Message):
    path    = os.path.join(PLUGINS_PATH, "GAMES")
    modules = scan_modules_from_path(path)
    text = (
        "<blockquoat>🎮 **ɢᴀᴍᴇs ᴍᴏᴅᴜʟᴇs**</blockquoat>"
        f"<blockquoat>{fmt_without_price(modules)}</blockquoat>"
        f"<blockquoat>📊 ᴛᴏᴛᴀʟ ᴍᴏᴅᴜʟᴇs: `{len(modules)}`</blockquoat>"
    )
    await _send(message, text)


# ─────────────────────────────────────────────────────────────────────────────
# /gamesprice
# → List GAMES modules WITH price
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("gamesprice"))
async def list_games_with_price(client: Client, message: Message):
    path    = os.path.join(PLUGINS_PATH, "GAMES")
    modules = scan_modules_from_path(path)
    free    = sum(1 for m in modules if m["price"] == 0)
    paid    = len(modules) - free
    text = (
        "<blockquoat>🎮 **ɢᴀᴍᴇs ᴍᴏᴅᴜʟᴇs & ᴘʀɪᴄᴇʟɪsᴛ**</blockquoat>"
        f"<blockquoat>{fmt_with_price(modules)}</blockquoat>"
        f"<blockquoat>📊 ᴛᴏᴛᴀʟ: `{len(modules)}` | ғʀᴇᴇ: `{free}` | ᴘᴀɪᴅ: `{paid}`</blockquoat>"
        "<blockquoat>🧾 ᴘʀɪᴄᴇs ᴀʀᴇ ᴍᴏɴᴛʜʟʏ.</blockquoat>"
    )
    await _send(message, text)


# ─── Module meta ──────────────────────────────────────────────────────────────
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_34"
__help__ = """
🔻 /modules ➠ ʟɪꜱᴛ ᴀʟʟ ᴀᴠᴀɪʟᴀʙʟᴇ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜ ᴘʀɪᴄᴇ
🔻 /plugins ➠ ᴠɪᴇᴡ ᴀʟʟ ᴘʟᴜɢɪɴꜱ / ᴍᴏᴅᴜʟᴇꜱ (ɴᴏ ᴘʀɪᴄᴇ)
🔻 /mymodules ➠ ꜱʜᴏᴡ ʏᴏᴜʀ ᴅᴇᴘʟᴏʏᴇᴅ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜ ᴘʀɪᴄᴇ
🔻 /myplugins ➠ ꜱʜᴏᴡ ʏᴏᴜʀ ᴅᴇᴘʟᴏʏᴇᴅ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜᴏᴜᴛ ᴘʀɪᴄᴇ
🔻 /probots ➠ ʟɪꜱᴛ ᴘʀᴏ-ʙᴏᴛꜱ ᴍᴏᴅᴜʟᴇꜱ (ɴᴏ ᴘʀɪᴄᴇ)
🔻 /probotsprice ➠ ʟɪꜱᴛ ᴘʀᴏ-ʙᴏᴛꜱ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜ ᴘʀɪᴄᴇ
🔻 /manage ➠ ʟɪꜱᴛ ᴍᴀɴᴀɢᴇ ᴍᴏᴅᴜʟᴇꜱ (ɴᴏ ᴘʀɪᴄᴇ)
🔻 /manageprice ➠ ʟɪꜱᴛ ᴍᴀɴᴀɢᴇ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜ ᴘʀɪᴄᴇ
🔻 /games ➠ ʟɪꜱᴛ ɢᴀᴍᴇꜱ ᴍᴏᴅᴜʟᴇꜱ (ɴᴏ ᴘʀɪᴄᴇ)
🔻 /gamesprice ➠ ʟɪꜱᴛ ɢᴀᴍᴇꜱ ᴍᴏᴅᴜʟᴇꜱ ᴡɪᴛʜ ᴘʀɪᴄᴇ
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "Modules"
MOD_PRICE = "0"
