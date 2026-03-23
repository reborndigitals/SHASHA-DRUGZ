import logging
from pyrogram import filters
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

LOGGER = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  ALL 50 WEB GAMES
# ─────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────
#  PANEL BUILDER
#  NOTE: WebAppInfo buttons CANNOT be used in edit_message_text /
#  edit_reply_markup — Telegram rejects them with BUTTON_TYPE_INVALID.
#  Every panel must always be sent as a FRESH message via the client.
# ─────────────────────────────────────────────────────────────────
def build_panel(lang: dict, page: int) -> InlineKeyboardMarkup:
    start  = page * GAMES_PER_PAGE
    end    = start + GAMES_PER_PAGE
    games  = WEB_GAMES[start:end]
    buttons = []

    def _btn(offset: int) -> InlineKeyboardButton:
        abs_idx = start + offset
        label   = lang.get(f"GAME_{abs_idx + 1}", f"Game {abs_idx + 1}")
        return InlineKeyboardButton(
            text=label,
            web_app=WebAppInfo(url=games[offset]),
        )

    # Rows: 3 / 3 / 2 / 2 / 1
    for lo, hi in [(0, 3), (3, 6), (6, 8), (8, 10), (10, 11)]:
        row = [_btn(i) for i in range(lo, hi) if i < len(games)]
        if row:
            buttons.append(row)

    # Navigation row — plain callback buttons, always safe to use
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            text=lang.get("BACK_BUTTON", "◀ Prev"),
            callback_data=f"web_prev_{page - 1}",
        ))
    if end < len(WEB_GAMES):
        nav.append(InlineKeyboardButton(
            text=lang.get("NEXT_BUTTON", "Next ▶"),
            callback_data=f"web_next_{page + 1}",
        ))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────
#  HELPER — delete old message, send fresh panel via app (Client)
#
#  Why not cq.message.chat.send_message()?
#  → Chat objects in Pyrogram do NOT have send_message().
#    That method lives on the Client (app). Always use:
#    app.send_message(chat_id, ...) ✅
# ─────────────────────────────────────────────────────────────────
async def _send_panel(cq: CallbackQuery, lang: dict, page: int) -> None:
    chat_id = cq.message.chat.id
    try:
        await cq.message.delete()
    except Exception:
        pass  # non-fatal — bot may lack delete permission

    # Use the global app client to send a fresh message
    await app.send_message(
        chat_id=chat_id,
        text="🎮 ᴄʜᴏᴏꜱᴇ ᴀ ɢᴀᴍᴇ ᴛᴏ ᴘʟᴀʏ",
        reply_markup=build_panel(lang, page),
    )
    await cq.answer()


# ─────────────────────────────────────────────────────────────────
#  CALLBACK: Help-menu button  →  H_B_44
# ─────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^H_B_44$"))
@languageCB
async def open_games(_, cq: CallbackQuery, _lang):
    await _send_panel(cq, _lang, 0)


# ─────────────────────────────────────────────────────────────────
#  CALLBACK: Pagination  (web_prev_N  /  web_next_N)
# ─────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^web_(prev|next)_(\d+)$"))
@languageCB
async def navigate(_, cq: CallbackQuery, _lang):
    page = int(cq.data.split("_")[-1])
    await _send_panel(cq, _lang, page)


# ─────────────────────────────────────────────────────────────────
#  CALLBACK: Help-module intercept  →  "help_mod ...|H_B_44"
# ─────────────────────────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^help_mod\s+.*\|H_B_44$"))
@languageCB
async def help_mod_webgames(_, cq: CallbackQuery, _lang):
    await _send_panel(cq, _lang, 0)


# ─────────────────────────────────────────────────────────────────
#  COMMAND: /webgames
# ─────────────────────────────────────────────────────────────────
@app.on_message(filters.command("webgames"))
async def webgames_cmd(_, message: Message):
    lang_code = getattr(message.from_user, "language_code", None) or "en"
    lang = get_string(lang_code)
    await message.reply_text(
        "🎮 ᴄʜᴏᴏꜱᴇ ᴀ ɢᴀᴍᴇ ᴛᴏ ᴘʟᴀʏ",
        reply_markup=build_panel(lang, 0),
    )


# ─────────────────────────────────────────────────────────────────
#  MODULE META
# ─────────────────────────────────────────────────────────────────
__menu__     = "CMD_GAMES"
__mod_name__ = "H_B_44"
__help__     = """
🔻 /webgames - Open Web-Games Panel
"""
