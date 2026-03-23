# SHASHA_DRUGZ/modules/zombies.py
import asyncio
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait
from SHASHA_DRUGZ import app

print("[zombies] deleted accounts module loaded")

chatQueue = []
stopProcess = False

# ------------------------------------------------------------------------------- #

@app.on_message(filters.command(["zombies", "Deletedaccounts"]))
async def remove_deleted_accounts(client, message):
    global stopProcess
    try:
        # Check sender privileges
        try:
            sender = await app.get_chat_member(message.chat.id, message.from_user.id)
            has_permissions = sender.privileges
        except:
            has_permissions = message.sender_chat

        if has_permissions:
            bot = await app.get_chat_member(message.chat.id, "self")
            if bot.status == ChatMemberStatus.MEMBER:
                await message.reply("➠ | ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs.")
                return
            else:
                if len(chatQueue) > 30:
                    await message.reply(
                        "➠ | ɪ'ᴍ ᴀʟʀᴇᴀᴅʏ ᴡᴏʀᴋɪɴɢ ᴏɴ ᴍᴀx 30 ᴄʜᴀᴛs. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ sʜᴏʀᴛʟʏ."
                    )
                    return
                if message.chat.id in chatQueue:
                    await message.reply(
                        "➠ | ᴛʜᴇʀᴇ's ᴀɴ ᴏɴɢᴏɪɴɢ ᴘʀᴏᴄᴇss ɪɴ ᴛʜɪs ᴄʜᴀᴛ. ᴜsᴇ /stop ᴛᴏ ʀᴇsᴇᴛ."
                    )
                    return

                chatQueue.append(message.chat.id)
                deletedList = [
                    member.user async for member in app.get_chat_members(message.chat.id)
                    if member.user.is_deleted
                ]
                lenDeletedList = len(deletedList)

                if lenDeletedList == 0:
                    await message.reply("⟳ | ɴᴏ ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs ɪɴ ᴛʜɪs ᴄʜᴀᴛ.")
                    chatQueue.remove(message.chat.id)
                    return

                k = 0
                processTime = lenDeletedList * 1
                temp = await app.send_message(
                    message.chat.id,
                    f"🧭 | ᴛᴏᴛᴀʟ ᴏғ {lenDeletedList} ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs ʙᴇɪɴɢ ʀᴇᴍᴏᴠᴇᴅ.\n🥀 | ᴇsᴛɪᴍᴀᴛᴇᴅ ᴛɪᴍᴇ: {processTime} sᴇᴄ."
                )

                if stopProcess: stopProcess = False

                while len(deletedList) > 0 and not stopProcess:
                    deletedAccount = deletedList.pop(0)
                    try:
                        await app.ban_chat_member(message.chat.id, deletedAccount.id)
                    except Exception:
                        pass
                    k += 1
                    await asyncio.sleep(10)

                if k == lenDeletedList:
                    await message.reply(f"✅ | sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ ᴀʟʟ ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs.")
                else:
                    await message.reply(f"✅ | sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ {k} ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs.")
                await temp.delete()
                chatQueue.remove(message.chat.id)

        else:
            await message.reply("👮🏻 | sᴏʀʀʏ, ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.")

    except FloodWait as e:
        await asyncio.sleep(e.value)
                          
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_63"
__help__ = """
🔻 /zombies ➠ ʀᴇᴍᴏᴠᴇ ᴀʟʟ ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs ғʀᴏᴍ ᴛʜᴇ ɢʀᴏᴜᴘ.  
🔻 /deletedaccounts ➠ ᴅᴏ ᴛʜᴇ sᴀᴍᴇ ᴀs /zombies, ʀᴇᴍᴏᴠɪɴɢ ᴅᴇʟᴇᴛᴇᴅ ᴀᴄᴄᴏᴜɴᴛs.   
"""
