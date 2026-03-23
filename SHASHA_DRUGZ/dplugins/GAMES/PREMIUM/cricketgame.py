#  ✅ /cricket main menu with full inline navigation
#  ✅ Solo cricket lobby + 1v1v1v1 rotation engine
#  ✅ Team Play (A vs B) — two innings + target chase
#  ✅ PM bowling system (cheat-proof, 1-min timer notice)
#  ✅ Spam-Free bowling mode
#  ✅ Overs system (1–20)
#  🎬 VIDEO CLIPS per game event:
#       bowling.mp4   → bowler notified to PM their number
#       batting.mp4   → batter's turn to send number in group
#       wicket.mp4    → OUT! wicket falls
#       three_run.mp4 → 3 runs scored
#       four_run.mp4  → FOUR! boundary
#       five_run.mp4  → 5 runs scored
#       six_run.mp4   → SIX! maximum
#  ✅ Live commentary engine
#  ✅ MOTM auto-calculation (batting + bowling pts)
#  ✅ Hat-trick detection
#  ✅ MongoDB persistent stats (never lost on restart)
#  ✅ Leaderboard — Runs / Wickets / SR / MOTM / Tourn Wins
#  ✅ Coins economy (win / MOTM / sixes / fours)
#  ✅ 10 auto-unlocking Badges & achievements
#  ✅ Daily missions (3/day · progress bars · coin rewards)
#  ✅ Tournament Mode — Full Auto Knockout Engine
#       QF → SF → Final → Champion (auto-detected from game)
#       BYE system for odd player counts
#       Rewards: Champion 200 / Runner-up 100 / SF 50
#  ✅ /cricketuserinfo (self + reply-to)
#  ✅ /crickethelp — full command reference
# ============================================================

import asyncio
import random
import datetime
import os
from collections import defaultdict
from typing import Dict, List, Optional

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message,
)
from pyrogram.errors import MessageNotModified
from motor.motor_asyncio import AsyncIOMotorClient

import config
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ import app

# ============================================================
# 🎬  VIDEO ASSET PATHS
# ============================================================

_ASSET_BASE = "SHASHA_DRUGZ/assets/cricket"

ASSETS: Dict[str, str] = {
    "batting":   os.path.join(_ASSET_BASE, "batting.mp4"),
    "bowling":   os.path.join(_ASSET_BASE, "bowling.mp4"),
    "wicket":    os.path.join(_ASSET_BASE, "wicket.mp4"),
    "three_run": os.path.join(_ASSET_BASE, "three_run.mp4"),
    "four_run":  os.path.join(_ASSET_BASE, "four_run.mp4"),
    "five_run":  os.path.join(_ASSET_BASE, "five_run.mp4"),
    "six_run":   os.path.join(_ASSET_BASE, "six_run.mp4"),
}

# Map run value → asset key  (1 and 2 use batting clip as fallback)
RUN_ASSET: Dict[int, str] = {
    3: "three_run",
    4: "four_run",
    5: "five_run",
    6: "six_run",
}


async def _send_video(chat_id: int, asset_key: str, caption: str) -> None:
    """
    Send a cricket video clip to the group chat.
    Falls back to a plain text message when the file is missing
    (e.g. dev environment without assets).
    """
    path = ASSETS.get(asset_key, "")
    if path and os.path.isfile(path):
        try:
            await app.send_video(
                chat_id,
                video=path,
                caption=caption,
                #parse_mode="markdown",
                supports_streaming=True,
            )
            return
        except Exception:
            pass
    # Fallback
    await app.send_message(chat_id, caption)


async def _send_video_reply(message: Message, asset_key: str, caption: str) -> None:
    """
    Reply to an existing message with a cricket video clip.
    Falls back to plain text reply when the file is missing.
    """
    path = ASSETS.get(asset_key, "")
    if path and os.path.isfile(path):
        try:
            await message.reply_video(
                video=path,
                caption=caption,
                #parse_mode="markdown",
                supports_streaming=True,
            )
            return
        except Exception:
            pass
    await message.reply_text(caption)

# ============================================================
# ⚙️  MONGODB SETUP
# ============================================================

MONGO_URL = getattr(config, "TEMP_MONGODB", None) or getattr(config, "MONGO_DB_URI", None)
if not MONGO_URL:
    raise Exception("MongoDB URL not found in config. Set TEMP_MONGODB or MONGO_DB_URI.")

_mongo_client = AsyncIOMotorClient(MONGO_URL)
_db           = _mongo_client["cricket_game"]

col_players  = _db["players"]
col_economy  = _db["economy"]
col_badges   = _db["badges"]
col_missions = _db["missions"]
col_matches  = _db["matches"]


async def _ensure_player(user_id: int) -> None:
    await col_players.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id,
            "matches": 0, "runs": 0, "balls": 0,
            "wickets": 0, "balls_bowled": 0,
            "fours": 0, "sixes": 0,
            "ducks": 0, "fifties": 0, "centuries": 0,
            "hattricks": 0, "motm": 0, "highest": 0,
            "tourn_wins": 0,
        }},
        upsert=True,
    )


async def _ensure_economy(user_id: int) -> None:
    await col_economy.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "coins": 0}},
        upsert=True,
    )

# ============================================================
# 💬  COMMENTARY BANKS
# ============================================================

COMMENTARY_RUNS: Dict[int, List[str]] = {
    1: ["<blockquote>🏃 ǫᴜɪᴄᴋ sɪɴɢʟᴇ!", "⚡ ɴᴜᴅɢᴇᴅ ғᴏʀ 1!", "🎯 sᴍᴀʀᴛ ᴘʟᴀᴄᴇᴍᴇɴᴛ — 1 ʀᴜɴ!</blockquote>"],
    2: ["<blockquote>🔁 ɢʀᴇᴀᴛ ʀᴜɴɴɪɴɢ! 2 ʀᴜɴs!", "💨 ᴛᴜʀɴᴇᴅ ғᴏʀ 2!", "🎳 ɢᴏᴏᴅ ᴄʀɪᴄᴋᴇᴛ — 2 ʀᴜɴs!</blockquote>"],
    3: ["<blockquote>🌀 ᴛʜʀᴇᴇ! ʙʀɪʟʟɪᴀɴᴛ ᴇғғᴏʀᴛ!", "🏃 ᴛʜʀᴇᴇ ʀᴜɴs — ᴏᴜᴛsᴛᴀɴᴅɪɴɢ ʀᴜɴɴɪɴɢ!</blockquote>"],
    4: ["<blockquote>🚀 ғᴏᴜʀ! ᴄʀᴀᴄᴋɪɴɢ ᴄᴏᴠᴇʀ ᴅʀɪᴠᴇ!", "💥 ғᴏᴜʀ! sᴍᴀsʜᴇs ᴛᴏ ᴛʜᴇ ʙᴏᴜɴᴅᴀʀʏ!", "🎆 ғᴏᴜʀ! ʀᴀᴄɪɴɢ ᴀᴡᴀʏ!</blockquote>"],
    5: ["<blockquote>😲 5 ᴏᴠᴇʀᴛʜʀᴏᴡs! ʟᴜᴄᴋʏ ʙʀᴇᴀᴋ!", "⚡ 5 ʀᴜɴs! ғɪᴇʟᴅᴇʀ ғᴜᴍʙʟᴇs!</blockquote>"],
    6: ["<<blockquote>💥 ᴍᴀssɪᴠᴇ sɪx! ɢᴏɴᴇ ɪɴᴛᴏ ᴛʜᴇ sᴛᴀɴᴅs!", "🌟 sɪx! ʀɪɢʜᴛ ᴏᴜᴛ ᴏғ ᴛʜᴇ sᴛᴀᴅɪᴜᴍ!", "🔥 ʙᴏᴏᴍ! ᴍᴏɴsᴛᴇʀ sɪx!</blockquote>"],
}
COMMENTARY_OUT: List[str] = [
    "<blockquote>🎯 ᴄʟᴇᴀɴ ʙᴏᴡʟᴇᴅ! ᴛɪᴍʙᴇʀ!</blockquote>",
    "<blockquote>😱 ᴄᴀᴜɢʜᴛ! ᴡʜᴀᴛ ᴀ ɢʀᴀʙ!</blockquote>",
    "<blockquote>🪙 ʟʙᴡ! ᴛʜᴇ ғɪɴɢᴇʀ ɢᴏᴇs ᴜᴘ!</blockquote>",
    "<blockquote>💥 sᴛᴜᴍᴘᴇᴅ! ᴄᴀᴜɢʜᴛ ᴏᴜᴛ ᴏғ ᴄʀᴇᴀsᴇ!</blockquote>",
    "<blockquote>⚡ ʀᴜɴ ᴏᴜᴛ! ᴅɪʀᴇᴄᴛ ʜɪᴛ!</blockquote>",
    "<blockquote>🎳 ɴɪᴄᴋᴇᴅ ᴏғғ! ᴇᴅɢᴇ ᴀɴᴅ ɢᴏɴᴇ!</blockquote>",
]
COMMENTARY_OVER_END: List[str] = [
    "<blockquote>🔔 ᴇɴᴅ ᴏғ ᴏᴠᴇʀ! ɢᴏᴏᴅ sᴘᴇʟʟ!</blockquote>",
    "<blockquote>📢 ᴏᴠᴇʀ ᴅᴏɴᴇ! ᴛᴇᴀᴍs ʜᴜᴅᴅʟᴇ.</blockquote>",
    "<blockquote>🏟️ ᴄʀᴏᴡᴅ ᴄʜᴇᴇʀs ᴀs ᴏᴠᴇʀ ᴇɴᴅs!</blockquote>",
]

# ============================================================
# 🌐  IN-MEMORY GAME STATE
# ============================================================

solo_games:          Dict[int, dict] = {}
team_games:          Dict[int, dict] = {}
tournaments:         Dict[int, object] = {}
bowler_pm_numbers:   Dict[int, int] = {}
bowler_history:      Dict[int, List[int]] = {}
consecutive_wickets: Dict[int, int] = {}

# ============================================================
# 🏆  TOURNAMENT DATA STRUCTURES
# ============================================================

class TournamentMatch:
    def __init__(self, p1: Optional[int], p2: Optional[int], match_num: int):
        self.player1   = p1
        self.player2   = p2
        self.match_num = match_num
        self.winner:  Optional[int] = None
        self.started: bool = False


class Tournament:
    def __init__(self, chat_id: int, host: int):
        self.chat_id        = chat_id
        self.host           = host
        self.players:       List[int]               = []
        self.player_names:  Dict[int, str]          = {}
        self.started        = False
        self.round_name     = "Lobby"
        self.matches:       List[TournamentMatch]   = []
        self.semifinalists: List[int]               = []
        self.runner_up:     Optional[int]           = None
        self.overs          = 2
        self.spam_free      = False


def _create_tourn_matches(players: List[Optional[int]], start: int = 1) -> List[TournamentMatch]:
    matches, num = [], start
    for i in range(0, len(players) - 1, 2):
        matches.append(TournamentMatch(players[i], players[i + 1], num))
        num += 1
    return matches


def _get_round_name(n: int) -> str:
    if n >= 8: return "⚡ ǫᴜᴀʀᴛᴇʀ-ғɪɴᴀʟ"
    if n == 4: return "🔥 sᴇᴍɪ-ғɪɴᴀʟ"
    if n == 2: return "🏆 ғɪɴᴀʟ"
    return "🎮 ɴᴇxᴛ ʀᴏᴜɴᴅ"

# ============================================================
# 🏏  MENU TEXT CONSTANTS
# ============================================================

CRICKET_MAIN_TEXT = """
<blockquote>🏏 **ᴄʀɪᴄᴋᴇᴛ ᴀʀᴇɴᴀ — ᴀᴄᴛɪᴠᴀᴛᴇᴅ**</blockquote>
<blockquote>🎯 **ʏᴏᴜʀ ᴍɪssɪᴏɴ:**
  ⚡ ᴏᴜᴛsᴍᴀʀᴛ ᴀɴᴅ ᴏᴜᴛᴘʟᴀʏ ʀɪᴠᴀʟs ɪɴ ᴇᴘɪᴄ 1v1ᴠ1v1 ᴄʟᴀsʜᴇs
  🏆 ᴅᴏᴍɪɴᴀᴛᴇ ᴛᴏᴜʀɴᴀᴍᴇɴᴛs ᴀɴᴅ ʀɪsᴇ ᴛʜʀᴏᴜɢʜ ᴛʜᴇ ʀᴀɴᴋs
  🌟 ʙᴜɪʟᴅ ʏᴏᴜʀ ᴜɴsᴛᴏᴘᴘᴀʙʟᴇ ᴄʀɪᴄᴋᴇᴛ ʟᴇɢᴀᴄʏ</blockquote>
<blockquote>📊 **ᴘʀᴏɢʀᴇss ᴛʀᴀᴄᴋᴇʀ:**
  📈 sᴛᴀᴛs: ʀᴜɴs · sʀ · ʙᴀʟʟs · 4s · 6s
  💰 ᴄᴏɪɴs · 🥇 ᴍᴠᴘ ᴛɪᴛʟᴇs · 🏅 ʙᴀᴅɢᴇs</blockquote>
<blockquote>🎙️ **ʟɪᴠᴇ ᴄᴏᴍᴍᴇɴᴛᴀʀʏ ᴇɴɢɪɴᴇ:** ᴀᴄᴛɪᴠᴀᴛᴇᴅ
🎬 **ᴠɪᴅᴇᴏ ʜɪɢʜʟɪɢʜᴛs:** ᴇɴᴀʙʟᴇᴅ ᴇᴠᴇʀʏ ʙᴀʟʟ!
🎥 ᴇᴠᴇʀʏ sʜᴏᴛ ᴄᴏᴜɴᴛs — ᴇᴠᴇʀʏ ᴍᴀᴛᴄʜ ᴛᴇʟʟs ᴀ sᴛᴏʀʏ.</blockquote>
"""

