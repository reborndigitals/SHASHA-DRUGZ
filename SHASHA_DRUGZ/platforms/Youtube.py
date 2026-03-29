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
#  ANDROID DEVICE PROFILES
# ══════════════════════════════════════════════════════════════════════════════
ANDROID_PROFILES = [
    {
        "ua":             "com.google.android.youtube/19.09.37 (Linux; U; Android 11; SM-G991B)",
        "client_version": "19.09.37",
        "android_sdk":    "30",
        "device":         "SM-G991B",
    },
    {
        "ua":             "com.google.android.youtube/18.45.43 (Linux; U; Android 10; Mi 9T)",
        "client_version": "18.45.43",
        "android_sdk":    "29",
        "device":         "Mi 9T",
    },
    {
        "ua":             "com.google.android.youtube/20.12.38 (Linux; U; Android 13; Pixel 7)",
        "client_version": "20.12.38",
        "android_sdk":    "33",
        "device":         "Pixel 7",
    },
    {
        "ua":             "com.google.android.youtube/17.31.35 (Linux; U; Android 9; Redmi Note 8)",
        "client_version": "17.31.35",
        "android_sdk":    "28",
        "device":         "Redmi Note 8",
    },
    {
        "ua":             "com.google.android.youtube/19.44.39 (Linux; U; Android 12; SM-A525F)",
        "client_version": "19.44.39",
        "android_sdk":    "31",
        "device":         "SM-A525F",
    },
]

_BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
]

def get_android_profile() -> dict:
    return dict(random.choice(ANDROID_PROFILES))

# ══════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════
PLAY_URL             = os.getenv("PLAY_URL", "https://youtu.be/ip8o5hDFLhI?si=jCdWYdBAEulr2b49")
ENABLE_YT_COOKIES    = os.getenv("ENABLE_YT_COOKIES", "true").lower() == "true"
AUTO_REFRESH_COOKIES = True
YT_GOOGLE_EMAIL      = os.getenv("YT_GOOGLE_EMAIL", "sthfsuh154@gmail.com")
YT_GOOGLE_PASSWORD   = os.getenv("YT_GOOGLE_PASSWORD", "143@Frnds")
YTDLP_PROXIES        = os.getenv("YTDLP_PROXIES", "")
PLAYWRIGHT_PROXIES   = os.getenv("PLAYWRIGHT_PROXIES", "")

PLAYWRIGHT_PROFILE_DIR = os.path.join(os.getcwd(), "playwright_profile")
os.makedirs(PLAYWRIGHT_PROFILE_DIR, exist_ok=True)

COOKIES_DIR  = os.path.join(os.getcwd(), "cookies");  os.makedirs(COOKIES_DIR,  exist_ok=True)
COOKIE_FILE  = os.path.join(COOKIES_DIR, "youtube_cookies.txt")
YT_CACHE_DIR = os.path.join(os.getcwd(), "ytcache");  os.makedirs(YT_CACHE_DIR, exist_ok=True)
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads"); os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
_COOKIE_LOCK       = asyncio.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_proxy_list(env: str):
    return [p.strip() for p in env.split(",") if p.strip()] if env else []

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

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def clear_old_cookies():
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            logger.warning("🧹 Old YouTube cookies removed")
        for f in glob.glob(os.path.join(COOKIES_DIR, "youtube*")):
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"clear_old_cookies: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  LOG GROUP HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def send_to_log_group(text: str = None, file_obj=None):
    if not LOG_GROUP_ID:
        return
    try:
        if file_obj and text:
            await app.send_document(chat_id=LOG_GROUP_ID, document=file_obj, caption=text)
        elif text:
            await app.send_message(chat_id=LOG_GROUP_ID, text=text)
    except Exception as e:
        logger.error(f"send_to_log_group: {e}")

