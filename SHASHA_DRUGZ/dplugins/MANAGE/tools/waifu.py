import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from SHASHA_DRUGZ import app


@Client.on_message(filters.command("waifu"))
async def waifu_command_handler(client: Client, message: Message):
    try:
        args = message.text.split(maxsplit=1)
        tag = args[1] if len(args) > 1 else "maid"

        waifu_data = get_waifu_data(tag)

        if waifu_data and 'images' in waifu_data and waifu_data['images']:
            image = waifu_data['images'][0]
            await message.reply_photo(
                photo=image["url"],
                caption=f"🌸 ʜᴇʀᴇ'ꜱ ʏᴏᴜʀ ᴡᴀɪꜰᴜ ({tag})"
            )
        else:
            await message.reply_text("❌ ɴᴏ ᴡᴀɪꜰᴜꜱ ꜰᴏᴜɴᴅ ᴡɪᴛʜ ᴛʜᴀᴛ ᴛᴀɢ.")

    except Exception as e:
        await message.reply_text(f"⚠️ ᴇʀʀᴏʀ: `{str(e)}`")


def get_waifu_data(tag):
    try:
        response = requests.get(
            "https://api.waifu.im/search",
            params={
                "included_tags": tag,
                "height": ">=2000"
            }
        )
        if response.status_code == 200:
            return response.json()
    except:
        return None

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_60"
__help__ = """
🔻 /waifu [tag] ➠ sᴇɴᴅs ʏᴏᴜ ᴀ ʀᴀɴᴅᴏᴍ ᴡᴀɪꜰᴜ ɪᴍᴀɢᴇ. ᴅᴇꜰᴀᴜʟᴛ ᴛᴀɢ: ᴍᴀɪᴅ
"""

MOD_TYPE = "MANAGEMENT"
MOD_NAME = "Waifu"
MOD_PRICE = "20"
