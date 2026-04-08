import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChatAdminRequired,
    InviteRequestSent,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter

links = {}

@Client.on_message(
    filters.group
    & filters.command("userbotjoin")
    & ~filters.private
)
async def join_group(client: Client, message):
    chat_id = message.chat.id

    # ── get the deployed bot's own ID via client (NOT app) ──
    try:
        me = await client.get_me()
    except Exception as e:
        await message.reply_text(f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ɢᴇᴛ ʙᴏᴛ ɪɴғᴏ.**\n`{e}`")
        return

    userbot = await get_assistant(chat_id)
    userbot_id = userbot.id

    done = await message.reply("**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɪɴᴠɪᴛɪɴɢ ᴀssɪsᴛᴀɴᴛ**...")
    await asyncio.sleep(1)

    # ── use client (deployed bot) — NOT app (main bot) ──
    try:
        chat_member = await client.get_chat_member(chat_id, me.id)
    except Exception as e:
        await done.edit_text(
            f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ғᴇᴛᴄʜ ᴄʜᴀᴛ ɪɴғᴏ.**\n`{e}`"
        )
        return

    is_admin = chat_member.status == ChatMemberStatus.ADMINISTRATOR

    # ── Condition 1 & 2: public group (has username) ──────────────────────────
    if message.chat.username:
        # Try joining by username first
        try:
            await userbot.join_chat(message.chat.username)
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ.**")
            return
        except UserAlreadyParticipant:
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
            return
        except InviteRequestSent:
            if is_admin:
                try:
                    await client.approve_chat_join_request(chat_id, userbot_id)
                    await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.**")
                except Exception:
                    await done.edit_text("**⚠️ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ sᴇɴᴛ, ᴘʟᴇᴀsᴇ ᴀᴘᴘʀᴏᴠᴇ ᴍᴀɴᴜᴀʟʟʏ.**")
            else:
                await done.edit_text("**⚠️ ᴊᴏɪɴ ʀᴇQᴜᴇsᴛ sᴇɴᴛ. ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴛᴏ ᴀᴘᴘʀᴏᴠᴇ.**")
            return
        except Exception:
            # Join by username failed — check if assistant is banned
            if is_admin:
                try:
                    userbot_member = await client.get_chat_member(chat_id, userbot_id)
                    if userbot_member.status in [
                        ChatMemberStatus.BANNED,
                        ChatMemberStatus.RESTRICTED,
                    ]:
                        try:
                            await client.unban_chat_member(chat_id, userbot_id)
                            await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ɪs ᴜɴʙᴀɴɴɪɴɢ...**")
                            await asyncio.sleep(1)
                            await userbot.join_chat(message.chat.username)
                            await done.edit_text(
                                "**ᴀssɪsᴛᴀɴᴛ ᴡᴀs ʙᴀɴɴᴇᴅ, ʙᴜᴛ ɴᴏᴡ ᴜɴʙᴀɴɴᴇᴅ, ᴀɴᴅ ᴊᴏɪɴᴇᴅ ✅**"
                            )
                        except UserAlreadyParticipant:
                            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
                        except Exception:
                            await done.edit_text(
                                "**ғᴀɪʟᴇᴅ ᴛᴏ ᴊᴏɪɴ. ᴘʟᴇᴀsᴇ ɢɪᴠᴇ ʙᴀɴ & ɪɴᴠɪᴛᴇ ᴘᴏᴡᴇʀ ᴏʀ ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ ᴛʜᴇɴ /userbotjoin**"
                            )
                    else:
                        await done.edit_text(
                            "**❌ ᴀssɪsᴛᴀɴᴛ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴊᴏɪɴ. ᴜɴᴋɴᴏᴡɴ ᴇʀʀᴏʀ.**"
                        )
                except Exception:
                    await done.edit_text(
                        "**❌ ғᴀɪʟᴇᴅ. ᴍᴀᴋᴇ sᴜʀᴇ ɪ ʜᴀᴠᴇ ʙᴀɴ & ɪɴᴠɪᴛᴇ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪssɪᴏɴs.**"
                    )
            else:
                await done.edit_text(
                    "**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ᴜɴʙᴀɴ / ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ!**"
                )
        return

    # ── Conditions 4-6: private group (no username) ───────────────────────────
    if not is_admin:
        await done.edit_text("**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**")
        return

    # is_admin = True, no username → invite via link
    # First check if assistant is already in or banned
    try:
        userbot_member = await client.get_chat_member(chat_id, userbot_id)
        if userbot_member.status in [
            ChatMemberStatus.BANNED,
            ChatMemberStatus.RESTRICTED,
        ]:
            # Unban first, then invite
            try:
                await client.unban_chat_member(chat_id, userbot_id)
                await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴜɴʙᴀɴɴᴇᴅ, ɴᴏᴡ ɪɴᴠɪᴛɪɴɢ...**")
                await asyncio.sleep(1)
                invite_link = await client.create_chat_invite_link(chat_id, expire_date=None)
                await asyncio.sleep(2)
                await userbot.join_chat(invite_link.invite_link)
                await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴡᴀs ʙᴀɴɴᴇᴅ, ɴᴏᴡ ᴜɴʙᴀɴɴᴇᴅ ᴀɴᴅ ᴊᴏɪɴᴇᴅ ✅**")
            except UserAlreadyParticipant:
                await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
            except InviteRequestSent:
                try:
                    await client.approve_chat_join_request(chat_id, userbot_id)
                except Exception:
                    pass
            except Exception as e:
                await done.edit_text(
                    f"**➻ ᴀssɪsᴛᴀɴᴛ ɪs ʙᴀɴɴᴇᴅ ᴀɴᴅ ɪ ᴄᴀɴɴᴏᴛ ᴜɴʙᴀɴ.**\n"
                    f"**ᴘʟᴇᴀsᴇ ɢɪᴠᴇ ʙᴀɴ ᴘᴏᴡᴇʀ ᴏʀ ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ ᴛʜᴇɴ /userbotjoin**\n\n"
                    f"**➥ ɪᴅ »** @{userbot.username}"
                )
        elif userbot_member.status not in [
            ChatMemberStatus.LEFT,
            ChatMemberStatus.BANNED,
            ChatMemberStatus.RESTRICTED,
        ]:
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
        else:
            # LEFT — invite via link
            raise UserNotParticipant
    except (UserNotParticipant, Exception):
        # Assistant not in chat — create invite and join
        try:
            await done.edit_text("**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɪɴᴠɪᴛɪɴɢ ᴀssɪsᴛᴀɴᴛ...**")
            invite_link = await client.create_chat_invite_link(chat_id, expire_date=None)
            await asyncio.sleep(2)
            await userbot.join_chat(invite_link.invite_link)
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ.**")
        except UserAlreadyParticipant:
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
        except InviteRequestSent:
            try:
                await client.approve_chat_join_request(chat_id, userbot_id)
            except Exception:
                pass
        except Exception as e:
            await done.edit_text(
                f"**➻ ɪ ᴄᴀɴɴᴏᴛ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**\n"
                f"**[ ɪ ᴅᴏɴᴛ ʜᴀᴠᴇ ɪɴᴠɪᴛᴇ ᴜsᴇʀ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ]**\n\n"
                f"**➥ ɪᴅ »** @{userbot.username}"
            )


@Client.on_message(filters.command("userbotleave") & filters.group & admin_filter)
async def leave_one(client: Client, message):
    try:
        userbot = await get_assistant(message.chat.id)
        await userbot.leave_chat(message.chat.id)
        await client.send_message(
            message.chat.id, "**✅ ᴜsᴇʀʙᴏᴛ sᴜᴄᴄᴇssғᴜʟʟʏ ʟᴇғᴛ ᴛʜɪs Chat.**"
        )
    except Exception as e:
        print(e)


@Client.on_message(filters.command("leaveall") & SUDOERS)
async def leave_all(client: Client, message):
    if message.from_user.id not in SUDOERS:
        return
    left = 0
    failed = 0
    lol = await message.reply("🔄 **ᴜsᴇʀʙᴏᴛ** ʟᴇᴀᴠɪɴɢ ᴀʟʟ ᴄʜᴀᴛs !")
    try:
        userbot = await get_assistant(message.chat.id)
        async for dialog in userbot.get_dialogs():
            if dialog.chat.id == -1001735663878:
                continue
            try:
                await userbot.leave_chat(dialog.chat.id)
                left += 1
                await lol.edit(
                    f"**ᴜsᴇʀʙᴏᴛ ʟᴇᴀᴠɪɴɢ ᴀʟʟ ɢʀᴏᴜᴘ...**\n\n**ʟᴇғᴛ:** {left} ᴄʜᴀᴛs.\n**ғᴀɪʟᴇᴅ:** {failed} ᴄʜᴀᴛs."
                )
            except Exception:
                failed += 1
                await lol.edit(
                    f"**ᴜsᴇʀʙᴏᴛ ʟᴇᴀᴠɪɴɢ...**\n\n**ʟᴇғᴛ:** {left} chats.\n**ғᴀɪʟᴇᴅ:** {failed} chats."
                )
            await asyncio.sleep(3)
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