async def send_cookie_file_to_log_group(reason: str = ""):
    if not os.path.exists(COOKIE_FILE):
        return
    ts      = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    caption = (
        f"🍪 **YouTube Cookie Regenerated**\n\n"
        f"📅 Time   : `{ts}`\n"
        f"📄 File   : `youtube_cookies.txt`\n"
        f"📝 Reason : {reason or 'On-demand refresh'}\n\n"
        f"#YouTubeCookies"
    )
    try:
        import pyrogram
        with open(COOKIE_FILE, "rb") as f:
            await app.send_document(
                chat_id=LOG_GROUP_ID,
                document=pyrogram.types.InputFile(f, file_name="youtube_cookies.txt"),
                caption=caption,
            )
        logger.info(f"✅ Cookie file sent to log group | reason={reason}")
    except Exception:
        try:
            with open(COOKIE_FILE, "rb") as f:
                await send_to_log_group(text=caption, file_obj=f)
        except Exception as e:
            logger.error(f"send_cookie_file_to_log_group: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC IP INFO
# ══════════════════════════════════════════════════════════════════════════════
async def get_public_ip_info() -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://ipapi.co/json/",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return {
                        "ip":      d.get("ip"),
                        "city":    d.get("city"),
                        "country": d.get("country_name"),
                        "org":     d.get("org"),
                    }
    except Exception as e:
        logger.error(f"get_public_ip_info: {e}")
    return {}

