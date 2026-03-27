# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║         SHASHA_DRUGZ — UNO GAME MODULE (STICKER EDITION)                   ║
# ║  Reference: https://github.com/AmanoTeam/UnuRobot  (classic.json stickers) ║
# ║                                                                             ║
# ║  FIX SUMMARY:                                                               ║
# ║                                                                             ║
# ║  #1 GROUP ISOLATION — _player_chat is now a two-way lookup:                ║
# ║     uid → chat_id  AND  (chat_id, uid) presence check.                     ║
# ║     A player already in Group A cannot affect Group B.                     ║
# ║     Joining a new group auto-removes the old session cleanly.              ║
# ║                                                                             ║
# ║  #2 LOBBY JOIN LIST — Every join/leave updates the lobby message           ║
# ║     to show all current members as clickable mentions + total count.       ║
# ║                                                                             ║
# ║  #3 All original fixes preserved:                                           ║
# ║     Names via game["names"] + _mention()                                   ║
# ║     input_message_content on every sticker + group=-1                      ║
# ║     _cancel_timer() first in uno_chosen (no false timeout)                 ║
# ║     Card sorting 🔵→🟢→🔴→🟡→⚫                                          ║
# ║     is_personal=True on all query.answer() calls                           ║
# ║     "Play Your Card" button fills "@bot uno" in inline box                 ║
# ║     Duplicate played-card sticker removed                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
import random
import asyncio
from datetime import datetime, timezone
from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultCachedSticker,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from motor.motor_asyncio import AsyncIOMotorClient
from SHASHA_DRUGZ import app
from config import MONGO_DB_URI

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
TURN_TIMEOUT = 60      # seconds before auto-draw + skip
MISS_LIMIT   = 3       # consecutive timeouts → eliminated
MIN_PLAYERS  = 2

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────
_mongo    = AsyncIOMotorClient(MONGO_DB_URI)
_db       = _mongo["SHASHA_UNO"]
games_col = _db["games"]
stats_col = _db["stats"]
wins_log  = _db["wins_log"]

# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY CACHE
#
# FIX #1 — GROUP ISOLATION
# _player_chat maps  uid → chat_id
# We NEVER let a player be in two groups at once.
# On join, if uid already has a chat_id → remove from old group first.
# ─────────────────────────────────────────────────────────────────────────────
_player_chat: dict[int, int]          = {}   # uid → chat_id (current active game)
_turn_timers: dict[int, asyncio.Task] = {}   # chat_id → timer task
_lobby_msg:   dict[int, int]          = {}   # chat_id → message_id of lobby message

# ─────────────────────────────────────────────────────────────────────────────
# CARD CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
COLOR_ICONS = {"r": "🟥", "g": "🟩", "b": "🟦", "y": "🟨", "x": "❓"}
VALUE_ICONS = {
    "0": "0️⃣","1": "1️⃣","2": "2️⃣","3": "3️⃣","4": "4️⃣",
    "5": "5️⃣","6": "6️⃣","7": "7️⃣","8": "8️⃣","9": "9️⃣",
    "draw": "+2","skip": "🚫","reverse": "🔁",
    "colorchooser": "🌈","draw_four": "+4",
}

