import os
import re
import glob
import time
import random
import asyncio
import logging
import datetime
from typing import Union, Optional, Tuple

import aiohttp
import yt_dlp
from playwright.async_api import async_playwright

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGER
# ══════════════════════════════════════════════════════════════════════════════
try:
    from SHASHA_DRUGZ import app, LOGGER
    logger = LOGGER("SHASHA_DRUGZ/platforms/Instagram.py")
except Exception:
    app = None
    logger = logging.getLogger("Instagram")
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(h)
    logger.setLevel(logging.INFO)

try:
    from config import LOG_GROUP_ID
except Exception:
    LOG_GROUP_ID = None

# ══════════════════════════════════════════════════════════════════════════════
#  ENVIRONMENT / PATHS
# ══════════════════════════════════════════════════════════════════════════════
ENABLE_IG_COOKIES    = os.getenv("ENABLE_IG_COOKIES", "true").lower() == "true"
AUTO_REFRESH_COOKIES = True

IG_PROXIES           = os.getenv("IG_PROXIES", "")
IG_PLAYWRIGHT_PROXY  = os.getenv("IG_PLAYWRIGHT_PROXY", "")

# Optional: set these env vars to generate logged-in session cookies
IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

COOKIES_DIR = os.path.join(os.getcwd(), "cookies")
os.makedirs(COOKIES_DIR, exist_ok=True)

COOKIE_FILE = os.path.join(COOKIES_DIR, "instagram_cookies.txt")

IG_PROFILE_DIR = os.path.join(os.getcwd(), "ig_playwright_profile")
os.makedirs(IG_PROFILE_DIR, exist_ok=True)

IG_CACHE_DIR = os.path.join(os.getcwd(), "igcache")
os.makedirs(IG_CACHE_DIR, exist_ok=True)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)

# Only one cookie generation at a time — prevents Chromium profile corruption
_COOKIE_LOCK = asyncio.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  URL PATTERNS
# ══════════════════════════════════════════════════════════════════════════════
INSTAGRAM_REGEX = re.compile(
    r"(https?://)?(www\.)?instagram\.com/"
    r"(p|reel|reels|tv|stories)/([A-Za-z0-9_\-]+)/?"
)
SHORTCODE_REGEX = re.compile(
    r"instagram\.com/(?:p|reel|reels|tv|stories)/([A-Za-z0-9_\-]+)"
)

# ══════════════════════════════════════════════════════════════════════════════
#  USER-AGENT ROTATION
# ══════════════════════════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.6099.43 Mobile Safari/537.36",
]

# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_proxy_list(proxy_env: str):
    if not proxy_env:
        return []
    return [p.strip() for p in proxy_env.split(",") if p.strip()]

IG_PROXY_POOL            = _parse_proxy_list(IG_PROXIES)
IG_PLAYWRIGHT_PROXY_POOL = _parse_proxy_list(IG_PLAYWRIGHT_PROXY)

def choose_random_proxy(pool):
    return random.choice(pool) if pool else None