# ══════════════════════════════════════════════════════════════════════════════
#  PLAYWRIGHT PROFILE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def cleanup_playwright_profile():
    for fname in ("SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"):
        fpath = os.path.join(PLAYWRIGHT_PROFILE_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE LOGIN INSIDE PLAYWRIGHT
#
#  FIX: Google's login flow in 2025/2026 added intermediate screens
#       ("choose account", "verify it's you", slow password field rendering).
#       We now use:
#         - Extended timeouts (20s per selector instead of 15s)
#         - Multiple password field selector fallbacks
#         - Post-login challenge detection
#         - Graceful fallback (login failure → anonymous warm-up, not crash)
# ══════════════════════════════════════════════════════════════════════════════
async def _google_login(page) -> bool:
    if not YT_GOOGLE_EMAIL or not YT_GOOGLE_PASSWORD:
        return False
    logger.info(f"🔐 Attempting Google login as: {YT_GOOGLE_EMAIL}")
    try:
        await page.goto(
            "https://accounts.google.com/signin/v2/identifier"
            "?service=youtube&hl=en&flowName=GlifWebSignIn",
            wait_until="domcontentloaded", timeout=60_000,
        )
        await page.wait_for_timeout(random.randint(2000, 3500))

        # ── Email step ────────────────────────────────────────────────────────
        email_input = page.locator("input[type='email']")
        await email_input.wait_for(state="visible", timeout=20_000)
        await email_input.fill(YT_GOOGLE_EMAIL)
        await page.wait_for_timeout(random.randint(500, 1000))
        await page.keyboard.press("Enter")

        # Give Google time to transition to password page
        await page.wait_for_timeout(random.randint(3000, 5000))

        # ── Password step — multiple selector fallbacks ────────────────────────
        # Google changes the password field's name/autocomplete attributes
        # periodically. We try all known variants with a generous timeout.
        pwd_input = None
        for pwd_sel in [
            "input[type='password']",
            "input[name='password']",
            "input[name='Passwd']",
            "input[aria-label='Enter your password']",
            "input[autocomplete='current-password']",
        ]:
            try:
                el = page.locator(pwd_sel)
                await el.wait_for(state="visible", timeout=20_000)
                if await el.count() > 0 and await el.first.is_visible():
                    pwd_input = el.first
                    logger.info(f"✅ Password field found: {pwd_sel}")
                    break
            except Exception:
                continue

        if not pwd_input:
            url  = page.url.lower()
            body = ""
            try:
                body = (await page.inner_text("body")).lower()
            except Exception:
                pass
            if any(s in url or s in body for s in (
                "challenge", "captcha", "verify", "unusual",
                "blocked", "suspicious", "selectchallenge",
            )):
                logger.error(f"🚨 Google login challenge/captcha detected: {page.url}")
            else:
                logger.error(
                    f"❌ Password field not found after email step.\n"
                    f"   URL: {page.url}\n"
                    f"   This usually means: 2FA prompt, captcha, or account lock."
                )
            return False

        await pwd_input.fill(YT_GOOGLE_PASSWORD)
        await page.wait_for_timeout(random.randint(500, 1000))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(random.randint(6000, 9000))

        # ── Post-login challenge check ────────────────────────────────────────
        url = page.url.lower()
        if any(s in url for s in ("challenge", "verify", "captcha", "selectchallenge")):
            logger.error(f"🚨 Post-login challenge/verification required: {page.url}")
            return False

        # ── Auth cookie check ─────────────────────────────────────────────────
        cookies = await page.context.cookies()
        auth = [c["name"] for c in cookies if c["name"] in (
            "SAPISID", "LOGIN_INFO", "__Secure-1PAPISID",
            "__Secure-3PAPISID", "SID", "HSID", "SSID",
        )]
        if auth:
            logger.info(f"✅ Google login successful | auth cookies: {auth}")
            return True

        logger.warning(
            f"⚠️ Google login: no auth cookies found.\n"
            f"   URL: {page.url}\n"
            f"   Possible causes: 2FA enabled, CAPTCHA, account flagged, wrong credentials."
        )
        return False

    except Exception as e:
        logger.error(f"_google_login: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  BROWSER PROFILE COOKIE GENERATION  (Playwright)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(reason: str = "Profile cookie generation") -> bool:
    logger.info(f"🌐 Launching browser profile [{reason}] ...")
    await send_to_log_group(
        text=(
            f"🌐 **Browser Profile – Generating Cookies**\n"
            f"📝 Reason : {reason}\n"
            f"⏳ Launching Chromium ...\n#YouTubeCookies"
        )
    )
    cleanup_playwright_profile()
    proxy      = choose_random_proxy(PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(_BROWSER_USER_AGENTS)
    context    = None
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                PLAYWRIGHT_PROFILE_DIR,
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars", "--window-size=1920,1080",
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
                Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)

            # Try Google login if credentials are set
            login_ok = False
            if YT_GOOGLE_EMAIL and YT_GOOGLE_PASSWORD:
                login_ok = await _google_login(page)
                if not login_ok:
                    logger.warning(
                        "⚠️ Google login failed — proceeding with anonymous warm-up.\n"
                        "   Visitor-only cookies will be generated.\n"
                        "   Fix: ensure account has no 2FA, correct password set in env."
                    )

            # Always warm up youtube.com (gets visitor cookies even if login failed)
            try:
                logger.info("🔗 Visiting youtube.com ...")
                await page.goto("https://www.youtube.com",
                                wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(random.randint(3000, 5000))
                await page.mouse.move(random.randint(100, 600), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1500))
                await page.mouse.wheel(0, random.randint(200, 600))
                await page.wait_for_timeout(random.randint(500, 1000))
            except Exception as e:
                logger.warning(f"youtube.com warm-up: {e}")

            if PLAY_URL:
                try:
                    logger.info(f"🎬 Priming with PLAY_URL: {PLAY_URL}")
                    await page.goto(PLAY_URL, wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(6000)
                except Exception as e:
                    logger.warning(f"PLAY_URL prime: {e}")

            try:
                await page.goto("https://www.youtube.com/feed/trending",
                                wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)
            except Exception:
                pass

            await context.close()
            logger.info("✅ Browser profile cookies refreshed")
            return True
    except Exception as e:
        logger.error(f"❌ Playwright error: {str(e)[:300]}")
        if context:
            try:
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Browser Cookie Generation Failed**\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n#YouTubeCookies"
            )
        )
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE REFRESH  (with lock)
#
#  FIX: Previously this returned None when only visitor cookies were obtained,
#       causing the caller to receive None and then crash with
#       "[Errno 2] No such file or directory: 'None'" when passing it to yt-dlp.
#       Now: visitor-only cookies are accepted and returned as a valid path.
# ══════════════════════════════════════════════════════════════════════════════
async def refresh_cookies_from_browser(reason: str = "On-demand refresh") -> Optional[str]:
    async with _COOKIE_LOCK:
        if (os.path.exists(COOKIE_FILE)
                and verify_cookies_file(COOKIE_FILE)
                and not is_cookie_file_expired(COOKIE_FILE)):
            logger.info("✅ Cookies already fresh – reusing")
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok:
            return None

        logger.info(f"🔄 Extracting cookies from browser profile [{reason}] ...")
        cmd = [
            "yt-dlp",
            "--cookies-from-browser", f"chrome:{PLAYWRIGHT_PROFILE_DIR}",
            "--cookies", COOKIE_FILE,
            "--no-check-certificate",
            "--quiet", "--no-download",
            "https://www.youtube.com",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode == 0 and os.path.exists(COOKIE_FILE):
                if verify_cookies_file(COOKIE_FILE):
                    if not is_cookie_file_expired(COOKIE_FILE):
                        logger.info("✅ Cookies extracted and verified")
                    else:
                        logger.info("✅ Cookies extracted (session cookies – no expiry)")

                    ip = await get_public_ip_info()
                    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                    await send_to_log_group(
                        text=(
                            f"🌐 **YouTube Cookies Ready**\n"
                            f"📅 Time     : `{ts}`\n"
                            f"🌍 IP       : `{ip.get('ip','unknown')}`\n"
                            f"📍 Location : {ip.get('city','?')}, {ip.get('country','?')}\n"
                            f"🏢 ISP      : {ip.get('org','?')}\n"
                            f"📝 Reason   : {reason}\n#YouTubeCookies"
                        )
                    )
                    await send_cookie_file_to_log_group(reason=reason)
                    return COOKIE_FILE

                # Cookie file exists but failed verification entirely
                logger.error("❌ Cookie file failed verification after extraction")
                if os.path.exists(COOKIE_FILE):
                    os.remove(COOKIE_FILE)
                return None

            err = stderr.decode()[:300] if stderr else "unknown"
            logger.warning(f"yt-dlp extraction failed (rc={proc.returncode}): {err}")
            return None

        except asyncio.TimeoutError:
            logger.error("Cookie extraction timed out")
            return None
        except Exception as e:
            logger.error(f"refresh_cookies_from_browser: {e}")
            return None

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE VERIFICATION
#  Accepts both authenticated (SAPISID etc.) and visitor (VISITOR_INFO1_LIVE,
#  YSC) cookies. Visitor cookies are valid for yt-dlp on public videos.
# ══════════════════════════════════════════════════════════════════════════════
def verify_cookies_file(filename: str) -> bool:
    try:
        if not os.path.exists(filename):
            return False
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        if "youtube.com" not in content and "google.com" not in content:
            logger.error("No youtube.com / google.com in cookie file")
            return False
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Cookie file is JSON not Netscape")
            return False
        valid = sum(
            1 for line in content.strip().split("\n")
            if line and not line.startswith("#") and "\t" in line
        )
        if valid < 3:
            logger.error(f"Too few valid lines: {valid}")
            return False

        AUTH_COOKIES    = ["SAPISID", "LOGIN_INFO", "__Secure-1PAPISID",
                           "__Secure-3PAPISID", "SID", "HSID", "SSID", "APISID"]
        VISITOR_COOKIES = ["VISITOR_INFO1_LIVE", "YSC", "PREF", "SOCS"]

        found_auth    = [c for c in AUTH_COOKIES    if c in content]
        found_visitor = [c for c in VISITOR_COOKIES if c in content]

        if found_auth:
            logger.info(
                f"✅ Cookies verified (authenticated): lines={valid} "
                f"| auth={found_auth} | visitor={found_visitor}"
            )
            return True
        elif found_visitor:
            logger.info(
                f"✅ Cookies verified (visitor/anonymous): lines={valid} "
                f"| visitor={found_visitor}\n"
                f"   ⚠️  Visitor cookies won't bypass bot detection on flagged IPs.\n"
                f"   Set YT_GOOGLE_EMAIL + YT_GOOGLE_PASSWORD for authenticated cookies."
            )
            return True
        else:
            logger.error(f"❌ No recognisable YouTube cookies found (lines={valid})")
            return False
    except Exception as e:
        logger.error(f"verify_cookies_file: {e}")
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
                if "youtube.com" not in parts[0] and "google.com" not in parts[0]:
                    continue
                try:
                    exp = int(parts[4])
                    if exp > 0 and (min_exp is None or exp < min_exp):
                        min_exp = exp
                except (ValueError, IndexError):
                    pass
        return min_exp
    except Exception as e:
        logger.error(f"get_cookie_min_expiry: {e}")
        return None

def is_cookie_file_expired(filepath: str) -> bool:
    if not os.path.exists(filepath):
        return True
    min_exp = get_cookie_min_expiry(filepath)
    if min_exp is None:
        # Session cookies have no expiry timestamp — treat as valid
        logger.info("Cookie expiry unknown (session cookies) – treating as valid")
        return False
    now = int(time.time())
    if min_exp < now:
        logger.info(f"🕐 Cookie expired at {datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z")
        return True
    rem = min_exp - now
    logger.info(f"✅ Cookie valid for {rem // 3600}h {(rem % 3600) // 60}m")
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH / ROBOT ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def is_auth_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(k in s for k in (
        "sign in to confirm", "confirm you are not a robot",
        "confirm you're not a bot", "http error 401", "http error 403",
        "unable to extract video data", "confirm your age",
        "cookie", "login required", "robot", "captcha",
        "recaptcha", "access denied", "forbidden", "sign in", "authentication",
    ))

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════
async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        if verify_cookies_file(COOKIE_FILE) and not is_cookie_file_expired(COOKIE_FILE):
            logger.info("✅ Using existing cookies")
            return COOKIE_FILE
        logger.warning("Cookies invalid/expired – regenerating ...")
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
    reason = "Force refresh – robot/auth" if force_refresh else "Initial / expired"
    return await refresh_cookies_from_browser(reason=reason)

# ══════════════════════════════════════════════════════════════════════════════
#  VIDEO ID EXTRACTION
#  Rejects Instagram URLs — shortcodes look identical to YouTube video IDs
# ══════════════════════════════════════════════════════════════════════════════
def extract_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    if "instagram.com" in url.lower():
        logger.warning(f"extract_video_id: rejected Instagram URL: {url}")
        return None
    for pattern in [
        r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})",
        r"watch\?v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"shorts/([A-Za-z0-9_-]{11})",
        r"embed/([A-Za-z0-9_-]{11})",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  YT-DLP OPTIONS
#
#  Strategy A — Android innertube (no cookies)
#    - android_embedded added alongside android for better cloud IP success rate
#    - X-YouTube-Client-Name: "3" kept (it's the Android client ID, safe to send)
#    - X-YouTube-Client-Version and X-Goog-Visitor-Id NOT included (fingerprints)
#
#  Strategy B — Desktop web + cookie file
#    - Used when Android client is blocked
#    - Requires at minimum visitor cookies; auth cookies strongly preferred
# ══════════════════════════════════════════════════════════════════════════════
def get_ytdlp_opts(extra_opts: dict = None, use_cookie_file: str = None) -> dict:
    proxy = choose_random_proxy(YTDLP_PROXY_POOL)

    if use_cookie_file and os.path.exists(use_cookie_file):
        # Strategy B: desktop web + cookies
        base = {
            "outtmpl":            os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
            "quiet":              True,
            "no_warnings":        True,
            "geo_bypass":         True,
            "nocheckcertificate": True,
            "source_address":     "0.0.0.0",
            "retries":            5,
            "fragment_retries":   5,
            "noplaylist":         True,
            "cachedir":           YT_CACHE_DIR,
            "cookiefile":         use_cookie_file,
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "web_safari"],
                }
            },
            "http_headers": {
                "User-Agent":      random.choice(_BROWSER_USER_AGENTS),
                "Accept-Language": "en-US,en;q=0.9",
                "Origin":          "https://www.youtube.com",
                "Referer":         "https://www.youtube.com/",
            },
        }
    else:
        # Strategy A: Android innertube — no cookies needed
        profile = get_android_profile()
        base = {
            "outtmpl":            os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
            "quiet":              True,
            "no_warnings":        True,
            "geo_bypass":         True,
            "nocheckcertificate": True,
            "source_address":     "0.0.0.0",
            "retries":            5,
            "fragment_retries":   5,
            "concurrent_fragment_downloads": 1,
            "sleep_interval":     random.uniform(1, 3),
            "max_sleep_interval": 5,
            "noplaylist":         True,
            "cachedir":           YT_CACHE_DIR,
            "extractor_args": {
                "youtube": {
                    # android_embedded is less flagged on cloud IPs than plain android
                    "player_client": ["android", "android_embedded"],
                }
            },
            "http_headers": {
                "User-Agent":            profile["ua"],
                "Accept-Language":       "en-US,en;q=0.9",
                # Client ID "3" = Android YouTube app. Safe to include.
                # Do NOT add Client-Version or Visitor-Id — those are fingerprints.
                "X-YouTube-Client-Name": "3",
            },
        }

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
    for f in os.listdir(DOWNLOAD_DIR):
        if video_id in f:
            return os.path.join(DOWNLOAD_DIR, f)
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  CORE DOWNLOAD
#
#  Attempt 1: Android innertube (no cookies)
#  Attempt 2: Cookie file + desktop web client
#
#  FIX 1 (CRITICAL): cookie_file now validated with `os.path.exists()` before
#    being passed to yt-dlp. This prevents the crash:
#    "[Errno 2] No such file or directory: 'None'"
#    which occurred because refresh_cookies_from_browser() returned None
#    (visitor-only cookies) but the old code passed it directly to yt-dlp.
#
#  FIX 2: Cookie fallback skipped entirely when ENABLE_YT_COOKIES=false.
# ══════════════════════════════════════════════════════════════════════════════
async def download_with_ytdlp(link: str, is_audio: bool) -> Optional[str]:
    # Hard guard — never process Instagram URLs here
    if "instagram.com" in link.lower():
        logger.error(f"❌ Rejected Instagram URL in YouTube downloader: {link}")
        return None

    video_id = extract_video_id(link)
    if not video_id:
        logger.error(f"Cannot extract video ID from: {link}")
        return None

    existing = _get_downloaded_file(video_id)
    if existing:
        logger.info(f"📁 Reusing cached: {existing}")
        return existing

    def _format_extra(audio: bool) -> dict:
        if audio:
            return {
                "format": "bestaudio[ext=m4a]/bestaudio",
                "postprocessors": [{
                    "key":              "FFmpegExtractAudio",
                    "preferredcodec":   "mp3",
                    "preferredquality": "192",
                }],
            }
        return {"format": "best[ext=mp4]/best", "merge_output_format": "mp4"}

    loop = asyncio.get_event_loop()

    # ── Attempt 1: Android client, no cookies ────────────────────────────────
    logger.info(f"🎵 Downloading {'audio' if is_audio else 'video'} (Android client): {link}")
    ydl_opts = get_ytdlp_opts(_format_extra(is_audio), use_cookie_file=None)
    try:
        await asyncio.sleep(random.uniform(2, 4))
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=True))
        fp = _get_downloaded_file(video_id)
        if fp:
            logger.info(f"✅ Download OK (Android client): {fp}")
            return fp
        logger.warning("Android client: finished but file not found — trying cookie fallback")
    except Exception as e:
        logger.warning(f"Android client attempt failed: {str(e)[:200]}")

    # ── Attempt 2: Cookie file + desktop web client ───────────────────────────
    if not ENABLE_YT_COOKIES:
        logger.warning("Cookie fallback disabled (ENABLE_YT_COOKIES=false) – giving up")
        return None

    logger.info("⚙️  Falling back to cookie-based web client ...")
    cookie_file = await get_cookies()

    # FIX: guard against None or non-existent path before passing to yt-dlp
    if not cookie_file or not os.path.exists(cookie_file):
        logger.warning("❌ No valid cookie file available – skipping cookie fallback")
        return None

    ydl_opts = get_ytdlp_opts(_format_extra(is_audio), use_cookie_file=cookie_file)

    for attempt in range(2):
        try:
            await asyncio.sleep(random.uniform(1.0, 3.0))
            async with DOWNLOAD_SEMAPHORE:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=True))
            fp = _get_downloaded_file(video_id)
            if fp:
                logger.info(f"✅ Download OK (cookie fallback): {fp}")
                return fp
            logger.error("Cookie fallback: file not found after download")
            return None

        except Exception as e:
            if is_auth_error(e) and AUTO_REFRESH_COOKIES and attempt == 0:
                logger.warning(f"🤖 Auth/robot detected (attempt {attempt+1}) – refreshing ...")
                clear_old_cookies()
                await send_to_log_group(
                    text=(
                        "⚠️ **YouTube: Robot/Auth Detected**\n"
                        "🧹 Old cookies cleared\n"
                        "🔄 Regenerating ...\n#YouTubeCookies"
                    )
                )
                new_cf = await refresh_cookies_from_browser(reason="Robot/auth during download")
                # FIX: validate new_cf is a real file before using it
                if new_cf and os.path.exists(new_cf):
                    logger.info("✅ Fresh cookies – retrying ...")
                    ydl_opts = get_ytdlp_opts(_format_extra(is_audio), use_cookie_file=new_cf)
                    continue
                logger.error("Cookie regen failed or returned invalid path – aborting")
                return None
            logger.error(f"Download error (cookie attempt {attempt+1}): {str(e)[:300]}")
            return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
