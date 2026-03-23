import asyncio
from pyrogram import filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, UserNotParticipant
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import mongodb

print("[admin] admins, staff, bots, admin, adminlist, report, rules")

# Anti-spam (optional)
user_last_message_time = {}
user_command_count = {}
SPAM_THRESHAND = 2
SPAM_WINDOW_SECONDS = 5

# Rules database collection
rules_db = mongodb.rules

# ------------------------------------------------------------------------------
# Helper to check if user is admin
# ------------------------------------------------------------------------------
async def is_admin(chat_id, user_id):
    try:
        member = await app.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except UserNotParticipant:
        return False

# ------------------------------------------------------------------------------
# Rules functions
# ------------------------------------------------------------------------------
async def get_rules(chat_id):
    data = await rules_db.find_one({"chat_id": chat_id})
    if data:
        return data.get("rules", "No rules set for this group.")
    return "No rules set for this group."

async def set_rules(chat_id, rules):
    await rules_db.update_one(
        {"chat_id": chat_id},
        {"$set": {"rules": rules}},
        upsert=True
    )

# ------------------------------------------------------------------------------
# /rules – View group rules
# ------------------------------------------------------------------------------
@app.on_message(filters.command("rules"))
async def rules_command(client, message: Message):
    rules = await get_rules(message.chat.id)
    await message.reply(f"**📜 Group Rules**\n\n{rules}")

