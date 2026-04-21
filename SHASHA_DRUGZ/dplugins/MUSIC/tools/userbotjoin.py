# SHASHA_DRUGZ/dplugins/MUSIC/tools/userbotjoin.py
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

# ─── Fix: resolve SUDOERS to a plain list of integer user IDs ────────────────
def _sudoers_ids():
    """
    SUDOERS may be a Pyrogram filter object, a list of User objects, a list of
    ints, or a set of ints.  filters.user() only accepts ints — extract them.
    """
    raw = SUDOERS
    # Already a plain list/set/tuple of ints
    if isinstance(raw, (list, set, tuple)):
        ids = []
        for item in raw:
            if isinstance(item, int):
                ids.append(item)
            elif hasattr(item, "id"):          # User / Chat object
                ids.append(item.id)
        return ids
    # Pyrogram AndFilter / OrFilter wrapping user IDs stored in .data
    if hasattr(raw, "data"):
        data = raw.data
        if isinstance(data, (list, set, tuple)):
            ids = []
            for item in data:
                if isinstance(item, int):
                    ids.append(item)
                elif hasattr(item, "id"):
                    ids.append(item.id)
            return ids
    # Single User object
    if hasattr(raw, "id"):
        return [raw.id]
    # Fallback: try int cast
    try:
        return [int(raw)]
    except Exception:
        return []

SUDOERS_IDS = _sudoers_ids()

# ─── Helper: get the correct userbot + its numeric ID ────────────────────────
async def _get_client_id(userbot: Client) -> int:
    """
    Safely get the Telegram user ID from a Pyrogram Client.
    FIX: Pyrogram Client does NOT have a plain .id attribute — it lives on
    client.me.id after start(). This function handles all cases safely.
    """
    # Preferred: client.me is populated after start()
    if userbot.me is not None:
        return userbot.me.id
    # SHASHA's custom Client subclass sets self.id = self.me.id in start()
    val = getattr(userbot, "id", None)
    if isinstance(val, int):
        return val
    # Last resort: API call
    me = await userbot.get_me()
    return me.id


async def _resolve_userbot(client: Client, chat_id: int):
    """
    Return (userbot_client, userbot_telegram_id).
    Priority:
      1. Custom assistant set via /setassistant for this deployed bot.
      2. Default pool via get_assistant(chat_id).
    """
    try:
        from SHASHA_DRUGZ.dplugins.COMMON.PREMIUM.setbotinfo import get_custom_assistant_userbot
        bot_id = client.me.id if client.me else None
        if bot_id is not None:
            custom = get_custom_assistant_userbot(bot_id)
            if custom is not None:
                uid = await _get_client_id(custom)
                return custom, uid
    except Exception:
        pass
    userbot = await get_assistant(chat_id)
    uid = await _get_client_id(userbot)
    return userbot, uid


def _ub_username(userbot: Client, fallback_id: int) -> str:
    """Safe username string for error messages."""
    try:
        if userbot.me and userbot.me.username:
            return f"@{userbot.me.username}"
    except Exception:
        pass
    return str(fallback_id)