SOLO_MENU_TEXT = """
<blockquote>🏏 **sᴏʟᴏ ᴄʀɪᴄᴋᴇᴛ ᴍᴏᴅᴇ**</blockquote>
<blockquote>**sᴇᴛᴜᴘ ᴄᴏᴍᴍᴀɴᴅs:**
• `/solocricket` — ᴄʀᴇᴀᴛᴇ sᴏʟᴏ ʟᴏʙʙʏ
• `/joincricket` — ᴊᴏɪɴ ᴇxɪsᴛɪɴɢ ɢᴀᴍᴇ
• `/startsolocricket` — sᴛᴀʀᴛ ᴍᴀᴛᴄʜ (ʜᴏsᴛ)
• `/extendsolocricket [sᴇᴄs]` — ᴇxᴛᴇɴᴅ ᴊᴏɪɴ ᴡɪɴᴅᴏᴡ</blockquote>
<blockquote>**ɪɴ-ɢᴀᴍᴇ ᴄᴏᴍᴍᴀɴᴅs:**
• `/cricketsolo_status` — ᴄᴜʀʀᴇɴᴛ ɢᴀᴍᴇ ɪɴғᴏ
• `/cricketsoloscore` — ʟɪᴠᴇ sᴄᴏʀᴇs
• `/cricketsoloplayers` — ʟɪsᴛ ᴀʟʟ ᴘʟᴀʏᴇʀs + ʀᴏʟᴇs
• `/cricketsololeave` — ʟᴇᴀᴠᴇ ᴍᴀᴛᴄʜ
• `/cricketmystatus` — ʏᴏᴜʀ ʀᴏʟᴇ & sᴄᴏʀᴇ
• `/cricketendsolo` — ғᴏʀᴄᴇ ᴇɴᴅ (ᴀᴅᴍɪɴ ᴏɴʟʏ)</blockquote>
<blockquote>**ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:**
• 🎬 ʙᴏᴡʟɪɴɢ ᴠɪᴅᴇᴏ ᴘʟᴀʏs → ʙᴏᴡʟᴇʀ ᴘᴍ's ɴᴜᴍʙᴇʀ (1 ᴍɪɴ)
• 🎬 ʙᴀᴛᴛɪɴɢ ᴠɪᴅᴇᴏ ᴘʟᴀʏs → ʙᴀᴛᴛᴇʀ sᴇɴᴅs 1–6 ɪɴ ɢʀᴏᴜᴘ
• ɴᴜᴍʙᴇʀs ᴍᴀᴛᴄʜ → 🎬 ᴡɪᴄᴋᴇᴛ ᴠɪᴅᴇᴏ + ᴏᴜᴛ ❌
• ᴅɪғғᴇʀᴇɴᴛ → 🎬 ʀᴜɴ ᴠɪᴅᴇᴏ + ʀᴜɴs sᴄᴏʀᴇᴅ ✅</blockquote>
"""

TEAM_MENU_TEXT = """
<blockquote>👥 **ᴛᴇᴀᴍ ᴘʟᴀʏ ᴍᴏᴅᴇ**</blockquote>
<blockquote>**ǫᴜɪᴄᴋ sᴛᴀʀᴛ:**
1️⃣ `/cricketgame` → **ɪ'ᴍ ᴛʜᴇ ʜᴏsᴛ**
2️⃣ sᴇʟᴇᴄᴛ ᴍᴏᴅᴇ
3️⃣ `/cricketcreateteam`
4️⃣ `/cricketjoinAteam` / `/cricketjoinBteam`
5️⃣ `/cricketstartteam`</blockquote>
<blockquote>ᴛᴡᴏ-ɪɴɴɪɴɢs ғᴏʀᴍᴀᴛ + ᴛᴀʀɢᴇᴛ ᴄʜᴀsᴇ + ᴠɪᴅᴇᴏ ʜɪɢʜʟɪɢʜᴛs!</blockquote>
"""

TEAM_COMMANDS_TEXT = """
<blockquote>📋 **ᴛᴇᴀᴍ ᴘʟᴀʏ ᴄᴏᴍᴍᴀɴᴅs**</blockquote>
<blockquote>• `/addcricket [A/B] [@user]` — ᴀᴅᴅ ᴘʟᴀʏᴇʀ
• `/removecricketplayer [@user]` — ʀᴇᴍᴏᴠᴇ ᴘʟᴀʏᴇʀ
• `/cricketteams` — sʜᴏᴡ ʀᴏsᴛᴇʀs
• `/cricketscore` — ʟɪᴠᴇ sᴄᴏʀᴇ
• `/endcricket` — ᴇɴᴅ (ᴀᴅᴍɪɴ)
• `/batting [@u]` — sᴇᴛ ʙᴀᴛᴛᴇʀ
• `/bowling [@u]` — sᴇᴛ ʙᴏᴡʟᴇʀ
• `/setovers [1-20]` — sᴇᴛ ᴍᴀᴛᴄʜ ᴏᴠᴇʀs</blockquote>
"""

GAME_MODES_TEXT = """
<blockquote>🎮 **ɢᴀᴍᴇ ᴍᴏᴅᴇs**</blockquote>
<blockquote>🎯 **ɴᴏʀᴍᴀʟ ᴍᴏᴅᴇ** — ᴀɴʏ ɴᴜᴍʙᴇʀ, ᴀɴʏ ᴛɪᴍᴇ
🚫 **sᴘᴀᴍ-ғʀᴇᴇ** — ɴᴏ sᴀᴍᴇ ɴᴜᴍʙᴇʀ 3× ɪɴ ᴀ ʀᴏᴡ</blockquote>
<blockquote>**ғᴏʀᴍᴀᴛ:** 1–20 ᴏᴠᴇʀs · 2 ɪɴɴɪɴɢs · ғᴜʟʟ sᴄᴏʀᴇᴄᴀʀᴅ</blockquote>
"""

MOTM_TEXT = """
<blockquote>⭐ **ᴍᴀɴ ᴏғ ᴛʜᴇ ᴍᴀᴛᴄʜ sʏsᴛᴇᴍ**</blockquote>
<blockquote>🏏 **ʙᴀᴛᴛɪɴɢ:** +1/ʀᴜɴ · +1/ғᴏᴜʀ · +2/sɪx
SR>100: +10 · ғɪғᴛʏ: +15 · ᴄᴇɴᴛᴜʀʏ: +35</blockquote>
<blockquote>⚾ **ʙᴏᴡʟɪɴɢ:** +25/ᴡɪᴄᴋᴇᴛ · ᴇᴄᴏɴᴏᴍʏ<6: (6-ER)×5
ʜᴀᴛ-ᴛʀɪᴄᴋ: +50</blockquote>
<blockquote>🎯 ʜɪɢʜᴇsᴛ ᴛᴏᴛᴀʟ = ᴍᴏᴛᴍ! ⚖️</blockquote>
"""

STATS_MENU_TEXT = """
<blockquote>📊 **sᴛᴀᴛɪsᴛɪᴄs sʏsᴛᴇᴍ**</blockquote>
</blockquote>• `/cricketuserinfo` — ʏᴏᴜʀ ᴄᴀʀᴇᴇʀ sᴛᴀᴛs
• `/cricketuserinfo` (ʀᴇᴘʟʏ) — ᴀɴʏᴏɴᴇ's sᴛᴀᴛs
• `/cricketleaderboard` — ɢʟᴏʙᴀʟ ᴛᴏᴘ 10
• `/cricketcoins` — ᴄᴏɪɴ ʙᴀʟᴀɴᴄᴇ
• `/cricketbadges` — ʏᴏᴜʀ ʙᴀᴅɢᴇs
• `/cricketmissions` — ᴅᴀɪʟʏ ᴍɪssɪᴏɴs</blockquote>
"""

TOURN_MENU_TEXT = """
<blockquote>🏆 **ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴍᴏᴅᴇ**</blockquote>
<blockquote>ᴀᴜᴛᴏ ᴋɴᴏᴄᴋᴏᴜᴛ — ɴᴏ ᴍᴀɴᴜᴀʟ ʀᴇsᴜʟᴛ ʀᴇᴘᴏʀᴛɪɴɢ!

• `/crickettournament` — ᴄʀᴇᴀᴛᴇ
• `/joincrickettourn` — ᴊᴏɪɴ
• `/startcrickettournament` — ʟᴀᴜɴᴄʜ (ᴍɪɴ 4)
• `/tournamentstatus` — ʟɪᴠᴇ ʙʀᴀᴄᴋᴇᴛ
• `/settournamentovers [n]` — sᴇᴛ ᴏᴠᴇʀs
• `/endcrickettourn` — ᴄᴀɴᴄᴇʟ</blockquote>

<blockquote>**ғᴏʀᴍᴀᴛ:** ǫғ → sғ → ғɪɴᴀʟ → 🏆 ᴄʜᴀᴍᴘɪᴏɴ

🥇 ᴄʜᴀᴍᴘɪᴏɴ: +200 ᴄᴏɪɴs + ʙᴀᴅɢᴇ
🥈 ʀᴜɴɴᴇʀ-ᴜᴘ: +100 ᴄᴏɪɴs
🥉 sᴇᴍɪ-ғɪɴᴀʟɪsᴛs: +50 ᴄᴏɪɴs</blockquote>
"""

# ============================================================
# 🎛️  /cricket MAIN COMMAND
# ============================================================

@Client.on_message(filters.command("cricket") & filters.group)
async def cricket_main_menu(_, message: Message):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏏 sᴏʟᴏ ᴄʀɪᴄᴋᴇᴛ",    callback_data="cricket_solo_menu"),
            InlineKeyboardButton("👥 ᴛᴇᴀᴍ ᴘʟᴀʏ",        callback_data="cricket_team_menu"),
        ],
        [
            InlineKeyboardButton("🏆 ᴛᴏᴜʀɴᴀᴍᴇɴᴛ",       callback_data="cricket_tourn_menu"),
            InlineKeyboardButton("⭐ ᴍᴀɴ ᴏғ ᴛʜᴇ ᴍᴀᴛᴄʜ",  callback_data="cricket_motm_info"),
        ],
        [
            InlineKeyboardButton("📊 sᴛᴀᴛɪsᴛɪᴄs",       callback_data="cricket_stats_info"),
        ],
    ])
    await message.reply_text(CRICKET_MAIN_TEXT, reply_markup=buttons)

# ============================================================
# 🎛️  CALLBACK QUERY ROUTER
# ============================================================

def _main_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏏 sᴏʟᴏ ᴄʀɪᴄᴋᴇᴛ",    callback_data="cricket_solo_menu"),
            InlineKeyboardButton("👥 ᴛᴇᴀᴍ ᴘʟᴀʏ",        callback_data="cricket_team_menu"),
        ],
        [
            InlineKeyboardButton("🏆 ᴛᴏᴜʀɴᴀᴍᴇɴᴛ",       callback_data="cricket_tourn_menu"),
            InlineKeyboardButton("⭐ ᴍᴀɴ ᴏғ ᴛʜᴇ ᴍᴀᴛᴄʜ",  callback_data="cricket_motm_info"),
        ],
        [InlineKeyboardButton("📊 sᴛᴀᴛɪsᴛɪᴄs",          callback_data="cricket_stats_info")],
    ])

def _back_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="cricket_main_menu")]])

def _back_team() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴛᴇᴀᴍ ᴍᴇɴᴜ", callback_data="cricket_team_menu")]])


