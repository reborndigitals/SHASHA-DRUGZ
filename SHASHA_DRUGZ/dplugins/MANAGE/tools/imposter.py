from pyrogram import Client, filters
from pyrogram.types import Message
from SHASHA_DRUGZ.mongo.pretenderdb import impo_off, impo_on, check_pretender, add_userdata, get_userdata, usr_data
from SHASHA_DRUGZ import app

print("[imposter] imposter")

# In-memory set to store chat IDs where imposter is explicitly disabled
disabled_chats = set()

@Client.on_message(filters.group & ~filters.bot & ~filters.via_bot, group=69)
async def chk_usr(client: Client, message: Message):
    # Skip if sender is a channel or if the chat is explicitly disabled
    if message.sender_chat or message.chat.id in disabled_chats:
        return

    # Rest of the original code unchanged
    if not await usr_data(message.from_user.id):
        return await add_userdata(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )
    usernamebefore, first_name, lastname_before = await get_userdata(message.from_user.id)
    msg = ""
    if (
        usernamebefore != message.from_user.username
        or first_name != message.from_user.first_name
        or lastname_before != message.from_user.last_name
    ):
        msg += f"""
**🔓 ᴘʀᴇᴛᴇɴᴅᴇʀ ᴅᴇᴛᴇᴄᴛᴇᴅ 🔓**
➖➖➖➖➖➖➖➖➖➖➖➖
**🍊 ɴᴀᴍᴇ** : {message.from_user.mention}
**🍅 ᴜsᴇʀ ɪᴅ** : {message.from_user.id}
➖➖➖➖➖➖➖➖➖➖➖➖\n
"""
    if usernamebefore != message.from_user.username:
        usernamebefore = f"@{usernamebefore}" if usernamebefore else "NO USERNAME"
        usernameafter = (
            f"@{message.from_user.username}"
            if message.from_user.username
            else "NO USERNAME"
        )
        msg += """
**🐻‍❄️ ᴄʜᴀɴɢᴇᴅ ᴜsᴇʀɴᴀᴍᴇ 🐻‍❄️**
➖➖➖➖➖➖➖➖➖➖➖➖
**🎭 ғʀᴏᴍ** : {bef}
**🍜 ᴛᴏ** : {aft}
➖➖➖➖➖➖➖➖➖➖➖➖\n
""".format(bef=usernamebefore, aft=usernameafter)
        await add_userdata(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )
    if first_name != message.from_user.first_name:
        msg += """
**🪧 ᴄʜᴀɴɢᴇs ғɪʀsᴛ ɴᴀᴍᴇ 🪧**
➖➖➖➖➖➖➖➖➖➖➖➖
**🔐 ғʀᴏᴍ** : {bef}
**🍓 ᴛᴏ** : {aft}
➖➖➖➖➖➖➖➖➖➖➖➖\n
""".format(
            bef=first_name, aft=message.from_user.first_name
        )
        await add_userdata(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )
    if lastname_before != message.from_user.last_name:
        lastname_before = lastname_before or "NO LAST NAME"
        lastname_after = message.from_user.last_name or "NO LAST NAME"
        msg += """
**🪧 ᴄʜᴀɴɢᴇs ʟᴀsᴛ ɴᴀᴍᴇ 🪧**
➖➖➖➖➖➖➖➖➖➖➖➖
**🚏ғʀᴏᴍ** : {bef}
**🍕 ᴛᴏ** : {aft}
➖➖➖➖➖➖➖➖➖➖➖➖\n
""".format(
            bef=lastname_before, aft=lastname_after
        )
        await add_userdata(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )
    if msg != "":
        await message.reply_photo("https://telegra.ph/file/58afe55fee5ae99d6901b.jpg", caption=msg)


@Client.on_message(filters.group & filters.command("imposter") & ~filters.bot & ~filters.via_bot)
async def set_mataa(client: Client, message: Message):
    if len(message.command) == 1:
        return await message.reply("**ᴅᴇᴛᴇᴄᴛ ᴘʀᴇᴛᴇɴᴅᴇʀ ᴜsᴇʀs ᴜsᴀɢᴇ : ᴘʀᴇᴛᴇɴᴅᴇʀ ᴏɴ|ᴏғғ**")
    if message.command[1] == "enable":
        cekset = await impo_on(message.chat.id)
        if cekset:
            await message.reply("**ᴘʀᴇᴛᴇɴᴅᴇʀ ᴍᴏᴅᴇ ɪs ᴀʟʀᴇᴀᴅʏ ᴇɴᴀʙʟᴇᴅ.**")
        else:
            await impo_on(message.chat.id)
            # Remove from disabled set if present
            disabled_chats.discard(message.chat.id)
            await message.reply(f"**sᴜᴄᴄᴇssғᴜʟʟʏ ᴇɴᴀʙʟᴇᴅ ᴘʀᴇᴛᴇɴᴅᴇʀ ᴍᴏᴅᴇ ғᴏʀ** {message.chat.title}")
    elif message.command[1] == "disable":
        cekset = await impo_off(message.chat.id)
        if not cekset:
            await message.reply("**ᴘʀᴇᴛᴇɴᴅᴇʀ ᴍᴏᴅᴇ ɪs ᴀʟʀᴇᴀᴅʏ ᴅɪsᴀʙʟᴇᴅ.**")
        else:
            await impo_off(message.chat.id)
            # Add to disabled set
            disabled_chats.add(message.chat.id)
            await message.reply(f"**sᴜᴄᴄᴇssғᴜʟʟʏ ᴅɪsᴀʙʟᴇᴅ ᴘʀᴇᴛᴇɴᴅᴇʀ ᴍᴏᴅᴇ ғᴏʀ** {message.chat.title}")
    else:
        await message.reply("**ᴅᴇᴛᴇᴄᴛ ᴘʀᴇᴛᴇɴᴅᴇʀ ᴜsᴇʀs ᴜsᴀɢᴇ : ᴘʀᴇᴛᴇɴᴅᴇʀ ᴏɴ|ᴏғғ**")

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_53"
__help__ = """
🔻 /imposter ➠ ᴘʀᴇᴛᴇɴᴅᴇʀ ᴅᴇᴛᴇᴄᴛɪᴏɴ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
"""
MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Name-History"
MOD_PRICE = "50"
