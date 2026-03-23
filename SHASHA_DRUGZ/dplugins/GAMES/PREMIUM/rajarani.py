
# ================= 👑 RAJA RANI GAME MODULE (SHASHA_DRUGZ COMPATIBLE) ================= #
import asyncio
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

from pyrogram import filters, Client
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message
)
from pyrogram.errors import MessageNotModified
from motor.motor_asyncio import AsyncIOMotorClient

import config
from SHASHA_DRUGZ import app

# ================= ⚙️ MONGODB CONFIG ================= #
MONGO_URL = getattr(config, "TEMP_MONGODB", None)
if not MONGO_URL:
    MONGO_URL = getattr(config, "MONGO_DB_URI", None)
if not MONGO_URL:
    raise Exception("MongoDB URL not found in config.")

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["raja_rani_bot"]
users_col = db["users"]
groups_col = db["groups"]
seasons_col = db["seasons"]

# ================= 🎭 ROLE DEFINITIONS (FIXED POINTS) ================= #
ROLES_DATA = {
    "king": {"name": "👑 ᴋɪɴɢ", "base": 1000, "emoji": "👑", "desc": "Ruler. Gets fixed 1000 points."},
    "queen": {"name": "👸 ǫᴜᴇᴇɴ", "base": 900, "emoji": "👸", "desc": "Royal. Gets fixed 900 points."},
    "judge": {"name": "⚖️ ᴊᴜᴅɢᴇ", "base": 800, "emoji": "⚖️", "desc": "Justice. Gets fixed 800 points."},
    "detective": {"name": "🧑‍🎓 ᴅᴇᴛᴇᴄᴛɪᴠᴇ", "base": 700, "emoji": "🧑‍🎓", "desc": "Investigator. Gets fixed 700 points."},
    "magician": {"name": "🧙 ᴍᴀɢɪᴄɪᴀɴ", "base": 600, "emoji": "🧙", "desc": "Trickster. Gets fixed 600 points."},
    "police": {"name": "🕵️ ᴘᴏʟɪᴄᴇ", "base": 500, "emoji": "🕵️", "desc": "Win: 500 | Loss: 0"},
    "thief": {"name": "🥷 ᴛʜɪᴇғ", "base": 500, "emoji": "🥷", "desc": "Win: 500 | Loss: 0"},
    "assassin": {"name": "🧨 ᴀssᴀssɪɴ", "base": 450, "emoji": "🧨", "desc": "Killer. Gets fixed 450 points."},
    "traitor": {"name": "🧛 ᴛʀᴀɪᴛᴏʀ", "base": 400, "emoji": "🧛", "desc": "Betrayer. Gets fixed 400 points."},
    "spy": {"name": "🕶 sᴘʏ", "base": 350, "emoji": "🕶", "desc": "Watcher. Gets fixed 350 points."},
    "milkman": {"name": "🥛 ᴍɪʟᴋᴍᴀɴ", "base": 300, "emoji": "🥛", "desc": "Civilian. Gets fixed 300 points."},
    "villager": {"name": "🧑‍🌾 ᴠɪʟʟᴀɢᴇʀ", "base": 250, "emoji": "🌾", "desc": "Civilian. Gets fixed 250 points."},
    "oracle": {"name": "🧿 ᴏʀᴀᴄʟᴇ", "base": 200, "emoji": "🧿", "desc": "Seer. Gets fixed 200 points."},
    "hypnotist": {"name": "🧠 ʜʏᴘɴᴏᴛɪsᴛ", "base": 150, "emoji": "🧠", "desc": "Mind. Gets fixed 150 points."},
    "shapeshifter": {"name": "🎭 sʜᴀᴘᴇsʜɪғᴛᴇʀ", "base": 100, "emoji": "🎭", "desc": "Shifter. Gets fixed 100 points."},
    "mirror": {"name": "🪞 ᴍɪʀʀᴏʀ", "base": 50, "emoji": "🪞", "desc": "Reflector. Gets fixed 50 points."},
}

# ================= 🛒 SHOP ITEMS ================= #
SHOP_ITEMS = {
    "shield": {"name": "🛡️ sʜɪᴇʟᴅ", "cost": 500, "desc": "Block 1 arrest (Thief Side)"},
    "extra_guess": {"name": "🎟️ ᴇxᴛʀᴀ ɢᴜᴇss", "cost": 700, "desc": "Police gets +1 try"},
    "time_boost": {"name": "⏳ ᴛɪᴍᴇ ʙᴏᴏsᴛ", "cost": 400, "desc": "+15s Police Timer"},
    "reveal": {"name": "🧿 ʀᴇᴠᴇᴀʟ ɢʟɪᴍᴘsᴇ", "cost": 800, "desc": "See 1 random role"},
    "fake_id": {"name": "🎭 ғᴀᴋᴇ-ɪᴅ", "cost": 600, "desc": "Appear innocent to Oracle"},
}

