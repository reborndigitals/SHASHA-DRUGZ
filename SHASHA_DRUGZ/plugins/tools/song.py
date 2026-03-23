import os
import asyncio
import requests
import time
import yt_dlp
from time import time

# FIX: Import from the correct library matching your code logic (.to_dict)
from youtube_search import YoutubeSearch 

from pyrogram import filters, Client
from pyrogram.types import Message

from SHASHA_DRUGZ import app

print("[song] song, insta, reel")

# ------------------- SPAM PROTECTION -------------------
user_last_message_time = {}
user_command_count = {}
SPAM_THRESHOLD = 2
SPAM_WINDOW_SECONDS = 5

async def check_spam(message):
    user_id = message.from_user.id
    current_time = time()
    last_message_time = user_last_message_time.get(user_id, 0)

    if current_time - last_message_time < SPAM_WINDOW_SECONDS:
        user_last_message_time[user_id] = current_time
        user_command_count[user_id] = user_command_count.get(user_id, 0) + 1
        if user_command_count[user_id] > SPAM_THRESHOLD:
            hu = await message.reply_text(f"**{message.from_user.mention} ᴘʟᴇᴀsᴇ ᴅᴏɴᴛ ᴅᴏ sᴘᴀᴍ, ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ ᴀғᴛᴇʀ 5 sᴇᴄ**")
            await asyncio.sleep(3)
            try:
                await hu.delete()
            except:
                pass
            return True
    else:
        user_command_count[user_id] = 1
        user_last_message_time[user_id] = current_time
    return False

# ------------------- SONG DOWNLOAD -------------------

@app.on_message(filters.command("song"))
async def download_song(client, message):
    if await check_spam(message):
        return

    if len(message.command) < 2:
        return await message.reply_text("usage: /song [song name]")

    query = " ".join(message.command[1:])  
    m = await message.reply("**🔄 sᴇᴀʀᴄʜɪɴɢ... **")
    
    ydl_ops = {"format": "bestaudio[ext=m4a]"}
    
    try:
        # Using youtube_search library
        results = YoutubeSearch(query, max_results=1).to_dict()
        if not results:
            await m.edit("**⚠️ ɴᴏ ʀᴇsᴜʟᴛs ᴡᴇʀᴇ ғᴏᴜɴᴅ. ᴍᴀᴋᴇ sᴜʀᴇ ʏᴏᴜ ᴛʏᴘᴇᴅ ᴛʜᴇ ᴄᴏʀʀᴇᴄᴛ sᴏɴɢ ɴᴀᴍᴇ**")
            return

        link = f"https://youtube.com{results[0]['url_suffix']}"
        title = results[0]["title"][:40]
        thumbnail = results[0]["thumbnails"][0]
        thumb_name = f"{title}.jpg"
        
        thumb = requests.get(thumbnail, allow_redirects=True)
        open(thumb_name, "wb").write(thumb.content)
        
        duration = results[0]["duration"]
        views = results[0]["views"]
        channel_name = results[0]["channel"]

    except Exception as e:
        await m.edit("**⚠️ ɴᴏ ʀᴇsᴜʟᴛs ᴡᴇʀᴇ ғᴏᴜɴᴅ. ᴍᴀᴋᴇ sᴜʀᴇ ʏᴏᴜ ᴛʏᴘᴇᴅ ᴛʜᴇ ᴄᴏʀʀᴇᴄᴛ sᴏɴɢ ɴᴀᴍᴇ**")
        print(str(e))
        return

    await m.edit("**📥 ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...**")
    
    audio_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_ops) as ydl:
            info_dict = ydl.extract_info(link, download=False)
            audio_file = ydl.prepare_filename(info_dict)
            ydl.process_info(info_dict)
        
        secmul, dur, dur_arr = 1, 0, duration.split(":")
        for i in range(len(dur_arr) - 1, -1, -1):
            dur += int(float(dur_arr[i])) * secmul
            secmul *= 60
            
        await m.edit("**📤 ᴜᴘʟᴏᴀᴅɪɴɢ...**")

        await message.reply_audio(
            audio_file,
            thumb=thumb_name,
            title=title,
            caption=f"{title}\nRᴇǫᴜᴇsᴛᴇᴅ ʙʏ ➪{message.from_user.mention}\nVɪᴇᴡs➪ {views}\nCʜᴀɴɴᴇʟ➪ {channel_name}",
            duration=dur
        )
        await m.delete()
    except Exception as e:
        await m.edit(" - An error !!")
        print(e)

    # Cleanup
    try:
        if audio_file and os.path.exists(audio_file):
            os.remove(audio_file)
        if os.path.exists(thumb_name):
            os.remove(thumb_name)
    except Exception as e:
        print(e)


# ------------------- INSTAGRAM DD METHOD -------------------

@app.on_message(filters.command(["ig", "insta"], ["/", "!", "."]))
async def download_instareels(client, message):
    if await check_spam(message):
        return

    try:
        if len(message.command) < 2:
            await message.reply_text("Give me an link to download it...")
            return
        
        reel_ = message.command[1]
    except IndexError:
        await message.reply_text("Give me an link to download it...")
        return

    if not reel_.startswith("https://www.instagram.com/"):
        await message.reply_text("In order to obtain the requested reel, a valid link is necessary.")
        return
    
    # DDInstagram Method
    OwO = reel_.split(".", 1)
    Reel_ = ".dd".join(OwO)
    
    try:
        await message.reply_video(Reel_)
        return
    except Exception:
        try:
            await message.reply_photo(Reel_)
            return
        except Exception:
            try:
                await message.reply_document(Reel_)
                return
            except Exception:
                await message.reply_text("I am unable to reach to this reel.")


# ------------------- INSTAGRAM API METHOD -------------------

@app.on_message(filters.command(["reel"], ["/", "!", "."]))
async def instagram_reel(client, message):
    if await check_spam(message):
        return

    if len(message.command) == 2:
        url = message.command[1]
        try:
            response = requests.post(f"https://lexica-api.vercel.app/download/instagram?url={url}")
            data = response.json()

            if data['code'] == 2:
                media_urls = data['content']['mediaUrls']
                if media_urls:
                    video_url = media_urls[0]['url']
                    await message.reply_video(f"{video_url}")
                else:
                    await message.reply("No video found in the response. Account might be private.")
            else:
                await message.reply("Request was not successful.")
        except Exception as e:
            await message.reply(f"Error: {e}")
    else:
        await message.reply("Please provide a valid Instagram URL using the /reel command.")

__menu__ = "CMD_MUSIC"
__mod_name__ = "H_B_8"
__help__ = """
🔻 /song <name> ➠ ᴅᴏᴡɴʟᴏᴀᴅꜱ ᴀᴜᴅɪᴏ ꜰʀᴏᴍ ʏᴏᴜᴛᴜʙᴇ
🔻 /ig /reel <link> ➠ ᴅᴏᴡɴʟᴏᴀᴅꜱ ɪɴꜱᴛᴀ ʀᴇᴇʟ / ᴘᴏꜱᴛ
🔻 /insta <link> ➠ ᴅᴏᴡɴʟᴏᴀᴅꜱ ɪɴꜱᴛᴀ ᴍᴇᴅɪᴀ
"""
