import os
import logging
import re
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    CallbackQuery,
    Message,
)

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.decorators.language import languageCB
from strings import get_string

# -------------------------------------------------------------------
# LOGGING (optional)
# -------------------------------------------------------------------
LOGGER = logging.getLogger(__name__)

# -------------------------------------------------------------------
# ALL 50 WEB GAMES (ORDERED)
# -------------------------------------------------------------------
WEB_GAMES = [
    "https://ultrashort.info/gkR6Ci",
    "https://ultrashort.info/xkKB8w",
    "https://ultrashort.info/TMyKFw",
    "https://ultrashort.info/Q4XZDV",
    "https://ultrashort.info/yzuwfg",
    "https://ultrashort.info/fMPToV",
    "https://ultrashort.info/tJHfhb",
    "https://ultrashort.info/ujoRZA",
    "https://ultrashort.info/ggg4cY",
    "https://ultrashort.info/FYZLhg",
    "https://ultrashort.info/K3cP4N",
    "https://ultrashort.info/9iS2ot",
    "https://ultrashort.info/NVMWSU",
    "https://ultrashort.info/zbL7Ee",
    "https://ultrashort.info/ZxPIFE",
    "https://ultrashort.info/qbSQ7L",
    "https://ultrashort.info/1TFVOO",
    "https://ultrashort.info/CvIbGW",
    "https://ultrashort.info/z5T0hl",
    "https://ultrashort.info/wXu7P9",
    "https://ultrashort.info/o8d7m4",
    "https://ultrashort.info/VqWr4i",
    "https://ultrashort.info/cUUfD8",
    "https://ultrashort.info/5UF1ky",
    "https://ultrashort.info/SL3s2o",
    "https://ultrashort.info/MSOvrx",
    "https://ultrashort.info/mlcO59",
    "https://ultrashort.info/Q5mfgi",
    "https://ultrashort.info/tK6bF9",
    "https://ultrashort.info/HJZmt1",
    "https://ultrashort.info/qu3Xjd",
    "https://ultrashort.info/ISf9PD",
    "https://ultrashort.info/xJSEBZ",
    "https://ultrashort.info/Xv8xLQ",
    "https://ultrashort.info/zgG9Cz",
    "https://ultrashort.info/uEVnVD",
    "https://ultrashort.info/z7SnZT",
    "https://ultrashort.info/YbjaHn",
    "https://ultrashort.info/CWatkc",
    "https://ultrashort.info/2Sn9J1",
    "https://ultrashort.info/GqgTKg",
    "https://ultrashort.info/U4n7cR",
    "https://ultrashort.info/zDemd8",
    "https://ultrashort.info/ivhBMA",
    "https://ultrashort.info/LJ2kSZ",
    "https://ultrashort.info/4SHOGN",
    "https://ultrashort.info/h9GT5e",
    "https://ultrashort.info/DN6bd4",
    "https://ultrashort.info/YbSe53",
    "https://ultrashort.info/Mh9b2H",
]

GAMES_PER_PAGE = 11


