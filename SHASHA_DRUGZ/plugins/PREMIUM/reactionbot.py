# SHASHA_DRUGZ/plugins/bot/reactionbot.py
import asyncio
import random
import re
from typing import Set, Dict, Tuple, Optional

from pyrogram import filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.enums import ChatMemberStatus, ChatType

from SHASHA_DRUGZ import app
from config import MENTION_USERNAMES, START_REACTIONS, OWNER_ID
from SHASHA_DRUGZ.utils.database import mongodb

try:
    from SHASHA_DRUGZ.misc import SUDOERS
except Exception:
    SUDOERS = set()

# ---------------- DATABASE ----------------
COLLECTION = mongodb["reaction_mentions"]
SETTINGS = mongodb["reaction_settings"]

# ---------------- STATE ----------------
REACTION_ENABLED = True  # global default flag
CHAT_REACTION_OVERRIDES: Dict[int, bool] = {} # per-chat override cache
custom_mentions: Set[str] = set(x.lower().lstrip("@") for x in (MENTION_USERNAMES or []))

# ---------------- VALID REACTIONS ----------------
# Reduced list to the most stable standard emojis to avoid 400 Errors
VALID_REACTIONS = {
    "👍", "👎", "❤️", "🔥", "🥰", "👏", "😁", "🤔", 
    "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩",
    "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳",
    "❤", "🔥", "💔", "💯", "🤣", "⚡", "💘", "🏆",
    "🍓", "🍾", "💋", "💘", "😈", "😴", "😭", "🤓",
    "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨", "🤝",
    "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪",
    "🗿", "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊",
    "😎", "👾", "🤷‍♂", "🤷", "🤷‍♀", "😡"
}

SAFE_REACTIONS = [e for e in (START_REACTIONS or []) if e in VALID_REACTIONS]
if not SAFE_REACTIONS:
    SAFE_REACTIONS = list(VALID_REACTIONS)
SAFE_REACTIONS = [e for e in (START_REACTIONS or []) if e in VALID_REACTIONS]
if not SAFE_REACTIONS:
    SAFE_REACTIONS = list(VALID_REACTIONS)

chat_used_reactions: Dict[int, Set[str]] = {}

def next_emoji(chat_id: int) -> str:
    if chat_id not in chat_used_reactions:
        chat_used_reactions[chat_id] = set()

    used = chat_used_reactions[chat_id]
    if len(used) >= len(SAFE_REACTIONS):
        used.clear()

    remaining = [e for e in SAFE_REACTIONS if e not in used]
    if not remaining:
        return random.choice(SAFE_REACTIONS)
        
    emoji = random.choice(remaining)
    used.add(emoji)
    chat_used_reactions[chat_id] = used
    return emoji


# ---------------- HELPERS & LOADERS ----------------
async def load_custom_mentions():
    try:
        docs = await COLLECTION.find({}).to_list(length=None)
        for doc in docs:
            name = doc.get("name")
            if name:
                custom_mentions.add(str(name).lower().lstrip("@"))
        print(f"[ReactionBot] Loaded {len(custom_mentions)} triggers.")
    except Exception as e:
        print(f"[ReactionBot] DB load error: {e}")

async def load_reaction_state():
    global REACTION_ENABLED, CHAT_REACTION_OVERRIDES
    try:
        # Load Global Switch
        doc = await SETTINGS.find_one({"_id": "switch"})
        if doc is not None:
            REACTION_ENABLED = doc.get("enabled", True)
        
        # Load Chat Overrides
        cursor = SETTINGS.find({"_id": {"$regex": r"^chat:"}})
        docs = await cursor.to_list(length=None)
        for d in docs:
            try:
                chat_id = int(d["_id"].split(":", 1)[1])
                CHAT_REACTION_OVERRIDES[chat_id] = bool(d.get("enabled", True))
            except:
                continue
    except Exception as e:
        print(f"[ReactionBot] State load error: {e}")

# Start Loaders safely
loop = asyncio.get_event_loop()
loop.create_task(load_custom_mentions())
loop.create_task(load_reaction_state())


def is_reaction_enabled_for_chat(chat_id: int) -> bool:
    """Check if reactions are enabled (Chat Override > Global Setting)"""
    return CHAT_REACTION_OVERRIDES.get(chat_id, REACTION_ENABLED)


async def set_chat_reaction_enabled(chat_id: int, enabled: bool):
    key = f"chat:{chat_id}"
    await SETTINGS.update_one({"_id": key}, {"$set": {"enabled": enabled}}, upsert=True)
    CHAT_REACTION_OVERRIDES[chat_id] = enabled


async def is_admin_or_sudo(client, message_obj) -> Tuple[bool, Optional[str]]:
    # Extract message from CallbackQuery if needed
    message = getattr(message_obj, "message", message_obj)
    user = getattr(message, "from_user", None)
    if not user: return False, "No user"
    
    # Check Owner/Sudo
    if user.id == OWNER_ID or user.id in SUDOERS:
        return True, None
    
    chat = getattr(message, "chat", None)
    if not chat: return False, "No chat"
    
    # Private chat check
    if chat.type == ChatType.PRIVATE:
        return False, "Private chat"

    # Check Admin Status
    try:
        member = await client.get_chat_member(chat.id, user.id)
        if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            return True, None
    except:
        pass
        
    return False, "Not Admin"


