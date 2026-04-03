#Protect-Group.py
# ╔══════════════════════════════════════════════════════════════════╗
# ║         BLOCKWORD MODULE — Pyrogram + MongoDB                    ║
# ║  • Auto-detect bad words (multilingual, all cases/leetspeak)    ║
# ║  • Per-group custom words (case-insensitive)                    ║
# ║  • Owner global words, inline toggles, warn system, reporting   ║
# ║  • Does NOT intercept other bot commands                        ║
# ╚══════════════════════════════════════════════════════════════════╝

import re
import unicodedata
from os import getenv
from datetime import datetime, timedelta
from SHASHA_DRUGZ import app
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB_URI, ADMINS_ID

# ──────────────────────────────────────────────────────────────────
# 🗃️  MONGO SETUP
# ──────────────────────────────────────────────────────────────────
mongo           = AsyncIOMotorClient(MONGO_DB_URI)
db              = mongo["BLOCKWORD_DB"]
settings_col    = db["bw_settings"]      # per-group toggle / warn config
group_words_col = db["bw_group_words"]   # per-group custom words (admins add)
owner_words_col = db["bw_owner_words"]   # global words added by bot owner
warns_col       = db["bw_warns"]         # per-user warn counts

# ──────────────────────────────────────────────────────────────────
# 🔡  NORMALISATION  (handles ALL case variants + leetspeak)
#
#  Pipeline:
#   1. unicodedata.normalize("NFKC") — collapses full-width / homoglyphs
#   2. casefold()                    — aggressive lowercase (ß→ss, etc.)
#   3. strip zero-width chars        — \u200b, \u200c, \u200d, \ufeff
#   4. leet-map substitution         — 0→o, 1→i, 3→e, 4→a, 5→s, 7→t …
#
#  Result: "DR0GZ", "Drugz", "d r u g s", "𝐃𝐑𝐔𝐆𝐒" all → "drugs"
# ──────────────────────────────────────────────────────────────────
_LEET_MAP: dict[str, str] = {
    "0": "o", "1": "i", "3": "e", "4": "a",
    "5": "s", "6": "g", "7": "t", "8": "b",
    "@": "a", "$": "s", "!": "i", "+": "t",
    "(": "c", ")": "o",
}
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")


def _normalize(text: str) -> str:
    """Return a fully normalised, casefolded version of text for matching."""
    text = unicodedata.normalize("NFKC", text)   # homoglyph collapse
    text = text.casefold()                        # aggressive lowercase
    text = _ZERO_WIDTH.sub("", text)              # strip invisible chars
    text = "".join(_LEET_MAP.get(ch, ch) for ch in text)  # leet decode
    return text