# ══════════════════════════════════════════════════════════════════════════════
#  LOG GROUP HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def send_to_log_group(text: str = None, file_obj=None):
    if not LOG_GROUP_ID or not app:
        logger.warning("LOG_GROUP_ID not configured or app unavailable – skipping")
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
        logger.warning("Instagram cookie file missing – cannot send to log group.")
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
        logger.info(f"✅ Instagram cookie sent to log group | reason={reason}")
    except Exception:
        try:
            with open(COOKIE_FILE, "rb") as f:
                await send_to_log_group(text=caption, file_obj=f)
        except Exception as e2:
            logger.error(f"Failed to send Instagram cookie file: {e2}")

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
#  COOKIE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def clear_old_cookies():
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            logger.warning("🧹 Old Instagram cookies removed")
        for f in glob.glob(os.path.join(COOKIES_DIR, "instagram*")):
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Failed to clear Instagram cookies: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  PLAYWRIGHT PROFILE LOCK CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def cleanup_playwright_profile():
    stale_files = [
        "SingletonLock", "SingletonCookie",
        "SingletonSocket", "DevToolsActivePort",
    ]
    for fname in stale_files:
        fpath = os.path.join(IG_PROFILE_DIR, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                logger.info(f"🧹 Removed stale IG profile file: {fname}")
            except Exception as e:
                logger.warning(f"Could not remove {fname}: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  BROWSER PROFILE COOKIE GENERATION  (Playwright)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(
    reason: str = "Profile cookie generation",
) -> bool:
    """
    Launch a persistent headless Chromium profile, visit Instagram
    (and optionally log in with IG_USERNAME / IG_PASSWORD), then close.
    yt-dlp will later export the Netscape cookie file from the profile.
    """
    logger.info(
        f"🌐 Launching browser profile to generate Instagram cookies [{reason}] ..."
    )
    await send_to_log_group(
        text=(
            f"🌐 **Instagram Browser Profile – Generating Cookies**\n\n"
            f"📝 Reason : {reason}\n"
            f"⏳ Launching headless Chromium ...\n\n"
            f"#InstagramCookies"
        )
    )
    cleanup_playwright_profile()
    proxy      = choose_random_proxy(IG_PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(USER_AGENTS)
    context    = None

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                IG_PROFILE_DIR,
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

            # ── Visit Instagram homepage ──────────────────────────────────────
            try:
                logger.info("🔗 Visiting instagram.com ...")
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await page.wait_for_timeout(4000)

                # Accept cookie / consent banner if present
                try:
                    accept_btn = page.locator(
                        "button:has-text('Allow all cookies'), "
                        "button:has-text('Allow'), "
                        "button:has-text('Accept')"
                    )
                    if await accept_btn.count() > 0:
                        await accept_btn.first.click()
                        await page.wait_for_timeout(2000)
                        logger.info("✅ Accepted Instagram cookie consent banner")
                except Exception:
                    pass

            except Exception as e:
                logger.warning(f"instagram.com visit warning: {e}")

            # ── Optional login with credentials ──────────────────────────────
            if IG_USERNAME and IG_PASSWORD:
                try:
                    logger.info(f"🔐 Attempting Instagram login for: {IG_USERNAME}")
                    await page.goto(
                        "https://www.instagram.com/accounts/login/",
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    await page.wait_for_timeout(3000)

                    username_input = page.locator("input[name='username']")
                    if await username_input.count() > 0:
                        await username_input.fill(IG_USERNAME)
                        await page.wait_for_timeout(random.randint(600, 1400))

                    password_input = page.locator("input[name='password']")
                    if await password_input.count() > 0:
                        await password_input.fill(IG_PASSWORD)
                        await page.wait_for_timeout(random.randint(600, 1400))

                    login_btn = page.locator("button[type='submit']")
                    if await login_btn.count() > 0:
                        await login_btn.click()
                        await page.wait_for_timeout(7000)
                        logger.info(
                            "✅ Instagram login submitted – waiting for session ..."
                        )

                    # Confirm login by checking for home-feed element
                    try:
                        await page.wait_for_selector(
                            "svg[aria-label='Home'], a[href='/']",
                            timeout=15_000,
                        )
                        logger.info("✅ Instagram login confirmed")
                    except Exception:
                        logger.warning(
                            "⚠️ Could not confirm Instagram login – proceeding anyway"
                        )

                except Exception as e:
                    logger.warning(f"Instagram login attempt failed: {e}")

            # ── Simulate natural browsing to seed more cookies ────────────────
            try:
                await page.goto(
                    "https://www.instagram.com/explore/",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                await page.wait_for_timeout(3000)
                await page.mouse.move(
                    random.randint(100, 600), random.randint(100, 400)
                )
                await page.wait_for_timeout(random.randint(500, 1500))
                await page.mouse.wheel(0, random.randint(300, 800))
                await page.wait_for_timeout(random.randint(500, 1000))
            except Exception:
                pass

            await context.close()
            logger.info(
                "✅ Instagram browser profile cookies refreshed successfully"
            )
            return True

    except Exception as e:
        logger.error(
            f"❌ Instagram Playwright cookie generation error: {str(e)[:300]}"
        )
        if context:
            try:
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Instagram Browser Profile – Cookie Generation Failed**\n\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n\n"
                f"#InstagramCookies"
            )
        )
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACT COOKIES FROM BROWSER PROFILE  (uses _COOKIE_LOCK)
# ══════════════════════════════════════════════════════════════════════════════
async def refresh_cookies_from_browser(
    reason: str = "On-demand refresh",
) -> Optional[str]:
    """
    Acquire the global lock, run Playwright to warm the profile,
    then call yt-dlp --cookies-from-browser to export Netscape cookies.
    Returns COOKIE_FILE path on success, None on failure.
    """
    async with _COOKIE_LOCK:
        # Another coroutine may have already refreshed while we waited
        if (
            os.path.exists(COOKIE_FILE)
            and verify_cookies_file(COOKIE_FILE)
            and not is_cookie_file_expired(COOKIE_FILE)
        ):
            logger.info(
                "✅ Instagram cookies already refreshed by another coroutine — reusing"
            )
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok:
            logger.error("Instagram browser profile cookie generation failed.")
            return None

        logger.info(
            f"🔄 Extracting Instagram cookies from browser profile ... "
            f"[reason={reason}]"
        )
        try:
            cmd = [
                "yt-dlp",
                "--cookies-from-browser", f"chrome:{IG_PROFILE_DIR}",
                "--cookies", COOKIE_FILE,
                "--no-check-certificate",
                "--quiet",
                "--no-download",
                "https://www.instagram.com/",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=120
            )

            if process.returncode == 0 and os.path.exists(COOKIE_FILE):
                if (
                    verify_cookies_file(COOKIE_FILE)
                    and not is_cookie_file_expired(COOKIE_FILE)
                ):
                    logger.info(
                        "✅ Instagram cookies extracted and verified successfully"
                    )
                    ip_info   = await get_public_ip_info() or {}
                    timestamp = datetime.datetime.utcnow().strftime(
                        "%Y-%m-%d %H:%M:%S UTC"
                    )
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
                    logger.error(
                        "❌ Instagram cookies failed verification or are expired"
                    )
                    if os.path.exists(COOKIE_FILE):
                        os.remove(COOKIE_FILE)

                    # One automatic retry with a fresh profile session
                    logger.info(
                        "🔁 Retrying Instagram cookie extraction with fresh browser ..."
                    )
                    ok2 = await generate_cookies_via_playwright(
                        reason=f"{reason} (retry)"
                    )
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
                            await send_cookie_file_to_log_group(
                                reason=f"{reason} (retry)"
                            )
                            return COOKIE_FILE
                    logger.error("❌ Instagram cookie retry extraction also failed")
                    return None
            else:
                error_msg = stderr.decode()[:300] if stderr else "Unknown error"
                logger.warning(
                    f"yt-dlp Instagram cookie extraction failed: {error_msg}"
                )
                await send_to_log_group(
                    text=(
                        f"⚠️ **Instagram Cookie Extraction Failed**\n\n"
                        f"📝 Reason : {reason}\n"
                        f"⚠️ Error  : `{error_msg[:250]}`\n\n"
                        f"#InstagramCookies"
                    )
                )
                return None

        except asyncio.TimeoutError:
            logger.error("Instagram cookie extraction timed out (120s)")
            return None
        except Exception as e:
            logger.error(f"Instagram cookie extraction error: {e}")
            return None

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE VERIFICATION  (Netscape format)
# ══════════════════════════════════════════════════════════════════════════════
def verify_cookies_file(filename: str) -> bool:
    """
    Validate that the cookie file is a valid Netscape-format file
    containing at least the minimum set of Instagram cookies.
    """
    try:
        if not os.path.exists(filename):
            logger.error(f"Instagram cookies file does not exist: {filename}")
            return False

        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()

        if "instagram.com" not in content and ".instagram.com" not in content:
            logger.error("No instagram.com domain found in cookies file")
            return False

        # Key cookies Instagram sets even for unauthenticated visitors
        important_cookies = [
            "sessionid", "csrftoken", "ds_user_id",
            "mid", "ig_did", "rur", "datr",
        ]
        found = [c for c in important_cookies if c in content]
        if len(found) < 2:
            logger.warning(
                f"⚠️ Too few important Instagram cookies found: {found}"
            )
            return False

        # Must be Netscape format, not JSON
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Instagram cookies file is JSON format, not Netscape")
            return False

        valid_lines = 0
        for line in content.strip().split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            if "\t" not in line:
                logger.error(
                    f"Invalid Netscape format (no tabs): {line[:100]}"
                )
                return False
            valid_lines += 1

        if valid_lines < 2:
            logger.error(
                f"Too few valid Instagram cookie lines: {valid_lines}"
            )
            return False

        logger.info(
            f"✅ Instagram cookies verified: {filename} | "
            f"lines={valid_lines} | found={found}"
        )
        return True

    except Exception as e:
        logger.error(f"Error verifying Instagram cookies file: {e}")
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
        logger.error(f"Failed to parse Instagram cookie expiry: {e}")
        return None


def is_cookie_file_expired(filepath: str) -> bool:
    if not os.path.exists(filepath):
        return True
    min_exp = get_cookie_min_expiry(filepath)
    if min_exp is None:
        logger.warning(
            "Could not determine Instagram cookie expiry – treating as expired."
        )
        return True
    now = int(time.time())
    if min_exp < now:
        logger.info(
            f"🕐 Instagram cookie expired at "
            f"{datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z"
        )
        return True
    remaining = min_exp - now
    logger.info(
        f"✅ Instagram cookie valid for "
        f"{remaining // 3600}h {(remaining % 3600) // 60}m"
    )
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH / RATE-LIMIT ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def is_auth_error(exception: Exception) -> bool:
    error_str = str(exception).lower()
    auth_indicators = [
        "login required",
        "not logged in",
        "checkpoint required",
        "rate limit",
        "rate-limit",
        "http error 401",
        "http error 403",
        "unable to extract",
        "cookie",
        "sign in",
        "authentication",
        "access denied",
        "forbidden",
        "bad credentials",
        "challenge required",
    ]
    return any(ind in error_str for ind in auth_indicators)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════
async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    """
    Return a valid Netscape cookie file path.
    Auto-generates / refreshes when the file is missing, invalid, or expired.
    """
    if not force_refresh and os.path.exists(COOKIE_FILE):
        if (
            verify_cookies_file(COOKIE_FILE)
            and not is_cookie_file_expired(COOKIE_FILE)
        ):
            logger.info("✅ Using existing (non-expired) Instagram cookies")
            return COOKIE_FILE
        else:
            logger.warning("Instagram cookies invalid or expired – regenerating ...")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)

    reason = (
        "Force refresh – login/rate-limit detected"
        if force_refresh
        else "Initial / expired"
    )
    return await refresh_cookies_from_browser(reason=reason)

# ══════════════════════════════════════════════════════════════════════════════
#  YT-DLP OPTIONS
# ══════════════════════════════════════════════════════════════════════════════
def get_ytdlp_opts(
    extra_opts: dict = None,
    use_cookie_file: str = None,
) -> dict:
    ua = random.choice(USER_AGENTS)
    base = {
        "outtmpl":            os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet":              True,
        "no_warnings":        True,
        "geo_bypass":         True,
        "nocheckcertificate": True,
        "retries":            10,
        "fragment_retries":   10,
        "cachedir":           IG_CACHE_DIR,
        "http_headers": {
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.instagram.com/",
        },
    }

    if use_cookie_file and os.path.exists(use_cookie_file):
        base["cookiefile"] = use_cookie_file
        logger.debug(f"Using Instagram cookiefile: {use_cookie_file}")
    else:
        # Fallback: read directly from the persistent Chromium profile
        base["cookiesfrombrowser"] = ("chrome", IG_PROFILE_DIR)
        logger.debug(
            "Falling back to cookiesfrombrowser with persistent IG profile"
        )

    proxy = choose_random_proxy(IG_PROXY_POOL)
    if proxy:
        base["proxy"] = proxy

    if extra_opts:
        base.update(extra_opts)
    return base

# ══════════════════════════════════════════════════════════════════════════════
#  FILE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _seconds_to_min(seconds) -> str:
    try:
        minutes = int(seconds) // 60
        secs    = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"
    except Exception:
        return "00:00"


def _extract_shortcode(url: str) -> Optional[str]:
    match = SHORTCODE_REGEX.search(url)
    return match.group(1) if match else None


def _find_downloaded_file(identifier: str) -> Optional[str]:
    """Scan downloads/ for any file whose name contains the given identifier."""
    if not identifier:
        return None
    for fname in os.listdir(DOWNLOAD_DIR):
        if identifier in fname:
            fpath = os.path.join(DOWNLOAD_DIR, fname)
            if os.path.isfile(fpath):
                return fpath
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  CORE DOWNLOAD (shared by video + audio paths)
# ══════════════════════════════════════════════════════════════════════════════
async def download_with_ytdlp(
    url: str,
    is_audio: bool = False,
) -> Optional[str]:
    """
    Download an Instagram reel / post video / IGTV clip using yt-dlp.
    Automatically refreshes cookies on auth / rate-limit errors (one retry).
    Returns the local file path on success, None on failure.
    """
    shortcode = _extract_shortcode(url)

    # Re-use a cached file if it already exists on disk
    if shortcode:
        existing = _find_downloaded_file(shortcode)
        if existing:
            logger.info(f"📁 Reusing cached Instagram file: {existing}")
            return existing

    cookie_file = await get_cookies()
    if not cookie_file:
        logger.error("No valid Instagram cookies – cannot download")
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
                def _run():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(url, download=True)
                info = await loop.run_in_executor(None, _run)

            video_id = (info or {}).get("id") or shortcode or ""
            filepath = None

            if info and info.get("requested_downloads"):
                filepath = info["requested_downloads"][0].get("filepath")
            if not filepath or not os.path.exists(filepath):
                filepath = (
                    _find_downloaded_file(video_id)
                    or _find_downloaded_file(shortcode or "")
                )

            if filepath and os.path.exists(filepath):
                logger.info(f"✅ Instagram download successful: {filepath}")
                return filepath

            logger.error("Instagram download finished but file not found on disk")
            return None

        except Exception as e:
            if is_auth_error(e) and AUTO_REFRESH_COOKIES and attempt == 0:
                logger.warning(
                    f"🔒 Instagram auth/rate-limit detected (attempt {attempt + 1})"
                    " – regenerating cookies ..."
                )
                clear_old_cookies()
                await send_to_log_group(
                    text=(
                        "⚠️ **Instagram: Auth / Rate-Limit Detected**\n\n"
                        "🧹 Old cookies cleared\n"
                        "🔄 Regenerating cookies via Browser Profile ...\n\n"
                        "#InstagramCookies"
                    )
                )
                new_cookie = await refresh_cookies_from_browser(
                    reason="Auth/rate-limit detected during download"
                )
                if new_cookie:
                    logger.info(
                        "✅ Fresh Instagram cookies obtained – retrying download ..."
                    )
                    ydl_opts = _build_opts(new_cookie)
                    continue
                else:
                    logger.error(
                        "Instagram cookie regeneration failed – aborting download"
                    )
                    return None
            else:
                logger.error(
                    f"Instagram download error (attempt {attempt + 1}): "
                    f"{str(e)[:300]}"
                )
                return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
#  METADATA (no download)
# ══════════════════════════════════════════════════════════════════════════════
async def _fetch_info(url: str) -> Optional[dict]:
    cookie_file = await get_cookies()
    ydl_opts    = get_ytdlp_opts(
        {"skip_download": True},
        use_cookie_file=cookie_file,
    )
    loop = asyncio.get_event_loop()
    try:
        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        return await loop.run_in_executor(None, _run)
    except Exception as e:
        logger.error(f"Instagram info extraction error: {str(e)[:300]}")
        return None

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def startup_services():
    """
    Called once at bot startup.
    Ensures valid Instagram cookies exist before any download request arrives.
    Mirrors the YouTube startup_services() pattern exactly.
    """
    if not ENABLE_IG_COOKIES:
        logger.info(
            "Instagram cookie handling disabled (ENABLE_IG_COOKIES=false)."
        )
        return

    logger.info("🚀 Starting Instagram cookie services (Browser Profile) ...")
    cleanup_playwright_profile()

    need_refresh = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )

    if need_refresh:
        logger.info(
            "🔄 No valid Instagram cookies – generating via Browser Profile ..."
        )
        cookie_file = await get_cookies(force_refresh=True)
        if cookie_file:
            logger.info(f"✅ Instagram cookies ready: {cookie_file}")
        else:
            logger.warning(
                "⚠️ Instagram cookie generation failed on startup.\n"
                "   The bot will retry automatically on the first download request."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **Instagram Startup Cookie Generation Failed**\n\n"
                    "Could not generate cookies via Browser Profile on startup.\n"
                    "The bot will retry automatically when a download is requested.\n\n"
                    "#InstagramCookies"
                )
            )
    else:
        logger.info(
            "✅ Existing Instagram cookies are valid and unexpired – "
            "skipping regeneration."
        )

