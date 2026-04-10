import asyncio
from pyrogram import Client, filters, raw
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ChatPermissions
)
from pyrogram.errors import (
    ChatAdminRequired, UserNotParticipant,
    FloodWait, PeerIdInvalid, UserPrivacyRestricted
)
from pyrogram.enums import ChatMemberStatus
from pymongo import MongoClient
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import MONGO_DB_URI

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#                  DATABASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fsubdb = MongoClient(MONGO_DB_URI)
forcesub_collection = fsubdb.status_db.status

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   In-Memory: Active VC Call → Chat mapping
#   call_id (int) → chat_id (int)
#   NOTE: Resets on bot restart (only affects
#         calls that were active before restart)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
vc_call_chat_map: dict[int, int] = {}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#               HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def resolve_chat_id(client: Client, channel_input: str):
    """
    Resolve a channel/group input to a Pyrogram Chat object.
    Supports:
      - @username
      - username (without @)
      - -100xxxxxxxxx  (supergroup/channel numeric ID)
      - plain integer string
    """
    channel_input = channel_input.strip()

    # Numeric ID: could be "-100..." or plain int
    if channel_input.lstrip("-").isdigit():
        numeric_id = int(channel_input)
        # Pyrogram accepts int directly; it handles the -100 prefix internally
        return await client.get_chat(numeric_id)

    # Username: strip leading @ if present
    username = channel_input.lstrip("@")
    return await client.get_chat(username)


async def is_owner_or_sudo(client: Client, chat_id: int, user_id: int) -> bool:
    """Only Group/Channel OWNER + Sudoers can manage FSub."""
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except Exception:
        return False


async def is_admin_or_above(client: Client, chat_id: int, user_id: int) -> bool:
    """Admins, Owners, Sudoers — all bypass FSub checks."""
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False


async def is_member_of(client: Client, chat_id: int, user_id: int) -> bool:
    """
    Returns True if user is a valid member of `chat_id`.
    Returns False if not a participant or banned.
    """
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status not in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]
    except UserNotParticipant:
        return False
    except Exception:
        return True  # Fail-open on unknown errors


async def mute_in_chat(client: Client, chat_id: int, user_id: int) -> bool:
    """Restrict all chat permissions (text mute)."""
    try:
        await client.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_polls=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            )
        )
        return True
    except Exception:
        return False


async def unmute_in_chat(client: Client, chat_id: int, user_id: int) -> bool:
    """Restore all chat permissions."""
    try:
        await client.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            )
        )
        return True
    except Exception:
        return False


async def kick_from_vc(client: Client, chat_id: int, user_id: int) -> bool:
    """
    Kick user from Voice Chat.
    Method: temporary ban + immediate unban.
    This removes them from the active VC call.
    Service messages are deleted automatically.
    """
    try:
        await client.ban_chat_member(chat_id, user_id)
        await asyncio.sleep(0.5)
        await client.unban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        print(f"[FSub VC Kick Error] chat={chat_id} user={user_id}: {e}")
        # Fallback: Admin-mute in VC so they can't speak
        return await admin_mute_in_vc(client, chat_id, user_id)


async def admin_mute_in_vc(client: Client, chat_id: int, user_id: int) -> bool:
    """
    Fallback: Admin-mute the user in VC using raw API.
    User cannot unmute themselves when muted by admin.
    """
    try:
        call_input = await get_active_call(client, chat_id)
        if not call_input:
            return False
        participant_peer = await client.resolve_peer(user_id)
        await client.invoke(
            raw.functions.phone.EditGroupCallParticipant(
                call=call_input,
                participant=participant_peer,
                muted=True,
            )
        )
        return True
    except Exception as e:
        print(f"[FSub VC AdminMute Error] chat={chat_id} user={user_id}: {e}")
        return False


