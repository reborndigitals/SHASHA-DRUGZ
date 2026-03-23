
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPermissions
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, ChatWriteForbidden
from pyrogram.enums import ChatMembersFilter, ChatMemberStatus
from pymongo import MongoClient

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import MONGO_DB_URI

# --- Database Connection ---
fsubdb = MongoClient(MONGO_DB_URI)
forcesub_collection = fsubdb.status_db.status


@app.on_message(filters.command(["fsub", "forcesub"]) & filters.group)
async def set_forcesub(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    member = await client.get_chat_member(chat_id, user_id)
    
    # 1. Check Permissions (Owner/Admin/Sudo only)
    if not (member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR] or user_id in SUDOERS):
        return await message.reply_text("🚫 **Only Group Admins or Sudoers can use this command.**")

    # 2. Handle Disable Command
    if len(message.command) == 2 and message.command[1].lower() in ["off", "disable"]:
        forcesub_collection.delete_one({"chat_id": chat_id})
        return await message.reply_text("✅ **Force subscription has been disabled for this group.**")

    # 3. Usage Help
    if len(message.command) != 2:
        return await message.reply_text("ℹ️ **Usage:**\n`/fsub <channel username/id>` to enable.\n`/fsub off` to disable.")

    channel_input = message.command[1]

    try:
        channel_info = await client.get_chat(channel_input)
        
        # 4. Check if Bot is Admin in the Target Channel
        bot_member = await channel_info.get_member(client.me.id)
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            return await message.reply_text(
                "⚠️ **I am not an admin in that channel!**\n\n"
                "Please make me an admin in the channel first, then try this command again."
            )

        channel_id = channel_info.id
        channel_username = channel_info.username

        # 5. Save to Database
        forcesub_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"channel_id": channel_id, "channel_username": channel_username}},
            upsert=True
        )

        await message.reply_text(
            f"🎉 **Force Subscription Enabled!**\n\n"
            f"**Channel:** [{channel_info.title}](https://t.me/{channel_username})\n"
            f"**Note:** Non-subscribers will be muted or their messages deleted."
        )

    except Exception as e:
        await message.reply_text(f"🚫 **Failed to set force subscription.**\nError: `{e}`")


@app.on_chat_member_updated()
async def on_user_join(client: Client, chat_member_updated):
    # Triggers when a user joins/leaves the GROUP
    chat_id = chat_member_updated.chat.id
    
    # Skip if not a group
    if not chat_member_updated.chat.type.name in ["SUPERGROUP", "GROUP", "CHANNEL"]: 
        return

    forcesub_data = forcesub_collection.find_one({"chat_id": chat_id})
    if not forcesub_data:
        return 

    channel_id = forcesub_data["channel_id"]
    channel_username = forcesub_data["channel_username"]
    new_member = chat_member_updated.new_chat_member

    if not new_member or new_member.user.is_bot:
        return

    # If User JOINED
    if new_member.status == ChatMemberStatus.MEMBER:
        user_id = new_member.user.id
        
        # Check if user is Admin/Sudo (Bypass)
        if user_id in SUDOERS:
            return

        try:
            # Check Channel Membership
            await client.get_chat_member(channel_id, user_id)
        except UserNotParticipant:
            # Mute the user
            try:
                await client.restrict_chat_member(
                    chat_id,
                    user_id,
                    permissions=ChatPermissions(can_send_messages=False)
                )
                button = InlineKeyboardMarkup([[InlineKeyboardButton("๏ Unmute Me ๏", callback_data=f"check_fsub_{user_id}")]])
                await client.send_message(
                    chat_id,
                    f"🚫 {new_member.user.mention}, **you have been muted!**\n\n"
                    f"Please join [Our Channel](https://t.me/{channel_username}) to speak here.",
                    reply_markup=button,
                    disable_web_page_preview=True
                )
            except Exception:
                pass 


