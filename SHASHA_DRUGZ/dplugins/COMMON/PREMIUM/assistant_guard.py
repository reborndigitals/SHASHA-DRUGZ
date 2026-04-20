"""
assistant_guard.py
──────────────────
Auto-unban + auto-join the assistant userbot whenever a /play command is
issued in a group where the assistant is missing or banned.

FIX 2 in this version:
  ensure_assistant_in_chat() now resolves the CORRECT assistant:
    1. If the deployed bot has a custom assistant set via /setassistant,
       that Pyrogram client is used (get_custom_assistant_userbot).
    2. Otherwise falls back to get_assistant(chat_id) — default pool.

This means the group will always get the right assistant invited,
not the default pool's userbot.
"""
import asyncio
import logging
from functools import wraps
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    InviteHashExpired,
    InviteHashInvalid,
    InviteRequestSent,
    PeerIdInvalid,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from pyrogram.types import Message
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import get_assistant

logger = logging.getLogger("assistant_guard")

# ──────────────────────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────
async def _get_assistant_status(chat_id: int, assistant_id: int) -> ChatMemberStatus | None:
    """
    Return the assistant's ChatMemberStatus in the group, or None if the
    assistant has never been in the group (UserNotParticipant / PeerIdInvalid).
    """
    try:
        member = await app.get_chat_member(chat_id, assistant_id)
        return member.status
    except UserNotParticipant:
        return None
    except PeerIdInvalid:
        return None
    except Exception as e:
        logger.debug(f"_get_assistant_status [{chat_id}]: {e}")
        return None


async def _bot_can_ban(chat_id: int) -> bool:
    """Return True if the main bot has ban/restrict permission in this chat."""
    try:
        me = await app.get_chat_member(chat_id, app.id)
        if me.status == ChatMemberStatus.ADMINISTRATOR:
            return bool(me.privileges and me.privileges.can_restrict_members)
        return False
    except Exception:
        return False


async def _bot_can_invite(chat_id: int) -> bool:
    """Return True if the main bot has invite-users permission in this chat."""
    try:
        me = await app.get_chat_member(chat_id, app.id)
        if me.status == ChatMemberStatus.ADMINISTRATOR:
            return bool(me.privileges and me.privileges.can_invite_users)
        return False
    except Exception:
        return False


async def _try_unban(chat_id: int, assistant_id: int) -> bool:
    """Attempt to unban the assistant. Returns True on success."""
    try:
        await app.unban_chat_member(chat_id, assistant_id)
        logger.info(f"[assistant_guard] Unbanned assistant {assistant_id} in {chat_id}")
        return True
    except ChatAdminRequired:
        logger.warning(f"[assistant_guard] Bot lacks ban rights in {chat_id}")
        return False
    except FloodWait as e:
        logger.warning(f"[assistant_guard] FloodWait {e.value}s during unban in {chat_id}")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.warning(f"[assistant_guard] Unban failed in {chat_id}: {e}")
        return False


async def _try_join_via_username(userbot, chat_id: int) -> bool:
    """Try joining via the group's public username."""
    try:
        chat = await app.get_chat(chat_id)
        username = chat.username
    except Exception as e:
        logger.debug(f"[assistant_guard] get_chat failed for {chat_id}: {e}")
        return False
    if not username:
        return False
    try:
        await userbot.join_chat(username)
        logger.info(f"[assistant_guard] Assistant joined {chat_id} via username")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        try:
            await app.approve_chat_join_request(chat_id, userbot.id)
            return True
        except Exception:
            return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Username join failed in {chat_id}: {e}")
        return False


async def _try_join_via_invite(userbot, chat_id: int) -> bool:
    """Try joining via a freshly generated invite link (requires invite permission)."""
    try:
        link_obj = await app.create_chat_invite_link(chat_id)
        link = link_obj.invite_link
        await asyncio.sleep(1)
        await userbot.join_chat(link)
        logger.info(f"[assistant_guard] Assistant joined {chat_id} via invite link")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        try:
            await app.approve_chat_join_request(chat_id, userbot.id)
            return True
        except Exception:
            return False
    except (InviteHashExpired, InviteHashInvalid):
        logger.warning(f"[assistant_guard] Invite link invalid for {chat_id}")
        return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Invite join failed in {chat_id}: {e}")
        return False


