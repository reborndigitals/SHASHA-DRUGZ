import asyncio
import datetime
from pyrogram import filters, enums
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions
)
from pyrogram.errors.exceptions.bad_request_400 import (
    ChatAdminRequired,
    UserAdminInvalid,
    BadRequest
)

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import mongodb
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import get_served_chats

# ========================== GLOBAL BAN DATABASE ==========================
gbans_collection = mongodb.gbans

async def add_gban(user_id: int, reason: str = None, admin_id: int = None):
    """Add a user to global ban list."""
    await gbans_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "reason": reason,
            "admin_id": admin_id,
            "date": datetime.datetime.now()
        }},
        upsert=True
    )

async def remove_gban(user_id: int):
    """Remove a user from global ban list."""
    await gbans_collection.delete_one({"user_id": user_id})

async def is_gbanned(user_id: int) -> bool:
    """Check if a user is globally banned."""
    return bool(await gbans_collection.find_one({"user_id": user_id}))

async def get_gban_reason(user_id: int) -> str:
    """Get the reason for global ban."""
    data = await gbans_collection.find_one({"user_id": user_id})
    return data.get("reason") if data else None

# ========================== HELPER FUNCTIONS ==========================
def mention(user, name, mention=True):
    if mention:
        return f"[{name}](tg://openmessage?user_id={user})"
    return f"[{name}](https://t.me/{user})"

async def get_userid_from_username(username):
    try:
        user = await app.get_users(username)
        return [user.id, user.first_name]
    except:
        return None

async def ban_user(user_id, first_name, admin_id, admin_name, chat_id, reason, time=None, silent=False):
    try:
        await app.ban_chat_member(chat_id, user_id)
    except ChatAdminRequired:
        msg_text = "Ban rights? Nah, I'm just here for the digital high-fives 🙌\nGive me ban rights! 😡🥺"
        return msg_text, False
    except UserAdminInvalid:
        msg_text = "I wont ban an admin bruh!!"
        return msg_text, False
    except Exception as e:
        if user_id == app.id:
            msg_text = "why should i ban myself? sorry but I'm not stupid like you"
            return msg_text, False
        msg_text = f"opps!!\n{e}"
        return msg_text, False

    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)

    if silent:
        # No message to group
        return None, True

    msg_text = f"{user_mention} was banned by {admin_mention}\n"
    if reason:
        msg_text += f"Reason: `{reason}`\n"
    if time:
        msg_text += f"Time: `{time}`\n"
    return msg_text, True

async def unban_user(user_id, first_name, admin_id, admin_name, chat_id):
    try:
        await app.unban_chat_member(chat_id, user_id)
    except ChatAdminRequired:
        return "Ban rights? Nah, I'm just here for the digital high-fives 🙌\nGive me ban rights! 😡🥺"
    except Exception as e:
        return f"opps!!\n{e}"
    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)
    return f"{user_mention} was unbanned by {admin_mention}"

async def mute_user(user_id, first_name, admin_id, admin_name, chat_id, reason, time=None):
    try:
        if time:
            mute_end_time = datetime.datetime.now() + time
            await app.restrict_chat_member(chat_id, user_id, ChatPermissions(), mute_end_time)
        else:
            await app.restrict_chat_member(chat_id, user_id, ChatPermissions())
    except ChatAdminRequired:
        return "Mute rights? Nah, I'm just here for the digital high-fives 🙌\nGive me mute rights! 😡🥺", False
    except UserAdminInvalid:
        return "I wont mute an admin bruh!!", False
    except Exception as e:
        if user_id == app.id:
            return "why should i mute myself? sorry but I'm not stupid like you", False
        return f"opps!!\n{e}", False

    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)
    msg_text = f"{user_mention} was muted by {admin_mention}\n"
    if reason:
        msg_text += f"Reason: `{reason}`\n"
    if time:
        msg_text += f"Time: `{time}`\n"
    return msg_text, True

async def unmute_user(user_id, first_name, admin_id, admin_name, chat_id):
    try:
        await app.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(
                can_send_media_messages=True,
                can_send_messages=True,
                can_send_other_messages=True,
                can_send_polls=True,
                can_add_web_page_previews=True,
                can_invite_users=True
            )
        )
    except ChatAdminRequired:
        return "Mute rights? Nah, I'm just here for the digital high-fives 🙌\nGive me unmute rights! 😡🥺"
    except Exception as e:
        return f"opps!!\n{e}"
    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)
    return f"{user_mention} was unmuted by {admin_mention}"

