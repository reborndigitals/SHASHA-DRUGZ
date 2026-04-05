import re
import os
from os import getenv
from dotenv import load_dotenv
from pyrogram import filters
load_dotenv()

API_ID = int(getenv("API_ID","8045459"))
API_HASH = getenv("API_HASH", "e6d1f09120e17a4372fe022dde88511b")
BOT_TOKEN = getenv("BOT_TOKEN", "8318822054:AAG1Q-uxHSXRqrZg4mBLhF7lr-Glj_zTEJc")

OWNER_USERNAME = getenv("OWNER_USERNAME","GhosttBatt")
BOT_USERNAME = getenv("BOT_USERNAME", "ShsshaOffiBot")
BOT_NAME = getenv("BOT_NAME", "˹𝐒ʜᴧƨнᴧ ༭ 𝐌ʋ𝗌ιᴄ˼𓆩𔘓⃭𓆪")
ASSUSERNAME = getenv("ASSUSERNAME", "Apple_Ponnu")
EVALOP = list(map(int, getenv("EVALOP", "1281282633 6773435708").split()))
MONGO_DB_URI = getenv("MONGO_DB_URI","mongodb+srv://ghosttbatt:Ghost2021@ghosttbatt.ocbirts.mongodb.net/?retryWrites=true&w=majority")
REDIS_URL = os.getenv("REDIS_URL","redis://default:LMXY37qj1iU91xEci0uaCcQa6kBEn4G3@redis-18407.crce286.ap-south-1-1.ec2.cloud.redislabs.com:18407")
GPT_API = getenv("GPT_API", "sk-proj-h6pk40oVRIxpXwrf3i50T3BlbkFJGVET8wX1yJtdi0zCWjDQ")
PLAYHT_API = getenv("PLAYHT_API", "22e323f342024c0fb4ee430eeb9d0011")
DATABASE_NAME = getenv("DATABASE_NAME","ghosttFed")
MONGO_URL = getenv("MONGO_URL","mongodb+srv://zewdatabase:ijoXgdmQ0NCyg9DO@zewgame.urb3i.mongodb.net/ontap?retryWrites=true&w=majority")

REACTION_ENABLED = getenv("REACTION_ENABLED","False")
DURATION_LIMIT_MIN = int(getenv("DURATION_LIMIT", 17000))

LOGGER_ID = int(getenv("LOGGER_ID", "-1001735663878"))
LOG_GROUP_ID = int(getenv("LOG_GROUP_ID", "-1001735663878"))
LOG_CHANNEL = int(getenv("LOG_CHANNEL", "-1003142547877"))
DEPLOY_LOGGER = int(getenv("DEPLOY_LOGGER", "-1001735663878"))
UPI_ID = os.getenv("UPI_ID", "GhosttBatt@jio")
DEFAULT_QR_PATH = os.getenv("QR_PATH", "SHASHA_DRUGZ/assets/shasha/GhosttBatt.jpg")

OWNER_ID = int(getenv("OWNER_ID", 6773435708))
ADMINS_ID_STR = getenv("ADMINS_ID", "1281282633 6773435708 7820081045").split()
ADMINS_ID = [int(admin_id) for admin_id in ADMINS_ID_STR if admin_id.isdigit()]

# ─── Store raw defaults for _BotStr fallback ──────────────────────────────────
_DEFAULT_SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/HeartBeat_Offi")
_DEFAULT_SUPPORT_CHAT    = getenv("SUPPORT_CHAT",    "https://t.me/HeartBeat_Fam")
_DEFAULT_MUST_JOIN       = getenv("MUST_JOIN",       "HeartBeat_Fam")
_DEFAULT_AUTO_GCAST      = os.getenv("AUTO_GCAST",   "False")
_DEFAULT_AUTO_GCAST_MSG  = getenv("AUTO_GCAST_MSG",  "<blockquote>⋆｡°✩ **𝐋ᴇᴛƨ𝐕ɪʙᴇ𝐎ᴜᴛ** ✩°｡⋆\n[˹𝐒ʜᴧƨнᴧ ༭ 𝐃꧊ꝛʋɢ𝗌˼𓆩𔘓⃭𓆪](https://t.me/SilukkuMusicBot)</blockquote>")
_DEFAULT_START_IMG       = getenv("START_IMG_URL",   "https://files.catbox.moe/qz10e1.jpg")
_DEFAULT_PING_IMG        = getenv("PING_IMG_URL",    "https://graph.org/file/ffdb1be822436121cf5fd.png")