ACHIEVEMENTS = {
    "perfect_police": "🏆 ᴘᴇʀғᴇᴄᴛ ᴘᴏʟɪᴄᴇ",
    "ghost_thief": "🥷 ɢʜᴏsᴛ ᴛʜɪᴇғ",
    "king_slayer": "👑 ᴋɪɴɢ sʟᴀʏᴇʀ",
    "mastermind": "🧠 ᴍᴀsᴛᴇʀᴍɪɴᴅ",
    "veteran": "🎖 ᴠᴇᴛᴇʀᴀɴ",
    "rich": "💰 ᴛʏᴄᴏᴏɴ",
}

STORY_TEXTS = [
    "<blockquote>🌙 **Night falls over the Kingdom...**</blockquote>",
    "<blockquote>💤 **Citizens close their eyes...**</blockquote>",
    "<blockquote>🕵️ **Secret Alliances whisper in the dark...**</blockquote>",
    "<blockquote>⚡ **The Night Phase begins!**</blockquote>",
]

# ================= 🧠 HELPERS ================= #
def get_mention(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

def get_role_name(key):
    return ROLES_DATA.get(key, {}).get("name", key)

def get_current_season():
    return datetime.utcnow().strftime("%Y-%m")

def get_dynamic_roles(count):
    roles = ["king", "police", "thief"]
    if count >= 4: roles.append("queen")
    if count >= 5: roles.append("milkman")
    if count >= 6: roles.append("thief")  # 2nd Thief
    if count >= 7: roles.append("magician")
    if count >= 8: roles.append("villager")
    if count >= 9: roles.append("judge")
    if count >= 10: roles.append("traitor")
    if count >= 11: roles.append("detective")
    if count >= 12: roles.append("police")  # 2nd Police
    if count >= 13: roles.append("hypnotist")
    if count >= 14: roles.append("spy")
    if count >= 15: roles.append("assassin")
    if count >= 16: roles.append("oracle")
    if count >= 17: roles.append("shapeshifter")
    if count >= 18: roles.append("mirror")
    while len(roles) < count:
        roles.append("villager")
    return roles[:count]

# --- STATS & SHOP ENGINE ---
async def update_stats(user_id, chat_id, name, points, won=False, role=None, quick_win=False):
    now = datetime.utcnow()
    season = get_current_season()
    user_doc = await users_col.find_one({"_id": user_id})
    achievements = user_doc.get("achievements", []) if user_doc else []
    streak = 1
    daily_bonus = 0
    if user_doc and user_doc.get("last_played"):
        diff = now - user_doc["last_played"]
        if diff.days == 1:
            streak = user_doc.get("streak", 0) + 1
        elif diff.days > 1:
            streak = 1
        if user_doc["last_played"].date() != now.date():
            daily_bonus = 200
    new_badges = []
    if won:
        if role == "thief" and "ghost_thief" not in achievements:
            achievements.append("ghost_thief")
            new_badges.append(ACHIEVEMENTS["ghost_thief"])
        if role == "police" and quick_win and "perfect_police" not in achievements:
            achievements.append("perfect_police")
            new_badges.append(ACHIEVEMENTS["perfect_police"])
        if role == "assassin" and "king_slayer" not in achievements:
            achievements.append("king_slayer")
            new_badges.append(ACHIEVEMENTS["king_slayer"])
    total_add = points + daily_bonus
    if streak == 3:
        total_add += 500
    await users_col.update_one(
        {"_id": user_id},
        {"$inc": {"points": total_add, "total_games": 1, "total_wins": 1 if won else 0},
         "$set": {"name": name, "last_played": now, "streak": streak, "achievements": achievements}},
        upsert=True
    )
    await seasons_col.update_one(
        {"season": season, "user_id": user_id},
        {"$inc": {"points": total_add}, "$set": {"name": name}},
        upsert=True
    )
    await groups_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"points": total_add}, "$set": {"name": name}},
        upsert=True
    )
    return new_badges

async def purchase_item(user_id, item_key):
    user = await users_col.find_one({"_id": user_id})
    if not user:
        return "❌ You need to play a game first!"
    cost = SHOP_ITEMS[item_key]["cost"]
    points = user.get("points", 0)
    inventory = user.get("inventory", [])
    if points < cost:
        return f"❌ Not enough points! Need {cost}."
    if item_key in inventory:
        return "⚠️ You already have this item!"
    await users_col.update_one(
        {"_id": user_id},
        {"$inc": {"points": -cost}, "$push": {"inventory": item_key}}
    )
    return f"✅ ʙᴏᴜɢʜᴛ **{SHOP_ITEMS[item_key]['name']}**!"

async def consume_item(user_id, item_key):
    await users_col.update_one({"_id": user_id}, {"$pull": {"inventory": item_key}})

async def get_inventory(user_id):
    user = await users_col.find_one({"_id": user_id})
    return user.get("inventory", []) if user else []

async def get_global_top():
    cursor = users_col.find().sort("points", -1).limit(10)
    return await cursor.to_list(length=10)

async def get_group_top(chat_id):
    cursor = groups_col.find({"chat_id": chat_id}).sort("points", -1).limit(10)
    return await cursor.to_list(length=10)

# ================= 🎮 GAME STORAGE ================= #
games: Dict[int, dict] = {}

