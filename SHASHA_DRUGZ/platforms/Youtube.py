import asyncio
import os
import re
import random
import time
import datetime
import glob
import logging
from typing import Union, Optional, Tuple
import yt_dlp
import aiohttp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
from playwright.async_api import async_playwright
from SHASHA_DRUGZ import app, LOGGER
from SHASHA_DRUGZ.utils.formatters import time_to_seconds
from config import LOG_GROUP_ID

# ══════════════════════════════════════════════════════════════════════════════
#  USER-AGENT ROTATION
# ══════════════════════════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ══════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════
PLAY_URL             = os.getenv("PLAY_URL", "https://youtu.be/ip8o5hDFLhI?si=jCdWYdBAEulr2b49")
ENABLE_YT_COOKIES    = os.getenv("ENABLE_YT_COOKIES", "true").lower() == "true"
AUTO_REFRESH_COOKIES = True
YTDLP_PROXIES        = os.getenv("YTDLP_PROXIES", "")
PLAYWRIGHT_PROXIES   = os.getenv("PLAYWRIGHT_PROXIES", "")

PLAYWRIGHT_PROFILE_DIR = os.path.join(os.getcwd(), "playwright_profile")
os.makedirs(PLAYWRIGHT_PROFILE_DIR, exist_ok=True)

COOKIES_DIR = os.path.join(os.getcwd(), "cookies")
os.makedirs(COOKIES_DIR, exist_ok=True)

COOKIE_FILE  = os.path.join(COOKIES_DIR, "youtube_cookies.txt")
YT_CACHE_DIR = os.path.join(os.getcwd(), "ytcache")
os.makedirs(YT_CACHE_DIR, exist_ok=True)

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

# Only ONE cookie generation at a time — prevents parallel Playwright launches
# from corrupting the shared browser profile.
_COOKIE_LOCK = asyncio.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  PO_TOKEN PLUGIN DETECTION
#
#  If yt-dlp-get-pot (or any po_token provider) is installed it prints
#  "Generating POT for …" and internally selects its own YouTube client for
#  token generation (typically "web" or "tv_embedded").
#
#  Setting extractor_args["youtube"]["player_client"] to ANY explicit list
#  overrides that choice.  When the client yt-dlp-get-pot chose is not in our
#  list the format manifest it returns is incomplete →
#  "Requested format is not available".
#
#  Fix: detect the plugin at import time and skip the player_client override
#  entirely when it is present.  When no plugin is found, set a broad client
#  list so yt-dlp still has good format coverage.
# ══════════════════════════════════════════════════════════════════════════════
def _detect_pot_plugin() -> bool:
    """Return True if a po_token provider plugin appears to be installed."""
    # Method 1 – check importlib for known package names
    try:
        import importlib.util
        for pkg in ("yt_dlp_get_pot", "ytdlp_get_pot", "yt_dlp_plugins"):
            if importlib.util.find_spec(pkg) is not None:
                return True
    except Exception:
        pass
    # Method 2 – scan yt-dlp's own plugin registry (works for egg-link installs)
    try:
        from yt_dlp import plugins as _ydlp_plugins  # noqa: F401
        import yt_dlp.plugins as plg_mod
        plugin_dirs = getattr(plg_mod, "_dirs", []) or []
        for d in plugin_dirs:
            if os.path.isdir(d):
                for entry in os.listdir(d):
                    if "pot" in entry.lower() or "getpot" in entry.lower():
                        return True
    except Exception:
        pass
    # Method 3 – conservative: check if the POT log line appears in a dry-run
    # (skip — too expensive at import time; rely on methods 1 & 2)
    return False


_POT_PLUGIN_PRESENT: bool = _detect_pot_plugin()

# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_proxy_list(proxy_env: str):
    if not proxy_env:
        return []
    return [p.strip() for p in proxy_env.split(",") if p.strip()]

YTDLP_PROXY_POOL      = _parse_proxy_list(YTDLP_PROXIES)
PLAYWRIGHT_PROXY_POOL = _parse_proxy_list(PLAYWRIGHT_PROXIES)

def choose_random_proxy(pool):
    return random.choice(pool) if pool else None

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGER
# ══════════════════════════════════════════════════════════════════════════════
def get_logger(name: str):
    try:
        return LOGGER(name)
    except Exception:
        log = logging.getLogger(name)
        if not log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            log.addHandler(h)
        log.setLevel(logging.INFO)
        return log

