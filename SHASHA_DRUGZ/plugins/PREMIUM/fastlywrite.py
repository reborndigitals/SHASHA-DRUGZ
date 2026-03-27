import os
import random
import asyncio
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import redis.asyncio as redis
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMemberStatus
from PIL import Image, ImageDraw, ImageFont

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import get_collection
from config import REDIS_URL

# ================================================================
# ROOT CAUSE EXPLANATION — READ BEFORE EDITING
# ================================================================
# Pyrogram dispatches messages to handler groups in NUMERIC ORDER:
#   group=-1 runs FIRST  (before everything)
#   group=0  runs second (default — chatbot, reactionbot live here)
#   group=100 runs LAST
#
# Previous version used group=100.  If chatbot / reactionbot /
# any other module registers @app.on_message(filters.text) at
# group=0 WITHOUT calling continue_propagation(), Pyrogram stops
# dispatching that message completely.  group=100 NEVER RUNS.
# That is the sole reason correct words got zero response.
#
# Fix: check_word is now registered at group=-1.  It runs before
# every other module.  Non-game messages are passed through via
# continue_propagation() so chatbot / reactionbot still work.
# ================================================================

# ── Redis ───────────────────────────────────────────────────────
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# ── MongoDB ─────────────────────────────────────────────────────
score_col = get_collection("fastly_scores")
meta_col  = get_collection("fastly_meta")

# ── Thread pool (image generation is CPU-bound / I/O) ───────────
_executor = ThreadPoolExecutor(max_workers=4)

# ================================================================
# WORD LIST
# ================================================================
WORD_FILE = "SHASHA_DRUGZ/assets/shasha/fastly_words.txt"
try:
    with open(WORD_FILE) as f:
        WORDS = [w.strip() for w in f if w.strip()]
except Exception:
    WORDS = [
        "angel","amour","adorer","affair","bliss","beauty","bloom","butter","charm","cherub",
        "caring","cutely","cuddle","cozily","cupcake","darling","dearly","dazzle","dreamy","devote",
        "delight","enchant","endear","esteem","embrace","eternal","fairy","fluffy","fancy","friend",
        "glimmer","glow","gentle","giggly","grace","golden","happy","hugger","honey","honest",
        "hearty","heart","idolize","innocent","jolly","joyful","joyous","kindly","kindred","lovely",
        "loving","lively","lilies","luster","magnet","marvel","mellow","mercy","miracle","muse",
        "nectar","nice","noble","pearly","petals","precious","pretty","purely","queen","quirky",
        "radiant","romance","rosy","rosebud","sweety","sweet","smiley","smiles","spark","starry",
        "sunny","sunbeam","tender","trusty","treasure","true","twinkle","unity","velvet","warmly",
        "wonder","worthy","xoxo","youth","zephyr","adoring","amazing","amused","angelic","ardent",
        "beaming","believe","blushy","bouncy","bright","bubbly","buttery","calmly","candor","careful",
        "caress","cheery","cherry","chic","chipper","chummy","classy","clever","cozy","cuddly",
        "dapper","daring","decent","dewy","divine","dream","elegant","elated","energy","ethereal",
        "fable","favor","feisty","festive","fiesta","flirty","fondly","forever","fortune","fresh",
        "frisky","funny","galaxy","gent","gleam","glossy","grateful","groovy","halo","handy",
        "harmony","heaven","honor","hope","humble","ideal","ignite","inspire","jewel","jingle",
        "jovial","keen","kind","kisses","lacy","lunar","lush","magic","marry","merry",
        "mesmer","minty","modest","motive","neatly","nifty","opal","orchid","paradise","passion",
        "pebble","pepper","petal","playful","plush","poetic","posh","praise","pride","promise",
        "proud","pure","quaint","quick","quiver","rare","ribbon","rising","romantic","roses",
        "royal","sassy","savor","serene","shiny","silky","simple","sincere","snuggle","softly",
        "sparkle","spirit","stable","starlit","stellar","strong","sugar","sunrise","sunset","sweetly",
        "talent","teacup","thanks","thrill","timeless","trophy","trust","truth","tulips","unique",
        "uplift","value","vivid","warm","witty","wondery","yearn","yummy","zest","zeal",
        "zenith","adorable","affable","amusing","amity","ardency","behold","bestie","blazing",
        "blessed","braver","breezy","buddy","calming","charming","cheerful","cherish","comely",
        "cosmic","daydream","dearest","dreamer","favored","feather","flawless","fondness",
        "freshen","gallant","genteel","giddy","gladly","gracious","heavenly","honesty","hopeful",
        "illume","inlove","jasmine","jollyjoy","jubilant","kindest","kindness","kismet","laugher",
        "lighten","likable","lollipop","lovable","loyally","lucky","lullaby","luminous","magical",
        "mellowy","mermaid","mirth","moonlit","peachy","petally","pleasing","plucky","prettyx",
        "prosper","quieter","radiancy","rainbow","rarejoy","rhapsody","romancy","roseate","royalty",
        "safely","serenity","shimmer","silvery","skyline","smiling","softie","soothing","sparkly",
        "spunky","stunner","sunlove","sweeten","sweetpea","tenderly","thankful","thriving","tickled",
        "together","truelove","trustee","twinkly","unison","uplifty","valiant","velvety","vibrant",
        "victory","warmest","welcome","whisper","wholesome","wishing","wonderly","yaylove","youthful",
        "zappy","zestful","zingy","zippy",
    ]

