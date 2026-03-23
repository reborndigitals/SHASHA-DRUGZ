from pyrogram.types import InlineKeyboardButton
from SHASHA_DRUGZ.mongo.deploydb import get_deployed_bot_by_id
from SHASHA_DRUGZ.utils.database import get_lang
from SHASHA_DRUGZ.utils.decorators.language import LanguageStart, languageCB
from strings import get_string


# ----------------------------------------------------
# SAFE LANGUAGE
# ----------------------------------------------------
def safe_lang(lang):
    if isinstance(lang, dict):
        return lang
    try:
        return get_string(lang)
    except Exception:
        return get_string("en")


# ----------------------------------------------------
# OWNER BUTTON BUILDER
# ----------------------------------------------------
async def downer_button(client, chat_id: int):
    """
    Build OWNER button dynamically for the running deployed bot
    with language support.

    Priority:
    1. Use owner's username (if available)
    2. Fallback to tg://user?id=OWNER_ID
    """

    # 🔹 Load language
    language = await get_lang(chat_id)
    _ = safe_lang(language)

    me = await client.get_me()
    bot = await get_deployed_bot_by_id(me.id)

    if not bot:
        return None  # safety

    owner_id = bot["owner_id"]

    try:
        owner = await client.get_users(owner_id)

        # ✅ If username exists → use username link
        if owner.username:
            return InlineKeyboardButton(
                _["D_OWNER"],
                url=f"https://t.me/{owner.username}",
            )

    except Exception:
        pass  # fallback if user fetch fails

    # ✅ Fallback → Use user ID
    return InlineKeyboardButton(
        _["D_OWNER"],
        url=f"tg://user?id={owner_id}",
    )
