import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMembersFilter
from pyrogram.errors import FloodWait

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import (
    get_active_chats,
    get_authuser_names,
    get_client,
    get_served_chats,
    get_served_users,
)
from SHASHA_DRUGZ.utils.decorators.language import language
from SHASHA_DRUGZ.utils.formatters import alpha_to_int
from config import adminlist

# ==========================================
# BROADCAST ALLOWED USERS
# ==========================================
BROADCAST_ID = [
    1281282633,
    6773435708,
]

IS_BROADCASTING = False

# ==========================================
# BROADCAST HANDLER
# ==========================================
@Client.on_message(filters.command(["broadcast", "gcast"]) & (filters.user(BROADCAST_ID) | SUDOERS))
@language
async def broadcast_message(client, message, _):
    global IS_BROADCASTING
    
    if IS_BROADCASTING:
        return await message.reply_text("⚠️ **A broadcast is already running.** Please wait for it to complete.")
    
    # ---------- DETERMINE BROADCAST TARGETS ----------
    text = message.text
    broadcast_to_chats = "-chat" in text or "-wfchat" in text
    broadcast_to_users = "-user" in text or "-wfuser" in text
    broadcast_to_assistant = "-assistant" in text
    pin_message = "-pin" in text
    pin_loud = "-pinloud" in text
    forward_mode = "-forward" in text
    no_bot = "-nobot" in text
    
    # Default: broadcast to both chats and users if no specific flag
    if not broadcast_to_chats and not broadcast_to_users and not broadcast_to_assistant:
        broadcast_to_chats = True
        broadcast_to_users = True
    
    # ---------- PREPARE CONTENT ----------
    if message.reply_to_message:
        reply = message.reply_to_message
        reply_id = reply.id
        chat_id = message.chat.id
        reply_markup = reply.reply_markup
        content_is_reply = True
    else:
        if len(message.command) < 2:
            return await message.reply_text(_["broad_2"])
        
        # Clean the message text by removing flags
        raw_text = message.text.split(None, 1)[1]
        flags_to_remove = [
            "-chat", "-wfchat", "-user", "-wfuser", "-assistant",
            "-pin", "-pinloud", "-forward", "-nobot"
        ]
        for flag in flags_to_remove:
            raw_text = raw_text.replace(flag, "")
        clean_text = raw_text.strip()
        
        if not clean_text:
            return await message.reply_text(_["broad_8"])
        
        content_is_reply = False
    
    IS_BROADCASTING = True
    progress_msg = await message.reply_text("🚀 **Broadcast started...**")
    
    # Stats tracking
    total_sent_chats = 0
    total_sent_users = 0
    total_pinned = 0
    
    # =====================================
    # BROADCAST TO CHATS (GROUPS)
    # =====================================
    if broadcast_to_chats and not no_bot:
        chats = [int(chat["chat_id"]) for chat in await get_served_chats()]
        total_chats = len(chats)
        
        if total_chats > 0:
            await progress_msg.edit_text(
                f"📢 **Broadcasting to Chats**\n\n"
                f"📊 Total Chats: `{total_chats}`\n"
                f"⏳ Progress: `0/{total_chats}`"
            )
            
            for i, chat_id in enumerate(chats, 1):
                try:
                    if content_is_reply:
                        if forward_mode:
                            sent_msg = await app.forward_messages(chat_id, chat_id, reply_id)
                        else:
                            sent_msg = await app.copy_message(
                                chat_id, chat_id, reply_id,
                                reply_markup=reply_markup
                            )
                    else:
                        sent_msg = await app.send_message(chat_id, text=clean_text)
                    
                    total_sent_chats += 1
                    
                    # Pin message if requested
                    if pin_message or pin_loud:
                        try:
                            await sent_msg.pin(disable_notification=(not pin_loud))
                            total_pinned += 1
                        except:
                            pass
                    
                    # Update progress every 25 messages
                    if i % 25 == 0:
                        await progress_msg.edit_text(
                            f"📢 **Broadcasting to Chats**\n\n"
                            f"📊 Total: `{total_chats}`\n"
                            f"✅ Sent: `{i}`\n"
                            f"📌 Pinned: `{total_pinned}`"
                        )
                    
                    await asyncio.sleep(0.2)
                    
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except:
                    continue
    
    # =====================================
    # BROADCAST TO USERS (BOT PM)
    # =====================================
    if broadcast_to_users:
        users = [int(user["user_id"]) for user in await get_served_users()]
        total_users = len(users)
        
        if total_users > 0:
            target = "Users" if broadcast_to_chats else "Users"
            await progress_msg.edit_text(
                f"👤 **Broadcasting to {target}**\n\n"
                f"📊 Total: `{total_users}`\n"
                f"⏳ Progress: `0/{total_users}`"
            )
            
            for i, user_id in enumerate(users, 1):
                try:
                    if content_is_reply:
                        if forward_mode:
                            await app.forward_messages(user_id, chat_id, reply_id)
                        else:
                            await app.copy_message(
                                user_id, chat_id, reply_id,
                                reply_markup=reply_markup
                            )
                    else:
                        await app.send_message(user_id, text=clean_text)
                    
                    total_sent_users += 1
                    
                    # Update progress every 25 messages
                    if i % 25 == 0:
                        await progress_msg.edit_text(
                            f"👤 **Broadcasting to {target}**\n\n"
                            f"📊 Total: `{total_users}`\n"
                            f"✅ Sent: `{i}`"
                        )
                    
                    await asyncio.sleep(0.2)
                    
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except:
                    continue
    
    # =====================================
    # BROADCAST TO ASSISTANT CHATS
    # =====================================
    if broadcast_to_assistant:
        from SHASHA_DRUGZ.core.userbot import assistants
        
        assistant_report = "🤖 **Assistant Broadcast Report**\n\n"
        
        for num in assistants:
            client = await get_client(num)
            assistant_sent = 0
            
            async for dialog in client.get_dialogs():
                try:
                    if content_is_reply:
                        await client.forward_messages(dialog.chat.id, chat_id, reply_id)
                    else:
                        await client.send_message(dialog.chat.id, text=clean_text)
                    
                    assistant_sent += 1
                    await asyncio.sleep(3)
                    
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except:
                    continue
            
            assistant_report += f"• Assistant `{num}` ➠ `{assistant_sent}` chats\n"
        
        await progress_msg.edit_text(assistant_report)
        IS_BROADCASTING = False
        return
    
    # =====================================
    # FINAL REPORT
    # =====================================
    report = "✅ **Broadcast Completed!**\n\n"
    
    if broadcast_to_chats and not no_bot:
        report += f"📢 **Chats:** `{total_sent_chats}` / `{len(await get_served_chats())}`\n"
        if pin_message or pin_loud:
            report += f"📌 **Pinned:** `{total_pinned}`\n"
    
    if broadcast_to_users:
        report += f"👤 **Users:** `{total_sent_users}` / `{len(await get_served_users())}`\n"
    
    await progress_msg.edit_text(report)
    IS_BROADCASTING = False