# ================================================================
# IMAGE GENERATOR  (runs in thread — never blocks event loop)
# ================================================================
def generate_image(word: str) -> str:
    template         = "SHASHA_DRUGZ/assets/shasha/fastlywrite.png"
    font_path        = "SHASHA_DRUGZ/assets/Sprintura Demo.otf"
    img           = Image.open(template).convert("RGBA")
    width, height = img.size
    draw          = ImageDraw.Draw(img)
    text_area_start = int(width * 0.55)
    text_area_width = width - text_area_start - 50
    font      = None
    font_size = 550
    while font_size > 80:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = ImageFont.load_default()
            break
        bbox = draw.textbbox((0, 0), word.upper(), font=font)
        if (bbox[2] - bbox[0]) < text_area_width:
            break
        font_size -= 30
    if font is None:
        font = ImageFont.load_default()
    display_word = word.upper()
    bbox         = draw.textbbox((0, 0), display_word, font=font)
    text_width   = bbox[2] - bbox[0]
    text_height  = bbox[3] - bbox[1]
    x = text_area_start + (text_area_width - text_width) // 2
    y = (height - text_height) // 2
    first_letter = display_word[0]
    rest_letters = display_word[1:]
    bbox_first   = draw.textbbox((0, 0), first_letter, font=font)
    first_width  = bbox_first[2] - bbox_first[0]
    draw.text((x, y), first_letter, font=font,
              fill=(255, 0, 0), stroke_width=8, stroke_fill=(0, 0, 0))
    draw.text((x + first_width, y), rest_letters, font=font,
              fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))
    footer_text = "PoweredBy. @HeartBeat_Offi"
    try:
        footer_font = ImageFont.truetype(font_path, 20)
    except Exception:
        footer_font = ImageFont.load_default()
    bbox_footer  = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_width = bbox_footer[2] - bbox_footer[0]
    footer_x     = text_area_start + (text_area_width - footer_width) // 2
    footer_y     = y + text_height + 50
    draw.text((footer_x, footer_y), footer_text, font=footer_font, fill=(220, 220, 220))
    path = f"fastly_{random.randint(10000, 99999)}.png"
    img.save(path)
    return path