MUST_JOIN = _DEFAULT_MUST_JOIN

#Ranking
AUTOPOST_TIME_HOUR = 21
AUTOPOST_TIME_MINUTE = 0

SERVER_PLAYLIST_LIMIT = int(getenv("SERVER_PLAYLIST_LIMIT", "3000"))
PLAYLIST_FETCH_LIMIT = int(getenv("PLAYLIST_FETCH_LIMIT", "2500"))
AUTO_LEAVING_ASSISTANT = False

SPOTIFY_CLIENT_ID = getenv("SPOTIFY_CLIENT_ID", "19609edb1b9f4ed7be0c8c1342039362")
SPOTIFY_CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET", "409e31d3ddd64af08cfcc3b0f064fcbe")
PLAYLIST_FETCH_LIMIT = int(getenv("PLAYLIST_FETCH_LIMIT", 2500))

TG_AUDIO_FILESIZE_LIMIT = int(getenv("TG_AUDIO_FILESIZE_LIMIT", 5499999999)) #5 GB
TG_VIDEO_FILESIZE_LIMIT = int(getenv("TG_VIDEO_FILESIZE_LIMIT", 5499999999)) #5 GB

AUTO_SUGGESTION_TIME = int(getenv("AUTO_SUGGESTION_TIME", "3"))
AUTO_SUGGESTION_MODE = getenv("AUTO_SUGGESTION_MODE", "True")
CLEANMODE_DELETE_MINS = int(getenv("CLEANMODE_MINS", "5"))

HEROKU_APP_NAME = getenv("HEROKU_APP_NAME")
HEROKU_API_KEY = getenv("HEROKU_API_KEY", "HRKU-fc1b7aea-b37a-4015-9877-8c3967ee97bc")
UPSTREAM_REPO = getenv("UPSTREAM_REPO", "https://github.com/reborndigitals/SHASHA_DRUG")
UPSTREAM_BRANCH = getenv("UPSTREAM_BRANCH", "master")
GIT_TOKEN = getenv("GIT_TOKEN", None)

STRING1 = getenv("STRING_SESSION1", "BQGJMTYANz9fx_SCUMDYpwW4a6KJJs1CDFRmqdlsud2Aw5ZYWKTUzi2OwvxK0kJA9xAjrv6uljGDVrxiJHcvRrQ38ZvPSOr1M69VTFyCD4PXS2x1tgnpeWfbaQFAwrHII9-C7buoLWB1wsE8nF7K8xJwHQNyYqGpxMXsMjN9FTGtoWUAHSzEVukyIJ31tCQGi-dV5PUvTBbQrd4tT97FaQ876uyeMfqP9CDp1lyys7uZiQ1VNoomYyWhT99AQ3VHH-M2ojqgOFCbA9KOg-uOg7VjtGKsuF21wUigIElrwxVJTkvUPnw1xqei4KmL53GqK7Td_9eec4YWGoaFJfHNJYbgh23xHgAAAAHSHPeVAA")
STRING2 = getenv("STRING_SESSION2", None)
STRING3 = getenv("STRING_SESSION3", None)
STRING4 = getenv("STRING_SESSION4", None)
STRING5 = getenv("STRING_SESSION5", None)

