import random
from pyrogram import Client
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Message
from config import LOGGER_ID as LOG_GROUP_ID
from SHASHA_DRUGZ import app  
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.database import delete_served_chat

photo = [
    "https://graph.org/file/f21bcb4b8b9c421409b64.png",
    "https://graph.org/file/f21bcb4b8b9c421409b64.png",
    "https://graph.org/file/f21bcb4b8b9c421409b64.png",
    "https://graph.org/file/f21bcb4b8b9c421409b64.png",
    "https://graph.org/file/f21bcb4b8b9c421409b64.png",
]

@app.on_message(filters.left_chat_member)
async def on_left_chat_member(_, message: Message):
    try:
        userbot = await get_assistant(message.chat.id)
        
        left_chat_member = message.left_chat_member
        if left_chat_member and left_chat_member.id == (await app.get_me()).id:
            remove_by = message.from_user.mention if message.from_user else "💕 𝐔𖽪𝙺𖽡𖽙𖽮 𝐔𖾗𖽞𖽷 🦋"
            title = message.chat.title
            username = f"@{message.chat.username}" if message.chat.username else "💕 𝐏𖽷𖽹ᵥ𖽖𖾓𖽞  𝐂𖽻𖽖𖾓 🦋"
            chat_id = message.chat.id
            left = f"✫ <b><u>💕 𝐋𖽞ꜰ𖾓 𝐆𖽷𖽙𖽪𖽳 🦋</u></b> ✫\n\n💕 𝐂𖽻𖽖𖾓 𝐓𖽹𖾓𖾘𖾔 🦋 {title}\n\n💕 𝐂𖽻𖽖𖾓  𝐈𖽴 🦋 {chat_id}\n\n💕 𝐑𖽞𖽧𖽙ᵥ𖾝 𝐁ʏ 🦋 {remove_by}\n\n💕 𝐁𖽙𖾓  🦋 @{app.username}"
            await app.send_photo(LOG_GROUP_ID, photo=random.choice(photo), caption=left)
            await delete_served_chat(chat_id)
            await userbot.leave_chat(chat_id)
    except Exception as e:
        print(f"Error: {e}")
    