class Game:
    def __init__(self, chat_id, creator_id, lobby_msg):
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.lobby_msg = lobby_msg
        self.players = {}
        self.roles = {}
        self.status = "waiting"
        self.lock = asyncio.Lock()
        self.police_ids = []
        self.thief_ids = []
        self.caught_thieves = []
        self.hypnotized = False
        self.judge_used = False
        self.extra_guess_used = False
        self.start_time = 0
        self.task_timer = None
        self.alliances = []
        self.left_players = {}
        self.active_items = {}

    def add_player(self, user_id, name):
        if user_id in self.left_players:
            if time.time() - self.left_players[user_id]['time'] < 30:
                self.players[user_id] = name
                del self.left_players[user_id]
                return "restored"
        if user_id not in self.players:
            self.players[user_id] = name
            return True
        return False

@Client.on_message(filters.command("rrshowroles"))
async def show_roles_handler(client, message):
    text = "**🎭 ᴀʟʟ ʀᴏʟᴇs & ᴅᴇsᴄʀɪᴘᴛɪᴏɴs:**\n\n"
    for key, data in ROLES_DATA.items():
        text += f"<blockquote>{data['emoji']} **{data['name']}**: {data['desc']} (Pts: {data['base']})</blockquote>\n"
    await message.reply(text)

@Client.on_message(filters.command("rajaranirules"))
async def rules_handler(client, message):
    text = (
        "<blockquote>📜 **ɢᴀᴍᴇ ɪɴsᴛʀᴜᴄᴛɪᴏɴs:**\n"
        "1. **ᴊᴏɪɴ:** 3-20 ᴘʟᴀʏᴇʀs ᴊᴏɪɴ ᴀ ʟᴏʙʙʏ.\n"
        "2. **ʀᴏʟᴇs:** ᴇᴠᴇʀʏᴏɴᴇ ɢᴇᴛs ᴀ sᴇᴄʀᴇᴛ ʀᴏʟᴇ.\n"
        "3. **ɴɪɢʜᴛ ᴘʜᴀsᴇ:** sᴘᴇᴄɪᴀʟ ʀᴏʟᴇs ᴀᴄᴛ ᴘʀɪᴠᴀᴛᴇʟʏ. Thieves chat.\n"
        "4. **ᴘᴏʟɪᴄᴇ ᴘʜᴀsᴇ:** ᴛʜᴇ ᴘᴏʟɪᴄᴇ ᴍᴜsᴛ ғɪɴᴅ ᴛʜᴇ ᴛʜɪᴇᴠᴇs.</blockquote>\n"
        "<blockquote>**ᴡɪɴ ᴄᴏɴᴅɪᴛɪᴏɴs:**\n"
        "👮 **ᴘᴏʟɪᴄᴇ:** 500 Pts if they catch Thieves. 0 if they lose.\n"
        "🥷 **ᴛʜɪᴇғ:** 500 Pts if they escape. 0 if caught.\n"
        "👑 **OTHERS:** Everyone else gets fixed points regardless of result.</blockquote>\n\n"
    )
    await message.reply(text)


# --- SHOP LOGIC ---
@Client.on_message(filters.command("rrshop"))
@Client.on_callback_query(filters.regex("open_shop"))
async def shop_handler(client, update):
    is_cb = isinstance(update, CallbackQuery)
    user = update.from_user
    user_doc = await users_col.find_one({"_id": user.id})
    points = user_doc.get("points", 0) if user_doc else 0
    inventory = user_doc.get("inventory", []) if user_doc else []
    text = f"<blockquote>🏪 **ɢᴀᴍᴇ sʜᴏᴘ**</blockquote>\n<blockquote>💰 ʏᴏᴜʀ ᴘᴏɪɴᴛs: **{points}**\n🎒 ɪɴᴠᴇɴᴛᴏʀʏ: {', '.join(inventory) if inventory else 'Empty'}</blockquote>\n<blockquote>sᴇʟᴇᴄᴛ ᴀɴ ɪᴛᴇᴍ ᴛᴏ ʙᴜʏ:</blockquote>"
    btns = []
    for key, item in SHOP_ITEMS.items():
        btns.append([InlineKeyboardButton(f"{item['name']} - {item['cost']} pts", callback_data=f"buy_{key}")])
    btns.append([InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="start_menu")])
    markup = InlineKeyboardMarkup(btns)
    if is_cb:
        await update.message.edit_text(text, reply_markup=markup)
    else:
        await update.reply(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"buy_(\w+)"))
async def buy_callback(client, callback):
    item_key = callback.matches[0].group(1)
    res = await purchase_item(callback.from_user.id, item_key)
    await callback.answer(res, show_alert=True)
    await shop_handler(client, callback)  # Refresh