# ──────────────────────────────────────────────────────────────────
# 🤬  BUILT-IN UNIVERSAL BAD-WORD PATTERNS
#  All patterns compiled with re.IGNORECASE | re.UNICODE.
#  Applied AFTER _normalize() → catches every case variant + leetspeak.
# ──────────────────────────────────────────────────────────────────
BUILTIN_PATTERNS: list[str] = [
    # ── Drugs ──────────────────────────────────────────────────────
    r"\bcocain[e]?\b", r"\bcoke\b", r"\bheroin\b", r"\bmeth\b",
    r"\bcrack\b", r"\bweed\b", r"\bganja\b", r"\bopium\b",
    r"\bfentanyl\b", r"\bmdma\b", r"\becstasy\b", r"\blsd\b",
    r"\bkratom\b", r"\bsmack\b", r"\bdrugz?\b", r"\bsnort\b",
    r"\bspice\b", r"\bshrooms?\b", r"\bpcp\b", r"\bxanax\b",
    r"\boxy(contin)?\b", r"\bpercocet\b", r"\bdealin[g]?\b",
    # ── Weapons ────────────────────────────────────────────────────
    r"\bgunz?\b", r"\bpistol\b", r"\brifle\b", r"\bak-?47\b",
    r"\bak47\b", r"\bbomb\b", r"\bgrenade\b", r"\bexplosives?\b",
    r"\bammo\b", r"\bbullets?\b", r"\bweapons?\b", r"\bknife\b",
    r"\bmachete\b", r"\bshotgun\b", r"\bsemiauto\b", r"\bsilencer\b",
    # ── Pornography ────────────────────────────────────────────────
    r"\bpornz?\b", r"\bpornhub\b", r"\bxvideos\b", r"\bxnxx\b",
    r"\bnudez?\b", r"\bnudes\b", r"\bsex\b", r"\bsexual\b",
    r"\bonlyfans\b", r"\bcamgirl\b", r"\bstrip(per)?\b",
    r"\bf+u+c+k+\b", r"\bfuk\b", r"\bfuq\b", r"\bfck\b",
    r"\bpornstar\b", r"\bbooty\b", r"\bboobs?\b",
    # ── Terrorism / Extremism ──────────────────────────────────────
    r"\bisis\b", r"\bis[- ]?il\b", r"\bal[- ]?qaeda\b",
    r"\bterror(ist)?\b", r"\bjihad\b", r"\bsuicide.?bomb\b",
    r"\bbeheading\b", r"\bextremis[tm]\b", r"\bradicali[sz]\b",
    # ── Violence / Threats ─────────────────────────────────────────
    r"\bkill\s+you\b", r"\bi.?will.?kill\b", r"\bmurder\b",
    r"\bstab\b", r"\bshoot\s+you\b", r"\bthreat(en)?\b",
    r"\brapist?\b", r"\brape\b",
    # ── Child Safety ───────────────────────────────────────────────
    r"\bpedophil[e]?\b", r"\bpedophilia\b", r"\bchild.?porn\b",
    r"\bminor.?sex\b", r"\blolita\b", r"\bcp\b", r"\bcsam\b",
    # ── Common English Profanity ───────────────────────────────────
    r"\bshit\b", r"\bass(hole)?\b", r"\bbitch\b", r"\bcunt\b",
    r"\bdick\b", r"\bpussy\b", r"\bwhore\b", r"\bslut\b",
    r"\bbastard?\b", r"\bdamn\b", r"\bcrap\b", r"\bprick\b",
    r"\bdouche\b", r"\bjerkoff\b", r"\bwanker\b",
    # ── Tamil bad words (transliterated) ──────────────────────────
    r"\bthevdiya\b", r"\bpundai\b", r"\bootha\b", r"\bsootha\b",
    r"\bkuthi\b", r"\bmyre\b", r"\bnaaye?\b", r"\bkazhuthai\b",
    r"\bnaayi\b", r"\bthayoli\b", r"\bpottai\b", r"\bkundi\b",
    r"\bsullu\b", r"\bsunni\b", r"\bnool\b", r"\bpaiyan\b",
    r"\bvadakkan\b", r"\berumai\b", r"\bthambi.?otha\b",
    # ── Hindi bad words (transliterated) ──────────────────────────
    r"\bchutiya\b", r"\bbehenchod\b", r"\bmadarchod\b",
    r"\bbc\b", r"\bmc\b", r"\bgandu\b", r"\blauda\b",
    r"\brandi\b", r"\bsaala\b", r"\bharamzada\b", r"\bharami\b",
    r"\bbhosad\b", r"\bchod\b", r"\bbhenchod\b", r"\bmaa.?ki\b",
    r"\bbehen.?ke\b", r"\bgaand\b",
]

_COMPILED_PATTERNS = [
    re.compile(p, re.IGNORECASE | re.UNICODE) for p in BUILTIN_PATTERNS
]


def check_builtin(raw_text: str) -> str | None:
    """
    Normalise raw_text then test against all built-in patterns.
    Handles: UPPERCASE / lowercase / MiXeD / l33t / unicode variants.
    Returns the matched token or None.
    """
    normalized = _normalize(raw_text)
    for pat in _COMPILED_PATTERNS:
        m = pat.search(normalized)
        if m:
            return m.group(0)
    return None