SHASHA_PICS = [
    "https://files.catbox.moe/qz10e1.jpg",
    "https://files.catbox.moe/mus8qn.jpg",
    "https://files.catbox.moe/n7t6ma.jpg",
    "https://files.catbox.moe/tb66lq.jpg",
    "https://files.catbox.moe/imwrq4.jpg",
    "https://files.catbox.moe/3u3dcp.jpg",
    "https://files.catbox.moe/70fnlf.jpg",
    "https://files.catbox.moe/i8r1dm.jpg",
    "https://files.catbox.moe/5u11yx.jpg"
]

RANKING_PIC = "https://files.catbox.moe/pfjca4.jpg"

GREET = [
    "💞", "🥂", "🔍", "🧪", "🥂", "⚡️", "🔥", "🦋", "🎩", "🌈", "🍷", "🥂", "🦋", "🥃", "🥤", "🕊️",
    "🦋", "🦋", "🕊️", "⚡️", "🕊️", "⚡️", "⚡️", "🥂", "💌", "🥂", "🥂", "🧨"
]
MENTION_USERNAMES = ["/start", "/help", "Ghost Bat", "Shasha", "bat here", "@"]
START_REACTIONS = [
    "👍", "👎", "❤️", "🔥", "🥰", "👏", "😁", "🤔",
    "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩",
    "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳",
    "❤", "🔥", "💔", "💯", "🤣", "⚡", "💘", "🏆",
    "🍓", "🍾", "💋", "💘", "😈", "😴", "😭", "🤓",
    "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨", "🤝",
    "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪",
    "🗿", "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊",
    "😎", "👾", "🤷‍♂", "🤷", "🤷‍♀", "😡"
]

# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC PER-BOT CONFIG PROXIES
# ─────────────────────────────────────────────────────────────────────────────
#
# HOW THIS WORKS:
#   Every deployed bot runs in the same process as the main bot but has its
#   own Pyrogram Client.  The isolation system sets _current_bot_id (a
#   ContextVar) before every message/callback handler.
#
#   _BotStr is a str subclass — isinstance(x, str) is True.
#   When any module accesses the VALUE (str(), f-string, Pyrogram send_photo,
#   startswith(), etc.) Python calls our overridden methods, which look up the
#   current bot's cached MongoDB settings and return the stored value.
#
#   This means `from config import START_IMG_URL` already imported in 500+
#   modules will automatically return the per-bot stored image because _BotStr
#   overrides ALL Python-level string operations.
#
#   On bot startup: call `await apply_to_config(bot_id)` to warm the cache.
#   On setbotinfo write: `_update()` calls `invalidate + get_bot_settings(force)`
#   which refreshes the cache.  The next access to START_IMG_URL etc. returns
#   the new value instantly — zero restarts needed.
#
#   When /resetbotset is called: all DB fields are set to None.
#   _BotStr._v() finds no value → falls back to the hardcoded default below.
# ─────────────────────────────────────────────────────────────────────────────

def _url_prefix(v: str) -> str:
    """Ensure support_chat / update_channel has https://t.me/ prefix."""
    v = v.strip().lstrip("@")
    return v if v.startswith("http") else f"https://t.me/{v}"


