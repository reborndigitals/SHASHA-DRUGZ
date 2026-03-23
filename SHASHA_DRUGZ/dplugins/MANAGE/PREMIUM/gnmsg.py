import re
from pyrogram import Client, filters
import random
from SHASHA_DRUGZ import app



######### GOOD NIGHT 
@Client.on_message(filters.command(["n","oodnight","ight"], prefixes=["g","G","n","N"]))
def goodnight_command_handler(client: Client, message):
    sender = message.from_user.mention
    send_sticker = random.choice([True, False])
    if send_sticker:
        sticker_id = get_random_sticker()
        app.send_sticker(message.chat.id, sticker_id)
        message.reply_text(f"**Goodnight, {sender}! Sleep tight. 🌙**")
    else:
        emoji = get_random_emoji()
        app.send_message(message.chat.id, emoji)
        message.reply_text(f"**Goodnight, {sender}! Sleep tight. {emoji}**")


def get_random_sticker():
    stickers = [
        "CAACAgQAAx0Ce2KwywABAU-fZobjXdmgKXmKWrVWOJk6HnB4vXEAApsQAAJCWf0ETJDh9FNzBJgeBA",
"CAACAgEAAx0Ce2KwywABAU-OZobi2aV1TnJkD2D10pdg09jhC88AAu0AA1EpDTk2V7yXSF8KHx4E",
"CAACAgEAAx0Ce2KwywABAU-bZobjMKemr4domSBhF2xGFlKM0gkAAplBAAJbnC4ae2lF5vUQWoIeBA",
"CAACAgEAAx0Ce2KwywABAU-dZobjSPYaQV6VM6J7HxxAHSmKz7YAAu8AA1EpDTnVI_Mr4Iy9Fx4E",
"CAACAgEAAx0Ce2KwywABAU_iZoblZeGTCFSIOLKJ0Ray843KcUMAAkUBAAJRKQ05nA448EOWeAoeBA",
"CAACAgEAAx0Ce2KwywABAU_qZoblo7FnSJ6imJ-aCaZ3HN7k5J4AAjEBAAJRKQ05Cwjl42PzQfUeBA",
"CAACAgUAAx0Ce2KwywABAU_uZobly5MRnt4PrQ5oTujq3pmvdFUAAqMBAAL_VAlXWVi8oa7uK70eBA"
    ]
    return random.choice(stickers)


def get_random_emoji():
    emojis = [
        "😴",
        "😪",
        "💤",
    ]
    return random.choice(emojis)

MOD_TYPE = "TOOLS"
MOD_NAME = "GN-Text"
MOD_PRICE = "10"
