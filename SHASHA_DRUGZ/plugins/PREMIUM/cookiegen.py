# SHASHA_DRUGZ/plugins/cookies_manager.py
import os
import traceback

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from SHASHA_DRUGZ import app, LOGGER
from config import ADMINS_ID, LOG_GROUP_ID
from SHASHA_DRUGZ.platforms.Youtube import (
    COOKIE_FILE,          # absolute path → cookies/youtube_cookies.txt
    get_cookies,          # async → returns path or None
    verify_cookies_file,  # sync → bool
)

# ─────────────────────────────────────────────────────────────────────────────
#  COOKIE FILE PATH  (resolved once at import time)
#  Falls back to a sane default if Youtube.py doesn't export COOKIE_FILE.
# ─────────────────────────────────────────────────────────────────────────────
try:
    _COOKIE_PATH: str = COOKIE_FILE
except Exception:
    _COOKIE_PATH = os.path.join(os.getcwd(), "cookies", "youtube_cookies.txt")

os.makedirs(os.path.dirname(_COOKIE_PATH), exist_ok=True)


def cookie_txt_file() -> str | None:
    """Return the cookie file path if it exists and is non-empty, else None."""
    if os.path.exists(_COOKIE_PATH) and os.path.getsize(_COOKIE_PATH) > 0:
        return _COOKIE_PATH
    return None


async def get_cookies_simple() -> str | None:
    """
    Wrapper around Youtube.get_cookies() that returns the cookie file path.
    Uses force_refresh=True so a brand-new cookie is always generated.
    """
    try:
        path = await get_cookies(force_refresh=True)
        return path if path and os.path.exists(path) else None
    except Exception as e:
        LOGGER("SHASHA_DRUGZ").error(f"get_cookies_simple: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  HELPER: admin check
# ─────────────────────────────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS_ID


# ─────────────────────────────────────────────────────────────────────────────
#  HELPER: button markup
# ─────────────────────────────────────────────────────────────────────────────
def cookie_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 𝐃ᴏᴡɴʟᴏᴀᴅ",   callback_data="cookie_download"),
            InlineKeyboardButton("🔄 𝐑ᴇɢᴇɴᴇʀᴀᴛᴇ", callback_data="cookie_regenerate"),
        ]
    ])


