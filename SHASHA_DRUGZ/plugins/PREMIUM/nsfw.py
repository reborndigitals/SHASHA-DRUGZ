import os
import json
import asyncio
import time
from typing import Dict, Any

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError

# `app` should be your Pyrogram client instance used in SHASHA_DRUGZ.
from SHASHA_DRUGZ import app

# Try to use motor (MongoDB); fallback to JSON file
USE_MONGO = False
try:
    import motor.motor_asyncio as motor
    MONGO_URL = os.getenv(
        "MONGO_URL",
        "mongodb+srv://iamnobita1:nobitamusic1@cluster0.k08op.mongodb.net/?retryWrites=true&w=majority",
    )
    if MONGO_URL:
        mongo_client = motor.AsyncIOMotorClient(MONGO_URL)
        db = mongo_client.get_default_database()
        nsfw_coll = db.get_collection("nsfw_settings")
        USE_MONGO = True
except Exception:
    USE_MONGO = False

SETTINGS_FILE = "nsfw_settings.json"
_default_settings = {
    "enabled": False,
    "block_types": {
        "sticker": True,
        "photo": True,
        "video": True,
        "animation": True,
        "document": True,
        "voice": False,
        "audio": False,
    },
    "warning_image": "",
    "time_mute": {"enabled": True, "duration_seconds": 60 * 60},
    "auto_kick": False,
    "auto_ban": False,
    "flood": {"enabled": True, "threshold": 5, "timeframe_seconds": 10},
}

_flood_track: Dict[int, Dict[int, list]] = {}


async def load_settings(chat_id: int) -> Dict[str, Any]:
    if USE_MONGO:
        try:
            doc = await nsfw_coll.find_one({"chat_id": chat_id})
            if not doc:
                await nsfw_coll.insert_one({"chat_id": chat_id, "settings": _default_settings})
                return dict(_default_settings)
            return doc.get("settings", dict(_default_settings))
        except Exception:
            return dict(_default_settings)
    else:
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w+") as f:
                json.dump({}, f)
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
        return data.get(str(chat_id), dict(_default_settings))


async def save_settings(chat_id: int, settings: Dict[str, Any]):
    if USE_MONGO:
        try:
            await nsfw_coll.update_one({"chat_id": chat_id}, {"$set": {"settings": settings}}, upsert=True)
        except Exception:
            pass
    else:
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w+") as f:
                json.dump({}, f)
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[str(chat_id)] = settings
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)


async def is_chat_owner(client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except RPCError:
        return False
    except Exception:
        return False


def settings_to_keyboard(settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(f"NSFW: {'ON' if settings['enabled'] else 'OFF'}", callback_data="nsfw_toggle")],
        [InlineKeyboardButton(f"Time-mute: {'ON' if settings['time_mute']['enabled'] else 'OFF'}", callback_data="toggle_time_mute")],
        [InlineKeyboardButton(f"Auto-kick: {'ON' if settings['auto_kick'] else 'OFF'}", callback_data="toggle_auto_kick"),
         InlineKeyboardButton(f"Auto-ban: {'ON' if settings['auto_ban'] else 'OFF'}", callback_data="toggle_auto_ban")],
        [InlineKeyboardButton("Change warning image", callback_data="change_warning_image")],
        [InlineKeyboardButton("Toggle block types", callback_data="block_types")],
        [InlineKeyboardButton("Close", callback_data="nsfw_close")]
    ]
    return InlineKeyboardMarkup(kb)