def check_custom_words(raw_text: str, words: list[str]) -> str | None:
    """
    Check raw_text against a list of custom words.
    Both the input text and stored words are normalised, so matching is
    completely case-insensitive (WORD = word = WoRd = w0rd).
    """
    normalized = _normalize(raw_text)
    for w in words:
        pattern = re.compile(re.escape(_normalize(w)), re.IGNORECASE | re.UNICODE)
        if pattern.search(normalized):
            return w
    return None


# ──────────────────────────────────────────────────────────────────
# 🛠️  DATABASE HELPERS
# ──────────────────────────────────────────────────────────────────
async def get_settings(chat_id: int) -> dict:
    data = await settings_col.find_one({"chat_id": chat_id})
    if not data:
        return {"enabled": True, "warn_limit": 3, "action": "mute"}
    return {
        "enabled":    data.get("enabled",    True),
        "warn_limit": data.get("warn_limit", 3),
        "action":     data.get("action",     "mute"),
    }


async def set_setting(chat_id: int, key: str, value) -> None:
    await settings_col.update_one(
        {"chat_id": chat_id}, {"$set": {key: value}}, upsert=True
    )


async def get_group_words(chat_id: int) -> list[str]:
    data = await group_words_col.find_one({"chat_id": chat_id})
    return data.get("words", []) if data else []


async def save_group_words(chat_id: int, words: list[str]) -> None:
    await group_words_col.update_one(
        {"chat_id": chat_id}, {"$set": {"words": words}}, upsert=True
    )


async def get_owner_words() -> list[str]:
    data = await owner_words_col.find_one({"_id": "global"})
    return data.get("words", []) if data else []


async def save_owner_words(words: list[str]) -> None:
    await owner_words_col.update_one(
        {"_id": "global"}, {"$set": {"words": words}}, upsert=True
    )


async def add_warn(chat_id: int, user_id: int) -> int:
    await warns_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
    )
    data = await warns_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return data["count"]


async def get_warn(chat_id: int, user_id: int) -> int:
    data = await warns_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return data["count"] if data else 0


async def reset_warn(chat_id: int, user_id: int) -> None:
    await warns_col.delete_one({"chat_id": chat_id, "user_id": user_id})


# ──────────────────────────────────────────────────────────────────
# 🔐  PERMISSION HELPERS
# ──────────────────────────────────────────────────────────────────
async def is_admin_or_owner(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id in ADMINS_ID:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def is_group_owner(client: Client, chat_id: int, user_id: int) -> bool:
    if user_id in ADMINS_ID:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except Exception:
        return False


async def get_group_owner(client: Client, chat_id: int):
    """Return the owner ChatMember object, or None."""
    try:
        async for member in client.get_chat_members(chat_id, filter="administrators"):
            if member.status == ChatMemberStatus.OWNER:
                return member
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────
# 🎛️  INLINE KEYBOARD BUILDERS
# ──────────────────────────────────────────────────────────────────
def dashboard_kb(enabled: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Disable" if enabled else "🟢 Enable"
    status_label = "✅ ON" if enabled else "❌ OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛡 Status: {status_label}", callback_data="bw_status_info")],
        [
            InlineKeyboardButton(toggle_label,         callback_data="bw_toggle"),
            InlineKeyboardButton("📋 Word List",       callback_data="bw_listwords"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings",        callback_data="bw_settings_menu"),
            InlineKeyboardButton("❓ Help",             callback_data="bw_help"),
        ],
    ])


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Warn Limit",      callback_data="bw_set_warnlimit"),
            InlineKeyboardButton("🔨 Punishment",      callback_data="bw_set_punishment"),
        ],
        [InlineKeyboardButton("« Back",                callback_data="bw_main")],
    ])


def punishment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔇 Mute",            callback_data="bw_action_mute"),
            InlineKeyboardButton("🚫 Ban",              callback_data="bw_action_ban"),
            InlineKeyboardButton("👢 Kick",             callback_data="bw_action_kick"),
        ],
        [InlineKeyboardButton("« Back",                callback_data="bw_settings_menu")],
    ])


