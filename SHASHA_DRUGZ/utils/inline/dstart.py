# SHASHA_DRUGZ/utils/inline/dstart.py
#
# CHANGES vs original:
#   1. dstart_panel / dprivate_panel now read support_chat and support_channel
#      from per-bot DB settings via bot_settings utility.
#   2. config.SUPPORT_CHAT / SUPPORT_CHANNEL are used ONLY as fallback.
#   3. bot_id is derived from client.me.id (non-blocking; .me is always
#      populated when handlers fire).
# ─────────────────────────────────────────────────────────────────────────────
from pyrogram.types import InlineKeyboardButton
import config
from SHASHA_DRUGZ import app
from .downer import downer_button

# ── NEW: per-bot settings reader ─────────────────────────────────────────────
from SHASHA_DRUGZ.utils.bot_settings import get_support_chat, get_support_channel


async def dstart_panel(client, _, chat_id):
    """
    Inline keyboard for group /start.
    Support/channel buttons come from per-bot DB settings.
    """
    bot_id = client.me.id if client.me else app.id

    # Read per-bot links; falls back to global config if not set
    sup_chat    = await get_support_chat(bot_id)
    sup_channel = await get_support_channel(bot_id)

    # OWNER button
    downer_btn = await downer_button(client, chat_id)

    buttons = [
        [
            InlineKeyboardButton(
                text=_["S_B_1"],
                url=f"https://t.me/{client.me.username}?startgroup=true"
            ),
        ],
        [
            InlineKeyboardButton(
                text=_["S_B_12"],
                callback_data="settings_back_helper"
            ),
        ],
        [
            InlineKeyboardButton(text=_["CHT"], url=sup_chat),
            InlineKeyboardButton(text=_["NET"], url=sup_channel),
            InlineKeyboardButton(
                text=_["DEV"],
                url=f"https://t.me/{config.OWNER_USERNAME}"
            ),
        ],
    ]

    # REPO row
    repo_row = [
        InlineKeyboardButton(
            text=_["REPO"],
            url="https://github.com/GhosttBatt/ShashaOffi"
        )
    ]
    if downer_btn:
        repo_row.append(downer_btn)
    buttons.append(repo_row)

    return buttons


async def dprivate_panel(client, _, chat_id):
    """
    Inline keyboard for private /start.
    Support/channel buttons come from per-bot DB settings.
    """
    bot_id = client.me.id if client.me else app.id

    sup_chat    = await get_support_chat(bot_id)
    sup_channel = await get_support_channel(bot_id)

    downer_btn = await downer_button(client, chat_id)

    buttons = [
        [
            InlineKeyboardButton(
                text=_["S_B_1"],
                url=f"https://t.me/{client.me.username}?startgroup=true"
            )
        ]
    ]

    # REPO + OWNER row
    repo_row = [
        InlineKeyboardButton(
            text=_["REPO"],
            url="https://github.com/GhosttBatt/ShashaOffi"
        )
    ]
    if downer_btn:
        repo_row.append(downer_btn)
    buttons.append(repo_row)

    buttons.append([
        InlineKeyboardButton(
            text=_["S_B_4"],
            callback_data="settings_back_helper"
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text=_["DEV"],
            url=f"https://t.me/{config.OWNER_USERNAME}"
        ),
        InlineKeyboardButton(text=_["CHT"], url=sup_chat),
        InlineKeyboardButton(text=_["NET"], url=sup_channel),
    ])

    return buttons
