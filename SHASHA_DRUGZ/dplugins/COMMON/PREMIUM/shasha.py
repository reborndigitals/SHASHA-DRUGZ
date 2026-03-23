import re
import random
import asyncio
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from SHASHA_DRUGZ import app


###### @ghosttbatt 
@app.on_message(filters.command(["bat", "ghosttbatt", "Bat", "here", "sha", "shan", "OnixGhost"], prefixes=["@", "Ghost ", "ghost ", "ghostt", "bat ", "batt", "sha", "Sha"]))
async def goodmorning_handler(_, message):
    sender = message.from_user.mention

    # Step 1: Random emoji
    emoji = get_random_emoji()
    emoji_msg = await app.send_message(message.chat.id, emoji)

    # Step 2: Delete emoji
    await asyncio.sleep(1.2)
    try:
        await emoji_msg.delete()
    except:
        pass

    # Step 3: Random video
    video_url = get_random_video()

    # Step 4: Random caption
    caption = get_random_caption(sender)

    # Step 5: Inline buttons
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🦇 𝐏ᴍ", url="https://t.me/ghosttbatt"),
                InlineKeyboardButton("✨ 𝐊ɪɴɢᴅᴏᴍ", url="https://t.me/HeartBeat_Fam") #callback_data="close_gm")
            ]
        ]
    )

    await app.send_video(
        chat_id=message.chat.id,
        video=video_url,
        caption=caption,
        reply_markup=buttons
    )


def get_random_video():
    videos = [
        "https://files.catbox.moe/8e9vtx.mp4",
        "https://files.catbox.moe/8e9vtx.mp4",
    ]
    return random.choice(videos)


def get_random_emoji():
    emojis = ["💥", "😈", "✨", "🚀", "⚡", "🖤", "🦇", "🔥", "💫", "💞", "💌", "❤️‍🔥", "🤞🏻", "💕"]
    return random.choice(emojis)


