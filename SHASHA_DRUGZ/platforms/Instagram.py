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
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# ══════════════════════════════════════════════════���═══════════════════════════
#  ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════

ENABLE_IG_COOKIES    = os.getenv("ENABLE_IG_COOKIES", "true").lower() == "true"
AUTO_REFRESH_COOKIES = True
YTDLP_PROXIES        = os.getenv("YTDLP_PROXIES", "")
PLAYWRIGHT_PROXIES   = os.getenv("PLAYWRIGHT_PROXIES", "")
PLAYWRIGHT_PROFILE_DIR = os.path.join(os.getcwd(), "playwright_profile_ig")
os.makedirs(PLAYWRIGHT_PROFILE_DIR, exist_ok=True)

COOKIES_DIR = os.path.join(os.getcwd(), "cookies")
os.makedirs(COOKIES_DIR, exist_ok=True)

COOKIE_FILE = os.path.join(COOKIES_DIR, "instagram_cookies.txt")
IG_CACHE_DIR = os.path.join(os.getcwd(), "igcache")
os.makedirs(IG_CACHE_DIR, exist_ok=True)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
_COOKIE_LOCK = asyncio.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ═══════════════════════════════════��══════════════════════════════════════════

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

logger = get_logger("SHASHA_DRUGZ/platforms/Instagram.py")

# ══════════��═══════════════════════════════════════════════════════════════════
#  COOKIE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════

def clear_old_cookies():
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            logger.warning("🧹 Old Instagram cookies removed")
        for f in glob.glob(os.path.join(COOKIES_DIR, "*instagram*")):
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
        f"🍪 **Instagram Cookie Regenerated**\n\n"
        f"📅 Time   : `{timestamp}`\n"
        f"📄 File   : `instagram_cookies.txt`\n"
        f"📝 Reason : {reason or 'On-demand refresh'}\n\n"
        f"#InstagramCookies"
    )

    try:
        import pyrogram
        with open(COOKIE_FILE, "rb") as f:
            await app.send_document(
                chat_id=LOG_GROUP_ID,
                document=pyrogram.types.InputFile(f, file_name="instagram_cookies.txt"),
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
            async with session.get("https://ipapi.co/json/", timeout=10) as resp:
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
# ═══════════════════════════════════════════════════════��══════════════════════

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
            f"🌐 **Browser Profile – Generating Instagram Cookies**\n\n"
            f"📝 Reason : {reason}\n"
            f"⏳ Launching headless Chromium ...\n\n"
            f"#InstagramCookies"
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

            # Stealth: remove webdriver fingerprint
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)

            try:
                logger.info("🔗 Visiting instagram.com ...")
                await page.goto("https://www.instagram.com",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(5000)
                await page.mouse.move(random.randint(100, 600), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1500))
                await page.mouse.wheel(0, random.randint(300, 800))
                await page.wait_for_timeout(random.randint(500, 1000))
            except Exception as e:
                logger.warning(f"instagram.com warning: {e}")

            try:
                logger.info("🔗 Visiting instagram.com/explore ...")
                await page.goto("https://www.instagram.com/explore/",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(4000)
            except Exception as e:
                logger.warning(f"instagram.com/explore warning: {e}")

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
                f"#InstagramCookies"
            )
        )
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACT COOKIES FROM BROWSER PROFILE
# ══════════════════════════════════════════════════════════════════════════════

