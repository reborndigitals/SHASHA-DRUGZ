# SHASHA_DRUGZ/dplugins/COMMON/bot/help.py
import sys
from collections import defaultdict
from typing import Dict, List, Union
from pyrogram import Client, filters, types
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)
from pyrogram.errors import MessageNotModified
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.utils.database import get_lang
from SHASHA_DRUGZ.utils.decorators.language import LanguageStart, languageCB
from strings import get_string
from config import BANNED_USERS
from SHASHA_DRUGZ.mongo.deploydb import get_deployed_bot_by_id
# Per-bot settings — image and support links read from DB
from SHASHA_DRUGZ.utils.bot_settings import (
    get_start_image,
    get_support_chat,
    get_support_channel,
)

def safe_lang(lang):
    if isinstance(lang, dict):
        return lang
    try:
        return get_string(lang)
    except Exception:
        return get_string("en")

# ── Per-client help cache so Bot A never sees Bot B's modules ─────────────────
_HELP_CACHE: Dict[int, Dict] = {}

def _get_menus(client_id: int) -> Dict:
    if client_id not in _HELP_CACHE:
        _HELP_CACHE[client_id] = defaultdict(lambda: defaultdict(list))
    return _HELP_CACHE[client_id]

async def load_module_helps(client: Client):
    bot_id   = client.me.id
    menus    = _get_menus(bot_id)
    menus.clear()
    bot_data = await get_deployed_bot_by_id(bot_id)
    allowed_plugins = set(bot_data.get("plugins", [])) if bot_data else None
    for module in list(sys.modules.values()):
        try:
            menu        = getattr(module, "__menu__",     None)
            mod_name    = getattr(module, "__mod_name__", None)
            help_text   = getattr(module, "__help__",     None)
            module_path = getattr(module, "__name__",     "")
        except Exception:
            continue
        if not (menu and mod_name and help_text):
            continue
        parts = module_path.split("SHASHA_DRUGZ.dplugins.")
        if len(parts) != 2:
            continue
        plugin_path = parts[1]
        if allowed_plugins is not None and plugin_path not in allowed_plugins:
            continue
        menus[menu][mod_name].append(help_text.strip())