async def get_active_call(
    client: Client, chat_id: int
) -> raw.base.InputGroupCall | None:
    """Get the active InputGroupCall for a chat, or None."""
    try:
        peer = await client.resolve_peer(chat_id)
        if isinstance(peer, raw.types.InputPeerChannel):
            full = await client.invoke(
                raw.functions.channels.GetFullChannel(channel=peer)
            )
            return full.full_chat.call
        elif isinstance(peer, raw.types.InputPeerChat):
            full = await client.invoke(
                raw.functions.messages.GetFullChat(chat_id=peer.chat_id)
            )
            return full.full_chat.call
    except Exception:
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           /fsub COMMAND HANDLER
#   Works in BOTH Groups and Channels
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_message(
    filters.command(["fsub", "forcesub"])
    & (filters.group | filters.channel)
)
async def set_forcesub(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    # ── Owner/Sudo only ──
    if not await is_owner_or_sudo(client, chat_id, user_id):
        return await message.reply_text(
            "🚫 **Permission Denied!**\n\n"
            "Only the **Chat Owner** or **Sudoers** can manage Force Subscription.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
            ]])
        )

    args = message.command[1:]

    # ── /fsub off / disable ──
    if args and args[0].lower() in ["off", "disable"]:
        if forcesub_collection.find_one({"chat_id": chat_id}):
            forcesub_collection.delete_one({"chat_id": chat_id})
            return await message.reply_text(
                "✅ **Force Subscription Disabled!**\n\n"
                "• Chat messages: **Open to all**\n"
                "• Voice Chat: **Open to all**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
                ]])
            )
        return await message.reply_text(
            "ℹ️ Force Subscription is already **disabled** for this chat.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
            ]])
        )

    # ── /fsub status ──
    if args and args[0].lower() in ["status", "info"]:
        data = forcesub_collection.find_one({"chat_id": chat_id})
        if not data:
            return await message.reply_text(
                "📊 **Force Subscription Status**\n\n"
                "🔴 **Status:** Disabled\n\n"
                "Use `/fsub <group_id>` to enable.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
                ]])
            )
        title = data.get("channel_title", "Unknown")
        username = data.get("channel_username")
        ch_url = f"https://t.me/{username}" if username else None
        buttons = []
        if ch_url:
            buttons.append([InlineKeyboardButton(f"📢 {title}", url=ch_url)])
        buttons.append([
            InlineKeyboardButton(
                "🔴 Disable FSub",
                callback_data=f"fsub_disable_{chat_id}_{user_id}"
            )
        ])
        buttons.append([InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")])
        return await message.reply_text(
            f"📊 **Force Subscription Status**\n\n"
            f"🟢 **Status:** Active\n"
            f"📢 **Required Chat:** {title}\n\n"
            f"🔒 **Enforced on:**\n"
            f"  • 💬 Chat messages\n"
            f"  • 🎙️ Voice Chat joins",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )

    # ── No argument → show help ──
    if not args:
        return await message.reply_text(
            "📖 **Force Subscription — Guide**\n\n"
            "**▸ Enable:**\n"
            "`/fsub @group_username`\n"
            "`/fsub -100xxxxxxxxx`\n\n"
            "**▸ Disable:**\n"
            "`/fsub off`\n\n"
            "**▸ Status:**\n"
            "`/fsub status`\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📌 Works in Groups **and** Channels\n"
            "🔒 Only **Chat Owner** can configure\n"
            "🎙️ Enforces on **VC joins** too",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
            ]])
        )

    # ── Set FSub ──
    channel_input = args[0]
    try:
        # FIX: Use resolve_chat_id to properly handle both @username and -100... IDs
        req_chat = await resolve_chat_id(client, channel_input)
    except Exception as e:
        return await message.reply_text(
            f"🚫 **Chat Not Found!**\n\nError: `{e}`\n\n"
            "Make sure the username/ID is correct and the bot is a member.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
            ]])
        )

    # Bot must be admin in the required chat
    try:
        bot_status = await client.get_chat_member(req_chat.id, client.me.id)
        if bot_status.status not in [
            ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR
        ]:
            raise PermissionError("Bot is not admin")
    except Exception:
        return await message.reply_text(
            "⚠️ **Bot is Not Admin in the Required Chat!**\n\n"
            "**Steps to fix:**\n"
            "1️⃣ Open the required group/channel\n"
            "2️⃣ Go to **Admins → Add Admin**\n"
            "3️⃣ Add this bot as **Admin**\n"
            "4️⃣ Re-run `/fsub <id>`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
            ]])
        )

    req_id = req_chat.id
    req_username = req_chat.username
    req_title = req_chat.title
    req_url = f"https://t.me/{req_username}" if req_username else None

    # Save (per-chat, completely isolated)
    forcesub_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "channel_id": req_id,
            "channel_username": req_username,
            "channel_title": req_title,
            "set_by": user_id,
        }},
        upsert=True
    )

    buttons = []
    if req_url:
        buttons.append([InlineKeyboardButton(f"📢 {req_title}", url=req_url)])
    buttons.append([
        InlineKeyboardButton(
            "🔴 Disable FSub",
            callback_data=f"fsub_disable_{chat_id}_{user_id}"
        )
    ])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")])

    await message.reply_text(
        f"🎉 **Force Subscription Enabled!**\n\n"
        f"📢 **Required Chat:** [{req_title}]({req_url or '#'})\n\n"
        f"🔒 **Now enforcing:**\n"
        f"  • 💬 Non-members → **Muted** in chat\n"
        f"  • 🎙️ Non-members → **Kicked** from Voice Chat\n\n"
        f"⚙️ Config is **isolated to this chat only**.\n"
        f"Other chats are unaffected.",
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#            CALLBACK: DISABLE BUTTON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_callback_query(filters.regex(r"^fsub_disable_(-?\d+)_(\d+)$"))
async def cb_disable(client: Client, cq: CallbackQuery):
    target_chat = int(cq.matches[0].group(1))
    auth_user = int(cq.matches[0].group(2))
    if cq.from_user.id != auth_user and cq.from_user.id not in SUDOERS:
        return await cq.answer("⚠️ Only the command issuer can use this!", show_alert=True)
    forcesub_collection.delete_one({"chat_id": target_chat})
    await cq.answer("✅ Force Subscription Disabled!", show_alert=True)
    try:
        await cq.message.edit_text(
            "✅ **Force Subscription Disabled.**\n\n"
            "All members can now freely chat and join VC."
        )
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#              CALLBACK: CLOSE BUTTON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_callback_query(filters.regex(r"^fsub_close_(\d+)$"))
async def cb_close(client: Client, cq: CallbackQuery):
    auth_user = int(cq.matches[0].group(1))
    if cq.from_user.id != auth_user and cq.from_user.id not in SUDOERS:
        return await cq.answer("⚠️ This is not for you!", show_alert=True)
    try:
        await cq.message.delete()
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           CALLBACK: UNMUTE CHECK BUTTON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_callback_query(filters.regex(r"^check_fsub_(\d+)$"))
async def cb_check_fsub(client: Client, cq: CallbackQuery):
    user_id = int(cq.matches[0].group(1))
    if cq.from_user.id != user_id:
        return await cq.answer("⚠️ This button is only for the muted user!", show_alert=True)

    chat_id = cq.message.chat.id
    data = forcesub_collection.find_one({"chat_id": chat_id})

    # FSub disabled → just unmute and delete warning
    if not data:
        await unmute_in_chat(client, chat_id, user_id)
        await cq.answer("✅ FSub disabled. You are unmuted!", show_alert=True)
        try:
            await cq.message.delete()
        except Exception:
            pass
        return

    req_id = data["channel_id"]
    req_username = data.get("channel_username")
    req_title = data.get("channel_title", "Required Group")
    req_url = f"https://t.me/{req_username}" if req_username else None

    if await is_member_of(client, req_id, user_id):
        # ✅ Verified → Unmute + delete the fsub warning message
        await unmute_in_chat(client, chat_id, user_id)
        await cq.answer("🎉 Verified! You are unmuted. Welcome!", show_alert=True)
        try:
            await cq.message.delete()  # Delete warning only after successful join verification
        except Exception:
            pass
    else:
        # ❌ Still not a member — keep warning, just update buttons
        buttons = []
        if req_url:
            buttons.append([InlineKeyboardButton(f"📢 Join {req_title}", url=req_url)])
        buttons.append([
            InlineKeyboardButton("✅ I Joined — Unmute Me", callback_data=f"check_fsub_{user_id}")
        ])
        await cq.answer(
            f"❌ You haven't joined {req_title} yet!\nJoin and try again.",
            show_alert=True
        )
        try:
            await cq.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#        AUTO-MUTE WHEN USER JOINS CHAT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_chat_member_updated()
async def on_user_join_chat(client: Client, update):
    chat_id = update.chat.id
    if update.chat.type.name not in ["SUPERGROUP", "GROUP", "CHANNEL"]:
        return

    data = forcesub_collection.find_one({"chat_id": chat_id})
    if not data:
        return

    new_member = update.new_chat_member
    if not new_member or new_member.user.is_bot:
        return
    if new_member.status != ChatMemberStatus.MEMBER:
        return

    user_id = new_member.user.id

    # Bypass: Sudoers
    if user_id in SUDOERS:
        return
    # Bypass: Admins/Owner
    if await is_admin_or_above(client, chat_id, user_id):
        return

    req_id = data["channel_id"]
    req_username = data.get("channel_username")
    req_title = data.get("channel_title", "Required Group")
    req_url = f"https://t.me/{req_username}" if req_username else None

    # Already a member of required group → allow
    if await is_member_of(client, req_id, user_id):
        return

    # ── Mute in chat ──
    muted = await mute_in_chat(client, chat_id, user_id)
    if not muted:
        return

    buttons = []
    if req_url:
        buttons.append([InlineKeyboardButton(f"📢 Join {req_title}", url=req_url)])
    buttons.append([
        InlineKeyboardButton("✅ I Joined — Unmute Me", callback_data=f"check_fsub_{user_id}")
    ])

    try:
        # NOTE: No auto-delete — message stays until user clicks "I Joined — Unmute Me"
        await client.send_message(
            chat_id,
            f"🔒 **Hello {new_member.user.mention}!**\n\n"
            f"You have been **muted** because you are not a member of **{req_title}**.\n\n"
            f"**To get access:**\n"
            f"1️⃣ Join **{req_title}**\n"
            f"2️⃣ Click **'I Joined — Unmute Me'** below\n\n"
            f"⚡ You'll be unmuted instantly after verification!",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#     RAW UPDATE HANDLER
#     1. Track VC Call start/end → vc_call_chat_map
#     2. Enforce FSub on VC join
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_raw_update()
async def raw_update_handler(client: Client, update, users: dict, chats: dict):
    # ── 1. Track Voice Chat sessions ──
    if isinstance(update, raw.types.UpdateGroupCall):
        call = update.call
        peer = getattr(update, "peer", None)
        old_chat_id = getattr(update, "chat_id", None)
        if peer:
            if isinstance(peer, raw.types.PeerChannel):
                chat_id = int(f"-100{peer.channel_id}")
            elif isinstance(peer, raw.types.PeerChat):
                chat_id = -peer.chat_id
            else:
                return
        elif old_chat_id:
            chat_id = -old_chat_id
        else:
            return
        if isinstance(call, raw.types.GroupCallDiscarded):
            vc_call_chat_map.pop(call.id, None)
        elif hasattr(call, "id"):
            vc_call_chat_map[call.id] = chat_id
        return

    # ── 2. Voice Chat participant joins ──
    if not isinstance(update, raw.types.UpdateGroupCallParticipants):
        return

    call_obj = update.call  # InputGroupCall
    call_id = call_obj.id

    # Find chat_id from memory map first
    chat_id = vc_call_chat_map.get(call_id)

    # Fallback: scan the `chats` dict for one with fsub configured
    if not chat_id:
        for _, chat_obj in chats.items():
            if isinstance(chat_obj, raw.types.Channel):
                potential = int(f"-100{chat_obj.id}")
            elif isinstance(chat_obj, raw.types.Chat):
                potential = -chat_obj.id
            else:
                continue
            if forcesub_collection.find_one({"chat_id": potential}):
                chat_id = potential
                vc_call_chat_map[call_id] = chat_id  # Cache for next time
                break

    if not chat_id:
        return

    # Check if this chat has FSub configured
    data = forcesub_collection.find_one({"chat_id": chat_id})
    if not data:
        return

    req_id = data["channel_id"]
    req_username = data.get("channel_username")
    req_title = data.get("channel_title", "Required Group")
    req_url = f"https://t.me/{req_username}" if req_username else None

    # Process each participant in this update
    for participant in update.participants:
        # Only care about NEW joiners
        if not getattr(participant, "just_joined", False):
            continue
        if getattr(participant, "left", False):
            continue

        peer = participant.peer
        if not isinstance(peer, raw.types.PeerUser):
            continue

        user_id = peer.user_id

        # Skip bots
        user_obj = users.get(user_id)
        if user_obj and getattr(user_obj, "bot", False):
            continue

        # Bypass: Sudoers
        if user_id in SUDOERS:
            continue

        # Bypass: Admins/Owner
        if await is_admin_or_above(client, chat_id, user_id):
            continue

        # Check required group membership
        if await is_member_of(client, req_id, user_id):
            continue  # ✅ Allowed

        # ── NOT a member → Kick from VC ──
        asyncio.create_task(
            _handle_vc_violator(client, chat_id, user_id, req_id, req_title, req_url)
        )


async def _handle_vc_violator(
    client: Client,
    chat_id: int,
    user_id: int,
    req_id: int,
    req_title: str,
    req_url: str | None,
):
    """
    Handle a user who joined VC without being in the required group.
    Runs as a background task to avoid blocking the raw update handler.
    """
    # Kick from VC (ban → unban removes them from call)
    kicked = await kick_from_vc(client, chat_id, user_id)
    if not kicked:
        return

    # Clean up any ban/unban service messages
    await asyncio.sleep(1)
    try:
        async for msg in client.get_chat_history(chat_id, limit=10):
            if msg.service and msg.from_user and msg.from_user.id == user_id:
                await msg.delete()
    except Exception:
        pass

    # ── Notify in group chat (auto-delete after 15s) ──
    try:
        user_info = await client.get_users(user_id)
        buttons_group = []
        if req_url:
            buttons_group.append([InlineKeyboardButton(f"📢 Join {req_title}", url=req_url)])
        notif = await client.send_message(
            chat_id,
            f"🎙️ **{user_info.mention} was removed from Voice Chat!**\n\n"
            f"Reason: Not a member of **{req_title}**.\n"
            f"Join the required group to access VC.",
            reply_markup=InlineKeyboardMarkup(buttons_group) if buttons_group else None,
            disable_web_page_preview=True
        )
        await asyncio.sleep(15)
        await notif.delete()
    except Exception:
        pass

    # ── DM the user with instructions ──
    try:
        chat_info = await client.get_chat(chat_id)
        chat_title = chat_info.title
        chat_username = chat_info.username
        buttons_dm = []
        if req_url:
            buttons_dm.append([InlineKeyboardButton(f"📢 Join {req_title}", url=req_url)])
        if chat_username:
            buttons_dm.append([
                InlineKeyboardButton("🎙️ Rejoin VC", url=f"https://t.me/{chat_username}")
            ])
        await client.send_message(
            user_id,
            f"🚫 **You were removed from Voice Chat!**\n\n"
            f"**Chat:** {chat_title}\n\n"
            f"To join the VC, you must be a member of **{req_title}**.\n\n"
            f"**Steps:**\n"
            f"1️⃣ Join **{req_title}**\n"
            f"2️⃣ Return to **{chat_title}**\n"
            f"3️⃣ Rejoin the Voice Chat",
            reply_markup=InlineKeyboardMarkup(buttons_dm) if buttons_dm else None,
            disable_web_page_preview=True
        )
    except (UserPrivacyRestricted, PeerIdInvalid):
        pass  # User blocked DMs — that's OK
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#     MESSAGE ENFORCER (on every message)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_forcesub(client: Client, message: Message) -> bool:
    """
    Returns True  → user is allowed, message proceeds.
    Returns False → user blocked, warned (message NOT deleted).
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return True
    if user_id in SUDOERS:
        return True
    if await is_admin_or_above(client, chat_id, user_id):
        return True

    data = forcesub_collection.find_one({"chat_id": chat_id})
    if not data:
        return True

    req_id = data["channel_id"]
    req_username = data.get("channel_username")
    req_title = data.get("channel_title", "Required Group")

    if req_username:
        req_url = f"https://t.me/{req_username}"
    else:
        try:
            req_url = await client.export_chat_invite_link(req_id)
        except Exception:
            req_url = None

    # Check membership
    if await is_member_of(client, req_id, user_id):
        return True

    # ── Not a member ──
    # NOTE: User message is NOT deleted (per requirement)

    # Also mute them (in case they weren't muted on join)
    await mute_in_chat(client, chat_id, user_id)

    buttons = []
    if req_url:
        buttons.append([InlineKeyboardButton(f"📢 Join {req_title}", url=req_url)])
    buttons.append([
        InlineKeyboardButton("✅ I Joined — Unmute Me", callback_data=f"check_fsub_{user_id}")
    ])

    try:
        # NOTE: No auto-delete — warning stays until user clicks "I Joined — Unmute Me"
        await message.reply_photo(
            photo="https://envs.sh/Tn_.jpg",
            caption=(
                f"🔒 **Hey {message.from_user.mention}!**\n\n"
                f"You need to join **{req_title}** to send messages here.\n\n"
                f"1️⃣ Click **'Join'** below\n"
                f"2️⃣ Click **'Unmute Me'** after joining"
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception:
        pass

    return False


@app.on_message(filters.group & ~filters.bot & ~filters.service, group=30)
async def enforce_forcesub(client: Client, message: Message):
    if not await check_forcesub(client, message):
        message.stop_propagation()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#              MODULE METADATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_42"
__help__ = """
**▸ Enable:**
`/fsub @group_username`
`/fsub -100xxxxxxxxx`
`/forcesub @group_username`

**▸ Disable:**
`/fsub off` | `/fsub disable`

**▸ Check Status:**
`/fsub status`

"""
