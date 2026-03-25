import os
import re
import time
import base64
import imghdr
import subprocess
import asyncio
import httpx
from traceback import format_exc
from uuid import uuid4

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import (
    PeerIdInvalid,
    ShortnameOccupyFailed,
    StickerEmojiInvalid,
    UserIsBlocked,
)
import pyrogram

from SHASHA_DRUGZ import app
from config import BOT_USERNAME
from SHASHA_DRUGZ.utils.errors import capture_err
from SHASHA_DRUGZ.utils.files import (
    get_document_from_file_id,
    resize_file_to_sticker_size,
    upload_document,
)
from SHASHA_DRUGZ.utils.stickerset import (
    create_sticker,
    create_sticker_set,
    get_sticker_set_by_name,
    add_sticker_to_set,
)

print("[sticker_kang] st, packkang, stid, kang")

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
MAX_STICKERS = 120
STATIC_TYPES = ["jpeg", "png", "webp"]


# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------
async def make_video_sticker(client, file_path, emoji, msg):
    """
    Convert video/gif to Telegram video sticker with a progress bar.
    """
    out = f"sticker_{uuid4().hex}.webm"

    # Get video duration (for progress calculation)
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]

    try:
        duration = float(subprocess.check_output(probe_cmd).decode().strip())
    except Exception:
        duration = 3  # fallback

    cmd = [
        "ffmpeg",
        "-i", file_path,
        "-vf", "scale=512:512:force_original_aspect_ratio=decrease,fps=30",
        "-c:v", "libvpx-vp9",
        "-b:v", "256K",
        "-an",
        "-t", "3",
        "-y",
        out
    ]

    process = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        universal_newlines=True
    )

    last_update = time.time()

    while True:
        line = process.stderr.readline()
        if not line:
            break

        # Extract time=XX:XX:XX.XX from ffmpeg output
        match = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
        if match:
            time_str = match.group(1)
            h, m, s = time_str.split(":")
            current_time = float(h) * 3600 + float(m) * 60 + float(s)

            percent = min((current_time / duration) * 100, 100)

            # Update progress every ~1 second to avoid spam
            if time.time() - last_update > 1:
                bar = "█" * int(percent // 10) + "░" * (10 - int(percent // 10))
                try:
                    await msg.edit(
                        f"🎬 **Converting to sticker...**\n\n"
                        f"[{bar}] {percent:.1f}%"
                    )
                except Exception:
                    pass
                last_update = time.time()

    process.wait()  # wait for conversion to finish

    # Final upload stage
    await msg.edit("📤 Uploading sticker...")

    sticker = await create_sticker(
        await upload_document(client, out, None),
        emoji,
        is_video=True,
    )

    os.remove(out)
    return sticker


# ------------------------------------------------------------------------------
# Command: /st <sticker_id> – send a sticker by its file_id
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("st"))
def generate_sticker(client, message: Message):
    if len(message.command) == 2:
        sticker_id = message.command[1]
        try:
            client.send_sticker(message.chat.id, sticker=sticker_id)
        except Exception as e:
            message.reply_text(f"Error: {e}")
    else:
        message.reply_text("Please provide a sticker ID after /st command.")


# ------------------------------------------------------------------------------
# Command: /packkang – copy an entire sticker pack
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("packkang"))
async def _packkang(client, message: Message):
    txt = await message.reply_text("**ᴘʀᴏᴄᴇssɪɴɢ....**")
    if not message.reply_to_message:
        await txt.edit('ʀᴇᴘʟʏ ᴛᴏ ᴍᴇssᴀɢᴇ')
        return
    if not message.reply_to_message.sticker:
        await txt.edit('ʀᴇᴘʟʏ ᴛᴏ sᴛɪᴄᴋᴇʀ')
        return
    if message.reply_to_message.sticker.is_animated or message.reply_to_message.sticker.is_video:
        return await txt.edit("ʀᴇᴘʟʏ ᴛᴏ ᴀ ɴᴏɴ-ᴀɴɪᴍᴀᴛᴇᴅ sᴛɪᴄᴋᴇʀ")
    if len(message.command) < 2:
        pack_name = f'{message.from_user.first_name}_sticker_pack_by_@{BOT_USERNAME}'
    else:
        pack_name = message.text.split(maxsplit=1)[1]
    short_name = message.reply_to_message.sticker.set_name
    stickers = await app.invoke(
        pyrogram.raw.functions.messages.GetStickerSet(
            stickerset=pyrogram.raw.types.InputStickerSetShortName(
                short_name=short_name),
            hash=0))
    shits = stickers.documents
    sticks = []

    for i in shits:
        sex = pyrogram.raw.types.InputDocument(
            id=i.id,
            access_hash=i.access_hash,
            file_reference=i.thumbs[0].bytes
        )
        sticks.append(
            pyrogram.raw.types.InputStickerSetItem(
                document=sex,
                emoji=i.attributes[1].alt
            )
        )

    try:
        short_name = f'stikcer_pack_{str(uuid4()).replace("-","")}_by_{app.me.username}'
        user_id = await app.resolve_peer(message.from_user.id)
        await app.invoke(
            pyrogram.raw.functions.stickers.CreateStickerSet(
                user_id=user_id,
                title=pack_name,
                short_name=short_name,
                stickers=sticks,
            )
        )
        await txt.edit(
            f"**ʜᴇʀᴇ ɪs ʏᴏᴜʀ ᴋᴀɴɢᴇᴅ ʟɪɴᴋ**!\n**ᴛᴏᴛᴀʟ sᴛɪᴄᴋᴇʀ **: {len(sticks)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("ᴘᴀᴄᴋ ʟɪɴᴋ", url=f"http://t.me/addstickers/{short_name}")]
            ])
        )
    except Exception as e:
        await message.reply(str(e))