# ─────────────────────────────────────────────────────────────────────────────
# STICKER FILE-IDs  (classic theme)
# ─────────────────────────────────────────────────────────────────────────────
STICKERS: dict[str, str] = {
    "b_0":          "CAACAgQAAxkDAAI372NtY-V641fF6HhAA4Vuc6CbI_LeAALZAQACX1eZAAEqnpNt3SpG_ysE",
    "b_1":          "CAACAgQAAxkDAAI38GNtY-UvkNQN3h5p5n_dfNbhPV9HAALbAQACX1eZAAHluPl_BVzaDisE",
    "b_2":          "CAACAgQAAxkDAAI38WNtY-X4Gvnxt4mofZ-Uv_zmGWHRAALdAQACX1eZAAEFe5JBdpP-cysE",
    "b_3":          "CAACAgQAAxkDAAI38mNtY-av7Gm6hUEdRs_mONWGzKoGAALfAQACX1eZAAFQJXWHQ2D7uisE",
    "b_4":          "CAACAgQAAxkDAAI382NtY-YXxHbN1MfXSl6FbzwgWq5vAALhAQACX1eZAAHo1SP4devY_ysE",
    "b_5":          "CAACAgQAAxkDAAI39GNtY-dNEOn0i1luuPjPOHvqyasxAALjAQACX1eZAALf6g-FruzaKwQ",
    "b_6":          "CAACAgQAAxkDAAI39WNtY-df9ew41xXE6ARS3VHDKg0NAALlAQACX1eZAAHwMoU1Nb4OgisE",
    "b_7":          "CAACAgQAAxkDAAI39mNtY-ftENXWBUBNqNTomh-NeufNAALnAQACX1eZAAFOBAnoop1fWisE",
    "b_8":          "CAACAgQAAxkDAAI392NtY-idvjst_LSKlwP2cEDnS3WpAALpAQACX1eZAAHmKrizqjwJ3isE",
    "b_9":          "CAACAgQAAxkDAAI3-GNtY-jEw-hh0ei6OxSl2r4DehmIAALrAQACX1eZAAHvul-ZztVWiisE",
    "b_draw":       "CAACAgQAAxkDAAI3-WNtY-nrtJj_c48YtjbPwydARdwJAALtAQACX1eZAAGdURg9n6qvEysE",
    "b_skip":       "CAACAgQAAxkDAAI3-mNtY-kVI0dIVd38sOvZrZmtRCv_AALxAQACX1eZAAHAf0ks_Y82JysE",
    "b_reverse":    "CAACAgQAAxkDAAI3-2NtY-p4_EUUTVDYKX12SMcKA9IbAALvAQACX1eZAAFjAZc535XzNSsE",
    "g_0":          "CAACAgQAAxkDAAI3_GNtY-qvO3V8NwHojOpf8aIpbnYvAAL3AQACX1eZAAH7m-CsNWDzBSsE",
    "g_1":          "CAACAgQAAxkDAAI3_WNtY-r28bGOeJGKL7ZtEwUrWXzfAAL5AQACX1eZAAFVNSG--aqs9CsE",
    "g_2":          "CAACAgQAAxkDAAI3_mNtY-sjqfdB5nu7iKPFqHRItFerAAL7AQACX1eZAAHDX5Qn7VbSdCsE",
    "g_3":          "CAACAgQAAxkDAAI3_2NtY-ueCVLB_KL8Xz0itFJGWNbYAAL9AQACX1eZAAGwUxSSKSNPaisE",
    "g_4":          "CAACAgQAAxkDAAI4AAFjbWPsRRrrb0KdkF5SGCO87ni9sAAC_wEAAl9XmQABARICqk9L7OArBA",
    "g_5":          "CAACAgQAAxkDAAI4AWNtY-zlRyWdS69Z4bcwBgklRcBEAAIBAgACX1eZAAGN2wN5nVhf3ysE",
    "g_6":          "CAACAgQAAxkDAAI4AmNtY-zXK3F2NTz-XaFeDk2rsP7NAAIDAgACX1eZAAFaJA80kw1XfSsE",
    "g_7":          "CAACAgQAAxkDAAI4A2NtY-0dqOmBW9-XK_BbtXg0OLRaAAIFAgACX1eZAAGDbLTCiNGLBisE",
    "g_8":          "CAACAgQAAxkDAAI4BGNtY-2kF7oUCmvU_AbU9lmudtZqAAIHAgACX1eZAAGnWrRTRZj7gSsE",
    "g_9":          "CAACAgQAAxkDAAI4BWNtY-60BpqwiJQ8-p93unknqHi2AAIJAgACX1eZAAHODOPdhwzltysE",
    "g_draw":       "CAACAgQAAxkDAAI4BmNtY-53H6EJgbUQSeEpguubOevXAAILAgACX1eZAAFWg06uGplHVysE",
    "g_skip":       "CAACAgQAAxkDAAI4B2NtY-5VirooDDZAWu4ENrVBBoFHAAIPAgACX1eZAAHn-hBXxRvYQisE",
    "g_reverse":    "CAACAgQAAxkDAAI4CGNtY-_G8b0fBt0N3OBgx9CIwJziAAINAgACX1eZAAFMYqmCS3vfySsE",
    "r_0":          "CAACAgQAAxkDAAI4CWNtY-9LOKHb1FqCn3GmqxOYCo_fAAIRAgACX1eZAAHK9atgT_cu_isE",
    "r_1":          "CAACAgQAAxkDAAI4CmNtY_Dxb_ivl-VHFRDPgHVOilCVAAITAgACX1eZAAH_6pt2airFESsE",
    "r_2":          "CAACAgQAAxkDAAI4C2NtY_B9bP3cd73NvBd-Un8yZTYzAAIVAgACX1eZAAHQrmSSeMDfgCsE",
    "r_3":          "CAACAgQAAxkDAAI4DGNtY_Hqk5RPHjNn50jy_ImBPYZLAAIXAgACX1eZAAFeHWWPa-piRysE",
    "r_4":          "CAACAgQAAxkDAAI4DWNtY_HqY4wNkPulTWHIY9d2Fep-AAIZAgACX1eZAAE7VUWywkd3KCsE",
    "r_5":          "CAACAgQAAxkDAAI4DmNtY_Lb9j5Qi5RVPEaSW3uZWAnlAAIbAgACX1eZAAF1s0b9V-PUJCsE",
    "r_6":          "CAACAgQAAxkDAAI4D2NtY_Kklm1t7E0KShmWTbXEwnpNAAIdAgACX1eZAAF8hSz11exIUisE",
    "r_7":          "CAACAgQAAxkDAAI4EGNtY_LoR07j-LayjpoVlEPLCCe0AAIfAgACX1eZAAEVnCo1RKSqnCsE",
    "r_8":          "CAACAgQAAxkDAAI4EWNtY_OrIOu5PPIUTZ-cn0FBFcT2AAIhAgACX1eZAAEhXezQrbzKOisE",
    "r_9":          "CAACAgQAAxkDAAI4EmNtY_PI6uILsPHkkyIDFp4ivFBJAAIjAgACX1eZAAHN4GBkUaxpqisE",
    "r_draw":       "CAACAgQAAxkDAAI4E2NtY_SNrUaYiRbAIEi9c_X-veafAAIlAgACX1eZAAGZvG1zNp2cVisE",
    "r_skip":       "CAACAgQAAxkDAAI4FGNtY_SrNSCK9k9FO9Xji2fb9LJMAAIpAgACX1eZAAFprUDwYHBu3SsE",
    "r_reverse":    "CAACAgQAAxkDAAI4FWNtY_V41t8UX4XtxugfwVMibbqLAAInAgACX1eZAAGay7EvXnoVZisE",
    "y_0":          "CAACAgQAAxkDAAI4FmNtY_XYaAevT9wxGiAxI1n6e_spAAIrAgACX1eZAAG1mgAB2D5sIc8rBA",
    "y_1":          "CAACAgQAAxkDAAI4F2NtY_aD1zsrQYWtYoeePhDN1bcvAAItAgACX1eZAAHqNCCjuSEQjisE",
    "y_2":          "CAACAgQAAxkDAAI4GGNtY_Y9kN6nzxvk8KwX8SnwTntmAAIvAgACX1eZAAH4u547rBAiBCsE",
    "y_3":          "CAACAgQAAxkDAAI4GWNtY_dJwM67rmUFcLEtByedoFJdAAIxAgACX1eZAAFBQ00TMrpMeisE",
    "y_4":          "CAACAgQAAxkDAAI4GmNtY_d6JUufI61BWnqI4DTVRxMVAAIzAgACX1eZAAF7IOqIuGqyDSsE",
    "y_5":          "CAACAgQAAxkDAAI4G2NtY_dxij19aBCA7Tjf5ytWzXgNAAI1AgACX1eZAAHyIiYzI-E-LisE",
    "y_6":          "CAACAgQAAxkDAAI4HGNtY_hPQ2iuWWmADOUYR-P-nNVFAAI3AgACX1eZAAH_E8fuZ374hysE",
    "y_7":          "CAACAgQAAxkDAAI4HWNtY_jp9tXZ3lpAV83tzDcazcA4AAI5AgACX1eZAAHPK6qSI6Ku_CsE",
    "y_8":          "CAACAgQAAxkDAAI4HmNtY_kQwEGUW6F38bBIYXfspzarAAI7AgACX1eZAAHXiL4XwJi0eysE",
    "y_9":          "CAACAgQAAxkDAAI4H2NtY_kJ_ofl80XkaVobKpd-IgqQAAI9AgACX1eZAAGG_opl6vQSOCsE",
    "y_draw":       "CAACAgQAAxkDAAI4IGNtY_qbKj2mnuJVlTai4F6se8MNAAI_AgACX1eZAAFrjyuhcA2ksysE",
    "y_skip":       "CAACAgQAAxkDAAI4IWNtY_rKy-RTeKjfZT0RAYNNreVhAAJDAgACX1eZAAF1m63alvMoxysE",
    "y_reverse":    "CAACAgQAAxkDAAI4ImNtY_vaX0rQZ_5ZUeFTpMa2ZQABOwACQQIAAl9XmQABCHpDm7MPbakrBA",
    "draw_four":    "CAACAgQAAxkDAAI4I2NtY_vr1Fa4_Q2Y6dxOopNX7sSsAAL1AQACX1eZAAHXOgABZUCgVkkrBA",
    "colorchooser": "CAACAgQAAxkDAAI4JGNtY_vpncCbuHH2xDLokQWxUAXSAALzAQACX1eZAAHI5jbpFQE9bCsE",
    "option_draw":  "CAACAgQAAxkDAAI4JWNtY_zry4NT2JAlWjTryYiuec4nAAL4AgACX1eZAAH-TdXSlvEa2ysE",
    "option_pass":  "CAACAgQAAxkDAAI4JmNtY_yMlr6rB3UdTikR3zFCk8kVAAL6AgACX1eZAAFuilR5QnD-VysE",
}
STICKERS_GREY: dict[str, str] = {
    "b_0":          "CAACAgQAAxkDAAI4KWNtY_3SM2AGtecbGE8XDjlWvcKxAAJFAgACX1eZAAHwXYFNZhQaIysE",
    "b_1":          "CAACAgQAAxkDAAI4KmNtY_7zNsvijvvGZAJmuxcYVgizAAJHAgACX1eZAAF_ZxC64wgdNCsE",
    "b_2":          "CAACAgQAAxkDAAI4K2NtY_4z7XEHPzcliqJth5G3ds6vAAJJAgACX1eZAAF-GuNgJ25IAAErBA",
    "b_3":          "CAACAgQAAxkDAAI4LGNtY_9ZPE9nPCPJQ0Rjf_zOkTsiAAJLAgACX1eZAAHIJQ71XJ39mCsE",
    "b_4":          "CAACAgQAAxkDAAI4LWNtY_--OWOFczobsp10PPj5p9pZAAJNAgACX1eZAAEjmR2mhJ8SsSsE",
    "b_5":          "CAACAgQAAxkDAAI4LmNtZAABTkAAAT7kcgxZkdA3rcZmxM0AAk8CAAJfV5kAASN8DC8z_yexKwQ",
    "b_6":          "CAACAgQAAxkDAAI4L2NtZAABOSkvi7YF9opHBHILrQukJwACUQIAAl9XmQABv35eqFpp188rBA",
    "b_7":          "CAACAgQAAxkDAAI4MGNtZAABcb94kfODfzBiW7R6caIITgACUwIAAl9XmQABv8VaivrtncwrBA",
    "b_8":          "CAACAgQAAxkDAAI4MWNtZAEPZcxI8yZZJ7mtvLEhRyQyAAJVAgACX1eZAAF8hUb4bS_NdCsE",
    "b_9":          "CAACAgQAAxkDAAI4MmNtZAHG55HKa6LNKc496jAPrUCzAAJXAgACX1eZAAGXAmJ0BKvi1ysE",
    "b_draw":       "CAACAgQAAxkDAAI4M2NtZALeN87Xgly5X7j5XK0dfaznAAJZAgACX1eZAAFS-DsDXK7zdisE",
    "b_skip":       "CAACAgQAAxkDAAI4NGNtZAJR4ZxfKgABx3HNLp-9w8fNagACXQIAAl9XmQABc7AYk0bGSHorBA",
    "b_reverse":    "CAACAgQAAxkDAAI4NWNtZAKP0DU5ZIh-4eID9fwEqWDhAAJbAgACX1eZAAHRLf8w4EEJfysE",
    "g_0":          "CAACAgQAAxkDAAI4NmNtZAMTsoTxk-Gzg61XUbgiWmuDAAJjAgACX1eZAAG_c8FzjSBlOCsE",
    "g_1":          "CAACAgQAAxkDAAI4N2NtZAOMsFWlo1a6VbET_L4Z33qjAAJlAgACX1eZAAH2R3CHmHduZCsE",
    "g_2":          "CAACAgQAAxkDAAI4OGNtZASmomincPijzQaGuhzS4NT3AAJnAgACX1eZAAHB14u8vZ5pjSsE",
    "g_3":          "CAACAgQAAxkDAAI4OWNtZATXrH2F0kmklBKkx5-yLbqeAAJpAgACX1eZAAFaZGnJmMcN9CsE",
    "g_4":          "CAACAgQAAxkDAAI4OmNtZARrtuTkDtrmFwSWGCMNNyzVAAJrAgACX1eZAAF3KxLEqQq8KysE",
    "g_5":          "CAACAgQAAxkDAAI4O2NtZAXsq9mIqylmXkuqblUSZ_s5AAJtAgACX1eZAAGObwogvTEInCsE",
    "g_6":          "CAACAgQAAxkDAAI4PGNtZAXYyNLL6UnAXV2J5fcYDSjcAAJvAgACX1eZAAEpOGFMRnLGmSsE",
    "g_7":          "CAACAgQAAxkDAAI4PWNtZAYp5RXbOKe2_RQkDLNHRnQsAAJxAgACX1eZAAEe_yu4DVELEisE",
    "g_8":          "CAACAgQAAxkDAAI4PmNtZAZuRr1ubCO9SBPYf5uVwxOVAAJzAgACX1eZAAH26plyNxWZuCsE",
    "g_9":          "CAACAgQAAxkDAAI4P2NtZAZ-4ux439AfgakLYhj7NkL7AAJ1AgACX1eZAAGrwYoTMk8UPSsE",
    "g_draw":       "CAACAgQAAxkDAAI4QGNtZAcDJt3SZBIXhpzxAw-0pCjgAAJ3AgACX1eZAAFnlFIJWhbZIysE",
    "g_skip":       "CAACAgQAAxkDAAI4QWNtZAdu6EvL3cTpvKgvVvS5TM8oAAJ7AgACX1eZAAFO5CqgPxquYSsE",
    "g_reverse":    "CAACAgQAAxkDAAI4QmNtZAhYEij-J99P6WZprlvTrO1FAAJ5AgACX1eZAAE9cd3JVwlSEisE",
    "r_0":          "CAACAgQAAxkDAAI4Q2NtZAhJMx2vsEJ0VqZf4K4vnICEAAJ9AgACX1eZAAEZAg2nRervSCsE",
    "r_1":          "CAACAgQAAxkDAAI4RGNtZAggA5W5F360ygp-Kt5511ZGAAJ_AgACX1eZAAFtLPMD6heoDysE",
    "r_2":          "CAACAgQAAxkDAAI4RWNtZAneP8mxTRUYpxCIcSZxrRzaAAKBAgACX1eZAAGuvzFU0Su89SsE",
    "r_3":          "CAACAgQAAxkDAAI4RmNtZAkm-2Z3z4dgngqsNQKlAAEUIgACgwIAAl9XmQABBRY8MBWexokrBA",
    "r_4":          "CAACAgQAAxkDAAI4R2NtZAr32JAr0Q5mSzPrZuPKAAEMAAOFAgACX1eZAAHZFzRnwree-ysE",
    "r_5":          "CAACAgQAAxkDAAI4SGNtZAo06aPW8Bt2bEfhuAwYIAihAAKHAgACX1eZAAHsdpjtu9I2ISsE",
    "r_6":          "CAACAgQAAxkDAAI4SWNtZArDcMo4iVhDv3V2PkjmODGWAAKJAgACX1eZAAG2D__a-tqZBSsE",
    "r_7":          "CAACAgQAAxkDAAI4SmNtZAsNc-unKFxRAUfRgRpIu8zGAAKLAgACX1eZAAGXaAtw5YFztSsE",
    "r_8":          "CAACAgQAAxkDAAI4S2NtZAtXBBjw_QmbUnPCqOjcPciqAAKNAgACX1eZAAGkCOaURWQl8CsE",
    "r_9":          "CAACAgQAAxkDAAI4TGNtZAxdvNd9s7XbaETEDpraDSB8AAKPAgACX1eZAAH-WS6bmv9CgSsE",
    "r_draw":       "CAACAgQAAxkDAAI4TWNtZAz-9sSylYycGwF82_5ceXLOAAKRAgACX1eZAAF2dldgt636fysE",
    "r_skip":       "CAACAgQAAxkDAAI4TmNtZAwwZq3xqWgdKCELX9yXNNDHAAKVAgACX1eZAAGedr9LYgVebCsE",
    "r_reverse":    "CAACAgQAAxkDAAI4T2NtZA1_h1jpVObJt7ZnGWC0EJu_AAKTAgACX1eZAAECR8T0lu-KmysE",
    "y_0":          "CAACAgQAAxkDAAI4UGNtZA3XHBEqHJ4oD2s1vu019fCAAAKXAgACX1eZAALmpUbJzkaKKwQ",
    "y_1":          "CAACAgQAAxkDAAI4UWNtZA70oPDw_EYnua3I_yHnoU0HAAKZAgACX1eZAAGB_02-C22PkysE",
    "y_2":          "CAACAgQAAxkDAAI4UmNtZA73r_BBydbo0QL4Lrp6zzRgAAKbAgACX1eZAAHVmZUJxJwqmCsE",
    "y_3":          "CAACAgQAAxkDAAI4U2NtZA7ITY2cWf3hZhbqbRFA2rznAAKdAgACX1eZAAGnajv8YZQj-ysE",
    "y_4":          "CAACAgQAAxkDAAI4VGNtZA_w89jaIqKJT3mJ3jf4sNfqAAKfAgACX1eZAAEmxeENpAa35SsE",
    "y_5":          "CAACAgQAAxkDAAI4VWNtZA9pJt03yLW1UVqmabBu03CRAAKhAgACX1eZAAH2evQmPPzx8isE",
    "y_6":          "CAACAgQAAxkDAAI4VmNtZBBLaA_cEcY1-cmo4oRl7kFUAAKjAgACX1eZAAGYOfBpuoRg_CsE",
    "y_7":          "CAACAgQAAxkDAAI4V2NtZBC1E-0IzKlEqkiFlLtGQ2djAAKlAgACX1eZAAFYxwrVWROuiysE",
    "y_8":          "CAACAgQAAxkDAAI4WGNtZBDuCE40_AciHh4BlfOxvd4EAAKnAgACX1eZAAF10j1L6rASCSsE",
    "y_9":          "CAACAgQAAxkDAAI4WWNtZBERcGe9cafGmVQMrn--6VyEAAKpAgACX1eZAAGV1nEmuqjoJCsE",
    "y_draw":       "CAACAgQAAxkDAAI4WmNtZBHW7Ik5O4gDp80GEnME_8opAAKrAgACX1eZAAGfJ2XK_ooNFisE",
    "y_skip":       "CAACAgQAAxkDAAI4W2NtZBLpZ4ilI48Wl42H2--LNZleAAKvAgACX1eZAAEVSSkTcHxJXCsE",
    "y_reverse":    "CAACAgQAAxkDAAI4XGNtZBJeXdZLAWEB9hQVadvba2mLAAKtAgACX1eZAAEiP9aakPoiDysE",
    "draw_four":    "CAACAgQAAxkDAAI4XWNtZBOEsZAZxOHFAttWBmLf5WSOAAJhAgACX1eZAAHWx9PCWaCqkysE",
    "colorchooser": "CAACAgQAAxkDAAI4XmNtZBPR9vYmNzz7P7Hq24wrLE16AAJfAgACX1eZAAH4WHYrSCRGIisE",
}

