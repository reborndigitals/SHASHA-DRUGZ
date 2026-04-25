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
#   In-Memory Cache: chat_id → fsub data
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_fsub_cache: dict[int, dict | None] = {}

def _cache_get(chat_id: int):
    return _fsub_cache.get(chat_id, "MISS")

def _cache_set(chat_id: int, data):
    _fsub_cache[chat_id] = data

def _cache_del(chat_id: int):
    _fsub_cache.pop(chat_id, None)

def _get_fsub_data(chat_id: int):
    cached = _cache_get(chat_id)
    if cached != "MISS":
        return cached
    data = forcesub_collection.find_one({"chat_id": chat_id})
    _cache_set(chat_id, data)
    return data

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   In-Memory: Active VC Call → Chat mapping
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
vc_call_chat_map: dict[int, int] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   In-Memory: Muted users per chat
#   { chat_id: set(user_id) }
#   Tracked = muted + caption already sent
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_muted_users: dict[int, set[int]] = {}

def _track_muted(chat_id: int, user_id: int):
    _muted_users.setdefault(chat_id, set()).add(user_id)

def _untrack_muted(chat_id: int, user_id: int):
    if chat_id in _muted_users:
        _muted_users[chat_id].discard(user_id)
        if not _muted_users[chat_id]:
            del _muted_users[chat_id]

def _is_tracked_muted(chat_id: int, user_id: int) -> bool:
    return user_id in _muted_users.get(chat_id, set())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#               HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def resolve_chat_id(client: Client, channel_input: str):
    channel_input = channel_input.strip()
    if channel_input.lstrip("-").isdigit():
        return await client.get_chat(int(channel_input))
    return await client.get_chat(channel_input.lstrip("@"))

