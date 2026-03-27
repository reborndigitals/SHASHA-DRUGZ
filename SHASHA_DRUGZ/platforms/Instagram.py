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
IG_USERNAME          = os.getenv("IG_USERNAME", "onixxghostt")
IG_PASSWORD          = os.getenv("IG_PASSWORD", "143@Frnds")
IG_TOTP_SECRET       = os.getenv("IG_TOTP_SECRET", "3IGFI5H7SACGQQVP7W7VCTCX76O6NDME")

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COOKIES_DIR = os.path.join(os.getcwd(), "cookies")
os.makedirs(COOKIES_DIR, exist_ok=True)
COOKIE_FILE = os.path.join(COOKIES_DIR, "instagram_cookies.txt")
IG_PROFILE_DIR = os.path.join(os.getcwd(), "ig_playwright_profile")
os.makedirs(IG_PROFILE_DIR, exist_ok=True)
IG_CACHE_DIR = os.path.join(os.getcwd(), "igcache")
os.makedirs(IG_CACHE_DIR, exist_ok=True)
SCREENSHOT_DIR = os.path.join(os.getcwd(), "ig_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
_COOKIE_LOCK       = asyncio.Lock()

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
#  USER-AGENT ROTATION  (realistic desktop Chrome UAs only)
# ══════════════════════════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
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

async def _send_screenshot_to_log_group(screenshot_path: str, caption: str):
    if not LOG_GROUP_ID or not app or not os.path.exists(screenshot_path):
        return
    try:
        await app.send_photo(
            chat_id=LOG_GROUP_ID,
            photo=screenshot_path,
            caption=caption,
        )
        logger.info(f"📸 Debug screenshot sent to log group: {screenshot_path}")
    except Exception as e:
        logger.error(f"Failed to send screenshot to log group: {e}")

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
#  NETSCAPE COOKIE WRITER
# ══════════════════════════════════════════════════════════════════════════════
def _write_netscape_cookies(cookies: list, filepath: str) -> bool:
    try:
        lines = ["# Netscape HTTP Cookie File", "# Auto-generated by Instagram.py\n"]
        written = 0
        for c in cookies:
            domain = c.get("domain", "")
            if not domain:
                continue
            if not domain.startswith("."):
                domain = "." + domain
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            path               = c.get("path", "/")
            secure             = "TRUE" if c.get("secure", False) else "FALSE"
            expires_raw        = c.get("expires", -1)
            expires            = int(expires_raw) if expires_raw and expires_raw > 0 else 0
            name               = c.get("name", "")
            value              = c.get("value", "")
            if not name:
                continue
            lines.append(
                f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
            )
            written += 1
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info(f"✅ Wrote {written} cookies to Netscape file: {filepath}")
        return written > 0
    except Exception as e:
        logger.error(f"Failed to write Netscape cookie file: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  HUMAN-LIKE TYPING
# ══════════════════════════════════════════════════════════════════════════════
async def _human_type(page, selector_or_locator, text: str) -> None:
    """
    Types text character-by-character with random delays to mimic human input.
    Accepts either a CSS selector string or an already-resolved Locator.
    """
    try:
        if isinstance(selector_or_locator, str):
            el = page.locator(selector_or_locator)
        else:
            el = selector_or_locator

        await el.click()
        await page.wait_for_timeout(random.randint(200, 500))

        # Clear existing value first
        await el.press("Control+a")
        await page.wait_for_timeout(random.randint(100, 300))
        await el.press("Delete")
        await page.wait_for_timeout(random.randint(100, 300))

        for char in text:
            await el.press(char)
            await page.wait_for_timeout(random.randint(60, 200))

        await page.wait_for_timeout(random.randint(400, 900))
    except Exception as e:
        logger.warning(f"_human_type fallback to fill(): {e}")
        try:
            if isinstance(selector_or_locator, str):
                await page.fill(selector_or_locator, text)
            else:
                await selector_or_locator.fill(text)
        except Exception as e2:
            logger.error(f"_human_type fill also failed: {e2}")

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE STATE LOGGER
# ══════════════════════════════════════════════════════════════════════════════
async def _log_page_state(page, label: str) -> str:
    try:
        current_url   = page.url
        current_title = await page.title()
        logger.info(
            f"📍 [{label}] URL   : {current_url}\n"
            f"            Title : {current_title}"
        )
        ts      = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        label_s = re.sub(r"[^A-Za-z0-9_\-]", "_", label)[:40]
        path    = os.path.join(SCREENSHOT_DIR, f"ig_{label_s}_{ts}.png")
        await page.screenshot(path=path, full_page=False)
        logger.info(f"📸 Screenshot saved: {path}")
        return path
    except Exception as e:
        logger.warning(f"_log_page_state failed [{label}]: {e}")
        return ""

# ══════════════════════════════════════════════════════════════════════════════
#  POPUP DISMISSAL
# ══════════════════════════════════════════════════════════════════════════════
async def _dismiss_popups(page) -> None:
    dismiss_targets = [
        ("cookie consent",    "[data-testid='cookie-policy-manage-dialog-accept-button'], "
                              "button:has-text('Allow all cookies'), "
                              "button:has-text('Allow essential and optional cookies')"),
        ("save login info",   "button:has-text('Save info'), button:has-text('Save Info')"),
        ("not now (generic)", "button:has-text('Not now'), button:has-text('Not Now')"),
        ("notifications",     "button:has-text('Not Now'), button:has-text('Turn On')"),
    ]
    for description, selector in dismiss_targets:
        try:
            btn = page.locator(selector)
            if await btn.count() > 0:
                await btn.first.click()
                logger.info(f"✅ Dismissed popup: {description}")
                await page.wait_for_timeout(random.randint(1200, 2200))
        except Exception as ex:
            logger.debug(f"Popup dismiss [{description}] skipped: {ex}")

# ══════════════════════════════════════════════════════════════════════════════
#  CHECKPOINT / 2FA DETECTION
# ══════════════════════════════════════════════════════════════════════════════
async def _check_for_checkpoint(page) -> bool:
    checkpoint_signals = [
        "challenge", "checkpoint", "accounts/suspended",
        "unusualactivity", "verification",
    ]
    current_url = page.url.lower()
    if any(sig in current_url for sig in checkpoint_signals):
        logger.error(
            f"🚨 Instagram CHECKPOINT detected! URL: {page.url}\n"
            "Resolve the challenge manually in a real browser, export cookies,\n"
            f"and place them at: {COOKIE_FILE}"
        )
        return True
    try:
        body_text = (await page.inner_text("body")).lower()
        text_signals = [
            "verify your account", "verify it's you",
            "we detected an unusual", "suspicious activity",
            "this account has been", "complete a security check",
        ]
        if any(sig in body_text for sig in text_signals):
            logger.error(f"🚨 Instagram CHECKPOINT detected via page text! URL: {page.url}")
            return True
    except Exception:
        pass
    return False

async def _check_for_2fa(page) -> str:
    try:
        current_url = page.url.lower()
        if "two_factor" in current_url or "2fa" in current_url:
            body_text = (await page.inner_text("body")).lower()
            if "text message" in body_text or "sms" in body_text:
                return "sms"
            return "totp"
        code_input = page.locator(
            "input[name='verificationCode'], "
            "input[aria-label*='Security Code'], "
            "input[aria-label*='Confirmation Code'], "
            "input[placeholder*='6-digit code'], "
            "input[placeholder*='security code']"
        )
        if await code_input.count() > 0:
            body_text = (await page.inner_text("body")).lower()
            if "text message" in body_text or "sms" in body_text:
                return "sms"
            return "totp"
    except Exception as e:
        logger.debug(f"_check_for_2fa error: {e}")
    return "none"

async def _handle_2fa(page) -> bool:
    fa_type = await _check_for_2fa(page)
    if fa_type == "none":
        return True
    if fa_type == "sms":
        logger.error(
            "🔒 Instagram requires SMS 2FA – cannot automate.\n"
            "Disable SMS 2FA or switch to authenticator app + set IG_TOTP_SECRET."
        )
        await send_to_log_group(
            text="🔒 **Instagram SMS 2FA Required – Cannot Automate**\n#2FA"
        )
        return False
    if fa_type == "totp":
        if not IG_TOTP_SECRET:
            logger.error("🔒 TOTP 2FA required but IG_TOTP_SECRET not set.")
            await send_to_log_group(
                text="🔒 **Instagram TOTP 2FA Required – IG_TOTP_SECRET Not Set**\n#2FA"
            )
            return False
        try:
            import pyotp
        except ImportError:
            logger.error("pyotp not installed. Run: pip install pyotp")
            return False
        try:
            totp  = pyotp.TOTP(IG_TOTP_SECRET)
            code  = totp.now()
            logger.info(f"🔑 TOTP code generated: {code}")
            code_input = page.locator(
                "input[name='verificationCode'], "
                "input[aria-label*='Security Code'], "
                "input[aria-label*='Confirmation Code'], "
                "input[placeholder*='6-digit code'], "
                "input[placeholder*='security code']"
            )
            if await code_input.count() == 0:
                logger.error("❌ TOTP input field not found")
                return False
            await code_input.first.fill(code)
            await page.wait_for_timeout(random.randint(600, 1000))
            submit_btn = page.locator(
                "button[type='submit'], "
                "button:has-text('Confirm'), "
                "button:has-text('Submit')"
            )
            if await submit_btn.count() > 0:
                await submit_btn.first.click()
            else:
                await code_input.first.press("Enter")
            logger.info("✅ TOTP submitted")
            await page.wait_for_timeout(5000)
            return True
        except Exception as e:
            logger.error(f"TOTP handling error: {e}")
            return False
    return False

async def _verify_login_success(context, page) -> bool:
    try:
        all_cookies   = await context.cookies()
        cookie_names  = {c["name"] for c in all_cookies if "instagram.com" in c.get("domain", "")}
        auth_cookies  = {"sessionid", "ds_user_id", "rur"}
        found_auth    = cookie_names & auth_cookies
        current_url   = page.url
        current_title = await page.title()
        logger.info(
            f"🔍 Login verification:\n"
            f"   URL           : {current_url}\n"
            f"   Title         : {current_title}\n"
            f"   Cookies found : {cookie_names}\n"
            f"   Auth cookies  : {found_auth or 'NONE ← login failed'}"
        )
        if found_auth:
            logger.info(f"✅ Login verified via session cookies: {found_auth}")
            return True
        return False
    except Exception as e:
        logger.error(f"_verify_login_success error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  FIND INPUT FIELDS  (handles old + new Instagram login page layouts)
# ══════════════════════════════════════════════════════════════════════════════
async def _find_username_input(page):
    """
    Instagram redesigned their login page (?flo=true).
    The username field may now use different attributes.
    Try multiple selectors in order of specificity.
    """
    candidates = [
        "input[name='username']",
        "input[name='email']",
        "input[aria-label='Mobile number, username or email']",
        "input[aria-label*='username']",
        "input[aria-label*='email']",
        "input[autocomplete='username']",
        "input[type='text']",
        "input[type='email']",
    ]
    for sel in candidates:
        try:
            el = page.locator(sel)
            count = await el.count()
            if count > 0:
                # Make sure it's visible
                if await el.first.is_visible():
                    logger.info(f"✅ Username field found via selector: {sel}")
                    return el.first
        except Exception:
            continue
    logger.error("❌ Username input not found with any known selector")
    return None

async def _find_password_input(page):
    """
    Find the password field with multiple fallback selectors.
    """
    candidates = [
        "input[name='password']",
        "input[type='password']",
        "input[aria-label='Password']",
        "input[aria-label*='assword']",
        "input[autocomplete='current-password']",
    ]
    for sel in candidates:
        try:
            el = page.locator(sel)
            count = await el.count()
            if count > 0:
                if await el.first.is_visible():
                    logger.info(f"✅ Password field found via selector: {sel}")
                    return el.first
        except Exception:
            continue
    logger.error("❌ Password input not found with any known selector")
    return None

async def _find_submit_button(page):
    """
    Find the login submit button with multiple fallback selectors.
    The new Instagram page uses a blue 'Log in' button.
    """
    candidates = [
        "button[type='submit']",
        "button:has-text('Log in')",
        "button:has-text('Log In')",
        "button:has-text('Login')",
        "div[role='button']:has-text('Log in')",
        "div[role='button']:has-text('Login')",
        "[data-testid='royal_login_button']",
    ]
    for sel in candidates:
        try:
            el = page.locator(sel)
            count = await el.count()
            if count > 0:
                if await el.first.is_visible():
                    logger.info(f"✅ Submit button found via selector: {sel}")
                    return el.first
        except Exception:
            continue
    logger.error("❌ Submit button not found with any known selector")
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  DETECT WHICH LOGIN URL IS ACTIVE
# ══════════════════════════════════════════════════════════════════════════════
async def _navigate_to_login(page) -> bool:
    """
    Instagram sometimes serves the new layout at /?flo=true instead of
    /accounts/login/. Try both and wait for the username input to appear.
    Returns True if login page loaded successfully.
    """
    login_urls = [
        "https://www.instagram.com/accounts/login/",
        "https://www.instagram.com/?flo=true",
        "https://www.instagram.com/",
    ]
    for url in login_urls:
        try:
            logger.info(f"🔗 Trying login URL: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            # Give React time to mount
            await page.wait_for_timeout(random.randint(2500, 4000))

            # Try to wait for username field
            try:
                await page.wait_for_selector(
                    "input[name='username'], "
                    "input[name='email'], "
                    "input[aria-label*='username'], "
                    "input[aria-label*='Mobile number'], "
                    "input[type='text']",
                    timeout=12_000,
                    state="visible",
                )
                logger.info(f"✅ Login form detected at: {url}")
                return True
            except Exception:
                logger.warning(f"⚠️ Login form not detected at {url} – trying next ...")
                continue
        except Exception as e:
            logger.warning(f"⚠️ Navigation to {url} failed: {e}")
            continue

    logger.error("❌ Could not load Instagram login page from any known URL")
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  STEALTH INIT SCRIPT
# ══════════════════════════════════════════════════════════════════════════════
STEALTH_SCRIPT = """
    // Hide webdriver flag
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // Realistic language + plugin values
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const p = { length: 3 };
            p[0] = { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' };
            p[1] = { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' };
            p[2] = { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' };
            return p;
        }
    });

    // Chrome runtime object
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };

    // Override permissions query to avoid detection
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );

    // Prevent iframe detection
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() { return window; }
    });

    // Spoof hardware concurrency and memory
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

    // Touch points (desktop)
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
"""

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PLAYWRIGHT COOKIE GENERATION
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(
    reason: str = "Profile cookie generation",
) -> bool:
    logger.info(
        f"🌐 Launching Playwright to generate Instagram cookies [{reason}] ...\n"
        f"   Credentials : {'✅ set' if IG_USERNAME and IG_PASSWORD else '❌ NOT SET – guest cookies only'}\n"
        f"   TOTP secret : {'✅ set' if IG_TOTP_SECRET else '⚠️  not set'}"
    )
    await send_to_log_group(
        text=(
            f"🌐 **Instagram – Generating Cookies**\n\n"
            f"📝 Reason      : {reason}\n"
            f"🔐 Credentials : {'Set ✅' if IG_USERNAME and IG_PASSWORD else 'NOT SET ❌'}\n"
            f"⏳ Launching headless Chromium ...\n\n"
            f"#InstagramCookies"
        )
    )
    cleanup_playwright_profile()
    proxy      = choose_random_proxy(IG_PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(USER_AGENTS)
    context    = None
    login_ok   = False

    try:
        async with async_playwright() as p:
            # ── Launch persistent context ─────────────────────────────────────
            context = await p.chromium.launch_persistent_context(
                IG_PROFILE_DIR,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-extensions",
                    "--disable-gpu",
                    "--disable-web-security",
                    "--window-size=1920,1080",
                    "--start-maximized",
                    f"--user-agent={user_agent}",
                ],
                proxy={"server": proxy} if proxy else None,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                ignore_https_errors=True,
                accept_downloads=False,
            )

            page = await context.new_page()

            # Inject stealth scripts before any navigation
            await page.add_init_script(STEALTH_SCRIPT)

            # ── Step 1 – Visit homepage to collect initial cookies ────────────
            logger.info("🔗 Step 1/5 – Visiting instagram.com ...")
            try:
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await page.wait_for_timeout(random.randint(3000, 5500))
                await _log_page_state(page, "step1_homepage")
            except Exception as e:
                logger.warning(f"⚠️ Homepage navigation warning (non-fatal): {e}")

            # ── Step 2 – Accept cookie banner ─────────────────────────────────
            logger.info("🔗 Step 2/5 – Accepting cookie consent banner ...")
            try:
                accept_selectors = [
                    "[data-testid='cookie-policy-manage-dialog-accept-button']",
                    "button:has-text('Allow all cookies')",
                    "button:has-text('Allow essential and optional cookies')",
                    "button:has-text('Allow')",
                    "button:has-text('Accept')",
                    "button:has-text('Accept All')",
                ]
                for sel in accept_selectors:
                    btn = page.locator(sel)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click()
                        logger.info(f"✅ Cookie consent accepted via: {sel}")
                        await page.wait_for_timeout(random.randint(1500, 2500))
                        break
                else:
                    logger.info("ℹ️  No cookie consent banner detected")
            except Exception as e:
                logger.debug(f"Cookie consent handling skipped: {e}")

            # ── Step 3 – Login flow ───────────────────────────────────────────
            if IG_USERNAME and IG_PASSWORD:
                logger.info(f"🔗 Step 3/5 – Logging in as: {IG_USERNAME} ...")
                try:
                    login_loaded = await _navigate_to_login(page)
                    shot = await _log_page_state(page, "step3_login_page")

                    if not login_loaded:
                        await _send_screenshot_to_log_group(
                            shot, "❌ IG: Login page failed to load"
                        )
                        # Collect guest cookies anyway
                    elif await _check_for_checkpoint(page):
                        shot = await _log_page_state(page, "step3_checkpoint_prelogin")
                        await _send_screenshot_to_log_group(
                            shot,
                            "🚨 **IG: Checkpoint BEFORE login**\n"
                            "Account may be flagged. Resolve manually."
                        )
                    else:
                        # ── Find and fill username ────────────────────────────
                        username_input = await _find_username_input(page)
                        if username_input:
                            await _human_type(page, username_input, IG_USERNAME)
                            logger.info(f"✍️  Username entered: {IG_USERNAME}")

                            # Pressing Tab often advances focus to password on new layout
                            await username_input.press("Tab")
                            await page.wait_for_timeout(random.randint(500, 1000))
                        else:
                            shot = await _log_page_state(page, "step3_no_username_field")
                            await _send_screenshot_to_log_group(
                                shot, "❌ IG: Username input field not found"
                            )

                        # ── Find and fill password ────────────────────────────
                        password_input = await _find_password_input(page)
                        if password_input:
                            await _human_type(page, password_input, IG_PASSWORD)
                            logger.info("✍️  Password entered")
                        else:
                            shot = await _log_page_state(page, "step3_no_password_field")
                            await _send_screenshot_to_log_group(
                                shot, "❌ IG: Password input field not found"
                            )

                        # Small random pause before clicking submit
                        await page.wait_for_timeout(random.randint(800, 1500))

                        # ── Find and click submit ─────────────────────────────
                        submit_btn = await _find_submit_button(page)
                        if submit_btn:
                            await submit_btn.click()
                            logger.info("🖱️  Login button clicked – awaiting response ...")
                            await page.wait_for_timeout(random.randint(6000, 9000))
                        else:
                            # Last resort: press Enter on password field
                            if password_input:
                                await password_input.press("Enter")
                                logger.info("🖱️  Pressed Enter on password field as fallback")
                                await page.wait_for_timeout(random.randint(6000, 9000))
                            else:
                                logger.error("❌ Cannot submit login – no button or password field found")
                                shot = await _log_page_state(page, "step3_no_submit")
                                await _send_screenshot_to_log_group(
                                    shot, "❌ IG: Cannot submit login form"
                                )

                        shot = await _log_page_state(page, "step3_post_submit")

                        # ── Post-submit checks ────────────────────────────────
                        if await _check_for_checkpoint(page):
                            shot = await _log_page_state(page, "step3_checkpoint_postlogin")
                            await _send_screenshot_to_log_group(
                                shot,
                                "🚨 **IG: Checkpoint after login**\n"
                                "Meta is blocking automated login. See logs."
                            )
                            await send_to_log_group(
                                text=(
                                    "🚨 **Instagram Checkpoint / Suspicious-Activity Block**\n\n"
                                    "Meta flagged this login attempt.\n"
                                    "Resolution:\n"
                                    "1. Open Instagram in a real browser\n"
                                    "2. Log in and complete the challenge\n"
                                    "3. Export cookies to Netscape format\n"
                                    f"4. Place at: `{COOKIE_FILE}`\n"
                                    "5. Restart the bot\n\n"
                                    "#InstagramCookies #Checkpoint"
                                )
                            )
                        elif await _check_for_2fa(page) != "none":
                            logger.info("🔑 2FA prompt detected ...")
                            shot = await _log_page_state(page, "step3_2fa_prompt")
                            await _send_screenshot_to_log_group(shot, "🔑 IG: 2FA prompt detected")
                            fa_ok = await _handle_2fa(page)
                            if fa_ok:
                                await page.wait_for_timeout(random.randint(4000, 6000))
                                await _dismiss_popups(page)
                                login_ok = await _verify_login_success(context, page)
                            else:
                                logger.error("❌ 2FA handling failed")
                                shot = await _log_page_state(page, "step3_2fa_failed")
                                await _send_screenshot_to_log_group(shot, "❌ IG: 2FA handling failed")
                        else:
                            await _dismiss_popups(page)
                            await page.wait_for_timeout(random.randint(2000, 3500))
                            shot = await _log_page_state(page, "step3_post_popups")
                            login_ok = await _verify_login_success(context, page)

                            if login_ok:
                                logger.info("✅ Instagram login confirmed!")
                                await send_to_log_group(
                                    text=(
                                        f"✅ **Instagram Login Successful**\n\n"
                                        f"👤 Account : `{IG_USERNAME}`\n"
                                        f"📝 Reason  : {reason}\n\n"
                                        f"#InstagramCookies"
                                    )
                                )
                            else:
                                logger.error(
                                    "❌ Login did NOT result in a session cookie.\n"
                                    "   Possible: wrong credentials, account disabled, "
                                    "or Meta rejected the headless browser silently."
                                )
                                shot = await _log_page_state(page, "step3_login_failed")
                                await _send_screenshot_to_log_group(
                                    shot,
                                    "❌ **IG: Login failed – no session cookie issued**\n"
                                    "Check IG_USERNAME / IG_PASSWORD and see logs."
                                )
                                await send_to_log_group(
                                    text=(
                                        f"❌ **Instagram Login Failed**\n\n"
                                        f"👤 Account  : `{IG_USERNAME}`\n"
                                        f"📝 Reason   : {reason}\n\n"
                                        f"Possible causes:\n"
                                        f"• Wrong credentials\n"
                                        f"• Account disabled or flagged\n"
                                        f"• Headless browser detected by Meta\n\n"
                                        f"#InstagramCookies"
                                    )
                                )

                except Exception as e:
                    logger.error(
                        f"❌ Unhandled exception during Instagram login:\n"
                        f"   {type(e).__name__}: {str(e)[:400]}"
                    )
                    shot = await _log_page_state(page, "step3_exception")
                    await _send_screenshot_to_log_group(
                        shot, f"❌ **IG: Login exception**\n`{str(e)[:300]}`"
                    )
            else:
                logger.warning(
                    "⚠️ Step 3/5 – SKIPPED (IG_USERNAME / IG_PASSWORD not set)\n"
                    "   Only guest cookies will be collected."
                )

            # ── Step 4 – Natural browsing simulation ──────────────────────────
            logger.info("🔗 Step 4/5 – Simulating natural browsing ...")
            try:
                await page.goto(
                    "https://www.instagram.com/explore/",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                await page.wait_for_timeout(random.randint(2000, 4000))
                await page.mouse.move(
                    random.randint(100, 600), random.randint(100, 400)
                )
                await page.wait_for_timeout(random.randint(500, 1500))
                await page.mouse.wheel(0, random.randint(300, 800))
                await page.wait_for_timeout(random.randint(500, 1000))
                await _log_page_state(page, "step4_explore")
            except Exception as e:
                logger.debug(f"Natural browsing simulation failed (non-fatal): {e}")

            # ── Step 5 – Export cookies ───────────────────────────────────────
            logger.info("🔗 Step 5/5 – Exporting cookies ...")
            all_cookies = await context.cookies()
            await context.close()
            context = None

            ig_cookies = [
                c for c in all_cookies
                if "instagram.com" in c.get("domain", "")
                or "facebook.com" in c.get("domain", "")
            ]
            cookie_names = {c["name"] for c in ig_cookies}
            logger.info(f"🍪 Collected {len(ig_cookies)} cookies: {cookie_names}")

            if not ig_cookies:
                logger.error("❌ Zero Instagram cookies collected – page likely never loaded.")
                return False

            ok = _write_netscape_cookies(ig_cookies, COOKIE_FILE)
            if ok:
                logger.info(
                    f"✅ Cookie file written.\n"
                    f"   Login status : {'AUTHENTICATED ✅' if login_ok else 'GUEST ONLY ⚠️'}\n"
                    f"   Cookies      : {cookie_names}"
                )
            return ok

    except Exception as e:
        logger.error(
            f"❌ Instagram Playwright session crashed:\n"
            f"   {type(e).__name__}: {str(e)[:400]}"
        )
        if context:
            try:
                pages = context.pages
                if pages:
                    shot = await _log_page_state(pages[-1], "fatal_crash")
                    await _send_screenshot_to_log_group(
                        shot, f"❌ **IG: Playwright session crashed**\n`{str(e)[:300]}`"
                    )
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Instagram Browser Profile – Session Crashed**\n\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n\n"
                f"#InstagramCookies"
            )
        )
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  REFRESH COOKIES  (acquires _COOKIE_LOCK)
# ══════════════════════════════════════════════════════════════════════════════
async def refresh_cookies_from_browser(
    reason: str = "On-demand refresh",
) -> Optional[str]:
    async with _COOKIE_LOCK:
        if (
            os.path.exists(COOKIE_FILE)
            and verify_cookies_file(COOKIE_FILE)
            and not is_cookie_file_expired(COOKIE_FILE)
        ):
            logger.info("✅ Instagram cookies already refreshed by another coroutine – reusing")
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok:
            logger.error("Instagram cookie generation failed.")
            return None
        if not os.path.exists(COOKIE_FILE):
            logger.error("Cookie file missing after generation.")
            return None
        if not verify_cookies_file(COOKIE_FILE) or is_cookie_file_expired(COOKIE_FILE):
            logger.warning("⚠️ Cookie verification failed – retrying ...")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
            ok2 = await generate_cookies_via_playwright(reason=f"{reason} (retry)")
            if not ok2 or not os.path.exists(COOKIE_FILE):
                return None
            if not verify_cookies_file(COOKIE_FILE):
                logger.error("❌ Cookie retry also failed verification")
                return None

        logger.info("✅ Instagram cookies verified successfully")
        ip_info   = await get_public_ip_info() or {}
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await send_to_log_group(
            text=(
                f"🌐 **Instagram Cookies Generated**\n\n"
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

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE VERIFICATION  (Netscape format)
# ══════════════════════════════════════════════════════════════════════════════
def verify_cookies_file(filename: str) -> bool:
    try:
        if not os.path.exists(filename):
            logger.error(f"Instagram cookies file does not exist: {filename}")
            return False
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        if "instagram.com" not in content:
            logger.error("No instagram.com domain found in cookies file")
            return False
        guest_cookies = ["mid", "ig_did", "csrftoken", "datr"]
        auth_cookies  = ["sessionid", "ds_user_id", "rur"]
        found_guest   = [c for c in guest_cookies if c in content]
        found_auth    = [c for c in auth_cookies  if c in content]
        found_all     = found_guest + found_auth
        if len(found_all) < 2:
            logger.warning(f"⚠️ Too few Instagram cookies: {found_all}")
            return False
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Instagram cookies file is JSON format, not Netscape")
            return False
        valid_lines = 0
        for line in content.strip().split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            if "\t" not in line:
                continue
            valid_lines += 1
        if valid_lines < 2:
            logger.error(f"Too few valid cookie lines: {valid_lines}")
            return False
        if found_auth:
            logger.info(
                f"✅ Instagram cookies verified (LOGGED-IN): "
                f"lines={valid_lines} | auth={found_auth}"
            )
        else:
            logger.warning(
                f"⚠️ Instagram cookies verified (GUEST ONLY – downloads may fail): "
                f"lines={valid_lines} | guest={found_guest}\n"
                f"   Set IG_USERNAME + IG_PASSWORD env vars for full access."
            )
        return True
    except Exception as e:
        logger.error(f"Error verifying Instagram cookies: {e}")
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
                if "instagram.com" not in parts[0]:
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
        logger.info("Instagram cookies have no expiry timestamp – treating as valid")
        return False
    now = int(time.time())
    if min_exp < now:
        logger.info(
            f"🕐 Instagram cookie expired at "
            f"{datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z"
        )
        return True
    remaining = min_exp - now
    logger.info(
        f"✅ Instagram cookie valid for {remaining // 3600}h {(remaining % 3600) // 60}m"
    )
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH / RATE-LIMIT ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def is_auth_error(exception: Exception) -> bool:
    error_str = str(exception).lower()
    auth_indicators = [
        "login required", "not logged in", "checkpoint required",
        "rate limit", "rate-limit", "rate_limit",
        "http error 401", "http error 403",
        "unable to extract", "cookie", "sign in",
        "authentication", "access denied", "forbidden",
        "bad credentials", "challenge required",
        "content is not available",
    ]
    return any(ind in error_str for ind in auth_indicators)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════
async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        if verify_cookies_file(COOKIE_FILE) and not is_cookie_file_expired(COOKIE_FILE):
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
        base["cookiesfrombrowser"] = ("chrome", IG_PROFILE_DIR)
        logger.debug("Falling back to cookiesfrombrowser (Chromium profile)")

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
    if not identifier:
        return None
    for fname in os.listdir(DOWNLOAD_DIR):
        if identifier in fname:
            fpath = os.path.join(DOWNLOAD_DIR, fname)
            if os.path.isfile(fpath):
                return fpath
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  CORE DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════
async def download_with_ytdlp(
    url: str,
    is_audio: bool = False,
) -> Optional[str]:
    shortcode = _extract_shortcode(url)
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
                        "🔄 Regenerating cookies ...\n\n"
                        "#InstagramCookies"
                    )
                )
                new_cookie = await refresh_cookies_from_browser(
                    reason="Auth/rate-limit detected during download"
                )
                if new_cookie:
                    logger.info("✅ Fresh cookies – retrying download ...")
                    ydl_opts = _build_opts(new_cookie)
                    continue
                else:
                    logger.error("Cookie regeneration failed – aborting")
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
    if not ENABLE_IG_COOKIES:
        logger.info("Instagram cookie handling disabled (ENABLE_IG_COOKIES=false).")
        return
    logger.info("🚀 Starting Instagram cookie services ...")
    cleanup_playwright_profile()
    need_refresh = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )
    if need_refresh:
        logger.info("🔄 No valid Instagram cookies – generating ...")
        cookie_file = await get_cookies(force_refresh=True)
        if cookie_file:
            logger.info(f"✅ Instagram cookies ready: {cookie_file}")
        else:
            logger.warning(
                "⚠️ Instagram cookie generation failed on startup.\n"
                "   Will retry automatically on first download request."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **Instagram Startup Cookie Generation Failed**\n\n"
                    "Will retry automatically on first download.\n\n"
                    "#InstagramCookies"
                )
            )
    else:
        logger.info("✅ Existing Instagram cookies are valid – skipping regeneration.")

# ══════════════════════════════════════════════════════════════════════════════
#  InstagramAPI CLASS
# ══════════════════════════════════════════════════════════════════════════════
class InstagramAPI:
    def __init__(self):
        self.regex    = INSTAGRAM_REGEX
        self.base_url = "https://www.instagram.com/"

    async def valid(self, link: str) -> bool:
        return bool(re.search(self.regex, link))

    async def info(self, url: str) -> Optional[dict]:
        raw          = await _fetch_info(url)
        shortcode    = _extract_shortcode(url) or ""
        duration_sec = 0
        title        = "Instagram Video"
        uploader     = "Unknown"
        thumbnail    = ""
        webpage_url  = url
        ext          = "mp4"
        vid_id       = shortcode
        if raw:
            duration_sec = raw.get("duration") or 0
            title        = raw.get("title") or raw.get("uploader") or title
            uploader     = raw.get("uploader") or uploader
            thumbnail    = raw.get("thumbnail") or ""
            webpage_url  = raw.get("webpage_url") or url
            ext          = raw.get("ext") or "mp4"
            vid_id       = raw.get("id") or shortcode
        return {
            "title":        title,
            "uploader":     uploader,
            "duration_sec": duration_sec,
            "duration_min": _seconds_to_min(duration_sec),
            "thumbnail":    thumbnail,
            "thumb":        thumbnail,
            "webpage_url":  webpage_url,
            "ext":          ext,
            "id":           vid_id,
        }

    async def download(self, url: str) -> tuple:
        filepath = await download_with_ytdlp(url, is_audio=False)
        if not filepath:
            return False, None
        meta = await self.info(url)
        return {
            "title":        meta["title"],
            "uploader":     meta["uploader"],
            "duration_sec": meta["duration_sec"],
            "duration_min": meta["duration_min"],
            "thumb":        meta["thumb"],
            "filepath":     filepath,
        }, filepath

    async def download_audio(self, url: str) -> tuple:
        filepath = await download_with_ytdlp(url, is_audio=True)
        if not filepath:
            return False, None
        meta = await self.info(url)
        return {
            "title":        meta["title"],
            "uploader":     meta["uploader"],
            "duration_sec": meta["duration_sec"],
            "duration_min": meta["duration_min"],
            "thumb":        meta["thumb"],
            "filepath":     filepath,
        }, filepath

    async def thumbnail(self, url: str) -> str:
        meta = await self.info(url)
        return meta["thumb"]

    async def track(self, url: str) -> tuple:
        meta = await self.info(url)
        return {
            "title":        meta["title"],
            "link":         meta["webpage_url"],
            "vidid":        meta["id"],
            "duration_min": meta["duration_min"],
            "thumb":        meta["thumb"],
        }, meta["id"]