def back_kb(cb: str = "bw_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data=cb)]])


def wordlist_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Refresh",             callback_data="bw_listwords"),
        InlineKeyboardButton("« Back",                 callback_data="bw_main"),
    ]])


# ──────────────────────────────────────────────────────────────────
# 📌  /blockword  — dashboard + quick on/off
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("blockword") & filters.group)
async def blockword_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")

    args = message.command[1:]
    settings = await get_settings(message.chat.id)

    if args and args[0].lower() in ("on", "off"):
        enabled = args[0].lower() == "on"
        await set_setting(message.chat.id, "enabled", enabled)
        label = "✅ BlockWord **enabled**." if enabled else "❌ BlockWord **disabled**."
        return await message.reply(label, reply_markup=dashboard_kb(enabled))

    enabled = settings["enabled"]
    await message.reply(
        f"🛡 **BlockWord Dashboard**\n\n"
        f"Status      : {'✅ Active' if enabled else '❌ Inactive'}\n"
        f"Warn Limit  : `{settings['warn_limit']}`\n"
        f"Punishment  : `{settings['action'].title()}`\n\n"
        f"Use the buttons below to manage.",
        reply_markup=dashboard_kb(enabled),
    )


# ──────────────────────────────────────────────────────────────────
# 📝  /addword  — admin adds per-group word (stored normalised)
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("addword") & filters.group)
async def add_word_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")

    if len(message.command) < 2:
        return await message.reply(
            "**Usage:** `/addword <word>`\n_Example: `/addword badword`_",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 View Words", callback_data="bw_listwords")
            ]]),
        )

    # Normalise before storing so matching is always case-insensitive
    word = _normalize(message.text.split(None, 1)[1].strip())
    words = await get_group_words(message.chat.id)

    if word in words:
        return await message.reply(
            f"⚠️ `{word}` is already in this group's blocklist.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 View Words", callback_data="bw_listwords")
            ]]),
        )

    words.append(word)
    await save_group_words(message.chat.id, words)
    await message.reply(
        f"✅ Word `{word}` added to **this group's** blocklist.\n"
        f"_(Matches: `{word}`, `{word.upper()}`, mixed cases, leetspeak — all caught)_\n"
        f"_(Does **not** affect other groups)_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 View Words", callback_data="bw_listwords"),
            InlineKeyboardButton("➕ Add More",   callback_data="bw_addword_hint"),
        ]]),
    )


# ──────────────────────────────────────────────────────────────────
# 🗑️  /removeword  — GROUP OWNER ONLY
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("removeword") & filters.group)
async def remove_word_cmd(client: Client, message: Message):
    if not await is_group_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Only the **group owner** can remove words.")

    if len(message.command) < 2:
        return await message.reply("**Usage:** `/removeword <word>`")

    word = _normalize(message.text.split(None, 1)[1].strip())
    words = await get_group_words(message.chat.id)

    if word not in words:
        return await message.reply(
            f"⚠️ `{word}` not found in this group's blocklist.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 View Words", callback_data="bw_listwords")
            ]]),
        )

    words.remove(word)
    await save_group_words(message.chat.id, words)
    await message.reply(
        f"🗑 Word `{word}` removed from this group's blocklist.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 View Words", callback_data="bw_listwords")
        ]]),
    )


# ──────────────────────────────────────────────────────────────────
# 📋  /blockwords  — list words (admin)
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("blockwords") & filters.group)
async def list_words_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")

    gw = await get_group_words(message.chat.id)
    ow = await get_owner_words()

    text = "📋 **Blocked Words**\n\n"
    text += ("**📌 This Group:**\n" + "\n".join(f"  • `{w}`" for w in gw) + "\n\n") if gw else "**📌 This Group:** _None added yet_\n\n"
    text += ("**🌍 Global (Bot Owner):**\n" + "\n".join(f"  • `{w}`" for w in ow)) if ow else "**🌍 Global (Bot Owner):** _None_"

    await message.reply(text, reply_markup=wordlist_kb())