async def main_menu_kb(client: Client, lang_dict: dict) -> InlineKeyboardMarkup:
    menus     = _get_menus(client.me.id)
    menu_keys = sorted(menus.keys())
    if not menu_keys:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("No Modules Available", callback_data="noop")
        ]])
    buttons, row = [], []
    for idx, menu_key in enumerate(menu_keys):
        row.append(InlineKeyboardButton(
            text=lang_dict.get(menu_key, menu_key),
            callback_data=f"help_menu {menu_key}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def module_menu_kb(
    client: Client, menu_key: str, page: int, total_pages: int, lang_dict: dict
) -> InlineKeyboardMarkup:
    """
    Build the module list keyboard for a given menu category.

    BUG FIX: the original code used `_` as both the language-dict parameter
    AND as the for-loop variable (`for _ in range(length)`), which silently
    shadowed the dict and made `_.get(mk, mk)` impossible. Fixed by:
      1. Renaming the loop variable to `_i`
      2. Using `lang_dict.get(mk, mk)` for human-readable button labels
         (mod_name values like "H_B_2" are language-string keys, not display names)
    """
    menus     = _get_menus(client.me.id)
    mod_keys  = sorted(menus[menu_key].keys())
    page_mods = mod_keys[page * 9:(page + 1) * 9]
    buttons, idx = [], 0
    for length in [3, 3, 2, 1]:
        if idx >= len(page_mods):
            break
        row_btns = []
        for _i in range(length):  # FIX: was `for _ in range(length)` — shadowed lang dict
            if idx < len(page_mods):
                mk = page_mods[idx]
                row_btns.append(InlineKeyboardButton(
                    # FIX: was `text=mk` — showed raw "H_B_2" instead of human name
                    # Now looks up the language string; falls back to key if not found
                    text=lang_dict.get(mk, mk),
                    callback_data=f"help_mod {menu_key}|{mk}"
                ))
                idx += 1
        if row_btns:
            buttons.append(row_btns)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Back", callback_data=f"help_menu {menu_key} {page-1}"))
    else:
        nav.append(InlineKeyboardButton("◀ Back", callback_data="settings_back_helper"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"help_menu {menu_key} {page+1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)

async def _safe_edit(cq: CallbackQuery, text: str, reply_markup=None, **kwargs):
    try:
        await cq.message.edit_text(text, reply_markup=reply_markup, **kwargs)
    except MessageNotModified:
        pass
    except Exception as e:
        import logging
        logging.warning(f"[help.py] edit_text failed: {e}")

@Client.on_message(filters.command(["help"]) & filters.private & ~BANNED_USERS)
@Client.on_callback_query(filters.regex("settings_back_helper") & ~BANNED_USERS)
async def helper_private(
    client: Client, update: Union[types.Message, types.CallbackQuery]
):
    await load_module_helps(client)
    is_cb = isinstance(update, types.CallbackQuery)

    if is_cb:
        try:
            await update.answer()
        except Exception:
            pass
        language = await get_lang(update.message.chat.id)
        lang_dict = get_string(language)
        await _safe_edit(
            update, lang_dict["dhelp_1"],
            reply_markup=await main_menu_kb(client, lang_dict)
        )
    else:
        try:
            await update.delete()
        except Exception:
            pass
        language  = await get_lang(update.chat.id)
        lang_dict = get_string(language)

        # FIX: Read start image directly from per-bot DB instead of config proxy.
        # The config proxy (_BotStr) needs the cache to be warmed via apply_to_config()
        # in deploy.py. get_start_image() reads from the DB directly with its own
        # fallback, so it always returns the correct stored value.
        bot_id    = client.me.id
        photo_url = await get_start_image(bot_id)

        await update.reply_photo(
            photo=photo_url,
            caption=lang_dict["dhelp_1"],
            reply_markup=await main_menu_kb(client, lang_dict),
        )

@Client.on_message(filters.command(["help"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def help_group(client: Client, message: Message, _lang):
    await load_module_helps(client)
    await message.reply_text(
        _lang["dhelp_1"],
        reply_markup=await main_menu_kb(client, _lang)
    )

@Client.on_callback_query(filters.regex("^help_menu") & ~BANNED_USERS)
@languageCB
async def help_menu_cb(client: Client, cq: CallbackQuery, lang_dict):
    await load_module_helps(client)
    parts    = cq.data.split()
    menu_key = parts[1]
    page     = int(parts[2]) if len(parts) > 2 else 0
    menus = _get_menus(client.me.id)
    if menu_key not in menus:
        return await cq.answer("Invalid menu", show_alert=True)
    mod_keys    = sorted(menus[menu_key].keys())
    total_pages = max(1, (len(mod_keys) + 8) // 9)
    page        = max(0, min(page, total_pages - 1))
    await _safe_edit(
        cq, lang_dict["dhelp_1"],
        reply_markup=await module_menu_kb(client, menu_key, page, total_pages, lang_dict)
    )
    try:
        await cq.answer()
    except Exception:
        pass

@Client.on_callback_query(filters.regex("^help_mod") & ~BANNED_USERS)
@languageCB
async def help_module_cb(client: Client, cq: CallbackQuery, lang_dict):
    try:
        _, data           = cq.data.split(None, 1)
        menu_key, mod_key = data.split("|", 1)
    except ValueError:
        return await cq.answer("Invalid data", show_alert=True)

    menus = _get_menus(client.me.id)
    helps = menus.get(menu_key, {}).get(mod_key)
    if not helps:
        return await cq.answer("No help found", show_alert=True)

    # Resolve language dict — @languageCB passes the lang code or dict
    resolved = safe_lang(lang_dict)

    # Read per-bot support links from DB (falls back to config defaults)
    bot_id      = client.me.id
    sup_channel = await get_support_channel(bot_id)
    sup_chat    = await get_support_chat(bot_id)

    # Use human-readable display name from language dict; fall back to raw key
    display_name = resolved.get(mod_key, mod_key)

    text = f"<blockquote><b>{display_name}</b></blockquote>\n<blockquote>"
    for h in helps:
        text += f"{h}\n"
    text += (
        f"</blockquote>\n⋆｡°✩ **ɴᴇᴛᴡᴏꝛᴋ** ✩°｡⋆\n"
        f"[ᴜᴘᴅᴧᴛᴇ𝗌]({sup_channel}) | [𝗌ᴜᴘᴘᴏꝛᴛ]({sup_chat})"
    )
    await _safe_edit(
        cq, text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                resolved.get("BACK_BUTTON", "◀ Back"),
                callback_data=f"help_menu {menu_key}"
            )
        ]]),
        disable_web_page_preview=True,
    )
    try:
        await cq.answer()
    except Exception:
        pass
