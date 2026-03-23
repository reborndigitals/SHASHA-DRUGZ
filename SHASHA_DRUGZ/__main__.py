import asyncio
import importlib
import logging
from pyrogram import idle
from pyrogram.errors import FloodWait as PyroFloodWait
from telethon.errors import FloodWaitError as TelethonFloodWait
import config
from SHASHA_DRUGZ import LOGGER, app, userbot, telethn
from SHASHA_DRUGZ.core.call import SHASHA
from SHASHA_DRUGZ.misc import sudo
from SHASHA_DRUGZ.plugins import ALL_MODULES
from SHASHA_DRUGZ.utils.database import get_banned_users, get_gbanned
from config import BANNED_USERS
from autorestart import autorestart
from SHASHA_DRUGZ.plugins.PREMIUM.deploy import (
    restart_bots, expiry_checker, load_manual_modules_map
)
from SHASHA_DRUGZ.mongo.deploydb import ensure_indexes
from SHASHA_DRUGZ.plugins.PREMIUM.movebots import load_movebots


# ==========================================================
# HIDE ONLY: AttributeError: 'UpdateGroupCall' has no chat_id
# ==========================================================
class HideUpdateGroupCallError(logging.Filter):
    def filter(self, record):
        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            if exc_value and "UpdateGroupCall" in str(exc_value) and "chat_id" in str(exc_value):
                return False
        msg = record.getMessage()
        if "UpdateGroupCall" in msg and "chat_id" in msg:
            return False
        return True

dispatcher_logger = logging.getLogger("pyrogram.dispatcher")
dispatcher_logger.addFilter(HideUpdateGroupCallError())
# ==========================================================


# ==========================================================
# SAFE TELETHON START — auto waits on FloodWait
# ==========================================================
async def start_telethn_safe():
    while True:
        try:
            await telethn.start(bot_token=config.BOT_TOKEN)
            LOGGER(__name__).info("✅ Telethon started successfully.")
            break
        except TelethonFloodWait as e:
            wait = e.seconds
            LOGGER(__name__).warning(
                f"⚠️ Telethon FloodWait: waiting {wait}s "
                f"({wait // 60}m {wait % 60}s) before retrying..."
            )
            await asyncio.sleep(wait + 5)
        except Exception as e:
            LOGGER(__name__).error(f"Unexpected error starting Telethon: {e}")
            raise
# ==========================================================


# ==========================================================
# SAFE PYROGRAM START — auto waits on FloodWait
# ==========================================================
async def start_app_safe():
    while True:
        try:
            await app.start()
            LOGGER(__name__).info("✅ Pyrogram app started successfully.")
            break
        except PyroFloodWait as e:
            wait = e.value
            LOGGER(__name__).warning(
                f"⚠️ Pyrogram FloodWait: waiting {wait}s "
                f"({wait // 60}m {wait % 60}s) before retrying..."
            )
            await asyncio.sleep(wait + 5)
        except Exception as e:
            LOGGER(__name__).error(f"Unexpected error starting Pyrogram app: {e}")
            raise
# ==========================================================


async def init_bot():
    if (
        not config.STRING1
        and not config.STRING2
        and not config.STRING3
        and not config.STRING4
        and not config.STRING5
    ):
        LOGGER(__name__).error(
            "𝐒𝐭𝐫𝐢𝐧𝐠 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐍𝐨𝐭 𝐅𝐢𝐥𝐥𝐞𝐝, 𝐏𝐥𝐞𝐚𝐬𝐞 𝐅𝐢𝐥𝐥 𝐀 𝐏𝐲𝐫𝐨𝐠𝐫𝐚𝐦 V2 𝐒𝐞𝐬𝐬𝐢𝐨𝐧🤬"
        )
    await sudo()
    try:
        gb = await get_gbanned()
        for u in gb:
            BANNED_USERS.add(u)
        ban = await get_banned_users()
        for u in ban:
            BANNED_USERS.add(u)
    except:
        pass

    # Use safe Pyrogram start
    await start_app_safe()

    for all_module in ALL_MODULES:
        importlib.import_module("SHASHA_DRUGZ.plugins" + all_module)
    LOGGER("SHASHA_DRUGZ.plugins").info("𝐀𝐥𝐥 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐋𝐨𝐚𝐝𝐞𝐝🥳...")
    await userbot.start()
    await SHASHA.start()
    await SHASHA.decorators()
    LOGGER("SHASHA_DRUGZ").info(
        "\n╔═════════ஜ۩۞۩ஜ════════╗\n"
        "  ☠︎︎ 𝗠𝗔𝗗𝗘 𝗕𝗬 𝗛𝗘𝗔𝗥𝗧𝗕𝗘𝗔𝗧\n"
        "╚═════════ஜ۩۞۩ஜ════════╝\n"
    )


async def main():
    # Start Telethon safely
    await start_telethn_safe()

    # Ensure database indexes
    await ensure_indexes()

    # Load manual modules map
    load_manual_modules_map()

    # Initialize main bot (Pyrogram start is inside, also safe)
    await init_bot()

    # ================= MOVE BOTS LOADER =================
    try:
        await load_movebots()
    except Exception:
        logging.exception("Error while starting movebots.")
    # ====================================================

    # Restart all deployed bots
    try:
        await restart_bots()
    except Exception:
        logging.exception("Fatal error in restart_bots, but main bot continues.")

    # Start expiry checker background task
    asyncio.create_task(expiry_checker())

    LOGGER("SHASHA_DRUGZ").info(
        "\n\n\n"
        "  ___ ______________   _____ __________________________________________   ________________\n"
        " /   |   \\_   _____/  /  _  \\______   \\__    ___/\\______   \\_   _____/  /  _  \\__    ___/\n"
        "/    ~    \\    __)_  /  /_\\  \\|       _/ |    |    |    |  _/|    __)_  /  /_\\  \\|    |   \n"
        "\\    Y    /        \\/    |    \\    |   \\ |    |    |    |   \\|        \\/    |    \\    |   \n"
        " \\___|_  /_______  /\\____|__  /____|_  / |____|    |______  /_______  /\\____|__  /____|   \n"
        "       \\/        \\/         \\/       \\/                   \\/        \\/         \\/  \n\n\n       "
    )

    # Idle
    await idle()

    # Clean shutdown
    await telethn.disconnect()
    await userbot.stop()
    await app.stop()

    LOGGER("SHASHA_DRUGZ").info(
        "\n╔═════════ஜ۩۞۩ஜ════════╗\n"
        "  ☠︎︎ 𝗠𝗔𝗗𝗘 𝗕𝗬 𝗛𝗘𝗔𝗥𝗧𝗕𝗘𝗔𝗧\n"
        "╚═════════ஜ۩۞۩ஜ════════╝\n"
    )


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    LOGGER(__name__).info("AutoRestart system started.")
    try:
        autorestart()
    except KeyboardInterrupt:
        LOGGER(__name__).info("AutoRestart system stopped manually.")
    except Exception as e:
        LOGGER(__name__).error(f"Unexpected error: {e}")
