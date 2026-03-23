import os
import requests
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from SHASHA_DRUGZ import app

# ================= CONFIG =================
IMGBB_API_KEY = "3c3870ff68945d4045bb272c9557ae44"


# ================= CATBOX UPLOAD =================
def upload_catbox(file_path):
    url = "https://catbox.moe/user/api.php"
    data = {"reqtype": "fileupload"}
    files = {"fileToUpload": open(file_path, "rb")}

    try:
        response = requests.post(url, data=data, files=files)
        if response.status_code == 200:
            link = response.text.strip()

            if not link.startswith("http"):
                link = f"https://files.catbox.moe/{link.split('/')[-1]}"

            return True, link
        else:
            return False, f"Error {response.status_code}: {response.text}"

    except Exception as e:
        return False, str(e)


# ================= IMGBB UPLOAD =================
def upload_imgbb(file_path):
    try:
        with open(file_path, "rb") as f:
            url = "https://api.imgbb.com/1/upload"
            payload = {
                "key": IMGBB_API_KEY
            }
            files = {
                "image": f
            }

            response = requests.post(url, data=payload, files=files)
            data = response.json()

            if data["success"]:
                return True, data["data"]["url"]
            else:
                return False, str(data)

    except Exception as e:
        return False, str(e)


# ================= CATBOX COMMAND =================
@app.on_message(filters.command(["tgm", "tgt", "telegraph", "tl"]))
async def catbox_upload(client, message):

    if not message.reply_to_message:
        return await message.reply_text(
            "❍ ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇᴅɪᴀ ᴛᴏ ᴜᴘʟᴏᴀᴅ"
        )

    media = message.reply_to_message

    file_size = 0
    if media.photo:
        file_size = media.photo.file_size
    elif media.video:
        file_size = media.video.file_size
    elif media.document:
        file_size = media.document.file_size

    if file_size > 200 * 1024 * 1024:
        return await message.reply_text(
            "❍ Pʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ғɪʟᴇ ᴜɴᴅᴇʀ 200MB."
        )

    text = await message.reply("❍ ᴘʀᴏᴄᴇssɪɴɢ...")

    async def progress(current, total):
        try:
            percent = current * 100 / total
            await text.edit_text(f"❍ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ... {percent:.1f}%")
        except:
            pass

    try:
        local_path = await media.download(progress=progress)

        await text.edit_text("❍ ᴜᴘʟᴏᴀᴅɪɴɢ...")

        success, upload_path = upload_catbox(local_path)

        if success:
            await text.edit_text(
                f"❍ | [ᴛᴀᴘ ᴛʜᴇ ʟɪɴᴋ]({upload_path})",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❍ ᴄʀᴇᴀᴛᴇ ʙʏ HEARTBEAT ™", url=upload_path)]]
                ),
            )
        else:
            await text.edit_text(
                f"❍ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ\n\n❍ {upload_path}"
            )

    except Exception as e:
        await text.edit_text(
            f"❍ ғɪʟᴇ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ\n\n❍ <i>ʀᴇᴀsᴏɴ: {e}</i>"
        )

    finally:
        try:
            os.remove(local_path)
        except:
            pass


# ================= IMGBB COMMAND =================
@app.on_message(filters.command(["imbb"]))
async def imgbb_upload(client, message):

    if not message.reply_to_message:
        return await message.reply_text(
            "❍ ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ ᴛᴏ ᴜᴘʟᴏᴀᴅ"
        )

    media = message.reply_to_message

    if not media.photo:
        return await message.reply_text(
            "❍ ᴘʟᴇᴀsᴇ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴘʜᴏᴛᴏ."
        )

    text = await message.reply("❍ ᴘʀᴏᴄᴇssɪɴɢ...")

    async def progress(current, total):
        try:
            percent = current * 100 / total
            await text.edit_text(f"❍ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ... {percent:.1f}%")
        except:
            pass

    try:
        local_path = await media.download(progress=progress)

        await text.edit_text("❍ ᴜᴘʟᴏᴀᴅɪɴɢ ᴛᴏ ɪᴍɢʙʙ...")

        success, upload_path = upload_imgbb(local_path)

        if success:
            await text.edit_text(
                f"❍ | [ᴛᴀᴘ ᴛʜᴇ ʟɪɴᴋ]({upload_path})",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❍ ᴏᴘᴇɴ ɪᴍɢʙʙ", url=upload_path)]]
                ),
            )
        else:
            await text.edit_text(
                f"❍ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ\n\n❍ {upload_path}"
            )

    except Exception as e:
        await text.edit_text(
            f"❍ ғɪʟᴇ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ\n\n❍ <i>ʀᴇᴀsᴏɴ: {e}</i>"
        )

    finally:
        try:
            os.remove(local_path)
        except:
            pass


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_52"

__help__ = """
🔻 /imgur, /tm ➠ ᴜᴘʟᴏᴀᴅꜱ ʀᴇᴘʟɪᴇᴅ ᴘʜᴏᴛᴏ ᴏʀ ɢɪꜰ ᴛᴏ ɪᴍɢᴜʀ ᴀɴᴅ ʀᴇᴛᴜʀɴꜱ ᴀ ᴅɪʀᴇᴄᴛ ʟɪɴᴋ  
🔻 /tgm, /tgt, /telegraph, /tl ➠ ᴜᴘʟᴏᴀᴅ ʀᴇᴘʟɪᴇᴅ ᴍᴇᴅɪᴀ ᴛᴏ ᴄᴀᴛʙᴏx ᴀɴᴅ ʀᴇᴛᴜʀɴꜱ ᴀ ᴅɪʀᴇᴄᴛ ʟɪɴᴋ
🔻 /imbb ➠ ᴜᴘʟᴏᴀᴅ ʀᴇᴘʟɪᴇᴅ ᴘʜᴏᴛᴏ ᴛᴏ ɪᴍɢʙʙ
"""
