from pyrogram import Client, filters
import random
from SHASHA_DRUGZ import app

print("[love] love")

def get_random_message(love_percentage):
    if love_percentage <= 30:
        return random.choice([
            "Love is in the air but needs a little spark.",
            "A good start but there's room to grow.",
            "It's just the beginning of something beautiful."
        ])
    elif love_percentage <= 70:
        return random.choice([
            "A strong connection is there. Keep nurturing it.",
            "You've got a good chance. Work on it.",
            "Love is blossoming, keep going."
        ])
    else:
        return random.choice([
            "Wow! It's a match made in heaven!",
            "Perfect match! Cherish this bond.",
            "Destined to be together. Congratulations!"
        ])
        
@Client.on_message(filters.command("love", prefixes="/"))
def love_command(client, message):
    command, *args = message.text.split(" ")
    if len(args) >= 2:
        name1 = args[0].strip()
        name2 = args[1].strip()
        
        love_percentage = random.randint(10, 100)
        love_message = get_random_message(love_percentage)

        response = f"{name1}💕 + {name2}💕 = {love_percentage}%\n\n{love_message}"
    else:
        response = "Please enter two names after /love command."
    app.send_message(message.chat.id, response)


__menu__ = "CMD_MENTION"
__mod_name__ = "H_B_33"
__help__ = """
🔻 /love <name1> <name2> ➠ ᴄᴀʟᴄᴜʟᴀᴛᴇs ʟᴏᴠᴇ ᴘᴇʀᴄᴇɴᴛᴀɢᴇ ʙᴇᴛᴡᴇᴇɴ ᴛᴡᴏ ɴᴀᴍᴇs ᴡɪᴛʜ ᴀ ʀᴀɴᴅᴏᴍ ᴍᴇssᴀɢᴇ
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "LoveCalc"
MOD_PRICE = "20"
