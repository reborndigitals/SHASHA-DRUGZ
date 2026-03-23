import asyncio
import datetime
import time
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from pyrogram.errors import FloodWait
from motor.motor_asyncio import AsyncIOMotorClient

from SHASHA_DRUGZ import app
from config import MONGO_URL, OWNER_ID

# ---------- NORMALIZE OWNER ID ----------
if isinstance(OWNER_ID, int):
    OWNER_ID = [OWNER_ID]

# ---------- DATABASE SETUP ----------
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["tagger_bot_db"]
groups_col = db["groups"]

# ---------- GLOBAL STATE ----------
MENTION_ACTIVE = []          # for normal /all tagging (chat_id list)
UTAG_ACTIVE = {}             # for unlimited tagging (chat_id -> bool)

# Additional state for tracking tag stats
NORMAL_TAG_DATA = {}         # chat_id -> {'initiator': user_id, 'start_time': float, 'total_count': int}
UTAG_TAG_DATA = {}           # chat_id -> {'initiator': user_id, 'start_time': float, 'total_count': int}


# ---------- HELPER FUNCTIONS ----------
async def get_group_config(chat_id):
    """Retrieve group settings (batch_size, last_run) from DB."""
    doc = await groups_col.find_one({"chat_id": chat_id})
    if not doc:
        return {"batch_size": 1, "last_run": None}
    return doc


async def set_batch_size(chat_id, size):
    """Update batch size for a group."""
    await groups_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"batch_size": size}},
        upsert=True
    )


async def update_last_run(chat_id):
    """Update last run timestamp for a group."""
    await groups_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"last_run": datetime.datetime.now()}},
        upsert=True
    )


async def is_admin(client, message: Message) -> bool:
    """
    Check if the sender is an admin or owner.
    Supports anonymous admins and owner IDs from config.
    """
    chat_id = message.chat.id

    # Anonymous admin (group sends as the group itself)
    if message.sender_chat and message.sender_chat.id == chat_id:
        return True

    if not message.from_user:
        return False

    user_id = message.from_user.id

    # Bot owner(s)
    if user_id in OWNER_ID:
        return True

    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        ]
    except:
        return False


async def send_tag_report(chat_id, initiator_id, total_members, duration, chat_title, chat_link):
    """Send tag completion report to group, owner(s), and initiator."""
    report = f"<blockquote>**⚡ ᴛᴀɢɢɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇᴅ Report**</blockquote>\n"
    report += f"<blockquote>**ɢʀᴏᴜᴘ:** {chat_title}\n"
    report += f"**ɢʀᴏᴜᴘ ɪᴅ:** `{chat_id}`\n"
    report += f"**ɢʀᴏᴜᴘ ʟɪɴᴋ:** {chat_link if chat_link else 'NONE'}\n"
    report += f"**ᴍᴇᴍʙᴇʀs ᴛᴀɢɢᴇᴅ:** {total_members}\n"
    report += f"**ᴛɪᴍᴇ ᴛᴀᴋᴇɴ:** {duration:.2f} seconds</blockquote>"

    # Send to group
    try:
        await app.send_message(chat_id, report)
    except Exception as e:
        print(f"ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ʀᴇᴘᴏʀᴛ ᴛᴏ ɢʀᴏᴜᴘ {chat_id}: {e}")

    # Send to owner(s)
    for owner_id in OWNER_ID:
        try:
            await app.send_message(owner_id, report)
        except Exception as e:
            print(f"ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ʀᴇᴘᴏʀᴛ ᴛᴏ ᴏᴡɴᴇʀ {owner_id}: {e}")

    # Send to initiator admin
    try:
        await app.send_message(initiator_id, report)
    except Exception as e:
        print(f"ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ʀᴇᴘᴏʀᴛ ᴛᴏ ɪɴɪᴛɪᴀᴛᴏʀ {initiator_id}: {e}")