@Client.on_callback_query(filters.regex(r"^cricket_"))
async def cricket_callback(_, query: CallbackQuery):
    data = query.data
    mapping = {
        "cricket_main_menu":     (CRICKET_MAIN_TEXT,   _main_buttons()),
        "cricket_solo_menu":     (SOLO_MENU_TEXT,       _back_main()),
        "cricket_motm_info":     (MOTM_TEXT,            _back_main()),
        "cricket_stats_info":    (STATS_MENU_TEXT,      _back_main()),
        "cricket_tourn_menu":    (TOURN_MENU_TEXT,      _back_main()),
        "cricket_game_modes":    (GAME_MODES_TEXT,      _back_team()),
        "cricket_team_commands": (TEAM_COMMANDS_TEXT,   _back_team()),
        "cricket_team_menu": (TEAM_MENU_TEXT, InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 ᴄᴏᴍᴍᴀɴᴅs",   callback_data="cricket_team_commands"),
                InlineKeyboardButton("🎮 ɢᴀᴍᴇ ᴍᴏᴅᴇs", callback_data="cricket_game_modes"),
            ],
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="cricket_main_menu")],
        ])),
    }
    if data in mapping:
        text, markup = mapping[data]
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except MessageNotModified:
            pass
    await query.answer()

# ============================================================
# 🏏  SOLO CRICKET — LOBBY
# ============================================================

def _new_solo_game(host_id: int, host_name: str) -> dict:
    return {
        "host": host_id, "host_name": host_name,
        "players": [host_id],
        "player_names": {host_id: host_name},
        "started": False, "spam_free": False, "overs": 2,
        "scores":       defaultdict(int),
        "balls_faced":  defaultdict(int),
        "wickets_lost": defaultdict(int),
        "fours":        defaultdict(int),
        "sixes":        defaultdict(int),
        "current_batter": host_id, "current_bowler": None,
        "ball_count": 0, "join_open": True,
        "tournament_chat": None,
    }


def _launch_solo_game(game: dict) -> None:
    players = game["players"]
    game["current_batter"] = players[0]
    game["current_bowler"] = players[1]
    game["started"]        = True
    game["join_open"]      = False


