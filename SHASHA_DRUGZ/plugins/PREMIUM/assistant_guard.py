# SHASHA_DRUGZ/plugins/PREMIUM/assistant_guard.py
"""
assistant_guard.py
──────────────────
Auto-unban + auto-join the assistant userbot whenever a /play command is
issued in a group where the assistant is missing or banned.

Logic flow on every /play (and variants) in a group:
  1. Get the assistant assigned to this chat.
  2. Check assistant's membership status via get_chat_member.
  3. MEMBER / ADMINISTRATOR / OWNER → already in, do nothing (fast path).
  4. RESTRICTED → already in the chat (just limited), do nothing.
  5. BANNED → try to unban first, then join.
  6. None (not in chat at all) → try join via username, then invite link.
  7. All steps run in a background task — play response is never delayed.
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
    ChatWriteForbidden,
    ChannelPrivate,
)
from pyrogram.types import Message, ChatPrivileges
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import get_assistant

logger = logging.getLogger("assistant_guard")

# ─── In-memory set to avoid re-checking the same chat repeatedly ─────────────
# Once confirmed present, skip the check for 10 minutes.
_confirmed_chats: dict = {}   # chat_id → timestamp
_RECHECK_SECONDS = 600        # 10 minutes


def _is_recently_confirmed(chat_id: int) -> bool:
    import time
    ts = _confirmed_chats.get(chat_id, 0)
    return (time.time() - ts) < _RECHECK_SECONDS


def _mark_confirmed(chat_id: int):
    import time
    _confirmed_chats[chat_id] = time.time()


def _clear_confirmed(chat_id: int):
    _confirmed_chats.pop(chat_id, None)


# ─── Get assistant member status — the ONLY reliable way ─────────────────────
async def _get_assistant_status(chat_id: int, assistant_id: int):
    """
    Returns ChatMemberStatus or None.
    None means UserNotParticipant (never joined or was removed).
    Handles all Pyrogram exceptions gracefully.
    """
    try:
        member = await app.get_chat_member(chat_id, assistant_id)
        return member.status
    except UserNotParticipant:
        return None
    except PeerIdInvalid:
        logger.debug(f"[assistant_guard] PeerIdInvalid for chat {chat_id}")
        return None
    except (ChannelPrivate, ChatWriteForbidden):
        logger.debug(f"[assistant_guard] Private/forbidden chat {chat_id}")
        return None
    except FloodWait as e:
        logger.warning(f"[assistant_guard] FloodWait {e.value}s checking status in {chat_id}")
        await asyncio.sleep(e.value)
        return None
    except Exception as e:
        logger.debug(f"[assistant_guard] get_chat_member error in {chat_id}: {e}")
        return None


# ─── Check bot's own permissions ─────────────────────────────────────────────
async def _bot_has_permission(chat_id: int, perm: str) -> bool:
    """
    Check if the main bot has a specific admin permission.
    perm: 'can_restrict_members' | 'can_invite_users'
    """
    try:
        me = await app.get_chat_member(chat_id, app.id)
        if me.status == ChatMemberStatus.ADMINISTRATOR:
            return bool(me.privileges and getattr(me.privileges, perm, False))
        if me.status == ChatMemberStatus.OWNER:
            return True
        return False
    except Exception:
        return False


# ─── Unban ────────────────────────────────────────────────────────────────────
async def _try_unban(chat_id: int, assistant_id: int) -> bool:
    try:
        await app.unban_chat_member(chat_id, assistant_id)
        logger.info(f"[assistant_guard] Unbanned assistant {assistant_id} in {chat_id}")
        return True
    except ChatAdminRequired:
        logger.warning(f"[assistant_guard] Bot lacks ban rights in {chat_id}")
        return False
    except FloodWait as e:
        logger.warning(f"[assistant_guard] FloodWait {e.value}s during unban in {chat_id}")
        await asyncio.sleep(min(e.value, 10))
        return False
    except Exception as e:
        logger.warning(f"[assistant_guard] Unban failed in {chat_id}: {e}")
        return False


# ─── Join via public username ─────────────────────────────────────────────────
async def _try_join_via_username(userbot: Client, chat_id: int) -> bool:
    try:
        chat = await app.get_chat(chat_id)
        username = getattr(chat, "username", None)
        if not username:
            return False
        await userbot.join_chat(username)
        logger.info(f"[assistant_guard] Assistant joined {chat_id} via @{username}")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        try:
            await app.approve_chat_join_request(chat_id, (await userbot.get_me()).id)
            return True
        except Exception:
            return False
    except FloodWait as e:
        await asyncio.sleep(min(e.value, 10))
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Username join failed in {chat_id}: {e}")
        return False


# ─── Join via invite link ─────────────────────────────────────────────────────
async def _try_join_via_invite(userbot: Client, chat_id: int) -> bool:
    """
    Tries create_chat_invite_link first (more reliable), falls back to
    export_chat_invite_link. Both require can_invite_users on the main bot.
    """
    link = None

    # Method 1: create a fresh single-use invite link
    try:
        link_obj = await app.create_chat_invite_link(chat_id)
        link = link_obj.invite_link
    except Exception:
        pass

    # Method 2: fall back to the permanent invite link
    if not link:
        try:
            link = await app.export_chat_invite_link(chat_id)
        except Exception as e:
            logger.debug(f"[assistant_guard] Could not get invite link for {chat_id}: {e}")
            return False

    try:
        await asyncio.sleep(1)
        await userbot.join_chat(link)
        logger.info(f"[assistant_guard] Assistant joined {chat_id} via invite link")
        return True
    except UserAlreadyParticipant:
        return True
    except InviteRequestSent:
        try:
            await app.approve_chat_join_request(chat_id, (await userbot.get_me()).id)
            return True
        except Exception:
            return False
    except (InviteHashExpired, InviteHashInvalid):
        logger.warning(f"[assistant_guard] Invite link expired/invalid for {chat_id}")
        return False
    except FloodWait as e:
        await asyncio.sleep(min(e.value, 10))
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Invite join failed in {chat_id}: {e}")
        return False


# ─── Promote assistant to admin (if bot has that right) ──────────────────────
async def _try_promote_assistant(chat_id: int, assistant_id: int) -> bool:
    """
    Promotes the assistant to admin with the permissions needed for voice chats.
    Only called if the bot itself is an admin with can_manage_chat.
    """
    try:
        await app.promote_chat_member(
            chat_id,
            assistant_id,
            privileges=ChatPrivileges(
                can_manage_chat=True,
                can_manage_video_chats=True,
            ),
        )
        logger.info(f"[assistant_guard] Promoted assistant {assistant_id} in {chat_id}")
        return True
    except ChatAdminRequired:
        logger.debug(f"[assistant_guard] Bot cannot promote in {chat_id}")
        return False
    except Exception as e:
        logger.debug(f"[assistant_guard] Promote failed in {chat_id}: {e}")
        return False


# ─── CORE: ensure assistant is present ───────────────────────────────────────
async def ensure_assistant_in_chat(chat_id: int) -> bool:
    """
    Silently ensure the assistant is a member of the group.
    Uses a 10-minute in-memory cache to avoid redundant API calls.

    Status handling:
      MEMBER / ADMINISTRATOR / OWNER → present, cache and return True
      RESTRICTED                     → present (limited perms), cache and return True
      BANNED                         → unban then join
      None (not participant)         → join via username or invite link
    """
    # Fast path: recently confirmed present
    if _is_recently_confirmed(chat_id):
        return True

    try:
        userbot = await get_assistant(chat_id)
    except Exception as e:
        logger.warning(f"[assistant_guard] Could not get assistant for {chat_id}: {e}")
        return False

    assistant_id = userbot.id

    # ── Step 1: check current membership status ───────────────────────────────
    status = await _get_assistant_status(chat_id, assistant_id)

    # Already present (including restricted = limited but in chat)
    if status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    ):
        _mark_confirmed(chat_id)
        return True

    # ── Step 2: banned → unban first ─────────────────────────────────────────
    if status == ChatMemberStatus.BANNED:
        _clear_confirmed(chat_id)
        can_ban = await _bot_has_permission(chat_id, "can_restrict_members")
        if not can_ban:
            logger.warning(
                f"[assistant_guard] Assistant banned in {chat_id} but bot "
                f"lacks can_restrict_members — cannot unban."
            )
            return False
        ok = await _try_unban(chat_id, assistant_id)
        if not ok:
            return False
        await asyncio.sleep(2)

    # ── Step 3: not in chat (None) or just unbanned → join ───────────────────
    _clear_confirmed(chat_id)

    # Try public username first (works for public groups, no extra perm needed)
    if await _try_join_via_username(userbot, chat_id):
        _mark_confirmed(chat_id)
        return True

    # Try invite link (requires can_invite_users on the main bot)
    can_invite = await _bot_has_permission(chat_id, "can_invite_users")
    if can_invite:
        if await _try_join_via_invite(userbot, chat_id):
            _mark_confirmed(chat_id)
            return True

    logger.warning(
        f"[assistant_guard] Could not join assistant into {chat_id}. "
        f"Bot needs 'Invite Users' admin right (and 'Ban Members' if assistant was banned)."
    )
    return False


# ─── PLAY COMMAND INTERCEPTOR ─────────────────────────────────────────────────
PLAY_COMMANDS = [
    "play", "vplay", "cplay", "cvplay",
    "playforce", "vplayforce", "cplayforce", "cvplayforce",
]


@app.on_message(
    filters.command(PLAY_COMMANDS, prefixes=["/", "!", "%", ".", "@", "#", ""])
    & filters.group,
    group=-10,
)
async def _play_assistant_guard(client: Client, message: Message):
    """
    Intercept every play command in a group and silently ensure the assistant
    is present. Runs at priority -10 (before normal handlers).
    Never blocks the play response — fire-and-forget background task.
    """
    asyncio.create_task(ensure_assistant_in_chat(message.chat.id))


# ─── OPTIONAL DECORATOR ──────────────────────────────────────────────────────
def with_assistant_guard(func):
    """
    Decorator that AWAITS the guard before running the handler.
    Use this on play handlers if you need the assistant guaranteed present
    before pytgcalls tries to connect.

    Usage:
        @app.on_message(...)
        @PlayWrapper
        @with_assistant_guard
        async def play_command(client, message):
            ...
    """
    @wraps(func)
    async def wrapper(client, message: Message, *args, **kwargs):
        guard_task = asyncio.create_task(ensure_assistant_in_chat(message.chat.id))
        try:
            result = await func(client, message, *args, **kwargs)
        finally:
            try:
                await guard_task
            except Exception as e:
                logger.debug(f"[assistant_guard] guard task error: {e}")
        return result
    return wrapper