#  STREAMING HELPER
# ══════════════════════════════════════════════════════════════════════════════
STREAM_MIN_SIZE = 500_000
STREAM_FORMAT   = "140/bestaudio"

async def wait_for_partial_file(
    file_path:      str,
    min_size:       int   = STREAM_MIN_SIZE,
    check_interval: float = 0.3,
):
    while True:
        if os.path.exists(file_path) and os.path.getsize(file_path) > min_size:
            return
        await asyncio.sleep(check_interval)

async def download_song_stream(link: str) -> Tuple[Optional[str], Optional[asyncio.Task]]:
    if "instagram.com" in link.lower():
        return None, None
    video_id = extract_video_id(link)
    if not video_id:
        return None, None
    existing = _get_downloaded_file(video_id, prefer_m4a=True)
    if existing:
        return existing, None

    ydl_opts      = get_ytdlp_opts({"format": STREAM_FORMAT}, use_cookie_file=None)
    expected_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")
    loop          = asyncio.get_event_loop()

    async def _dl():
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=True))

    task = asyncio.create_task(_dl())
    try:
        await wait_for_partial_file(expected_path)
        return expected_path, task
    except Exception as e:
        logger.error(f"Streaming wait: {e}")
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
        logger.warning("PLAY_URL not set – skipping auto-test")
        return
    if retries <= 0:
        logger.error("❌ PLAY_URL test: max retries reached")
        await send_to_log_group(
            text=f"❌ **Cookie Auto-Test: Max Retries Reached**\nURL: `{PLAY_URL}`\n#CookieTest"
        )
        return

    logger.info(f"🎬 Auto-testing with PLAY_URL (retries={retries}) ...")
    test_dir = os.path.join(os.getcwd(), "cookie_test")
    os.makedirs(test_dir, exist_ok=True)
    video_id = extract_video_id(PLAY_URL)

    test_opts = get_ytdlp_opts(
        {
            "outtmpl": os.path.join(test_dir, "%(id)s.%(ext)s"),
            "format":  "bestaudio[ext=m4a]/bestaudio",
        },
        use_cookie_file=None,
    )
    try:
        loop = asyncio.get_event_loop()
        async with DOWNLOAD_SEMAPHORE:
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                await loop.run_in_executor(None, lambda: ydl.extract_info(PLAY_URL, download=True))

        file_path = None
        if video_id:
            for ext in ["mp3", "webm", "m4a", "opus", "mp4", "mkv"]:
                p = os.path.join(test_dir, f"{video_id}.{ext}")
                if os.path.exists(p):
                    file_path = p
                    break
        if not file_path:
            files = [
                os.path.join(test_dir, f) for f in os.listdir(test_dir)
                if os.path.isfile(os.path.join(test_dir, f))
            ]
            if files:
                file_path = max(files, key=os.path.getmtime)

        if file_path and os.path.exists(file_path):
            size_kb = os.path.getsize(file_path) // 1024
            logger.info(f"✅ Cookie test PASSED – {file_path} ({size_kb} KB)")
            await send_to_log_group(
                text=(
                    f"✅ **Cookie Auto-Test: PASSED**\n"
                    f"🎬 URL  : `{PLAY_URL}`\n"
                    f"📦 Size : `{size_kb} KB`\n#CookieTest"
                )
            )
            try:
                os.remove(file_path)
            except Exception:
                pass
        else:
            logger.error("❌ Cookie test FAILED – file not found")
            await send_to_log_group(
                text=f"❌ **Cookie Auto-Test: File Not Found**\nURL: `{PLAY_URL}`\n#CookieTest"
            )
    except Exception as e:
        err = str(e)
        logger.error(f"Cookie auto-test error: {err}")
        await send_to_log_group(
            text=f"❌ **Cookie Auto-Test Error**\n⚠️ `{err[:300]}`\n#CookieTest"
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
    out, err = await proc.communicate()
    if err:
        decoded = err.decode("utf-8")
        if "unavailable videos are hidden" in decoded.lower():
            return out.decode("utf-8")
        return decoded
    return out.decode("utf-8")

async def check_file_size(link: str) -> Optional[int]:
    if "instagram.com" in link.lower():
        return None
    try:
        ydl_opts = get_ytdlp_opts({"quiet": True}, use_cookie_file=None)
        loop = asyncio.get_event_loop()
        def _get():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
                return sum(
                    f.get("filesize") or f.get("filesize_approx") or 0
                    for f in info.get("formats", [])
                )
        return await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=60)
    except Exception as e:
        logger.error(f"check_file_size: {e}")
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

    def _is_youtube(self, link: str) -> bool:
        if not link:
            return False
        if "instagram.com" in link.lower():
            return False
        return True

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return False
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
        if not self._is_youtube(link):
            return None
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for r in (await results.next())["result"]:
            duration_sec = int(time_to_seconds(r["duration"])) if r["duration"] else 0
            return (
                r["title"], r["duration"], duration_sec,
                r["thumbnails"][0]["url"].split("?")[0], r["id"]
            )

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return None
        if "&" in link:
            link = link.split("&")[0]
        for r in (await VideosSearch(link, limit=1).next())["result"]:
            return r["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return None
        if "&" in link:
            link = link.split("&")[0]
        for r in (await VideosSearch(link, limit=1).next())["result"]:
            return r["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return None
        if "&" in link:
            link = link.split("&")[0]
        for r in (await VideosSearch(link, limit=1).next())["result"]:
            return r["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return 0, "Not a YouTube URL"
        try:
            f = await download_video(link)
            return (1, f) if f else (0, "Video download failed")
        except Exception as e:
            return 0, f"Video failed: {str(e)[:100]}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        ydl_opts = get_ytdlp_opts(
            {"quiet": True, "extract_flat": True, "playlistend": limit},
            use_cookie_file=None,
        )
        loop = asyncio.get_event_loop()
        try:
            def _get():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    return [e["id"] for e in info.get("entries", []) if e.get("id")]
            return await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=60)
        except Exception as e:
            logger.error(f"playlist: {e}")
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return None, None
        if "&" in link:
            link = link.split("&")[0]
        for r in (await VideosSearch(link, limit=1).next())["result"]:
            return {
                "title":        r["title"],
                "link":         r["link"],
                "vidid":        r["id"],
                "duration_min": r["duration"],
                "thumb":        r["thumbnails"][0]["url"].split("?")[0],
            }, r["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if not self._is_youtube(link):
            return [], link
        if "&" in link:
            link = link.split("&")[0]
        ydl_opts = get_ytdlp_opts({"quiet": True}, use_cookie_file=None)
        loop = asyncio.get_event_loop()
        try:
            def _get():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(link, download=False)
                    return [
                        {
                            "format":      f.get("format"),
                            "filesize":    f.get("filesize"),
                            "format_id":   f.get("format_id"),
                            "ext":         f.get("ext"),
                            "format_note": f.get("format_note"),
                            "yturl":       link,
                        }
                        for f in info.get("formats", [])
                        if "dash" not in str(f.get("format", "")).lower()
                    ]
            result = await asyncio.wait_for(loop.run_in_executor(None, _get), timeout=60)
            return result, link
        except Exception as e:
            logger.error(f"formats: {e}")
            return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        result = (await VideosSearch(link, limit=10).next()).get("result")
        r = result[query_type]
        return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]

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
        if not self._is_youtube(link):
            return None, False
        try:
            if video:
                f = await download_video(link)
            else:
                f = await download_song(link)
            return f, bool(f)
        except Exception as e:
            logger.error(f"download: {e}")
            return None, False

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def startup_services():
    if not ENABLE_YT_COOKIES:
        logger.info("YouTube cookie handling disabled – using Android client only.")
        return

    logger.info("🚀 Starting YouTube services ...")
    cleanup_playwright_profile()

    need_refresh = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )
    if need_refresh:
        logger.info("🔄 No valid cookies – generating ...")
        cf = await get_cookies(force_refresh=True)
        if cf:
            logger.info(f"✅ Cookies ready: {cf}")
        else:
            logger.warning(
                "⚠️ Startup cookie generation failed.\n"
                "   Downloads will use Android innertube client (no cookies).\n"
                "   Set YT_GOOGLE_EMAIL + YT_GOOGLE_PASSWORD for authenticated cookies,\n"
                "   or set ENABLE_YT_COOKIES=false to suppress this warning."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **YouTube Startup: Cookie Generation Failed**\n"
                    "Downloads will use Android client (no auth cookies).\n"
                    "Set `YT_GOOGLE_EMAIL` + `YT_GOOGLE_PASSWORD` for full auth.\n"
                    "#YouTubeCookies"
                )
            )
    else:
        logger.info("✅ Existing cookies valid – skipping regeneration.")

    logger.info("🎬 Running PLAY_URL startup test ...")
    await test_cookie_with_playurl(retries=2)