# ─── /userbotjoin ─────────────────────────────────────────────────────────────
@Client.on_message(
    filters.group
    & filters.command("userbotjoin")
    & ~filters.private
)
async def join_group(client: Client, message):
    chat_id = message.chat.id
    try:
        userbot, userbot_id = await _resolve_userbot(client, chat_id)
    except Exception as e:
        await message.reply(f"**❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ʀᴇsᴏʟᴠᴇ ᴀssɪsᴛᴀɴᴛ:**\n`{e}`")
        return

    done = await message.reply("**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ɪɴᴠɪᴛɪɴɢ ᴀssɪsᴛᴀɴᴛ**...")
    await asyncio.sleep(1)

    # Check admin status using the deployed bot (client), not app
    try:
        bot_me = client.me or await client.get_me()
        chat_member = await client.get_chat_member(chat_id, bot_me.id)
        is_admin = chat_member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception as e:
        await done.edit_text(f"**❌ ғᴀɪʟᴇᴅ ᴛᴏ ғᴇᴛᴄʜ ᴄʜᴀᴛ ɪɴғᴏ.**\n`{e}`")
        return

    # ── PUBLIC GROUP (has username) ───────────────────────────────────────────
    if message.chat.username:
        # Admin: check for ban and unban first
        if is_admin:
            try:
                ub_member = await client.get_chat_member(chat_id, userbot_id)
                if ub_member.status in (ChatMemberStatus.BANNED, ChatMemberStatus.RESTRICTED):
                    try:
                        await client.unban_chat_member(chat_id, userbot_id)
                        await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴜɴʙᴀɴɴᴇᴅ, ɴᴏᴡ ᴊᴏɪɴɪɴɢ...**")
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
                pass
            except Exception:
                pass

        # Join via username
        try:
            await userbot.join_chat(message.chat.username)
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴊᴏɪɴᴇᴅ.**")
        except UserAlreadyParticipant:
            await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
        except InviteRequestSent:
            try:
                await client.approve_chat_join_request(chat_id, userbot_id)
                await done.edit_text("**✅ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.**")
            except Exception:
                await done.edit_text("**⚠️ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ sᴇɴᴛ — ᴀᴘᴘʀᴏᴠᴇ ᴍᴀɴᴜᴀʟʟʏ.**")
        except Exception as e:
            if is_admin:
                await done.edit_text(
                    "**ғᴀɪʟᴇᴅ ᴛᴏ ᴊᴏɪɴ — ɢɪᴠᴇ ʙᴀɴ + ɪɴᴠɪᴛᴇ ᴘᴏᴡᴇʀ ᴏʀ ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ ᴛʜᴇɴ /userbotjoin**"
                )
            else:
                await done.edit_text(
                    "**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ᴜɴʙᴀɴ / ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ!**"
                )
        return

    # ── PRIVATE GROUP (no username) ───────────────────────────────────────────
    if not is_admin:
        await done.edit_text("**ɪ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛᴏ ɪɴᴠɪᴛᴇ ᴍʏ ᴀssɪsᴛᴀɴᴛ.**")
        return

    # Bot is admin — check current userbot status
    try:
        ub_member = await client.get_chat_member(chat_id, userbot_id)
        ub_status = ub_member.status
    except UserNotParticipant:
        ub_status = None
    except Exception:
        ub_status = None

    # Already in chat
    if ub_status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    ):
        await done.edit_text("**✅ ᴀssɪsᴛᴀɴᴛ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ.**")
        return

    # Banned — unban first
    if ub_status == ChatMemberStatus.BANNED:
        try:
            await client.unban_chat_member(chat_id, userbot_id)
            await done.edit_text("**ᴀssɪsᴛᴀɴᴛ ᴜɴʙᴀɴɴᴇᴅ, ɴᴏᴡ ɪɴᴠɪᴛɪɴɢ...**")
            await asyncio.sleep(1)
        except ChatAdminRequired:
            await done.edit_text(
                f"**ᴀssɪsᴛᴀɴᴛ ɪs ʙᴀɴɴᴇᴅ ʙᴜᴛ ɪ ʟᴀᴄᴋ ʙᴀɴ ᴘᴏᴡᴇʀ.**\n\n"
                f"**ᴜɴʙᴀɴ ᴍᴀɴᴜᴀʟʟʏ:** {_ub_username(userbot, userbot_id)}"
            )
            return
        except Exception as e:
            await done.edit_text(f"**ᴜɴʙᴀɴ ғᴀɪʟᴇᴅ:** `{e}`")
            return

    # Generate invite link and join
    try:
        await done.edit_text("**ɢᴇɴᴇʀᴀᴛɪɴɢ ɪɴᴠɪᴛᴇ ʟɪɴᴋ...**")
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
            f"**ɪ ɴᴇᴇᴅ 'ɪɴᴠɪᴛᴇ ᴜsᴇʀs' ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ.**\n\n"
            f"**➥ ᴀssɪsᴛᴀɴᴛ ɪᴅ »** {_ub_username(userbot, userbot_id)}"
        )
    except Exception as e:
        await done.edit_text(
            f"**➻ ᴄᴏᴜʟᴅ ɴᴏᴛ ɪɴᴠɪᴛᴇ ᴀssɪsᴛᴀɴᴛ.**\n"
            f"ɢɪᴠᴇ ᴍᴇ **ɪɴᴠɪᴛᴇ ᴜsᴇʀs** ᴀᴅᴍɪɴ ᴘᴏᴡᴇʀ ᴛʜᴇɴ /userbotjoin ᴀɢᴀɪɴ.\n\n"
            f"**➥ ᴀssɪsᴛᴀɴᴛ »** {_ub_username(userbot, userbot_id)}\n"
            f"**ᴇʀʀᴏʀ:** `{e}`"
        )


# ─── /userbotleave ────────────────────────────────────────────────────────────
@Client.on_message(filters.command("userbotleave") & filters.group & admin_filter)
async def leave_one(client: Client, message):
    try:
        userbot, _ = await _resolve_userbot(client, message.chat.id)
        await userbot.leave_chat(message.chat.id)
        await message.reply("**✅ ᴜsᴇʀʙᴏᴛ sᴜᴄᴄᴇssғᴜʟʟʏ ʟᴇғᴛ ᴛʜɪs Chat.**")
    except Exception as e:
        await message.reply(f"**❌ ᴇʀʀᴏʀ:** `{e}`")


# ─── /leaveall ────────────────────────────────────────────────────────────────
@Client.on_message(
    filters.command("leaveall")
    & filters.group
    & filters.user(SUDOERS_IDS)          # ← fixed: plain list of ints
)
async def leave_all(client: Client, message):
    left = 0
    failed = 0
    lol = await message.reply("🔄 **ᴜsᴇʀʙᴏᴛ** ʟᴇᴀᴠɪɴɢ ᴀʟʟ ᴄʜᴀᴛs !")
    try:
        userbot, _ = await _resolve_userbot(client, message.chat.id)
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
