from pyrogram import Client, filters
from youtubesearchpython.__future__ import VideosSearch

from SHASHA_DRUGZ import app

print("[get_thumb] getthumb")


@app.on_message(filters.command("getthumb", prefixes="/"))
async def get_thumbnail_command(client, message):
    try:
        # Check if ID provided
        if len(message.command) < 2:
            return await message.reply("❌ Usage: `/getthumb <video-id or search query>`", quote=True)

        query = message.text.split(None, 1)[1]

        # Perform YouTube search
        results = VideosSearch(query, limit=1)
        data = await results.next()

        if not data.get("result"):
            return await message.reply("❌ No results found. Try a different query.", quote=True)

        result = data["result"][0]

        # Get thumbnail safely
        thumbnail_url = result["thumbnails"][0]["url"].split("?")[0]

        await message.reply_photo(
            thumbnail_url,
            caption=f"**🎬 Title:** {result.get('title', 'Unknown')}\n\n"
                    f"**🔗 URL:** {result.get('link', 'Unavailable')}"
        )

    except Exception as e:
        await message.reply(f"⚠️ Error: `{e}`", quote=True)


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_8"
__help__ = """
🔻 /getthumb <video name | video id | youtube link> ➠ ɢᴇᴛs ʏᴏᴜᴛᴜʙᴇ ᴠɪᴅᴇᴏ ᴛʜᴜᴍʙɴᴀɪʟ ᴡɪᴛʜ ᴛɪᴛʟᴇ & ʟɪɴᴋ
"""
