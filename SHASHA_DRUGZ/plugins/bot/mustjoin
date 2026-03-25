from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, ChatWriteForbidden
from SHASHA_DRUGZ import app
from config import MUST_JOIN

#--------------------------

#MUST_JOIN = "HeartBeat_Fam"
#------------------------
@app.on_message(filters.incoming & filters.private, group=-1)
async def must_join_channel(app: Client, msg: Message):
    if not MUST_JOIN:
        return
    try:
        try:
            await app.get_chat_member(MUST_JOIN, msg.from_user.id)
        except UserNotParticipant:
            if MUST_JOIN.isalpha():
                link = "https://t.me/" + MUST_JOIN
            else:
                chat_info = await app.get_chat(MUST_JOIN)
                link = chat_info.invite_link
            try:
                await msg.reply_photo(
                    photo="https://files.catbox.moe/qz10e1.jpg",
                    caption=f"☆ . * ● ¸ . ✦ .★　° :. ★ * • ○ ° ★\n\n┏━━━━•❅•°• - ⭕️ - •°•❅•━━━━┓\n ⊰●⊱┈─★ 𝐽𝑜𝑖𝑛 𝑈𝑠 ★─┈⊰●⊱\n\n  ᴏᴜꝛ ғᴧϻɪʟʏ\n┗━━━━•❅•°• - ⭕️ - •°•❅•━━━━┛\n\n➽───────────────❥<blockquote>[ᴊᴏɪɴ ᴍʏ ɢʀᴏᴜᴘ 1𝗌ᴛ. ᴀɴᴅ  𝗌ᴛᴀʀᴛ ᴀɢᴀɪɴ.]({link})</blockquote>☆ . * ● ¸ . ✦ .★　° :. ★ * • ○ ° ★ ",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("🔻 𝐌ʋƨт 𝐉σιи 🔻", url=link),
                            ]
                        ]
                    )
                )
                await msg.stop_propagation()
            except ChatWriteForbidden:
                pass
    except ChatAdminRequired:
        print(f"๏ᴘʀᴏᴍᴏᴛᴇ ᴍᴇ ᴀs ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴇ ᴍᴜsᴛ_Jᴏɪɴ ᴄʜᴀᴛ ๏: {MUST_JOIN} !")
