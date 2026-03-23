import requests
from requests import get 
from SHASHA_DRUGZ import app
from pyrogram import filters
from pyrogram.types import InputMediaPhoto

print("[tringtring] image")

@app.on_message(filters.command(["image"], prefixes=["/", "!", "%", ",", "", ".", "@", "#"]))
async def pinterest(_, message):
     chat_id = message.chat.id

     try:
       query= message.text.split(None,1)[1]
     except:
         return await message.reply("**ɢɪᴠᴇ ɪᴍᴀɢᴇ ɴᴀᴍᴇ ғᴏʀ sᴇᴀʀᴄʜ 🔍**")

     images = get(f"https://pinterest-api-one.vercel.app/?q={query}").json()

     media_group = []
     count = 0

     msg = await message.reply(f"sᴄʀᴀᴘɪɴɢ ɪᴍᴀɢᴇs ғʀᴏᴍ ᴘɪɴᴛᴇʀᴇᴛs...")
     for url in images["images"][:6]:
                  
          media_group.append(InputMediaPhoto(media=url))
          count += 1
          await msg.edit(f"=> ᴏᴡᴏ sᴄʀᴀᴘᴇᴅ ɪᴍᴀɢᴇs {count}")

     try:
        
        await app.send_media_group(
                chat_id=chat_id, 
                media=media_group,
                reply_to_message_id=message.id)
        return await msg.delete()

     except Exception as e:
           await msg.delete()
           return await message.reply(f"ᴇʀʀᴏʀ : {e}")

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_58"
__help__ = """
🔻 /image ➠ ʀᴇᴘʟʏ ᴏʀ ᴘʀᴏᴠɪᴅᴇ ᴀ ɴᴀᴍᴇ ᴛᴏ sᴇᴀʀᴄʜ ᴀɴᴅ ᴘᴏsᴛ ɪᴍᴀɢᴇs ғʀᴏᴍ ᴘɪɴᴛᴇʀᴇsᴛ
"""