# ─────────────────────────────────────────────────────────────────────────────
# NAME HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _mention(game: dict, uid: int) -> str:
    name = game.get("names", {}).get(str(uid), str(uid))
    return f"[{name}](tg://user?id={uid})"

def _store_name(game: dict, uid: int, first_name: str) -> None:
    game.setdefault("names", {})[str(uid)] = first_name

# ─────────────────────────────────────────────────────────────────────────────
# CARD HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _sticker_key(color: str, value: str) -> str:
    return value if color == "x" else f"{color}_{value}"

def card_display(color: str, value: str) -> str:
    return COLOR_ICONS.get(color, "❓") + VALUE_ICONS.get(value, value)

def _create_deck() -> list:
    colors = ["r", "g", "b", "y"]
    values = ["0","1","2","3","4","5","6","7","8","9","draw","skip","reverse"]
    deck = []
    for c in colors:
        for v in values:
            deck.append([c, v])
            if v != "0":
                deck.append([c, v])
    for _ in range(4):
        deck.append(["x", "colorchooser"])
        deck.append(["x", "draw_four"])
    random.shuffle(deck)
    return deck

def _card_playable(card: list, top: list, chosen_color: str | None, pending_draw: int) -> bool:
    c, v   = card
    tc, tv = top
    eff    = chosen_color if chosen_color else tc
    if c == "x":
        if pending_draw > 0:
            return v == "draw_four" and tv in ("draw_four", "draw")
        return True
    if pending_draw > 0:
        return "draw" in v and "draw" in tv
    return c == eff or v == tv