# ================================================================
# INLINE KEYBOARDS
# ================================================================
def result_buttons(chat_id: int) -> InlineKeyboardMarkup:
    """Row 1: New Word   Row 2: Leaderboard | My Rank"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 ɴᴇᴡ ᴡᴏʀᴅ", callback_data=f"fastly_new_{chat_id}")],
        [
            InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data=f"fastly_lb_{chat_id}"),
            InlineKeyboardButton("📊 ᴍʏ ʀᴀɴᴋ",     callback_data=f"fastly_myrank_{chat_id}"),
        ],
    ])

def lb_menu(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 ᴏᴠᴇʀᴀʟʟ",   callback_data=f"fastlylb_all_{chat_id}"),
            InlineKeyboardButton("📅 ᴛᴏᴅᴀʏ",     callback_data=f"fastlylb_today_{chat_id}"),
        ],
        [
            InlineKeyboardButton("📆 ᴡᴇᴇᴋʟʏ",    callback_data=f"fastlylb_week_{chat_id}"),
            InlineKeyboardButton("🗓 ᴍᴏɴᴛʜʟʏ",   callback_data=f"fastlylb_month_{chat_id}"),
        ],
        [
            InlineKeyboardButton("⚡ sᴘᴇᴇᴅ ᴛᴏᴘ", callback_data=f"fastlylb_speed_{chat_id}"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="fastly_back")],
    ])

# ================================================================
# DATABASE HELPERS
# ================================================================
async def add_score(chat_id: int, user, speed: float, reply_to_name: str = None):
    data = await score_col.find_one({"chat_id": chat_id, "user_id": user.id})
    now  = datetime.utcnow()
    if not data:
        doc = {
            "chat_id":    chat_id,
            "user_id":    user.id,
            "name":       user.first_name,
            "coins":      3,
            "today":      3,
            "weekly":     3,
            "monthly":    3,
            "words_won":  1,
            "best_speed": speed,
            "updated":    now,
        }
        if reply_to_name:
            doc["last_reply_to"] = reply_to_name
        await score_col.insert_one(doc)
    else:
        update = {
            "$inc": {"coins": 3, "today": 3, "weekly": 3, "monthly": 3, "words_won": 1},
            "$set": {"name": user.first_name, "updated": now},
        }
        if speed > data.get("best_speed", 0):
            update["$set"]["best_speed"] = speed
        if reply_to_name:
            update["$set"]["last_reply_to"] = reply_to_name
        await score_col.update_one({"_id": data["_id"]}, update)

async def get_top(chat_id: int, field: str) -> str:
    cursor = score_col.find({"chat_id": chat_id}).sort(field, -1).limit(10)
    medals = ["🥇", "🥈", "🥉"]
    lines  = []
    i      = 0
    async for u in cursor:
        rank  = medals[i] if i < 3 else f"{i + 1}."
        speed = u.get("best_speed", 0)
        if field == "best_speed":
            lines.append(f"{rank} {u['name']} — ⚡ {speed:.2f} ᴡᴘᴍ")
        else:
            lines.append(f"{rank} {u['name']} — {u.get(field, 0)} ᴄᴏɪɴs  ⚡{speed:.1f} ᴡᴘᴍ")
        i += 1
    return "\n".join(lines) if lines else "ɴᴏ ᴘʟᴀʏᴇʀs ʏᴇᴛ."

# ================================================================
# WIN PROCESSOR  (shared by active-round and late-answer paths)
# ================================================================
async def _process_win(message, game_data: dict, elapsed: float, is_late: bool = False):
    user             = message.from_user
    minutes, seconds = divmod(int(elapsed), 60)
    word_len         = len(game_data["word"])
    wpm = round((word_len / 5) / (elapsed / 60), 2) if elapsed > 0 else 0.0

    # Detect if user replied to a human (not the bot)
    reply_to_name = None
    if message.reply_to_message:
        rtu = message.reply_to_message.from_user
        if rtu and not rtu.is_bot:
            reply_to_name = rtu.first_name

    await add_score(message.chat.id, user, wpm, reply_to_name)
    await meta_col.update_one(
        {"_id": "chats"}, {"$addToSet": {"ids": message.chat.id}}, upsert=True
    )

    late_tag   = "  _(late answer)_" if is_late else ""
    reply_line = f"<blockquote>\n💬 **ʀᴇᴘʟɪᴇᴅ ᴛᴏ:** {reply_to_name}</blockquote>" if reply_to_name else ""
    result_text = (
        f"<blockquote>✅ {user.mention} ɢᴜᴇssᴇᴅ ᴛʜᴇ ᴡᴏʀᴅ ᴄᴏʀʀᴇᴄᴛʟʏ!{late_tag}\n"
        f"💰 **+3 ᴄᴏɪɴs**\n"
        f"⏱ **ᴛɪᴍᴇ:** {minutes}ᴍ {seconds}s  ({elapsed:.2f}s)\n"
        f"⚡ **sᴘᴇᴇᴅ:** {wpm:.2f} ᴡᴘᴍ"
        f"{reply_line}</blockquote>"
    )
    await redis_client.set(f"fastly_result:{message.chat.id}", result_text, ex=14400)
    await message.reply_text(result_text, reply_markup=result_buttons(message.chat.id))

# ================================================================
# SEND GAME
#   • Redis key set BEFORE photo send → no missed fast-typer window
#   • No repeated words per group (tracks last 30)
# ================================================================
async def send_game(chat_id: int, force: bool = False):
    if not force:
        if await redis_client.exists(f"fastly:{chat_id}"):
            return

    # Pick a word not recently used in this group
    try:
        used_raw  = await redis_client.lrange(f"fastly_used:{chat_id}", 0, -1)
        available = [w for w in WORDS if w not in set(used_raw)]
        if not available:
            available = WORDS
            await redis_client.delete(f"fastly_used:{chat_id}")
    except Exception:
        available = WORDS

    word = random.choice(available)

    # Generate image off the event loop
    loop = asyncio.get_event_loop()
    img  = await loop.run_in_executor(_executor, generate_image, word)

    # ── SET REDIS KEY *BEFORE* SENDING PHOTO ─────────────────
    # Fast typers can answer in < 1 s after the photo appears.
    # If we set the key after send_photo, they get no response.
    now      = time.time()
    game_key = f"fastly:{chat_id}"
    await redis_client.hset(game_key, mapping={"word": word, "time": str(now), "msg_id": "0"})
    await redis_client.expire(game_key, 14399)
    # ─────────────────────────────────────────────────────────

    sent_msg = None
    try:
        sent_msg = await app.send_photo(
            chat_id,
            img,
            caption=(
                "<blockquote>⚡ **ғᴀsᴛʟʏ ᴡʀɪᴛᴇ ɢᴀᴍᴇ**</blockquote>\n"
                "<blockquote>ᴛʏᴘᴇ ᴛʜᴇ ᴡᴏʀᴅ sʜᴏᴡɴ ɪɴ ᴛʜᴇ ɪᴍᴀɢᴇ!\n"
                "🏆 ғɪʀsᴛ ᴄᴏʀʀᴇᴄᴛ ᴀɴsᴡᴇʀ ᴡɪɴs **3 ᴄᴏɪɴs**</blockquote>"
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ", callback_data=f"fastly_lb_{chat_id}")]]
            ),
        )
        # Patch the real message-id in (used by late-answer claim check)
        await redis_client.hset(game_key, "msg_id", str(sent_msg.id))
    except Exception as e:
        print(f"[fastlywrite] send_game photo error: {e}")
        await redis_client.delete(game_key)
    finally:
        try:
            os.remove(img)
        except Exception:
            pass

    # Keep last game for 1 h (late-answer path)
    if sent_msg:
        try:
            await redis_client.hset(
                f"fastly_last:{chat_id}",
                mapping={"word": word, "time": str(now), "msg_id": str(sent_msg.id)},
            )
            await redis_client.expire(f"fastly_last:{chat_id}", 3600)
        except Exception:
            pass

    # Track used words — keep last 30
    try:
        await redis_client.lpush(f"fastly_used:{chat_id}", word)
        await redis_client.ltrim(f"fastly_used:{chat_id}", 0, 29)
        await redis_client.expire(f"fastly_used:{chat_id}", 86400)
    except Exception:
        pass

# ================================================================
# COMMANDS
# ================================================================
@app.on_message(filters.command("fastlywrite") & filters.group)
async def manual_fastly(_, message):
    await meta_col.update_one(
        {"_id": "chats"}, {"$addToSet": {"ids": message.chat.id}}, upsert=True
    )
    await send_game(message.chat.id, force=True)

@app.on_message(filters.command("fastlytop") & filters.group)
async def cmd_fastlytop(_, message):
    top = await get_top(message.chat.id, "coins")
    await message.reply_text(f"🌍 **ᴏᴠᴇʀᴀʟʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**\n\n{top}")

@app.on_message(filters.command("fastlytoday") & filters.group)
async def cmd_fastlytoday(_, message):
    top = await get_top(message.chat.id, "today")
    await message.reply_text(f"📅 **ᴛᴏᴅᴀʏ's ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**\n\n{top}")

@app.on_message(filters.command("fastlyweek") & filters.group)
async def cmd_fastlyweek(_, message):
    top = await get_top(message.chat.id, "weekly")
    await message.reply_text(f"📆 **ᴡᴇᴇᴋʟʏ Leaderboard**\n\n{top}")

@app.on_message(filters.command("fastlymonth") & filters.group)
async def cmd_fastlymonth(_, message):
    top = await get_top(message.chat.id, "monthly")
    await message.reply_text(f"🗓 **ᴍᴏɴᴛʜʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**\n\n{top}")

@app.on_message(filters.command("myfastlyrank") & filters.group)
async def cmd_my_rank(_, message):
    user    = message.from_user
    chat_id = message.chat.id
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": user.id})
    if not data:
        await message.reply_text("📊 ʏᴏᴜ haven't ᴘʟᴀʏᴇᴅ yet!\ᴜse /fastlywrite ᴛᴏ sᴛᴀʀᴛ.")
        return
    rank = (
        await score_col.count_documents(
            {"chat_id": chat_id, "coins": {"$gt": data.get("coins", 0)}}
        ) + 1
    )
    speed      = data.get("best_speed", 0)
    reply_to   = data.get("last_reply_to")
    reply_line = f"\n💬 **ʟᴀsᴛ ʀᴇᴘʟɪᴇᴅ ᴛᴏ:** {reply_to}" if reply_to else ""
    await message.reply_text(
        f"<blockquote>📊**ʏᴏᴜʀ ғᴀsᴛʟʏ sᴛᴀᴛs** — {user.mention}</blockquote>\n"
        f"<blockquote>🏅 **ʀᴀɴᴋ:** #{rank}\n"
        f"💰 **ᴛᴏᴛᴀʟ ᴄᴏɪɴs:** {data.get('coins', 0)}\n"
        f"📅 **ᴛᴏᴅᴀʏ:** {data.get('today', 0)}\n"
        f"📆 **ᴡᴇᴇᴋʟʏ:** {data.get('weekly', 0)}\n"
        f"🗓 **ᴍᴏɴᴛʜʟʏ:** {data.get('monthly', 0)}\n"
        f"🔤 **ᴡᴏʀᴅs Won:** {data.get('words_won', 0)}\n"
        f"⚡ **ʙᴇsᴛ sᴘᴇᴇᴅ:** {speed:.2f} ᴡᴘᴍ</blockquote>"
        f"{reply_line}"
    )

@app.on_message(filters.command("fastlyrules") & filters.group)
async def cmd_fastlyrules(_, message):
    await message.reply_text(
        "<blockquote>📜 **ғᴀsᴛʟʏ ᴡʀɪᴛᴇ ʀᴜʟᴇs**</blockquote>\n"
        "<blockquote>1️⃣ ᴀ ᴡᴏʀᴅ ɪᴍᴀɢᴇ ɪs sᴇɴᴛ ᴛᴏ ᴛʜᴇ ɢʀᴏᴜᴘ.\n"
        "2️⃣ ᴛʏᴘᴇ ᴛʜᴇ ᴇxᴀᴄᴛ word sʜᴏᴡɴ — ᴀɴʏ ᴄᴀsᴇ (CAPS / small / mixed) ᴀʟʟ ᴀᴄᴄᴇᴘᴛᴇᴅ.\n"
        "3️⃣ ғɪʀsᴛ ᴄᴏʀʀᴇᴄᴛ ᴀɴsᴡᴇʀ ᴡɪɴs **3 ᴄᴏɪɴs**.\n"
        "4️⃣ ᴛʏᴘᴇ ᴅɪʀᴇᴄᴛʟʏ ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇssᴀɢᴇ — ʙᴏᴛʜ ᴡᴏʀᴋ.\n"
        "5️⃣ ɢᴀᴍᴇ ᴇxᴘɪʀᴇs ᴀғᴛᴇʀ 10 ᴍɪɴᴜᴛᴇs. ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ʙᴏᴛ's ᴡᴏʀᴅ ɪᴍᴀɢᴇ ᴛᴏ ᴄʟᴀɪᴍ ᴀ ʟᴀᴛᴇ ᴡɪɴ.\n"
        "6️⃣ ᴜsᴇ /myfastlyrank ᴛᴏ sᴇᴇ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ sᴛᴀᴛs.\n\n"
        "⚡ sᴘᴇᴇᴅ + ᴀᴄᴄᴜʀᴀᴄʏ = ᴠɪᴄᴛᴏʀʏ!</blockquote>"
    )

# ================================================================
# CHECK WORD  —  group=-1  (THE FIX THAT MAKES EVERYTHING WORK)
#
# WHY group=-1 ?
#   Pyrogram dispatches in ascending group order.
#   chatbot / reactionbot register at group=0 (default).
#   If they consume the message without calling
#   continue_propagation(), group=100 NEVER RUNS.
#   group=-1 runs BEFORE group=0 — fastlywrite always gets first
#   look.  Non-game text passes through via continue_propagation()
#   so chatbot / reactionbot still receive it normally.
#
# WHY no `await` on continue_propagation() ?
#   It is synchronous — raises ContinuePropagation immediately.
#   `await`-ing it is undefined behaviour in some Pyrogram builds.
#
# CASE INSENSITIVITY:  both sides .lower() — ANGEL/Angel/angel OK.
# CHEAT DETECTION:     removed (MIN_TIME gone).
# ================================================================
@app.on_message(
    filters.incoming
    & filters.text
    & filters.group
    & ~filters.command(
        ["fastlywrite", "fastlytop", "fastlytoday", "fastlyweek",
         "fastlymonth", "fastlyrules", "myfastlyrank"]
    )
    & ~filters.via_bot,
    group=-1,   # ← THE ONLY CHANGE THAT FIXES "NO RESPONSE" BUG
)
async def check_word(_, message):
    typed   = (message.text or "").strip().lower()
    chat_id = message.chat.id

    if not typed:
        message.continue_propagation()
        return

    # ── PATH A: Active round ────────────────────────────────
    game = None
    try:
        key = f"fastly:{chat_id}"
        if await redis_client.exists(key):
            game = await redis_client.hgetall(key)
    except Exception as e:
        print(f"[fastlywrite] Redis read error: {e}")
        message.continue_propagation()
        return

    if game and "word" in game and "time" in game:
        if typed != game["word"].lower():
            # Wrong word — let chatbot / reactionbot have it
            message.continue_propagation()
            return

        # Correct word — atomic delete so only one winner per round
        try:
            deleted = await redis_client.delete(key)
        except Exception as e:
            print(f"[fastlywrite] Redis delete error: {e}")
            return

        if not deleted:
            # Another coroutine already claimed this round
            return

        elapsed = time.time() - float(game["time"])
        try:
            await _process_win(message, game, elapsed, is_late=False)
        except Exception as e:
            print(f"[fastlywrite] _process_win error (active): {e}")
        return  # Message consumed — do NOT propagate

    # ── PATH B: No active round → late-answer via bot reply ─
    reply = message.reply_to_message
    if not reply:
        message.continue_propagation()
        return

    if not (reply.from_user and reply.from_user.is_bot):
        message.continue_propagation()
        return

    last = None
    try:
        last = await redis_client.hgetall(f"fastly_last:{chat_id}")
    except Exception as e:
        print(f"[fastlywrite] Redis last-game error: {e}")
        message.continue_propagation()
        return

    if not last or "word" not in last or "msg_id" not in last:
        message.continue_propagation()
        return

    # Must reply to the exact game message
    if str(reply.id) != last.get("msg_id", ""):
        message.continue_propagation()
        return

    if typed != last["word"].lower():
        message.continue_propagation()
        return

    # Atomic claim — only one winner per expired round
    claimed_key = f"fastly_claimed:{chat_id}:{last['msg_id']}"
    try:
        ok = await redis_client.set(claimed_key, "1", ex=3600, nx=True)
    except Exception as e:
        print(f"[fastlywrite] Redis claim error: {e}")
        message.continue_propagation()
        return

    if not ok:
        message.continue_propagation()
        return

    elapsed = time.time() - float(last["time"])
    try:
        await _process_win(message, last, elapsed, is_late=True)
    except Exception as e:
        print(f"[fastlywrite] _process_win error (late): {e}")

# ================================================================
# CALLBACKS
# ================================================================
@app.on_callback_query(filters.regex(r"^fastly_lb_(-?\d+)$"))
async def open_lb(_, query):
    chat_id = int(query.data.split("_")[2])
    top     = await get_top(chat_id, "coins")
    await query.message.edit_text(
        f"<blockquote>🌍 **ᴏᴠᴇʀᴀʟʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**</blockquote>\n<blockquote>{top}</blockquote>",
        reply_markup=lb_menu(chat_id),
    )

@app.on_callback_query(filters.regex(r"^fastlylb_"))
async def show_lb(_, query):
    parts   = query.data.split("_")   # fastlylb_<mode>_<chat_id>
    mode    = parts[1]
    chat_id = int(parts[2])
    MODES   = {
        "all":   ("coins",      "🌍 ᴏᴠᴇʀᴀʟʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"),
        "today": ("today",      "📅 ᴛᴏᴅᴀʏ's ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"),
        "week":  ("weekly",     "📆 ᴡᴇᴇᴋʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"),
        "month": ("monthly",    "🗓 ᴍᴏɴᴛʜʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"),
        "speed": ("best_speed", "⚡ sᴘᴇᴇᴅ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ᴡᴘᴍ)"),
    }
    field, title = MODES.get(mode, ("monthly", "🗓 ᴍᴏɴᴛʜʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ"))
    top = await get_top(chat_id, field)
    await query.message.edit_text(f"{title}\n\n{top}", reply_markup=lb_menu(chat_id))

@app.on_callback_query(filters.regex(r"^fastly_myrank_(-?\d+)$"))
async def cb_my_rank(_, query):
    chat_id = int(query.data.split("_")[2])
    user    = query.from_user
    data    = await score_col.find_one({"chat_id": chat_id, "user_id": user.id})
    if not data:
        await query.answer("ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴘʟᴀʏᴇᴅ ʏᴇᴛ!", show_alert=True)
        return
    rank = (
        await score_col.count_documents(
            {"chat_id": chat_id, "coins": {"$gt": data.get("coins", 0)}}
        ) + 1
    )
    speed      = data.get("best_speed", 0)
    reply_to   = data.get("last_reply_to")
    reply_line = f"\n💬 **ʟᴀsᴛ ʀᴇᴘʟɪᴇᴅ ᴛᴏ:** {reply_to}" if reply_to else ""
    text = (
        f"<blockquote>📊 **ʏᴏᴜʀ ғᴀsᴛʟʏ sᴛᴀᴛs** — {user.mention}</blockquote>\n"
        f"<blockquote>🏅 **ʀᴀɴᴋ:** #{rank}\n"
        f"💰 **ᴛᴏᴛᴀʟ ᴄᴏɪɴs:** {data.get('coins', 0)}\n"
        f"📅 **ᴛᴏᴅᴀʏ:** {data.get('today', 0)}\n"
        f"📆 **ᴡᴇᴇᴋʟʏ:** {data.get('weekly', 0)}\n"
        f"🗓 **ᴍᴏɴᴛʜʟʏ:** {data.get('monthly', 0)}\n"
        f"🔤 **ᴡᴏʀᴅs ᴡᴏɴ:** {data.get('words_won', 0)}\n"
        f"⚡ **ʙᴇsᴛ sᴘᴇᴇᴅ:** {speed:.2f} ᴡᴘᴍ"
        f"{reply_line}</blockquote>"
    )
    await query.answer()
    await query.message.edit_text(text, reply_markup=result_buttons(chat_id))

@app.on_callback_query(filters.regex(r"^fastly_back$"))
async def back_to_result(_, query):
    chat_id = query.message.chat.id
    text    = await redis_client.get(f"fastly_result:{chat_id}")
    if not text:
        text = "<blockquote>⚠️ ʀᴇsᴜʟᴛ ᴇxᴘɪʀᴇᴅ. ᴜsᴇ /fastlywrite ᴛᴏ sᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ.</blockquote>"
    await query.message.edit_text(text, reply_markup=result_buttons(chat_id))

@app.on_callback_query(filters.regex(r"^fastly_new_(-?\d+)$"))
async def new_word(_, query):
    chat_id = int(query.data.split("_")[2])
    await query.answer("Starting new word...")
    await send_game(chat_id, force=True)

# ================================================================
# BACKGROUND TASKS
# ================================================================
async def auto_fastly():
    """Send a word to all registered groups every 4 hours."""
    while True:
        await asyncio.sleep(14400)
        try:
            meta = await meta_col.find_one({"_id": "chats"})
            if meta and "ids" in meta:
                for chat in list(meta["ids"]):
                    try:
                        await send_game(chat, force=False)
                    except Exception:
                        await meta_col.update_one(
                            {"_id": "chats"}, {"$pull": {"ids": chat}}
                        )
        except Exception as e:
            print(f"[fastlywrite] auto_fastly error: {e}")

async def reset_scores():
    """Reset daily / weekly / monthly scores on schedule."""
    while True:
        try:
            now  = datetime.utcnow()
            meta = await meta_col.find_one({"_id": "reset_meta"})
            if not meta:
                meta = {"_id": "reset_meta", "day": None, "week": None, "month": None}
                await meta_col.insert_one(meta)
            if meta.get("day") != now.date().isoformat():
                await score_col.update_many({}, {"$set": {"today": 0}})
                await meta_col.update_one(
                    {"_id": "reset_meta"}, {"$set": {"day": now.date().isoformat()}}
                )
            week = f"{now.year}-{now.isocalendar()[1]}"
            if meta.get("week") != week:
                await score_col.update_many({}, {"$set": {"weekly": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"week": week}})
            month = f"{now.year}-{now.month}"
            if meta.get("month") != month:
                await score_col.update_many({}, {"$set": {"monthly": 0}})
                await meta_col.update_one({"_id": "reset_meta"}, {"$set": {"month": month}})
        except Exception as e:
            print(f"[fastlywrite] reset_scores error: {e}")
        await asyncio.sleep(3600)

try:
    asyncio.create_task(auto_fastly())
    asyncio.create_task(reset_scores())
    print("[fastlywrite] Background tasks started.")
except Exception as _e:
    print(f"[fastlywrite] Task start error: {_e}")

# ================================================================
# MODULE META
# ================================================================
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_77"
__help__     = """
🔻 /fastlywrite ➠ ɴᴇᴡ ғᴀsᴛʟʏ ᴡᴏʀᴅ ɢᴀᴍᴇ
🔻 /fastlytop ➠ ᴏᴠᴇʀᴀʟʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /fastlytoday ➠ ᴛᴏᴅᴀʏ's ᴛᴏᴘ ᴘʟᴀʏᴇʀs
🔻 /fastlyweek ➠ ᴡᴇᴇᴋʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /fastlymonth ➠ ᴍᴏɴᴛʜʟʏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /fastlyrules ➠ ɢᴀᴍᴇ ʀᴜʟᴇs
🔻 /myfastlyrank ➠ ʏᴏᴜʀ ᴘᴇʀsᴏɴᴀʟ sᴛᴀᴛs & ʀᴀɴᴋ
"""
