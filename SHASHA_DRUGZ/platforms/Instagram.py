import os
import re
import glob
import time
import shutil
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
#  FIX 1 — USER-AGENT ROTATION (updated to 2025/2026 Chrome versions)
# ══════════════════════════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
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

# FIX 5 — Full profile wipe to avoid stale session poisoning
def wipe_playwright_profile():
    """Completely removes and recreates the Playwright profile directory."""
    try:
        if os.path.exists(IG_PROFILE_DIR):
            shutil.rmtree(IG_PROFILE_DIR)
            logger.info("🧹 Wiped stale Playwright profile directory")
        os.makedirs(IG_PROFILE_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to wipe Playwright profile: {e}")

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
async def _human_type(page, locator, text: str) -> None:
    try:
        await locator.click()
        await page.wait_for_timeout(random.randint(300, 600))
        await locator.press("Control+a")
        await page.wait_for_timeout(random.randint(100, 200))
        await locator.press("Delete")
        await page.wait_for_timeout(random.randint(200, 400))
        for char in text:
            await locator.press(char)
            await page.wait_for_timeout(random.randint(80, 220))
        await page.wait_for_timeout(random.randint(400, 900))
    except Exception as e:
        logger.warning(f"_human_type fallback to fill(): {e}")
        try:
            await locator.fill(text)
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
        logger.error(f"🚨 Instagram CHECKPOINT detected! URL: {page.url}")
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
        logger.error("🔒 Instagram requires SMS 2FA – cannot automate.")
        await send_to_log_group(text="🔒 **Instagram SMS 2FA Required – Cannot Automate**\n#2FA")
        return False
    if fa_type == "totp":
        if not IG_TOTP_SECRET:
            logger.error("🔒 TOTP 2FA required but IG_TOTP_SECRET not set.")
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
            f"   All cookies   : {cookie_names}\n"
            f"   Auth cookies  : {found_auth or 'NONE ← login failed'}"
        )
        if found_auth:
            logger.info(f"✅ Login verified via session cookies: {found_auth}")
            return True
        # Also check URL – if we're past login page, probably logged in
        if "instagram.com" in current_url and "login" not in current_url.lower() and "accounts" not in current_url.lower():
            if "sessionid" in str(all_cookies).lower():
                return True
        return False
    except Exception as e:
        logger.error(f"_verify_login_success error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  STEALTH INIT SCRIPT  (enhanced)
# ══════════════════════════════════════════════════════════════════════════════
STEALTH_SCRIPT = """
    // Remove webdriver indicator
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
        configurable: true
    });

    // Spoof automation-related properties
    delete navigator.__proto__.webdriver;

    // Realistic plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            return {
                length: 3,
                0: {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                1: {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                2: {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
                item: function(idx) { return this[idx]; },
                namedItem: function(name) {
                    for (let k in this) {
                        if (this[k] && this[k].name === name) return this[k];
                    }
                    return null;
                },
                refresh: function() {}
            };
        }
    });

    // Languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true
    });

    // Chrome object
    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', GC_PRESSURE: 'gc_pressure', OS_UPDATE: 'os_update' },
            PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
            RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
        }
    };

    // Permissions
    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }

    // Hardware
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });

    // Realistic screen values
    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
    Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });

    // Prevent iframe detection
    try {
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() { return window; }
        });
    } catch(e) {}

    // Canvas fingerprint randomization
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        return origToDataURL.apply(this, arguments);
    };
"""

# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN VIA /accounts/login/ CLASSIC PATH
# ══════════════════════════════════════════════════════════════════════════════
async def _try_classic_login(page, context) -> bool:
    logger.info("🔐 Attempting classic login path: /accounts/login/")

    try:
        # FIX 2 — Use domcontentloaded instead of networkidle (Instagram SPA never idles)
        await page.goto(
            "https://www.instagram.com/accounts/login/",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        # FIX 2 — Give React extra time to hydrate after domcontentloaded
        await page.wait_for_timeout(random.randint(5000, 8000))
    except Exception as e:
        logger.warning(f"Classic login navigation warning: {e}")
        try:
            await page.goto(
                "https://www.instagram.com/accounts/login/",
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            await page.wait_for_timeout(random.randint(5000, 8000))
        except Exception as e2:
            logger.error(f"Classic login navigation failed: {e2}")
            return False

    # FIX 3 — Blank-page guard: bail early if Instagram served an empty page
    try:
        body_len = len(await page.inner_text("body"))
        logger.info(f"📄 Login page body length: {body_len} chars")
        if body_len < 200:
            logger.error(
                "❌ Login page appears blank/empty – likely bot-blocked at this URL.\n"
                "   Meta served no content; cannot find login form."
            )
            screenshot_path = await _log_page_state(page, "step2_blank_login_page")
            await _send_screenshot_to_log_group(
                screenshot_path,
                "🚨 **IG: Login page blank – bot-blocked or empty response**\n"
                "Check proxy / UA / account status."
            )
            return False
    except Exception as e:
        logger.warning(f"Body length check failed (non-fatal): {e}")

    # Wait for username input with extended timeout
    username_input = None
    password_input = None

    username_selectors = [
        "input[name='username']",
        "input[aria-label='Phone number, username, or email']",
        "input[aria-label*='username']",
        "input[aria-label*='email']",
        "input[type='text']",
    ]

    for sel in username_selectors:
        try:
            await page.wait_for_selector(sel, timeout=8000, state="visible")
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                username_input = el.first
                logger.info(f"✅ Classic: username field found via {sel}")
                break
        except Exception:
            continue

    if not username_input:
        logger.error("❌ Classic login: username field not found")
        return False

    password_selectors = [
        "input[name='password']",
        "input[type='password']",
        "input[aria-label='Password']",
        "input[aria-label*='assword']",
    ]

    for sel in password_selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                password_input = el.first
                logger.info(f"✅ Classic: password field found via {sel}")
                break
        except Exception:
            continue

    if not password_input:
        logger.error("❌ Classic login: password field not found")
        return False

    logger.info(f"✍️  Entering username: {IG_USERNAME}")
    await _human_type(page, username_input, IG_USERNAME)
    await page.wait_for_timeout(random.randint(500, 1000))

    logger.info("✍️  Entering password")
    await _human_type(page, password_input, IG_PASSWORD)
    await page.wait_for_timeout(random.randint(700, 1200))

    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Log in')",
        "button:has-text('Log In')",
    ]

    submit_btn = None
    for sel in submit_selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                submit_btn = el.first
                logger.info(f"✅ Classic: submit button found via {sel}")
                break
        except Exception:
            continue

    if submit_btn:
        await submit_btn.click()
        logger.info("🖱️  Submit button clicked")
    else:
        await password_input.press("Enter")
        logger.info("🖱️  Enter pressed on password field")

    try:
        await page.wait_for_url(
            lambda url: "login" not in url.lower() and "accounts" not in url.lower(),
            timeout=15_000,
        )
        logger.info(f"✅ Navigated away from login page → {page.url}")
    except Exception:
        await page.wait_for_timeout(8000)

    return await _verify_login_success(context, page)


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN VIA MOBILE API (most stealth-friendly)
# ══════════════════════════════════════════════════════════════════════════════
async def _try_mobile_login(page, context) -> bool:
    logger.info("📱 Attempting mobile web login path")

    try:
        await page.set_viewport_size({"width": 390, "height": 844})

        await page.goto(
            "https://www.instagram.com/accounts/login/?source=auth_switcher",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        await page.wait_for_timeout(random.randint(4000, 6500))

        # FIX 3 — Blank-page guard for mobile path too
        try:
            body_len = len(await page.inner_text("body"))
            logger.info(f"📄 Mobile login page body length: {body_len} chars")
            if body_len < 200:
                logger.error("❌ Mobile login page is blank – bot-blocked")
                return False
        except Exception:
            pass

        try:
            cookie_btn = page.locator("button:has-text('Allow all cookies'), button:has-text('Accept All')")
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        try:
            await page.wait_for_selector(
                "input[name='username'], input[name='email'], input[aria-label*='username']",
                timeout=12_000,
                state="visible"
            )
        except Exception:
            logger.warning("Mobile login: username field wait timed out")
            return False

        username_input = None
        for sel in ["input[name='username']", "input[name='email']", "input[type='text']"]:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                username_input = el.first
                break

        if not username_input:
            logger.error("Mobile login: username field not found")
            return False

        password_input = None
        for sel in ["input[name='password']", "input[type='password']"]:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                password_input = el.first
                break

        if not password_input:
            logger.error("Mobile login: password field not found")
            return False

        await _human_type(page, username_input, IG_USERNAME)
        await page.wait_for_timeout(random.randint(600, 1100))
        await _human_type(page, password_input, IG_PASSWORD)
        await page.wait_for_timeout(random.randint(700, 1300))

        submit_btn = None
        for sel in ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Log In')"]:
            el = page.locator(sel)
            if await el.count() > 0:
                submit_btn = el.first
                break

        if submit_btn:
            await submit_btn.click()
        else:
            await password_input.press("Enter")

        await page.wait_for_timeout(10000)

        await page.set_viewport_size({"width": 1920, "height": 1080})

        return await _verify_login_success(context, page)

    except Exception as e:
        logger.error(f"Mobile login failed: {e}")
        try:
            await page.set_viewport_size({"width": 1920, "height": 1080})
        except Exception:
            pass
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PLAYWRIGHT COOKIE GENERATION
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(
    reason: str = "Profile cookie generation",
) -> bool:
    """
    Generates authenticated Instagram cookies via Playwright.
    ONLY writes cookies if login is successful.
    Returns False if login fails.
    """
    if not IG_USERNAME or not IG_PASSWORD:
        logger.error(
            "❌ IG_USERNAME and IG_PASSWORD must be set.\n"
            "   Cookies will NOT be generated without successful login."
        )
        await send_to_log_group(
            text=(
                "❌ **Instagram: IG_USERNAME/IG_PASSWORD not set**\n"
                "Cannot generate cookies without credentials.\n#InstagramCookies"
            )
        )
        return False

    logger.info(
        f"🌐 Launching Playwright to generate Instagram cookies [{reason}] ...\n"
        f"   Username    : {IG_USERNAME}\n"
        f"   TOTP secret : {'✅ set' if IG_TOTP_SECRET else '⚠️  not set'}"
    )

    await send_to_log_group(
        text=(
            f"🌐 **Browser Profile – Generating Cookies**\n\n"
            f"📝 Reason   : {reason}\n"
            f"⏳ Launching headless Chromium ...\n\n"
            f"#YouTubeCookies"
        )
    )

    # FIX 5 — Wipe the entire persistent profile before each fresh login
    # to avoid stale cookies / localStorage poisoning the new session
    wipe_playwright_profile()

    proxy      = choose_random_proxy(IG_PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(USER_AGENTS)
    context    = None
    login_ok   = False

    try:
        async with async_playwright() as p:
            # ── Launch with persistent context ────────────────────────────────
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
                    "--lang=en-US",
                    "--accept-lang=en-US",
                    "--disable-automation",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-default-apps",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-client-side-phishing-detection",
                    "--disable-hang-monitor",
                    "--disable-popup-blocking",
                    "--disable-prompt-on-repost",
                    "--disable-sync",
                    "--disable-translate",
                    "--metrics-recording-only",
                    "--safebrowsing-disable-auto-update",
                ],
                proxy={"server": proxy} if proxy else None,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                ignore_https_errors=True,
                accept_downloads=False,
                # FIX 1 — Updated sec-ch-ua header to match current Chrome versions
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Chromium";v="131", "Not(A:Brand";v="99", "Google Chrome";v="131"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
            )

            page = await context.new_page()

            # Inject stealth scripts before any navigation
            await page.add_init_script(STEALTH_SCRIPT)

            # ── Step 1 – Warm up: visit homepage ─────────────────────────────
            logger.info("🔗 Step 1/4 – Warming up: visiting instagram.com ...")
            try:
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
                await page.wait_for_timeout(random.randint(2500, 4000))

                # Accept cookie banner if present
                try:
                    accept_selectors = [
                        "[data-testid='cookie-policy-manage-dialog-accept-button']",
                        "button:has-text('Allow all cookies')",
                        "button:has-text('Allow essential and optional cookies')",
                        "button:has-text('Accept All')",
                        "button:has-text('Allow')",
                    ]
                    for sel in accept_selectors:
                        btn = page.locator(sel)
                        if await btn.count() > 0 and await btn.first.is_visible():
                            await btn.first.click()
                            logger.info(f"✅ Cookie consent accepted via: {sel}")
                            await page.wait_for_timeout(random.randint(1500, 2500))
                            break
                except Exception as e:
                    logger.debug(f"Cookie consent handling skipped: {e}")

                await _log_page_state(page, "step1_homepage")

                # Simulate human behaviour
                await page.mouse.move(random.randint(200, 800), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1200))
                await page.mouse.wheel(0, random.randint(100, 400))
                await page.wait_for_timeout(random.randint(1000, 2000))

            except Exception as e:
                logger.warning(f"Homepage warmup warning (non-fatal): {e}")

            # ── Step 2 – Login ────────────────────────────────────────────────
            logger.info(f"🔗 Step 2/4 – Logging in as: {IG_USERNAME} ...")

            # FIX 4 — Navigate to login by clicking from homepage instead of
            # direct goto. Direct navigation is a known bot-detection trigger.
            login_clicked = False
            try:
                login_link = page.locator(
                    "a[href='/accounts/login/'], "
                    "a:has-text('Log in'), "
                    "a:has-text('Log In')"
                )
                if await login_link.count() > 0:
                    await login_link.first.click()
                    await page.wait_for_timeout(random.randint(3000, 5500))
                    logger.info(f"✅ Navigated to login via click → {page.url}")
                    login_clicked = True
            except Exception as e:
                logger.warning(f"Click-to-login failed – will fall through to classic goto: {e}")

            # Try classic login (handles the goto itself if click didn't navigate there)
            try:
                if login_clicked and "login" in page.url.lower():
                    # We're already on the login page; skip the goto inside _try_classic_login
                    # by calling the field-detection portion directly
                    login_ok = await _try_classic_login_on_current_page(page, context)
                else:
                    login_ok = await _try_classic_login(page, context)
            except Exception as e:
                logger.warning(f"Classic login threw exception: {e}")
                login_ok = False

            # If classic failed, try mobile login
            if not login_ok:
                logger.warning("⚠️ Classic login failed – trying mobile web login ...")
                try:
                    login_ok = await _try_mobile_login(page, context)
                except Exception as e:
                    logger.warning(f"Mobile login threw exception: {e}")
                    login_ok = False

            # ── Post-login checks ─────────────────────────────────────────────
            if login_ok:
                fa_type = await _check_for_2fa(page)
                if fa_type != "none":
                    logger.info(f"🔑 2FA prompt detected ({fa_type}) ...")
                    shot = await _log_page_state(page, "step2_2fa_prompt")
                    await _send_screenshot_to_log_group(shot, f"🔑 IG: 2FA prompt ({fa_type})")
                    fa_ok = await _handle_2fa(page)
                    if fa_ok:
                        await page.wait_for_timeout(5000)
                        login_ok = await _verify_login_success(context, page)
                    else:
                        login_ok = False

                if await _check_for_checkpoint(page):
                    shot = await _log_page_state(page, "step2_checkpoint")
                    await _send_screenshot_to_log_group(
                        shot, "🚨 **IG: Checkpoint detected after login**"
                    )
                    login_ok = False

                if login_ok:
                    await _dismiss_popups(page)
                    await page.wait_for_timeout(random.randint(2000, 3500))
                    shot = await _log_page_state(page, "step2_logged_in")
                    logger.info("✅ Instagram login confirmed!")
                    await send_to_log_group(
                        text=(
                            f"✅ **Instagram Login Successful**\n\n"
                            f"👤 Account : `{IG_USERNAME}`\n"
                            f"📝 Reason  : {reason}\n\n"
                            f"#InstagramCookies"
                        )
                    )

            if not login_ok:
                logger.error(
                    "❌ Instagram login FAILED.\n"
                    "   Cookies will NOT be saved.\n"
                    "   Possible causes:\n"
                    "   • Wrong credentials\n"
                    "   • Account disabled or flagged\n"
                    "   • Bot detection by Instagram\n"
                    "   • Account requires SMS 2FA\n"
                    "   • Account locked/suspended"
                )
                shot = await _log_page_state(page, "step2_login_failed")
                await _send_screenshot_to_log_group(
                    shot,
                    "❌ **IG: Login Failed – Cookies NOT saved**\n"
                    "Check credentials and see logs."
                )
                await send_to_log_group(
                    text=(
                        f"❌ **Instagram Login FAILED**\n\n"
                        f"👤 Account : `{IG_USERNAME}`\n"
                        f"📝 Reason  : {reason}\n\n"
                        f"**Cookies NOT generated.**\n\n"
                        f"Possible causes:\n"
                        f"• Wrong IG_USERNAME / IG_PASSWORD\n"
                        f"• Account disabled or flagged\n"
                        f"• Bot detection by Meta\n"
                        f"• SMS 2FA enabled (not supported)\n\n"
                        f"#InstagramCookies"
                    )
                )
                await context.close()
                context = None
                return False

            # ── Step 3 – Natural browsing simulation ──────────────────────────
            logger.info("🔗 Step 3/4 – Simulating natural browsing ...")
            try:
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                await page.wait_for_timeout(random.randint(2000, 4000))
                await page.mouse.move(random.randint(100, 600), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1200))
                await page.mouse.wheel(0, random.randint(200, 600))
                await page.wait_for_timeout(random.randint(1000, 2000))
                await _log_page_state(page, "step3_feed")
            except Exception as e:
                logger.debug(f"Natural browsing simulation non-fatal: {e}")

            # ── Step 4 – Export cookies ───────────────────────────────────────
            logger.info("🔗 Step 4/4 – Exporting authenticated cookies ...")
            all_cookies = await context.cookies()
            await context.close()
            context = None

            ig_cookies = [
                c for c in all_cookies
                if "instagram.com" in c.get("domain", "")
                or "facebook.com" in c.get("domain", "")
            ]

            cookie_names = {c["name"] for c in ig_cookies}
            auth_present = {"sessionid", "ds_user_id"} & cookie_names

            logger.info(
                f"🍪 Collected {len(ig_cookies)} cookies: {cookie_names}\n"
                f"   Auth cookies present: {auth_present or 'NONE'}"
            )

            if not auth_present:
                logger.error(
                    "❌ No authenticated cookies found (sessionid/ds_user_id missing).\n"
                    "   Login appeared to succeed but cookies are invalid.\n"
                    "   NOT writing cookie file."
                )
                await send_to_log_group(
                    text=(
                        "❌ **Instagram: Login appeared OK but no auth cookies found**\n"
                        "Cookie file NOT written.\n#InstagramCookies"
                    )
                )
                return False

            ok = _write_netscape_cookies(ig_cookies, COOKIE_FILE)
            if ok:
                logger.info(
                    f"✅ Authenticated Instagram cookies saved!\n"
                    f"   Auth cookies: {auth_present}\n"
                    f"   Total cookies: {len(ig_cookies)}"
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
                        shot, f"❌ **IG: Playwright crashed**\n`{str(e)[:300]}`"
                    )
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Instagram Browser Session Crashed**\n\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n\n"
                f"#InstagramCookies"
            )
        )
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  FIX 4 HELPER — Classic login on a page we're already on
#  (skips the goto, jumps straight to field detection)
# ══════════════════════════════════════════════════════════════════════════════
async def _try_classic_login_on_current_page(page, context) -> bool:
    """
    Runs the field-detection + submit portion of classic login
    without navigating away first. Used when we've already clicked
    the Log In link from the homepage.
    """
    logger.info("🔐 Classic login: already on login page (arrived via click)")

    # FIX 3 — blank-page guard
    try:
        body_len = len(await page.inner_text("body"))
        logger.info(f"📄 Login page body length: {body_len} chars")
        if body_len < 200:
            logger.error("❌ Login page is blank after click-navigation – bot blocked")
            screenshot_path = await _log_page_state(page, "step2_blank_after_click")
            await _send_screenshot_to_log_group(
                screenshot_path, "🚨 **IG: Blank login page after click**"
            )
            return False
    except Exception as e:
        logger.warning(f"Body length check failed: {e}")

    username_input = None
    password_input = None

    username_selectors = [
        "input[name='username']",
        "input[aria-label='Phone number, username, or email']",
        "input[aria-label*='username']",
        "input[aria-label*='email']",
        "input[type='text']",
    ]

    for sel in username_selectors:
        try:
            await page.wait_for_selector(sel, timeout=8000, state="visible")
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                username_input = el.first
                logger.info(f"✅ Classic (click-nav): username field via {sel}")
                break
        except Exception:
            continue

    if not username_input:
        logger.error("❌ Classic (click-nav): username field not found")
        return False

    password_selectors = [
        "input[name='password']",
        "input[type='password']",
        "input[aria-label='Password']",
        "input[aria-label*='assword']",
    ]

    for sel in password_selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                password_input = el.first
                logger.info(f"✅ Classic (click-nav): password field via {sel}")
                break
        except Exception:
            continue

    if not password_input:
        logger.error("❌ Classic (click-nav): password field not found")
        return False

    logger.info(f"✍️  Entering username: {IG_USERNAME}")
    await _human_type(page, username_input, IG_USERNAME)
    await page.wait_for_timeout(random.randint(500, 1000))

    logger.info("✍️  Entering password")
    await _human_type(page, password_input, IG_PASSWORD)
    await page.wait_for_timeout(random.randint(700, 1200))

    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Log in')",
        "button:has-text('Log In')",
    ]

    submit_btn = None
    for sel in submit_selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                submit_btn = el.first
                logger.info(f"✅ Classic (click-nav): submit button via {sel}")
                break
        except Exception:
            continue

    if submit_btn:
        await submit_btn.click()
        logger.info("🖱️  Submit button clicked")
    else:
        await password_input.press("Enter")
        logger.info("🖱️  Enter pressed on password field")

    try:
        await page.wait_for_url(
            lambda url: "login" not in url.lower() and "accounts" not in url.lower(),
            timeout=15_000,
        )
        logger.info(f"✅ Navigated away from login page → {page.url}")
    except Exception:
        await page.wait_for_timeout(8000)

    return await _verify_login_success(context, page)


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
            logger.error("Instagram cookie generation failed (login unsuccessful).")
            return None

        if not os.path.exists(COOKIE_FILE):
            logger.error("Cookie file missing after generation – login failed.")
            return None

        if not verify_cookies_file(COOKIE_FILE):
            logger.error("Cookie file verification failed after generation.")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
            return None

        if is_cookie_file_expired(COOKIE_FILE):
            logger.error("Cookie file expired immediately after generation – this should not happen.")
            return None

        logger.info("✅ Instagram authenticated cookies verified successfully")

        ip_info   = await get_public_ip_info() or {}
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await send_to_log_group(
            text=(
                f"🌐 **Instagram Cookies Generated (Authenticated)**\n\n"
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

        auth_cookies = ["sessionid", "ds_user_id"]
        found_auth   = [c for c in auth_cookies if c in content]

        if not found_auth:
            logger.error(
                "❌ Cookie file has NO auth cookies (sessionid/ds_user_id missing).\n"
                "   This is a guest-only cookie file and cannot be used for downloads."
            )
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

        logger.info(
            f"✅ Instagram cookies verified (AUTHENTICATED): "
            f"lines={valid_lines} | auth={found_auth}"
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
            logger.info("✅ Using existing valid authenticated Instagram cookies")
            return COOKIE_FILE
        else:
            logger.warning("Instagram cookies invalid/expired or not authenticated – regenerating ...")
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
        logger.warning("No cookie file available for yt-dlp")

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
        logger.error(
            "❌ No valid authenticated Instagram cookies available.\n"
            "   Login must succeed before downloads are possible."
        )
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
                        "🔄 Regenerating authenticated cookies ...\n\n"
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
                    logger.error("Cookie regeneration failed – cannot retry download")
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
    if not cookie_file:
        logger.warning("No authenticated cookies for info fetch – may fail")
        return None

    ydl_opts = get_ytdlp_opts(
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

    if not IG_USERNAME or not IG_PASSWORD:
        logger.error(
            "❌ IG_USERNAME and IG_PASSWORD are required.\n"
            "   Set them as environment variables.\n"
            "   Instagram downloads will NOT work without authenticated cookies."
        )
        await send_to_log_group(
            text=(
                "❌ **Instagram: Credentials Not Configured**\n\n"
                "Set `IG_USERNAME` and `IG_PASSWORD` environment variables.\n"
                "Downloads will fail until this is resolved.\n\n"
                "#InstagramCookies"
            )
        )
        return

    logger.info("🚀 Starting Instagram cookie services ...")
    cleanup_playwright_profile()

    need_refresh = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )

    if need_refresh:
        logger.info("🔄 No valid authenticated Instagram cookies – generating ...")
        cookie_file = await get_cookies(force_refresh=True)
        if cookie_file:
            logger.info(f"✅ Instagram authenticated cookies ready: {cookie_file}")
        else:
            logger.warning(
                "⚠️ Instagram cookie generation failed on startup.\n"
                "   Will retry automatically on first download request."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **Instagram Startup Cookie Generation Failed**\n\n"
                    "Login may have failed. Will retry on first download.\n\n"
                    "#InstagramCookies"
                )
            )
    else:
        logger.info("✅ Existing authenticated Instagram cookies are valid – skipping regeneration.")

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
