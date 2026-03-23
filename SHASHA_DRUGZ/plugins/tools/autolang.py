from pyrogram import filters
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup
from SHASHA_DRUGZ import app
from strings import get_string, languages_present
from SHASHA_DRUGZ.utils.database import get_lang, set_lang
from SHASHA_DRUGZ.utils.decorators import language
from pykeyboard import InlineKeyboard
from pyrogram.types import InlineKeyboardButton
from config import BANNED_USERS


def languages_keyboard(_):
    keyboard = InlineKeyboard(row_width=2)
    keyboard.add(
        *[
            InlineKeyboardButton(
                text=languages_present[i],
                callback_data=f"languages:{i}",
            )
            for i in languages_present
        ]
    )
    keyboard.row(
        InlineKeyboardButton(
            text=_["BACK_BUTTON"], callback_data=f"settingsback_helper"
        ),
        InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data=f"close"),
    )
    return keyboard


@app.on_chat_member_updated(filters.group)
async def send_lang_message(_, member: ChatMemberUpdated):
    """Automatically sends the set language message when the bot is added to a group."""

    # Check if the bot was just added
    if (
        member.new_chat_member
        and member.new_chat_member.user.is_self  # the bot itself
        and member.old_chat_member is None
    ):
        chat = member.chat
        _ = get_string("en")  # Default to English for initial message
        keyboard = languages_keyboard(_)

        await app.send_message(
            chat.id,
            _["lang_1"],  # “Please choose your language” text
            reply_markup=keyboard,
        )