# ---------- /setuser (Batch Size Configuration) ----------
@app.on_message(filters.command(["setuser"]) & filters.group)
async def setuser_handler(client, message: Message):
    if not await is_admin(client, message):
        return await message.reply("🍎 **ᴀᴅᴍɪɴ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ.**")

    buttons = [
        [
            InlineKeyboardButton("1", callback_data="set_batch_1"),
            InlineKeyboardButton("2", callback_data="set_batch_2"),
            InlineKeyboardButton("3", callback_data="set_batch_3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="set_batch_4"),
            InlineKeyboardButton("5", callback_data="set_batch_5"),
        ]
    ]

    await message.reply(
        "<blockquote>✨ **ᴛᴀɢ sᴇᴛᴛɪɴɢs**</blockquote>\n<blockquote>sᴇʟᴇᴄᴛ ʜᴏᴡ ᴍᴀɴʏ ᴜsᴇʀs ᴛᴏ ᴍᴇɴᴛɪᴏɴ ᴘᴇʀ ᴍᴇssᴀɢᴇ:</blockquote>",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex("^set_batch_"))
async def batch_callback(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    # Admin check
    is_auth = False
    try:
        mem = await client.get_chat_member(chat_id, user_id)
        if mem.status in [
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        ]:
            is_auth = True
    except:
        pass

    if user_id in OWNER_ID:
        is_auth = True

    if not is_auth:
        return await query.answer("You are not an admin!", show_alert=True)

    size = int(data.split("_")[-1])
    await set_batch_size(chat_id, size)

    await query.message.edit_text(
        f"<blockquote>🍏 **sᴇᴛᴛɪɴɢs ᴜᴘᴅᴀᴛᴇᴅ!**</blockquote>\n<blockquote>ɴᴏᴡ ᴛᴀɢɢɪɴɢ **{size}** ᴜsᴇʀs ᴘᴇʀ ᴍᴇssᴀɢᴇ.</blockquote>"
    )
    await query.answer("ʙᴀᴛᴄʜ sɪᴢᴇ ᴜᴘᴅᴀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!")


# ---------- /tagreport (Status of Ongoing Tags) ----------
@app.on_message(filters.command(["tagreport"]) & filters.group)
async def report_handler(client, message: Message):
    if not await is_admin(client, message):
        return

    # We'll report both normal and unlimited tagging processes
    report = "<blockquote>**💫 ᴛᴀɢɢɪɴɢ sᴛᴀᴛᴜs ʀᴇᴘᴏʀᴛ:**</blockquote>\n"

    if MENTION_ACTIVE:
        for chat_id in MENTION_ACTIVE:
            try:
                chat = await client.get_chat(chat_id)
                title = chat.title
            except:
                title = "ᴜɴᴋɴᴏᴡɴ ɢʀᴏᴜᴘ"
            report += f"🍏 **{title}** (`{chat_id}`) – ɴᴏʀᴍᴀʟ ᴛᴀɢ ʀᴜɴɴɪɴɢ\n"
    else:
        report += "ɴᴏ ɴᴏʀᴍᴀʟ ᴛᴀɢɢɪɴɢ ᴘʀᴏᴄᴇssᴇs.\n"

    if UTAG_ACTIVE:
        for chat_id, active in UTAG_ACTIVE.items():
            if active:
                try:
                    chat = await client.get_chat(chat_id)
                    title = chat.title
                except:
                    title = "ᴜɴᴋɴᴏᴡɴ ɢʀᴏᴜᴘ"
                report += f"🔵 **{title}** (`{chat_id}`) – Unlimited tag running\n"
    else:
        report += "ɴᴏ ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢɢɪɴɢ ᴘʀᴏᴄᴇssᴇs.\n"

    await message.reply(report)


# ---------- NORMAL TAG (/all, /mention, /mentionall) ----------
@app.on_message(
    filters.command(["all", "mention", "mentionall"], prefixes=["/", "@", ".", "#", "!"]) & filters.group
)
async def tag_all_users(client, message: Message):
    # Admin check
    if not await is_admin(client, message):
        return

    chat_id = message.chat.id

    # Prevent multiple concurrent tags in same chat
    if chat_id in MENTION_ACTIVE:
        return await message.reply("⚠️ ᴀ ᴛᴀɢɢɪɴɢ ᴘʀᴏᴄᴇss ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ɪɴ ᴛʜɪs ᴄʜᴀᴛ. ᴜsᴇ /stopmention ᴛᴏ sᴛᴏᴘ ɪᴛ ғɪʀsᴛ.")

    replied = message.reply_to_message

    # Get text to send
    if replied:
        text_to_send = replied.text or replied.caption or ""
    elif len(message.command) > 1:
        text_to_send = message.text.split(None, 1)[1]
    else:
        await message.reply("**ɢɪᴠᴇ sᴏᴍᴇ ᴛᴇxᴛ ᴛᴏ ᴛᴀɢ ᴀʟʟ, ʟɪᴋᴇ »** `@all Hi Friends`")
        return

    # Mark as active and store stats
    MENTION_ACTIVE.append(chat_id)
    start_time = time.time()
    NORMAL_TAG_DATA[chat_id] = {
        'initiator': message.from_user.id,
        'start_time': start_time,
        'total_count': 0
    }

    # Fetch batch size
    config = await get_group_config(chat_id)
    batch_size = config.get("batch_size", 1)

    user_chunk = []
    user_count = 0

    try:
        async for member in app.get_chat_members(chat_id):
            # Check if stopped
            if chat_id not in MENTION_ACTIVE:
                break

            # Skip bots and deleted accounts
            if member.user.is_bot or member.user.is_deleted:
                continue

            user_mention = f"[{member.user.first_name}](tg://user?id={member.user.id})"
            user_chunk.append(user_mention)
            user_count += 1

            # When chunk reaches batch size, send
            if user_count == batch_size:
                mention_text = "\n".join(user_chunk)
                final_msg = f"{text_to_send}\n{mention_text}" if text_to_send else mention_text

                # Send with flood handling
                while True:
                    try:
                        if replied:
                            await replied.reply_text(final_msg)
                        else:
                            await app.send_message(chat_id, final_msg)
                        break  # success, exit retry loop
                    except FloodWait as e:
                        # Wait the required time and retry same chunk
                        await asyncio.sleep(e.value)
                        continue

                # Increment total count
                if chat_id in NORMAL_TAG_DATA:
                    NORMAL_TAG_DATA[chat_id]['total_count'] += batch_size

                # Small delay between batches
                await asyncio.sleep(1)

                # Reset chunk
                user_chunk = []
                user_count = 0

        # Send remaining users if any
        if user_chunk and chat_id in MENTION_ACTIVE:
            mention_text = "\n".join(user_chunk)
            final_msg = f"{text_to_send}\n{mention_text}" if text_to_send else mention_text
            while True:
                try:
                    if replied:
                        await replied.reply_text(final_msg)
                    else:
                        await app.send_message(chat_id, final_msg)
                    break
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    continue

            # Increment remaining count
            if chat_id in NORMAL_TAG_DATA:
                NORMAL_TAG_DATA[chat_id]['total_count'] += len(user_chunk)

    finally:
        # Cleanup: remove chat from active list
        try:
            MENTION_ACTIVE.remove(chat_id)
        except ValueError:
            pass

        # Send completion report
        if chat_id in NORMAL_TAG_DATA:
            data = NORMAL_TAG_DATA.pop(chat_id)
            total = data['total_count']
            duration = time.time() - data['start_time']
            try:
                chat = await client.get_chat(chat_id)
                title = chat.title
                link = f"https://t.me/{chat.username}" if chat.username else None
            except:
                title = "Unknown Group"
                link = None

            await send_tag_report(chat_id, data['initiator'], total, duration, title, link)


@app.on_message(
    filters.command(
        ["stopmention", "offall", "allstop", "stopall", "cancelmention",
         "offmention", "mentionoff", "alloff", "cancelall", "allcancel"],
        prefixes=["/", "@", "#", "!"]
    ) & filters.group
)
async def stop_tagging(client, message: Message):
    if not await is_admin(client, message):
        return

    chat_id = message.chat.id
    if chat_id in MENTION_ACTIVE:
        try:
            MENTION_ACTIVE.remove(chat_id)
        except ValueError:
            pass
        await message.reply("**🛑 ᴛᴀɢɢɪɴɢ ᴘʀᴏᴄᴇss sᴜᴄᴄᴇssғᴜʟʟʏ sᴛᴏᴘᴘᴇᴅ!**")
    else:
        await message.reply("**⚠️ ɴᴏ ᴏɴɢᴏɪɴɢ ɴᴏʀᴍᴀʟ ᴛᴀɢɢɪɴɢ ᴘʀᴏᴄᴇss.**")


# ---------- UNLIMITED TAG (/utag, /uall) ----------
@app.on_message(
    filters.command(["utag", "uall"], prefixes=["/", "@", ".", "#"]) & filters.group
)
async def utag_all_users(client, message: Message):
    if not await is_admin(client, message):
        return

    chat_id = message.chat.id

    if UTAG_ACTIVE.get(chat_id, False):
        return await message.reply("⚠️ ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢɢɪɴɢ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ. ᴜsᴇ /stoputag ᴛᴏ sᴛᴏᴘ ɪᴛ ғɪʀsᴛ.")

    if len(message.text.split()) == 1:
        await message.reply(
            "**ɢɪᴠᴇ sᴏᴍᴇ ᴛᴇxᴛ ᴛᴏ ᴛᴀɢ ᴀʟʟ, ʟɪᴋᴇ »** `@utag ʜɪ ғʀɪᴇɴᴅs`"
        )
        return

    text = message.text.split(None, 1)[1]

    # Mark active and store stats
    UTAG_ACTIVE[chat_id] = True
    start_time = time.time()
    UTAG_TAG_DATA[chat_id] = {
        'initiator': message.from_user.id,
        'start_time': start_time,
        'total_count': 0
    }

    await message.reply(
        "**ᴜᴛᴀɢ [ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢ] sᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**\n"
        "**๏ ᴛᴀɢɢɪɴɢ ᴡɪᴛʜ ᴅᴇʟᴀʏ ᴏғ 4 sᴇᴄ.**\n"
        "**➥ ᴛᴏ ᴏғғ ᴛᴀɢɢɪɴɢ » /stoputag**"
    )

    try:
        while UTAG_ACTIVE.get(chat_id):
            try:
                config = await get_group_config(chat_id)
                batch_size = config.get("batch_size", 1)

                user_chunk = []
                user_count = 0

                async for member in app.get_chat_members(chat_id):
                    if not UTAG_ACTIVE.get(chat_id):
                        break
                    if member.user.is_bot or member.user.is_deleted:
                        continue

                    user_mention = f"[{member.user.first_name}](tg://user?id={member.user.id})"
                    user_chunk.append(user_mention)
                    user_count += 1

                    if user_count == batch_size:
                        mention_text = "\n".join(user_chunk)
                        final_msg = f"{text}\n{mention_text}" if text else mention_text

                        # Send with flood handling
                        while True:
                            try:
                                await app.send_message(chat_id, final_msg)
                                break
                            except FloodWait as e:
                                await asyncio.sleep(e.value)
                                continue

                        # Increment total count
                        if chat_id in UTAG_TAG_DATA:
                            UTAG_TAG_DATA[chat_id]['total_count'] += batch_size

                        await asyncio.sleep(4)  # intentional delay
                        user_chunk = []
                        user_count = 0

                # Send remaining users after loop finishes one full pass
                if user_chunk and UTAG_ACTIVE.get(chat_id):
                    mention_text = "\n".join(user_chunk)
                    final_msg = f"{text}\n{mention_text}" if text else mention_text
                    while True:
                        try:
                            await app.send_message(chat_id, final_msg)
                            break
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                            continue

                    # Increment remaining count
                    if chat_id in UTAG_TAG_DATA:
                        UTAG_TAG_DATA[chat_id]['total_count'] += len(user_chunk)

                    await asyncio.sleep(4)

            except Exception as e:
                print(f"[utag error] {e}")
                await asyncio.sleep(4)

    finally:
        # Cleanup and send report
        UTAG_ACTIVE[chat_id] = False  # ensure it's marked as stopped
        if chat_id in UTAG_TAG_DATA:
            data = UTAG_TAG_DATA.pop(chat_id)
            total = data['total_count']
            duration = time.time() - data['start_time']
            try:
                chat = await client.get_chat(chat_id)
                title = chat.title
                link = f"https://t.me/{chat.username}" if chat.username else None
            except:
                title = "ᴜɴᴋɴᴏᴡɴ ɢʀᴏᴜᴘ"
                link = None

            await send_tag_report(chat_id, data['initiator'], total, duration, title, link)


@app.on_message(
    filters.command(
        ["stoputag", "stopuall", "offutag", "offuall", "utagoff", "ualloff"],
        prefixes=["/", ".", "@", "#"]
    ) & filters.group
)
async def stop_utag(client, message: Message):
    if not await is_admin(client, message):
        return

    chat_id = message.chat.id
    if UTAG_ACTIVE.get(chat_id):
        UTAG_ACTIVE[chat_id] = False
        await message.reply("**🛑 sᴛᴏᴘᴘɪɴɢ ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢɢɪɴɢ. ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...**")
    else:
        await message.reply("**⚠️ ᴜᴛᴀɢ ᴘʀᴏᴄᴇss ɪs ɴᴏᴛ ᴀᴄᴛɪᴠᴇ!**")


# ---------- MODULE INFO ----------
__menu__ = "CMD_MENTION"
__mod_name__ = "H_B_11"
__help__ = """
**ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs:**
🔻 /setuser – ᴄʜᴏᴏsᴇ ʜᴏᴡ ᴍᴀɴʏ ᴜsᴇʀs ᴛᴏ ᴍᴇɴᴛɪᴏɴ ᴘᴇʀ ᴍᴇssᴀɢᴇ (1‑5)
🔻 /tagreport – sʜᴏᴡ ᴄᴜʀʀᴇɴᴛ ᴛᴀɢɢɪɴɢ ᴘʀᴏᴄᴇssᴇs ɪɴ ᴀʟʟ ɢʀᴏᴜᴘs

**ɴᴏʀᴍᴀʟ ᴛᴀɢ (ᴏɴᴇ-ᴛɪᴍᴇ):**
🔻 /all , /mention , /mentionall <text> – ᴛᴀɢ ᴀʟʟ ᴜsᴇʀs ᴏɴᴄᴇ
🔻 /stopmention , /offall , /allstop – sᴛᴏᴘ ᴛʜᴇ ᴏɴɢᴏɪɴɢ ɴᴏʀᴍᴀʟ ᴛᴀɢɢɪɴɢ

**ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢ (ᴄᴏɴᴛɪɴᴜᴏᴜs ʟᴏᴏᴘ):**
🔻 /utag , /uall <text> – sᴛᴀʀᴛ ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢɢɪɴɢ (ʟᴏᴏᴘs ғᴏʀᴇᴠᴇʀ ᴜɴᴛɪʟ sᴛᴏᴘᴘᴇᴅ)
🔻 /stoputag , /stopuall – sᴛᴏᴘ ᴜɴʟɪᴍɪᴛᴇᴅ ᴛᴀɢɢɪɴɢ
"""