# ==============================================================================
#                               COMMAND HANDLERS
# ==============================================================================

@app.on_message(filters.command(["reaction", "react"], prefixes=["/", "!", "%", ",", ".", "@", "#"]))
async def react_command(client, message: Message):
    ok, _ = await is_admin_or_sudo(client, message)
    if not ok:
        return await message.reply_text("⚠️ Only admins can use this.")
    
    chat_id = message.chat.id
    enabled = is_reaction_enabled_for_chat(chat_id)
    
    # The Buttons you requested
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍏 𝐄ɴᴀʙʟᴇ", callback_data=f"react_chat_on:{chat_id}"),
            InlineKeyboardButton("🍎 𝐃ɪsᴀʙʟᴇ", callback_data=f"react_chat_off:{chat_id}")
        ],
        #[
            #InlineKeyboardButton("🗑 Cʟᴇᴀʀ Sᴇᴛᴛɪɴɢs", callback_data=f"react_chat_clear:{chat_id}")
        #]
    ])
    
    status_text = "🍏 𝐄ɴᴀʙʟᴇᴅ" if enabled else "🍎 𝐃ɪsᴀʙʟᴇᴅ"
    await message.reply_text(
        f"**⚙️ Reaction Settings**\n\n"
        f"**Current Chat Status:** {status_text}\n"
        f"Use the buttons below to toggle auto-reactions for this chat.",
        reply_markup=kb
    )


@app.on_callback_query(filters.regex("^react_"))
async def reaction_callback(client, query: CallbackQuery):
    ok, _ = await is_admin_or_sudo(client, query)
    if not ok:
        return await query.answer("⚠️ Admins Only!", show_alert=True)
    
    action = query.data
    try:
        if action.startswith("react_chat_on:"):
            chat_id = int(action.split(":")[1])
            await set_chat_reaction_enabled(chat_id, True)
            await query.edit_message_text(f"✅ **Auto-Reactions Enabled for this chat!**")
            
        elif action.startswith("react_chat_off:"):
            chat_id = int(action.split(":")[1])
            await set_chat_reaction_enabled(chat_id, False)
            await query.edit_message_text(f"❌ **Auto-Reactions Disabled for this chat!**\n(Custom triggers will still work if configured)")
            
        elif action.startswith("react_chat_clear:"):
            chat_id = int(action.split(":")[1])
            key = f"chat:{chat_id}"
            await SETTINGS.delete_one({"_id": key})
            if chat_id in CHAT_REACTION_OVERRIDES:
                del CHAT_REACTION_OVERRIDES[chat_id]
            await query.edit_message_text(f"🧹 **Settings Cleared.** Using global default.")
            
    except Exception as e:
        print(f"Reaction Callback Error: {e}")
        await query.answer("An error occurred.", show_alert=True)


@app.on_message(filters.command("addreact", prefixes=["/"]))
async def add_react(client, message: Message):
    ok, _ = await is_admin_or_sudo(client, message)
    if not ok: return
    
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/addreact <word_or_username>`")
    
    raw = message.text.split(None, 1)[1].strip().lower().lstrip("@")
    
    if raw in custom_mentions:
        return await message.reply_text(f"ℹ️ `{raw}` is already in the list.")

    # Try to resolve ID if it's a username (Feature from reference)
    resolved_id = None
    try:
        user = await client.get_users(raw)
        resolved_id = user.id
    except Exception:
        resolved_id = None

    # Add word
    await COLLECTION.update_one({"name": raw}, {"$set": {"name": raw}}, upsert=True)
    custom_mentions.add(raw)

    # Add ID if resolved
    if resolved_id:
        id_key = f"id:{resolved_id}"
        await COLLECTION.update_one({"name": id_key}, {"$set": {"name": id_key}}, upsert=True)
        custom_mentions.add(id_key)
        await message.reply_text(f"✨ Added trigger: `{raw}` (and ID `{resolved_id}`)")
    else:
        await message.reply_text(f"✨ Added trigger: `{raw}`")


@app.on_message(filters.command("delreact", prefixes=["/"]))
async def del_react(client, message: Message):
    ok, _ = await is_admin_or_sudo(client, message)
    if not ok: return
    
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/delreact <word>`")
    
    word = message.command[1].lower().lstrip("@")
    
    deleted = False
    if word in custom_mentions:
        await COLLECTION.delete_one({"name": word})
        custom_mentions.remove(word)
        deleted = True
        
    # Also try removing ID mapping if user exists
    try:
        user = await client.get_users(word)
        id_key = f"id:{user.id}"
        if id_key in custom_mentions:
            await COLLECTION.delete_one({"name": id_key})
            custom_mentions.remove(id_key)
            deleted = True
    except:
        pass

    if deleted:
        await message.reply_text(f"🗑 Deleted trigger: `{word}`")
    else:
        await message.reply_text(f"❌ `{word}` not found in triggers.")


