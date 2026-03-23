import os
import base64
import requests
from pyrogram import Client, filters
from SHASHA_DRUGZ import app

# Imgur Client ID (You can replace this with your own if needed)
IMGUR_CLIENT_ID = "a10ad04550b0648"

@Client.on_message(filters.command(["imgur", "tm"]))
async def imgur_upload(client, message):
    # Check if the user replied to a message
    if not message.reply_to_message:
        return await message.reply_text("Please reply to a **Photo** or **GIF** to upload it.")

    msg = await message.reply_text("`Processing...`")

    # Determine media type and download
    media = message.reply_to_message
    file_path = None

    try:
        if media.photo:
            file_path = await media.download()
        elif media.animation:
            file_path = await media.download()
        else:
            return await msg.edit_text("❌ Only **Photos** and **GIFs** are supported.")

        await msg.edit_text("`Uploading to Imgur...`")

        # Encode file to Base64
        with open(file_path, "rb") as file:
            data = file.read()
            base64_data = base64.b64encode(data)

        # Upload to Imgur API
        url = "https://api.imgur.com/3/image"
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        response = requests.post(url, headers=headers, data={"image": base64_data})
        result = response.json()

        # Handle Success
        if response.status_code == 200 and result.get("success"):
            link = result["data"]["link"]
            await msg.edit_text(
                f"✅ **Upload Successful!**\n\n🔗 **Link:** `{link}`",
                disable_web_page_preview=True
            )
        else:
            # Handle API Error
            error_message = result.get("data", {}).get("error", "Unknown Error")
            await msg.edit_text(f"❌ **Upload Failed:**\n`{error_message}`")

    except Exception as e:
        await msg.edit_text(f"❌ **Error:** `{str(e)}`")

    finally:
        # Clean up: Delete the downloaded file to save space
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_52"
__help__ = """
🔻 /imgur /tm ➠ Uploads replied **Photo or GIF** to Imgur and returns a direct link
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Imgur-Link"
MOD_PRICE = "30"