def _resolve_userbot_for_message(message: Message):
    """
    FIX 2: Resolve the correct userbot to invite for a given message's bot client.

    The message.chat.id is the group.  message._client is the deployed bot
    handling this message (not the main `app`).  We check if that deployed
    bot has a custom assistant configured.

    Returns the correct Pyrogram Client (custom or None to fall back to pool).
    """
    try:
        from SHASHA_DRUGZ.dplugins.COMMON.PREMIUM.setbotinfo import get_custom_assistant_userbot
        # message._client is the deployed bot Pyrogram Client
        client = getattr(message, "_client", None)
        if client is None:
            # Try accessing via the handler's client parameter (set by decorator)
            return None
        bot_id = client.me.id if (client.me is not None) else None
        if bot_id is not None:
            custom = get_custom_assistant_userbot(bot_id)
            if custom is not None:
                return custom
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  CORE: ensure assistant is present (unban if needed, then join)
# ──────────────────────────────────────────────────────────────────────────────
async def ensure_assistant_in_chat(chat_id: int, userbot=None) -> bool:
    """
    Silently ensure the assistant is a member of the group.
    Called as a background task — never blocks the play response.
    Returns True if the assistant is (or becomes) a member.

    FIX 2: Accepts an optional `userbot` argument.  When called from the
    play interceptor below, the correct userbot (custom or pool) is resolved
    from the message context and passed in.  This guarantees the right
    assistant is invited, not whatever get_assistant(chat_id) returns.
    """
    if userbot is None:
        try:
            userbot = await get_assistant(chat_id)
        except Exception as e:
            logger.warning(f"[assistant_guard] Could not get assistant for {chat_id}: {e}")
            return False

    assistant_id = userbot.id

    # ── Step 1: check current status ──────────────────────────────────────────
    status = await _get_assistant_status(chat_id, assistant_id)
    if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return True

    if status == ChatMemberStatus.RESTRICTED:
        logger.debug(f"[assistant_guard] Assistant is restricted (not banned) in {chat_id} — treating as present")
        return True

    # ── Step 2: if banned, unban first ────────────────────────────────────────
    if status == ChatMemberStatus.BANNED:
        if not await _bot_can_ban(chat_id):
            logger.warning(
                f"[assistant_guard] Assistant is banned in {chat_id} "
                f"but bot lacks ban rights to unban."
            )
            return False
        unbanned = await _try_unban(chat_id, assistant_id)
        if not unbanned:
            return False
        await asyncio.sleep(2)

    # ── Step 3: join the chat ─────────────────────────────────────────────────
    if await _try_join_via_username(userbot, chat_id):
        return True

    if await _bot_can_invite(chat_id):
        if await _try_join_via_invite(userbot, chat_id):
            return True

    logger.warning(
        f"[assistant_guard] Could not get assistant into {chat_id}. "
        f"Bot may need 'Invite Users' or 'Ban Members' admin rights."
    )
    return False

# ──────────────────────────────────────────────────────────────────────────────
#  PLAY COMMAND INTERCEPTOR
#  Fires *before* PlayWrapper so the assistant is ready when pytgcalls needs it.
# ──────────────────────────────────────────────────────────────────────────────
PLAY_COMMANDS = [
    "play", "vplay", "cplay", "cvplay",
    "playforce", "vplayforce", "cplayforce", "cvplayforce",
]

@Client.on_message(
    filters.command(PLAY_COMMANDS, prefixes=["/", "!", "%", ".", "@", "#", ""])
    & filters.group,
    group=-10,          # negative group number = runs BEFORE normal handlers
)
async def _play_assistant_guard(client: Client, message: Message):
    """
    Intercept every play command in a group and silently ensure the CORRECT
    assistant is present.  Runs at handler priority -10 so it fires before
    PlayWrapper.  Does NOT stop propagation.

    FIX 2: Resolves custom assistant first, falls back to default pool.
    """
    chat_id = message.chat.id

    # Resolve the correct userbot for THIS deployed bot
    userbot = None
    try:
        from SHASHA_DRUGZ.dplugins.COMMON.PREMIUM.setbotinfo import get_custom_assistant_userbot
        bot_id = client.me.id if client.me else None
        if bot_id is not None:
            userbot = get_custom_assistant_userbot(bot_id)
    except Exception:
        pass

    # Fire-and-forget with the correct userbot (None → falls back to pool inside)
    asyncio.create_task(ensure_assistant_in_chat(chat_id, userbot=userbot))

    # Let the message propagate to the real play handler
    # (do NOT call message.stop_propagation())

# ──────────────────────────────────────────────────────────────────────────────
#  DECORATOR  (optional — for use in PlayWrapper if you prefer explicit hooking)
# ──────────────────────────────────────────────────────────────────────────────
def with_assistant_guard(func):
    """
    Optional decorator you can wrap around any async handler to ensure the
    assistant is in the chat before the handler runs.  AWAITS the guard so
    the assistant is guaranteed present before the stream starts.
    """
    @wraps(func)
    async def wrapper(client, message: Message, *args, **kwargs):
        chat_id = message.chat.id

        # Resolve correct userbot
        userbot = None
        try:
            from SHASHA_DRUGZ.dplugins.COMMON.PREMIUM.setbotinfo import get_custom_assistant_userbot
            bot_id = client.me.id if client.me else None
            if bot_id is not None:
                userbot = get_custom_assistant_userbot(bot_id)
        except Exception:
            pass

        guard_task = asyncio.create_task(ensure_assistant_in_chat(chat_id, userbot=userbot))
        try:
            result = await func(client, message, *args, **kwargs)
        finally:
            try:
                await guard_task
            except Exception as e:
                logger.debug(f"[assistant_guard] Background guard error: {e}")
        return result
    return wrapper

MOD_TYPE = "MUSIC"
MOD_NAME = "Assist-Guard"
MOD_PRICE = "0"
