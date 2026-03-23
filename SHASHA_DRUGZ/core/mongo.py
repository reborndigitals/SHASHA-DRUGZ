# SHASHA_DRUGZ/core/mongo.py
# =====================================================
# CHANGES FROM ORIGINAL:
#   1. Import IsolatedDatabase / IsolatedSyncDatabase
#   2. Wrap mongodb and pymongodb with those proxies
#   3. Expose raw_mongodb / raw_pymongodb for admin code
#      that intentionally needs cross-bot access
# Everything else is identical to the original file.
# =====================================================

from motor.motor_asyncio import AsyncIOMotorClient as _mongo_client_
from pymongo import MongoClient
from pyrogram import Client
import config
from ..logging import LOGGER

# ── Isolation proxies (import AFTER motor/pymongo, no circular risk) ──────────
from SHASHA_DRUGZ.core.isolation import IsolatedDatabase, IsolatedSyncDatabase

TEMP_MONGODB = (
    "mongodb+srv://ghosttbatt:Ghost2021@ghhosttbatt.ocbirts.mongodb.net/"
    "?retryWrites=true&w=majority"
)

if config.MONGO_DB_URI is None:
    LOGGER(__name__).warning(
        "𝐍o 𝐌ONGO 𝐃B 𝐔RL 𝐅ound.. 𝐘our 𝐁ot 𝐖ill 𝐖ork 𝐎n 𝐒𝐇𝐀𝐒𝐇𝐀-𝐌𝐔𝐒𝐈𝐂 𝐃atabase"
    )
    temp_client = Client(
        "SHASHA_DRUGZ",
        bot_token=config.BOT_TOKEN,
        api_id=config.API_ID,
        api_hash=config.API_HASH,
    )
    temp_client.start()
    info     = temp_client.get_me()
    username = info.username
    temp_client.stop()
    _mongo_async_  = _mongo_client_(TEMP_MONGODB)
    _mongo_sync_   = MongoClient(TEMP_MONGODB)
    _raw_mongodb   = _mongo_async_[username]
    _raw_pymongodb = _mongo_sync_[username]
else:
    _mongo_async_  = _mongo_client_(config.MONGO_DB_URI)
    _mongo_sync_   = MongoClient(config.MONGO_DB_URI)
    _raw_mongodb   = _mongo_async_.SHASHA_DRUGZ
    _raw_pymongodb = _mongo_sync_.SHASHA_DRUGZ

# ── Public isolated handles (what all 500+ modules import) ───────────────────
mongodb   = IsolatedDatabase(_raw_mongodb)       # async  (motor)
pymongodb = IsolatedSyncDatabase(_raw_pymongodb) # sync   (pymongo)

# ── Raw handles — use ONLY in deploy.py / admin code ─────────────────────────
# These bypass the isolation proxy and always hit the real collection name.
raw_mongodb   = _raw_mongodb
raw_pymongodb = _raw_pymongodb


# ── Collection helpers ────────────────────────────────────────────────────────

def get_collection(name: str):
    """
    Isolated collection for the current bot context.
      Main bot  → db[name]
      Bot 111   → db[bot_111_name]
    """
    return mongodb[name]


def get_raw_collection(name: str):
    """
    Un-isolated collection — always the real name.
    Use only in admin / deploy code.
    """
    return _raw_mongodb[name]