@app.on_message(filters.command("nsfw") & filters.group)
async def nsfw_command(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_chat_owner(client, chat_id, user_id):
        await message.reply_text("⚠️ Only the group owner can change NSFW settings.")
        return

    if len(message.command) < 2:
        settings = await load_settings(chat_id)
        text = (
            f"NSFW settings for this chat:Enabled: {settings['enabled']}"
            f" Block types: {', '.join([t for t,v in settings['block_types'].items() if v])}"
        )
        await client.send_message(chat_id, text, reply_markup=settings_to_keyboard(settings))
        return

    arg = message.command[1].lower()
    settings = await load_settings(chat_id)
    if arg in ("on", "enable", "1", "true"):
        settings["enabled"] = True
        await save_settings(chat_id, settings)
        await client.send_message(chat_id, "✅ NSFW filters enabled.")
    elif arg in ("off", "disable", "0", "false"):
        settings["enabled"] = False
        await save_settings(chat_id, settings)
        await client.send_message(chat_id, "✅ NSFW filters disabled.")
    else:
        await client.send_message(chat_id, "Usage: /nsfw on|off")


@app.on_callback_query(filters.regex(r"^nsfw_"))
async def nsfw_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id

    if not await is_chat_owner(client, chat_id, user_id):
        await callback_query.answer("Only the group owner can change these.", show_alert=True)
        return

    settings = await load_settings(chat_id)

    if data == "nsfw_toggle":
        settings["enabled"] = not settings.get("enabled", False)
        await save_settings(chat_id, settings)
        await callback_query.message.edit_reply_markup(settings_to_keyboard(settings))
        await callback_query.answer("Toggled NSFW")
        return

    if data == "toggle_time_mute":
        settings["time_mute"]["enabled"] = not settings["time_mute"].get("enabled", True)
        await save_settings(chat_id, settings)
        await callback_query.message.edit_reply_markup(settings_to_keyboard(settings))
        await callback_query.answer("Toggled time-mute")
        return

    if data == "toggle_auto_kick":
        settings["auto_kick"] = not settings.get("auto_kick", False)
        await save_settings(chat_id, settings)
        await callback_query.message.edit_reply_markup(settings_to_keyboard(settings))
        await callback_query.answer("Toggled auto-kick")
        return

    if data == "toggle_auto_ban":
        settings["auto_ban"] = not settings.get("auto_ban", False)
        await save_settings(chat_id, settings)
        await callback_query.message.edit_reply_markup(settings_to_keyboard(settings))
        await callback_query.answer("Toggled auto-ban")
        return

    if data == "change_warning_image":
        await callback_query.answer("Use /set_warning_image <image_url> to set warning image", show_alert=True)
        return

    if data == "block_types":
        kb = []
        for t, val in settings["block_types"].items():
            kb.append([InlineKeyboardButton(f"{t}: {'ON' if val else 'OFF'}", callback_data=f"toggle_block_{t}")])
        kb.append([InlineKeyboardButton("Back", callback_data="nsfw_toggle")])
        await callback_query.message.edit_reply_markup(InlineKeyboardMarkup(kb))
        await callback_query.answer()
        return

    if data.startswith("toggle_block_"):
        t = data.split("toggle_block_")[1]
        if t in settings["block_types"]:
            settings["block_types"][t] = not settings["block_types"][t]
            await save_settings(chat_id, settings)
            kb = []
            for tt, val in settings["block_types"].items():
                kb.append([InlineKeyboardButton(f"{tt}: {'ON' if val else 'OFF'}", callback_data=f"toggle_block_{tt}")])
            kb.append([InlineKeyboardButton("Back", callback_data="nsfw_toggle")])
            await callback_query.message.edit_reply_markup(InlineKeyboardMarkup(kb))
            await callback_query.answer(f"Toggled {t}")
        else:
            await callback_query.answer("Unknown type", show_alert=True)
        return

    if data == "nsfw_close":
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await callback_query.answer()
        return


# Custom filter to ignore bot commands
def not_command_filter(_, __, message: Message):
    if message.text and message.text.startswith("/"):
        return False
    return True


@app.on_message(
    filters.group & filters.create(not_command_filter),
    group=2
)
async def nsfw_moderator(client, message: Message):
    if not message.from_user:
        return

    chat_id = message.chat.id
    settings = await load_settings(chat_id)

    if not settings.get("enabled", False):
        return

    blocked = False
    blocked_reason = None

    if message.sticker and settings["block_types"].get("sticker"):
        blocked = True
        blocked_reason = "sticker"
    elif message.photo and settings["block_types"].get("photo"):
        blocked = True
        blocked_reason = "photo"
    elif message.video and settings["block_types"].get("video"):
        blocked = True
        blocked_reason = "video"
    elif message.animation and settings["block_types"].get("animation"):
        blocked = True
        blocked_reason = "animation"
    elif message.document and settings["block_types"].get("document"):
        blocked = True
        blocked_reason = "document"
    elif message.voice and settings["block_types"].get("voice"):
        blocked = True
        blocked_reason = "voice"
    elif message.audio and settings["block_types"].get("audio"):
        blocked = True
        blocked_reason = "audio"

    # Flood detection
    user_id = message.from_user.id
    now_ts = int(time.time())
    if settings.get("flood", {}).get("enabled"):
        timeframe = int(settings["flood"].get("timeframe_seconds", 10))
        threshold = int(settings["flood"].get("threshold", 5))
        chat_track = _flood_track.setdefault(chat_id, {})
        user_times = chat_track.setdefault(user_id, [])
        user_times.append(now_ts)
        while user_times and user_times[0] < now_ts - timeframe:
            user_times.pop(0)
        if len(user_times) >= threshold:
            blocked = True
            blocked_reason = blocked_reason or "flood"
            chat_track[user_id] = []

    if not blocked:
        return

    try:
        await client.delete_messages(chat_id, message.message_id)
    except Exception:
        pass

    warning_img = settings.get("warning_image")
    reply_text = f"⚠️ Your message was removed ({blocked_reason}). This group does not allow that media while NSFW filter is active."

    if warning_img:
        try:
            await client.send_photo(chat_id, warning_img, caption=reply_text)
        except Exception:
            await client.send_message(chat_id, reply_text)
    else:
        await client.send_message(chat_id, reply_text)

    if settings.get("time_mute", {}).get("enabled"):
        duration = int(settings["time_mute"].get("duration_seconds", 3600))
        until_date = int(time.time()) + duration
        try:
            perms = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_send_polls=False,
            )
            await client.restrict_chat_member(chat_id, user_id, permissions=perms, until_date=until_date)
            await client.send_message(chat_id, f"🔇 User <a href='tg://user?id={user_id}'>user</a> muted for {duration // 60} minutes.")
        except Exception:
            pass

    if settings.get("auto_kick"):
        try:
            await client.ban_chat_member(chat_id, user_id, revoke_messages=True)
            await asyncio.sleep(1)
            await client.unban_chat_member(chat_id, user_id)
            await client.send_message(chat_id, f"👢 User <a href='tg://user?id={user_id}'>user</a> was kicked (auto-kick).")
        except Exception:
            pass

    if settings.get("auto_ban"):
        try:
            await client.ban_chat_member(chat_id, user_id, revoke_messages=True)
            await client.send_message(chat_id, f"⛔ User <a href='tg://user?id={user_id}'>user</a> was banned (auto-ban).")
        except Exception:
            pass