# ─────────────────────────────────────────────────────────────────────────────
# CARD SORTING  🔵→🟢→🔴→🟡→⚫
# ─────────────────────────────────────────────────────────────────────────────
_COLOR_ORDER = {"b": 0, "g": 1, "r": 2, "y": 3, "x": 4}
_VALUE_ORDER = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4,
    "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "skip": 10, "reverse": 11, "draw": 12,
    "colorchooser": 13, "draw_four": 14,
}

def _sort_hand(hand: list) -> list:
    return sorted(hand, key=lambda card: (
        _COLOR_ORDER.get(card[0], 5), _VALUE_ORDER.get(card[1], 99)
    ))

# ─────────────────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────
async def _get_game(chat_id: int) -> dict | None:
    return await games_col.find_one({"chat": chat_id})

async def _save_game(data: dict) -> None:
    await games_col.update_one({"chat": data["chat"]}, {"$set": data}, upsert=True)

async def _delete_game(chat_id: int) -> None:
    await games_col.delete_one({"chat": chat_id})

# ─────────────────────────────────────────────────────────────────────────────
# FIX #1 — GROUP ISOLATION HELPERS
#
# _register_player(uid, chat_id):
#   If uid is already in another group's game, cleanly remove them from that
#   group's game document before registering in the new one.
#
# _unregister_player(uid):
#   Remove uid from _player_chat only.
# ─────────────────────────────────────────────────────────────────────────────
async def _register_player(uid: int, chat_id: int) -> None:
    """Register uid → chat_id, removing from old group game if needed."""
    old_chat = _player_chat.get(uid)
    if old_chat and old_chat != chat_id:
        # Cleanly remove from old group's DB game so no ghost players
        old_game = await _get_game(old_chat)
        if old_game and uid in old_game.get("players", []) and not old_game.get("started"):
            old_game["players"].remove(uid)
            old_game.get("names", {}).pop(str(uid), None)
            await _save_game(old_game)
        # If the old game was started, we leave them in — they'll time out naturally
        # but we still move the local pointer so inline queries go to new group
    _player_chat[uid] = chat_id

def _unregister_player(uid: int) -> None:
    _player_chat.pop(uid, None)

# ─────────────────────────────────────────────────────────────────────────────
# FIX #2 — LOBBY MESSAGE HELPERS
#
# Build the lobby text showing all joined players as mentions + count.
# Edits the original lobby message in place whenever someone joins/leaves.
# ─────────────────────────────────────────────────────────────────────────────
def _lobby_text(game: dict) -> str:
    players = game.get("players", [])
    names   = game.get("names", {})
    count   = len(players)
    lines   = [
        f"<blockquote>🃏 **ᴜɴᴏ ʟᴏʙʙʏ**</blockquote>",
        f"<blockquote>👥 **{count} ᴘʟᴀʏᴇʀ(s) ᴊᴏɪɴᴇᴅ** (ᴍɪɴ {MIN_PLAYERS} ᴛᴏ sᴛᴀʀᴛ)</blockquote>",
        "<blockquote>",
    ]
    for uid in players:
        name = names.get(str(uid), str(uid))
        lines.append(f"• [{name}](tg://user?id={uid})")
    lines.append("</blockquote>")
    lines.append("<blockquote>ᴛᴀᴘ **ᴊᴏɪɴ** ᴛᴏ ᴇɴᴛᴇʀ · ᴛᴀᴘ **sᴛᴀʀᴛ** ᴡʜᴇɴ ʀᴇᴀᴅʏ\nᴄᴏᴍᴍᴀɴᴅs: /unojoin  /unostart  /unoend</blockquote>")
    return "\n".join(lines)

def _lobby_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ᴊᴏɪɴ",  callback_data="uno_join"),
        InlineKeyboardButton("🚀 sᴛᴀʀᴛ", callback_data="uno_start_btn"),
    ]])

async def _update_lobby_message(chat_id: int, game: dict) -> None:
    """Edit the lobby message to show updated player list."""
    msg_id = _lobby_msg.get(chat_id)
    if not msg_id:
        return
    try:
        await app.edit_message_text(
            chat_id, msg_id,
            _lobby_text(game),
            reply_markup=_lobby_kb(),
            disable_web_page_preview=True,
        )
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# TURN TIMEOUT
# ─────────────────────────────────────────────────────────────────────────────
def _cancel_timer(chat_id: int) -> None:
    t = _turn_timers.pop(chat_id, None)
    if t:
        t.cancel()

async def _timeout_task(chat_id: int, uid: int) -> None:
    await asyncio.sleep(TURN_TIMEOUT)
    game = await _get_game(chat_id)
    if not game or not game.get("started") or game.get("turn") != uid:
        return
    miss_counts: dict = game.get("miss_counts", {})
    miss_counts[str(uid)] = miss_counts.get(str(uid), 0) + 1
    game["miss_counts"]   = miss_counts
    misses = miss_counts[str(uid)]
    deck = game["deck"]
    if not deck:
        deck = _create_deck(); random.shuffle(deck)
    game["hands"].setdefault(str(uid), []).append(deck.pop())
    game["deck"]         = deck
    game["pending_draw"] = 0
    game["drawed"]       = False
    try:
        if misses >= MISS_LIMIT:
            await app.send_message(
                chat_id,
                f"<blockquote>💀 **{_mention(game, uid)}** ᴍɪssᴇᴅ **{MISS_LIMIT}** ᴛᴜʀɴs "
                f"ɪɴ ᴀ ʀᴏᴡ ᴀɴᴅ ɪs **ᴇʟɪᴍɪɴᴀᴛᴇᴅ**! 🃏</blockquote>",
                disable_web_page_preview=True,
            )
            game["players"].remove(uid)
            game["hands"].pop(str(uid), None)
            game.get("miss_counts", {}).pop(str(uid), None)
            game.get("names", {}).pop(str(uid), None)
            _unregister_player(uid)
            if len(game["players"]) < MIN_PLAYERS:
                winner_uid = game["players"][0] if game["players"] else None
                await _save_game(game)
                if winner_uid:
                    await _handle_win(chat_id, winner_uid, game)
                else:
                    await _delete_game(chat_id)
                    await app.send_message(chat_id, "🎮 Game over — no players left.")
                return
            game["turn"] = game["players"][0]
            await _save_game(game)
            await _announce_turn(chat_id, game)
        else:
            remaining = MISS_LIMIT - misses
            warn = (f" ({remaining} more miss{'es' if remaining != 1 else ''} → eliminated)"
                    if remaining <= 2 else "")
            await app.send_message(
                chat_id,
                f"<blockquote>⏰ **{_mention(game, uid)}** ᴛɪᴍᴇᴅ ᴏᴜᴛ — ᴀᴜᴛᴏ-ᴅʀᴇᴡ ᴀɴᴅ sᴋɪᴘᴘᴇᴅ.{warn}</blockquote>",
                disable_web_page_preview=True,
            )
            game["turn"] = _next_player(game)
            await _save_game(game)
            await _announce_turn(chat_id, game)
    except Exception:
        pass

def _reset_timer(chat_id: int, uid: int) -> None:
    _cancel_timer(chat_id)
    _turn_timers[chat_id] = asyncio.create_task(_timeout_task(chat_id, uid))

def _reset_miss(game: dict, uid: int) -> None:
    game.setdefault("miss_counts", {})[str(uid)] = 0

# ─────────────────────────────────────────────────────────────────────────────
# GAME LOGIC HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _next_player(game: dict, skip: bool = False) -> int:
    players = game["players"]
    idx  = players.index(game["turn"])
    step = -1 if game.get("reverse") else 1
    if skip:
        idx = (idx + step) % len(players)
    return players[(idx + step) % len(players)]

def _play_btn(label: str = "🃏 ᴘʟᴀʏ ʏᴏᴜʀ ᴄᴀʀᴅ") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, switch_inline_query_current_chat="uno")
    ]])

