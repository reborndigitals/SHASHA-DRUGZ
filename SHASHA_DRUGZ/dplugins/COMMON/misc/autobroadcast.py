import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.enums import ParseMode
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import get_served_chats
from SHASHA_DRUGZ.core.mongo import mongodb

db = mongodb

from config import START_IMG_URL, AUTO_GCAST_MSG, AUTO_GCAST, LOGGER_ID, SUPPORT_CHAT

# ------------------ Database helpers ------------------
AUTO_BROADCAST_COLL = db["auto_broadcast"]  # collection name

async def get_ab_settings():
    """Return the current auto‑broadcast settings dict."""
    settings = await AUTO_BROADCAST_COLL.find_one({"_id": "settings"})
    if not settings:
        # Initialise with config defaults
        settings = {
            "_id": "settings",
            "enabled": bool(AUTO_GCAST),
            "image_url": START_IMG_URL,
            "message": AUTO_GCAST_MSG or "",
            "button_url": SUPPORT_CHAT,
        }
        await AUTO_BROADCAST_COLL.insert_one(settings)
    return settings

async def update_ab_settings(updates: dict):
    """Apply partial updates to the settings document."""
    await AUTO_BROADCAST_COLL.update_one(
        {"_id": "settings"},
        {"$set": updates},
        upsert=True
    )

# ------------------ Command handlers ------------------
@Client.on_message(filters.command("abroadcastimage") & filters.private)
async def set_ab_image(client: Client, message: Message):
    """Set the image for auto‑broadcast (reply to a photo)."""
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply_text("❌ Please reply to a photo.")
    file_id = message.reply_to_message.photo.file_id
    await update_ab_settings({"image_url": file_id})
    await message.reply_text("✅ Auto‑broadcast image updated successfully.")

@Client.on_message(filters.command("abroadcastmsg") & filters.private)
async def set_ab_message(client: Client, message: Message):
    """Set the caption/message for auto‑broadcast."""
    new_msg = None
    if len(message.command) > 1:
        new_msg = message.text.split(maxsplit=1)[1]
    elif message.reply_to_message and message.reply_to_message.text:
        new_msg = message.reply_to_message.text
    else:
        return await message.reply_text("❌ Please provide the message text or reply to a message.")
    await update_ab_settings({"message": new_msg})
    await message.reply_text("✅ Auto‑broadcast message updated successfully.")

@Client.on_message(filters.command("abroadcasturl") & filters.private)
async def set_ab_url(client: Client, message: Message):
    """Set the button URL for auto‑broadcast."""
    if len(message.command) < 2:
        return await message.reply_text("❌ Please provide a URL.\nUsage: `/abroadcasturl https://example.com`")
    url = message.command[1]
    await update_ab_settings({"button_url": url})
    await message.reply_text("✅ Auto‑broadcast button URL updated successfully.")

@Client.on_message(filters.command("resetautobroadcast") & filters.private)
async def reset_ab(client: Client, message: Message):
    """Reset auto‑broadcast settings to config defaults."""
    await update_ab_settings({
        "image_url": START_IMG_URL,
        "message": AUTO_GCAST_MSG or "",
        "button_url": SUPPORT_CHAT,
        "enabled": bool(AUTO_GCAST)
    })
    await message.reply_text("✅ Auto‑broadcast settings reset to default values.")

@Client.on_message(filters.command("autobroadcast") & filters.private)
async def toggle_ab_menu(client: Client, message: Message):
    """Show enable/disable buttons for auto‑broadcast."""
    settings = await get_ab_settings()
    status = "✅ Enabled" if settings["enabled"] else "❌ Disabled"
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Enable", callback_data="ab_enable"),
            InlineKeyboardButton("Disable", callback_data="ab_disable")
        ]
    ])
    await message.reply_text(f"**Auto‑Broadcast Status:** {status}\n\nChoose an option:", reply_markup=buttons)

