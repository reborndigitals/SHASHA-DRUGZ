import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChatAdminRequired,
    InviteRequestSent,
    UserAlreadyParticipant,
    UserNotParticipant,
    ChannelInvalid,
    ChatIdInvalid,
    PeerIdInvalid,
)
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter

links = {}


# ──────────────────────────────────────────────────────────────────────────────
# SAFE HELPER: checks if userbot is already in chat using the BOT client
# (never calls userbot.get_chat before joining — avoids CHANNEL_INVALID)
# ──────────────────────────────────────────────────────────────────────────────
async def get_userbot_status(client: Client, chat_id: int, userbot_id: int):
    """
    Returns ChatMemberStatus or None if userbot is not found / chat invalid.
    Uses the deployed bot (client) to check — NOT the userbot itself.
    """
    try:
        member = await client.get_chat_member(chat_id, userbot_id)
        return member.status
    except UserNotParticipant:
        return ChatMemberStatus.LEFT
    except (ChannelInvalid, ChatIdInvalid, PeerIdInvalid):
        return None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# SAFE HELPER: joins via invite link (for private groups)
# ──────────────────────────────────────────────────────────────────────────────
async def _join_via_invite(client: Client, userbot, chat_id: int, done, userbot_username: str):
    try:
        invite_link = await client.create_chat_invite_link(chat_id, expire_date=None)
        await asyncio.sleep(2)
        await userbot.join_chat(invite_link.invite_link)
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ.**")
    except UserAlreadyParticipant:
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
    except InviteRequestSent:
        try:
            await client.approve_chat_join_request(chat_id, userbot.id)
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.**")
        except Exception as e:
            await done.edit_text(
                f"**⚠️ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ sᴇɴᴛ ʙᴜᴛ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴀᴜᴛᴏ-ᴀᴘᴘʀᴏᴠᴇ.**\n`{e}`"
            )
    except ChatAdminRequired:
        await done.edit_text(
            f"**❌ ɪ ɴᴇᴇᴅ 'ɪɴᴠɪᴛᴇ ᴜsᴇʀs' ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ.**\n\n"
            f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** @{userbot_username}"
        )
    except Exception as e:
        await done.edit_text(
            f"**➻ ɪ ᴄᴀɴɴᴏᴛ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**\n`{e}`\n\n"
            f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** @{userbot_username}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# /userbotjoin
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(
    filters.group
    & filters.command("userbotjoin")
    & ~filters.private
)
async def join_group(client: Client, message):
    chat_id = message.chat.id

    # Get deployed bot's own info
    try:
        me = await client.get_me()
    except Exception as e:
        await message.reply_text(f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ɢᴇᴛ ʙᴏᴛ ɪɴғᴏ.**\n`{e}`")
        return

    # Get assistant (userbot) instance — do NOT call get_chat yet
    userbot = await get_assistant(chat_id)
    userbot_id = userbot.id
    userbot_username = userbot.username or str(userbot_id)

    done = await message.reply("**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɪɴᴠɪᴛɪɴɢ ᴀssɪsᴛᴀɴᴛ...**")
    await asyncio.sleep(1)

    # Check bot's own admin status using the deployed bot (client)
    try:
        chat_member = await client.get_chat_member(chat_id, me.id)
    except Exception as e:
        await done.edit_text(f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ғᴇᴛᴄʜ ᴄʜᴀᴛ ɪɴғᴏ.**\n`{e}`")
        return

    is_admin = chat_member.status == ChatMemberStatus.ADMINISTRATOR

    # ── Check current userbot status SAFELY via bot client (not userbot) ──────
    userbot_status = await get_userbot_status(client, chat_id, userbot_id)

    if userbot_status is None:
        # Chat is truly invalid for bot too — abort
        await done.edit_text(
            "**❌ ᴄʜᴀᴛ ɪs ɪɴᴠᴀʟɪᴅ ᴏʀ ʙᴏᴛ ɪs ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ. ᴀᴅᴅ ᴍᴇ ᴀs ᴀᴅᴍɪɴ ғɪʀsᴛ.**"
        )
        return

    # Already in chat
    if userbot_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴄʜᴀᴛ.**")
        return

    # ── PUBLIC GROUP (has username) ───────────────────────────────────────────
    if message.chat.username:

        # Banned/restricted → unban first (needs admin)
        if userbot_status in [ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED]:
            if not is_admin:
                await done.edit_text(
                    "**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ᴜɴʙᴀɴ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**"
                )
                return
            try:
                await client.unban_chat_member(chat_id, userbot_id)
                await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴜɴʙᴀɴɴᴇᴅ, ɴᴏᴡ ᴊᴏɪɴɪɴɢ...**")
                await asyncio.sleep(1)
            except ChatAdminRequired:
                await done.edit_text(
                    "**❌ ɪ ɴᴇᴇᴅ 'ʙᴀɴ ᴜsᴇʀs' ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ᴜɴʙᴀɴ.**"
                )
                return
            except Exception as e:
                await done.edit_text(
                    f"**❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴜɴʙᴀɴ ᴀssɪsᴛᴀɴᴛ.**\n`{e}`"
                )
                return

        # Now join by username
        try:
            await userbot.join_chat(message.chat.username)
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ.**")
        except UserAlreadyParticipant:
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
        except InviteRequestSent:
            if is_admin:
                try:
                    await client.approve_chat_join_request(chat_id, userbot_id)
                    await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.**")
                except Exception as e:
                    await done.edit_text(
                        f"**⚠️ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ sᴇɴᴛ ʙᴜᴛ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴀᴜᴛᴏ-ᴀᴘᴘʀᴏᴠᴇ.**\n`{e}`"
                    )
            else:
                await done.edit_text(
                    "**⚠️ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ sᴇɴᴛ. ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴛᴏ ᴀᴘᴘʀᴏᴠᴇ.**"
                )
        except Exception as e:
            await done.edit_text(
                f"**❌ ᴀssɪsᴛᴀɴᴛ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴊᴏɪɴ.**\n`{e}`\n\n"
                f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** @{userbot_username}"
            )
        return

    # ── PRIVATE GROUP (no username) ───────────────────────────────────────────
    if not is_admin:
        await done.edit_text(
            "**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**"
        )
        return

    # Banned/restricted in private group → unban first
    if userbot_status in [ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED]:
        try:
            await client.unban_chat_member(chat_id, userbot_id)
            await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴜɴʙᴀɴɴᴇᴅ, ɴᴏᴡ ɪɴᴠɪᴛɪɴɢ...**")
            await asyncio.sleep(1)
        except ChatAdminRequired:
            await done.edit_text(
                f"**❌ ᴀssɪsᴛᴀɴᴛ ɪs ʙᴀɴɴᴇᴅ. ɪ ɴᴇᴇᴅ 'ʙᴀɴ ᴜsᴇʀs' ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ.**\n\n"
                f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** @{userbot_username}"
            )
            return
        except Exception as e:
            await done.edit_text(
                f"**➻ ᴀssɪsᴛᴀɴᴛ ɪs ʙᴀɴɴᴇᴅ ᴀɴᴅ ɪ ᴄᴀɴɴᴏᴛ ᴜɴʙᴀɴ.**\n`{e}`\n\n"
                f"**ᴘʟᴇᴀsᴇ ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ ᴛʜᴇɴ /userbotjoin**\n\n"
                f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** @{userbot_username}"
            )
            return

    # LEFT state → invite via link (safe: bot is already in chat so invite works)
    await done.edit_text("**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɪɴᴠɪᴛɪɴɢ ᴀssɪsᴛᴀɴᴛ...**")
    await _join_via_invite(client, userbot, chat_id, done, userbot_username)


# ──────────────────────────────────────────────────────────────────────────────
# /userbotleave
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("userbotleave") & filters.group & admin_filter)
async def leave_one(client: Client, message):
    try:
        userbot = await get_assistant(message.chat.id)
        await userbot.leave_chat(message.chat.id)
        await client.send_message(
            message.chat.id, "**✅ ᴜsᴇʀʙᴏᴛ sᴜᴄᴄᴇssғᴜʟʟʏ ʟᴇғᴛ ᴛʜɪs Chat.**"
        )
    except Exception as e:
        await message.reply_text(f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ʟᴇᴀᴠᴇ.**\n`{e}`")


# ──────────────────────────────────────────────────────────────────────────────
# /leaveall
# ──────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("leaveall") & SUDOERS)
async def leave_all(client: Client, message):
    if message.from_user.id not in SUDOERS:
        return

    left = 0
    failed = 0
    lol = await message.reply("🔄 **ᴜsᴇʀʙᴏᴛ** ʟᴇᴀᴠɪɴɢ ᴀʟʟ ᴄʜᴀᴛs!")

    try:
        userbot = await get_assistant(message.chat.id)
        async for dialog in userbot.get_dialogs():
            if dialog.chat.id == -1001735663878:
                continue
            try:
                await userbot.leave_chat(dialog.chat.id)
                left += 1
                await lol.edit(
                    f"**ᴜsᴇʀʙᴏᴛ ʟᴇᴀᴠɪɴɢ ᴀʟʟ ɢʀᴏᴜᴘ...**\n\n"
                    f"**ʟᴇғᴛ:** {left} ᴄʜᴀᴛs.\n**ғᴀɪʟᴇᴅ:** {failed} ᴄʜᴀᴛs."
                )
            except Exception:
                failed += 1
                await lol.edit(
                    f"**ᴜsᴇʀʙᴏᴛ ʟᴇᴀᴠɪɴɢ...**\n\n"
                    f"**ʟᴇғᴛ:** {left} chats.\n**ғᴀɪʟᴇᴅ:** {failed} chats."
                )
            await asyncio.sleep(3)
    except Exception as e:
        await message.reply_text(f"**❌ ɢᴇᴛ_ᴅɪᴀʟᴏɢs ғᴀɪʟᴇᴅ.**\n`{e}`")
    finally:
        await client.send_message(
            message.chat.id,
            f"**✅ ʟᴇғᴛ ғʀᴏᴍ:** {left} chats.\n**❌ ғᴀɪʟᴇᴅ ɪɴ:** {failed} chats.",
        )


__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_60"
__help__ = """
🔻 /userbotjoin ➠ ɪɴᴠɪᴛᴇs ᴛʜᴇ ᴀssɪsᴛᴀɴᴛ ᴛᴏ ᴛʜᴇ ɢʀᴏᴜᴘ ᴏʀ ᴜɴʙᴀɴs ɪғ ʙᴀɴɴᴇᴅ
🔻 /userbotleave ➠ ʀᴇᴍᴏᴠᴇs ᴛʜᴇ ᴀssɪsᴛᴀɴᴛ ғʀᴏᴍ ᴛʜᴇ ɢʀᴏᴜᴘ
🔻 /leaveall ➠ ᴍᴀᴋᴇs ᴛʜᴇ ᴀssɪsᴛᴀɴᴛ ʟᴇᴀᴠᴇ ᴀʟʟ ɢʀᴏᴜᴘs ɪᴛ ɪs ɪɴ
"""
MOD_TYPE = "MUSIC"
MOD_NAME = "AssistantJoin"
MOD_PRICE = "0"