async def _announce_turn(chat_id: int, game: dict) -> None:
    top_c, top_v = game["top_card"]
    chosen       = game.get("chosen_color")
    turn_uid     = game["turn"]
    card_txt     = card_display(top_c, top_v)
    if chosen and top_c == "x":
        card_txt += f" → {COLOR_ICONS[chosen]}"
    pending   = game.get("pending_draw", 0)
    draw_warn = f"\n⚠️ ɴᴇxᴛ ᴘʟᴀʏᴇʀ ᴍᴜsᴛ ᴅʀᴀᴡ **{pending}** ᴄᴀʀᴅ(s)!" if pending > 0 else ""
    miss      = game.get("miss_counts", {}).get(str(turn_uid), 0)
    miss_warn = f"\n⚠️ Miss streak: **{miss}/{MISS_LIMIT}**" if miss > 0 else ""
    lines = [
        f"<blockquote>🎯 **ᴛᴜʀɴ:** {_mention(game, turn_uid)}",
        f"🃏 **ᴛᴏᴘ ᴄᴀʀᴅ:** {card_txt}{draw_warn}{miss_warn}",
        "",
        "**ᴘʟᴀʏᴇʀs:**</blockquote>",
    ]
    for uid in game["players"]:
        n = len(game["hands"].get(str(uid), []))
        m = "▶️" if uid == turn_uid else "  "
        lines.append(f"{m} {_mention(game, uid)} — {n} card(s)")
    sk = _sticker_key(top_c, top_v)
    try:
        await app.send_sticker(chat_id, sticker=STICKERS[sk])
    except Exception:
        pass
    await app.send_message(
        chat_id, "\n".join(lines),
        reply_markup=_play_btn(), disable_web_page_preview=True
    )
    _reset_timer(chat_id, turn_uid)

# ─────────────────────────────────────────────────────────────────────────────
# STARTUP RECOVERY
# ─────────────────────────────────────────────────────────────────────────────
async def _recover_state() -> None:
    async for game in games_col.find({"started": True}):
        for uid in game.get("players", []):
            _player_chat[uid] = game["chat"]
    print(f"[unogame] Recovered {len(_player_chat)} active player(s).")

try:
    asyncio.get_event_loop().create_task(_recover_state())
except Exception as _e:
    print(f"[unogame] Recovery error: {_e}")

@app.on_message(filters.command("unorecovery", prefixes=["/", "!", "."]) & filters.private)
async def uno_recovery_cmd(client, message):
    count = 0
    async for game in games_col.find({"started": True}):
        for uid in game.get("players", []):
            _player_chat[uid] = game["chat"]
            count += 1
    await message.reply(f"<blockquote>✅ Recovered {count} player session(s).</blockquote>")

# ─────────────────────────────────────────────────────────────────────────────
# /unogame — Create lobby
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command(["unogame", "unonew"], prefixes=["/", "!", "."]) &
    filters.group
)
async def uno_create(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # FIX #1: check if user is already in THIS group's game
    existing = await _get_game(chat_id)
    if existing:
        return await message.reply(
            "<blockquote>⚠️ ᴀ ᴜɴᴏ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ʜᴇʀᴇ!\n"
            "ᴜsᴇ /unoend ᴛᴏ ᴄᴀɴᴄᴇʟ ɪᴛ ғɪʀsᴛ.</blockquote>"
        )

    game = {
        "chat":           chat_id,
        "players":        [user_id],
        "hands":          {},
        "deck":           _create_deck(),
        "top_card":       None,
        "turn":           None,
        "reverse":        False,
        "started":        False,
        "pending_draw":   0,
        "drawed":         False,
        "choosing_color": False,
        "chosen_color":   None,
        "creator":        user_id,
        "miss_counts":    {},
        "names":          {str(user_id): message.from_user.first_name},
    }
    await _save_game(game)
    await _register_player(user_id, chat_id)  # FIX #1

    sent = await message.reply(
        _lobby_text(game),
        reply_markup=_lobby_kb(),
        disable_web_page_preview=True,
    )
    _lobby_msg[chat_id] = sent.id  # FIX #2: store lobby message id

# ─────────────────────────────────────────────────────────────────────────────
# /unojoin
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command("unojoin", prefixes=["/", "!", "."]) &
    filters.group
)
async def uno_join_cmd(client, message):
    result = await _do_join(message.chat.id, message.from_user)
    await message.reply(result)

@app.on_callback_query(filters.regex("^uno_join$"))
async def uno_join_cb(client, cq):
    result = await _do_join(cq.message.chat.id, cq.from_user)
    await cq.answer(result, show_alert=False)

async def _do_join(chat_id: int, user) -> str:
    game = await _get_game(chat_id)
    if not game:
        return "❌ ɴᴏ ᴜɴᴏ ɢᴀᴍᴇ ʀᴜɴɴɪɴɢ ʜᴇʀᴇ."
    if game.get("started"):
        return "❌ ɢᴀᴍᴇ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ."
    if user.id in game["players"]:
        return "⚠️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!"

    # FIX #1: register (removes from old group if needed)
    await _register_player(user.id, chat_id)
    game["players"].append(user.id)
    _store_name(game, user.id, user.first_name)
    await _save_game(game)

    # FIX #2: update lobby message with new player list
    await _update_lobby_message(chat_id, game)

    return f"✅ {user.first_name} ᴊᴏɪɴᴇᴅ! ({len(game['players'])} ᴘʟᴀʏᴇʀs)"

# ─────────────────────────────────────────────────────────────────────────────
# /unostart
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command("unostart", prefixes=["/", "!", "."]) &
    filters.group
)
async def uno_start_cmd(client, message):
    await _do_start(message.chat.id, message.from_user.id, reply_func=message.reply)

@app.on_callback_query(filters.regex("^uno_start_btn$"))
async def uno_start_cb(client, cq):
    await _do_start(cq.message.chat.id, cq.from_user.id, reply_func=cq.answer)

async def _do_start(chat_id: int, user_id: int, reply_func) -> None:
    game = await _get_game(chat_id)
    if not game:
        return await reply_func("<blockquote>❌ ɴᴏ ʟᴏʙʙʏ ᴛᴏ sᴛᴀʀᴛ.</blockquote>")
    if game["started"]:
        return await reply_func("<blockquote>⚠️ ᴀʟʀᴇᴀᴅʏ sᴛᴀʀᴛᴇᴅ!</blockquote>")
    if len(game["players"]) < MIN_PLAYERS:
        return await reply_func(
            f"<blockquote>❌ ɴᴇᴇᴅ ᴀᴛ ʟᴇᴀsᴛ {MIN_PLAYERS} ᴘʟᴀʏᴇʀs.\n"
            f"ᴄᴜʀʀᴇɴᴛʟʏ: {len(game['players'])}</blockquote>"
        )
    deck = _create_deck()
    random.shuffle(deck)
    hands: dict[str, list] = {}
    for uid in game["players"]:
        hands[str(uid)] = [deck.pop() for _ in range(7)]
        await _register_player(uid, chat_id)  # FIX #1: re-confirm all in this chat
    top_card = None
    while deck:
        c = deck.pop()
        if c[0] != "x":
            top_card = c
            break
    if not top_card:
        return await reply_func("<blockquote>❌ ᴅᴇᴄᴋ ᴇʀʀᴏʀ, ᴛʀʏ ᴀɢᴀɪɴ.</blockquote>")
    game.update({
        "started":        True,
        "hands":          hands,
        "deck":           deck,
        "top_card":       top_card,
        "turn":           game["players"][0],
        "reverse":        False,
        "pending_draw":   0,
        "drawed":         False,
        "choosing_color": False,
        "chosen_color":   None,
        "miss_counts":    {},
    })
    await _save_game(game)

    # Remove lobby keyboard now that game started
    msg_id = _lobby_msg.pop(chat_id, None)
    if msg_id:
        try:
            await app.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
        except Exception:
            pass

    await reply_func("<blockquote>🚀 ᴜɴᴏ sᴛᴀʀᴛᴇᴅ! ɢᴏᴏᴅ ʟᴜᴄᴋ! 🍀</blockquote>")
    await _announce_turn(chat_id, game)