# ------------------------------------------------------------------------------
# /setrules – Set group rules (admin only)
# ------------------------------------------------------------------------------
@app.on_message(filters.command("setrules"))
async def set_rules_command(client, message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply("❌ Only admins can set rules.")
        return
    if len(message.command) < 2:
        await message.reply("Usage: /setrules <rules text>")
        return
    rules_text = message.text.split(None, 1)[1]
    await set_rules(message.chat.id, rules_text)
    await message.reply("✅ Rules have been updated.")

# ------------------------------------------------------------------------------
# /admins and /staff – List all admins with titles
# ------------------------------------------------------------------------------
@app.on_message(filters.command(["admins", "staff"]))
async def admins_command(client, message: Message):
    try:
        admin_list = []
        owner = None
        async for member in app.get_chat_members(message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            if member.user.is_bot:
                continue
            if member.status == enums.ChatMemberStatus.OWNER:
                owner = member
            else:
                admin_list.append(member)

        text = f"**👥 Group Staff – {message.chat.title}**\n\n"

        # Owner
        if owner:
            title = owner.privileges.custom_title if owner.privileges and owner.privileges.custom_title else "Owner"
            text += f"👑 **Owner**\n"
            text += f"   • {owner.user.mention}"
            if title != "Owner":
                text += f" (`{title}`)"
            text += "\n\n"
        else:
            text += "👑 **Owner** (hidden)\n\n"

        # Admins
        if admin_list:
            text += f"👮 **Admins** ({len(admin_list)})\n"
            for i, admin in enumerate(admin_list, 1):
                title = admin.privileges.custom_title if admin.privileges and admin.privileges.custom_title else "Admin"
                mention = admin.user.mention
                text += f"{'└' if i == len(admin_list) else '├'} {mention}"
                if title != "Admin":
                    text += f" (`{title}`)"
                text += "\n"
        else:
            text += "👮 **Admins** (hidden)\n"

        await message.reply(text)

    except FloodWait as e:
        await asyncio.sleep(e.value)

# ------------------------------------------------------------------------------
# /adminlist – Alias for /admins
# ------------------------------------------------------------------------------
@app.on_message(filters.command("adminlist"))
async def adminlist_command(client, message: Message):
    await admins_command(client, message)

# ------------------------------------------------------------------------------
# /bots – List all bots in the group
# ------------------------------------------------------------------------------
@app.on_message(filters.command("bots"))
async def bots_command(client, message: Message):
    try:
        bot_list = []
        async for member in app.get_chat_members(message.chat.id, filter=enums.ChatMembersFilter.BOTS):
            bot_list.append(member.user)

        if not bot_list:
            await message.reply("🤖 No bots in this group.")
            return

        text = f"**🤖 Bot List – {message.chat.title}**\n\n"
        for i, bot in enumerate(bot_list, 1):
            text += f"{'└' if i == len(bot_list) else '├'} @{bot.username}\n"
        text += f"\n✅ **Total bots:** {len(bot_list)}"

        await message.reply(text)

    except FloodWait as e:
        await asyncio.sleep(e.value)

# ------------------------------------------------------------------------------
# /admin – Get admin info of a user (by reply, username, or ID)
# ------------------------------------------------------------------------------
@app.on_message(filters.command("admin"))
async def admin_info(client, message: Message):
    user_id = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif len(message.command) > 1:
        try:
            user = await app.get_users(message.command[1])
            user_id = user.id
        except:
            await message.reply("❌ User not found.")
            return
    else:
        user_id = message.from_user.id

    try:
        member = await app.get_chat_member(message.chat.id, user_id)
    except UserNotParticipant:
        await message.reply("❌ This user is not in the group.")
        return

    if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        await message.reply("❌ This user is not an admin.")
        return

    title = member.privileges.custom_title if member.privileges and member.privileges.custom_title else "Admin"
    text = f"**Admin Info**\n\n"
    text += f"👤 {member.user.mention}\n"
    text += f"📌 Title: `{title}`\n"
    text += f"🆔 ID: `{member.user.id}`\n"
    if member.privileges:
        perms = []
        if member.privileges.can_change_info: perms.append("Change Info")
        if member.privileges.can_delete_messages: perms.append("Delete Messages")
        if member.privileges.can_invite_users: perms.append("Invite Users")
        if member.privileges.can_restrict_members: perms.append("Restrict Members")
        if member.privileges.can_pin_messages: perms.append("Pin Messages")
        if member.privileges.can_promote_members: perms.append("Promote Members")
        if member.privileges.can_manage_video_chats: perms.append("Manage Video Chats")
        if member.privileges.is_anonymous: perms.append("Anonymous")
        if perms:
            text += f"🔧 Permissions: `{', '.join(perms)}`"
        else:
            text += "🔧 No special permissions."

    await message.reply(text)

# ------------------------------------------------------------------------------
# /report – Report a user/message to admins
# ------------------------------------------------------------------------------
@app.on_message(filters.command("report"))
async def report_command(client, message: Message):
    if not message.reply_to_message:
        await message.reply("❌ Reply to a message to report it.")
        return

    reported_msg = message.reply_to_message
    reported_user = reported_msg.from_user
    reporter = message.from_user

    # Check if reporter is not reporting themselves
    if reported_user and reported_user.id == reporter.id:
        await message.reply("😂 You cannot report yourself.")
        return

    # Get all admins (except bots)
    admin_mentions = []
    async for member in app.get_chat_members(message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
        if not member.user.is_bot:
            admin_mentions.append(member.user.mention)

    if not admin_mentions:
        await message.reply("No admins found to report to.")
        return

    # Prepare report message
    report_text = (
        f"⚠️ **Report**\n\n"
        f"👤 **Reporter:** {reporter.mention}\n"
        f"👤 **Reported:** {reported_user.mention if reported_user else 'Unknown'}\n"
        f"💬 **Message:** [Jump]({reported_msg.link})\n"
    )

    # Send to admins (in the group with tags)
    admin_tags = ", ".join(admin_mentions)
    final_text = f"{report_text}\n📢 {admin_tags}"
    await message.reply(final_text, disable_web_page_preview=True)

# ------------------------------------------------------------------------------
# Module metadata for help menu
# ------------------------------------------------------------------------------
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_13"
__help__ = """
🔻 /admins or /staff ➠ ʟɪsᴛ ᴀʟʟ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs ᴀɴᴅ ᴛʜᴇɪʀ ᴛɪᴛʟᴇs
🔻 /adminlist ➠ ᴀʟɪᴀs ᴏғ /admins
🔻 /admin <reply/username/id> ➠ ɢᴇᴛ ᴀᴅᴍɪɴ ɪɴғᴏ ᴏғ ᴀ ᴜsᴇʀ
🔻 /bots ➠ ʟɪsᴛ ᴀʟʟ ʙᴏᴛs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
🔻 /report <reply> ➠ ʀᴇᴘᴏʀᴛ ᴀ ᴍᴇssᴀɢᴇ ᴛᴏ ᴀᴅᴍɪɴs
🔻 /rules ➠ ᴠɪᴇᴡ ɢʀᴏᴜᴘ ʀᴜʟᴇs
🔻 /setrules <text> ➠ sᴇᴛ ɢʀᴏᴜᴘ ʀᴜʟᴇs (ᴀᴅᴍɪɴ ᴏɴʟʏ)
"""
