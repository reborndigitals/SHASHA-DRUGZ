"""
assistant_guard.py
──────────────────
Auto-unban + auto-join the assistant userbot whenever a /play command is
issued in a group where the assistant is missing or banned.
Drop this file into your SHASHA_DRUGZ/dplugins/COMMON/PREMIUM/ directory.
No changes needed in music.py or start.py — this module runs transparently
as a middleware layer that fires before the PlayWrapper decorator processes
the command.
Logic flow on every /play (and variants) in a group:
  1. Get the assistant assigned to this chat.
  2. Check assistant's membership status via the main bot (app).
  3. If BANNED → unban first (needs ban permission on bot).
  4. If RESTRICTED → treat as already in chat (no rejoin needed).
  5. If not in the group at all → invite via username or generated invite link.
  6. If already a member → do nothing (fast-path, no extra API calls).
  7. All steps run silently in a background task so the play response is
     not delayed.
Only the assistant is ever touched — regular users are never affected.
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
    # FIX 1: Wrap get_chat in its own try/except to handle CHANNEL_INVALID
    # on supergroups that aren't cached by the bot yet.
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
        # Group has join requests — approve immediately via main bot
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
        # FIX 3: create_chat_invite_link is more reliable than export_chat_invite_link
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


# ──────────────────────────────────────────────────────────────────────────────
#  CORE: ensure assistant is present (unban if needed, then join)
# ──────────────────────────────────────────────────────────────────────────────

async def ensure_assistant_in_chat(chat_id: int) -> bool:
    """
    Silently ensure the assistant is a member of the group.
    Called as a background task — never blocks the play response.
    Returns True if the assistant is (or becomes) a member.
    """
    try:
        userbot = await get_assistant(chat_id)
    except Exception as e:
        logger.warning(f"[assistant_guard] Could not get assistant for {chat_id}: {e}")
        return False

    assistant_id = userbot.id

    # ── Step 1: check current status ──────────────────────────────────────────
    status = await _get_assistant_status(chat_id, assistant_id)

    if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        # Already in — nothing to do
        return True

    # FIX 2: RESTRICTED means the assistant IS in the chat, just with limits.
    # Attempting to rejoin a restricted member causes unnecessary API errors.
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
        # Give Telegram a moment to process the unban before joining
        await asyncio.sleep(2)

    # ── Step 3: join the chat ─────────────────────────────────────────────────
    # Try username first (no extra permission needed on public groups)
    if await _try_join_via_username(userbot, chat_id):
        return True

    # Fallback: invite link (requires can_invite_users on main bot)
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
    Intercept every play command in a group and silently ensure the assistant
    is present. Runs at handler priority -10 so it fires before PlayWrapper.
    Does NOT stop propagation — the play command continues normally.
    """
    chat_id = message.chat.id
    # Fire-and-forget: don't await, don't delay the play response
    asyncio.create_task(ensure_assistant_in_chat(chat_id))
    # Let the message propagate to the real play handler
    # (do NOT call message.stop_propagation())


# ──────────────────────────────────────────────────────────────────────────────
#  DECORATOR  (optional — for use in PlayWrapper if you prefer explicit hooking)
# ──────────────────────────────────────────────────────────────────────────────

def with_assistant_guard(func):
    """
    Optional decorator you can wrap around any async handler to ensure the
    assistant is in the chat before the handler runs.
    Usage in music.py:
        @Client.on_message(...)
        @PlayWrapper
        @with_assistant_guard          ← add this
        async def play_commnd(...):
            ...
    Unlike the interceptor above (which is fire-and-forget), this decorator
    AWAITS the guard so the assistant is guaranteed to be present before the
    stream starts. Use it if you hit race conditions.
    """
    @wraps(func)
    async def wrapper(client, message: Message, *args, **kwargs):
        chat_id = message.chat.id
        # Run guard concurrently with the start of the play pipeline
        guard_task = asyncio.create_task(ensure_assistant_in_chat(chat_id))
        try:
            result = await func(client, message, *args, **kwargs)
        finally:
            # Ensure guard task is awaited to surface any exceptions in logs
            try:
                await guard_task
            except Exception as e:
                logger.debug(f"[assistant_guard] Background guard error: {e}")
        return result
    return wrapper

MOD_TYPE = "MUSIC
MOD_NAME = "assist_guard"
MOD_PRICE = "0"