@Client.on_callback_query(filters.regex("^ab_(enable|disable)$"))
async def toggle_ab_callback(client: Client, callback: CallbackQuery):
    """Handle enable/disable callbacks."""
    action = callback.data.split("_")[1]
    new_state = (action == "enable")
    await update_ab_settings({"enabled": new_state})
    status = "✅ Enabled" if new_state else "❌ Disabled"
    await callback.message.edit_text(f"Auto‑Broadcast has been **{status}**.", reply_markup=None)
    await callback.answer()

# ------------------ Broadcast logic ------------------
async def send_text_once():
    """Send the info message to LOGGER_ID once on startup."""
    try:
        await app.send_message(
            LOGGER_ID,
            "**ᴀᴜᴛᴏ ɢᴄᴀsᴛ ɪs ᴇɴᴀʙʟᴇᴅ sᴏ ᴀᴜᴛᴏ ɢᴄᴀsᴛ/ʙʀᴏᴀᴅᴄᴀsᴛ ɪs ᴅᴏɪɴ ɪɴ ᴀʟʟ ᴄʜᴀᴛs ᴄᴏɴᴛɪɴᴜᴏᴜsʟʏ.**\n"
            "**ɪᴛ ᴄᴀɴ ʙᴇ sᴛᴏᴘᴘᴇᴅ ʙʏ ᴘᴜᴛ ᴠᴀʀɪᴀʙʟᴇ [ᴀᴜᴛᴏ_ɢᴄᴀsᴛ = (ᴋᴇᴇᴘ ʙʟᴀɴᴋ & ᴅᴏɴᴛ ᴡʀɪᴛᴇ ᴀɴʏᴛʜɪɴɢ)]**"
        )
    except Exception:
        pass

async def send_message_to_chats(settings: dict):
    """Send the broadcast to all served chats using current settings."""
    image = settings.get("image_url") or START_IMG_URL
    caption = settings.get("message") or ""
    button_url = settings.get("button_url") or SUPPORT_CHAT

    # Build button if URL exists
    reply_markup = None
    if button_url:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💥 𝐆σ 𝐅ᴇᴧᴛᴜʀᴇ𝗌 🚀", url=button_url)]
        ])

    chats = await get_served_chats()
    for chat_info in chats:
        chat_id = chat_info.get("chat_id")
        if not isinstance(chat_id, int):
            continue
        try:
            await app.send_photo(chat_id, photo=image, caption=caption, reply_markup=reply_markup)
            await asyncio.sleep(20)  # avoid flood waits
        except Exception:
            continue  # ignore errors for individual chats

async def continuous_broadcast():
    """Background task: broadcast every 8 hours if enabled."""
    await send_text_once()  # one‑time startup message

    while True:
        settings = await get_ab_settings()
        if settings.get("enabled"):
            try:
                await send_message_to_chats(settings)
            except Exception:
                pass  # global error ignored

        await asyncio.sleep(28800)  # 8 hours

# ------------------ Start background task ------------------
asyncio.create_task(continuous_broadcast())

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_38"
__help__ = """
🔻 /abroadcast ➠ ᴇɴᴀʙʟᴇ / ᴅɪsᴀʙʟᴇ ᴀᴜᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ sᴇᴛᴛɪɴɢs
🔻 /abroadcastimage ➠ sᴇᴛ ᴀᴜᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ɪᴍᴀɢᴇ (ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ)
🔻 /abroadcastmsg ➠ sᴇᴛ ᴀᴜᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇssᴀɢᴇ / ᴄᴀᴘᴛɪᴏɴ
🔻 /abroadcasturl ➠ sᴇᴛ ᴀᴜᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ʙᴜᴛᴛᴏɴ ᴜʀʟ
🔻 /resetautobroadcast ➠ ʀᴇsᴇᴛ ᴀᴜᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ sᴇᴛᴛɪɴɢs ᴛᴏ ᴅᴇғᴀᴜʟᴛ
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "AutoBroadcast"
MOD_PRICE = "50"