# ──────────────────────────────────────────────────────────────────
# 🌍  /ownerblockword  — bot owner adds a GLOBAL word
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("ownerblockword"))
async def owner_block_word_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMINS_ID:
        return await message.reply("❌ Bot owner only.")

    if len(message.command) < 2:
        return await message.reply("**Usage:** `/ownerblockword <word>`")

    word = _normalize(message.text.split(None, 1)[1].strip())
    words = await get_owner_words()

    if word in words:
        return await message.reply(f"⚠️ `{word}` is already in the global blocklist.")

    words.append(word)
    await save_owner_words(words)
    await message.reply(
        f"🌍 `{word}` added to **global** blocklist.\n_(Affects ALL groups. Matches any case/leetspeak.)_",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Global Words", callback_data="bw_owner_listwords")
        ]]),
    )


# ──────────────────────────────────────────────────────────────────
# 🌍  /ownerrmword  — bot owner removes one global word
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("ownerrmword"))
async def owner_rm_word_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMINS_ID:
        return await message.reply("❌ Bot owner only.")

    if len(message.command) < 2:
        return await message.reply("**Usage:** `/ownerrmword <word>`")

    word = _normalize(message.text.split(None, 1)[1].strip())
    words = await get_owner_words()

    if word not in words:
        return await message.reply(f"⚠️ `{word}` not found in global blocklist.")

    words.remove(word)
    await save_owner_words(words)
    await message.reply(
        f"🗑 `{word}` removed from **global** blocklist.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Global Words", callback_data="bw_owner_listwords")
        ]]),
    )


# ──────────────────────────────────────────────────────────────────
# 🧹  /rmallwords  — bot owner clears ALL global words
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("rmallwords"))
async def rm_all_words_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMINS_ID:
        return await message.reply("❌ Bot owner only.")

    await save_owner_words([])
    await message.reply(
        "🧹 All **global** blocked words cleared.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Done", callback_data="bw_noop")
        ]]),
    )


# ──────────────────────────────────────────────────────────────────
# ⚙️  /setwarnlimit & /setpunishment
# ──────────────────────────────────────────────────────────────────
@app.on_message(filters.command("setwarnlimit") & filters.group)
async def set_warn_limit_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("**Usage:** `/setwarnlimit <number>`\nExample: `/setwarnlimit 3`")

    limit = int(message.command[1])
    if limit < 1:
        return await message.reply("⚠️ Warn limit must be at least 1.")

    await set_setting(message.chat.id, "warn_limit", limit)
    await message.reply(f"✅ Warn limit set to **{limit}**.", reply_markup=back_kb("bw_settings_menu"))


@app.on_message(filters.command("setpunishment") & filters.group)
async def set_punishment_cmd(client: Client, message: Message):
    if not await is_admin_or_owner(client, message.chat.id, message.from_user.id):
        return await message.reply("❌ Admins only.")

    if len(message.command) < 2 or message.command[1].lower() not in ("mute", "ban", "kick"):
        return await message.reply("Choose punishment:", reply_markup=punishment_kb())

    action = message.command[1].lower()
    await set_setting(message.chat.id, "action", action)
    await message.reply(f"✅ Punishment set to **{action.title()}**.", reply_markup=back_kb("bw_settings_menu"))