@Client.on_message(filters.command("solocricket") & filters.group)
async def cmd_solocricket(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat in solo_games and solo_games[chat].get("started"):
        return await message.reply_text("<blockquote>❌ ᴍᴀᴛᴄʜ ʀᴜɴɴɪɴɢ! ᴜsᴇ `/cricketendsolo` ғɪʀsᴛ.</blockquote>")
    solo_games[chat] = _new_solo_game(user.id, user.first_name)
    await message.reply_text(
        f"</blockquote>🏏 **sᴏʟᴏ ᴄʀɪᴄᴋᴇᴛ ʟᴏʙʙʏ ᴄʀᴇᴀᴛᴇᴅ!**</blockquote>\n\n"
        f"<blockquote>👑 ʜᴏsᴛ: **{user.first_name}**\n"
        f"⚙️ ᴏᴠᴇʀs: `2` (change: `/setovers [n]`)\n"
        f"📢 ᴊᴏɪɴ: `/joincricket`\n"
        f"🚀 sᴛᴀʀᴛ: `/startsolocricket`</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("joincricket") & filters.group)
async def cmd_joincricket(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in solo_games:
        return await message.reply_text("<blockquote>❌ ɴᴏ ʟᴏʙʙʏ. ᴜsᴇ `/solocricket` ғɪʀsᴛ.</blockquote>")
    game = solo_games[chat]
    if game.get("started"):
        return await message.reply_text("<blockquote>❌ ᴍᴀᴛᴄʜ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ.</blockquote>")
    if user.id in game["players"]:
        return await message.reply_text("<blockquote>ℹ️ ᴀʟʀᴇᴀᴅʏ ɪɴ ʟᴏʙʙʏ!</blockquote>")
    game["players"].append(user.id)
    game["player_names"][user.id] = user.first_name
    await message.reply_text(
        f"<blockquote>✅ **{user.first_name}** ᴊᴏɪɴᴇᴅ! ({len(game['players'])} players)</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("startsolocricket") & filters.group)
async def cmd_startsolocricket(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in solo_games:
        return await message.reply_text("<blockquote>❌ ɴᴏ ʟᴏʙʙʏ. ᴜsᴇ `/solocricket` ғɪʀsᴛ.<blockquote>")
    game = solo_games[chat]
    if game["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("<blockquote>❌ ᴏɴʟʏ ʜᴏsᴛ ᴄᴀɴ sᴛᴀʀᴛ.</blockquote>")
    if len(game["players"]) < 2:
        return await message.reply_text("<blockquote>❌ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ 2 ᴘʟᴀʏᴇʀs!</blockquote>")
    if game.get("started"):
        return await message.reply_text("<blockquote>❌ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ.</blockquote>")
    _launch_solo_game(game)
    await _announce_ball_start(chat, game)


@Client.on_message(filters.command("setovers") & filters.group)
async def cmd_setovers(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    game = solo_games.get(chat) or team_games.get(chat)
    if not game:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.")
    if game.get("host") != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ.")
    args = message.command
    if len(args) < 2 or not args[1].isdigit():
        return await message.reply_text("ᴜsᴀɢᴇ: `/setovers [1-20]`")
    overs = max(1, min(20, int(args[1])))
    game["overs"] = overs
    await message.reply_text(f"<blockquote>⚙️ ᴏᴠᴇʀs sᴇᴛ ᴛᴏ **{overs}** ({overs*6} ʙᴀʟʟs)</blockquote>")


@Client.on_message(filters.command("setspamfree") & filters.group)
async def cmd_setspamfree(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    game = solo_games.get(chat) or team_games.get(chat)
    if not game:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏʙʙʏ.")
    if game.get("host") != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ.")
    game["spam_free"] = not game.get("spam_free", False)
    mode = "🚫 sᴘᴀᴍ-ғʀᴇᴇ" if game["spam_free"] else "🎯 ɴᴏʀᴍᴀʟ"
    await message.reply_text(f"🎮 ᴍᴏᴅᴇ: **{mode}**!")


@Client.on_message(filters.command("extendsolocricket") & filters.group)
async def cmd_extend(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in solo_games:
        return await message.reply_text("❌ ɴᴏ ʟᴏʙʙʏ.")
    if solo_games[chat]["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ.")
    args = message.command
    secs = int(args[1]) if len(args) > 1 and args[1].isdigit() else 60
    await message.reply_text(f"⏳ ᴊᴏɪɴ ᴡɪɴᴅᴏᴡ ᴇxᴛᴇɴᴅᴇᴅ **{secs}s**!")
    await asyncio.sleep(secs)
    if chat in solo_games and not solo_games[chat].get("started"):
        await message.reply_text("🔔 ᴊᴏɪɴ ᴡɪɴᴅᴏᴡ ᴄʟᴏsᴇᴅ!")


@Client.on_message(filters.command("cricketsolo_status") & filters.group)
async def cmd_solo_status(_, message: Message):
    chat = message.chat.id
    if chat not in solo_games:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.")
    g = solo_games[chat]
    await message.reply_text(
        f"**sᴛᴀᴛᴜs:** {'🟢 ʀᴜɴɴɪɴɢ' if g.get('started') else '🟡 ᴡᴀɪᴛɪɴɢ'} | "
        f"**ᴍᴏᴅᴇ:** {'🚫 sᴘᴀᴍ-ғʀᴇᴇ' if g.get('spam_free') else '🎯 ɴᴏʀᴍᴀʟ'} | "
        f"**ᴏᴠᴇʀs:** {g['overs']}\n"
        f"**ᴘʟᴀʏᴇʀs:** {', '.join(g['player_names'].values())}",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketsoloscore") & filters.group)
async def cmd_soloscore(_, message: Message):
    chat = message.chat.id
    if chat not in solo_games:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.")
    g = solo_games[chat]
    if not g.get("started"):
        return await message.reply_text("⏳ ɴᴏᴛ sᴛᴀʀᴛᴇᴅ ʏᴇᴛ.")
    lines = []
    for pid in g["players"]:
        n  = g["player_names"][pid]
        r  = g["scores"][pid]
        b  = g["balls_faced"][pid]
        sr = round(r / b * 100, 1) if b else 0.0
        lines.append(f"🏏 **{n}**: {r} ({b}b) SR:{sr}  4s:{g['fours'][pid]} 6s:{g['sixes'][pid]}")
    await message.reply_text(
        "<blockquote>📊 **ʟɪᴠᴇ sᴄᴏʀᴇs**</blockquote>\n" + "\n".join(lines) +
        f"<blockquote>\n⏱️ {_fmt_overs(g['ball_count'])}/{g['overs']} ᴏᴠᴇʀs</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketsoloplayers") & filters.group)
async def cmd_solo_players(_, message: Message):
    chat = message.chat.id
    if chat not in solo_games:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ.")
    g = solo_games[chat]
    lines = []
    for pid in g["players"]:
        if pid == g.get("current_batter"):   r = " 🏏 ʙᴀᴛᴛɪɴɢ"
        elif pid == g.get("current_bowler"): r = " 🎯 ʙᴏᴡʟɪɴɢ"
        else:                                r = " ⏳ ᴡᴀɪᴛɪɴɢ"
        lines.append(f"• {g['player_names'][pid]}{r}")
    await message.reply_text("**ᴘʟᴀʏᴇʀs ɪɴ ᴍᴀᴛᴄʜ:**\n" + "\n".join(lines))


@Client.on_message(filters.command("cricketsololeave") & filters.group)
async def cmd_solo_leave(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in solo_games or user.id not in solo_games[chat]["players"]:
        return await message.reply_text("❌ ɴᴏᴛ ɪɴ ᴛʜɪs ɢᴀᴍᴇ.")
    g = solo_games[chat]
    g["players"].remove(user.id)
    if len(g["players"]) < 2:
        del solo_games[chat]
        return await message.reply_text(f"<blockquote>👋 {user.first_name} ʟᴇғᴛ — ᴍᴀᴛᴄʜ ᴇɴᴅᴇᴅ!</blockquote>")
    if g.get("current_batter") == user.id or g.get("current_bowler") == user.id:
        _rotate(g)
    await message.reply_text(f"<blockquote.👋 **{user.first_name}** ʟᴇғᴛ.</blockquote>")


@Client.on_message(filters.command("cricketmystatus") & (filters.group | filters.private))
async def cmd_mystatus(_, message: Message):
    user = message.from_user
    chat = message.chat.id
    if chat in solo_games:
        g = solo_games[chat]
        if user.id in g["players"]:
            role = ("Batter 🏏" if user.id == g["current_batter"]
                    else "ʙᴏᴡʟᴇʀ 🎯" if user.id == g["current_bowler"] else "ᴡᴀɪᴛɪɴɢ ⏳")
            return await message.reply_text(
                f"<blockquote>**ʏᴏᴜʀ sᴛᴀᴛᴜs:** {role}</blockquote>\n<blockquote>ʀᴜɴs: {g['scores'][user.id]}  ʙᴀʟʟs: {g['balls_faced'][user.id]}</blockquote>",
                #parse_mode="markdown",
            )
    await message.reply_text("<blockquote>ℹ️ ɴᴏᴛ ɪɴ ᴀɴʏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ ʀɪɢʜᴛ ɴᴏᴡ.</blockquote>")


@Client.on_message(filters.command("cricketendsolo") & filters.group)
async def cmd_end_solo(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in solo_games:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ sᴏʟᴏ ɢᴀᴍᴇ.")
    g = solo_games[chat]
    if g["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ ᴏʀ ᴀᴅᴍɪɴs.")
    result = await _finish_solo_match(chat, g, forced=True)
    del solo_games[chat]
    await app.send_message(chat, result)

# ============================================================
# 🎬  VIDEO ANNOUNCEMENT HELPERS
# ============================================================

async def _announce_ball_start(chat_id: int, game: dict) -> None:
    """
    Called at the start of every ball delivery:
    1. Send bowling video → tells bowler to PM their number
    2. Send batting video → tells batter to send in group
    Mirrors the screenshot flow exactly.
    """
    batter_id   = game["current_batter"]
    bowler_id   = game["current_bowler"]
    batter_name = game["player_names"].get(batter_id, "?")
    bowler_name = game["player_names"].get(bowler_id, "?")
    over_str    = _fmt_overs(game["ball_count"])
    overs       = game["overs"]

    # Step 1 – Bowling video: notify bowler to PM
    await _send_video(
        chat_id,
        "bowling",
        f"<blockquote>🎯 **{bowler_name}**, ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ sᴇɴᴅ ʏᴏᴜʀ ɴᴜᴍʙᴇʀ ᴠɪᴀ **ʙᴏᴛ ᴘᴍ**!</blockquote>\n"
        f"<blockquote>⏳ ʏᴏᴜ ʜᴀᴠᴇ **1 ᴍɪɴ** ᴛᴏ sᴇɴᴅ `1–6` ᴘʀɪᴠᴀᴛᴇʟʏ.\n\n"
        f"📊 ᴏᴠᴇʀ: `{over_str}/{overs}`</blockquote>",
    )
    await asyncio.sleep(1)

    # Step 2 – Batting video: prompt batter to send in group
    await _send_video(
        chat_id,
        "batting",
        f"<blockquote.🏏 ɴᴏᴡ ʙᴀᴛᴛᴇʀ: **{batter_name}** ᴄᴀɴ sᴇɴᴅ ɴᴜᴍʙᴇʀ **(1–6)!!**</blockquote>\n"
        f"<blockquote>📩 ʙᴏᴡʟᴇʀ **{bowler_name}** — sᴇɴᴅ ʏᴏᴜʀ ɴᴜᴍʙᴇʀ ᴠɪᴀ **ᴘᴍ** ғɪʀsᴛ!\n"
        f"📊 ᴏᴠᴇʀ: `{over_str}/{overs}`</blockquote>",
    )


async def _announce_new_batter(chat_id: int, game: dict) -> None:
    """After a wicket — show batting video with new batter announcement."""
    batter_name = game["player_names"].get(game["current_batter"], "?")
    bowler_name = game["player_names"].get(game["current_bowler"], "?")

    await _send_video(
        chat_id,
        "batting",
        f"<blockquote>🔄 **ɴᴇᴡ ʙᴀᴛsᴍᴀɴ: {batter_name}** 🏏</blockquote>\n"
        f"<blockquote>🎯 ʙᴏᴡʟᴇʀ: **{bowler_name}** → ᴘᴍ ʏᴏᴜʀ ɴᴜᴍʙᴇʀ!\n"
        f"🏏 **{batter_name}** → sᴇɴᴅ `1–6` ɪɴ ɢʀᴏᴜᴘ!</blockquote>\n"
        f"<blockquote>⚡ ɢᴇᴛ ʀᴇᴀᴅʏ ғᴏʀ ᴛʜᴇ ɴᴇxᴛ ʙᴀʟʟ 🏏</blockquote>",
    )

# ============================================================
# 🎯  PM BOWLING — private number input
# ============================================================

@Client.on_message(
    filters.private
    & filters.regex(r"^[1-6]$")
    & ~filters.via_bot,
    group=10
)
async def pm_bowl_handler(_, message: Message):
    # Extra safety: ignore any message that starts with '/'
    if message.text.startswith("/"):
        return

    user = message.from_user
    text = message.text.strip()
    num = int(text)

    is_spam_free = any(
        g.get("current_bowler") == user.id and g.get("spam_free")
        for g in list(solo_games.values()) + list(team_games.values())
    )
    if is_spam_free:
        hist = bowler_history.get(user.id, [])
        if len(hist) >= 2 and hist[-1] == num and hist[-2] == num:
            return await message.reply_text(
                "<blockquote>🚫 **sᴘᴀᴍ-ғʀᴇᴇ ᴍᴏᴅᴇ:** ᴄᴀɴ'ᴛ ʙᴏᴡʟ sᴀᴍᴇ ɴᴜᴍʙᴇʀ 3× ɪɴ ᴀ ʀᴏᴡ!</blockquote>\n"
                "<blockquote>ᴄʜᴏᴏsᴇ ᴀ ᴅɪғғᴇʀᴇɴᴛ ɴᴜᴍʙᴇʀ.</blockquote>",
                #parse_mode="markdown",
            )
        hist.append(num)
        bowler_history[user.id] = hist[-3:]

    bowler_pm_numbers[user.id] = num
    await message.reply_text(
        f"<blockquote>🎯 **ʙᴏᴡʟɪɴɢ ɴᴜᴍʙᴇʀ `{num}` ʟᴏᴄᴋᴇᴅ ɪɴ!**</blockquote>\n<blockquote>ᴡᴀɪᴛɪɴɢ ғᴏʀ ʙᴀᴛᴛᴇʀ...</blockquote>",
        #parse_mode="markdown",
    )

# ============================================================
# 🏏  GROUP NUMBER HANDLER — batter input
# ============================================================

@Client.on_message(
    filters.group
    & filters.regex(r"^[1-6]$")
    & ~filters.via_bot,
    group=10
)
async def group_number_handler(_, message: Message):
    # Extra safety: ignore any message that starts with '/'
    if message.text.startswith("/"):
        return

    chat = message.chat.id
    user = message.from_user
    text = message.text.strip()

    if chat in solo_games:
        g = solo_games[chat]
        if not g.get("started") or user.id != g["current_batter"]:
            return
        bowler_id = g["current_bowler"]
        if bowler_id not in bowler_pm_numbers:
            bowler_name = g["player_names"].get(bowler_id, "bowler")
            return await message.reply_text(
                f"<blockquote>⏳ ᴡᴀɪᴛɪɴɢ ғᴏʀ **{bowler_name}** ᴛᴏ sᴇɴᴅ ᴠɪᴀ ᴘᴍ ғɪʀsᴛ...</blockquote>",
                #parse_mode="markdown",
            )
        bat, bowl = int(text), bowler_pm_numbers.pop(bowler_id)
        await _process_solo_ball(message, g, chat, user, bat, bowl)

    elif chat in team_games:
        g = team_games[chat]
        if not g.get("started") or user.id != g.get("current_batter"):
            return
        bowler_id = g.get("current_bowler")
        if bowler_id not in bowler_pm_numbers:
            bowler_name = g["player_names"].get(bowler_id, "bowler")
            return await message.reply_text(
                f"<blockquote>⏳ ᴡᴀɪᴛɪɴɢ ғᴏʀ **{bowler_name}** ᴛᴏ ᴘᴍ ғɪʀsᴛ...</blockquote>",
                #parse_mode="markdown",
            )
        bat, bowl = int(text), bowler_pm_numbers.pop(bowler_id)
        await _process_team_ball(message, g, chat, user, bat, bowl)

# ============================================================
# 🏏  SOLO BALL LOGIC — with video clips
# ============================================================

async def _process_solo_ball(message: Message, game: dict, chat_id: int,
                              user, bat: int, bowl: int):
    batter_id   = user.id
    bowler_id   = game["current_bowler"]
    batter_name = game["player_names"][batter_id]
    bowler_name = game["player_names"][bowler_id]
    game["ball_count"] += 1
    over_str = _fmt_overs(game["ball_count"])

    if bat == bowl:
        # ── WICKET ──────────────────────────────────────────
        game["wickets_lost"][batter_id] += 1
        game["balls_faced"][batter_id]  += 1
        consecutive_wickets[bowler_id]   = consecutive_wickets.get(bowler_id, 0) + 1
        comment = random.choice(COMMENTARY_OUT)
        hat_trick_msg = ""
        if consecutive_wickets.get(bowler_id, 0) >= 3:
            hat_trick_msg = "\n<blockquote>🔥🎯 **ʜᴀᴛ-ᴛʀɪᴄᴋ!!!** ɪɴᴄʀᴇᴅɪʙʟᴇ ʙᴏᴡʟɪɴɢ!</blockquote>"
            consecutive_wickets[bowler_id] = 0

        # Send wicket video
        await _send_video_reply(
            message,
            "wicket",
            f"<blockquote>🏏 **{batter_name}** ➜ `{bat}`  |  🎯 **{bowler_name}** ➜ `{bowl}`</blockquote>\n"
            f"<blockquote>{comment}\n"
            f"❌ **ɴᴜᴍʙᴇʀ ᴍᴀᴛᴄʜᴇs, {batter_name}!**{hat_trick_msg}\n\n"
            f"📊 {game['scores'][batter_id]} ʀᴜɴs  |  ⏱️ `{over_str}/{game['overs']}`</blockquote>",
        )

        if game["ball_count"] >= game["overs"] * 6:
            return await _end_solo_game(message, game, chat_id)

        _rotate(game)
        if game.get("current_batter") and game.get("current_bowler"):
            await asyncio.sleep(1)
            await _announce_new_batter(chat_id, game)

    else:
        # ── RUNS ────────────────────────────────────────────
        runs = bat
        consecutive_wickets[bowler_id]  = 0
        game["scores"][batter_id]      += runs
        game["balls_faced"][batter_id] += 1
        if runs == 4: game["fours"][batter_id] += 1
        if runs == 6: game["sixes"][batter_id] += 1

        comment   = random.choice(COMMENTARY_RUNS.get(runs, ["✅ Shot!"]))
        total     = game["scores"][batter_id]
        b_faced   = game["balls_faced"][batter_id]
        sr        = round(total / b_faced * 100, 1) if b_faced else 0.0
        asset_key = RUN_ASSET.get(runs, "batting")

        # Send run video (four/six/three/five or batting for 1,2)
        await _send_video_reply(
            message,
            asset_key,
            f"<blockquote>🏏 **{batter_name}** ➜ `{bat}`  |  🎯 **{bowler_name}** ➜ `{bowl}`</blockquote>\n"
            f"</blockquote>{comment}\n"
            f"✅ **{runs} ʀᴜɴ{'s' if runs!=1 else ''}!**\n\n"
            f"📊 {batter_name}: **{total}** ({b_faced}b) sʀ:{sr}  |  "
            f"⏱️ `{over_str}/{game['overs']}`</blockquote>",
        )

        # Over end commentary
        if game["ball_count"] % 6 == 0:
            oc = game["ball_count"] // 6
            await app.send_message(
                chat_id,
                f"{random.choice(COMMENTARY_OVER_END)}\n📢 **Over {oc} done!**",
                #parse_mode="markdown",
            )

        if game["ball_count"] >= game["overs"] * 6:
            return await _end_solo_game(message, game, chat_id)

        # Prompt next ball with bowling + batting videos
        await asyncio.sleep(1)
        await _announce_ball_start(chat_id, game)


async def _end_solo_game(message: Message, game: dict, chat_id: int) -> None:
    winner_id = max(game["scores"], key=game["scores"].get) if game["scores"] else None
    result    = await _finish_solo_match(chat_id, game)
    del solo_games[chat_id]
    await app.send_message(chat_id, result)
    if game.get("tournament_chat") is not None and winner_id is not None:
        await asyncio.sleep(2)
        await _on_tournament_match_done(game["tournament_chat"], winner_id)


def _rotate(game: dict) -> None:
    players = game["players"]
    cb = game["current_batter"]
    if cb in players:
        players.remove(cb)
        players.append(cb)
    game["current_batter"] = players[0] if players else None
    game["current_bowler"] = players[1] if len(players) > 1 else None


def _fmt_overs(ball_count: int) -> str:
    return f"{ball_count // 6}.{ball_count % 6}"


async def _finish_solo_match(chat_id: int, game: dict, forced: bool = False) -> str:
    scores = game["scores"]
    if not scores:
        return "🏁 Match ended — no runs scored."

    winner_id   = max(scores, key=scores.get)
    winner_name = game["player_names"].get(winner_id, str(winner_id))
    motm_id     = _calc_motm(game)
    motm_name   = game["player_names"].get(motm_id, "N/A") if motm_id else "N/A"

    lines = ["<blockquote>🛑 **ᴍᴀᴛᴄʜ ᴇɴᴅᴇᴅ (Force)**</blockquote>" if forced else "<blockquote>🏁 **ᴍᴀᴛᴄʜ ғɪɴɪsʜᴇᴅ!**</blockquote>",
             "<blockquote>\n📊 **ғɪɴᴀʟ sᴄᴏʀᴇʙᴏᴀʀᴅ:**</blockquote>"]
    for pid in game["players"]:
        n     = game["player_names"][pid]
        r     = scores.get(pid, 0)
        b     = game["balls_faced"].get(pid, 0)
        sr    = round(r / b * 100, 1) if b else 0.0
        crown = " 🏆" if pid == winner_id else ""
        lines.append(
            f"\n<blockquote>🏏 **{n}{crown}**: {r} ({b}b) SR:{sr}  "
            f"4s:{game['fours'].get(pid,0)} 6s:{game['sixes'].get(pid,0)}</blockquote>"
        )
    lines.append(f"\n<blockquote>🏆 **ᴡɪɴɴᴇʀ: {winner_name}**\n⭐ **ᴍᴏᴛᴍ: {motm_name}**</blockquote>")

    for pid in game["players"]:
        await _save_player_stats(pid, game, winner_id, motm_id)
        await _update_mission(pid, "Play Matches", 1)
        if game["scores"].get(pid, 0) > 0:
            await _update_mission(pid, "Score Runs", game["scores"][pid])
        if game["sixes"].get(pid, 0) > 0:
            await _update_mission(pid, "Hit Sixes", game["sixes"][pid])
        b4 = game["fours"].get(pid, 0) + game["sixes"].get(pid, 0)
        if b4:
            await _update_mission(pid, "Hit Boundaries", b4)

    return "".join(lines)


def _calc_motm(game: dict) -> Optional[int]:
    best, motm = -1, None
    for pid in game["players"]:
        r  = game["scores"].get(pid, 0)
        b  = game["balls_faced"].get(pid, 0)
        sr = r / b * 100 if b else 0
        pts  = r + game["fours"].get(pid, 0) + game["sixes"].get(pid, 0) * 2
        if sr > 100:  pts += 10
        if r >= 100:  pts += 35
        elif r >= 50: pts += 15
        if pts > best: best, motm = pts, pid
    return motm

# ============================================================
# 💾  STATS — SAVE & HELPERS
# ============================================================

async def _save_player_stats(user_id: int, game: dict, winner_id: int,
                              motm_id: Optional[int]) -> None:
    await _ensure_player(user_id)
    await _ensure_economy(user_id)
    runs  = game["scores"].get(user_id, 0)
    balls = game["balls_faced"].get(user_id, 0)
    fours = game["fours"].get(user_id, 0)
    sixes = game["sixes"].get(user_id, 0)

    inc = {"matches": 1, "runs": runs, "balls": balls, "fours": fours, "sixes": sixes}
    if runs >= 100:         inc["centuries"] = 1
    elif runs >= 50:        inc["fifties"]   = 1
    if runs == 0 and balls: inc["ducks"]     = 1
    if user_id == motm_id:  inc["motm"]      = 1

    upd: dict = {"$inc": inc}
    doc = await col_players.find_one({"user_id": user_id})
    if doc and runs > doc.get("highest", 0):
        upd["$set"] = {"highest": runs}
    await col_players.update_one({"user_id": user_id}, upd)

    coins = 0
    if user_id == winner_id: coins += 50
    if user_id == motm_id:   coins += 40
    coins += sixes * 5 + fours * 3
    if coins:
        await _add_coins(user_id, coins)
    await _check_badges(user_id)


async def _add_coins(user_id: int, amount: int) -> None:
    await _ensure_economy(user_id)
    await col_economy.update_one({"user_id": user_id}, {"$inc": {"coins": amount}})


async def _check_badges(user_id: int) -> None:
    doc = await col_players.find_one({"user_id": user_id})
    eco = await col_economy.find_one({"user_id": user_id})
    if not doc: return
    coins = eco.get("coins", 0) if eco else 0
    checks = [
        (doc.get("runs", 0) >= 500,      "🔥 ʀᴜɴ ᴍᴀᴄʜɪɴᴇ"),
        (doc.get("sixes", 0) >= 50,       "💥 sɪx ᴋɪɴɢ"),
        (doc.get("wickets", 0) >= 25,     "🎯 ᴡɪᴄᴋᴇᴛ ʜᴜɴᴛᴇʀ"),
        (doc.get("centuries", 0) >= 1,    "🏏 ᴄᴇɴᴛᴜʀʏ ᴍᴀsᴛᴇʀ"),
        (doc.get("motm", 0) >= 10,        "⭐ ᴍᴠᴘ ʟᴇɢᴇɴᴅ"),
        (doc.get("hattricks", 0) >= 1,    "🎳 ʜᴀᴛ-ᴛʀɪᴄᴋ ʜᴇʀᴏ"),
        (doc.get("matches", 0) >= 50,     "📅 ᴠᴇᴛᴇʀᴀɴ"),
        (doc.get("ducks", 0) >= 10,       "🦆 sᴇʀɪᴀʟ ᴅᴜᴄᴋᴇʀ"),
        (coins >= 1000,                   "💰 ᴄᴏɪɴ ᴋɪɴɢ"),
        (doc.get("tourn_wins", 0) >= 1,  "🏆 ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴄʜᴀᴍᴘɪᴏɴ"),
    ]
    for cond, badge in checks:
        await _maybe_award_badge(user_id, cond, badge)


async def _maybe_award_badge(user_id: int, condition: bool, badge: str) -> None:
    if not condition: return
    if await col_badges.find_one({"user_id": user_id, "badge": badge}): return
    await col_badges.insert_one({"user_id": user_id, "badge": badge})

# ============================================================
# 📊  USER INFO  &  LEADERBOARD
# ============================================================

@Client.on_message(filters.command("cricketuserinfo") & (filters.group | filters.private))
async def cmd_cricketuserinfo(_, message: Message):
    user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    doc  = await col_players.find_one({"user_id": user.id})
    eco  = await col_economy.find_one({"user_id": user.id})
    if not doc:
        return await message.reply_text(
            f"❌ **{user.first_name}** has no stats yet. Play a match!",
            #parse_mode="markdown",
        )
    sr = round(doc["runs"] / doc["balls"] * 100, 2) if doc.get("balls", 0) > 0 else 0.00
    badges_list = [b["badge"] async for b in col_badges.find({"user_id": user.id})]

    await message.reply_text(
        f"<blockquote>📊 **{user.first_name}'s ᴄʀɪᴄᴋᴇᴛ ᴄᴀʀᴇᴇʀ**</blockquote>\n"
        f"<blockquote>🏏 **ʙᴀᴛᴛɪɴɢ**\n"
        f"  ᴍᴀᴛᴄʜᴇs: `{doc.get('matches',0)}`  ʜɪɢʜᴇsᴛ: `{doc.get('highest',0)}`\n"
        f"  ʀᴜɴs: `{doc.get('runs',0)}`  ʙᴀʟʟs: `{doc.get('balls',0)}`  sʀ: `{sr}`\n"
        f"  4s: `{doc.get('fours',0)}`  6s: `{doc.get('sixes',0)}`\n"
        f"  100s: `{doc.get('centuries',0)}`  50s: `{doc.get('fifties',0)}`  "
        f"ᴅᴜᴄᴋs: `{doc.get('ducks',0)}`</blockquote>\n"
        f"<blockquote>⚾ **ʙᴏᴡʟɪɴɢ**\n"
        f"  ᴡɪᴄᴋᴇᴛs: `{doc.get('wickets',0)}`  ʜᴀᴛ-ᴛʀɪᴄᴋs: `{doc.get('hattricks',0)}`\n\n"
        f"⭐ ᴍᴏᴛᴍ: `{doc.get('motm',0)}`  🏆 ᴛᴏᴜʀɴ ᴡɪɴs: `{doc.get('tourn_wins',0)}`\n"
        f"💰 ᴄᴏɪɴs: `{eco.get('coins',0) if eco else 0}`\n\n"
        f"🏅 **ʙᴀᴅɢᴇs:** {'  '.join(badges_list) or 'None yet'}</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketleaderboard") & (filters.group | filters.private))
async def cmd_leaderboard(_, message: Message):
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏏 ᴛᴏᴘ ʀᴜɴs",    callback_data="lb_runs"),
         InlineKeyboardButton("⚾ ᴛᴏᴘ ᴡɪᴄᴋᴇᴛs", callback_data="lb_wickets")],
        [InlineKeyboardButton("⚡ ᴛᴏᴘ sʀ",      callback_data="lb_sr"),
         InlineKeyboardButton("⭐ ᴍᴏsᴛ ᴍᴏᴛᴍ",   callback_data="lb_motm")],
        [InlineKeyboardButton("🏆 ᴛᴏᴜʀɴ. ᴡɪɴs", callback_data="lb_tourn")],
    ])
    await message.reply_text(
        "🏆 **Cricket Leaderboard** — Pick a category:",
        reply_markup=buttons,
    )


@Client.on_callback_query(filters.regex(r"^lb_"))
async def lb_callback(_, query: CallbackQuery):
    cat  = query.data
    info = {
        "lb_runs":    ("runs",       "🏏 ᴛᴏᴘ ʀᴜɴ sᴄᴏʀᴇʀs"),
        "lb_wickets": ("wickets",    "⚾ ᴛᴏᴘ ᴡɪᴄᴋᴇᴛ ᴛᴀᴋᴇʀs"),
        "lb_motm":    ("motm",       "⭐ ᴍᴏsᴛ ᴍᴏᴛᴍ ᴀᴡᴀʀᴅs"),
        "lb_tourn":   ("tourn_wins", "🏆 ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴄʜᴀᴍᴘɪᴏɴs"),
        "lb_sr":      ("runs",       "⚡ ᴛᴏᴘ sᴛʀɪᴋᴇ ʀᴀᴛᴇ"),
    }
    if cat not in info: return await query.answer()
    field, title = info[cat]

    cursor = (col_players.find({"balls": {"$gt": 10}}).sort(field, -1).limit(10)
              if cat == "lb_sr" else col_players.find({}).sort(field, -1).limit(10))

    text, pos, medals = f"🏆 **{title}**\n\n", 1, ["🥇", "🥈", "🥉"]
    async for doc in cursor:
        m   = medals[pos-1] if pos <= 3 else f"{pos}."
        uid = doc["user_id"]
        if cat == "lb_sr":
            v = round(doc["runs"] / doc["balls"] * 100, 1) if doc.get("balls", 0) else 0
            text += f"{m} `{uid}` — SR **{v}**\n"
        else:
            text += f"{m} `{uid}` — **{doc.get(field, 0)}** {field.replace('_',' ')}\n"
        pos += 1
    if pos == 1: text += "No data yet!"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏏 ʀᴜɴs",    callback_data="lb_runs"),
         InlineKeyboardButton("⚾ ᴡɪᴄᴋᴇᴛs", callback_data="lb_wickets")],
        [InlineKeyboardButton("⚡ sʀ",      callback_data="lb_sr"),
         InlineKeyboardButton("⭐ ᴍᴏᴛᴍ",    callback_data="lb_motm")],
        [InlineKeyboardButton("🏆 ᴛᴏᴜʀɴ.",  callback_data="lb_tourn")],
    ])
    try:
        await query.edit_message_text(text, reply_markup=buttons)
    except MessageNotModified:
        pass
    await query.answer()

# ============================================================
# 💰  COINS  &  BADGES
# ============================================================

@Client.on_message(filters.command("cricketcoins") & (filters.group | filters.private))
async def cmd_cricketcoins(_, message: Message):
    user = message.from_user
    await _ensure_economy(user.id)
    eco   = await col_economy.find_one({"user_id": user.id})
    coins = eco.get("coins", 0) if eco else 0
    await message.reply_text(
        f"<blockquote>💰 **{user.first_name}'s ᴄᴏɪɴs**\n\n🪙 ʙᴀʟᴀɴᴄᴇ: **{coins}**</blockquote>\n"
        f"<blockquote>_ᴇᴀʀɴ ʙʏ ᴡɪɴɴɪɴɢ, ᴍᴏᴛᴍ, sɪxᴇs & ᴛᴏᴜʀɴᴀᴍᴇɴᴛs!_</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketbadges") & (filters.group | filters.private))
async def cmd_cricketbadges(_, message: Message):
    user = message.from_user
    lst  = [b["badge"] async for b in col_badges.find({"user_id": user.id})]
    if not lst:
        return await message.reply_text(
            f"<blockquote>🏅 **{user.first_name}** — ɴᴏ ʙᴀᴅɢᴇs ʏᴇᴛ. ᴘʟᴀʏ ᴍᴀᴛᴄʜᴇs ᴛᴏ ᴇᴀʀɴ!</blockquote>",
            #parse_mode="markdown",
        )
    await message.reply_text(
        f"🏅 **{user.first_name}'s ʙᴀᴅɢᴇs** ({len(lst)})\n" + "\n".join(f"  {b}" for b in lst),
        #parse_mode="markdown",
    )

# ============================================================
# 🎯  DAILY MISSIONS SYSTEM
# ============================================================

MISSION_POOL: List[tuple] = [
    ("Score Runs",    30,  40), ("Hit Sixes",       3,  50),
    ("Play Matches",   2,  30), ("Take Wickets",     2,  60),
    ("Hit Boundaries", 5,  45), ("Score Runs",      50,  70),
    ("Hit Sixes",      5,  80), ("Play Matches",     3,  50),
    ("Hit Boundaries",10,  65),
]


async def _generate_daily_missions(user_id: int) -> None:
    today = str(datetime.date.today())
    if await col_missions.find_one({"user_id": user_id, "date": today}):
        return
    selected = random.sample(MISSION_POOL, 3)
    await col_missions.insert_many([
        {"user_id": user_id, "mission": n, "progress": 0,
         "target": t, "reward": r, "date": today, "completed": False}
        for n, t, r in selected
    ])


async def _update_mission(user_id: int, mission_type: str, amount: int = 1) -> None:
    today = str(datetime.date.today())
    async for m in col_missions.find(
        {"user_id": user_id, "mission": mission_type, "date": today, "completed": False}
    ):
        new_prog  = m["progress"] + amount
        completed = new_prog >= m["target"]
        await col_missions.update_one(
            {"_id": m["_id"]},
            {"$set": {"progress": new_prog, "completed": completed}},
        )
        if completed:
            await _add_coins(user_id, m["reward"])


@Client.on_message(filters.command("cricketmissions") & (filters.group | filters.private))
async def cmd_cricketmissions(_, message: Message):
    user  = message.from_user
    today = str(datetime.date.today())
    await _generate_daily_missions(user.id)
    text  = f"<blockquote>🎯 **ᴅᴀɪʟʏ ᴍɪssɪᴏɴs** — {today}</blockquote>\n"
    found = False
    async for m in col_missions.find({"user_id": user.id, "date": today}):
        found = True
        prog, tgt, rew = m["progress"], m["target"], m["reward"]
        if m["completed"]:
            status = "<blockquote>✅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</blockquote>"
        else:
            filled = int(prog / tgt * 10)
            bar    = "█" * filled + "░" * (10 - filled)
            status = f"{prog}/{tgt}  [{bar}]"
        text += f"<blockquote>🏏 **{m['mission']}**\n{status}\n💰 ʀᴇᴡᴀʀᴅ: {rew} coins</blockquote>\n"
    if not found: text += "<; blockquote>ᴄᴏᴜʟᴅ ɴᴏᴛ ɢᴇɴᴇʀᴀᴛᴇ ᴍɪssɪᴏɴs. ᴛʀʏ ᴀɢᴀɪɴ.</blockquote>"
    text += "<blockquote>_ʀᴇsᴇᴛs ᴅᴀɪʟʏ ᴀᴛ ᴍɪᴅɴɪɢʜᴛ!_</blockquote>"
    await message.reply_text(text)

# ============================================================
# 👥  TEAM PLAY SYSTEM
# ============================================================

@Client.on_message(filters.command("cricketgame") & filters.group)
async def cmd_cricketgame(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat in team_games and team_games[chat].get("started"):
        return await message.reply_text("❌ ᴛᴇᴀᴍ ᴍᴀᴛᴄʜ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!")
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎙️ ɪ'ᴍ ᴛʜᴇ ʜᴏsᴛ", callback_data=f"teamhost_{user.id}_{chat}")],
    ])
    await message.reply_text(
        "<blockquote>🏏 **ᴛᴇᴀᴍ ᴍᴀᴛᴄʜ sᴇᴛᴜᴘ**</blockquote>\n<<blockquote>ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ɪғ ʏᴏᴜ ᴀʀᴇ ᴛʜᴇ ʜᴏsᴛ:</blockquote>",
        reply_markup=buttons,
    )


@Client.on_callback_query(filters.regex(r"^teamhost_"))
async def cb_team_host(_, query: CallbackQuery):
    parts   = query.data.split("_")
    host_id = int(parts[1])
    chat_id = int(parts[2])
    if query.from_user.id != host_id:
        return await query.answer("❌ ᴏɴʟʏ ᴛʜᴇ ʜᴏsᴛ!", show_alert=True)
    team_games[chat_id] = {
        "host": host_id, "host_name": query.from_user.first_name,
        "team_a": [], "team_b": [], "player_names": {host_id: query.from_user.first_name},
        "started": False, "spam_free": False, "overs": 5, "innings": 1,
        "innings1_runs": 0, "innings1_wickets": 0, "innings1_balls": 0,
        "innings2_runs": 0, "innings2_wickets": 0, "innings2_balls": 0,
        "target": None, "batting_team": "A", "bowling_team": "B",
        "current_batter": None, "current_bowler": None,
        "ball_count": 0, "bat_index": 0, "bowl_index": 0,
        "scores":        defaultdict(int),
        "balls_faced":   defaultdict(int),
        "fours_hit":     defaultdict(int),
        "sixes_hit":     defaultdict(int),
        "wickets_taken": defaultdict(int),
    }
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 ɴᴏʀᴍᴀʟ",    callback_data=f"tmode_normal_{chat_id}"),
         InlineKeyboardButton("🚫 sᴘᴀᴍ-ғʀᴇᴇ", callback_data=f"tmode_spamfree_{chat_id}")],
    ])
    await query.edit_message_text("<blockquote>⚙️ **sᴇʟᴇᴄᴛ ɢᴀᴍᴇ ᴍᴏᴅᴇ:**</blockquote>", reply_markup=buttons)
    await query.answer()


