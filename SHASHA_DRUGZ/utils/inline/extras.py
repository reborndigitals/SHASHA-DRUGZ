from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config


def botplaylist_markup(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["S_B_9"], url=config.SUPPORT_CHAT),
            InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close"),
        ],
    ]
    return buttons


def close_markup(_):
    upl = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data="close"),
            ]
        ]
    )
    return upl


def supp_markup(_):
    upl = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text=_["S_B_9"], url=config.SUPPORT_CHAT),
            ]
        ]
    )
    return upl