class _BotStr(str):
    """
    A str subclass that resolves to the current deployed bot's per-bot DB value
    when any string operation is performed on it.

    Fallback chain:
      1. Current bot's MongoDB cache  (bot_{id}_settings)
      2. Hardcoded default            (original config.py value)

    Works transparently with `from config import X` — no module changes needed.
    """
    __slots__ = ("_db_key", "_transform")

    def __new__(cls, default: str, db_key: str, transform=None):
        obj = super().__new__(cls, default)
        obj._db_key = db_key
        obj._transform = transform
        return obj

    def _v(self) -> str:
        """Return the current bot's value or the hardcoded default."""
        try:
            from SHASHA_DRUGZ.core.isolation import _current_bot_id
            import SHASHA_DRUGZ.utils.bot_settings as _bs
            bot_id = _current_bot_id.get(None)
            if bot_id is not None:
                settings = _bs._cache.get(bot_id)
                if settings is not None:
                    # Navigate dot-separated keys  e.g. "auto_gcast.message"
                    keys = self._db_key.split(".")
                    val = settings
                    for k in keys:
                        val = val.get(k) if isinstance(val, dict) else None
                    if val is not None and str(val).strip():
                        result = str(val)
                        return self._transform(result) if self._transform else result
        except Exception:
            pass
        return str.__str__(self)   # original hardcoded default

    # ── str protocol overrides ───────────────────────────────────────────────
    def __str__(self):              return self._v()
    def __repr__(self):             return repr(self._v())
    def __format__(self, spec):     return format(self._v(), spec)
    def __eq__(self, other):        return self._v() == (str(other) if other is not None else None)
    def __ne__(self, other):        return not self.__eq__(other)
    def __hash__(self):             return hash(self._v())
    def __bool__(self):             return bool(self._v())
    def __len__(self):              return len(self._v())
    def __iter__(self):             return iter(self._v())
    def __getitem__(self, key):     return self._v()[key]
    def __contains__(self, o):      return o in self._v()
    def __add__(self, other):       return self._v() + str(other)
    def __radd__(self, other):      return str(other) + self._v()
    def __mul__(self, n):           return self._v() * n
    def __rmul__(self, n):          return n * self._v()
    def __mod__(self, other):       return self._v() % other
    def __rmod__(self, other):      return other % self._v()
    # str methods — all delegate to resolved value
    def upper(self):                return self._v().upper()
    def lower(self):                return self._v().lower()
    def strip(self, *a):            return self._v().strip(*a)
    def lstrip(self, *a):           return self._v().lstrip(*a)
    def rstrip(self, *a):           return self._v().rstrip(*a)
    def split(self, *a, **k):       return self._v().split(*a, **k)
    def rsplit(self, *a, **k):      return self._v().rsplit(*a, **k)
    def join(self, it):             return self._v().join(it)
    def startswith(self, *a):       return self._v().startswith(*a)
    def endswith(self, *a):         return self._v().endswith(*a)
    def replace(self, *a):          return self._v().replace(*a)
    def encode(self, *a, **k):      return self._v().encode(*a, **k)
    def format(self, *a, **k):      return self._v().format(*a, **k)
    def format_map(self, m):        return self._v().format_map(m)
    def find(self, *a):             return self._v().find(*a)
    def rfind(self, *a):            return self._v().rfind(*a)
    def index(self, *a):            return self._v().index(*a)
    def rindex(self, *a):           return self._v().rindex(*a)
    def count(self, *a):            return self._v().count(*a)
    def center(self, *a):           return self._v().center(*a)
    def ljust(self, *a):            return self._v().ljust(*a)
    def rjust(self, *a):            return self._v().rjust(*a)
    def zfill(self, n):             return self._v().zfill(n)
    def expandtabs(self, *a):       return self._v().expandtabs(*a)
    def capitalize(self):           return self._v().capitalize()
    def title(self):                return self._v().title()
    def swapcase(self):             return self._v().swapcase()
    def casefold(self):             return self._v().casefold()
    def isalpha(self):              return self._v().isalpha()
    def isdigit(self):              return self._v().isdigit()
    def isalnum(self):              return self._v().isalnum()
    def isspace(self):              return self._v().isspace()
    def islower(self):              return self._v().islower()
    def isupper(self):              return self._v().isupper()
    def istitle(self):              return self._v().istitle()
    def isnumeric(self):            return self._v().isnumeric()
    def isdecimal(self):            return self._v().isdecimal()
    def isprintable(self):          return self._v().isprintable()
    def isidentifier(self):         return self._v().isidentifier()
    def partition(self, sep):       return self._v().partition(sep)
    def rpartition(self, sep):      return self._v().rpartition(sep)
    def splitlines(self, *a):       return self._v().splitlines(*a)
    def translate(self, t):         return self._v().translate(t)
    def maketrans(self, *a):        return str.maketrans(*a)
    def removeprefix(self, p):      return self._v().removeprefix(p)
    def removesuffix(self, s):      return self._v().removesuffix(s)


