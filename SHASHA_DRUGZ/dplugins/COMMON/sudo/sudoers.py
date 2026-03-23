# sudoers.py

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import add_sudo, remove_sudo
from SHASHA_DRUGZ.utils.decorators.language import language
from SHASHA_DRUGZ.utils.extraction import extract_user
from SHASHA_DRUGZ.utils.inline import close_markup
from config import BANNED_USERS, OWNER_ID

# Define your command prefixes
PREFIXES = ["/", "!", "%", ",", "", ".", "@", "#"]

@Client.on_message(filters.command(["addsudo"], prefixes=PREFIXES) & filters.user(OWNER_ID))
@language
async def useradd(client, message: Message, _):
    if not message.reply_to_message:
        if len(message.command) != 2:
            return await message.reply_text(_["general_1"])
    
    user = await extract_user(message)
    if not user:
        return await message.reply_text("❌ Could not extract user info.")

    if user.id in SUDOERS:
        return await message.reply_text(_["sudo_1"].format(user.mention))
    
    added = await add_sudo(user.id)
    if added:
        SUDOERS.add(user.id)
        await message.reply_text(_["sudo_2"].format(user.mention))
    else:
        await message.reply_text(_["sudo_8"])


@Client.on_message(filters.command(["delsudo", "rmsudo"], prefixes=PREFIXES) & filters.user(OWNER_ID))
@language
async def userdel(client, message: Message, _):
    if not message.reply_to_message:
        if len(message.command) != 2:
            return await message.reply_text(_["general_1"])
    
    user = await extract_user(message)
    if not user:
        return await message.reply_text("❌ Could not extract user info.")

    if user.id not in SUDOERS:
        return await message.reply_text(_["sudo_3"].format(user.mention))
    
    removed = await remove_sudo(user.id)
    if removed:
        SUDOERS.discard(user.id)
        await message.reply_text(_["sudo_4"].format(user.mention))
    else:
        await message.reply_text(_["sudo_8"])


@Client.on_message(filters.command(["deleteallsudo", "delallsudo", "removeallsudo"], prefixes=PREFIXES) & filters.user(OWNER_ID))
@language
async def delete_all_sudoers(client, message: Message, _):
    # Calculate count excluding Owner
    sudo_count = len([uid for uid in SUDOERS if uid != OWNER_ID])
    
    if sudo_count == 0:
        return await message.reply_text("❌ <b>No sudoers found to delete!</b>")
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Delete All", callback_data="confirm_delete_all_sudo"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete_all_sudo")
        ]
    ])
    
    await message.reply_text(
        f"⚠️ <b>Warning!</b>\n\n"
        f"Are you sure you want to delete all <code>{sudo_count}</code> sudoers?\n"
        f"<i>This action cannot be undone!</i>",
        reply_markup=keyboard
    )


@Client.on_message(filters.command(["sudolist", "listsudo", "sudoers"], prefixes=PREFIXES) & ~BANNED_USERS)
@language
async def sudoers_list(client, message: Message, _):
    text = _["sudo_5"]
    
    # 1. Handle Owner
    try:
        owner = await app.get_users(OWNER_ID)
        owner_name = owner.first_name if not owner.mention else owner.mention
        text += f"1➤ {owner_name} <code>{OWNER_ID}</code>\n"
    except:
        text += f"1➤ Owner <code>{OWNER_ID}</code>\n"
    
    # 2. Handle Sudoers (Batch Fetching for Speed)
    sudoers_ids = [uid for uid in SUDOERS if uid != OWNER_ID]
    
    if not sudoers_ids:
        text += "\n<b>No sudoers found.</b>"
        return await message.reply_text(text, reply_markup=close_markup(_))

    text += _["sudo_6"]
    
    try:
        # Fetch ALL users in ONE call (Prevents FloodWait)
        users = await app.get_users(sudoers_ids)
        
        # Determine if result is a list or single object
        if not isinstance(users, list):
            users = [users]

        for i, user in enumerate(users):
            user_name = user.first_name if not user.mention else user.mention
            text += f"{i + 2}➤ {user_name} <code>{user.id}</code>\n"
            
    except Exception:
        # Fallback if batch fetch fails
        for i, user_id in enumerate(sudoers_ids):
            text += f"{i + 2}➤ User <code>{user_id}</code>\n"

    await message.reply_text(text, reply_markup=close_markup(_))


# --- Callback Handlers ---

@Client.on_callback_query(filters.regex("confirm_delete_all_sudo"))
async def confirm_delete_all_sudoers(client, callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        return await callback_query.answer("❌ Only owner can do this!", show_alert=True)
    
    deleted_count = 0
    sudoers_to_remove = [user_id for user_id in SUDOERS.copy() if user_id != OWNER_ID]
    
    for user_id in sudoers_to_remove:
        try:
            removed = await remove_sudo(user_id)
            if removed:
                SUDOERS.discard(user_id)
                deleted_count += 1
        except:
            continue
    
    await callback_query.message.edit_text(
        f"✅ <b>Successfully deleted sudoers!</b>\n\n"
        f"📊 <b>Deleted:</b> <code>{deleted_count}</code> users\n"
        f"🛡️ <b>Protected:</b> Owner remains safe"
    )

@Client.on_callback_query(filters.regex("cancel_delete_all_sudo"))
async def cancel_delete_all_sudoers(client, callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
         return await callback_query.answer("❌ Only owner can do this!", show_alert=True)
    await callback_query.message.edit_text("❌ <b>Cancelled!</b>\n\nNo sudoers were deleted.")


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_25"
__help__ = """
🔻 /addsudo <reply to user or user_id> ➠ ᴀᴅᴅ ᴀ ᴜsᴇʀ ᴀs sᴜᴅᴏᴇʀ  
🔻 /delsudo or /rmsudo <reply to user or user_id> ➠ ʀᴇᴍᴏᴠᴇ ᴀ sᴜᴅᴏᴇʀ
🔻 /deleteallsudo or /delallsudo or /removeallsudo ➠ ᴅᴇʟᴇᴛᴇ ᴀʟʟ sᴜᴅᴏᴇʀs 
🔻 /sudolist or /listsudo or /sudoers ➠ ʟɪsᴛ ᴀʟʟ sᴜᴅᴏᴇʀs ɪɴ ᴛʜᴇ ʙᴏᴛ
"""
MOD_TYPE = "SUDO"
MOD_NAME = "Sudoers"
MOD_PRICE = "50"