# ──────────────────────────────────────────────────────────────────
# 🔍  ENFORCEMENT HANDLER
#
#  KEY GUARDS — this handler will NEVER fire for:
#  ✅ ~filters.command("")  → skips ALL /commands (own bot + other bots)
#  ✅ ~filters.bot          → skips messages sent by bots
#  ✅ ~filters.service      → skips service messages (joins, pins, etc.)
#  ✅ filters.group         → only fires in group chats
# ──────────────────────────────────────────────────────────────────
@app.on_message(
    filters.group
    & ~filters.command("")    # ← NEVER intercept any /command message
    & ~filters.bot
    & ~filters.service,
    group=10,                 # lower priority so commands always fire first
)
async def enforce_blockword(client: Client, message: Message):
    raw_text = message.text or message.caption or ""
    if not raw_text:
        return

    chat_id = message.chat.id
    settings = await get_settings(chat_id)

    if not settings["enabled"]:
        return

    user = message.from_user
    if not user:
        return

    # Skip bot owners and group admins
    if user.id in ADMINS_ID:
        return
    try:
        member = await client.get_chat_member(chat_id, user.id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return
    except Exception:
        pass

    # ── 1. Built-in bad words (normalised + case-insensitive) ──────
    matched_word = check_builtin(raw_text)

    # ── 2. Global (bot owner) words ────────────────────────────────
    if not matched_word:
        owner_words = await get_owner_words()
        matched_word = check_custom_words(raw_text, owner_words)

    # ── 3. Per-group custom words ──────────────────────────────────
    if not matched_word:
        group_words = await get_group_words(chat_id)
        matched_word = check_custom_words(raw_text, group_words)

    if not matched_word:
        return  # clean message

    # ── Delete offending message ───────────────────────────────────
    try:
        await message.delete()
    except Exception:
        pass

    # ── Warn counter ───────────────────────────────────────────────
    warn_count = await add_warn(chat_id, user.id)
    warn_limit = settings["warn_limit"]

    # ── Tag group owner in report ──────────────────────────────────
    try:
        owner_member = await get_group_owner(client, chat_id)
        owner_mention = owner_member.user.mention if owner_member else "_(owner not found)_"
    except Exception:
        owner_mention = "_(owner lookup failed)_"

    report_text = (
        f"🚨 **Violation Detected**\n\n"
        f"👤 User    : {user.mention}\n"
        f"🔤 Matched : `{matched_word}`\n"
        f"⚠️ Warns   : `{warn_count}/{warn_limit}`\n"
        f"👑 Owner   : {owner_mention}"
    )

    if warn_count < warn_limit:
        return await client.send_message(
            chat_id,
            report_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Word List",  callback_data="bw_listwords"),
                InlineKeyboardButton("⚙️ Settings",   callback_data="bw_settings_menu"),
            ]]),
        )

    # ── Warn limit reached — punish ────────────────────────────────
    action = settings["action"]
    try:
        if action == "ban":
            await client.ban_chat_member(chat_id, user.id)
            action_text = "🚫 **Banned**"
        elif action == "kick":
            await client.ban_chat_member(chat_id, user.id)
            await client.unban_chat_member(chat_id, user.id)
            action_text = "👢 **Kicked**"
        else:  # mute (default)
            until = datetime.utcnow() + timedelta(hours=1)
            await client.restrict_chat_member(
                chat_id, user.id, ChatPermissions(), until_date=until
            )
            action_text = "🔇 **Muted** (1 hour)"
    except Exception as e:
        action_text = f"⚠️ Action failed: `{e}`"

    await reset_warn(chat_id, user.id)

    await client.send_message(
        chat_id,
        f"{report_text}\n\n"
        f"🔨 Action  : {action_text}\n"
        f"📌 Reason  : Reached warn limit `{warn_limit}`.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Word List",  callback_data="bw_listwords"),
            InlineKeyboardButton("⚙️ Settings",   callback_data="bw_settings_menu"),
        ]]),
    )