class _MustJoinStr(_BotStr):
    """
    Special _BotStr for MUST_JOIN.

    Logic:
      • If bot has registered settings AND must_join.enabled == True
        AND must_join.link is set → return the link (truthy → module enforces join)
      • If bot has registered settings AND must_join.enabled == False
        → return "" (falsy → module skips join check, even if default exists)
      • If bot has NO settings yet → return hardcoded default (truthy)

    This prevents the global default from leaking into deployed bots that
    have explicitly disabled must_join.
    """
    def _v(self) -> str:
        try:
            from SHASHA_DRUGZ.core.isolation import _current_bot_id
            import SHASHA_DRUGZ.utils.bot_settings as _bs
            bot_id = _current_bot_id.get(None)
            if bot_id is not None:
                settings = _bs._cache.get(bot_id)
                if settings is not None:
                    mj = settings.get("must_join") or {}
                    # Bot has settings doc — its must_join state is authoritative
                    if mj.get("enabled") and mj.get("link"):
                        lnk = mj["link"].strip().lstrip("@")
                        return lnk
                    # Explicitly disabled or not set → no must-join for this bot
                    return ""
        except Exception:
            pass
        # No bot context (main bot) → use global default
        return str.__str__(self)


class _BotInt(int):
    """
    An int subclass that resolves to the current deployed bot's per-bot DB
    value for integer config fields (LOG_GROUP_ID, LOGGER_ID).

    Falls back to the hardcoded default when no per-bot value is stored.

    Note: __slots__ is intentionally omitted — int subclasses do not support
    nonempty __slots__ in CPython. _db_key is stored in the instance __dict__.
    """

    def __new__(cls, default: int, db_key: str):
        obj = super().__new__(cls, default)
        obj._db_key = db_key
        return obj

    def _v(self) -> int:
        try:
            from SHASHA_DRUGZ.core.isolation import _current_bot_id
            import SHASHA_DRUGZ.utils.bot_settings as _bs
            bot_id = _current_bot_id.get(None)
            if bot_id is not None:
                settings = _bs._cache.get(bot_id)
                if settings is not None:
                    val = settings.get(self._db_key)
                    if val is not None and isinstance(val, int):
                        return val
        except Exception:
            pass
        return int.__int__(self)

    def __int__(self):        return self._v()
    def __index__(self):      return self._v()
    def __str__(self):        return str(self._v())
    def __repr__(self):       return repr(self._v())
    def __format__(self, s):  return format(self._v(), s)
    def __bool__(self):       return bool(self._v())
    def __eq__(self, o):      return self._v() == o
    def __ne__(self, o):      return self._v() != o
    def __lt__(self, o):      return self._v() < o
    def __le__(self, o):      return self._v() <= o
    def __gt__(self, o):      return self._v() > o
    def __ge__(self, o):      return self._v() >= o
    def __hash__(self):       return hash(self._v())
    def __neg__(self):        return -self._v()
    def __pos__(self):        return +self._v()
    def __abs__(self):        return abs(self._v())
    def __add__(self, o):     return self._v() + o
    def __radd__(self, o):    return o + self._v()
    def __sub__(self, o):     return self._v() - o
    def __rsub__(self, o):    return o - self._v()
    def __mul__(self, o):     return self._v() * o
    def __rmul__(self, o):    return o * self._v()
    def __floordiv__(self, o):return self._v() // o
    def __mod__(self, o):     return self._v() % o
    def __pow__(self, o):     return self._v() ** o
    def __and__(self, o):     return self._v() & o
    def __or__(self, o):      return self._v() | o
    def __xor__(self, o):     return self._v() ^ o
    def __lshift__(self, o):  return self._v() << o
    def __rshift__(self, o):  return self._v() >> o
    def __invert__(self):     return ~self._v()
    def bit_length(self):     return self._v().bit_length()


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC CONFIG VALUES
# Each one wraps the original default and resolves from per-bot MongoDB cache
# ─────────────────────────────────────────────────────────────────────────────

