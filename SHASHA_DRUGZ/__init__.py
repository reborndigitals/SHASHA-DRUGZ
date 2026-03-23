from SHASHA_DRUGZ.core.bot import SHASHA
from SHASHA_DRUGZ.core.dir import dirr
from SHASHA_DRUGZ.core.git import git
from SHASHA_DRUGZ.core.userbot import Userbot
from SHASHA_DRUGZ.misc import dbb, heroku
from pyrogram import Client
from telethon import TelegramClient
from config import API_ID, API_HASH
from SafoneAPI import SafoneAPI
from .logging import LOGGER

dirr()
git()
dbb()
heroku()

app = SHASHA()
api = SafoneAPI()
userbot = Userbot()

from .platforms import *

Apple = AppleAPI()
Carbon = CarbonAPI()
SoundCloud = SoundAPI()
Spotify = SpotifyAPI()
Resso = RessoAPI()
Telegram = TeleAPI()
YouTube = YouTubeAPI()
Instagram = InstagramAPI()

# Correct Telethon initialization (no start here)
telethn = TelegramClient(
    "SHASHA_DRUGZ",
    API_ID,
    API_HASH,
    sequential_updates=True
)
