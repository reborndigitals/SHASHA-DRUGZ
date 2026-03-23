from pyrogram.types import InlineKeyboardButton
import config
from SHASHA_DRUGZ import app

def start_panel(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["S_B_1"], url=f"https://t.me/{app.username}?startgroup=true"),
        ],
        [
            InlineKeyboardButton(text=_["S_B_12"], callback_data="settings_back_helper"),
        ],
        [
            InlineKeyboardButton(text=_["CHT"], url=config.SUPPORT_CHAT),
            InlineKeyboardButton(text=_["NET"], url=config.SUPPORT_CHANNEL),
        ],
        [
            InlineKeyboardButton(text=_["DEV"], url=f"https://t.me/{config.OWNER_USERNAME}"),
            InlineKeyboardButton(text=_["DEPLOY"], callback_data="deploy_start"),
        ],
    ]
    return buttons

def private_panel(_):
    buttons = [
        [
            InlineKeyboardButton( text=_["S_B_1"], url=f"https://t.me/{app.username}?startgroup=true")
        ],
        [
            InlineKeyboardButton(text=_["CHT"], url=config.SUPPORT_CHAT),
            InlineKeyboardButton(text=_["NET"], url=config.SUPPORT_CHANNEL),
        ],
        [
            InlineKeyboardButton(text=_["S_B_4"], callback_data="settings_back_helper")
        ],
        [
            InlineKeyboardButton(text=_["DEV"], url=f"https://t.me/{config.OWNER_USERNAME}"),
            InlineKeyboardButton(text=_["DEPLOY"], callback_data="deploy_start"),
        ],
    ]
    return buttons