async def mute_all_users(admin_id, admin_name, chat_id, reason=None):
    try:
        members = []
        async for member in app.get_chat_members(chat_id):
            if member.user.id == app.id:
                continue
            if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                continue
            members.append(member)

        if not members:
            return "No members to mute.", False

        success = 0
        failed = 0
        for member in members:
            try:
                await app.restrict_chat_member(chat_id, member.user.id, ChatPermissions())
                success += 1
            except:
                failed += 1

        admin_mention = mention(admin_id, admin_name)
        msg = f"{admin_mention} muted all users.\n✅ Success: {success}\n❌ Failed: {failed}"
        if reason:
            msg += f"\nReason: `{reason}`"
        return msg, True
    except ChatAdminRequired:
        return "I need mute rights to mute all users! 😡🥺", False
    except Exception as e:
        return f"opps!!\n{e}", False

async def unmute_all_users(admin_id, admin_name, chat_id):
    try:
        members = []
        async for member in app.get_chat_members(chat_id):
            if member.user.id == app.id:
                continue
            members.append(member)

        if not members:
            return "No members to unmute.", False

        success = 0
        failed = 0
        for member in members:
            try:
                await app.restrict_chat_member(
                    chat_id,
                    member.user.id,
                    ChatPermissions(
                        can_send_media_messages=True,
                        can_send_messages=True,
                        can_send_other_messages=True,
                        can_send_polls=True,
                        can_add_web_page_previews=True,
                        can_invite_users=True
                    )
                )
                success += 1
            except:
                failed += 1

        admin_mention = mention(admin_id, admin_name)
        return f"{admin_mention} unmuted all users.\n✅ Success: {success}\n❌ Failed: {failed}", True
    except ChatAdminRequired:
        return "I need mute rights to unmute all users! 😡🥺", False
    except Exception as e:
        return f"opps!!\n{e}", False

# ========================== MUTEALL ==========================
@app.on_message(filters.command(["muteall"]))
async def muteall_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to mute members.")
    else:
        return await message.reply_text("You don't have permission to mute members.")

    reason = message.text.split(None, 1)[1] if len(message.command) > 1 else None
    msg_text, result = await mute_all_users(admin_id, admin_name, chat_id, reason)
    await message.reply_text(msg_text)

# ========================== UNMUTEALL ==========================
@app.on_message(filters.command(["unmuteall"]))
async def unmuteall_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to unmute members.")
    else:
        return await message.reply_text("You don't have permission to unmute members.")

    msg_text, result = await unmute_all_users(admin_id, admin_name, chat_id)
    await message.reply_text(msg_text)

# ========================== BAN ==========================
@app.on_message(filters.command(["ban"]))
async def ban_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    # Permission check
    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to ban someone.")
    else:
        return await message.reply_text("You don't have permission to ban someone.")

    # Parse user
    if len(message.command) > 1:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            first_name = message.reply_to_message.from_user.first_name
            reason = message.text.split(None, 1)[1]
        else:
            try:
                user_id = int(message.command[1])
                first_name = "User"
            except:
                user_obj = await get_userid_from_username(message.command[1])
                if not user_obj:
                    return await message.reply_text("I can't find that user")
                user_id, first_name = user_obj
            reason = message.text.partition(message.command[1])[2] or None
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
        reason = None
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    msg_text, result = await ban_user(user_id, first_name, admin_id, admin_name, chat_id, reason)
    if result:
        await message.reply_text(msg_text)
    else:
        await message.reply_text(msg_text)

# ========================== UNBAN ==========================
@app.on_message(filters.command(["unban"]))
async def unban_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to unban someone.")
    else:
        return await message.reply_text("You don't have permission to unban someone.")

    if len(message.command) > 1:
        try:
            user_id = int(message.command[1])
            first_name = "User"
        except:
            user_obj = await get_userid_from_username(message.command[1])
            if not user_obj:
                return await message.reply_text("I can't find that user")
            user_id, first_name = user_obj
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    msg_text = await unban_user(user_id, first_name, admin_id, admin_name, chat_id)
    await message.reply_text(msg_text)

# ========================== MUTE ==========================
@app.on_message(filters.command(["mute"]))
async def mute_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to mute someone.")
    else:
        return await message.reply_text("You don't have permission to mute someone.")

    if len(message.command) > 1:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            first_name = message.reply_to_message.from_user.first_name
            reason = message.text.split(None, 1)[1]
        else:
            try:
                user_id = int(message.command[1])
                first_name = "User"
            except:
                user_obj = await get_userid_from_username(message.command[1])
                if not user_obj:
                    return await message.reply_text("I can't find that user")
                user_id, first_name = user_obj
            reason = message.text.partition(message.command[1])[2] or None
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
        reason = None
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    msg_text, result = await mute_user(user_id, first_name, admin_id, admin_name, chat_id, reason)
    if result:
        await message.reply_text(msg_text)
    else:
        await message.reply_text(msg_text)

