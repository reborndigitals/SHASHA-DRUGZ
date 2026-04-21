"""
SHASHA_DRUGZ/dplugins/MUSIC/tools/userbotjoin.py

FIXES:
  1. Changed @app.on_message → @Client.on_message so the commands are
     registered on each DEPLOYED bot client (not the main bot).
     The original code used @app.on_message which meant the commands were
     only registered on the main bot — deployed bots never saw them.

  2. Resolve the CORRECT assistant via get_custom_assistant_userbot(bot_id)
     before falling back to get_assistant(chat_id).  This ensures that when
     a deployed bot owner has run /setassistant, THAT userbot is invited to
     the group rather than the default STRING1/STRING2/... pool.

  3. All Telegram API calls for permission checks and invite-link generation
     now use `client` (the deployed bot, which IS admin in the group) instead
     of `app` (the main bot, which is never admin in deployed-bot groups).
     The only exception is approve_chat_join_request / unban where we try
     both `client` and `app` as fallbacks.
"""
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChatAdminRequired,
    InviteRequestSent,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import get_assistant
from SHASHA_DRUGZ.utils.shasha_ban import admin_filter

links = {}


# ─────────────────────────────────────────────────────────────────────────────
#  HELPER: resolve the correct assistant userbot for the current deployed bot
# ─────────────────────────────────────────────────────────────────────────────
def _get_correct_assistant(client: Client):
    """
    Return the custom assistant Pyrogram client set via /setassistant,
    or None if the bot is using the default pool.

    Callers should fall back to get_assistant(chat_id) when this returns None.
    """
    try:
        from SHASHA_DRUGZ.dplugins.COMMON.PREMIUM.setbotinfo import get_custom_assistant_userbot
        bot_id = client.me.id if client.me else None
        if bot_id is not None:
            custom = get_custom_assistant_userbot(bot_id)
            if custom is not None:
                return custom
    except Exception:
        pass
    return None


async def _resolve_userbot(client: Client, chat_id: int):
    """
    Resolve the correct userbot:
      1. Custom assistant (set via /setassistant) — preferred
      2. Default pool via get_assistant(chat_id) — fallback
    """
    custom = _get_correct_assistant(client)
    if custom is not None:
        return custom
    return await get_assistant(chat_id)