# Admin commands
@app.on_message(filters.command("setnsfw") & filters.group)
async def nsfw_show_settings(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_chat_owner(client, chat_id, user_id):
        await client.send_message(chat_id, "Only the group owner can view NSFW settings.")
        return
    settings = await load_settings(chat_id)
    text = json.dumps(settings, indent=2)
    await client.send_message(chat_id, f"NSFW settings:<pre>{text}</pre>")


@app.on_message(filters.command("setwarnimage") & filters.group)
async def set_warning_image(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_chat_owner(client, chat_id, user_id):
        await client.send_message(chat_id, "Only the group owner can change warning image.")
        return
    if len(message.command) < 2:
        await client.send_message(chat_id, "Usage: /setwarnimage <image_url>Send empty to clear")
        return
    url = message.command[1].strip()
    settings = await load_settings(chat_id)
    settings["warning_image"] = url
    await save_settings(chat_id, settings)
    await client.send_message(chat_id, "✅ Warning image updated.")


@app.on_message(filters.command("setmutetime") & filters.group)
async def set_mute_duration(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_chat_owner(client, chat_id, user_id):
        await client.send_message(chat_id, "Only the group owner can change mute duration.")
        return
    if len(message.command) < 2:
        await client.send_message(chat_id, "Usage: /setmutetime <seconds>")
        return
    try:
        secs = int(message.command[1])
        settings = await load_settings(chat_id)
        settings["time_mute"]["duration_seconds"] = secs
        await save_settings(chat_id, settings)
        await client.send_message(chat_id, f"✅ Mute duration set to {secs} seconds.")
    except ValueError:
        await client.send_message(chat_id, "Provide an integer number of seconds.")


@app.on_message(filters.command("setflood") & filters.group)
async def set_flood(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_chat_owner(client, chat_id, user_id):
        await client.send_message(chat_id, "Only the group owner can change flood settings.")
        return
    if len(message.command) < 2:
        await client.send_message(chat_id, "Usage: /setflood <threshold> <timeframe_seconds> OR /setflood off")
        return
    if message.command[1].lower() == "off":
        settings = await load_settings(chat_id)
        settings["flood"]["enabled"] = False
        await save_settings(chat_id, settings)
        await client.send_message(chat_id, "✅ Flood protection disabled.")
        return
    try:
        threshold = int(message.command[1])
        timeframe = int(message.command[2]) if len(message.command) > 2 else 10
        settings = await load_settings(chat_id)
        settings["flood"]["enabled"] = True
        settings["flood"]["threshold"] = threshold
        settings["flood"]["timeframe_seconds"] = timeframe
        await save_settings(chat_id, settings)
        await client.send_message(chat_id, f"✅ Flood set: {threshold} messages per {timeframe} seconds.")
    except Exception:
        await client.send_message(chat_id, "Invalid numbers. Usage: /setflood <threshold> <timeframe_seconds>")


@app.on_message(filters.new_chat_members)
async def on_new_chat_member(client, message: Message):
    chat_id = message.chat.id
    await load_settings(chat_id)


__menu__ = "CMD_PRO"
__mod_name__ = "H_B_31"
__help__ = """
🔻 /nsfw ➠ ᴏᴘᴇɴꜱ ᴛʜᴇ ɴꜱꜰᴡ ꜱᴇᴛᴛɪɴɢꜱ ᴘᴀɴᴇʟ ᴡɪᴛʜ ɪɴʟɪɴᴇ ᴄᴏɴᴛʀᴏʟꜱ (ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ ᴏɴʟʏ).
🔻 /nsfw on ➠ ᴇɴᴀʙʟᴇꜱ ɴꜱꜰᴡ ꜰɪʟᴛᴇʀꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /nsfw off ➠ ᴅɪꜱᴀʙʟᴇꜱ ɴꜱꜰᴡ ꜰɪʟᴛᴇʀꜱ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /setnsfw ➠ ꜱʜᴏᴡꜱ ᴄᴜʀʀᴇɴᴛ ɴꜱꜰᴡ ꜱᴇᴛᴛɪɴɢꜱ ɪɴ ᴅᴇᴛᴀɪʟᴇᴅ ꜰᴏʀᴍᴀᴛ (ᴏᴡɴᴇʀ ᴏɴʟʏ).
🔻 /setwarnimage <image_url> ➠ ꜱᴇᴛꜱ ᴀ ᴡᴀʀɴɪɴɢ ɪᴍᴀɢᴇ ꜱʜᴏᴡɴ ᴡʜᴇɴ ɴꜱꜰᴡ ᴍᴇᴅɪᴀ ɪꜱ ʀᴇᴍᴏᴠᴇᴅ.
🔻 /setwarnimage ➠ ᴄʟᴇᴀʀꜱ ᴛʜᴇ ᴡᴀʀɴɪɴɢ ɪᴍᴀɢᴇ (ꜱᴇᴛ ᴇᴍᴘᴛʏ).
🔻 /setmutetime <seconds> ➠ ꜱᴇᴛꜱ ᴛᴇᴍᴘᴏʀᴀʀʏ ᴍᴜᴛᴇ ᴅᴜʀᴀᴛɪᴏɴ ꜰᴏʀ ɴꜱꜰᴡ ᴠɪᴏʟᴀᴛɪᴏɴꜱ.
🔻 /setflood <count> <seconds> ➠ ᴇɴᴀʙʟᴇꜱ ꜰʟᴏᴏᴅ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ꜰᴏʀ ɴꜱꜰᴡ ꜱᴘᴀᴍ
🔻 /setflood off ➠ ᴅɪꜱᴀʙʟᴇꜱ ꜰʟᴏᴏᴅ ᴅᴇᴛᴇᴄᴛɪᴏɴ ꜰᴏʀ ɴꜱꜰᴡ ꜰɪʟᴛᴇʀꜱ.

🔻 (ᴀᴜᴛᴏ) ➠ ᴅᴇʟᴇᴛᴇꜱ ɴꜱꜰᴡ ᴍᴇᴅɪᴀ (ꜱᴛɪᴄᴋᴇʀ / ᴘʜᴏᴛᴏ / ᴠɪᴅᴇᴏ / ɢɪꜰ / ᴅᴏᴄᴜᴍᴇɴᴛ / ᴀᴜᴅɪᴏ / ᴠᴏɪᴄᴇ).
🔻 (ᴀᴜᴛᴏ) ➠ ᴀᴘᴘʟɪᴇꜱ ᴍᴜᴛᴇ / ᴋɪᴄᴋ / ʙᴀɴ ʙᴀꜱᴇᴅ ᴏɴ ꜱᴇᴛᴛɪɴɢꜱ.
🔻 (ᴀᴜᴛᴏ) ➠ ꜱᴇɴᴅꜱ ᴡᴀʀɴɪɴɢ ᴍᴇꜱꜱᴀɢᴇ ᴏʀ ɪᴍᴀɢᴇ ᴡʜᴇɴ ᴄᴏɴᴛᴇɴᴛ ɪꜱ ʀᴇᴍᴏᴠᴇᴅ.
"""