async def refresh_cookies_from_browser(reason: str = "On-demand refresh") -> Optional[str]:
    async with _COOKIE_LOCK:
        # After waiting for the lock, check if cookies are already fresh
        if os.path.exists(COOKIE_FILE) and verify_cookies_file(COOKIE_FILE) \
                and not is_cookie_file_expired(COOKIE_FILE):
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
                "https://www.instagram.com",
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
                            f"🌐 **Instagram Cookies Extracted (Browser Profile)**\n\n"
                            f"📅 Time     : `{timestamp}`\n"
                            f"🌍 IP       : `{ip_info.get('ip', 'unknown')}`\n"
                            f"📍 Location : {ip_info.get('city', 'unknown')}, "
                            f"{ip_info.get('country', 'unknown')}\n"
                            f"🏢 ISP/Org  : {ip_info.get('org', 'unknown')}\n"
                            f"📝 Reason   : {reason}\n\n"
                            f"#InstagramCookies"
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
                        f"#InstagramCookies"
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

        if "instagram.com" not in content and ".instagram.com" not in content:
            logger.error("No instagram.com domain in cookies file")
            return False

        important_cookies = [
            "sessionid", "ds_user_id", "ig_did", "csrftoken",
            "shbid", "shbts",
        ]

        found = [c for c in important_cookies if c in content]

        if len(found) < 1:
            logger.warning(f"⚠️ Too few important cookies found: {found}")
            return False

        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Cookies file is JSON format, not Netscape")
            return False

        valid_lines = 0
        for line in content.strip().split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            if "\t" not in line:
                logger.error(f"Invalid Netscape format (no tabs): {line[:100]}")
                return False
            valid_lines += 1

        if valid_lines < 2:
            logger.error(f"Too few valid cookie lines: {valid_lines}")
            return False

        logger.info(f"✅ Cookies verified: {filename} | lines={valid_lines} | found={found}")
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
                if "instagram.com" not in domain:
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
        logger.warning("Could not determine cookie expiry – treating as expired.")
        return True

    now = int(time.time())

    if min_exp < now:
        logger.info(f"🕐 Cookie expired at {datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z")
        return True

    remaining = min_exp - now
    logger.info(f"✅ Cookie valid for {remaining // 3600}h {(remaining % 3600) // 60}m")
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH / ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def is_auth_error(exception: Exception) -> bool:
    error_str = str(exception).lower()
    auth_indicators = [
        "login required",
        "http error 401",
        "http error 403",
        "unable to extract",
        "not authorized",
        "challenge_required",
        "access denied",
        "forbidden",
        "authentication",
        "cookie",
        "session",
        "invalid",
    ]
    return any(ind in error_str for ind in auth_indicators)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════

async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        if verify_cookies_file(COOKIE_FILE) and not is_cookie_file_expired(COOKIE_FILE):
            logger.info("✅ Using existing (non-expired) cookies")
            return COOKIE_FILE
        else:
            logger.warning("Existing cookies invalid or expired – regenerating ...")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)

    reason = "Force refresh – auth detected" if force_refresh else "Initial / expired"
    return await refresh_cookies_from_browser(reason=reason)

# ══════════════════════════════════════════════════════════════════════════════
#  INSTAGRAM URL & VIDEO ID EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None

    # Instagram reels: /reel/VIDEO_ID/
    reel_match = re.search(r'/reel/([A-Za-z0-9_-]+)/', url)
    if reel_match:
        return reel_match.group(1)

    # Instagram posts: /p/VIDEO_ID/
    post_match = re.search(r'/p/([A-Za-z0-9_-]+)/', url)
    if post_match:
        return post_match.group(1)

    # Instagram TV: /tv/VIDEO_ID/
    tv_match = re.search(r'/tv/([A-Za-z0-9_-]+)/', url)
    if tv_match:
        return tv_match.group(1)

    # Fallback: extract alphanumeric string
    match = re.search(r'([A-Za-z0-9_-]{10,})', url)
    if match:
        return match.group(1)

    return None

def is_instagram_url(url: str) -> bool:
    return "instagram.com" in url.lower() or "igsh=" in url.lower()