# -------------------------------------------------------------------
# BUILD PANEL DYNAMICALLY
# -------------------------------------------------------------------
def build_panel(_: dict, page: int):
    """
    Build the inline keyboard for the given page.
    `_` is the language dictionary (from get_string).
    """
    start = page * GAMES_PER_PAGE
    end = start + GAMES_PER_PAGE
    games = WEB_GAMES[start:end]

    buttons = []
    index = start + 1

    # Row 1 (3 buttons)
    row = []
    for i in range(3):
        if i < len(games):
            row.append(
                InlineKeyboardButton(
                    text=_[f"GAME_{index + i}"],
                    web_app=WebAppInfo(url=games[i])
                )
            )
    buttons.append(row)

    # Row 2 (3 buttons)
    row = []
    for i in range(3, 6):
        if i < len(games):
            row.append(
                InlineKeyboardButton(
                    text=_[f"GAME_{index + i}"],
                    web_app=WebAppInfo(url=games[i])
                )
            )
    buttons.append(row)

    # Row 3 (2 buttons)
    row = []
    for i in range(6, 8):
        if i < len(games):
            row.append(
                InlineKeyboardButton(
                    text=_[f"GAME_{index + i}"],
                    web_app=WebAppInfo(url=games[i])
                )
            )
    if row:
        buttons.append(row)

    # Row 4 (2 buttons)
    row = []
    for i in range(8, 10):
        if i < len(games):
            row.append(
                InlineKeyboardButton(
                    text=_[f"GAME_{index + i}"],
                    web_app=WebAppInfo(url=games[i])
                )
            )
    if row:
        buttons.append(row)

    # Row 5 (1 button) – if there are 11 games on this page
    if len(games) > 10:
        buttons.append([
            InlineKeyboardButton(
                text=_[f"GAME_{index + 10}"],
                web_app=WebAppInfo(url=games[10])
            )
        ])

    # Navigation row
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text=_["BACK_BUTTON"],
            callback_data=f"web_prev_{page-1}"
        ))
    if end < len(WEB_GAMES):
        nav.append(InlineKeyboardButton(
            text=_["NEXT_BUTTON"],
            callback_data=f"web_next_{page+1}"
        ))

    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


# -------------------------------------------------------------------
# CALLBACK: Open Games Panel (triggered by help menu button H_B_44)
# -------------------------------------------------------------------
@Client.on_callback_query(filters.regex("^H_B_44$"))
@languageCB
async def open_games(_, cq: CallbackQuery, _lang):
    await cq.message.edit_text(
        "🎮 ᴄʜᴏᴏꜱᴇ ᴀ ɢᴀᴍᴇ ᴛᴏ ᴘʟᴀʏ", #_lang["CMD_GAMES"],
        reply_markup=build_panel(_lang, 0)
    )
    await cq.answer()


# -------------------------------------------------------------------
# CALLBACK: Pagination (prev/next)
# -------------------------------------------------------------------
@Client.on_callback_query(filters.regex("^web_(prev|next)_(\\d+)$"))
@languageCB
async def navigate(_, cq: CallbackQuery, _lang):
    page = int(cq.data.split("_")[-1])
    await cq.message.edit_reply_markup(
        reply_markup=build_panel(_lang, page)
    )
    await cq.answer()


# -------------------------------------------------------------------
# COMMAND: /games
# -------------------------------------------------------------------
@Client.on_message(filters.command("games"))
async def games_cmd(client, message: Message):
    lang_code = message.from_user.language_code or "en"
    _ = get_string(lang_code)

    await message.reply_text(
        "🎮 ᴄʜᴏᴏꜱᴇ ᴀ ɢᴀᴍᴇ ᴛᴏ ᴘʟᴀʏ", #_["CMD_GAMES"],
        reply_markup=build_panel(_, 0)
    )


# -------------------------------------------------------------------
# INTERCEPT HELP MODULE CALLBACK FOR H_B_44
# This handler runs when the user clicks the Web Games module button
# in the help menu (callback "help_mod ...|H_B_44"). It displays the
# games panel instead of the default help text.
# -------------------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^help_mod\s+.*\|H_B_44$"))
@languageCB
async def help_mod_webgames(_, cq: CallbackQuery, _lang):
    # Extract menu_key from callback data (needed for potential back navigation)
    parts = cq.data.split()
    if len(parts) < 2:
        return
    data = parts[1]
    menu_key, mod_key = data.split("|", 1)   # mod_key is "H_B_44"

    # Show the games panel (same as /games)
    await cq.message.edit_text(
        _lang["help_1"],
        reply_markup=build_panel(_lang, 0)
    )
    await cq.answer()


# -------------------------------------------------------------------
# HELP MENU INTEGRATION
# -------------------------------------------------------------------
__menu__ = "CMD_GAMES"          # Key for the main help menu (not used directly)
__mod_name__ = "H_B_44"         # This must match the callback from the help button
__help__ = """
🔻 /games - Open Web Games Panel
"""
MOD_TYPE = "GAMES"
MOD_NAME = "WebGames-50"
MOD_PRICE = "50"