# Images — /setstartimg updates "start_image" in DB
# ALL image aliases point to the same db_key so one command updates everything
START_IMG_URL            = _BotStr(_DEFAULT_START_IMG, "start_image")
PING_IMG_URL             = _BotStr(_DEFAULT_PING_IMG,  "ping_image")
PLAYLIST_IMG_URL         = _BotStr(_DEFAULT_START_IMG, "start_image")
STATS_IMG_URL            = _BotStr(_DEFAULT_START_IMG, "start_image")
TELEGRAM_AUDIO_URL       = _BotStr(_DEFAULT_START_IMG, "start_image")
TELEGRAM_VIDEO_URL       = _BotStr(_DEFAULT_START_IMG, "start_image")
STREAM_IMG_URL           = _BotStr(_DEFAULT_START_IMG, "start_image")
SOUNCLOUD_IMG_URL        = _BotStr(_DEFAULT_START_IMG, "start_image")
YOUTUBE_IMG_URL          = _BotStr(_DEFAULT_START_IMG, "start_image")
SPOTIFY_ARTIST_IMG_URL   = _BotStr(_DEFAULT_START_IMG, "start_image")
SPOTIFY_ALBUM_IMG_URL    = _BotStr(_DEFAULT_START_IMG, "start_image")
SPOTIFY_PLAYLIST_IMG_URL = _BotStr(_DEFAULT_START_IMG, "start_image")

# Links — /setsupport and /setupdates update these
# _url_prefix auto-adds https://t.me/ if needed
SUPPORT_CHANNEL = _BotStr(_DEFAULT_SUPPORT_CHANNEL, "update_channel", _url_prefix)
SUPPORT_CHAT    = _BotStr(_DEFAULT_SUPPORT_CHAT,    "support_chat",   _url_prefix)

# Must join — /setmustjoin and /mustjoin enable|disable
# _MustJoinStr handles the enabled flag check
MUST_JOIN = _MustJoinStr(_DEFAULT_MUST_JOIN, "must_join.link")

# Gcast — /autogcast enable|disable and /setgcastmsg
AUTO_GCAST     = _BotStr(_DEFAULT_AUTO_GCAST,     "auto_gcast.enabled")
AUTO_GCAST_MSG = _BotStr(_DEFAULT_AUTO_GCAST_MSG, "auto_gcast.message")

# Log channel — /setlogger updates this
LOG_GROUP_ID = _BotInt(int(getenv("LOG_GROUP_ID", "-1001735663878")), "log_channel")
LOGGER_ID    = _BotInt(int(getenv("LOGGER_ID",    "-1001735663878")), "log_channel")

# ─────────────────────────────────────────────────────────────────────────────

BANNED_USERS = filters.user()
adminlist = {}
lyrical = {}
votemode = {}
autoclean = []
confirmer = {}
chatstats = {}
userstats = {}
clean = {}
autoclean = []

def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))

DURATION_LIMIT = int(time_to_seconds(f"{DURATION_LIMIT_MIN}:00"))

# Validate using the DEFAULTS (these run at import time before any bot context)
if _DEFAULT_SUPPORT_CHANNEL:
    if not re.match("(?:http|https)://", _DEFAULT_SUPPORT_CHANNEL):
        raise SystemExit(
            "[ERROR] - Your SUPPORT_CHANNEL url is wrong. Please ensure that it starts with https://"
        )
if _DEFAULT_SUPPORT_CHAT:
    if not re.match("(?:http|https)://", _DEFAULT_SUPPORT_CHAT):
        raise SystemExit(
            "[ERROR] - Your SUPPORT_CHAT url is wrong. Please ensure that it starts with https://"
        )