# ========================== UNMUTE ==========================
@app.on_message(filters.command(["unmute"]))
async def unmute_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to unmute someone.")
    else:
        return await message.reply_text("You don't have permission to unmute someone.")

    if len(message.command) > 1:
        try:
            user_id = int(message.command[1])
            first_name = "User"
        except:
            user_obj = await get_userid_from_username(message.command[1])
            if not user_obj:
                return await message.reply_text("I can't find that user")
            user_id, first_name = user_obj
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    msg_text = await unmute_user(user_id, first_name, admin_id, admin_name, chat_id)
    await message.reply_text(msg_text)

# ========================== TMUTE ==========================
@app.on_message(filters.command(["tmute"]))
async def tmute_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to mute someone.")
    else:
        return await message.reply_text("You don't have permission to mute someone.")

    if len(message.command) > 1:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            first_name = message.reply_to_message.from_user.first_name
            time_str = message.text.split(None, 1)[1]

            try:
                time_amount = int(time_str[:-1])
                unit = time_str[-1]
            except:
                return await message.reply_text("Wrong format!!\nFormat: `/tmute 2m`")

            if unit == "m":
                mute_duration = datetime.timedelta(minutes=time_amount)
            elif unit == "h":
                mute_duration = datetime.timedelta(hours=time_amount)
            elif unit == "d":
                mute_duration = datetime.timedelta(days=time_amount)
            else:
                return await message.reply_text("Wrong format!!\nUse m (minutes), h (hours), d (days)")
        else:
            try:
                user_id = int(message.command[1])
                first_name = "User"
            except:
                user_obj = await get_userid_from_username(message.command[1])
                if not user_obj:
                    return await message.reply_text("I can't find that user")
                user_id, first_name = user_obj

            try:
                time_str = message.text.partition(message.command[1])[2].strip()
                if not time_str:
                    return await message.reply_text("Please specify time.\nFormat: `/tmute @user 2m`")
                time_amount = int(time_str[:-1])
                unit = time_str[-1]
            except:
                return await message.reply_text("Wrong format!!\nFormat: `/tmute @user 2m`")

            if unit == "m":
                mute_duration = datetime.timedelta(minutes=time_amount)
            elif unit == "h":
                mute_duration = datetime.timedelta(hours=time_amount)
            elif unit == "d":
                mute_duration = datetime.timedelta(days=time_amount)
            else:
                return await message.reply_text("Wrong format!!\nUse m (minutes), h (hours), d (days)")
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message\nFormat: /tmute <username> <time>")

    msg_text, result = await mute_user(user_id, first_name, admin_id, admin_name, chat_id, reason=None, time=mute_duration)
    if result:
        await message.reply_text(msg_text)
    else:
        await message.reply_text(msg_text)

# ========================== TBAN ==========================
@app.on_message(filters.command(["tban"]))
async def tban_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to ban someone.")
    else:
        return await message.reply_text("You don't have permission to ban someone.")

    if len(message.command) > 1:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            first_name = message.reply_to_message.from_user.first_name
            time_str = message.text.split(None, 1)[1]

            try:
                time_amount = int(time_str[:-1])
                unit = time_str[-1]
            except:
                return await message.reply_text("Wrong format!!\nFormat: `/tban 2m`")

            if unit == "m":
                ban_duration = datetime.timedelta(minutes=time_amount)
            elif unit == "h":
                ban_duration = datetime.timedelta(hours=time_amount)
            elif unit == "d":
                ban_duration = datetime.timedelta(days=time_amount)
            else:
                return await message.reply_text("Wrong format!!\nUse m (minutes), h (hours), d (days)")
            reason = None
        else:
            try:
                user_id = int(message.command[1])
                first_name = "User"
            except:
                user_obj = await get_userid_from_username(message.command[1])
                if not user_obj:
                    return await message.reply_text("I can't find that user")
                user_id, first_name = user_obj

            try:
                time_str = message.text.partition(message.command[1])[2].strip()
                if not time_str:
                    return await message.reply_text("Please specify time.\nFormat: `/tban @user 2m`")
                time_amount = int(time_str[:-1])
                unit = time_str[-1]
            except:
                return await message.reply_text("Wrong format!!\nFormat: `/tban @user 2m`")

            if unit == "m":
                ban_duration = datetime.timedelta(minutes=time_amount)
            elif unit == "h":
                ban_duration = datetime.timedelta(hours=time_amount)
            elif unit == "d":
                ban_duration = datetime.timedelta(days=time_amount)
            else:
                return await message.reply_text("Wrong format!!\nUse m (minutes), h (hours), d (days)")
            reason = None
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message\nFormat: /tban <username> <time>")

    # First ban the user
    msg_text, result = await ban_user(user_id, first_name, admin_id, admin_name, chat_id, reason, time=time_str, silent=True)
    if not result:
        return await message.reply_text(msg_text)

    # Schedule unban after duration
    async def unban_later():
        await asyncio.sleep(ban_duration.total_seconds())
        await unban_user(user_id, first_name, admin_id, admin_name, chat_id)
    asyncio.create_task(unban_later())

    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)
    await message.reply_text(f"{user_mention} was temporarily banned by {admin_mention} for {time_str}.\nThey will be unbanned automatically.")