@app.on_callback_query(filters.regex(r"check_fsub_(\d+)"))
async def check_fsub_callback(client: Client, callback_query: CallbackQuery):
    user_id = int(callback_query.matches[0].group(1))
    
    # Only the muted user can click
    if callback_query.from_user.id != user_id:
        return await callback_query.answer("⚠️ This is not for you!", show_alert=True)

    chat_id = callback_query.message.chat.id
    forcesub_data = forcesub_collection.find_one({"chat_id": chat_id})
    
    if not forcesub_data:
        await callback_query.answer("✅ Force sub is disabled.", show_alert=True)
        return await callback_query.message.delete()

    channel_id = forcesub_data["channel_id"]

    try:
        await client.get_chat_member(channel_id, user_id)
        # Unmute User
        await client.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await callback_query.answer("🎉 You are unmuted!")
        await callback_query.message.delete()
        
    except UserNotParticipant:
        await callback_query.answer("❌ You still haven't joined the channel!", show_alert=True)
    except Exception as e:
        await callback_query.answer(f"Error: {e}", show_alert=True)


async def check_forcesub(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Bypass for Sudoers/Admins
    if user_id in SUDOERS:
        return True
    
    # Check if user is Admin in the group
    member = await client.get_chat_member(chat_id, user_id)
    if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
        return True

    forcesub_data = forcesub_collection.find_one({"chat_id": chat_id})
    if not forcesub_data:
        return True

    channel_id = forcesub_data["channel_id"]
    channel_username = forcesub_data["channel_username"]
    channel_url = f"https://t.me/{channel_username}" if channel_username else await client.export_chat_invite_link(channel_id)

    try:
        await client.get_chat_member(channel_id, user_id)
        return True
    except UserNotParticipant:
        # User is NOT in channel
        try:
            await message.delete() # Delete their message
        except:
            pass # Bot might lack delete permissions

        msg = await message.reply_photo(
            photo="https://envs.sh/Tn_.jpg",
            caption=f"👋 **Hello {message.from_user.mention},**\n\nYou must join [This Channel]({channel_url}) to send messages here.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("๏ Join Channel ๏", url=channel_url)]])
        )
        # Delete warning after 5 seconds to keep chat clean
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return False

    except ChatAdminRequired:
        # Bot lost admin in the channel
        forcesub_collection.delete_one({"chat_id": chat_id})
        await message.reply_text("🚫 **Force Sub Disabled:** I am no longer an admin in the channel.")
        return True
    except Exception:
        return True

@app.on_message(filters.group & ~filters.bot & ~filters.service, group=30)
async def enforce_forcesub(client: Client, message: Message):
    # If check_forcesub returns False, stop other handlers
    if not await check_forcesub(client, message):
        message.stop_propagation()


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_42"
__help__ = """
🔻 /fsub <channel_username | channel_id> ➠ ᴇɴᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /forcesub <channel_username | channel_id> ➠ ᴇɴᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /fsub off ➠ ᴅɪꜱᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /forcesub off ➠ ᴅɪꜱᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /fsub disable ➠ ᴛᴜʀɴꜱ ᴏꜰꜰ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴇᴀᴛᴜʀᴇ.
🔻 /forcesub disable ➠ ᴛᴜʀɴꜱ ᴏꜰꜰ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴇᴀᴛᴜʀᴇ.
🔻 (ᴀᴜᴛᴏ) ➠ ᴍᴜᴛᴇꜱ ᴜꜱᴇʀꜱ ᴡʜᴏ ᴊᴏɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ ᴡɪᴛʜᴏᴜᴛ ᴊᴏɪɴɪɴɢ ᴛʜᴇ ꜱᴇᴛ ᴄʜᴀɴɴᴇʟ.
🔻 (ᴀᴜᴛᴏ) ➠ ᴅᴇʟᴇᴛᴇꜱ ᴍᴇꜱꜱᴀɢᴇꜱ ꜰʀᴏᴍ ɴᴏɴ-ꜱᴜʙꜱᴄʀɪʙᴇᴅ ᴜꜱᴇʀꜱ.
🔻 (ʙᴜᴛᴛᴏɴ) ➠ “ᴜɴᴍᴜᴛᴇ ᴍᴇ” — ᴠᴇʀɪꜰɪᴇꜱ ᴄʜᴀɴɴᴇʟ ᴊᴏɪɴ ᴀɴᴅ ᴜɴᴍᴜᴛᴇꜱ ᴛʜᴇ ᴜꜱᴇʀ.
🔻 (ᴀᴜᴛᴏ) ➠ ꜱᴜᴅᴏᴇʀꜱ & ɢʀᴏᴜᴘ ᴀᴅᴍɪɴꜱ ᴀʀᴇ ᴇxᴇᴍᴘᴛ ꜰʀᴏᴍ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ.
"""
