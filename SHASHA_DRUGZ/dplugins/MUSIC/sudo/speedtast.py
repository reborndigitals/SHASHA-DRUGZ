
import asyncio
import speedtest
from pyrogram import Client, filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.decorators.language import language


def testspeed():
    """Run speedtest in a blocking function."""
    try:
        test = speedtest.Speedtest()
        test.get_best_server()
        test.download()
        test.upload()
        test.results.share()
        return test.results.dict()
    except Exception as e:
        return {"error": str(e)}


@Client.on_message(filters.command(["speedtest", "spt"], prefixes=["/", "!", "%", ",", "", ".", "@", "#"]) & SUDOERS)
@language
async def speedtest_function(client, message: Message, _):
    # Send initial message once
    status_msg = await message.reply_text(_["server_11"])

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, testspeed)

    if "error" in result:
        await status_msg.edit_text(f"<code>{result['error']}</code>")
        return

    output = _["server_15"].format(
        result["client"]["isp"],
        result["client"]["country"],
        result["server"]["name"],
        result["server"]["country"],
        result["server"]["cc"],
        result["server"]["sponsor"],
        result["server"]["latency"],
        result["ping"],
    )

    # Send final result
    await message.reply_photo(photo=result["share"], caption=output)
    # Delete initial status message
    await status_msg.delete()

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_59"
__help__ = """
🔻 /speedtest, /spt ➠ ʀᴜɴ sᴘᴇᴇᴅ ᴛᴇꜱᴛ
"""
MOD_TYPE = "SUDO"
MOD_NAME = "SpeedTest"
MOD_PRICE = "50"