# ------------------------------------------------------------------------------
# Command: /stickerid or /stid – get sticker file_id
# ------------------------------------------------------------------------------
@Client.on_message(filters.command(["stickerid", "stid"]))
async def sticker_id(client, msg: Message):
    if not msg.reply_to_message:
        await msg.reply_text("Reply to a sticker")
    elif not msg.reply_to_message.sticker:
        await msg.reply_text("Reply to a sticker")
    st_in = msg.reply_to_message.sticker
    await msg.reply_text(f"""
⊹ <u>**sᴛɪᴄᴋᴇʀ ɪɴғᴏ</u>** ⊹
**⊚ sᴛɪᴄᴋᴇʀ ɪᴅ **: `{st_in.file_id}`\n
**⊚ sᴛɪᴄᴋᴇʀ ᴜɴɪǫᴜᴇ ɪᴅ **: `{st_in.file_unique_id}`
""")


# ------------------------------------------------------------------------------
# Command: /kang – add a sticker/image/gif/video to your personal pack
# ------------------------------------------------------------------------------
@Client.on_message(filters.command("kang"))
@capture_err
async def kang(client, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to a sticker, image, gif, or video.")
    if not message.from_user:
        return await message.reply_text("Use this in my PM.")

    msg = await message.reply_text("Kanging...")
    r = message.reply_to_message
    emoji = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "🤔"

    try:
        # Static sticker
        if r.sticker and not r.sticker.is_animated and not r.sticker.is_video:
            sticker = await create_sticker(
                await get_document_from_file_id(r.sticker.file_id),
                r.sticker.emoji or emoji,
            )
        # Animated TGS
        elif r.sticker and r.sticker.is_animated:
            sticker = await create_sticker(
                await get_document_from_file_id(r.sticker.file_id),
                r.sticker.emoji or emoji,
                is_animated=True,
            )
        # Video sticker
        elif r.sticker and r.sticker.is_video:
            sticker = await create_sticker(
                await get_document_from_file_id(r.sticker.file_id),
                r.sticker.emoji or emoji,
                is_video=True,
            )
        # Video / GIF
        elif r.video or r.animation:
            file = await app.download_media(r)
            sticker = await make_video_sticker(client, file, emoji, msg)
            os.remove(file)
        # Photo or document
        elif r.photo or r.document:
            file = await app.download_media(r)
            ftype = imghdr.what(file)
            if ftype in STATIC_TYPES:
                file = await resize_file_to_sticker_size(file)
                sticker = await create_sticker(
                    await upload_document(client, file, message.chat.id),
                    emoji,
                )
            else:  # Probably a GIF disguised as document
                sticker = await make_video_sticker(client, file, emoji, msg)
            os.remove(file)
        else:
            return await msg.edit("Unsupported media type.")

        # Handle pack creation / addition
        packname = f"f{message.from_user.id}_by_{BOT_USERNAME}"
        limit = 0
        packnum = 0
        while True:
            if limit > 50:
                return await msg.delete()
            stickerset = await get_sticker_set_by_name(client, packname)
            if not stickerset:
                await create_sticker_set(
                    client,
                    message.from_user.id,
                    f"{message.from_user.first_name[:32]}'s kang pack",
                    packname,
                    [sticker],
                )
                break
            elif stickerset.set.count >= MAX_STICKERS:
                packnum += 1
                packname = f"f{packnum}_{message.from_user.id}_by_{BOT_USERNAME}"
                limit += 1
                continue
            else:
                await add_sticker_to_set(client, stickerset, sticker)
                break

        await msg.edit(f"Sticker Kanged!\n[Add Pack](t.me/addstickers/{packname})")

    except (PeerIdInvalid, UserIsBlocked):
        await msg.edit(
            "Start me in PM first.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Start", url=f"t.me/{BOT_USERNAME}")]]
            ),
        )
    except StickerEmojiInvalid:
        await msg.edit("Invalid emoji.")
    except ShortnameOccupyFailed:
        await msg.edit("Change your Telegram username.")
    except Exception:
        print(format_exc())
        await msg.edit("Failed to kang sticker.")


# ------------------------------------------------------------------------------
# Module metadata (for help menu)
# ------------------------------------------------------------------------------
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_54"
__help__ = """
🔻 /st <sticker_id> ➠ sᴇɴᴅ sᴛɪᴄᴋᴇʀ ʙʏ ɪᴅ
🔻 /kang ➠ ᴀᴅᴅ sᴛɪᴄᴋᴇʀ/ɪᴍᴀɢᴇ/ɢɪꜰ/ᴠɪᴅᴇᴏ ᴛᴏ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ ᴘᴀᴄᴋ
🔻 /packkang ➠ ᴋᴀɴɢ ᴀɴ ᴇɴᴛɪʀᴇ sᴛɪᴄᴋᴇʀ ᴘᴀᴄᴋ
🔻 /stickerid, /stid ➠ ɢᴇᴛ sᴛɪᴄᴋᴇʀ ɪᴅ & ᴜɴɪǫᴜᴇ ɪᴅ
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "KangSticker"
MOD_PRICE = "60"