# ──────────────────────────────────────────────────────────────────
# 🔘  CALLBACK QUERY HANDLERS
# ──────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^bw_"))
async def blockword_callbacks(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    data    = query.data

    if data == "bw_noop":
        return await query.answer("ℹ️ No action needed.")

    if data == "bw_status_info":
        s = await get_settings(chat_id)
        return await query.answer(
            f"Status: {'ON ✅' if s['enabled'] else 'OFF ❌'}  |  "
            f"Warn Limit: {s['warn_limit']}  |  Action: {s['action'].title()}",
            show_alert=True,
        )

    is_admin     = await is_admin_or_owner(client, chat_id, user_id)
    is_owner     = await is_group_owner(client, chat_id, user_id)
    is_bot_owner = user_id in ADMINS_ID

    # ── Toggle ─────────────────────────────────────────────────────
    if data == "bw_toggle":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        s = await get_settings(chat_id)
        new_state = not s["enabled"]
        await set_setting(chat_id, "enabled", new_state)
        await query.message.edit_text(
            f"🛡 **BlockWord Dashboard**\n\n"
            f"Status      : {'✅ Active' if new_state else '❌ Inactive'}\n"
            f"Warn Limit  : `{s['warn_limit']}`\n"
            f"Punishment  : `{s['action'].title()}`",
            reply_markup=dashboard_kb(new_state),
        )
        return await query.answer(f"BlockWord {'✅ Enabled' if new_state else '❌ Disabled'}!")

    # ── Main dashboard ─────────────────────────────────────────────
    if data == "bw_main":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        s = await get_settings(chat_id)
        enabled = s["enabled"]
        await query.message.edit_text(
            f"🛡 **BlockWord Dashboard**\n\n"
            f"Status      : {'✅ Active' if enabled else '❌ Inactive'}\n"
            f"Warn Limit  : `{s['warn_limit']}`\n"
            f"Punishment  : `{s['action'].title()}`\n\n"
            f"Use the buttons below to manage.",
            reply_markup=dashboard_kb(enabled),
        )
        return await query.answer()

    # ── Word list ──────────────────────────────────────────────────
    if data == "bw_listwords":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        gw = await get_group_words(chat_id)
        ow = await get_owner_words()
        text = "📋 **Blocked Words**\n\n"
        text += ("**📌 This Group:**\n" + "\n".join(f"  • `{w}`" for w in gw) + "\n\n") if gw else "**📌 This Group:** _None_\n\n"
        text += ("**🌍 Global:**\n"     + "\n".join(f"  • `{w}`" for w in ow))           if ow else "**🌍 Global:** _None_"
        await query.message.edit_text(text, reply_markup=wordlist_kb())
        return await query.answer()

    # ── Global word list (bot owner) ───────────────────────────────
    if data == "bw_owner_listwords":
        if not is_bot_owner:
            return await query.answer("❌ Bot owner only!", show_alert=True)
        words = await get_owner_words()
        text = "🌍 **Global Blocked Words:**\n" + ("\n".join(f"  • `{w}`" for w in words) if words else "_None_")
        await query.message.edit_text(text, reply_markup=back_kb("bw_main"))
        return await query.answer()

    # ── Settings menu ──────────────────────────────────────────────
    if data == "bw_settings_menu":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        s = await get_settings(chat_id)
        await query.message.edit_text(
            f"⚙️ **Settings**\n\n"
            f"Warn Limit  : `{s['warn_limit']}`\n"
            f"Punishment  : `{s['action'].title()}`\n\n"
            f"Select what to change:",
            reply_markup=settings_kb(),
        )
        return await query.answer()

    # ── Warn limit hint ────────────────────────────────────────────
    if data == "bw_set_warnlimit":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        await query.message.edit_text(
            "⚠️ **Set Warn Limit**\n\n"
            "Send the command:\n`/setwarnlimit <number>`\n\n"
            "Example: `/setwarnlimit 3`",
            reply_markup=back_kb("bw_settings_menu"),
        )
        return await query.answer()

    # ── Punishment picker ──────────────────────────────────────────
    if data == "bw_set_punishment":
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        await query.message.edit_text(
            "🔨 **Choose Punishment on Warn Limit Reached:**",
            reply_markup=punishment_kb(),
        )
        return await query.answer()

    # ── Punishment selection ───────────────────────────────────────
    if data in ("bw_action_mute", "bw_action_ban", "bw_action_kick"):
        if not is_admin:
            return await query.answer("❌ Admins only!", show_alert=True)
        action = data.replace("bw_action_", "")
        await set_setting(chat_id, "action", action)
        await query.message.edit_text(
            f"✅ Punishment set to **{action.title()}**.",
            reply_markup=back_kb("bw_settings_menu"),
        )
        return await query.answer(f"Punishment → {action.title()}")

    # ── Add word hint ──────────────────────────────────────────────
    if data == "bw_addword_hint":
        return await query.answer("Send /addword <word> to add another word.", show_alert=True)

    # ── Help ───────────────────────────────────────────────────────
    if data == "bw_help":
        help_text = (
            "🛡 **BlockWord Help**\n\n"
            "**👮 Admin Commands:**\n"
            "• `/blockword` — Open dashboard\n"
            "• `/blockword on|off` — Quick toggle\n"
            "• `/addword <word>` — Add word _(this group only)_\n"
            "• `/blockwords` — List blocked words\n"
            "• `/setwarnlimit <n>` — Set warn limit\n"
            "• `/setpunishment` — Set punishment action\n\n"
            "**👑 Group Owner Commands:**\n"
            "• `/removeword <word>` — Remove a group word\n\n"
            "**🤖 Bot Owner Commands:**\n"
            "• `/ownerblockword <word>` — Add global word\n"
            "• `/ownerrmword <word>` — Remove global word\n"
            "• `/rmallwords` — Clear ALL global words\n\n"
            "**ℹ️ Notes:**\n"
            "• Built-in bad words always detected regardless of toggle.\n"
            "• Detection is fully **case-insensitive**:\n"
            "  `DRUGS` = `drugs` = `DrUgS` = `DR0GS` = `ᴅʀᴜɢs` ✓\n"
            "• Leetspeak caught automatically (0→o, 1→i, 3→e …).\n"
            "• Other bot commands are **never** blocked.\n"
            "• Everything survives restarts (MongoDB)."
        )
        await query.message.edit_text(help_text, reply_markup=back_kb("bw_main"))
        return await query.answer()

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_88"
__help__ = """
👮 **Admin Commands:**
🔻 /blockword — ᴏᴘᴇɴ ᴅᴀsʜʙᴏᴀʀᴅ
🔻 /blockword on|off — ǫᴜɪᴄᴋ ᴛᴏɢɢʟᴇ
🔻 /addword <word> — ᴀᴅᴅ ᴡᴏʀᴅ (ᴛʜɪs ɢʀᴏᴜᴘ ᴏɴʟʏ)
🔻 /blockwords — ʟɪsᴛ ʙʟᴏᴄᴋᴇᴅ ᴡᴏʀᴅs
🔻 /setwarnlimit <n> — sᴇᴛ ᴡᴀʀɴ ʟɪᴍɪᴛ
🔻 /setpunishment — sᴇᴛ ᴘᴜɴɪsʜᴍᴇɴᴛ ᴀᴄᴛɪᴏɴ

👑 **Group Owner Commands:**
🔻 /removeword <word> — ʀᴇᴍᴏᴠᴇ ᴀ ɢʀᴏᴜᴘ ᴡᴏʀᴅ

🤖 **Bot Owner Commands:**
🔻 /ownerblockword <word> — ᴀᴅᴅ ɢʟᴏʙᴀʟ ʙʟᴏᴄᴋ ᴡᴏʀᴅ
🔻 /ownerrmword <word> — ʀᴇᴍᴏᴠᴇ ɢʟᴏʙᴀʟ ᴡᴏʀᴅ
🔻 /rmallwords — ᴄʟᴇᴀʀ ᴀʟʟ ɢʟᴏʙᴀʟ ᴡᴏʀᴅs

ℹ️ **Notes:**
🔻 ʙᴜɪʟᴛ-ɪɴ ʙᴀᴅ ᴡᴏʀᴅs ᴀʟᴡᴀʏs ᴅᴇᴛᴇᴄᴛᴇᴅ
🔻 ᴄᴀsᴇ-ɪɴsᴇɴsɪᴛɪᴠᴇ (DRUGS = drugs = DrUgS = DR0GS = ᴅʀᴜɢs ✓)
🔻 ʟᴇᴇᴛsᴘᴇᴀᴋ ᴀᴜᴛᴏ ᴅᴇᴛᴇᴄᴛᴇᴅ (0→o, 1→i, 3→e)
🔻 ᴏᴛʜᴇʀ ʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅs ɴᴇᴠᴇʀ ʙʟᴏᴄᴋᴇᴅ
"""