async def is_owner_or_sudo(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except Exception:
        return False

async def is_admin_or_above(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id in SUDOERS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False

async def is_member_of(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status not in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]
    except UserNotParticipant:
        return False
    except Exception:
        return True  # Fail-open on unknown errors

async def mute_in_chat(client: Client, chat_id: int, user_id: int) -> bool:
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
    try:
        await client.ban_chat_member(chat_id, user_id)
        await asyncio.sleep(0.5)
        await client.unban_chat_member(chat_id, user_id)
        return True
    except Exception as e:
        print(f"[FSub VC Kick Error] chat={chat_id} user={user_id}: {e}")
        return await admin_mute_in_vc(client, chat_id, user_id)

async def admin_mute_in_vc(client: Client, chat_id: int, user_id: int) -> bool:
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

async def get_active_call(client: Client, chat_id: int) -> "raw.base.InputGroupCall | None":
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
#  SAFE FILTER: True only for non-command text
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _is_not_command(_, __, msg: Message) -> bool:
    try:
        text = msg.text or msg.caption or ""
        text = text.strip()
        if not text:
            return False
        return not text.startswith("/")
    except Exception:
        return False

_not_command = filters.create(_is_not_command, name="NotCommandFilter")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   AUTO-UNMUTE BACKGROUND LOOP
#   Polls every 30s — unmutes users who joined
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _auto_unmute_loop(client: Client):
    await asyncio.sleep(10)  # Startup delay
    while True:
        try:
            if _muted_users:
                snapshot = {
                    chat_id: set(users)
                    for chat_id, users in _muted_users.items()
                }
                for chat_id, user_ids in snapshot.items():
                    data = _get_fsub_data(chat_id)
                    if not data:
                        # FSub disabled — unmute everyone and clear
                        for uid in user_ids:
                            await unmute_in_chat(client, chat_id, uid)
                            _untrack_muted(chat_id, uid)
                        continue
                    req_id = data["channel_id"]
                    for user_id in user_ids:
                        try:
                            is_member = await asyncio.wait_for(
                                is_member_of(client, req_id, user_id), timeout=3
                            )
                            if is_member:
                                await unmute_in_chat(client, chat_id, user_id)
                                _untrack_muted(chat_id, user_id)
                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            print(f"[FSub AutoUnmute Error] chat={chat_id} user={user_id}: {e}")
                        await asyncio.sleep(0.3)
        except Exception as e:
            print(f"[FSub _auto_unmute_loop Error] {e}")
        await asyncio.sleep(30)

asyncio.get_event_loop().create_task(_auto_unmute_loop(app))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           /fsub COMMAND HANDLER
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
            _cache_del(chat_id)
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
        req_chat = await resolve_chat_id(client, channel_input)
    except Exception as e:
        return await message.reply_text(
            f"🚫 **Chat Not Found!**\n\nError: `{e}`\n\n"
            "Make sure the username/ID is correct and the bot is a member.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Close", callback_data=f"fsub_close_{user_id}")
            ]])
        )

    try:
        bot_status = await client.get_chat_member(req_chat.id, client.me.id)
        if bot_status.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
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
    _cache_del(chat_id)

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
        f"  • 💬 Non-members → **Muted** when they try to send a message\n"
        f"  • 🎙️ Non-members → **Kicked** from Voice Chat\n\n"
        f"⚡ Users will be **auto-unmuted** once they join the required chat.\n\n"
        f"⚙️ Config is **isolated to this chat only**.",
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
    _cache_del(target_chat)
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
#   AUTO-MUTE WHEN USER JOINS THE GROUP
#   ✅ Already in fsub channel → skip entirely
#   ❌ Not in fsub channel → mute + send caption
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_chat_member_updated(filters.group, group=20)
async def on_user_join_chat(client: Client, update):
    try:
        chat_id = update.chat.id
        data = _get_fsub_data(chat_id)
        if not data:
            return

        new_member = update.new_chat_member
        if not new_member or not new_member.user:
            return
        if new_member.user.is_bot:
            return
        if new_member.status != ChatMemberStatus.MEMBER:
            return

        user_id = new_member.user.id
        if user_id in SUDOERS:
            return
        if await is_admin_or_above(client, chat_id, user_id):
            return

        req_id = data["channel_id"]
        req_username = data.get("channel_username")
        req_title = data.get("channel_title", "Required Group")
        req_url = f"https://t.me/{req_username}" if req_username else None

        # ✅ Check if already a member of required channel — skip if yes
        try:
            already_member = await asyncio.wait_for(
                is_member_of(client, req_id, user_id), timeout=3
            )
        except asyncio.TimeoutError:
            return

        if already_member:
            return  # Already joined — no mute, no caption, no tag

        # Not a member — mute
        muted = await mute_in_chat(client, chat_id, user_id)
        if not muted:
            return

        _track_muted(chat_id, user_id)

        buttons = []
        if req_url:
            buttons.append([InlineKeyboardButton(f"ᴊᴏɪɴ🔻{req_title}", url=req_url)])

        try:
            await client.send_message(
                chat_id,
                f"🔒 **ʜᴇʏ {new_member.user.mention}!**\n\n"
                f"ʏᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ **ᴍᴜᴛᴇᴅ** ʙᴇᴄᴀᴜsᴇ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏғ **{req_title}**.\n\n"
                f"**ᴛᴏ ɢᴇᴛ ᴜɴᴍᴜᴛᴇᴅ:**\n"
                f"ᴊᴏɪɴ \n\n**{req_title}** ᴜsɪɴɢ ᴛʜᴇ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ\n\n"
                f"⚡ ʏᴏᴜ'ʟʟ ʙᴇ **ᴜɴᴍᴜᴛᴇᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ** ᴏɴᴄᴇ ʏᴏᴜ ᴊᴏɪɴ!",
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
                disable_web_page_preview=True
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[FSub on_user_join_chat Error] {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#     RAW UPDATE HANDLER — VC enforcement
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_raw_update(group=20)
async def raw_update_handler(client: Client, update, users: dict, chats: dict):
    try:
        if forcesub_collection.count_documents({}) == 0:
            return

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

        call_obj = update.call
        call_id = call_obj.id
        chat_id = vc_call_chat_map.get(call_id)

        if not chat_id:
            for _, chat_obj in chats.items():
                try:
                    if isinstance(chat_obj, raw.types.Channel):
                        potential = int(f"-100{chat_obj.id}")
                    elif isinstance(chat_obj, raw.types.Chat):
                        potential = -chat_obj.id
                    else:
                        continue
                    if _get_fsub_data(potential):
                        chat_id = potential
                        vc_call_chat_map[call_id] = chat_id
                        break
                except Exception:
                    continue

        if not chat_id:
            return

        data = _get_fsub_data(chat_id)
        if not data:
            return

        req_id = data["channel_id"]
        req_username = data.get("channel_username")
        req_title = data.get("channel_title", "Required Group")
        req_url = f"https://t.me/{req_username}" if req_username else None

        for participant in update.participants:
            try:
                if not getattr(participant, "just_joined", False):
                    continue
                if getattr(participant, "left", False):
                    continue
                peer = participant.peer
                if not isinstance(peer, raw.types.PeerUser):
                    continue
                user_id = peer.user_id
                user_obj = users.get(user_id)
                if user_obj and getattr(user_obj, "bot", False):
                    continue
                if user_id in SUDOERS:
                    continue
                if await is_admin_or_above(client, chat_id, user_id):
                    continue
                try:
                    is_member = await asyncio.wait_for(
                        is_member_of(client, req_id, user_id), timeout=3
                    )
                except asyncio.TimeoutError:
                    continue
                if is_member:
                    continue
                asyncio.create_task(
                    _handle_vc_violator(client, chat_id, user_id, req_id, req_title, req_url)
                )
            except Exception as e:
                print(f"[FSub raw_update participant loop Error] {e}")
                continue

    except Exception as e:
        print(f"[FSub raw_update_handler Error] {e}")


async def _handle_vc_violator(
    client: Client,
    chat_id: int,
    user_id: int,
    req_id: int,
    req_title: str,
    req_url: "str | None",
):
    try:
        kicked = await kick_from_vc(client, chat_id, user_id)
        if not kicked:
            return

        await asyncio.sleep(1)
        try:
            async for msg in client.get_chat_history(chat_id, limit=10):
                if msg.service and msg.from_user and msg.from_user.id == user_id:
                    await msg.delete()
        except Exception:
            pass

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
            pass
        except Exception:
            pass

    except Exception as e:
        print(f"[FSub _handle_vc_violator Error] chat={chat_id} user={user_id}: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   CORE FSub CHECK — triggered on every message
#
#   Logic:
#   ✅ Already in fsub channel → allow (no mute, no caption, no tag)
#   ❌ Not in fsub channel + first offence → mute + send caption with join button
#   ❌ Not in fsub channel + already muted → just mute silently (no repeat caption)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_forcesub(client: Client, message: Message) -> None:
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        if message.from_user.is_bot:
            return
        if user_id in SUDOERS:
            return

        data = _get_fsub_data(chat_id)
        if not data:
            return

        if await is_admin_or_above(client, chat_id, user_id):
            return

        req_id = data["channel_id"]
        req_username = data.get("channel_username")
        req_title = data.get("channel_title", "Required Group")

        # ✅ Check membership in required channel
        try:
            is_member = await asyncio.wait_for(
                is_member_of(client, req_id, user_id), timeout=3
            )
        except asyncio.TimeoutError:
            return

        # Already in fsub channel — do nothing at all (no mute, no caption, no tag)
        if is_member:
            return

        # Not a member — mute them silently (in case they somehow got unmuted)
        await mute_in_chat(client, chat_id, user_id)

        # Caption already sent once — don't spam
        if _is_tracked_muted(chat_id, user_id):
            return

        # First time being caught — track and send caption
        _track_muted(chat_id, user_id)

        if req_username:
            req_url = f"https://t.me/{req_username}"
        else:
            try:
                req_url = await client.export_chat_invite_link(req_id)
            except Exception:
                req_url = None

        buttons = []
        if req_url:
            buttons.append([InlineKeyboardButton(f"📢 Join {req_title}", url=req_url)])

        try:
            await message.reply_photo(
                photo="https://envs.sh/Tn_.jpg",
                caption=(
                    f"🔒 **Hey {message.from_user.mention}!**\n\n"
                    f"You need to join **{req_title}** to send messages here.\n\n"
                    f"1️⃣ Click **'Join'** below\n\n"
                    f"⚡ You'll be **unmuted automatically** once you join!"
                ),
                reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
            )
        except Exception:
            pass

    except Exception as e:
        print(f"[FSub check_forcesub Error] {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENFORCER: fires on every non-command message
#  group=30 ensures it runs after other handlers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.on_message(
    filters.group
    & filters.incoming
    & filters.text
    & filters.user
    & _not_command
    & ~filters.via_bot
    & ~filters.service,
    group=30
)
async def enforce_forcesub(client: Client, message: Message):
    try:
        chat_id = message.chat.id
        data = _get_fsub_data(chat_id)
        if not data:
            return
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return
        asyncio.create_task(check_forcesub(client, message))
    except Exception as e:
        print(f"[FSub enforce_forcesub Error] {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#              MODULE METADATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_42"
__help__ = """
🔻 /fsub <channel_username | channel_id> ➠ ᴇɴᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /forcesub <channel_username | channel_id> ➠ ᴇɴᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /fsub off ➠ ᴅɪꜱᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /forcesub off ➠ ᴅɪꜱᴀʙʟᴇꜱ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴏʀ ᴛʜᴇ ɢʀᴏᴜᴘ.
🔻 /fsub disable ➠ ᴛᴜʀɴꜱ ᴏꜰꜰ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴇᴀᴛᴜʀᴇ.
🔻 /forcesub disable ➠ ᴛᴜʀɴꜱ ᴏꜰꜰ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ꜰᴇᴀᴛᴜʀᴇ.
🔻 (ᴀᴜᴛᴏ) ➠ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ ᴍᴇᴍʙᴇʀꜱ ᴄᴀɴ ᴍꜱɢ ꜰʀᴇᴇʟʏ — ɴᴏ ᴍᴜᴛᴇ, ɴᴏ ᴛᴀɢ.
🔻 (ᴀᴜᴛᴏ) ➠ ɴᴏɴ-ᴍᴇᴍʙᴇʀꜱ ᴀʀᴇ ᴍᴜᴛᴇᴅ ᴏɴ ꜰɪʀꜱᴛ ᴍꜱɢ + ɢᴇᴛ ᴊᴏɪɴ ᴄᴀᴘᴛɪᴏɴ.
🔻 (ᴀᴜᴛᴏ) ➠ ᴄᴀᴘᴛɪᴏɴ ꜱᴇɴᴛ ᴏɴʟʏ ᴏɴᴄᴇ ᴘᴇʀ ᴜꜱᴇʀ — ɴᴏ ꜱᴘᴀᴍ.
🔻 (ᴀᴜᴛᴏ) ➠ ᴜɴᴍᴜᴛᴇꜱ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴡʜᴇɴ ᴜꜱᴇʀ ᴊᴏɪɴꜱ ʀᴇQᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟ.
🔻 (ᴀᴜᴛᴏ) ➠ ꜱᴜᴅᴏᴇʀꜱ & ɢʀᴏᴜᴘ ᴀᴅᴍɪɴꜱ ᴀʀᴇ ᴇxᴇᴍᴘᴛ ꜰʀᴏᴍ ꜰᴏʀᴄᴇ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ.
"""