@Client.on_callback_query(filters.regex(r"^tmode_"))
async def cb_team_mode(_, query: CallbackQuery):
    parts   = query.data.split("_")
    mode    = parts[1]
    chat_id = int(parts[2])
    if chat_id not in team_games:
        return await query.answer("Session expired.", show_alert=True)
    game = team_games[chat_id]
    if query.from_user.id != game["host"]:
        return await query.answer("❌ ᴏɴʟʏ ʜᴏsᴛ!", show_alert=True)
    game["spam_free"] = (mode == "spamfree")
    mode_str = "🚫 sᴘᴀᴍ-ғʀᴇᴇ" if game["spam_free"] else "🎯 ɴᴏʀᴍᴀʟ"
    await query.edit_message_text(
        f"<blockquote>✅ ᴍᴏᴅᴇ: **{mode_str}**</blockquote>\n<blockquote>`/cricketcreateteam` → ᴊᴏɪɴ → `/cricketstartteam`</blockquote>",
        #parse_mode="markdown",
    )
    await query.answer()


@Client.on_message(filters.command("cricketcreateteam") & filters.group)
async def cmd_create_teams(_, message: Message):
    chat = message.chat.id
    if chat not in team_games:
        return await message.reply_text("❌ ᴜsᴇ `/cricketgame` ғɪʀsᴛ.")
    await message.reply_text(
        "<blockquote>🏟️ **ᴛᴇᴀᴍs ᴄʀᴇᴀᴛᴇᴅ!**</blockquote>\n"
        "<blockquote>• `/cricketjoinAteam` — ᴛᴇᴀᴍ ᴀ 🔴\n"
        "• `/cricketjoinBteam` — ᴛᴇᴀᴍ ʙ 🔵\n"
        "• `/setovers [n]` — sᴇᴛ ᴏᴠᴇʀs\n"
        "• `/cricketstartteam` — sᴛᴀʀᴛ!</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketjoinAteam") & filters.group)