# ══════════════════════════════════════════════════════════════════════════════
#  YT-DLP OPTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_ytdlp_opts(extra_opts: dict = None, use_cookie_file: str = None) -> dict:
    ua = random.choice(USER_AGENTS)

    base = {
        "outtmpl":            "downloads/%(id)s.%(ext)s",
        "quiet":              True,
        "no_warnings":        True,
        "nocheckcertificate": True,
        "retries":            10,
        "fragment_retries":   10,
        "cachedir":           IG_CACHE_DIR,
        "http_headers": {
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

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

def _get_downloaded_file(video_id: str, prefer_mp4: bool = True) -> Optional[str]:
    if not video_id:
        return None

    DOWNLOAD_DIR = "downloads"
    exts = ["mp4", "mkv", "webm", "mov"] if prefer_mp4 \
           else ["webm", "mp4", "mkv", "mov"]

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
#  CORE DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

async def download_with_ytdlp(link: str, is_audio: bool = False) -> Optional[str]:
    video_id = extract_video_id(link)

    if not video_id:
        logger.error(f"Could not extract video ID from {link}")
        return None

    DOWNLOAD_DIR = "downloads"
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    existing = _get_downloaded_file(video_id)
    if existing:
        logger.info(f"📁 File already exists: {existing}")
        return existing

    cookie_file = await get_cookies()
    if not cookie_file:
        logger.error("No valid cookies – cannot download")
        return None

    def _build_opts(cf):
        if is_audio:
            extra = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key":              "FFmpegExtractAudio",
                    "preferredcodec":   "mp3",
                    "preferredquality": "192",
                }],
            }
        else:
            extra = {
                "format":              "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
            }
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
            if file_path:
                logger.info(f"✅ Download successful: {file_path}")
                return file_path

            logger.error("Download finished but file not found on disk")
            return None

        except Exception as e:
            if is_auth_error(e) and AUTO_REFRESH_COOKIES and attempt == 0:
                logger.warning(
                    f"🔐 Auth/login error detected on attempt {attempt + 1} – "
                    "regenerating cookies ..."
                )

                clear_old_cookies()
                await send_to_log_group(
                    text=(
                        "⚠️ **Instagram: Login Required – Detected**\n\n"
                        "🧹 Old cookies cleared\n"
                        "🔄 Regenerating cookies via Browser Profile ...\n\n"
                        "#InstagramCookies"
                    )
                )

                new_cookie = await refresh_cookies_from_browser(
                    reason="Auth/login error detected during download"
                )

                if new_cookie:
                    logger.info("✅ Fresh cookies obtained – retrying download ...")
                    ydl_opts = _build_opts(new_cookie)
                    continue
                else:
                    logger.error("Cookie regeneration failed – aborting download")
                    return None
            else:
                logger.error(f"Download error (attempt {attempt + 1}): {str(e)[:300]}")
                return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD WRAPPERS
# ══════════════════════════════════════════════════════════════════════════════

async def download_video(link: str) -> Optional[str]:
    logger.info(f"🎬 Downloading Instagram video: {link}")
    return await download_with_ytdlp(link, is_audio=False)

async def download_audio(link: str) -> Optional[str]:
    logger.info(f"🎵 Downloading Instagram audio: {link}")
    return await download_with_ytdlp(link, is_audio=True)

# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════════════════════

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
#  INSTAGRAM API CLASS
# ══════════════════════════════════════════════════════════════════════════════

class InstagramAPI:

    def __init__(self):
        self.base = "https://www.instagram.com/reel/"
        self.regex = re.compile(
            r"(https?://)?(www\.)?instagram\.com/(reel|p|tv)/([A-Za-z0-9_-]+)"
        )

    async def exists(self, link: str) -> bool:
        return is_instagram_url(link) and bool(re.search(self.regex, link))

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

    async def video(self, link: str) -> tuple:
        try:
            if not is_instagram_url(link):
                return 0, "Invalid Instagram URL"

            downloaded_file = await download_video(link)

            if downloaded_file:
                return 1, downloaded_file

            return 0, "Video download failed"

        except Exception as e:
            return 0, f"Video failed: {str(e)[:100]}"

    async def audio(self, link: str) -> tuple:
        try:
            if not is_instagram_url(link):
                return 0, "Invalid Instagram URL"

            downloaded_file = await download_audio(link)

            if downloaded_file:
                return 1, downloaded_file

            return 0, "Audio download failed"

        except Exception as e:
            return 0, f"Audio failed: {str(e)[:100]}"

    async def download(
        self,
        link:      str,
        mystic     = None,
        video:     Union[bool, str] = None,
        audio:     Union[bool, str] = None,
    ) -> tuple:
        try:
            if not is_instagram_url(link):
                return None, False

            if audio:
                downloaded_file = await download_audio(link)
            else:
                downloaded_file = await download_video(link)

            return downloaded_file, bool(downloaded_file)

        except Exception as e:
            logger.error(f"Download error: {e}")
            return None, False

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════

async def startup_services():
    if not ENABLE_IG_COOKIES:
        logger.info("Instagram cookie handling disabled (ENABLE_IG_COOKIES=false).")
        return

    logger.info("🚀 Starting Instagram services (Browser Profile) ...")

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
                    "Could not generate Instagram cookies via Browser Profile on startup.\n"
                    "The bot will retry automatically when a download is requested.\n\n"
                    "#InstagramCookies"
                )
            )
    else:
        logger.info("✅ Existing cookies are valid and unexpired – skipping regeneration.")