# ─────────────────────────────────────────────────────────────────────────────
# INLINE QUERY — Private card sticker gallery
# group=-1 → runs before all other inline handlers
# FIX #1: uid is scoped to its own chat_id only
# ─────────────────────────────────────────────────────────────────────────────
@app.on_inline_query(group=-1)
async def uno_inline(client, query):
    if query.query.strip().lower() != "uno":
        return

    uid     = query.from_user.id
    chat_id = _player_chat.get(uid)   # FIX #1: uid only resolves to ONE chat

    if not chat_id:
        return await query.answer(
            [InlineQueryResultArticle(
                id="nogame", title="❌ ɴᴏᴛ ɪɴ ᴀ ɢᴀᴍᴇ",
                input_message_content=InputTextMessageContent("ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ɪɴ ᴀɴʏ ᴜɴᴏ ɢᴀᴍᴇ."),
            )],
            cache_time=0, is_personal=True,
        )

    game = await _get_game(chat_id)
    if not game or not game.get("started"):
        return await query.answer(
            [InlineQueryResultArticle(
                id="nogame", title="❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ",
                input_message_content=InputTextMessageContent("No active UNO game found."),
            )],
            cache_time=0, is_personal=True,
        )

    # FIX #1: make sure uid is actually IN this game (not a ghost from old group)
    if uid not in game.get("players", []):
        return await query.answer(
            [InlineQueryResultArticle(
                id="notplayer", title="❌ ɴᴏᴛ ɪɴ ᴛʜɪs ɢᴀᴍᴇ",
                input_message_content=InputTextMessageContent("You are not a player in this game."),
            )],
            cache_time=0, is_personal=True,
        )

    _store_name(game, uid, query.from_user.first_name)
    top_c, top_v = game["top_card"]
    hand    = game["hands"].get(str(uid), [])
    pending = game.get("pending_draw", 0)
    chosen  = game.get("chosen_color")
    is_turn = game["turn"] == uid
    top_txt = card_display(top_c, top_v)
    if chosen and top_c == "x":
        top_txt += f" → {COLOR_ICONS[chosen]}"

    info_lines = [f"🃏 ᴛᴏᴘ: {top_txt}"]
    if pending:
        info_lines.append(f"⚠️ ᴅʀᴀᴡ ᴘᴇɴᴀʟᴛʏ: {pending}")
    info_lines.append("")
    for p in game["players"]:
        n    = len(game["hands"].get(str(p), []))
        m    = "▶️ " if p == game["turn"] else "   "
        name = game.get("names", {}).get(str(p), str(p))
        info_lines.append(f"{m}[{name}](tg://user?id={p}) — {n} card(s)")
    info_txt = "\n".join(info_lines)

    results = []

    # ── Colour chooser ───────────────────────────────────────────────────────
    if game.get("choosing_color") and is_turn:
        for col in ["r", "g", "b", "y"]:
            results.append(InlineQueryResultArticle(
                id=f"color_{col}",
                title=f"{COLOR_ICONS[col]} Choose {col.upper()}",
                description="ᴛᴀᴘ ᴛᴏ sᴇᴛ ᴛʜɪs ᴄᴏʟᴏᴜʀ",
                input_message_content=InputTextMessageContent(
                    f"🌈 {query.from_user.first_name} ᴄʜᴏsᴇ {COLOR_ICONS[col]}!"
                ),
            ))
        return await query.answer(results, cache_time=0, is_personal=True)

    # ── Not your turn ────────────────────────────────────────────────────────
    if not is_turn:
        sorted_hand = _sort_hand(hand)
        for i, card in enumerate(sorted_hand):
            c, v = card
            sk   = _sticker_key(c, v)
            grey = STICKERS_GREY.get(sk)
            if grey:
                results.append(InlineQueryResultCachedSticker(
                    id=f"info_{i}", sticker_file_id=grey,
                    input_message_content=InputTextMessageContent(
                        f"⏳ ɪᴛ's ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ ʏᴇᴛ!\n\n{info_txt}"
                    ),
                ))
        if not results:
            results.append(InlineQueryResultArticle(
                id="wait", title="⏳ ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ",
                input_message_content=InputTextMessageContent(f"⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ.\n\n{info_txt}"),
            ))
        return await query.answer(results, cache_time=0, is_gallery=True, is_personal=True)

    # ── Your turn ────────────────────────────────────────────────────────────
    if game.get("drawed"):
        results.append(InlineQueryResultCachedSticker(
            id="pass",
            sticker_file_id=STICKERS["option_pass"],
            input_message_content=InputTextMessageContent("⏭️ ᴘᴀssᴇᴅ ᴛᴜʀɴ."),
        ))
    else:
        draw_label = f"📥 ᴅʀᴀᴡ {pending} card(s)" if pending > 0 else "📥 ᴅʀᴀᴡ ᴀ ᴄᴀʀᴅ"
        results.append(InlineQueryResultCachedSticker(
            id="draw",
            sticker_file_id=STICKERS["option_draw"],
            input_message_content=InputTextMessageContent(draw_label),
        ))

    sorted_hand = _sort_hand(hand)
    for i, card in enumerate(sorted_hand):
        c, v     = card
        sk       = _sticker_key(c, v)
        playable = _card_playable(card, game["top_card"], chosen, pending)
        orig_idx = next(
            (j for j, hc in enumerate(hand) if hc[0] == c and hc[1] == v),
            i
        )
        if playable:
            stk = STICKERS.get(sk)
            if stk:
                results.append(InlineQueryResultCachedSticker(
                    id=f"play_{c}_{v}_{orig_idx}",
                    sticker_file_id=stk,
                    input_message_content=InputTextMessageContent(
                        f"🃏 {query.from_user.first_name} ᴘʟᴀʏᴇᴅ {card_display(c, v)}!"
                    ),
                ))
        else:
            grey = STICKERS_GREY.get(sk)
            if grey:
                results.append(InlineQueryResultCachedSticker(
                    id=f"info_{i}", sticker_file_id=grey,
                    input_message_content=InputTextMessageContent(
                        f"🚫 ᴄᴀɴ'ᴛ ᴘʟᴀʏ {card_display(c, v)} ʀɪɢʜᴛ ɴᴏᴡ.\n\n{info_txt}"
                    ),
                ))

    return await query.answer(results, cache_time=0, is_gallery=True, is_personal=True)

