import importlib
import os
from collections import defaultdict
from typing import Dict, List, Union

from pyrogram import filters, types
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import get_lang
from SHASHA_DRUGZ.utils.decorators.language import LanguageStart, languageCB
from strings import get_string

from config import BANNED_USERS, START_IMG_URL, SUPPORT_CHAT, SUPPORT_CHANNEL
from SHASHA_DRUGZ.misc import SUDOERS

# ----------------------------------------------------
# HELPER: ensure _ is a dict
# ----------------------------------------------------
def safe_lang(lang):
    if isinstance(lang, dict):
        return lang
    try:
        return get_string(lang)
    except:
        return get_string("en")

# ----------------------------------------------------
# GLOBAL STORES
# ----------------------------------------------------
HELP_MENUS: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

PLUGINS_PATH = "SHASHA_DRUGZ/plugins"


# ----------------------------------------------------
# LOAD MODULE HELPS
# ----------------------------------------------------
def load_module_helps():
    for root, _, files in os.walk(PLUGINS_PATH):
        for file in files:
            if not file.endswith(".py") or file.startswith("_"):
                continue

            module_path = (
                os.path.join(root, file)
                .replace("/", ".")
                .replace("\\", ".")
                .replace(".py", "")
            )

            try:
                module = importlib.import_module(module_path)
            except Exception:
                continue

            menu = getattr(module, "__menu__", None)
            mod_name = getattr(module, "__mod_name__", None)
            help_text = getattr(module, "__help__", None)

            if not (menu and mod_name and help_text):
                continue

            HELP_MENUS[menu][mod_name].append(help_text.strip())


load_module_helps()


# ----------------------------------------------------
# KEYBOARDS
# ----------------------------------------------------
def main_menu_kb(_):
    """Main menu: buttons arranged as 2,1,2,1,... per row"""
    buttons = []
    row = []
    menu_keys = sorted(HELP_MENUS.keys())

    for idx, menu_key in enumerate(menu_keys):
        row.append(
            InlineKeyboardButton(
                text=_[menu_key],
                callback_data=f"help_menu {menu_key}",
            )
        )
        # Determine when to finalize row based on pattern 2,1,2,1...
        if idx % 3 == 1:          # after second button of a 2‑button block
            buttons.append(row)
            row = []
        elif idx % 3 == 2:         # after a single‑button block
            buttons.append(row)
            row = []

    if row:                         # leftover buttons (should not happen with pattern)
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


def module_menu_kb(menu_key, page, total_pages, _):
    """Submenu: 9 modules per page, rows [3,3,2,1] + navigation"""
    mod_keys = sorted(HELP_MENUS[menu_key].keys())
    start = page * 9
    end = start + 9
    page_mods = mod_keys[start:end]

    # Build module buttons using fixed row lengths
    row_lengths = [3, 3, 2, 1]
    buttons = []
    idx = 0
    for length in row_lengths:
        if idx >= len(page_mods):
            break
        row_btns = []
        for j in range(length):
            if idx < len(page_mods):
                mod_key = page_mods[idx]
                row_btns.append(
                    InlineKeyboardButton(
                        text=_[mod_key],
                        callback_data=f"help_mod {menu_key}|{mod_key}",
                    )
                )
                idx += 1
            else:
                break
        if row_btns:
            buttons.append(row_btns)

    # Navigation row: Back / Next (Back on first page goes to main menu)
    nav_btns = []
    if page > 0:
        nav_btns.append(
            InlineKeyboardButton(
                _["BACK_BUTTON"],
                callback_data=f"help_menu {menu_key} {page-1}",
            )
        )
    else:
        nav_btns.append(
            InlineKeyboardButton(
                _["BACK_BUTTON"],
                callback_data="settings_back_helper",
            )
        )

    if page < total_pages - 1:
        nav_btns.append(
            InlineKeyboardButton(
                _["NEXT_BUTTON"],
                callback_data=f"help_menu {menu_key} {page+1}",
            )
        )

    if nav_btns:
        buttons.append(nav_btns)

    return InlineKeyboardMarkup(buttons)


# ----------------------------------------------------
# PRIVATE HELP (MAIN MENU)
# ----------------------------------------------------
@app.on_message(filters.command(["help"]) & filters.private & ~BANNED_USERS)
@app.on_callback_query(filters.regex("settings_back_helper") & ~BANNED_USERS)
async def helper_private(
    client: app, update: Union[types.Message, types.CallbackQuery]
):
    is_callback = isinstance(update, types.CallbackQuery)

    if is_callback:
        try:
            await update.answer()
        except:
            pass

        chat_id = update.message.chat.id
        language = await get_lang(chat_id)
        _ = get_string(language)

        await update.message.edit_text(
            _["help_1"],
            reply_markup=main_menu_kb(_),
        )
    else:
        try:
            await update.delete()
        except:
            pass

        language = await get_lang(update.chat.id)
        _ = get_string(language)

        await update.reply_photo(
            photo=START_IMG_URL,
            caption=_["help_1"],
            reply_markup=main_menu_kb(_),
        )


# ----------------------------------------------------
# GROUP HELP
# ----------------------------------------------------
@app.on_message(filters.command(["help"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def help_group(_, message: Message, _lang):
    await message.reply_text(
        _lang["help_2"],
        reply_markup=main_menu_kb(_lang),
    )


# ----------------------------------------------------
# MENU CALLBACK (with pagination)
# ----------------------------------------------------
@app.on_callback_query(filters.regex("^help_menu") & ~BANNED_USERS)
@languageCB
async def help_menu_cb(client, cq: CallbackQuery, _):
    parts = cq.data.split()
    menu_key = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    if menu_key not in HELP_MENUS:
        return await cq.answer("Invalid menu", show_alert=True)

    mod_keys = sorted(HELP_MENUS[menu_key].keys())
    total_pages = (len(mod_keys) + 8) // 9   # ceil division

    if page < 0 or page >= total_pages:
        page = 0

    await cq.message.edit_text(
        _["help_1"],
        reply_markup=module_menu_kb(menu_key, page, total_pages, _),
    )
    await cq.answer()


# ----------------------------------------------------
# MODULE HELP CALLBACK (fixed with safe_lang)
# ----------------------------------------------------
@app.on_callback_query(filters.regex("^help_mod") & ~BANNED_USERS)
@languageCB
async def help_module_cb(client, cq: CallbackQuery, _):
    _, data = cq.data.split(None, 1)
    menu_key, mod_key = data.split("|", 1)

    helps = HELP_MENUS.get(menu_key, {}).get(mod_key)
    if not helps:
        return await cq.answer("No help found", show_alert=True)

    lang = safe_lang(_)

    text = f"<blockquote><b>{lang.get(mod_key, mod_key)}</b></blockquote>\n"

    combined = []
    for h in helps:
        combined.extend(h.splitlines())

    text += "<blockquote>"
    for line in combined:
        text += f"{line}\n"
    text += "</blockquote>"

    text += (
        "\n⋆｡°✩ **𝐇ʙ-𝐅ᴀᴍ** ✩°｡⋆\n"
        f"[ʜᴇᴧꝛᴛʙᴇᴧᴛ ᴏғғɪᴄɪᴧʟ]({SUPPORT_CHANNEL}) | "
        f"[ʜᴇᴧꝛᴛʙᴇᴧᴛ ᴄʜᴧᴛ]({SUPPORT_CHAT})"
    )

    await cq.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    lang.get("BACK_BUTTON", "Back"),
                    callback_data=f"help_menu {menu_key}"
                )
            ]]
        ),
        disable_web_page_preview=True,
    )
    await cq.answer()