async def cmd_join_a(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in team_games:
        return await message.reply_text("❌ ɴᴏ ᴛᴇᴀᴍ ɢᴀᴍᴇ.")
    g = team_games[chat]
    if user.id in g["team_a"] or user.id in g["team_b"]:
        return await message.reply_text("ℹ️ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀ ᴛᴇᴀᴍ!")
    g["team_a"].append(user.id)
    g["player_names"][user.id] = user.first_name
    await message.reply_text(
        f"<blockquote.✅ **{user.first_name}** → ᴛᴇᴀᴍ ᴀ 🔴 ({len(g['team_a'])} ᴘʟᴀʏᴇʀs)</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketjoinBteam") & filters.group)
async def cmd_join_b(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in team_games:
        return await message.reply_text("❌ ɴᴏ ᴛᴇᴀᴍ ɢᴀᴍᴇ.")
    g = team_games[chat]
    if user.id in g["team_a"] or user.id in g["team_b"]:
        return await message.reply_text("ℹ️ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀ ᴛᴇᴀᴍ!")
    g["team_b"].append(user.id)
    g["player_names"][user.id] = user.first_name
    await message.reply_text(
        f"<blockquote>✅ **{user.first_name}** → ᴛᴇᴀᴍ ʙ 🔵 ({len(g['team_b'])} ᴘʟᴀʏᴇʀs)</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("addcricket") & filters.group)
async def cmd_addcricket(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in team_games:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴇᴀᴍ ɢᴀᴍᴇ.")
    g = team_games[chat]
    if g["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ host/ᴀᴅᴍɪɴ.")
    args = message.command
    if len(args) < 3:
        return await message.reply_text("ᴜsᴀɢᴇ: `/addcricket [ᴀ/ʙ] [@ᴜsᴇʀ]`")
    team = args[1].upper()
    if message.entities:
        for ent in message.entities:
            if ent.type == "mention":
                mention = message.text[ent.offset:ent.offset + ent.length]
                return await message.reply_text(f"✅ ᴀᴅᴅᴇᴅ {mention} ᴛᴏ ᴛᴇᴀᴍ {team}.")
    await message.reply_text("❌ ᴘʟᴇᴀsᴇ @ᴍᴇɴᴛɪᴏɴ ᴛʜᴇ ᴜsᴇʀ.")


@Client.on_message(filters.command("removecricketplayer") & filters.group)
async def cmd_remove_player(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in team_games:
        return await message.reply_text("<blockquote>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴇᴀᴍ ɢᴀᴍᴇ.</blockquote>")
    if team_games[chat]["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("<blockquote>❌ ᴏɴʟʏ ʜᴏsᴛ/admin.</blockquote>")
    await message.reply_text("<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴘʟᴀʏᴇʀ's ᴍᴇssᴀɢᴇ: `/removecricketplayer @ᴜsᴇʀɴᴀᴍᴇ`.</blockquote>")


@Client.on_message(filters.command("cricketteams") & filters.group)
async def cmd_show_teams(_, message: Message):
    chat = message.chat.id
    if chat not in team_games:
        return await message.reply_text("<blockquote>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴇᴀᴍ ɢᴀᴍᴇ.</blockquote>")
    g = team_games[chat]
    a = [g["player_names"].get(p, str(p)) for p in g["team_a"]]
    b = [g["player_names"].get(p, str(p)) for p in g["team_b"]]
    await message.reply_text(
        f"🏟️ **ᴛᴇᴀᴍ ʀᴏsᴛᴇʀs**<blockquote>\n🔴 ᴛᴇᴀᴍ ᴀ ({len(a)})\n" +
        ("\n".join(f"  • {n}" for n in a) or "  (empty)") +
        f"\n\n🔵 ᴛᴇᴀᴍ ʙ ({len(b)})\n" +
        ("\n".join(f"  • {n}" for n in b) or "  (empty)"),
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("cricketstartteam") & filters.group)
async def cmd_start_team(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in team_games:
        return await message.reply_text("❌ ɴᴏ ᴛᴇᴀᴍ ɢᴀᴍᴇ. ᴜsᴇ `/cricketgame`.")
    g = team_games[chat]
    if g["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ.")
    if not g["team_a"] or not g["team_b"]:
        return await message.reply_text("❌ ᴇᴀᴄʜ ᴛᴇᴀᴍ ɴᴇᴇᴅs ≥1 ᴘʟᴀʏᴇʀ!")
    g["started"]        = True
    g["current_batter"] = g["team_a"][0]
    g["current_bowler"] = g["team_b"][0]
    bn  = g["player_names"][g["current_batter"]]
    bon = g["player_names"][g["current_bowler"]]

    # Bowling video first
    await _send_video(
        chat, "bowling",
        f"<blockquote.🎯 **{bon}** — sᴇɴᴅ ʏᴏᴜʀ ʙᴏᴡʟɪɴɢ ɴᴜᴍʙᴇʀ ᴠɪᴀ **ʙᴏᴛ ᴘᴍ**!\n⏳ 1ᴍɪɴ</blockquote>",
    )
    await asyncio.sleep(1)
    # Batting video
    await _send_video(
        chat, "batting",
        f"<blockquote>🏏 **ᴛᴇᴀᴍ ᴍᴀᴛᴄʜ sᴛᴀʀᴛᴇᴅ!**</blockquote>\n<blockquote.🔴 **ᴛᴇᴀᴍ ᴀ** ʙᴀᴛs ғɪʀsᴛ!\n"
        f"🏏 ɴᴏᴡ ʙᴀᴛᴛᴇʀ: **{bn}** ᴄᴀɴ sᴇɴᴅ **(1–6)!!**\n"
        f"🎯 ʙᴏᴡʟᴇʀ: **{bon}** (ᴘᴍ ɴᴜᴍʙᴇʀ ғɪʀsᴛ!)\n⏱️ ᴏᴠᴇʀs: {g['overs']}</blockquote>",
    )


async def _process_team_ball(message: Message, game: dict, chat_id: int,
                              user, bat: int, bowl: int):
    batter_id   = user.id
    bowler_id   = game["current_bowler"]
    batter_name = game["player_names"][batter_id]
    bowler_name = game["player_names"][bowler_id]
    inning      = game["innings"]
    game["ball_count"]             += 1
    game[f"innings{inning}_balls"] += 1
    over_str = _fmt_overs(game["ball_count"])

    if bat == bowl:
        game[f"innings{inning}_wickets"] += 1
        game["balls_faced"][batter_id]   += 1
        game["wickets_taken"][bowler_id] += 1
        comment = random.choice(COMMENTARY_OUT)

        await _send_video_reply(
            message, "wicket",
            f"<blockquote.🏏 **{batter_name}** ➜ `{bat}`  |  🎯 **{bowler_name}** ➜ `{bowl}`</blockquote>\n"
            f"<blockquote>{comment}\n"
            f"❌ **ɴᴜᴍʙᴇʀ ᴍᴀᴛᴄʜᴇs, {batter_name}!**\n\n"
            f"sᴄᴏʀᴇ: {game[f'innings{inning}_runs']}/{game[f'innings{inning}_wickets']} "
            f"| `{over_str}/{game['overs']}`</blockquote>",
        )
        _rotate_team_batter(game)

    else:
        runs = bat
        game[f"innings{inning}_runs"]  += runs
        game["scores"][batter_id]      += runs
        game["balls_faced"][batter_id] += 1
        if runs == 4: game["fours_hit"][batter_id] += 1
        if runs == 6: game["sixes_hit"][batter_id] += 1

        if inning == 2 and game["innings2_runs"] >= game["target"]:
            await _send_video_reply(
                message, RUN_ASSET.get(runs, "batting"),
                f"<blockquote.🏏 {batter_name} ➜ `{bat}`  |  🎯 {bowler_name} ➜ `{bowl}`</blockquote>\n"
                f"<blockquote>🎆 **{runs} ʀᴜɴs! ᴛᴀʀɢᴇᴛ ᴄʜᴀsᴇᴅ!**\n🏆 **ᴛᴇᴀᴍ ʙ ᴡɪɴs!**</blockquote>",
            )
            return await _finish_team_match(message, game, chat_id)

        comment = random.choice(COMMENTARY_RUNS.get(runs, ["✅ sʜᴏᴛ!"]))
        await _send_video_reply(
            message, RUN_ASSET.get(runs, "batting"),
            f"<blockquote>🏏 **{batter_name}** ➜ `{bat}`  |  🎯 **{bowler_name}** ➜ `{bowl}`</blockquote>\n"
            f"<blockquote>{comment}\n✅ **{runs} Run{'s' if runs!=1 else ''}!**\n\n"
            f"Score: {game[f'innings{inning}_runs']}/{game[f'innings{inning}_wickets']} "
            f"| `{over_str}/{game['overs']}`</blockquote>",
        )
        if game["ball_count"] % 6 == 0:
            await app.send_message(
                chat_id,
                f"<blockquote>🔔 **ᴏᴠᴇʀ {game['ball_count']//6} ᴄᴏᴍᴘʟᴇᴛᴇ!**</blockquote>",
                #parse_mode="markdown",
            )

    # End of innings?
    if game["ball_count"] >= game["overs"] * 6:
        if inning == 1:
            target = game["innings1_runs"] + 1
            game.update({
                "innings": 2, "target": target, "ball_count": 0,
                "batting_team": "B", "bowling_team": "A",
                "current_batter": game["team_b"][0],
                "current_bowler": game["team_a"][0],
                "bat_index": 0, "bowl_index": 0,
            })
            bn  = game["player_names"][game["current_batter"]]
            bon = game["player_names"][game["current_bowler"]]
            await app.send_message(
                chat_id,
                f"<blockquote>🔁 **ɪɴɴɪɴɢs ʙʀᴇᴀᴋ!**</blockquote>\n"
                f"<blockquote>🔴 ᴛᴇᴀᴍ ᴀ: **{game['innings1_runs']}/{game['innings1_wickets']}**\n"
                f"🎯 ᴛᴀʀɢᴇᴛ ғᴏʀ ᴛᴇᴀᴍ ʙ: **{target}**</blockquote>",
                #parse_mode="markdown",
            )
            await asyncio.sleep(1)
            await _send_video(chat_id, "bowling",
                              f"<blockquote>🎯 **{bon}** — sᴇɴᴅ ᴘᴍ ɴᴜᴍʙᴇʀ!\n⏳ 1ᴍɪɴ</blockquote>")
            await asyncio.sleep(1)
            await _send_video(chat_id, "batting",
                              f"<blockquote>🔵 ᴛᴇᴀᴍ ʙ ʙᴀᴛs!\n🏏 ɴᴏᴡ ʙᴀᴛᴛᴇʀ: **{bn}** ᴄᴀɴ sᴇɴᴅ **(1–6)!!**</blockquote>")
        else:
            await _finish_team_match(message, game, chat_id)
        return

    # Next ball videos
    await asyncio.sleep(1)
    nb  = game["player_names"].get(game["current_batter"], "?")
    nbo = game["player_names"].get(game["current_bowler"], "?")
    await _send_video(chat_id, "bowling",
                      f"<blockquote>🎯 **{nbo}** — sᴇɴᴅ ʏᴏᴜʀ ɴᴜᴍʙᴇʀ ᴠɪᴀ ᴘᴍ!\n⏳ 1ᴍɪɴ</blockquote>")
    await asyncio.sleep(1)
    await _send_video(chat_id, "batting",
                      f"<blockquote>🏏 ɴᴏᴡ ʙᴀᴛᴛᴇʀ: **{nb}** ᴄᴀɴ sᴇɴᴅ **(1–6)!!**</blockquote>")


def _rotate_team_batter(game: dict) -> None:
    team = game["team_a"] if game["batting_team"] == "A" else game["team_b"]
    idx  = (game.get("bat_index", 0) + 1) % len(team)
    game["bat_index"]      = idx
    game["current_batter"] = team[idx]


async def _finish_team_match(message: Message, game: dict, chat_id: int) -> None:
    t1, w1 = game["innings1_runs"], game["innings1_wickets"]
    t2, w2 = game["innings2_runs"], game["innings2_wickets"]
    target = game.get("target", t1 + 1)

    if t2 >= target:
        winner_label, margin = "🔵 ᴛᴇᴀᴍ ʙ", f"by {10 - w2} ᴡɪᴄᴋᴇᴛs"
    else:
        winner_label, margin = "🔴 ᴛᴇᴀᴍ ᴀ", f"by {t1 - t2} ʀᴜɴs"

    motm_id   = _calc_motm_team(game)
    motm_name = game["player_names"].get(motm_id, "N/A") if motm_id else "N/A"
    all_p     = game["team_a"] + game["team_b"]
    top5      = sorted(all_p, key=lambda p: game["scores"].get(p, 0), reverse=True)[:5]
    top_lines = "\n".join(
        f"  🏏 {game['player_names'].get(p,'?')}: {game['scores'].get(p,0)} ({game['balls_faced'].get(p,0)}b)"
        for p in top5
    )
    await app.send_message(
        chat_id,
        f"<blockquote>🏁 **ᴍᴀᴛᴄʜ ғɪɴɪsʜᴇᴅ!**</blockquote>\n"
        f"<blockquote>🔴 ᴛᴇᴀᴍ ᴀ: {t1}/{w1}  |  🔵 ᴛᴇᴀᴍ ʙ: {t2}/{w2}</blockquote>\n"
        f"<blockquote>🏆 **ᴡɪɴɴᴇʀ: {winner_label}** ({margin})\n"
        f"⭐ **ᴍᴏᴛᴍ: {motm_name}**</blockquote>\n"
        f"<blockquote>**ᴛᴏᴘ sᴄᴏʀᴇʀs:**\n{top_lines}</blockquote>",
        #parse_mode="markdown",
    )
    del team_games[chat_id]


def _calc_motm_team(game: dict) -> Optional[int]:
    best, motm = -1, None
    for pid in game["team_a"] + game["team_b"]:
        r  = game["scores"].get(pid, 0)
        b  = game["balls_faced"].get(pid, 0)
        sr = r / b * 100 if b else 0
        pts = r + game["fours_hit"].get(pid, 0) + game["sixes_hit"].get(pid, 0) * 2
        pts += game["wickets_taken"].get(pid, 0) * 25
        if sr > 100:  pts += 10
        if r >= 100:  pts += 35
        elif r >= 50: pts += 15
        if pts > best: best, motm = pts, pid
    return motm


@Client.on_message(filters.command("cricketscore") & filters.group)
async def cmd_team_score(_, message: Message):
    chat = message.chat.id
    if chat not in team_games:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴇᴀᴍ ɢᴀᴍᴇ.")
    g   = team_games[chat]
    if not g.get("started"):
        return await message.reply_text("⏳ ɴᴏᴛ sᴛᴀʀᴛᴇᴅ ʏᴇᴛ.")
    inn  = g.get("innings", 1)
    text = (
        f"<blockquote>📊 **ʟɪᴠᴇ sᴄᴏʀᴇ — ɪɴɴɪɴɢs {inn}**</blockquote>\n"
        f"<blockquote>sᴄᴏʀᴇ: **{g[f'innings{inn}_runs']}/{g[f'innings{inn}_wickets']}**\n"
        f"ᴏᴠᴇʀs: **{_fmt_overs(g['ball_count'])}/{g['overs']}**</blockquote>"
    )
    if g.get("target"):
        text += f"\nᴛᴀʀɢᴇᴛ: {g['target']} | ɴᴇᴇᴅ: {g['target'] - g[f'innings{inn}_runs']}"
    await message.reply_text(text)


@Client.on_message(filters.command("endcricket") & filters.group)
async def cmd_end_team(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in team_games:
        return await message.reply_text("<blockquote>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴇᴀᴍ ɢᴀᴍᴇ.</blockquote>")
    if team_games[chat]["host"] != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ/admin.")
    del team_games[chat]
    await message.reply_text("<blockquote>🛑 **ᴛᴇᴀᴍ ᴍᴀᴛᴄʜ ᴇɴᴅᴇᴅ.**</blockquote>")


@Client.on_message(filters.command(["batting", "bowling"]) & filters.group)
async def cmd_captain(_, message: Message):
    cmd  = message.command[0]
    args = message.command
    role = "Batter" if cmd == "batting" else "Bowler"
    if len(args) < 2:
        return await message.reply_text(f"<blockquote>ᴜsᴀɢᴇ: `/{cmd} [@username]`</blockquote>")
    await message.reply_text(f"<blockquote>✅ **{role}** sᴇᴛ ᴛᴏ **{args[1]}**.</blockquote>")

# ============================================================
# 🏆  TOURNAMENT MODE — Full Auto-Knockout Engine
# ============================================================

@Client.on_message(filters.command("crickettournament") & filters.group)
async def cmd_crickettournament(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat in tournaments:
        return await message.reply_text("<blockquote>⚠️ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴇxɪsᴛs! ᴜsᴇ `/endcrickettourn` ᴛᴏ ᴄᴀɴᴄᴇʟ.</blockquote>")
    t = Tournament(chat, user.id)
    t.players.append(user.id)
    t.player_names[user.id] = user.first_name
    tournaments[chat] = t
    await message.reply_text(
        f"<blockquote>🏆 **ᴄʀɪᴄᴋᴇᴛ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴄʀᴇᴀᴛᴇᴅ!**</blockquote>\n"
        f"<blockquote>👑 ʜᴏsᴛ: **{user.first_name}**\n\n"
        f"📢 `/joincrickettourn` — ᴊᴏɪɴ\n"
        f"⚙️ `/settournamentovers [n]` — sᴇᴛ ᴏᴠᴇʀs\n"
        f"🚀 `/startcrickettournament` (ᴍɪɴ 4)\n\n"
        f"🥇 ᴄʜᴀᴍᴘɪᴏɴ → +200 ᴄᴏɪɴs + ʙᴀᴅɢᴇ\n"
        f"🥈 ʀᴜɴɴᴇʀ-ᴜᴘ → +100 ᴄᴏɪɴs\n"
        f"🥉 sᴇᴍɪ-ғɪɴᴀʟɪsᴛs → +50 ᴄᴏɪɴs</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("joincrickettourn") & filters.group)
async def cmd_jointourn(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in tournaments:
        return await message.reply_text("<blockquote>❌ ɴᴏ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ.</blockquote>")
    t = tournaments[chat]
    if t.started:
        return await message.reply_text("<blockquote>❌ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ!</blockquote>")
    if user.id in t.players:
        return await message.reply_text("<blockquote>ℹ️ ᴀʟʀᴇᴀᴅʏ ʀᴇɢɪsᴛᴇʀᴇᴅ!</blockquote>")
    t.players.append(user.id)
    t.player_names[user.id] = user.first_name
    await message.reply_text(
        f"<blockquote>✅ **{user.first_name}** ᴇɴᴛᴇʀᴇᴅ! ʀᴇɢɪsᴛᴇʀᴇᴅ: **{len(t.players)}**</blockquote>",
        #parse_mode="markdown",
    )


@Client.on_message(filters.command("settournamentovers") & filters.group)
async def cmd_tourn_overs(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in tournaments:
        return await message.reply_text("<blockquote>❌ ɴᴏ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ.</blockquote>")
    t = tournaments[chat]
    if t.host != user.id and user.id not in SUDOERS:
        return await message.reply_text("<blockquote>❌ ᴏɴʟʏ ʜᴏsᴛ.</blockquote>")
    args = message.command
    if len(args) < 2 or not args[1].isdigit():
        return await message.reply_text("<blockquote>ᴜsᴀɢᴇ: `/settournamentovers [1-20]`</blockquote>")
    t.overs = max(1, min(20, int(args[1])))
    await message.reply_text(f"<blockquote>⚙️ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴏᴠᴇʀs: **{t.overs}**</blockquote>")


@Client.on_message(filters.command("startcrickettournament") & filters.group)
async def cmd_starttourn(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in tournaments:
        return await message.reply_text("<blockquote>❌ ɴᴏ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ.</blockquote>")
    t = tournaments[chat]
    if t.host != user.id and user.id not in SUDOERS:
        return await message.reply_text("<blockquote>❌ ᴏɴʟʏ ʜᴏsᴛ.</blockquote>")
    if t.started:
        return await message.reply_text("<blockquote>❌ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ!</blockquote>")
    if len(t.players) < 4:
        return await message.reply_text(
            f"<blockquote>❌ ɴᴇᴇᴅ **4+ ᴘʟᴀʏᴇʀs** (have {len(t.players)}).</blockquote>"
        )
    players: List[Optional[int]] = list(t.players)
    random.shuffle(players)
    if len(players) % 2 != 0:
        players.append(None)
    t.started    = True
    t.round_name = _get_round_name(len(t.players))
    t.matches    = _create_tourn_matches(players)
    await message.reply_text(_format_bracket(t))
    await asyncio.sleep(2)
    await _start_next_tourn_match(chat)


@Client.on_message(filters.command("tournamentstatus") & filters.group)
async def cmd_tourn_status(_, message: Message):
    chat = message.chat.id
    if chat not in tournaments:
        return await message.reply_text("❌ No active tournament.")
    t    = tournaments[chat]
    text = f"🏆 **{t.round_name} — ʟɪᴠᴇ ʙʀᴀᴄᴋᴇᴛ**\n\nᴘʟᴀʏᴇʀs: {len(t.players)} | ᴏᴠᴇʀs: {t.overs}\n"
    for m in t.matches:
        p1n = t.player_names.get(m.player1, str(m.player1)) if m.player1 else "🟡 ʙʏᴇ"
        p2n = t.player_names.get(m.player2, str(m.player2)) if m.player2 else "🟡 ʙʏᴇ"
        if m.winner is None:
            status = "⏳ ᴘᴇɴᴅɪɴɢ" if not m.started else "🏏 ɪɴ-ᴘʀᴏɢʀᴇss"
        else:
            wn = t.player_names.get(m.winner, str(m.winner))
            status = f"✅ {wn} won"
        text += f"  ⚔️ ᴍᴀᴛᴄʜ {m.match_num}: **{p1n}** 🆚 **{p2n}** — {status}\n"
    await message.reply_text(text)


@Client.on_message(filters.command("endcrickettourn") & filters.group)
async def cmd_end_tourn(_, message: Message):
    chat = message.chat.id
    user = message.from_user
    if chat not in tournaments:
        return await message.reply_text("❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ.")
    t = tournaments[chat]
    if t.host != user.id and user.id not in SUDOERS:
        return await message.reply_text("❌ ᴏɴʟʏ ʜᴏsᴛ/ᴀᴅᴍɪɴ.")
    if chat in solo_games and solo_games[chat].get("tournament_chat") == chat:
        del solo_games[chat]
    del tournaments[chat]
    await message.reply_text("<blockquote>🛑 **ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ.**</blockquote>")

# ─── Tournament Helpers ──────────────────────────────────────

def _format_bracket(t: Tournament) -> str:
    text = f"🏆 **{t.round_name} ʙʀᴀᴄᴋᴇᴛ**\n\n"
    for m in t.matches:
        p1n = t.player_names.get(m.player1, "?") if m.player1 else "🟡 BYE"
        p2n = t.player_names.get(m.player2, "?") if m.player2 else "🟡 BYE"
        text += f"  ⚔️ ᴍᴀᴛᴄʜ {m.match_num}: **{p1n}** 🆚 **{p2n}**\n"
    text += "\n🤖 Matches start automatically!"
    return text


async def _start_next_tourn_match(chat_id: int) -> None:
    if chat_id not in tournaments:
        return
    t = tournaments[chat_id]
    for match in t.matches:
        if match.started or match.winner is not None:
            continue
        # BYE
        if match.player1 is None or match.player2 is None:
            wid = match.player2 if match.player1 is None else match.player1
            match.winner = wid
            match.started = True
            wn = t.player_names.get(wid, str(wid))
            await app.send_message(
                chat_id,
                f"⏭️ **ᴍᴀᴛᴄʜ {match.match_num} — ʙʏᴇ**\n🟡 **{wn}** ᴀᴅᴠᴀɴᴄᴇs!",
                #parse_mode="markdown",
            )
            await asyncio.sleep(1)
            await _on_tournament_match_done(chat_id, wid)
            return

        match.started = True
        p1_id, p2_id  = match.player1, match.player2
        p1n = t.player_names.get(p1_id, str(p1_id))
        p2n = t.player_names.get(p2_id, str(p2_id))

        game = _new_solo_game(p1_id, p1n)
        game["players"]         = [p1_id, p2_id]
        game["player_names"]    = {p1_id: p1n, p2_id: p2n}
        game["overs"]           = t.overs
        game["spam_free"]       = t.spam_free
        game["tournament_chat"] = chat_id
        _launch_solo_game(game)
        solo_games[chat_id]     = game

        await app.send_message(
            chat_id,
            f"<blockquote>🏏 **ᴛᴏᴜʀɴᴀᴍᴇɴᴛ — ᴍᴀᴛᴄʜ {match.match_num} — {t.round_name}**</blockquote>\n"
            f"<blockquote>🔥 **{p1n}** 🆚 **{p2n}**  |  ⏱️ ᴏᴠᴇʀs: {t.overs}\n\n"
            f"ᴡɪɴɴᴇʀ ᴀᴅᴠᴀɴᴄᴇs ⚡</blockquote>",
            #parse_mode="markdown",
        )
        await asyncio.sleep(1)
        await _announce_ball_start(chat_id, game)
        return


async def _on_tournament_match_done(tourn_chat: int, winner_id: int) -> None:
    if tourn_chat not in tournaments:
        return
    t = tournaments[tourn_chat]
    for match in t.matches:
        if match.started and match.winner is None:
            if winner_id in [match.player1, match.player2]:
                match.winner = winner_id
                wn = t.player_names.get(winner_id, str(winner_id))
                await app.send_message(
                    tourn_chat,
                    f"🎉 **ᴍᴀᴛᴄʜ {match.match_num} ʀᴇsᴜʟᴛ!**\n🥇 **{wn}** ᴀᴅᴠᴀɴᴄᴇs!",
                    #parse_mode="markdown",
                )
                break
    await asyncio.sleep(1)
    if all(m.winner is not None for m in t.matches):
        winners = [m.winner for m in t.matches]
        await asyncio.sleep(2)
        await _advance_tournament_round(tourn_chat, winners)
    else:
        await asyncio.sleep(2)
        await _start_next_tourn_match(tourn_chat)


async def _advance_tournament_round(chat_id: int, winners: List[int]) -> None:
    if chat_id not in tournaments:
        return
    t = tournaments[chat_id]

    if len(winners) == 1:
        champ_id   = winners[0]
        champ_name = t.player_names.get(champ_id, str(champ_id))
        runner_id, runner_name = None, "N/A"
        if len(t.matches) == 1:
            loser = (t.matches[0].player1 if t.matches[0].player2 == champ_id
                     else t.matches[0].player2)
            runner_id   = loser
            runner_name = t.player_names.get(loser, str(loser)) if loser else "N/A"

        sf_names     = [t.player_names.get(p, str(p)) for p in t.semifinalists
                        if p not in [champ_id, runner_id]]
        reward_lines = [f"  🥇 **{champ_name}**: +200 ᴄᴏɪɴs + 🏆 ʙᴀᴅɢᴇ"]
        if runner_id: reward_lines.append(f"<blockquote> 🥈 **{runner_name}**: +100 ᴄᴏɪɴs</blockquote>")
        reward_lines += [f"  🥉 **{n}**: +50 ᴄᴏɪɴs" for n in sf_names]

        await app.send_message(
            chat_id,
            f"<blockquote>🎉🏆 **ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴄʜᴀᴍᴘɪᴏɴ!** 🏆🎉</blockquote>\n"
            f"<blockquote>👑 **{champ_name}** ɪs ᴛʜᴇ ᴄʜᴀᴍᴘɪᴏɴ!</blockquote>\n"
            f"<blockquote>🏅 **ʀᴇᴡᴀʀᴅs:**</blockquote>\n" + "\n".join(reward_lines),
            #parse_mode="markdown",
        )
        await _add_coins(champ_id, 200)
        await _ensure_player(champ_id)
        await col_players.update_one({"user_id": champ_id}, {"$inc": {"tourn_wins": 1}})
        await _maybe_award_badge(champ_id, True, "<blockquote>🏆 ᴛᴏᴜʀɴᴀᴍᴇɴᴛ ᴄʜᴀᴍᴘɪᴏɴ</blockquote>")
        await _check_badges(champ_id)
        if runner_id: await _add_coins(runner_id, 100)
        for sf_id in t.semifinalists:
            if sf_id not in [champ_id, runner_id]:
                await _add_coins(sf_id, 50)
        del tournaments[chat_id]
        return

    if len(winners) == 4:   t.semifinalists = list(winners)
    if len(winners) == 2:   t.round_name = "🏆 FINAL"
    elif len(winners) == 4: t.round_name = "🔥 Semi-Final"
    elif len(winners) >= 8: t.round_name = "⚡ Quarter-Final"
    else:                   t.round_name = "🎮 Next Round"

    if len(winners) % 2 != 0: winners.append(None)
    t.matches = _create_tourn_matches(winners)
    await app.send_message(chat_id, _format_bracket(t))
    await asyncio.sleep(2)
    await _start_next_tourn_match(chat_id)

# ============================================================
# 📌  HELP COMMAND
# ============================================================

@Client.on_message(filters.command("crickethelp") & (filters.group | filters.private))
async def cmd_cricket_help(_, message: Message):
    await message.reply_text(
        "<blockquote>🏏 **ᴄʀɪᴄᴋᴇᴛ ʙᴏᴛ — ғᴜʟʟ ᴄᴏᴍᴍᴀɴᴅ ʀᴇғᴇʀᴇɴᴄᴇ**</blockquote>\n"
        "<blockquote>ᴜsᴇ `/cricket` ɪɴ ᴀ ɢʀᴏᴜᴘ ғᴏʀ ᴛʜᴇ ғᴜʟʟ ᴍᴇɴᴜ!</blockquote>\n"
        "<blockquote>**🏏 sᴏʟᴏ ɢᴀᴍᴇ**\n"
        "`/solocricket` `/joincricket` `/startsolocricket`\n"
        "`/extendsolocricket [s]` `/setovers [n]` `/setspamfree`\n"
        "`/cricketsolo_status` `/cricketsoloscore` `/cricketsoloplayers`\n"
        "`/cricketsololeave` `/cricketmystatus` `/cricketendsolo`</blockquote>\n\n"
        "<blockquote>**👥 ᴛᴇᴀᴍ ɢᴀᴍᴇ**\n"
        "`/cricketgame` `/cricketcreateteam`\n"
        "`/cricketjoinAteam` `/cricketjoinBteam` `/cricketstartteam`\n"
        "`/addcricket [A/B] [@u]` `/removecricketplayer [@u]`\n"
        "`/cricketteams` `/cricketscore` `/endcricket`\n"
        "`/batting [@u]` `/bowling [@u]`</blockquote>\n\n"
        "<blockquote>**🏆 ᴛᴏᴜʀɴᴀᴍᴇɴᴛ**\n"
        "`/crickettournament` `/joincrickettourn`\n"
        "`/startcrickettournament` `/tournamentstatus`\n"
        "`/settournamentovers [n]` `/endcrickettourn`</blockquote>\n\n"
        "<blockquote>**📊 sᴛᴀᴛs & ᴇᴄᴏɴᴏᴍʏ**\n"
        "`/cricketuserinfo` `/cricketleaderboard`\n"
        "`/cricketcoins` `/cricketbadges` `/cricketmissions`</blockquote>\n\n"
        "<blockquote>🎬 **ᴠɪᴅᴇᴏ ʜɪɢʜʟɪɢʜᴛs ᴘʟᴀʏ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴇᴠᴇʀʏ ʙᴀʟʟ!**\n"
        "🎯 **ʙᴏᴡʟᴇʀs ᴀʟᴡᴀʏs ᴘᴍ ᴛʜᴇɪʀ ɴᴜᴍʙᴇʀ ᴛᴏ ᴘʀᴇᴠᴇɴᴛ ᴄʜᴇᴀᴛɪɴɢ!**</blockquote>",
        #parse_mode="markdown",
    )


__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_76"
__help__     = """
🔻 /crickethelp - ꜰᴜʟʟ ᴄᴏᴍᴍᴀɴᴅ ʟɪꜱᴛ
🔻 /cricket - ᴏᴘᴇɴ ᴄʀɪᴄᴋᴇᴛ ᴀʀᴇɴᴀ ᴍᴇɴᴜ
🔻 /solocricket - ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ꜱᴏʟᴏ ɢᴀᴍᴇ
"""

MOD_TYPE = "GAMES"
MOD_NAME = "Cricket-Game"
MOD_PRICE = "300"