# ─────────────────────────────────────────────────────────────────────────────
# CHOSEN INLINE RESULT — Process the played card
# ─────────────────────────────────────────────────────────────────────────────
@app.on_chosen_inline_result(group=-1)
async def uno_chosen(client, result):
    uid     = result.from_user.id
    res_id  = result.result_id
    chat_id = _player_chat.get(uid)
    if not chat_id:
        return

    game = await _get_game(chat_id)
    if not game or not game.get("started"):
        return

    # FIX #1: verify player is actually in this game
    if uid not in game.get("players", []):
        return

    if game["turn"] != uid and not res_id.startswith("info"):
        return

    # Cancel timer IMMEDIATELY before any await
    _cancel_timer(chat_id)
    _store_name(game, uid, result.from_user.first_name)
    name    = result.from_user.first_name
    hand    = game["hands"].get(str(uid), [])
    pending = game.get("pending_draw", 0)

    # ── Colour chosen ────────────────────────────────────────────────────────
    if res_id.startswith("color_") and game.get("choosing_color"):
        chosen_color           = res_id.split("_")[1]
        game["chosen_color"]   = chosen_color
        game["choosing_color"] = False
        game["turn"]           = _next_player(game)
        game["drawed"]         = False
        _reset_miss(game, uid)
        await _save_game(game)
        await app.send_message(
            chat_id,
            f"🌈 **{name}** ᴄʜᴏsᴇ **{COLOR_ICONS[chosen_color]}**!",
        )
        await _announce_turn(chat_id, game)
        return

    # ── Pass ─────────────────────────────────────────────────────────────────
    if res_id == "pass":
        game["turn"]   = _next_player(game)
        game["drawed"] = False
        _reset_miss(game, uid)
        await _save_game(game)
        await app.send_message(chat_id, f"⏭️ **{name}** passed.")
        await _announce_turn(chat_id, game)
        return

    # ── Draw ─────────────────────────────────────────────────────────────────
    if res_id == "draw":
        deck   = game["deck"]
        amount = pending if pending > 0 else 1
        if len(deck) < amount:
            deck = _create_deck()
            random.shuffle(deck)
            await app.send_message(chat_id, "🔄 Reshuffling deck...")
        drawn = [deck.pop() for _ in range(min(amount, len(deck)))]
        hand.extend(drawn)
        game["hands"][str(uid)] = hand
        game["deck"]            = deck
        game["pending_draw"]    = 0
        _reset_miss(game, uid)
        await app.send_message(
            chat_id,
            f"📥 **{name}** ᴅʀᴇᴡ **{len(drawn)}** ᴄᴀʀᴅ(s)",
        )
        if pending > 0:
            game["drawed"] = False
            game["turn"]   = _next_player(game)
            await _save_game(game)
            await _announce_turn(chat_id, game)
        else:
            game["drawed"] = True
            await _save_game(game)
            await _announce_turn(chat_id, game)
        return

    # ── Play a card ──────────────────────────────────────────────────────────
    if res_id.startswith("play_"):
        parts = res_id.split("_")
        color = parts[1]
        idx   = int(parts[-1])
        value = "_".join(parts[2:-1])

        if idx >= len(hand) or list(hand[idx]) != [color, value]:
            found = False
            for i, c in enumerate(hand):
                if c[0] == color and c[1] == value:
                    idx = i
                    found = True
                    break
            if not found:
                await app.send_message(chat_id, "❌ ᴄᴀʀᴅ ɴᴏᴛ ғᴏᴜɴᴅ — ᴛʀʏ ᴀɢᴀɪɴ.")
                return

        _reset_miss(game, uid)
        card = hand.pop(idx)
        game["hands"][str(uid)] = hand
        game["top_card"]        = card
        game["drawed"]          = False
        game["chosen_color"]    = None
        skip_next = False

        if value == "skip":
            skip_next = True
            await app.send_message(
                chat_id,
                f"🚫 **{name}** ᴘʟᴀʏᴇᴅ **sᴋɪᴘ** {card_display(color, value)}!"
            )
        elif value == "reverse":
            game["reverse"] = not game["reverse"]
            if len(game["players"]) == 2:
                skip_next = True
            await app.send_message(
                chat_id,
                f"🔁 **{name}** ᴘʟᴀʏᴇᴅ **ʀᴇᴠᴇʀsᴇ** {card_display(color, value)}!"
            )
        elif value == "draw":
            game["pending_draw"] = pending + 2
            await app.send_message(
                chat_id,
                f"📥 **{name}** ᴘʟᴀʏᴇᴅ **+2** {card_display(color, value)}!\n"
                f"sᴛᴀᴄᴋ ᴛᴏᴛᴀʟ: **{game['pending_draw']}** 📥"
            )
        elif value == "draw_four":
            game["pending_draw"]   = pending + 4
            game["choosing_color"] = True
            await app.send_message(
                chat_id,
                f"🃏 **{name}** ᴘʟᴀʏᴇᴅ **+4** {card_display(color, value)}!\n"
                f"sᴛᴀᴄᴋ: **{game['pending_draw']}** ⚡\nᴄʜᴏᴏsᴇ ᴀ ᴄᴏʟᴏᴜʀ 👇",
                reply_markup=_play_btn("🌈 ᴄʜᴏᴏsᴇ ᴄᴏʟᴏᴜʀ"),
            )
            await _save_game(game)
            return
        elif value == "colorchooser":
            game["choosing_color"] = True
            await app.send_message(
                chat_id,
                f"🌈 **{name}** ᴘʟᴀʏᴇᴅ **ᴡɪʟᴅ** {card_display(color, value)}!\nᴄʜᴏᴏsᴇ ᴀ ᴄᴏʟᴏᴜʀ 👇",
                reply_markup=_play_btn("🌈 ᴄʜᴏᴏsᴇ ᴄᴏʟᴏᴜʀ"),
            )
            await _save_game(game)
            return

        # ── Win ───────────────────────────────────────────────────────────────
        if len(hand) == 0:
            await _handle_win(chat_id, uid, game)
            return

        # ── UNO alert ─────────────────────────────────────────────────────────
        if len(hand) == 1:
            await app.send_message(chat_id, f"🔔 **{name}** ʜᴀs **ᴜɴᴏ!** 1 ᴄᴀʀᴅ ʟᴇғᴛ! 🃏")

        game["turn"] = _next_player(game, skip=skip_next)
        await _save_game(game)
        await _announce_turn(chat_id, game)
        return

    # info_ taps (grey cards) — silently ignored

# ─────────────────────────────────────────────────────────────────────────────
# WIN HANDLER
# ─────────────────────────────────────────────────────────────────────────────
async def _handle_win(chat_id: int, uid: int, game: dict) -> None:
    _cancel_timer(chat_id)
    await app.send_message(
        chat_id,
        f"🏆 **{_mention(game, uid)}** ᴘʟᴀʏᴇᴅ ᴛʜᴇɪʀ ʟᴀsᴛ ᴄᴀʀᴅ ᴀɴᴅ **ᴡɪɴs ᴛʜᴇ ɢᴀᴍᴇ!** 🎉🥳🎊",
        disable_web_page_preview=True,
    )
    if uid in game.get("players", []):
        game["players"].remove(uid)
    for pid in game.get("players", []):
        _unregister_player(pid)
        await stats_col.update_one({"user": pid}, {"$inc": {"games": 1}}, upsert=True)
    _unregister_player(uid)
    _lobby_msg.pop(chat_id, None)
    now = datetime.now(tz=timezone.utc)
    await stats_col.update_one({"user": uid}, {"$inc": {"wins": 1, "games": 1}}, upsert=True)
    await wins_log.insert_one({"user": uid, "chat_id": chat_id, "ts": now})
    await _delete_game(chat_id)
    await app.send_message(chat_id, "🎮 Game over! Use /unogame for a rematch.")

# ─────────────────────────────────────────────────────────────────────────────
# /unoleave
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command("unoleave", prefixes=["/", "!", "."]) &
    filters.group
)
async def uno_leave(client, message):
    uid     = message.from_user.id
    chat_id = message.chat.id
    game    = await _get_game(chat_id)
    if not game or uid not in game["players"]:
        return await message.reply("❌ ʏᴏᴜ'ʀᴇ ɴᴏᴛ ɪɴ ᴀ ɢᴀᴍᴇ ʜᴇʀᴇ.")

    was_turn = game.get("turn") == uid
    game["players"].remove(uid)
    game["hands"].pop(str(uid), None)
    game.get("miss_counts", {}).pop(str(uid), None)
    game.get("names", {}).pop(str(uid), None)
    _unregister_player(uid)

    if len(game["players"]) < MIN_PLAYERS:
        for pid in game["players"]:
            _unregister_player(pid)
        _cancel_timer(chat_id)
        _lobby_msg.pop(chat_id, None)
        await _delete_game(chat_id)
        return await message.reply(
            f"👋 **{message.from_user.first_name}** ʟᴇғᴛ. ᴛᴏᴏ ғᴇᴡ ᴘʟᴀʏᴇʀs — ɢᴀᴍᴇ ᴇɴᴅᴇᴅ."
        )

    if was_turn and game["started"]:
        game["turn"]   = _next_player(game)
        game["drawed"] = False

    await _save_game(game)

    # FIX #2: update lobby if not started yet
    if not game.get("started"):
        await _update_lobby_message(chat_id, game)

    await message.reply(f"👋 **{message.from_user.first_name}** ʟᴇғᴛ ᴛʜᴇ ɢᴀᴍᴇ.")
    if was_turn and game["started"]:
        await _announce_turn(chat_id, game)

# ─────────────────────────────────────────────────────────────────────────────
# /unoend
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command("unoend", prefixes=["/", "!", "."]) &
    filters.group
)
async def uno_end(client, message):
    chat_id = message.chat.id
    game    = await _get_game(chat_id)
    if not game:
        return await message.reply("❌ ɴᴏ ɢᴀᴍᴇ ʀᴜɴɴɪɴɢ.")
    for pid in game["players"]:
        _unregister_player(pid)
    _cancel_timer(chat_id)
    _lobby_msg.pop(chat_id, None)
    await _delete_game(chat_id)
    await message.reply(
        f"<blockquote>🛑 ᴜɴᴏ ɢᴀᴍᴇ ᴇɴᴅᴇᴅ ʙʏ **{message.from_user.first_name}**.</blockquote>"
    )

# ─────────────────────────────────────────────────────────────────────────────
# /unostatus
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(
    filters.command("unostatus", prefixes=["/", "!", "."]) &
    filters.group
)
async def uno_status(client, message):
    chat_id = message.chat.id
    game    = await _get_game(chat_id)
    if not game:
        return await message.reply("<blockquote>❌ ɴᴏ ᴜɴᴏ ɢᴀᴍᴇ ʀᴜɴɴɪɴɢ ʜᴇʀᴇ.</blockquote>")
    if not game.get("started"):
        # FIX #2: show lobby player list even from /unostatus
        return await message.reply(
            _lobby_text(game),
            reply_markup=_lobby_kb(),
            disable_web_page_preview=True,
        )
    top_c, top_v = game["top_card"]
    chosen  = game.get("chosen_color")
    top_txt = card_display(top_c, top_v)
    if chosen and top_c == "x":
        top_txt += f" → {COLOR_ICONS[chosen]}"
    pending = game.get("pending_draw", 0)
    lines   = ["🃏 **ᴜɴᴏ ɢᴀᴍᴇ sᴛᴀᴛᴜs**", f"🔝 ᴛᴏᴘ ᴄᴀʀᴅ : {top_txt}"]
    if pending:
        lines.append(f"⚠️ ᴘᴇɴᴅɪɴɢ draw: {pending}")
    lines += [f"🎯 ᴛᴜʀɴ     : {_mention(game, game['turn'])}", "", "**ᴘʟᴀʏᴇʀs:**"]
    miss_counts = game.get("miss_counts", {})
    for uid in game["players"]:
        n      = len(game["hands"].get(str(uid), []))
        m      = "▶️" if uid == game["turn"] else "  "
        misses = miss_counts.get(str(uid), 0)
        warn   = f" ⚠️{misses}/{MISS_LIMIT}" if misses > 0 else ""
        lines.append(f"{m} {_mention(game, uid)} — {n} card(s){warn}")
    await message.reply(
        "\n".join(lines), reply_markup=_play_btn(), disable_web_page_preview=True
    )