logger = get_logger("SHASHA_DRUGZ/platforms/Youtube.py")
logger.info(f"po_token plugin detected at startup: {_POT_PLUGIN_PRESENT}")

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def clear_old_cookies():
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            logger.warning("🧹 Old YouTube cookies removed")
        for f in glob.glob(os.path.join(COOKIES_DIR, "*")):
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Failed to clear cookies: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  LOG GROUP HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def send_to_log_group(text: str = None, file_obj=None):
    if not LOG_GROUP_ID:
        logger.warning("LOG_GROUP_ID not configured – skipping")
        return
    try:
        if file_obj and text:
            await app.send_document(chat_id=LOG_GROUP_ID, document=file_obj, caption=text)
        elif text:
            await app.send_message(chat_id=LOG_GROUP_ID, text=text)
    except Exception as e:
        logger.error(f"Failed to send to log group: {e}")

async def send_cookie_file_to_log_group(reason: str = ""):
    if not os.path.exists(COOKIE_FILE):
        logger.warning("Cookie file missing – cannot send to log group.")
        return
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    caption = (
        f"🍪 **YouTube Cookie Regenerated**\n\n"
        f"📅 Time   : `{timestamp}`\n"
        f"📄 File   : `youtube_cookie.txt`\n"
        f"📝 Reason : {reason or 'On-demand refresh'}\n\n"
        f"#YouTubeCookies"
    )
    try:
        import pyrogram
        with open(COOKIE_FILE, "rb") as f:
            await app.send_document(
                chat_id=LOG_GROUP_ID,
                document=pyrogram.types.InputFile(f, file_name="youtube_cookie.txt"),
                caption=caption,
            )
        logger.info(f"✅ Cookie sent to log group | reason={reason}")
    except Exception:
        try:
            with open(COOKIE_FILE, "rb") as f:
                await send_to_log_group(text=caption, file_obj=f)
        except Exception as e2:
            logger.error(f"Failed to send cookie file: {e2}")

# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC IP INFO
# ══════════════════════════════════════════════════════════════════════════════
async def get_public_ip_info():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://ipapi.co/json/",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "ip":      data.get("ip"),
                        "city":    data.get("city"),
                        "country": data.get("country_name"),
                        "org":     data.get("org"),
                    }
    except Exception as e:
        logger.error(f"Failed to fetch IP info: {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  PLAYWRIGHT PROFILE LOCK CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def cleanup_playwright_profile():
    stale_files = [
        "SingletonLock", "SingletonCookie",
        "SingletonSocket", "DevToolsActivePort",
    ]
    for fname in stale_files:
        fpath = os.path.join(PLAYWRIGHT_PROFILE_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                logger.info(f"🧹 Removed stale profile file: {fname}")
            except Exception as e:
                logger.warning(f"Could not remove {fname}: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  BROWSER PROFILE COOKIE GENERATION
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(reason: str = "Profile cookie generation") -> bool:
    logger.info(f"🌐 Launching browser profile to generate cookies [{reason}] ...")
    await send_to_log_group(
        text=(
            f"🌐 **Browser Profile – Generating Cookies**\n\n"
            f"📝 Reason : {reason}\n"
            f"⏳ Launching headless Chromium ...\n\n"
            f"#YouTubeCookies"
        )
    )
    cleanup_playwright_profile()
    proxy      = choose_random_proxy(PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(USER_AGENTS)
    context    = None
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                PLAYWRIGHT_PROFILE_DIR,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                ],
                proxy={"server": proxy} if proxy else None,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
            )
            page = await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)
            try:
                logger.info("🔗 Visiting accounts.google.com ...")
                await page.goto("https://accounts.google.com",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(4000)
            except Exception as e:
                logger.warning(f"accounts.google.com warning: {e}")
            try:
                logger.info("🔗 Visiting youtube.com ...")
                await page.goto("https://www.youtube.com",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(5000)
                await page.mouse.move(random.randint(100, 600), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1500))
                await page.mouse.wheel(0, random.randint(300, 800))
                await page.wait_for_timeout(random.randint(500, 1000))
            except Exception as e:
                logger.warning(f"youtube.com warning: {e}")
            if PLAY_URL:
                try:
                    logger.info(f"🎬 Priming session with PLAY_URL: {PLAY_URL}")
                    await page.goto(PLAY_URL,
                                    wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(6000)
                except Exception as e:
                    logger.warning(f"PLAY_URL prime warning: {e}")
            try:
                await page.goto("https://www.youtube.com/feed/trending",
                                wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)
            except Exception:
                pass
            await context.close()
            logger.info("✅ Browser profile cookies refreshed successfully")
            return True
    except Exception as e:
        logger.error(f"❌ Playwright cookie generation error: {str(e)[:300]}")
        if context:
            try:
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Browser Profile – Cookie Generation Failed**\n\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n\n"
                f"#YouTubeCookies"
            )
        )
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACT COOKIES FROM BROWSER PROFILE
# ══════════════════════════════════════════════════════════════════════════════
async def refresh_cookies_from_browser(reason: str = "On-demand refresh") -> Optional[str]:
    async with _COOKIE_LOCK:
        if (
            os.path.exists(COOKIE_FILE)
            and verify_cookies_file(COOKIE_FILE)
            and not is_cookie_file_expired(COOKIE_FILE)
        ):
            logger.info("✅ Cookies already refreshed by another coroutine — reusing")
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok:
            logger.error("Browser profile cookie generation failed.")
            return None

        logger.info(f"🔄 Extracting cookies from browser profile ... [reason={reason}]")
        try:
            cmd = [
                "yt-dlp",
                "--cookies-from-browser", f"chrome:{PLAYWRIGHT_PROFILE_DIR}",
                "--cookies", COOKIE_FILE,
                "--no-check-certificate",
                "--quiet",
                "--no-download",
                "https://www.youtube.com",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if process.returncode == 0 and os.path.exists(COOKIE_FILE):
                if verify_cookies_file(COOKIE_FILE) and not is_cookie_file_expired(COOKIE_FILE):
                    logger.info("✅ Cookies extracted and verified successfully")
                    ip_info   = await get_public_ip_info() or {}
                    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                    await send_to_log_group(
                        text=(
                            f"🌐 **YouTube Cookies Extracted (Browser Profile)**\n\n"
                            f"📅 Time     : `{timestamp}`\n"
                            f"🌍 IP       : `{ip_info.get('ip', 'unknown')}`\n"
                            f"📍 Location : {ip_info.get('city', 'unknown')}, "
                            f"{ip_info.get('country', 'unknown')}\n"
                            f"🏢 ISP/Org  : {ip_info.get('org', 'unknown')}\n"
                            f"📝 Reason   : {reason}\n\n"
                            f"#YouTubeCookies"
                        )
                    )
                    await send_cookie_file_to_log_group(reason=reason)
                    return COOKIE_FILE
                else:
                    logger.error("❌ Extracted cookies failed verification or are expired")
                    if os.path.exists(COOKIE_FILE):
                        os.remove(COOKIE_FILE)
                    logger.info("🔁 Retrying cookie extraction with a fresh browser session ...")
                    ok2 = await generate_cookies_via_playwright(reason=f"{reason} (retry)")
                    if not ok2:
                        return None
                    process2 = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(process2.communicate(), timeout=120)
                    if process2.returncode == 0 and os.path.exists(COOKIE_FILE):
                        if verify_cookies_file(COOKIE_FILE):
                            await send_cookie_file_to_log_group(reason=f"{reason} (retry)")
                            return COOKIE_FILE
                    logger.error("❌ Retry extraction also failed")
                    return None
            else:
                error_msg = stderr.decode()[:300] if stderr else "Unknown error"
                logger.warning(f"yt-dlp cookie extraction failed: {error_msg}")
                await send_to_log_group(
                    text=(
                        f"⚠️ **Cookie Extraction Failed**\n\n"
                        f"📝 Reason : {reason}\n"
                        f"⚠️ Error  : `{error_msg[:250]}`\n\n"
                        f"#YouTubeCookies"
                    )
                )
                return None
        except asyncio.TimeoutError:
            logger.error("Cookie extraction timed out (120s)")
            return None
        except Exception as e:
            logger.error(f"Cookie extraction error: {e}")
            return None

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════
def verify_cookies_file(filename: str) -> bool:
    try:
        if not os.path.exists(filename):
            logger.error(f"Cookies file does not exist: {filename}")
            return False
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        if "youtube.com" not in content and ".youtube.com" not in content:
            logger.error("No youtube.com domain in cookies file")
            return False
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Cookies file is JSON format, not Netscape")
            return False

        auth_cookies = [
            "SAPISID", "LOGIN_INFO", "__Secure-1PAPISID",
            "__Secure-3PAPISID", "SID", "HSID", "SSID", "APISID",
        ]
        visitor_cookies = [
            "VISITOR_INFO1_LIVE", "YSC", "PREF", "SOCS",
            "__Secure-ROLLOUT_TOKEN", "VISITOR_PRIVACY_METADATA",
        ]
        found_auth    = [c for c in auth_cookies    if c in content]
        found_visitor = [c for c in visitor_cookies if c in content]
        found_any     = found_auth + found_visitor

        if len(found_any) < 2:
            logger.warning(f"⚠️ Too few cookies found: auth={found_auth} visitor={found_visitor}")
            return False

        valid_lines = 0
        for line in content.strip().split("\n"):
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            if "\t" not in line:
                logger.error(f"Invalid Netscape format (no tabs): {line[:100]}")
                return False
            valid_lines += 1

        if valid_lines < 3:
            logger.error(f"Too few valid cookie lines: {valid_lines}")
            return False

        logger.info(
            f"✅ Cookies verified: {filename} | lines={valid_lines} "
            f"| auth={found_auth} | visitor={found_visitor}"
        )
        return True
    except Exception as e:
        logger.error(f"Error verifying cookies file: {e}")
        return False

def get_cookie_min_expiry(filepath: str) -> Optional[int]:
    try:
        min_exp = None
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain = parts[0]
                if "youtube.com" not in domain and "google.com" not in domain:
                    continue
                try:
                    exp = int(parts[4])
                    if exp <= 0:
                        continue
                    if min_exp is None or exp < min_exp:
                        min_exp = exp
                except (ValueError, IndexError):
                    continue
        return min_exp
    except Exception as e:
        logger.error(f"Failed to parse cookie expiry: {e}")
        return None

def is_cookie_file_expired(filepath: str) -> bool:
    if not os.path.exists(filepath):
        return True
    min_exp = get_cookie_min_expiry(filepath)
    if min_exp is None:
        logger.info("Cookie expiry unknown (session cookies) – treating as valid")
        return False
    now = int(time.time())
    if min_exp < now:
        logger.info(f"🕐 Cookie expired at {datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z")
        return True
    remaining = min_exp - now
    logger.info(f"✅ Cookie valid for {remaining // 3600}h {(remaining % 3600) // 60}m")
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH / ROBOT ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def is_auth_error(exception: Exception) -> bool:
    error_str = str(exception).lower()
    auth_indicators = [
        "sign in to confirm you're not a bot",
        "confirm you are not a robot",
        "confirm you're not a bot",
        "http error 401",
        "http error 403",
        "unable to extract video data",
        "this video may be inappropriate",
        "confirm your age",
        "cookie",
        "login required",
        "robot",
        "captcha",
        "recaptcha",
        "access denied",
        "forbidden",
        "sign in",
        "authentication",
    ]
    return any(ind in error_str for ind in auth_indicators)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════
async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    if force_refresh:
        cleanup_playwright_profile()

    if not force_refresh and os.path.exists(COOKIE_FILE):
        if verify_cookies_file(COOKIE_FILE) and not is_cookie_file_expired(COOKIE_FILE):
            logger.info("✅ Using existing (non-expired) cookies")
            return COOKIE_FILE
        else:
            logger.warning("Existing cookies invalid or expired – regenerating ...")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
    reason = "Force refresh – robot/auth detected" if force_refresh else "Initial / expired"
    return await refresh_cookies_from_browser(reason=reason)

# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO ID EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    patterns = [
        r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})",
        r"watch\?v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"shorts/([A-Za-z0-9_-]{11})",
        r"embed/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  YT-DLP OPTIONS