# ========================== SBAN (Silent Ban) ==========================
@app.on_message(filters.command(["sban"]))
async def sban_command_handler(client, message):
    chat = message.chat
    chat_id = chat.id
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    member = await chat.get_member(admin_id)
    if member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to ban someone.")
    else:
        return await message.reply_text("You don't have permission to ban someone.")

    if len(message.command) > 1:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            first_name = message.reply_to_message.from_user.first_name
            reason = message.text.split(None, 1)[1]
        else:
            try:
                user_id = int(message.command[1])
                first_name = "User"
            except:
                user_obj = await get_userid_from_username(message.command[1])
                if not user_obj:
                    return await message.reply_text("I can't find that user")
                user_id, first_name = user_obj
            reason = message.text.partition(message.command[1])[2] or None
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
        reason = None
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    msg_text, result = await ban_user(user_id, first_name, admin_id, admin_name, chat_id, reason, silent=True)
    if result:
        # Silent ban – delete the command message
        await message.delete()
    else:
        await message.reply_text(msg_text)

# ========================== GLOBAL BAN ==========================
@app.on_message(filters.command(["gban", "globalban"]))
async def gban_command_handler(client, message):
    chat = message.chat
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    # Check if user is sudoer or admin in this chat
    if admin_id not in SUDOERS:
        member = await chat.get_member(admin_id)
        if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return await message.reply_text("You need to be an admin in this group to use global ban.")
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to restrict members.")

    # Parse user
    if len(message.command) > 1:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            first_name = message.reply_to_message.from_user.first_name
            reason = message.text.split(None, 1)[1]
        else:
            try:
                user_id = int(message.command[1])
                first_name = "User"
            except:
                user_obj = await get_userid_from_username(message.command[1])
                if not user_obj:
                    return await message.reply_text("I can't find that user")
                user_id, first_name = user_obj
            reason = message.text.partition(message.command[1])[2] or None
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
        reason = None
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    # Check if already gbanned
    if await is_gbanned(user_id):
        return await message.reply_text("This user is already globally banned.")

    # Add to global ban list
    await add_gban(user_id, reason, admin_id)

    # Get all served chats
    chats = await get_served_chats()
    total = len(chats)
    success = 0
    failed = 0

    progress = await message.reply_text(f"🌐 **Global Ban in progress...**\nProcessing {total} chats...")

    for chat_data in chats:
        chat_id = chat_data["chat_id"]
        try:
            # Check if bot is admin in that chat
            bot_member = await app.get_chat_member(chat_id, app.id)
            if bot_member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                if bot_member.privileges.can_restrict_members:
                    await app.ban_chat_member(chat_id, user_id)
                    success += 1
                else:
                    failed += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.5)  # Avoid flood

    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)
    await progress.edit_text(
        f"✅ **Global Ban Completed**\n\n"
        f"{user_mention} was globally banned by {admin_mention}\n"
        f"Reason: {reason or 'No reason'}\n\n"
        f"📊 Total chats: {total}\n"
        f"✅ Banned in: {success}\n"
        f"❌ Failed: {failed}"
    )