# ══════════════════════════════════════════════════════════════════════════════
#  InstagramAPI CLASS
# ══════════════════════════════════════════════════════════════════════════════
class InstagramAPI:

    def __init__(self):
        self.regex    = INSTAGRAM_REGEX
        self.base_url = "https://www.instagram.com/"

    # ── VALIDATION ────────────────────────────────────────────────────────────
    async def valid(self, link: str) -> bool:
        """Return True if the link is a recognised Instagram URL."""
        return bool(re.search(self.regex, link))

    # ── METADATA (no download) ────────────────────────────────────────────────
    async def info(self, url: str) -> Optional[dict]:
        """
        Fetch metadata for an Instagram post / reel / video
        without downloading the media file.
        """
        raw = await _fetch_info(url)
        if not raw:
            return None
        duration_sec = raw.get("duration") or 0
        return {
            "title":        raw.get("title")    or raw.get("uploader") or "Instagram Video",
            "uploader":     raw.get("uploader") or "Unknown",
            "duration_sec": duration_sec,
            "duration_min": _seconds_to_min(duration_sec),
            "thumbnail":    raw.get("thumbnail") or "",
            "webpage_url":  raw.get("webpage_url") or url,
            "ext":          raw.get("ext") or "mp4",
            "id":           raw.get("id") or _extract_shortcode(url) or "",
        }

    # ── VIDEO DOWNLOAD ────────────────────────────────────────────────────────
    async def download(self, url: str) -> tuple:
        """
        Download an Instagram reel / post video / IGTV clip.

        Returns
        -------
        (track_details dict, filepath str)  on success
        (False, None)                        on failure
        """
        filepath = await download_with_ytdlp(url, is_audio=False)
        if not filepath:
            return False, None

        meta = await self.info(url) or {}
        track_details = {
            "title":        meta.get("title",        "Instagram Video"),
            "uploader":     meta.get("uploader",     "Unknown"),
            "duration_sec": meta.get("duration_sec", 0),
            "duration_min": meta.get("duration_min", "00:00"),
            "thumb":        meta.get("thumbnail",    ""),
            "filepath":     filepath,
        }
        return track_details, filepath

    # ── AUDIO EXTRACTION ──────────────────────────────────────────────────────
    async def download_audio(self, url: str) -> tuple:
        """
        Extract audio from an Instagram reel / video as mp3.

        Returns
        -------
        (track_details dict, filepath str)  on success
        (False, None)                        on failure
        """
        filepath = await download_with_ytdlp(url, is_audio=True)
        if not filepath:
            return False, None

        meta = await self.info(url) or {}
        track_details = {
            "title":        meta.get("title",        "Instagram Audio"),
            "uploader":     meta.get("uploader",     "Unknown"),
            "duration_sec": meta.get("duration_sec", 0),
            "duration_min": meta.get("duration_min", "00:00"),
            "thumb":        meta.get("thumbnail",    ""),
            "filepath":     filepath,
        }
        return track_details, filepath

    # ── THUMBNAIL ─────────────────────────────────────────────────────────────
    async def thumbnail(self, url: str) -> Optional[str]:
        """Return the thumbnail URL for an Instagram post, or None."""
        meta = await self.info(url)
        return meta.get("thumbnail") if meta else None

    # ── TRACK-STYLE HELPER  (mirrors YouTube / Spotify / Resso pattern) ───────
    async def track(self, url: str) -> tuple:
        """
        Return (track_details dict, shortcode str) without downloading.
        Matches the interface used by YouTubeAPI.track(), SpotifyAPI.track(), etc.
        """
        meta = await self.info(url)
        if not meta:
            return None, None

        track_details = {
            "title":        meta["title"],
            "link":         meta["webpage_url"],
            "vidid":        meta["id"],
            "duration_min": meta["duration_min"],
            "thumb":        meta["thumbnail"],
        }
        return track_details, meta["id"]