#
#  KEY FIX — po_token plugin conflict:
#
#  When yt-dlp-get-pot (or any po_token provider) is installed it selects its
#  own YouTube client (typically "web" or "tv_embedded") for token generation.
#  Setting extractor_args["youtube"]["player_client"] to ANY explicit list
#  overrides that selection.  When the plugin's chosen client is not in our
#  list the format manifest it fetches is incomplete →
#  "Requested format is not available".
#
#  Solution: skip the player_client override entirely when _POT_PLUGIN_PRESENT
#  is True.  When no plugin is present, set a broad list for good coverage.
# ══════════════════════════════════════════════════════════════════════════════
def get_ytdlp_opts(extra_opts: dict = None, use_cookie_file: str = None) -> dict:
    ua = random.choice(USER_AGENTS)
    base = {
        "outtmpl":            os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet":              True,
        "no_warnings":        True,
        "geo_bypass":         True,
        "nocheckcertificate": True,
        "retries":            10,
        "fragment_retries":   10,
        "cachedir":           YT_CACHE_DIR,
        "http_headers": {
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    # Do NOT set player_client when a po_token plugin is present —
    # overriding its client choice breaks format resolution.
    if not _POT_PLUGIN_PRESENT:
        base["extractor_args"] = {
            "youtube": {
                "player_client": ["ios", "android", "web", "tv_embedded"]
            }
        }
        logger.debug("No po_token plugin — using explicit player_client list")
    else:
        logger.debug("po_token plugin active — skipping player_client override")

    if use_cookie_file and os.path.exists(use_cookie_file):
        base["cookiefile"] = use_cookie_file
        logger.debug(f"Using cookiefile: {use_cookie_file}")
    else:
        base["cookiesfrombrowser"] = ("chrome", PLAYWRIGHT_PROFILE_DIR)
        logger.debug("Falling back to cookiesfrombrowser with persistent profile")

    proxy = choose_random_proxy(YTDLP_PROXY_POOL)
    if proxy:
        base["proxy"] = proxy

    if extra_opts:
        base.update(extra_opts)
    return base

# ══════════════════════════════════════════════════════════════════════════════
#  FILE FINDER
# ══════════════════════════════════════════════════════════════════════════════
def _get_downloaded_file(video_id: str, prefer_m4a: bool = False) -> Optional[str]:
    if not video_id:
        return None
    exts = ["m4a", "mp3", "webm", "opus", "mp4", "mkv"] if prefer_m4a \
           else ["mp3", "webm", "m4a", "opus", "mp4", "mkv"]
    for ext in exts:
        p = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(p):
            return p
    if os.path.exists(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            if video_id in f:
                return os.path.join(DOWNLOAD_DIR, f)
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  FORMAT STRINGS
#  "bestaudio/best" — most permissive; resolves with any client / container.
#  FFmpegExtractAudio converts to mp3 192k regardless of source container.
# ══════════════════════════════════════════════════════════════════════════════
def _audio_format_opts() -> dict:
    return {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key":              "FFmpegExtractAudio",
            "preferredcodec":   "mp3",
            "preferredquality": "192",
        }],
    }

def _video_format_opts() -> dict:
    return {
        "format":              "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
    }

# ══════════════════════════════════════════════════════════════════════════════
#  CORE DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════
async def download_with_ytdlp(link: str, is_audio: bool) -> Optional[str]:
    video_id = extract_video_id(link)
    if not video_id:
        logger.error(f"Could not extract video ID from {link}")
        return None

    existing = _get_downloaded_file(video_id)
    if existing and os.path.exists(existing):
        logger.info(f"📁 File already exists: {existing}")
        return existing

    cookie_file = await get_cookies()
    if not cookie_file or not os.path.exists(cookie_file):
        logger.warning("No valid cookie file – attempting download without cookies")
        cookie_file = None

    def _build_opts(cf: Optional[str]) -> dict:
        extra = _audio_format_opts() if is_audio else _video_format_opts()
        return get_ytdlp_opts(extra, use_cookie_file=cf)

    ydl_opts = _build_opts(cookie_file)
    loop     = asyncio.get_event_loop()

    for attempt in range(2):
        try:
            await asyncio.sleep(random.uniform(0.5, 2.5))
            async with DOWNLOAD_SEMAPHORE:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await loop.run_in_executor(
                        None, lambda: ydl.extract_info(link, download=True)
                    )
            file_path = _get_downloaded_file(video_id)
            if file_path and os.path.exists(file_path):
                logger.info(f"✅ Download successful: {file_path}")
                return file_path
            logger.error(f"Download finished but file not found on disk. video_id={video_id!r}")
            return None

        except Exception as e:
            err_str = str(e)
            logger.error(f"Download error (attempt {attempt + 1}): {err_str[:300]}")

            if is_auth_error(e) and AUTO_REFRESH_COOKIES and attempt == 0:
                logger.warning("🤖 Robot/auth detected – regenerating cookies ...")
                clear_old_cookies()
                await send_to_log_group(
                    text=(
                        "⚠️ **YouTube: Robot/Auth Detected**\n\n"
                        "🧹 Old cookies cleared\n"
                        "🔄 Regenerating cookies via Browser Profile ...\n\n"
                        "#YouTubeCookies"
                    )
                )
                new_cookie = await refresh_cookies_from_browser(
                    reason="Robot/auth detected during download"
                )
                if new_cookie and os.path.exists(new_cookie):
                    logger.info("✅ Fresh cookies obtained – retrying download ...")
                    ydl_opts = _build_opts(new_cookie)
                    continue
                else:
                    logger.error("Cookie regeneration failed – aborting download")
                    return None
            else:
                return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
#  STREAMING HELPER
# ══════════════════════════════════════════════════════════════════════════════
STREAM_MIN_SIZE = 500_000
STREAM_FORMAT   = "140/bestaudio/best"   # 140 = m4a 128k; fallback to best audio

async def wait_for_partial_file(
    file_path: str,
    min_size: int = STREAM_MIN_SIZE,
    check_interval: float = 0.3,
):
    while True:
        if os.path.exists(file_path) and os.path.getsize(file_path) > min_size:
            return
        await asyncio.sleep(check_interval)

async def download_song_stream(link: str) -> Tuple[Optional[str], Optional[asyncio.Task]]:
    video_id = extract_video_id(link)
    if not video_id:
        return None, None

    existing = _get_downloaded_file(video_id, prefer_m4a=True)
    if existing and os.path.exists(existing):
        return existing, None

    cookie_file = await get_cookies()
    if cookie_file and not os.path.exists(cookie_file):
        cookie_file = None

    ydl_opts      = get_ytdlp_opts({"format": STREAM_FORMAT}, use_cookie_file=cookie_file)
    expected_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")
    loop          = asyncio.get_event_loop()

    async def _download_task():
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(
                    None, lambda: ydl.extract_info(link, download=True)
                )

    task = asyncio.create_task(_download_task())
    try:
        await wait_for_partial_file(expected_path, min_size=STREAM_MIN_SIZE)
        return expected_path, task
    except Exception as e:
        logger.error(f"Streaming wait error: {e}")
        task.cancel()
        return None, None

# ══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD WRAPPERS
# ══════════════════════════════════════════════════════════════════════════════
async def download_song(link: str) -> Optional[str]:
    logger.info(f"🎵 Downloading audio: {link}")
    return await download_with_ytdlp(link, is_audio=True)

async def download_video(link: str) -> Optional[str]:
    logger.info(f"🎬 Downloading video: {link}")
    return await download_with_ytdlp(link, is_audio=False)

# ══════════════════════════════════════════════════════════════════════════════
#  PLAY_URL AUTO-TEST
# ══════════════════════════════════════════════════════════════════════════════
async def test_cookie_with_playurl(retries: int = 2):
    if not PLAY_URL:
        logger.warning("PLAY_URL not set – skipping auto-test.")
        return
    if retries <= 0:
        logger.error("❌ PLAY_URL test: max retries reached")
        await send_to_log_group(
            text=(
                "❌ **Cookie Auto-Test: Max Retries Reached**\n\n"
                f"🎬 URL: `{PLAY_URL}`\n\n"
                "Will retry on next download.\n\n"
                "#CookieTest"
            )
        )
        return

    logger.info(f"🎬 Auto-testing cookies with PLAY_URL (retries left: {retries}) ...")
    test_dir = os.path.join(os.getcwd(), "cookie_test")
    os.makedirs(test_dir, exist_ok=True)
    video_id = extract_video_id(PLAY_URL)

    test_opts = get_ytdlp_opts(
        {
            "outtmpl": os.path.join(test_dir, "%(id)s.%(ext)s"),
            "format":  "bestaudio/best",
        },
        use_cookie_file=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    )
    try:
        loop = asyncio.get_event_loop()
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                await loop.run_in_executor(
                    None, lambda: ydl.extract_info(PLAY_URL, download=True)
                )

        file_path = None
        if video_id:
            for ext in ["mp3", "webm", "m4a", "opus", "mp4", "mkv"]:
                p = os.path.join(test_dir, f"{video_id}.{ext}")
                if os.path.exists(p):
                    file_path = p
                    break
        if not file_path and os.path.exists(test_dir):
            files = [
                os.path.join(test_dir, f)
                for f in os.listdir(test_dir)
                if os.path.isfile(os.path.join(test_dir, f))
            ]
            if files:
                file_path = max(files, key=os.path.getmtime)

        if file_path and os.path.exists(file_path):
            size_kb = os.path.getsize(file_path) // 1024
            logger.info(f"✅ Cookie test PASSED – {file_path} ({size_kb} KB)")
            await send_to_log_group(
                text=(
                    f"✅ **Cookie Auto-Test: PASSED**\n\n"
                    f"🎬 URL  : `{PLAY_URL}`\n"
                    f"📁 File : `{os.path.basename(file_path)}`\n"
                    f"📦 Size : `{size_kb} KB`\n\n"
                    f"Cookies are working correctly ✔️\n\n"
                    f"#CookieTest"
                )
            )
            try:
                os.remove(file_path)
            except Exception:
                pass
        else:
            logger.error("❌ Cookie test FAILED – file not found after download")
            await send_to_log_group(
                text=(
                    f"❌ **Cookie Auto-Test: FAILED**\n\n"
                    f"🎬 URL: `{PLAY_URL}`\n\n"
                    f"Download appeared to complete but no file was found.\n"
                    f"Triggering cookie regeneration ...\n\n"
                    f"#CookieTest"
                )
            )
            clear_old_cookies()
            new_cookie = await refresh_cookies_from_browser(reason="PLAY_URL test: file not found")
            if new_cookie:
                await test_cookie_with_playurl(retries=retries - 1)

    except Exception as e:
        err_str = str(e)
        logger.error(f"Cookie auto-test error: {err_str}")
        if is_auth_error(e):
            logger.warning("🤖 Robot/auth detected during PLAY_URL test – regenerating ...")
            clear_old_cookies()
            await send_to_log_group(
                text=(
                    f"⚠️ **Robot/Auth Detected During PLAY_URL Cookie Test**\n\n"
                    f"🔗 URL    : `{PLAY_URL}`\n"
                    f"⚠️ Error  : `{err_str[:200]}`\n\n"
                    f"🧹 Old cookies cleared\n"
                    f"🔄 Regenerating via Browser Profile ...\n\n"
                    f"#YouTubeCookies"
                )
            )
            new_cookie = await refresh_cookies_from_browser(
                reason="Robot detected during PLAY_URL auto-test"
            )
            if new_cookie:
                await test_cookie_with_playurl(retries=retries - 1)
        else:
            await send_to_log_group(
                text=(
                    f"❌ **Cookie Auto-Test: ERROR**\n\n"
                    f"🎬 URL   : `{PLAY_URL}`\n"
                    f"⚠️ Error : `{err_str[:300]}`\n\n"
                    f"Cookies will regenerate automatically on next download.\n\n"
                    f"#CookieTest"
                )
            )

# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════════════════════
async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        err = errorz.decode("utf-8")
        if "unavailable videos are hidden" in err.lower():
            return out.decode("utf-8")
        return err
    return out.decode("utf-8")

async def check_file_size(link):
    try:
        ydl_opts = get_ytdlp_opts(
            {"quiet": True},
            use_cookie_file=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        )
        loop = asyncio.get_event_loop()
        def _get_size():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info  = ydl.extract_info(link, download=False)
                total = 0
                for f in info.get("formats", []):
                    size = f.get("filesize") or f.get("filesize_approx")
                    if size:
                        total += size
                return total
        return await asyncio.wait_for(
            loop.run_in_executor(None, _get_size),
            timeout=60,
        )
    except Exception as e:
        logger.error(f"Failed to get file size: {e}")
        return None

# ══════════════════════════════════════════════════════════════════════════════
#  YouTubeAPI CLASS
# ══════════════════════════════════════════════════════════════════════════════
class YouTubeAPI:
    def __init__(self):
        self.base     = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.status   = "https://www.youtube.com/oembed?url="
        self.regex    = re.compile(
            r"(https?://)?(www\.|m\.)?"
            r"(youtube\.com/(?:watch\?v=|shorts/|live/|embed/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&\?][^\s]*)?"
        )
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-9?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title        = result["title"]
            duration_min = result["duration"]
            thumbnail    = result["thumbnails"][0]["url"].split("?")[0]
            vidid        = result["id"]
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        try:
            downloaded_file = await download_video(link)
            if downloaded_file and os.path.exists(downloaded_file):
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video failed: {str(e)[:100]}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        ydl_opts = get_ytdlp_opts(
            {"quiet": True, "extract_flat": True, "playlistend": limit},
            use_cookie_file=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        )
        loop = asyncio.get_event_loop()
        try:
            def _get_playlist():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    if "entries" in info:
                        return [e["id"] for e in info["entries"] if e.get("id")]
                    return []
            return await asyncio.wait_for(
                loop.run_in_executor(None, _get_playlist),
                timeout=60,
            )
        except Exception as e:
            logger.error(f"Playlist extraction failed: {e}")
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title        = result["title"]
            duration_min = result["duration"]
            vidid        = result["id"]
            yturl        = result["link"]
            thumbnail    = result["thumbnails"][0]["url"].split("?")[0]
        track_details = {
            "title":        title,
            "link":         yturl,
            "vidid":        vidid,
            "duration_min": duration_min,
            "thumb":        thumbnail,
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ydl_opts = get_ytdlp_opts(
            {"quiet": True},
            use_cookie_file=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        )
        loop = asyncio.get_event_loop()
        try:
            def _get_formats():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info              = ydl.extract_info(link, download=False)
                    formats_available = []
                    for fmt in info.get("formats", []):
                        try:
                            if "dash" not in str(fmt.get("format", "")).lower():
                                formats_available.append({
                                    "format":      fmt.get("format"),
                                    "filesize":    fmt.get("filesize"),
                                    "format_id":   fmt.get("format_id"),
                                    "ext":         fmt.get("ext"),
                                    "format_note": fmt.get("format_note"),
                                    "yturl":       link,
                                })
                        except Exception:
                            continue
                    return formats_available
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _get_formats),
                timeout=60,
            )
            return result, link
        except Exception as e:
            logger.error(f"Failed to get formats: {e}")
            return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a      = VideosSearch(link, limit=10)
        result = (await a.next()).get("result")
        title        = result[query_type]["title"]
        duration_min = result[query_type]["duration"]
        vidid        = result[query_type]["id"]
        thumbnail    = result[query_type]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid

    async def download(
        self,
        link:      str,
        mystic,
        video:     Union[bool, str] = None,
        videoid:   Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title:     Union[bool, str] = None,
    ) -> tuple:
        if videoid:
            link = self.base + link
        try:
            if songvideo or songaudio:
                downloaded_file = await download_song(link)
            elif video:
                downloaded_file = await download_video(link)
            else:
                downloaded_file = await download_song(link)

            # Guard None / missing path — prevents "[Errno 2] No such file: None"
            if not downloaded_file or not os.path.exists(downloaded_file):
                logger.error(
                    f"Downloaded file path invalid or missing: {downloaded_file!r} "
                    f"for link={link!r}"
                )
                return None, False

            return downloaded_file, True
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None, False

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def startup_services():
    if not ENABLE_YT_COOKIES:
        logger.info("YouTube cookie handling disabled (ENABLE_YT_COOKIES=false).")
        return
    logger.info("🚀 Starting YouTube services (Browser Profile) ...")
    cleanup_playwright_profile()
    need_refresh = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )
    if need_refresh:
        logger.info("🔄 No valid cookies found – generating via Browser Profile ...")
        cookie_file = await get_cookies(force_refresh=True)
        if cookie_file:
            logger.info(f"✅ Cookies ready: {cookie_file}")
        else:
            logger.warning(
                "⚠️ Cookie generation failed on startup.\n"
                "   The bot will retry automatically on the first download request."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **Startup Cookie Generation Failed**\n\n"
                    "Could not generate cookies via Browser Profile on startup.\n"
                    "The bot will retry automatically when a download is requested.\n\n"
                    "#YouTubeCookies"
                )
            )
    else:
        logger.info("✅ Existing cookies are valid and unexpired – skipping regeneration.")
    logger.info("🎬 Running PLAY_URL startup test ...")
    await test_cookie_with_playurl(retries=2)