@Client.on_message(filters.command(["rrprofile", "rrrank"]))
@Client.on_callback_query(filters.regex("my_profile"))
async def profile_handler(client, update):
    is_cb = isinstance(update, CallbackQuery)
    user = update.from_user
    uid = user.id
    doc = await users_col.find_one({"_id": uid})
    if not doc:
        txt = "❌ ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ᴀɴʏ ɢᴀᴍᴇs ʏᴇᴛ!"
        if is_cb:
            await update.answer(txt, show_alert=True)
        else:
            await update.reply(txt)
        return
    wins = doc.get("total_wins", 0)
    games_count = doc.get("total_games", 0)
    win_rate = int((wins / games_count) * 100) if games_count > 0 else 0
    badges_list = doc.get("achievements", [])
    badges = "\n".join([f"• {ACHIEVEMENTS.get(b, b)}" for b in badges_list]) if badges_list else "None"
    text = (
        f"<blockquote>👤 **ᴘʟᴀʏᴇʀ ᴄᴀʀᴅ: {user.first_name}**</blockquote>\n"
        f"<blockquote>💰 ᴘᴏɪɴᴛs: {doc.get('points', 0)}\n"
        f"📊 ᴡɪɴ ʀᴀᴛᴇ: {win_rate}% ({wins}/{games_count})\n"
        f"🔥 sᴛʀᴇᴀᴋ: {doc.get('streak', 0)} ᴅᴀʏs</blockquote>\n"
        f"<blockquote>🏆 **ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛs:**\n{badges}</blockquote>"
    )
    if is_cb:
        await update.message.edit_text(text)
    else:
        await update.reply(text)

# ================= 🎮 LOBBY SYSTEM ================= #
@Client.on_message(filters.command("rajarani") & filters.group)
async def lobby_create(client, message):
    chat_id = message.chat.id
    if chat_id in games:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 END GAME", callback_data="end_game_btn")]])
        await message.reply("⚠️ ɢᴀᴍᴇ ɪs ʀᴜɴɴɪɴɢ!\nᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ғᴏʀᴄᴇ sᴛᴏᴘ.", reply_markup=btn)
        return
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("✋ ᴊᴏɪɴ ɢᴀᴍᴇ", callback_data="rr_join")]])
    lobby_msg = await message.reply(
        f"<blockquote>**👑 ʀᴀᴊᴀ ʀᴀɴɪ: ᴜʟᴛɪᴍᴀᴛᴇ ᴇᴅɪᴛɪᴏɴ**</blockquote>\n<blockquote>ᴄʟɪᴄᴋ **ᴊᴏɪɴ** ᴛᴏ ᴇɴᴛᴇʀ!</blockquote>",
        reply_markup=markup
    )
    games[chat_id] = Game(chat_id, message.from_user.id, lobby_msg)

@Client.on_message(filters.command("rrjoin") & filters.group)
@Client.on_callback_query(filters.regex("rr_join"))
async def join_handler(client, update):
    is_callback = isinstance(update, CallbackQuery)
    user = update.from_user
    if not is_callback:
        message = update
        chat_id = message.chat.id
        try:
            await message.delete()
        except:
            pass
    else:
        message = update.message
        chat_id = message.chat.id
    if chat_id not in games:
        if is_callback:
            await update.answer("Expired.")
        return
    game = games[chat_id]
    async with game.lock:
        if game.status != "waiting":
            if is_callback:
                await update.answer("ɢᴀᴍᴇ sᴛᴀʀᴛᴇᴅ!")
            return
        res = game.add_player(user.id, user.first_name)
        if res is False:
            if is_callback:
                await update.answer("Already In!")
            return
        if is_callback:
            await update.answer("Joined!")
        count = len(game.players)
        p_list = "\n".join([f"• {get_mention(u, n)}" for u, n in game.players.items()])
        text = f"<blockquote>**👑 ʀᴀᴊᴀ ʀᴀɴɪ: ʟᴏʙʙʏ**</blockquote>\n<blockquote>ᴘʟᴀʏᴇʀs ({count}/20):\n{p_list}</blockquote>\n\n<blockquote>ᴄʟɪᴄᴋ **ᴊᴏɪɴ** or `/join`</blockquote>"
        rows = [[InlineKeyboardButton("🕹️ ᴊᴏɪɴ ɢᴀᴍᴇ", callback_data="rr_join")]]
        if count >= 3:
            rows.append([InlineKeyboardButton("▶️ ғᴏʀᴄᴇ sᴛᴀʀᴛ", callback_data="rr_start")])
        markup = InlineKeyboardMarkup(rows)
        try:
            if is_callback:
                await message.edit_text(text, reply_markup=markup)
            elif game.lobby_msg:
                try:
                    await game.lobby_msg.edit_text(text, reply_markup=markup)
                except MessageNotModified:
                    pass
                except Exception:
                    game.lobby_msg = await client.send_message(chat_id, text, reply_markup=markup)
        except Exception as e:
            print(f"Lobby Update Error: {e}")
        if count == 20:
            await start_game_sequence(client, chat_id)

@Client.on_callback_query(filters.regex("rr_start"))
async def force_start_btn(client, callback):
    chat_id = callback.message.chat.id
    game = games.get(chat_id)
    if not game:
        return
    if callback.from_user.id != game.creator_id:
        await callback.answer("❌ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ ᴄʀᴇᴀᴛᴏʀ ᴄᴀɴ ғᴏʀᴄᴇ sᴛᴀʀᴛ!", show_alert=True)
        return
    if len(game.players) < 3:
        await callback.answer("ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ 3 ᴘʟᴀʏᴇʀs!", show_alert=True)
        return
    await callback.answer("🚀 sᴛᴀʀᴛɪɴɢ ɢᴀᴍᴇ...")
    await start_game_sequence(client, chat_id)