# ==========================================
# AUTO CLEAN ADMINLIST
# ==========================================
async def auto_clean():
    while not await asyncio.sleep(10):
        try:
            served_chats = await get_active_chats()
            for chat_id in served_chats:
                if chat_id not in adminlist:
                    adminlist[chat_id] = []
                    async for user in app.get_chat_members(
                        chat_id, filter=ChatMembersFilter.ADMINISTRATORS
                    ):
                        if user.privileges.can_manage_video_chats:
                            adminlist[chat_id].append(user.user.id)
                    authusers = await get_authuser_names(chat_id)
                    for user in authusers:
                        user_id = await alpha_to_int(user)
                        adminlist[chat_id].append(user_id)
        except:
            continue


asyncio.create_task(auto_clean())

# ==========================================
# HELP TEXT
# ==========================================
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_21"
__help__ = """
🔻 /broadcast or /gcast ➠ ʙʀᴏᴀᴅᴄᴀsᴛ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴀʟʟ ɢʀᴏᴜᴘs ᴀɴᴅ ᴜsᴇʀs ᴛʜᴀᴛ ʙᴏᴛ ɪs sᴇʀᴠɪɴɢ

⚡ Usage:
   • ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ: `/broadcast -chat -user`
   • ᴏʀ ᴜsᴇ ᴛᴇxᴛ: `/broadcast Your message here -chat -user -pin`

🛠 Flags:
   • `-chat` ➠ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ ɢʀᴏᴜᴘs
   • `-user` ➠ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ ᴜsᴇʀs (PM)
   • `-assistant` ➠ ʙʀᴏᴀᴅᴄᴀsᴛ ᴠɪᴀ ᴀssɪsᴛᴀɴᴛs
   • `-pin` ➠ ᴘɪɴ ᴛʜᴇ ᴍᴇssᴀɢᴇ ɪɴ ɢʀᴏᴜᴘs
   • `-pinloud` ➠ ᴘɪɴ ᴡɪᴛʜ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ
   • `-forward` ➠ ғᴏʀᴡᴀʀᴅ ᴍᴇssᴀɢᴇ ɪɴsᴛᴇᴀᴅ ᴏғ ᴄᴏᴘʏ
   • `-nobot` ➠ ᴅᴏɴ'ᴛ sᴇɴᴅ ᴛᴏ ʙᴏᴛ ɢʀᴏᴜᴘs

📌 Notes:
   • ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴀʏ ᴛᴀᴋᴇ sᴏᴍᴇ ᴛɪᴍᴇ ɪғ ʙᴏᴛ ɪs ɪɴ ʟᴏᴛs ᴏғ ᴄʜᴀᴛs/ᴜsᴇʀs
   • ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ʙʀᴏᴀᴅᴄᴀsᴛs ᴡɪʟʟ ʙᴇ ᴘʀᴇᴠᴇɴᴛᴇᴅ
"""

MOD_TYPE = "TOOLS"
MOD_NAME = "Broadcast"
MOD_PRICE = "50"