def get_random_caption(sender):
    captions = [
        f"<blockquote>**ʜᴇʏ {sender}, ꜱᴏᴍᴇᴛɪᴍᴇꜱ ʏᴏᴜʀ ᴘʀᴇꜱᴇɴᴄᴇ ꜰᴇᴇʟꜱ ʟᴏᴜᴅᴇʀ ᴛʜᴀɴ ʏᴏᴜʀ ᴡᴏʀᴅꜱ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɴᴏᴛ ᴇᴠᴇʀʏ ᴄᴏɴɴᴇᴄᴛɪᴏɴ ɪꜱ ꜱᴘᴏᴋᴇɴ… ꜱᴏᴍᴇ ᴀʀᴇ ᴊᴜꜱᴛ ꜰᴇʟᴛ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜ ᴀᴘᴘᴇᴀʀ ꜰᴏʀ ᴀ ᴍᴏᴍᴇɴᴛ ʙᴜᴛ ꜱᴛᴀʏ ɪɴ ᴛʜᴏᴜɢʜᴛꜱ ꜰᴏʀ ʟᴏɴɢ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ᴛʜᴇ ᴡᴀʏ ʏᴏᴜ ꜱʜᴏᴡ ᴜᴘ ᴜɴᴇxᴘᴇᴄᴛᴇᴅʟʏ… ɪᴛ ʜɪᴛꜱ ᴅɪꜰꜰᴇʀᴇɴᴛ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ꜱᴏᴍᴇ ᴘᴇᴏᴘʟᴇ ᴄᴏᴍᴇ ᴀꜱ ʙʟᴇꜱꜱɪɴɢꜱ ᴡɪᴛʜᴏᴜᴛ ᴛʀʏɪɴɢ… ʏᴏᴜ’ʀᴇ ᴏɴᴇ ᴏꜰ ᴛʜᴇᴍ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜʀ ᴛᴀɢ ꜰᴇʟᴛ ꜱɪᴍᴘʟᴇ, ʙᴜᴛ ᴛʜᴇ ꜰᴇᴇʟɪɴɢ ʙᴇʜɪɴᴅ ɪᴛ ᴡᴀꜱɴ’ᴛ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ᴍᴀʏʙᴇ ʏᴏᴜ ᴅᴏɴ’ᴛ ᴋɴᴏᴡ… ʙᴜᴛ ʏᴏᴜʀ ᴘʀᴇꜱᴇɴᴄᴇ ᴡᴀʀᴍꜱ ᴍᴏʀᴇ ᴛʜᴀɴ ʏᴏᴜʀ ᴡᴏʀᴅꜱ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜʀ ɴᴀᴍᴇ ᴄᴀʀʀɪᴇꜱ ᴀ ꜰᴇᴇʟɪɴɢ ɪ ᴄᴀɴ’ᴛ ᴇxᴘʟᴀɪɴ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ᴛʜᴇ ᴡᴀʏ ʏᴏᴜ ᴄᴀʟʟ ᴍᴇ… ɪᴛ ꜰᴇᴇʟꜱ ʟɪᴋᴇ ꜱᴏᴍᴇᴛʜɪɴɢ ɪ ᴅɪᴅɴ’ᴛ ᴋɴᴏᴡ ɪ ɴᴇᴇᴅᴇᴅ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ꜱᴏᴍᴇᴛɪᴍᴇꜱ ᴀ ꜱᴍᴀʟʟ ᴛᴀɢ ᴛᴏᴜᴄʜᴇꜱ ᴛʜᴇ ʜᴇᴀʀᴛ ᴍᴏʀᴇ ᴛʜᴀɴ ʙɪɢ ᴄᴏɴᴠᴇʀꜱᴀᴛɪᴏɴꜱ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ꜰᴜɴɴʏ ʜᴏᴡ ʏᴏᴜʀ ᴛᴀɢ ᴍᴀᴋᴇꜱ ᴍᴇ ꜱᴍɪʟᴇ ᴀɴᴅ ᴏᴠᴇʀᴛʜɪɴᴋ ᴀᴛ ᴛʜᴇ ꜱᴀᴍᴇ ᴛɪᴍᴇ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪ ᴅᴏɴ’ᴛ ᴋɴᴏᴡ ɪꜰ ɪ ꜱʜᴏᴜʟᴅ ɪɢɴᴏʀᴇ ʏᴏᴜ ᴏʀ ꜰᴇᴇʟ ꜱᴏᴍᴇᴛʜɪɴɢ… ʙᴜᴛ ʜᴇʀᴇ ɪ ᴀᴍ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜʀ ᴘʀᴇꜱᴇɴᴄᴇ ꜰᴇᴇʟꜱ ʀɪɢʜᴛ… ʙᴜᴛ ᴛʜᴇ ᴛɪᴍɪɴɢ ɴᴇᴠᴇʀ ᴅᴏᴇꜱ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜ ꜱʜᴏᴡ ᴜᴘ ʟɪᴋᴇ ᴀ ᴄᴏᴍꜰᴏʀᴛ ᴀɴᴅ ᴀ ᴄʜᴀᴏꜱ ᴛᴏɢᴇᴛʜᴇʀ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪ ᴅᴏɴ’ᴛ ᴋɴᴏᴡ ᴡʜᴇᴛʜᴇʀ ᴛᴏ ᴘᴜꜱʜ ʏᴏᴜ ᴀᴡᴀʏ ᴏʀ ᴘᴜʟʟ ʏᴏᴜ ᴄʟᴏꜱᴇʀ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜ ᴄᴏɴꜰᴜꜱᴇ ᴍʏ ʜᴇᴀʀᴛ ᴀɴᴅ ᴄᴀʟᴍ ɪᴛ ᴀᴛ ᴛʜᴇ ꜱᴀᴍᴇ ᴛɪᴍᴇ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪ ᴀᴄᴛ ᴄᴀʀᴇʟᴇꜱꜱ, ʙᴜᴛ ʏᴏᴜʀ ᴛᴀɢ ꜱᴛɪʟʟ ʜɪᴛꜱ ꜱᴏᴍᴇᴡʜᴇʀᴇ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪ ᴡɪꜱʜ ʏᴏᴜʀ ɪɴᴛᴇɴᴛɪᴏɴꜱ ᴡᴇʀᴇ ᴀꜱ ᴄʟᴇᴀʀ ᴀꜱ ʏᴏᴜʀ ɴᴀᴍᴇ ᴏɴ ᴍʏ ꜱᴄʀᴇᴇɴ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪ ᴘʀᴇᴛᴇɴᴅ ɪ ᴅᴏɴ’ᴛ ᴄᴀʀᴇ… ʙᴜᴛ ᴛʜᴀᴛ ᴛᴀɢ ᴅɪᴅɴ’ᴛ ɢᴏ ᴜɴɴᴏᴛɪᴄᴇᴅ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ꜱᴏᴍᴇ ᴅᴀʏꜱ ʏᴏᴜ ꜰᴇᴇʟ ʟɪᴋᴇ ᴀ ʜᴀʙɪᴛ, ꜱᴏᴍᴇ ᴅᴀʏꜱ ʟɪᴋᴇ ᴀ ᴍɪꜱᴛᴀᴋᴇ… ʏᴇᴛ ɪ ʀᴇꜱᴘᴏɴᴅ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ɪᴅᴇᴀ ʜᴏᴡ ᴀ ꜱᴍᴀʟʟ ᴛᴀɢ ꜰʀᴏᴍ ʏᴏᴜ ᴄᴀɴ ꜱᴏꜰᴛᴇɴ ᴀ ᴡʜᴏʟᴇ ᴅᴀʏ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ꜱᴏᴍᴇᴛɪᴍᴇꜱ ᴛʜᴇ ᴘᴇᴏᴘʟᴇ ᴡᴇ ᴅᴏɴ’ᴛ ᴛᴀʟᴋ ᴛᴏ ᴍᴜᴄʜ ꜱᴛɪʟʟ ᴍᴀᴛᴛᴇʀ ᴛʜᴇ ᴍᴏꜱᴛ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜ ꜱʜᴏᴡᴇᴅ ᴜᴘ ꜰᴏʀ ᴀ ᴍᴏᴍᴇɴᴛ, ʙᴜᴛ ꜱᴏᴍᴇʜᴏᴡ ɪᴛ ꜰᴇʟᴛ ʟɪᴋᴇ ᴄᴏᴍꜰᴏʀᴛ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪ ᴅᴏɴ’ᴛ ᴋɴᴏᴡ ᴡʜʏ… ʙᴜᴛ ʏᴏᴜʀ ᴘʀᴇꜱᴇɴᴄᴇ ꜰᴇᴇʟꜱ ꜰᴀᴍɪʟɪᴀʀ ᴛᴏ ᴍʏ ʜᴇᴀʀᴛ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ᴛʜᴇ ᴡᴀʏ ʏᴏᴜ ᴀᴘᴘᴇᴀʀ ꜱᴜᴅᴅᴇɴʟʏ… ɪᴛ ꜰᴇᴇʟꜱ ʟɪᴋᴇ ᴛʜᴇ ᴜɴɪᴠᴇʀꜱᴇ ᴄʜᴇᴄᴋɪɴɢ ᴏɴ ᴍᴇ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ᴍᴀʏʙᴇ ʏᴏᴜ’ʀᴇ ɴᴏᴛ ᴀᴡᴀʀᴇ, ʙᴜᴛ ʏᴏᴜʀ ᴘʀᴇꜱᴇɴᴄᴇ ᴄᴀʀʀɪᴇꜱ ᴀ ᴡᴀʀᴍᴛʜ ɪ ᴀᴍɪꜱꜱ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ɪᴛ’ꜱ ꜱᴛʀᴀɴɢᴇ ʜᴏᴡ ʏᴏᴜʀ ɴᴀᴍᴇ ᴄᴀɴ ᴛʀɪɢɢᴇʀ ᴀ ꜰᴇᴇʟɪɴɢ ɪ ᴄᴀɴ’ᴛ ᴇxᴘʟᴀɪɴ…**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ꜱᴏᴍᴇᴛɪᴍᴇꜱ ᴀ ꜱᴍᴀʟʟ ᴍᴏᴍᴇɴᴛ ᴡɪᴛʜ ᴛʜᴇ ʀɪɢʜᴛ ᴘᴇʀꜱᴏɴ ꜰᴇᴇʟꜱ ʙɪɢɢᴇʀ ᴛʜᴀɴ ᴀ ᴡʜᴏʟᴇ ᴅᴀʏ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜʀ ᴛᴀɢ ꜰᴇʟᴛ ꜱɪᴍᴘʟᴇ… ʙᴜᴛ ᴛʜᴇ ᴇᴍᴏᴛɪᴏɴ ʙᴇʜɪɴᴅ ɪᴛ ᴡᴀꜱɴ’ᴛ.**</blockquote>",
    f"<blockquote>**ʜᴇʏ {sender}, ʏᴏᴜ ᴛᴏᴜᴄʜᴇᴅ ᴀ ᴘʟᴀᴄᴇ ɪɴ ᴍʏ ʜᴇᴀʀᴛ ᴛʜᴀᴛ ɪ ᴅɪᴅɴ’ᴛ ᴇᴠᴇɴ ᴋɴᴏᴡ ɴᴇᴇᴅᴇᴅ ʜᴇᴀʟɪɴɢ.**</blockquote>",
]
    return random.choice(captions)


# Close Button Handler
@app.on_callback_query(filters.regex("close_gm"))
async def close_gm_btn(_, query):
    try:
        await query.message.delete()
    except:
        pass
    await query.answer()