@Client.on_message(filters.command("rrend") & filters.group)
async def end_game_cmd(client, message):
    chat_id = message.chat.id
    if chat_id not in games:
        await message.reply("⚠️ ɴᴏ ɢᴀᴍᴇ ɪs ʀᴜɴɴɪɴɢ!")
        return
    game = games[chat_id]
    if game.task_timer:
        game.task_timer.cancel()
    del games[chat_id]
    await message.reply(f"<blockquote>🍎 **ɢᴀᴍᴇ ғᴏʀᴄᴇ-ᴇɴᴅᴇᴅ** ʙʏ {message.from_user.first_name}!</blockquote>\n<blockquote>/rajarani ᴛᴏ sᴛᴀʀᴛ ɴᴇᴡ.</blockquote>")

@Client.on_callback_query(filters.regex("end_game_btn"))
async def end_game_btn_handler(client, callback):
    chat_id = callback.message.chat.id
    if chat_id not in games:
        await callback.answer("Game already ended.", show_alert=True)
        try:
            await callback.message.delete()
        except:
            pass
        return
    game = games[chat_id]
    if game.task_timer:
        game.task_timer.cancel()
    del games[chat_id]
    try:
        await callback.message.edit_text(f"<blockquote>🍎 **ɢᴀᴍᴇ ғᴏʀᴄᴇ-ᴇɴᴅᴇᴅ** ʙʏ {callback.from_user.first_name}!</blockquote>")
    except:
        pass
    await client.send_message(chat_id, "<blockquote>✅ ɢᴀᴍᴇ ᴄʟᴇᴀʀᴇᴅ! /rajarani ᴛᴏ ᴘʟᴀʏ.</blockquote>")

# ================= ⚙️ GAME ENGINE ================= #
async def start_game_sequence(client, chat_id):
    game = games[chat_id]
    game.status = "starting"
    msg = await client.send_message(chat_id, "🎲 **ʀᴏʟʟɪɴɢ ᴅɪᴄᴇ...**")
    for txt in ["🎲 **ᴀssɪɢɴɪɴɢ ʀᴏʟᴇs...**", "👑 **ɢᴀᴍᴇ sᴛᴀʀᴛɪɴɢ!**"]:
        await asyncio.sleep(1)
        await msg.edit_text(txt)
    p_ids = list(game.players.keys())
    random.shuffle(p_ids)
    role_list = get_dynamic_roles(len(p_ids))
    random.shuffle(role_list)
    for i, uid in enumerate(p_ids):
        r = role_list[i]
        game.roles[uid] = r
        if r == "police":
            game.police_ids.append(uid)
        if r == "thief":
            game.thief_ids.append(uid)
        inv = await get_inventory(uid)
        if inv:
            game.active_items[uid] = inv
    if len(p_ids) >= 5:
        game.alliances.append(tuple(random.sample(p_ids, 2)))
    await msg.edit_text("📖 **ᴛʜᴇ sᴛᴏʀʏ ʙᴇɢɪɴs...**")
    for line in STORY_TEXTS:
        await asyncio.sleep(1.5)
        await msg.edit_text(line)
    btns = InlineKeyboardMarkup([[InlineKeyboardButton("👀 ᴄʜᴇᴄᴋ ʀᴏʟᴇ", callback_data="rr_check")]])
    await msg.edit_text("🎭 **ɪᴅᴇɴᴛɪᴛɪᴇs ᴀssɪɢɴᴇᴅ!**\nᴄʜᴇᴄᴋ ᴄᴀʀᴇғᴜʟʟʏ.", reply_markup=btns)
    await asyncio.sleep(8)
    await night_phase(client, chat_id)

async def night_phase(client, chat_id):
    if chat_id not in games:
        return
    btns = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ ʙᴜʏ 𝗌ʜᴏᴘ", callback_data="night_menu")]
    ])
    msg = await client.send_message(chat_id, "🌑 **sʜᴏᴘ ɪᴛᴇᴍss(15s)**\nsᴘᴇᴄɪᴀʟ ʀᴏʟᴇs & ᴛᴏᴋᴇɴ𝗌 ᴀᴄᴛ ɴᴏᴡ!", reply_markup=btns)
    await asyncio.sleep(15)
    try:
        await msg.delete()
    except:
        pass
    if chat_id in games:
        await police_round(client, chat_id)

