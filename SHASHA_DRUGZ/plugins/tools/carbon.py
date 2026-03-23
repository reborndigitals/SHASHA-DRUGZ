import aiohttp
from io import BytesIO
from SHASHA_DRUGZ import app
from pyrogram import filters

print("[carbon] carbon")

async def make_carbon(code):
    url = "https://carbonara.solopov.dev/api/cook"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"code": code}) as resp:
            image = BytesIO(await resp.read())
    image.name = "carbon.png"
    return image



@app.on_message(filters.command("carbon"))
async def _carbon(client, message):
    replied = message.reply_to_message
    if not replied:
        await message.reply_text("**ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴛᴇxᴛ ᴍᴇssᴀɢᴇ ᴛᴏ ᴍᴀᴋᴇ ᴀ ᴄᴀʀʙᴏɴ.**")
        return
    if not (replied.text or replied.caption):
        return await message.reply_text("**ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴛᴇxᴛ ᴍᴇssᴀɢᴇ ᴛᴏ ᴍᴀᴋᴇ ᴀ ᴄᴀʀʙᴏɴ.**")
    text = await message.reply("Processing...")
    carbon = await make_carbon(replied.text or replied.caption)
    await text.edit("**ᴜᴘʟᴏᴀᴅɪɴɢ...**")
    await message.reply_photo(carbon)
    await text.delete()
    carbon.close()

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_58"
__help__ = """
🔻 /carbon ➠ ᴄᴏɴᴠᴇʀᴛs ʀᴇᴘʟɪᴇᴅ ᴛᴇxᴛ ɪɴᴛᴏ ᴀ ᴄᴀʀʙᴏɴ-sᴛʏʟᴇ ᴄᴏᴅᴇ ɪᴍᴀɢᴇ
"""