# ─────────────────────────────────────────────────────────────────────────────
# /unostats
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("unostats", prefixes=["/", "!", "."]))
async def uno_stats(client, message):
    uid   = message.from_user.id
    data  = await stats_col.find_one({"user": uid}) or {}
    wins  = data.get("wins", 0)
    games = data.get("games", 0)
    rate  = f"{wins/games*100:.1f}%" if games else "N/A"
    await message.reply(
        f"<blockquote>📊 **ᴜɴᴏ sᴛᴀᴛs — {message.from_user.first_name}**</blockquote>\n"
        f"<blockquote>🎮 ɢᴀᴍᴇs ᴘʟᴀʏᴇᴅ : `{games}`\n"
        f"🏆 ᴡɪɴs         : `{wins}`\n"
        f"📈 ᴡɪɴ ʀᴀᴛᴇ     : `{rate}`</blockquote>"
    )

# ─────────────────────────────────────────────────────────────────────────────
# /unotop
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("unotop", prefixes=["/", "!", "."]))
async def uno_top(client, message):
    lines  = ["🏆 **ᴜɴᴏ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ**\n"]
    medals = ["🥇", "🥈", "🥉"]
    rank   = 1
    async for user in stats_col.find().sort("wins", -1).limit(10):
        uid  = user.get("user", 0)
        wins = user.get("wins", 0)
        gms  = user.get("games", 0)
        m    = medals[rank - 1] if rank <= 3 else f"{rank}."
        lines.append(f"{m} [ᴘʟᴀʏᴇʀ](tg://user?id={uid}) — {wins} ᴡɪɴs / {gms} ɢᴀᴍᴇs")
        rank += 1
    if rank == 1:
        lines.append("_ɴᴏ ɢᴀᴍᴇs ᴘʟᴀʏᴇᴅ ʏᴇᴛ!_")
    await message.reply("\n".join(lines), disable_web_page_preview=True)

# ─────────────────────────────────────────────────────────────────────────────
# /unohelp
# ─────────────────────────────────────────────────────────────────────────────
@app.on_message(filters.command("unohelp", prefixes=["/", "!", "."]))
async def uno_help(client, message):
    await message.reply(
        "<blockquote>🃏 **ᴜɴᴏ ɢᴀᴍᴇ ᴄᴏᴍᴍᴀɴᴅs**</blockquote>\n"
        "<blockquote>**Group commands:**\n"
        "`/unogame`   — ᴄʀᴇᴀᴛᴇ ᴀ ɴᴇᴡ ʟᴏʙʙʏ\n"
        "`/unojoin`   — ᴊᴏɪɴ ᴛʜᴇ ʟᴏʙʙʏ\n"
        "`/unostart`  — sᴛᴀʀᴛ ᴛʜᴇ ɢᴀᴍᴇ\n"
        "`/unoleave`  — ʟᴇᴀᴠᴇ ᴛʜᴇ ɢᴀᴍᴇ\n"
        "`/unoend`    — ғᴏʀᴄᴇ-ᴇɴᴅ ᴛʜᴇ ɢᴀᴍᴇ\n"
        "`/unostatus` — sʜᴏᴡ ᴄᴜʀʀᴇɴᴛ ɢᴀᴍᴇ sᴛᴀᴛᴇ</blockquote>\n"
        "<blockquote>**ᴘᴇʀsᴏɴᴀʟ ᴄᴏᴍᴍᴀɴᴅs:**\n"
        "`/unostats`  — ʏᴏᴜʀ ᴡɪɴ sᴛᴀᴛs\n"
        "`/unotop`    — ɢʟᴏʙᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</blockquote>\n"
        "<blockquote>**ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:**\n"
        "1️⃣ `/unogame` → ᴏᴛʜᴇʀs `/unojoin` → `/unostart`\n"
        "2️⃣ ᴡʜᴇɴ ɪᴛ's ʏᴏᴜʀ ᴛᴜʀɴ ᴛᴀᴘ **🃏 ᴘʟᴀʏ ʏᴏᴜʀ ᴄᴀʀᴅ**\n"
        "3️⃣ ʏᴏᴜʀ ᴄᴀʀᴅs ᴀᴘᴘᴇᴀʀ **sᴏʀᴛᴇᴅ ʙʏ ᴄᴏʟᴏᴜʀ** (🔵→🟢→🔴→🟡→⚫)\n"
        "4️⃣ ᴛᴀᴘ ᴀ ᴄᴏʟᴏᴜʀᴇᴅ sᴛɪᴄᴋᴇʀ ᴛᴏ ᴘʟᴀʏ; ɢʀᴇʏ = ᴄᴀɴ'ᴛ ᴘʟᴀʏ\n"
        "5️⃣ ᴡɪʟᴅ/+4 ᴏᴘᴇɴs ᴄᴏʟᴏᴜʀ ᴘɪᴄᴋᴇʀ · ᴅʀᴀᴡ ᴄᴀʀᴅs sᴛᴀᴄᴋ\n"
        "6️⃣ ɪᴅʟᴇ **60s** → ᴀᴜᴛᴏ-ᴅʀᴀᴡ + sᴋɪᴘ · **3** ᴍɪssᴇs → **ᴇʟɪᴍɪɴᴀᴛᴇᴅ!**\n"
        "7️⃣ ғɪʀsᴛ ᴛᴏ ᴇᴍᴘᴛʏ ʜᴀɴᴅ ᴡɪɴs! 🏆</blockquote>\n"
        "<blockquote>🔒 **ɢʀᴏᴜᴘ ɪsᴏʟᴀᴛɪᴏɴ:** ᴇᴀᴄʜ ɢʀᴏᴜᴘ ʜᴀs ɪᴛs ᴏᴡɴ ɪɴᴅᴇᴘᴇɴᴅᴇɴᴛ ɢᴀᴍᴇ.\n"
        "ᴊᴏɪɴɪɴɢ ᴀ ɴᴇᴡ ɢʀᴏᴜᴘ's ʟᴏʙʙʏ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʀᴇᴍᴏᴠᴇs ʏᴏᴜ ғʀᴏᴍ ᴀɴʏ ᴘʀᴇᴠɪᴏᴜs ʟᴏʙʙʏ.</blockquote>"
    )

# ─────────────────────────────────────────────────────────────────────────────
# MODULE META
# ─────────────────────────────────────────────────────────────────────────────
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_78"
__help__     = """
🔻 /unohelp     — ꜰᴜʟʟ ᴄᴏᴍᴍᴀɴᴅ ʟɪꜱᴛ
🔻 /unogame     — ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴜɴᴏ ɢᴀᴍᴇ (ʟᴏʙʙʏ ꜱʜᴏᴡꜱ ᴊᴏɪɴᴇᴅ ᴘʟᴀʏᴇʀꜱ)
🔻 /unojoin     — ᴊᴏɪɴ ᴛʜᴇ ʟᴏʙʙʏ (ʟᴏʙʙʏ ᴜᴘᴅᴀᴛᴇꜱ ʟɪᴠᴇ)
🔻 /unostart    — ꜱᴛᴀʀᴛ ᴛʜᴇ ɢᴀᴍᴇ
🔻 /unoleave    — ʟᴇᴀᴠᴇ ᴛʜᴇ ɢᴀᴍᴇ
🔻 /unoend      — ꜰᴏʀᴄᴇ ꜱᴛᴏᴘ ᴛʜᴇ ɢᴀᴍᴇ
🔻 /unostatus   — ꜱʜᴏᴡ ɢᴀᴍᴇ ꜱᴛᴀᴛᴜꜱ / ʟᴏʙʙʏ
🔻 /unostats    — ʏᴏᴜʀ ᴜɴᴏ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ
🔻 /unotop      — ᴛᴏᴘ 10 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ
🔻 /unorecovery — ʀᴇᴄᴏᴠᴇʀ ꜱᴇꜱꜱɪᴏɴꜱ (ᴏᴡɴᴇʀ)
"""