async def police_round(client, chat_id):
    if chat_id not in games:
        return
    game = games[chat_id]
    game.status = "guessing"
    game.start_time = time.time()
    p_names = ", ".join([game.players[p] for p in game.police_ids])
    bonus_time = 0
    for pid in game.police_ids:
        if "time_boost" in game.active_items.get(pid, []):
            bonus_time = 15
            await consume_item(pid, "time_boost")
            await client.send_message(chat_id, "⏳ **ɪᴛᴇᴍ ᴀᴄᴛɪᴠᴀᴛᴇᴅ:** ᴛɪᴍᴇ ʙᴏᴏsᴛ (+15s) ʙʏ ᴘᴏʟɪᴄᴇ!")
    btns = []
    for uid, name in game.players.items():
        if uid not in game.police_ids and uid not in game.caught_thieves:
            btns.append(
                InlineKeyboardButton(
                    f"{name}",
                    callback_data=f"guess_{uid}"
                )
            )
    markup = []
    row = []
    for btn in btns:
        row.append(btn)
        if len(row) == 1:
            markup.append(row)
            row = []
    if row:
        markup.append(row)
    await client.send_message(
        chat_id,
        f"<blockquote>👮‍♂️ **ᴘᴏʟɪᴄᴇ ᴀssᴀᴜʟᴛ**\n</blockquote>"
        f"<blockquote>ᴏғғɪᴄᴇʀs: {p_names}\n</blockquote>"
        f"<blockquote>ᴄᴀᴛᴄʜ ᴛʜᴇ ᴛʜɪᴇᴠᴇs! ({len(game.thief_ids) - len(game.caught_thieves)} ʀᴇᴍᴀɪɴɪɴɢ)</blockquote>",
        reply_markup=InlineKeyboardMarkup(markup)
    )
    game.task_timer = asyncio.create_task(game_timeout(client, chat_id, 60 + bonus_time))

async def game_timeout(client, chat_id, duration):
    try:
        remaining = duration
        while remaining > 0:
            step = 20 if remaining >= 20 else remaining
            await asyncio.sleep(step)
            remaining -= step
            game = games.get(chat_id)
            if not game or game.status != "guessing":
                return
            if remaining > 0:
                try:
                    await client.send_message(chat_id, f"<blockquote>⏳ **ғɪɴᴅ ᴛʜɪᴇғ! {remaining}s ʀᴇᴍᴀɪɴɪɴɢ!**</blockquote>")
                except:
                    pass
        await resolve_game(client, chat_id, "thief", "⏰ Time Up! Police failed.")
    except asyncio.CancelledError:
        pass

@Client.on_callback_query(filters.regex("night_menu"))
async def night_menu_handle(client, callback):
    game = games.get(callback.message.chat.id)
    if not game:
        return
    uid = callback.from_user.id
    if uid not in game.roles:
        return
    role = game.roles[uid]
    items = game.active_items.get(uid, [])
    text = f"🌙 **ɴɪɢʜᴛ ᴍᴇɴᴜ: {ROLES_DATA[role]['name']}**\n🎒 ɪᴛᴇᴍs: {', '.join(items) if items else 'None'}\n"
    if role == "thief":
        partners = [game.players[t] for t in game.thief_ids if t != uid]
        text += f"\n🥷 **ᴛʜɪᴇғ ᴄʜᴀᴛ:**\nᴘᴀʀᴛɴᴇʀs: {', '.join(partners) if partners else 'Alone'}"
    elif role == "police":
        partners = [game.players[p] for p in game.police_ids if p != uid]
        text += f"\n👮 **ᴘᴏʟɪᴄᴇ ʀᴀᴅɪᴏ:**\nʙᴀᴄᴋᴜᴘ: {', '.join(partners) if partners else 'None'}"
    if role == "hypnotist":
        game.hypnotized = True
        text += "\n✅ **ᴀᴄᴛɪᴏɴ:** ᴘᴏʟɪᴄᴇ ʜʏᴘɴᴏᴛɪᴢᴇᴅ!"
    elif role == "oracle" or "reveal" in items:
        target = random.choice(list(game.players.keys()))
        t_items = game.active_items.get(target, [])
        role_shown = ROLES_DATA[game.roles[target]]['name']
        if "fake_id" in t_items:
            role_shown = "🧑‍🌾 ᴠɪʟʟᴀɢᴇʀ (ғᴀᴋᴇ-ɪᴅ)"
        text += f"\n✅ **ᴠɪsɪᴏɴ:** {game.players[target]} is {role_shown}"
        if "reveal" in items:
            await consume_item(uid, "reveal")
    elif role == "magician":
        text += "\n✅ **ᴀᴄᴛɪᴏɴ:** ʀᴏʟᴇs sᴡᴀᴘᴘᴇᴅ! (ᴄᴏsᴍᴇᴛɪᴄ)"
    await callback.answer(text, show_alert=True)

@Client.on_callback_query(filters.regex("rr_check"))
async def check_role_btn(client, callback):
    game = games.get(callback.message.chat.id)
    uid = callback.from_user.id
    if not game or uid not in game.roles:
        await callback.answer("Not playing.")
        return
    r = game.roles[uid]
    d = ROLES_DATA[r]
    txt = f"ʏᴏᴜʀ ɪᴅᴇɴᴛɪᴛʏ: {d['name']}\n{d.get('desc', '')}"
    if r == "thief" and len(game.thief_ids) > 1:
        partners = [game.players[t] for t in game.thief_ids if t != uid]
        txt += f"\n\n🥷 **ᴘᴀʀᴛɴᴇʀs:** {', '.join(partners)}"
    if r == "spy" and game.police_ids:
        p_target = random.choice(game.police_ids)
        txt += f"\n\n🕶 **ɪɴᴛᴇʟ:** {game.players[p_target]} ɪs ᴘᴏʟɪᴄᴇ!"
    for pair in game.alliances:
        if uid in pair:
            pid = pair[0] if pair[1] == uid else pair[1]
            txt += f"\n\n🤝 **ᴀʟʟɪᴀɴᴄᴇ:** sᴇᴄʀᴇᴛʟʏ ʟɪɴᴋᴇᴅ ᴡɪᴛʜ {game.players[pid]}!"
    await callback.answer(txt, show_alert=True)