# ========================== GLOBAL UNBAN ==========================
@app.on_message(filters.command(["gunban", "globalunban"]))
async def gunban_command_handler(client, message):
    chat = message.chat
    admin_id = message.from_user.id
    admin_name = message.from_user.first_name

    # Check if user is sudoer or admin in this chat
    if admin_id not in SUDOERS:
        member = await chat.get_member(admin_id)
        if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return await message.reply_text("You need to be an admin in this group to use global unban.")
        if not member.privileges.can_restrict_members:
            return await message.reply_text("You don't have permission to restrict members.")

    # Parse user
    if len(message.command) > 1:
        try:
            user_id = int(message.command[1])
            first_name = "User"
        except:
            user_obj = await get_userid_from_username(message.command[1])
            if not user_obj:
                return await message.reply_text("I can't find that user")
            user_id, first_name = user_obj
    elif message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        first_name = message.reply_to_message.from_user.first_name
    else:
        return await message.reply_text("Please specify a valid user or reply to that user's message")

    # Check if actually gbanned
    if not await is_gbanned(user_id):
        return await message.reply_text("This user is not globally banned.")

    # Remove from global ban list
    await remove_gban(user_id)

    # Get all served chats
    chats = await get_served_chats()
    total = len(chats)
    success = 0
    failed = 0

    progress = await message.reply_text(f"🌐 **Global Unban in progress...**\nProcessing {total} chats...")

    for chat_data in chats:
        chat_id = chat_data["chat_id"]
        try:
            # Check if bot is admin in that chat
            bot_member = await app.get_chat_member(chat_id, app.id)
            if bot_member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                if bot_member.privileges.can_restrict_members:
                    await app.unban_chat_member(chat_id, user_id)
                    success += 1
                else:
                    failed += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.5)

    user_mention = mention(user_id, first_name)
    admin_mention = mention(admin_id, admin_name)
    await progress.edit_text(
        f"✅ **Global Unban Completed**\n\n"
        f"{user_mention} was globally unbanned by {admin_mention}\n\n"
        f"📊 Total chats: {total}\n"
        f"✅ Unbanned in: {success}\n"
        f"❌ Failed: {failed}"
    )

# ========================== HELP TEXT ==========================
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_4"
__help__ = """
🔻 /ban ➠ ʙᴀɴs ᴀ ᴜsᴇʀ ғʀᴏᴍ ᴛʜᴇ ɢʀᴏᴜᴘ (ʀᴇᴘʟʏ / ᴜsᴇʀɴᴀᴍᴇ / ɪᴅ).
🔻 /unban ➠ ᴜɴʙᴀɴs ᴀ ᴘʀᴇᴠɪᴏᴜsʟʏ ʙᴀɴɴᴇᴅ ᴜsᴇʀ.
🔻 /mute ➠ ᴍᴜᴛᴇs ᴀ ᴜsᴇʀ ғʀᴏᴍ sᴇɴᴅɪɴɢ ᴍᴇssᴀɢᴇs.
🔻 /unmute ➠ ᴜɴᴍᴜᴛᴇs ᴀ ᴍᴜᴛᴇᴅ ᴜsᴇʀ ᴀɴᴅ ʀᴇsᴛᴏʀᴇs ᴘᴇʀᴍɪssɪᴏɴs.
🔻 /tmute (2m, 1h, 1d) ➠ ᴛᴇᴍᴘᴏʀᴀʀɪʟʏ ᴍᴜᴛᴇs ᴀ ᴜsᴇʀ ғᴏʀ ᴀ sᴘᴇᴄɪғɪᴇᴅ ᴛɪᴍᴇ (ᴍ / ʜ / ᴅ).
🔻 /tban (2m, 1h, 1d) ➠ ᴛᴇᴍᴘᴏʀᴀʀɪʟʏ ʙᴀɴs ᴀ ᴜsᴇʀ ғᴏʀ ᴀ sᴘᴇᴄɪғɪᴇᴅ ᴛɪᴍᴇ.
🔻 /sban ➠ sɪʟᴇɴᴛ ʙᴀɴ (ʙᴀɴs ᴡɪᴛʜᴏᴜᴛ ᴀɴʏ ᴍᴇssᴀɢᴇ).
🔻 /muteall ➠ ᴍᴜᴛᴇs ᴀʟʟ ɴᴏɴ-ᴀᴅᴍɪɴ ᴍᴇᴍʙᴇʀs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /unmuteall ➠ ᴜɴᴍᴜᴛᴇs ᴀʟʟ ᴍᴇᴍʙᴇʀs ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /gban or /globalban ➠ ɢʟᴏʙᴀʟʟʏ ʙᴀɴs ᴀ ᴜsᴇʀ ғʀᴏᴍ ᴀʟʟ ɢʀᴏᴜᴘs ᴡʜᴇʀᴇ ʙᴏᴛ ɪs ᴀᴅᴍɪɴ.
🔻 /gunban or /globalunban ➠ ɢʟᴏʙᴀʟʟʏ ᴜɴʙᴀɴs ᴀ ᴜsᴇʀ.
"""