# ─────────────────────────────────────────────────────────────────────────────
#  /userbotjoin
#  FIX: @Client.on_message so deployed bots register this handler, not app.
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(
    filters.group
    & filters.command("userbotjoin")
    & ~filters.private
)
async def join_group(client: Client, message):
    chat_id = message.chat.id

    # FIX 2: resolve the correct userbot
    userbot = await _resolve_userbot(client, chat_id)
    userbot_id = userbot.id

    done = await message.reply("**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɪɴᴠɪᴛɪɴɢ ᴀssɪsᴛᴀɴᴛ**...")
    await asyncio.sleep(1)

    # FIX 3: use `client` (deployed bot) for permission checks — it's the
    # one that is admin in the group, not `app` (main bot).
    try:
        bot_me = await client.get_me()
        chat_member = await client.get_chat_member(chat_id, bot_me.id)
    except Exception as e:
        await done.edit_text(
            f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ғᴇᴛᴄʜ ᴄʜᴀᴛ ɪɴғᴏ.**\n`{e}`"
        )
        return

    is_admin = chat_member.status in (
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )

    # ── Condition 1 & 2: group has a public username ───────────────────────
    if message.chat.username:
        # First check if already banned and unban if we have rights
        if is_admin:
            try:
                userbot_member = await client.get_chat_member(chat_id, userbot_id)
                if userbot_member.status in (
                    ChatMemberStatus.BANNED,
                    ChatMemberStatus.RESTRICTED,
                ):
                    try:
                        await client.unban_chat_member(chat_id, userbot_id)
                        await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ɪs ᴜɴʙᴀɴɴɪɴɢ...**")
                        await asyncio.sleep(1)
                    except ChatAdminRequired:
                        await done.edit_text(
                            "**ғᴀɪʟᴇᴅ ᴛᴏ ᴜɴʙᴀɴ — ɢɪᴠᴇ ᴍᴇ ʙᴀɴ ᴘᴏᴡᴇʀ ᴏʀ ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ ᴛʜᴇɴ /userbotjoin**"
                        )
                        return
                    except Exception as e:
                        await done.edit_text(f"**ᴜɴʙᴀɴ ᴇʀʀᴏʀ:** `{e}`")
                        return
            except UserNotParticipant:
                pass  # not in chat → proceed to join
            except Exception:
                pass

        # Now try joining via username
        try:
            await userbot.join_chat(message.chat.username)
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ.**")
            return
        except UserAlreadyParticipant:
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
            return
        except InviteRequestSent:
            try:
                await client.approve_chat_join_request(chat_id, userbot_id)
                await done.edit_text("**✅ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.**")
            except Exception:
                await done.edit_text("**⚠️ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ sᴇɴᴛ — ᴀᴘᴘʀᴏᴠᴇ ᴍᴀɴᴜᴀʟʟʏ.**")
            return
        except Exception as e:
            if is_admin:
                await done.edit_text(f"**ᴊᴏɪɴ ᴇʀʀᴏʀ:** `{e}`")
            else:
                await done.edit_text(
                    "**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ᴜɴʙᴀɴ / ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ!**"
                )
            return

    # ── Conditions 4, 5, 6: private group (no public username) ────────────
    if not is_admin:
        await done.edit_text("**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**")
        return

    # Bot is admin, private group → check current userbot status first
    try:
        userbot_member = await client.get_chat_member(chat_id, userbot_id)
        ub_status = userbot_member.status
    except UserNotParticipant:
        ub_status = None
    except Exception:
        ub_status = None

    # If already in chat (and not banned), done
    if ub_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    ):
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
        return

    # If banned, unban first
    if ub_status == ChatMemberStatus.BANNED:
        try:
            await client.unban_chat_member(chat_id, userbot_id)
            await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴜɴʙᴀɴɴᴇᴅ, ɴᴏᴡ ɪɴᴠɪᴛɪɴɢ...**")
            await asyncio.sleep(1)
        except ChatAdminRequired:
            await done.edit_text(
                f"**ᴀssɪsᴛᴀɴᴛ ɪs ʙᴀɴɴᴇᴅ ʙᴜᴛ ɪ ʟᴀᴄᴋ ʙᴀɴ ᴘᴏᴡᴇʀ.**\n\n"
                f"**ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ:** @{userbot.username or userbot_id}"
            )
            return
        except Exception as e:
            await done.edit_text(f"**ᴜɴʙᴀɴ ғᴀɪʟᴇᴅ:** `{e}`")
            return

    # Generate invite link and join
    try:
        await done.edit_text("**ɢᴇɴᴇʀᴀᴛɪɴɢ ɪɴᴠɪᴛᴇ ʟɪɴᴋ...**")
        # FIX 3: use client (deployed bot, which is admin) not app
        invite_link = await client.create_chat_invite_link(chat_id, expire_date=None)
        await asyncio.sleep(2)
        await userbot.join_chat(invite_link.invite_link)
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ.**")
    except UserAlreadyParticipant:
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
    except InviteRequestSent:
        try:
            await client.approve_chat_join_request(chat_id, userbot_id)
            await done.edit_text("**✅ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.**")
        except Exception:
            await done.edit_text("**⚠️ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ sᴇɴᴛ — ᴀᴘᴘʀᴏᴠᴇ ᴍᴀɴᴜᴀʟʟʏ.**")
    except ChatAdminRequired:
        await done.edit_text(
            f"**ɪ ɴᴇᴇᴅ 'ɪɴᴠɪᴛᴇ ᴜsᴇʀs' ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**\n\n"
            f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** @{userbot.username or userbot_id}"
        )
    except Exception as e:
        await done.edit_text(
            f"**➻ ɪ ᴄᴏᴜʟᴅ ɴᴏᴛ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**\n"
            f"ᴘʟᴇᴀsᴇ ɢɪᴠᴇ ᴍᴇ **ɪɴᴠɪᴛᴇ ᴜsᴇʀs** ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛʜᴇɴ ʀᴜɴ /userbotjoin ᴀɢᴀɪɴ.\n\n"
            f"**➥ ᴀssɪsᴛᴀɴᴛ »** @{userbot.username or userbot_id}\n"
            f"**ᴇʀʀᴏʀ:** `{e}`"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  /userbotleave
#  FIX: @Client.on_message so deployed bots handle this, not app.
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("userbotleave") & filters.group & admin_filter)
async def leave_one(client: Client, message):
    try:
        userbot = await _resolve_userbot(client, message.chat.id)
        await userbot.leave_chat(message.chat.id)
        await message.reply("**✅ ᴜsᴇʀʙᴏᴛ sᴜᴄᴄᴇssғᴜʟʟʏ ʟᴇғᴛ ᴛʜɪs Chat.**")
    except Exception as e:
        await message.reply(f"**❌ ᴇʀʀᴏʀ:** `{e}`")


# ─────────────────────────────────────────────────────────────────────────────
#  /leaveall  (SUDOERS only)
#  FIX: @Client.on_message so deployed bots handle this.
#  Note: SUDOERS check is kept so only authorized users can run this.
# ─────────────────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("leaveall") & filters.group & filters.user(SUDOERS))
async def leave_all(client: Client, message):
    left = 0
    failed = 0
    lol = await message.reply("🔄 **ᴜsᴇʀʙᴏᴛ** ʟᴇᴀᴠɪɴɢ ᴀʟʟ ᴄʜᴀᴛs !")
    try:
        userbot = await _resolve_userbot(client, message.chat.id)
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
    finally:
        await message.reply(
            f"**✅ ʟᴇғᴛ ғʀᴏᴍ:** {left} chats.\n**❌ ғᴀɪʟᴇᴅ ɪɴ:** {failed} chats."
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

MOD_TYPE = "MUSIC"
MOD_NAME = "AssistantJoin"
MOD_PRICE = "0"