# ─────────────────────────────────────────────────────────────────────────────
#  HELPER: log-group notification
# ─────────────────────────────────────────────────────────────────────────────
async def notify_log_group(user, cookie_file: str, action: str) -> None:
    try:
        if not LOG_GROUP_ID or not user:
            return
        caption = (
            f"🍪 **Manual Cookie Action**\n\n"
            f"👤 User   : {user.mention}\n"
            f"🆔 ID     : `{user.id}`\n"
            f"⚙️ Action : **{action}**"
        )
        await app.send_document(LOG_GROUP_ID, document=cookie_file, caption=caption)
    except Exception as e:
        LOGGER("SHASHA_DRUGZ").error(f"LOG GROUP COOKIE ERROR: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  /getcookie  — send the current cookie file to the admin
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("getcookie"))
async def get_cookie_command(client, message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.reply_text("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.")

    try:
        cookie_file = cookie_txt_file()
        if not cookie_file:
            return await message.reply_text("❌ ɴᴏ ᴄᴏᴏᴋɪᴇ ғɪʟᴇ ғᴏᴜɴᴅ.")

        await message.reply_document(
            document=cookie_file,
            caption="🍪 **ʟᴀᴛᴇsᴛ ʏᴏᴜᴛᴜʙᴇ ᴄᴏᴏᴋɪᴇ ғɪʟᴇ**",
            reply_markup=cookie_buttons(),
        )
        await notify_log_group(message.from_user, cookie_file, "Downloaded Cookie")

    except Exception as e:
        LOGGER("SHASHA_DRUGZ").error(f"GET COOKIE ERROR: {e}")
        await message.reply_text(f"❌ ᴇʀʀᴏʀ:\n`{str(e)[:200]}`")


# ─────────────────────────────────────────────────────────────────────────────
#  /newcookie  — generate a fresh cookie via Playwright and return it
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("newcookie"))
async def new_cookie_command(client, message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.reply_text("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.")

    msg = await message.reply_text("🔄 ɢᴇɴᴇʀᴀᴛɪɴɢ ɴᴇᴡ ᴄᴏᴏᴋɪᴇs...")
    try:
        cookie_file = await get_cookies_simple()
        if not cookie_file:
            return await msg.edit("❌ ᴄᴏᴏᴋɪᴇ ɢᴇɴᴇʀᴀᴛɪᴏɴ ғᴀɪʟᴇᴅ.")

        await msg.edit("✅ ɴᴇᴡ ᴄᴏᴏᴋɪᴇ ɢᴇɴᴇʀᴀᴛᴇᴅ!")
        await message.reply_document(
            document=cookie_file,
            caption="🍪 **ғʀᴇsʜ ʏᴏᴜᴛᴜʙᴇ ᴄᴏᴏᴋɪᴇ ɢᴇɴᴇʀᴀᴛᴇᴅ**",
            reply_markup=cookie_buttons(),
        )
        await notify_log_group(message.from_user, cookie_file, "Generated New Cookie")

    except Exception as e:
        LOGGER("SHASHA_DRUGZ").error(traceback.format_exc())
        await msg.edit(f"❌ ᴄᴏᴏᴋɪᴇ ɢᴇɴᴇʀᴀᴛɪᴏɴ ғᴀɪʟᴇᴅ:\n`{str(e)[:200]}`")


# ─────────────────────────────────────────────────────────────────────────────
#  /uploadcookie  — reply to a .txt file to replace the active cookie file
#
#  Steps:
#    1. Verify the reply contains a .txt document.
#    2. Download it to a temp path.
#    3. Validate it looks like a Netscape cookie file with YouTube cookies.
#    4. Remove any existing youtube_cookies.txt.
#    5. Move the uploaded file into place as youtube_cookies.txt.
#    6. Confirm to the admin and notify the log group.
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("uploadcookie"))
async def upload_cookie_command(client, message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        return await message.reply_text("❌ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.")

    # ── Must reply to a document ──────────────────────────────────────────────
    reply = message.reply_to_message
    if not reply or not reply.document:
        return await message.reply_text(
            "❌ **Usage:** Reply to a `.txt` cookie file with `/uploadcookie`"
        )

    doc = reply.document

    # ── Must be a .txt file ───────────────────────────────────────────────────
    file_name: str = doc.file_name or ""
    if not file_name.lower().endswith(".txt"):
        return await message.reply_text(
            "❌ ᴏɴʟʏ `.txt` ғɪʟᴇs ᴀʀᴇ ᴀᴄᴄᴇᴘᴛᴇᴅ."
        )

    msg = await message.reply_text("📥 ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴄᴏᴏᴋɪᴇ ғɪʟᴇ...")

    try:
        # ── Download to a temp path first ─────────────────────────────────────
        cookies_dir = os.path.dirname(_COOKIE_PATH)
        os.makedirs(cookies_dir, exist_ok=True)
        tmp_path = os.path.join(cookies_dir, f"_upload_tmp_{doc.file_unique_id}.txt")

        await client.download_media(reply, file_name=tmp_path)

        if not os.path.exists(tmp_path):
            return await msg.edit("❌ ᴅᴏᴡɴʟᴏᴀᴅ ғᴀɪʟᴇᴅ. ᴛʀʏ ᴀɢᴀɪɴ.")

        # ── Validate the file is a proper Netscape cookie file ────────────────
        await msg.edit("🔍 ᴠᴀʟɪᴅᴀᴛɪɴɢ ᴄᴏᴏᴋɪᴇ ғɪʟᴇ...")

        if not verify_cookies_file(tmp_path):
            os.remove(tmp_path)
            return await msg.edit(
                "❌ **Invalid cookie file.**\n\n"
                "The file does not appear to be a valid Netscape cookie file "
                "containing YouTube cookies.\n\n"
                "Make sure it includes `youtube.com` cookies and is in "
                "Netscape HTTP Cookie File format."
            )

        # ── Remove old cookie file ────────────────────────────────────────────
        if os.path.exists(_COOKIE_PATH):
            os.remove(_COOKIE_PATH)
            LOGGER("SHASHA_DRUGZ").info(f"uploadcookie: removed old {_COOKIE_PATH}")

        # ── Move uploaded file into place ─────────────────────────────────────
        os.rename(tmp_path, _COOKIE_PATH)
        LOGGER("SHASHA_DRUGZ").info(
            f"uploadcookie: installed new cookie file → {_COOKIE_PATH}"
        )

        # ── Confirm ───────────────────────────────────────────────────────────
        await msg.edit(
            f"✅ **Cookie file uploaded successfully!**\n\n"
            f"📄 Saved as: `youtube_cookies.txt`\n"
            f"📁 Path: `{_COOKIE_PATH}`\n\n"
            f"The new cookie will be used for all future downloads.",
            reply_markup=cookie_buttons(),
        )

        # ── Log group notification ────────────────────────────────────────────
        await notify_log_group(
            message.from_user,
            _COOKIE_PATH,
            f"Uploaded Cookie (original: {file_name})",
        )

    except Exception as e:
        LOGGER("SHASHA_DRUGZ").error(f"UPLOAD COOKIE ERROR:\n{traceback.format_exc()}")
        # Clean up temp file if it exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        await msg.edit(f"❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ:\n`{str(e)[:300]}`")


# ─────────────────────────────────────────────────────────────────────────────
#  BUTTON CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex("^cookie_"))
async def cookie_callback_handler(client, query: CallbackQuery):
    if not query.from_user or not is_admin(query.from_user.id):
        return await query.answer("❌ ɴᴏᴛ ᴀʟʟᴏᴡᴇᴅ", show_alert=True)

    action = query.data
    try:
        # ── DOWNLOAD BUTTON ───────────────────────────────────────────────────
        if action == "cookie_download":
            cookie_file = cookie_txt_file()
            if not cookie_file:
                return await query.answer("No cookie file found", show_alert=True)

            await query.message.reply_document(
                document=cookie_file,
                caption="📥 **ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ ᴄᴏᴏᴋɪᴇ ғɪʟᴇ**",
            )
            await notify_log_group(
                query.from_user,
                cookie_file,
                "Downloaded via Button",
            )
            await query.answer("ᴄᴏᴏᴋɪᴇ sᴇɴᴛ ✅")

        # ── REGENERATE BUTTON ─────────────────────────────────────────────────
        elif action == "cookie_regenerate":
            await query.answer("ɢᴇɴᴇʀᴀᴛɪɴɢ ɴᴇᴡ ᴄᴏᴏᴋɪᴇ...")
            status = await query.message.reply_text("🔄 ʀᴇɢᴇɴᴇʀᴀᴛɪɴɢ ᴄᴏᴏᴋɪᴇs...")

            cookie_file = await get_cookies_simple()
            if not cookie_file:
                return await status.edit("❌ ᴄᴏᴏᴋɪᴇ ɢᴇɴᴇʀᴀᴛɪᴏɴ ғᴀɪʟᴇᴅ.")

            await status.edit("✅ ᴄᴏᴏᴋɪᴇ ʀᴇɢᴇɴᴇʀᴀᴛᴇᴅ!")
            await query.message.reply_document(
                document=cookie_file,
                caption="🍪 **ɴᴇᴡ ᴄᴏᴏᴋɪᴇ ɢᴇɴᴇʀᴀᴛᴇᴅ**",
                reply_markup=cookie_buttons(),
            )
            await notify_log_group(
                query.from_user,
                cookie_file,
                "Regenerated via Button",
            )

    except Exception:
        LOGGER("SHASHA_DRUGZ").error(traceback.format_exc())
        await query.answer("Error occurred", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE META
# ─────────────────────────────────────────────────────────────────────────────