@Client.on_callback_query(filters.regex(r"guess_(\d+)"))
async def guess_handle(client, callback):
    game = games.get(callback.message.chat.id)
    if not game or game.status != "guessing":
        return
    uid = callback.from_user.id
    if uid not in game.police_ids:
        await callback.answer("👮‍♂️ ᴏɴʟʏ ᴘᴏʟɪᴄᴇ ᴄᴀɴ ᴀʀʀᴇsᴛ!", show_alert=True)
        return
    if game.hypnotized:
        game.hypnotized = False
        await callback.answer("😵 ʏᴏᴜ ᴀʀᴇ ʜʏᴘɴᴏᴛɪᴢᴇᴅ! (ᴛᴜʀɴ sᴋɪᴘᴘᴇᴅ)", show_alert=True)
        return
    target_id = int(callback.matches[0].group(1))
    t_role = game.roles[target_id]
    t_items = game.active_items.get(target_id, [])
    if t_role == "assassin":
        await resolve_game(client, game.chat_id, "thief", "🧨 **ʙᴏᴏᴍ!** ᴘᴏʟɪᴄᴇ ᴄʟɪᴄᴋᴇᴅ ᴛʜᴇ ᴀssᴀssɪɴ!")
        return
    if t_role == "mirror":
        candidates = [u for u in game.players if u != target_id]
        if candidates:
            redirect = random.choice(candidates)
            t_role = game.roles[redirect]
            t_items = game.active_items.get(redirect, [])
            await callback.answer(f"🪞 ᴍɪʀʀᴏʀ ʀᴇғʟᴇᴄᴛᴇᴅ ɢᴜᴇss ᴛᴏ {game.players[redirect]}!", show_alert=True)
            target_id = redirect
    if t_role == "thief":
        if target_id not in game.caught_thieves:
            game.caught_thieves.append(target_id)
            if len(game.caught_thieves) == len(game.thief_ids):
                if game.task_timer:
                    game.task_timer.cancel()
                await resolve_game(client, game.chat_id, "police", "✅ **ᴠɪᴄᴛᴏʀʏ!** ᴀʟʟ ᴛʜɪᴇᴠᴇs ᴄᴀᴜɢʜᴛ!")
            else:
                await callback.answer("✅ ᴛʜɪᴇғ ᴄᴀᴜɢʜᴛ! ᴋᴇᴇᴘ sᴇᴀʀᴄʜɪɴɢ.", show_alert=True)
                await callback.message.edit_text("👮‍♂️ **ᴛʜɪᴇғ ᴅᴏᴡɴ!** ᴋᴇᴇᴘ ɢᴏɪɴɢ!")
        else:
            await callback.answer("ᴀʟʀᴇᴀᴅʏ ᴄᴀᴜɢʜᴛ.")
    else:
        if "extra_guess" in game.active_items.get(uid, []) and not game.extra_guess_used:
            game.extra_guess_used = True
            await consume_item(uid, "extra_guess")
            await callback.answer("🎟️ ᴇxᴛʀᴀ ɢᴜᴇss ᴛᴏᴋᴇɴ ᴜsᴇᴅ! ᴛʀʏ ᴀɢᴀɪɴ!", show_alert=True)
            return
        if game.task_timer:
            game.task_timer.cancel()
        await resolve_game(client, game.chat_id, "thief", f"❌ **ᴡʀᴏɴɢ!** ᴀʀʀᴇsᴛᴇᴅ {ROLES_DATA[t_role]['name']}")

# ================= 🏁 END GAME (FIXED POINTS SCORING) ================= #
async def resolve_game(client, chat_id, winner, reason):
    game = games[chat_id]
    del games[chat_id]
    scores = []
    mvp_name, max_pts = "None", 0
    for uid, role in game.roles.items():
        data = ROLES_DATA.get(role, {})
        base_points = data.get("base", 0)
        pts = 0
        won = False
        if role == "police":
            if winner == "police":
                pts = 500
                won = True
            else:
                pts = 0
        elif role == "thief":
            if winner == "thief":
                pts = 500
                won = True
            else:
                pts = 0
        else:
            pts = base_points
            won = True
        badges = await update_stats(
            uid,
            chat_id,
            game.players[uid],
            pts,
            won=won,
            role=role,
            quick_win=False
        )
        entry = f"{data['name']} - {game.players[uid]}: +{pts}"
        if badges:
            entry += f" ({len(badges)}🏅)"
        scores.append(entry)
        if pts > max_pts:
            max_pts = pts
            mvp_name = game.players[uid]
    villains = ", ".join(game.players[t] for t in game.thief_ids)
    msg = (
        f"<blockquote>{reason}</blockquote>\n"
        f"<blockquote>📊 **ғɪɴᴀʟ sᴄᴏʀᴇʙᴏᴀʀᴅ**\n"
        f"{chr(10).join(scores)}</blockquote>"
        f"<blockquote>\n\n🏆 **ᴍᴠᴘ:** {mvp_name}\n"
        f"😈 **ᴠɪʟʟᴀɪɴ:** {villains}\n</blockquote>"
        f"<blockquote>/rajarani ᴛᴏ ᴘʟᴀʏ ᴀɢᴀɪɴ!</blockquote>"
    )
    await client.send_message(chat_id, msg)