@app.on_message(filters.command("reactlist", prefixes=["/"]))
async def list_react(client, message: Message):
    if not custom_mentions:
        return await message.reply_text("No triggers found.")
    
    txt = "\n".join(f"• `{x}`" for x in sorted(custom_mentions) if not x.startswith("id:"))
    await message.reply_text(f"**📜 Reaction Triggers (Always Active):**\n\n{txt}")


@app.on_message(filters.command("clearreact", prefixes=["/"]))
async def clear_react(client, message: Message):
    ok, _ = await is_admin_or_sudo(client, message)
    if not ok: return
    
    await COLLECTION.delete_many({})
    custom_mentions.clear()
    for n in (MENTION_USERNAMES or []):
        custom_mentions.add(n.lower().lstrip("@"))
        
    await message.reply_text("🧹 All custom triggers cleared.")


# ==============================================================================
#                               WATCHERS
# ==============================================================================

WORD_RE = re.compile(r"\b([\w@:\-\.]+)\b", flags=re.UNICODE)

def message_words(text: str):
    return set(m.group(1).lower() for m in WORD_RE.finditer(text))

@app.on_message(
    (filters.text | filters.caption) & ~filters.regex(r"^[\\/!.#].*"),
    group=6
)
async def reaction_watcher(client, message: Message):
    if not message.from_user:
        return

    # 1. Ignore Commands explicitly
    text = message.text or message.caption or ""
    if text.strip().startswith(("/", "!", ".", "#", "$")):
        return
    
    chat_id = message.chat.id
    
    # 2. Check Triggers (Mentions/Keywords)
    if not is_reaction_enabled_for_chat(chat_id):
        return

    triggered = False
    
    # Analyze Entities (Mentions)
    entities = (message.entities or []) + (message.caption_entities or [])
    mentioned_users = set()
    
    for ent in entities:
        if ent.type == "mention":
            val = text[ent.offset:ent.offset + ent.length].lstrip("@").lower()
            mentioned_users.add(val)
        elif ent.type == "text_mention" and ent.user:
            mentioned_users.add(f"id:{ent.user.id}")
            if ent.user.username:
                mentioned_users.add(ent.user.username.lower())

    # Check matches in Entities
    for u in mentioned_users:
        if u in custom_mentions:
            try:
                await message.react(next_emoji(chat_id))
            except Exception:
                pass # Ignore invalid reactions
            triggered = True
            break
            
    # Check matches in Text Words
    if not triggered:
        words = message_words(text)
        for trig in custom_mentions:
            if trig in words or trig in text.lower():
                try:
                    await message.react(next_emoji(chat_id))
                except Exception:
                    pass
                triggered = True
                break

    # 3. Auto-React (Random)
    if not triggered:
        if is_reaction_enabled_for_chat(chat_id):
            try:
                await message.react(next_emoji(chat_id))
            except Exception:
                pass


__menu__ = "CMD_CHAT"
__mod_name__ = "H_B_10"
__help__ = """
🔻 /reaction | /react ➠ ᴏᴘᴇɴꜱ ᴀᴜᴛᴏ-ʀᴇᴀᴄᴛɪᴏɴ ꜱᴇᴛᴛɪɴɢꜱ ꜰᴏʀ ᴛʜᴇ ᴄʜᴀᴛ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
🔻 /addreact <ᴡᴏʀᴅ / ᴜꜱᴇʀɴᴀᴍᴇ> ➠ ᴀᴅᴅꜱ ᴀ ᴄᴜꜱᴛᴏᴍ ᴛʀɪɢɢᴇʀ ᴛʜᴀᴛ ᴀᴜᴛᴏ-ʀᴇᴀᴄᴛꜱ ᴡʜᴇɴ ᴍᴇɴᴛɪᴏɴᴇᴅ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
🔻 /delreact <ᴡᴏʀᴅ / ᴜꜱᴇʀɴᴀᴍᴇ> ➠ ʀᴇᴍᴏᴠᴇꜱ ᴀ ꜱᴀᴠᴇᴅ ʀᴇᴀᴄᴛɪᴏɴ ᴛʀɪɢɢᴇʀ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
🔻 /reactlist ➠ ꜱʜᴏᴡꜱ ᴀʟʟ ᴀᴄᴛɪᴠᴇ ʀᴇᴀᴄᴛɪᴏɴ ᴛʀɪɢɢᴇʀꜱ ꜰᴏʀ ᴛʜᴇ ʙᴏᴛ.
🔻 /clearreact ➠ ᴄʟᴇᴀʀꜱ ᴀʟʟ ᴄᴜꜱᴛᴏᴍ ʀᴇᴀᴄᴛɪᴏɴ ᴛʀɪɢɢᴇʀꜱ ᴀɴᴅ ʀᴇꜱᴇᴛꜱ ᴛᴏ ᴅᴇꜰᴀᴜʟᴛ (ᴀᴅᴍɪɴꜱ ᴏɴʟʏ).
"""