# ================= 🏆 LEADERBOARDS ================= #
@Client.on_message(filters.command("rrtop"))
async def top_command(client, message):
    data = await get_group_top(message.chat.id)
    text = f"<blockquote>🏆 **ɢʀᴏᴜᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**</blockquote>\n\n"
    if not data:
        text += "<blockquote>ɴᴏ ʀᴇᴄᴏʀᴅs.</blockquote>"
    for i, u in enumerate(data, 1):
        if i == 1:
            rank_str = "🥇"
        elif i == 2:
            rank_str = "🥈"
        elif i == 3:
            rank_str = "🥉"
        else:
            rank_str = f"{i}."
        text += f"<blockquote>{rank_str} {u.get('name')} - {u.get('points')}</blockquote>\n"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 ᴏᴠᴇʀᴀʟʟ", callback_data="top_global")]
    ])
    await message.reply(text, reply_markup=buttons)

@Client.on_callback_query(filters.regex("top_group"))
async def top_group_cb(client, callback):
    data = await get_group_top(callback.message.chat.id)
    text = f"<blockquote>🏆 **ɢʀᴏᴜᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**</blockquote>\n\n"
    if not data:
        text += "<blockquote>ɴᴏ ʀᴇᴄᴏʀᴅs.</blockquote>"
    for i, u in enumerate(data, 1):
        if i == 1:
            rank_str = "🥇"
        elif i == 2:
            rank_str = "🥈"
        elif i == 3:
            rank_str = "🥉"
        else:
            rank_str = f"{i}."
        text += f"<blockquote>{rank_str} {u.get('name')} - {u.get('points')}</blockquote>\n"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 ᴏᴠᴇʀᴀʟʟ", callback_data="top_global")]
    ])
    await callback.message.edit_text(text, reply_markup=buttons)

@Client.on_callback_query(filters.regex("top_global"))
async def top_global_cb(client, callback):
    data = await get_global_top()
    text = "<blockquote>🌍 <b>ɢʟᴏʙᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b></blockquote>\n\n"
    if not data:
        text += "<blockquote>ɴᴏ ʀᴇᴄᴏʀᴅs.</blockquote>"
    else:
        for i, u in enumerate(data, 1):
            if i == 1:
                rank_str = "🥇"
            elif i == 2:
                rank_str = "🥈"
            elif i == 3:
                rank_str = "🥉"
            else:
                rank_str = f"{i}."
            text += f"<blockquote>{rank_str} {u.get('name')} - {u.get('points')}</blockquote>\n"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 ᴛʜɪs ɢʀᴏᴜᴘ", callback_data="top_group")]
    ])
    await callback.message.edit_text(
        text,
        reply_markup=buttons,
        disable_web_page_preview=True
    )


__menu__ = "CMD_GAMES"
__mod_name__ = "H_B_39"
__help__ = """
🔻 /rajarani ➠ sᴛᴀʀᴛs ᴀ ɴᴇᴡ ʀᴀᴊᴀ ʀᴀɴɪ ɢᴀᴍᴇ ʟᴏʙʙʏ.
🔻 /rrjoin ➠ ᴊᴏɪɴs ᴛʜᴇ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.
🔻 /rrend ➠ ғᴏʀᴄᴇ ᴇɴᴅs ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ɢᴀᴍᴇ.
🔻 /rrshowroles ➠ sʜᴏᴡs ᴀʟʟ ʀᴏʟᴇs ᴀɴᴅ ᴛʜᴇɪʀ ᴘᴏɪɴᴛs.
🔻 /rajaranirules ➠ ᴅɪsᴘʟᴀʏs ᴄᴏᴍᴘʟᴇᴛᴇ ɢᴀᴍᴇ ɪɴsᴛʀᴜᴄᴛɪᴏɴs.
🔻 /rrshop ➠ ᴏᴘᴇɴs ᴛʜᴇ ɢᴀᴍᴇ sʜᴏᴘ ᴛᴏ ʙᴜʏ ɪᴛᴇᴍs.
🔻 /rrprofile ➠ sʜᴏᴡs ʏᴏᴜʀ ᴘʟᴀʏᴇʀ ᴘʀᴏғɪʟᴇ & sᴛᴀᴛs.
🔻 /rrrank ➠ sʜᴏᴡs ʏᴏᴜʀ ʀᴀɴᴋ & sᴛᴀᴛɪsᴛɪᴄs.
🔻 /rrtop ➠ sʜᴏᴡs ɢʀᴏᴜᴘ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ.
"""

MOD_TYPE = "GAMES"
MOD_NAME = "Raja Rani"
MOD_PRICE = "250"
