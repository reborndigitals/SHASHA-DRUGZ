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

IG_USERNAME    = os.getenv("IG_USERNAME", "onixxghostt")
IG_PASSWORD    = os.getenv("IG_PASSWORD", "143@Frnds")
# Optional: base-32 TOTP secret for accounts with authenticator-app 2FA.
# Generate with: import pyotp; pyotp.random_base32()
# Leave empty if the account has no 2FA or uses SMS (SMS 2FA cannot be
# automated headlessly — the bot will pause and warn you).
IG_TOTP_SECRET = os.getenv("IG_TOTP_SECRET", "")

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


async def _send_screenshot_to_log_group(screenshot_path: str, caption: str):
    """Send a debug screenshot to the log group (best-effort)."""
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
#  PLAYWRIGHT LOGIN HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _log_page_state(page, label: str) -> str:
    """
    Log the current URL + title, capture a timestamped screenshot,
    and return the screenshot path (or empty string on failure).
    Always call this before returning from a login stage.
    """
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


async def _dismiss_popups(page) -> None:
    """
    Dismiss common post-login Instagram interstitials:
      - "Save your login info?" dialog
      - "Turn on notifications?" dialog
      - Cookie consent banners
    These block navigation and must be dismissed before cookies settle.
    """
    # Ordered list of (description, selector)
    dismiss_targets = [
        ("cookie consent",    "button:has-text('Allow all cookies'), button:has-text('Allow essential and optional cookies')"),
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


async def _check_for_checkpoint(page) -> bool:
    """
    Return True if Instagram has redirected to a checkpoint / challenge page.
    These are Meta's suspicious-activity walls that require human verification.
    """
    checkpoint_signals = [
        "challenge",
        "checkpoint",
        "accounts/suspended",
        "unusualactivity",
        "verification",
    ]
    current_url = page.url.lower()
    if any(sig in current_url for sig in checkpoint_signals):
        logger.error(
            f"🚨 Instagram CHECKPOINT detected!\n"
            f"   URL: {page.url}\n"
            f"   This account has been flagged by Meta. "
            "You must resolve the challenge manually in a real browser "
            "before this bot can obtain a valid session cookie.\n"
            "   Possible causes:\n"
            "     • Logging in from a new IP too quickly\n"
            "     • Headless browser fingerprint detected by Meta\n"
            "     • Account has been locked / flagged for suspicious activity\n"
            "   Resolution:\n"
            "     1. Open https://www.instagram.com in a real browser\n"
            "     2. Log in as the bot account and complete the challenge\n"
            "     3. Export cookies manually and place them at:\n"
            f"       {COOKIE_FILE}\n"
            "     4. Restart the bot"
        )
        return True

    # Text-based check in case URL hasn't changed yet
    try:
        body_text = (await page.inner_text("body")).lower()
        text_signals = [
            "verify your account",
            "verify it's you",
            "we detected an unusual",
            "suspicious activity",
            "this account has been",
            "complete a security check",
        ]
        if any(sig in body_text for sig in text_signals):
            logger.error(
                f"🚨 Instagram CHECKPOINT detected via page text!\n"
                f"   URL: {page.url}"
            )
            return True
    except Exception:
        pass

    return False


async def _check_for_2fa(page) -> str:
    """
    Detect whether Instagram is showing a 2FA prompt and return the type:
      'totp'   – authenticator app (6-digit code)
      'sms'    – SMS code
      'none'   – no 2FA detected
    """
    try:
        current_url = page.url.lower()
        # Instagram redirects to /accounts/login/two_factor/ for 2FA
        if "two_factor" in current_url or "2fa" in current_url:
            body_text = (await page.inner_text("body")).lower()
            if "text message" in body_text or "sms" in body_text:
                return "sms"
            return "totp"

        # Fallback: look for the 2FA code input field
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
    """
    Attempt to handle 2FA automatically.
      - TOTP: fills the code using pyotp if IG_TOTP_SECRET is set.
      - SMS:  cannot be automated; logs a clear error with instructions.
    Returns True if 2FA was successfully submitted, False otherwise.
    """
    fa_type = await _check_for_2fa(page)

    if fa_type == "none":
        return True  # No 2FA needed

    if fa_type == "sms":
        logger.error(
            "🔒 Instagram requires SMS 2FA verification.\n"
            "   SMS 2FA cannot be automated in a headless browser.\n"
            "   Options:\n"
            "     • Disable SMS 2FA on this account and use an authenticator app instead\n"
            "     • Set IG_TOTP_SECRET env var with your TOTP secret\n"
            "     • Log in manually, export cookies, and place at:\n"
            f"       {COOKIE_FILE}"
        )
        await send_to_log_group(
            text=(
                "🔒 **Instagram SMS 2FA Required – Cannot Automate**\n\n"
                "SMS 2FA cannot be completed headlessly.\n"
                "Please disable SMS 2FA or switch to an authenticator app,\n"
                "then set `IG_TOTP_SECRET` in your environment.\n\n"
                "#InstagramCookies #2FA"
            )
        )
        return False

    if fa_type == "totp":
        if not IG_TOTP_SECRET:
            logger.error(
                "🔒 Instagram requires TOTP (authenticator app) 2FA.\n"
                "   The account has 2FA enabled but IG_TOTP_SECRET is not set.\n"
                "   To automate TOTP:\n"
                "     1. Open your authenticator app\n"
                "     2. Find the secret/seed key for your Instagram account\n"
                "     3. Set it as: IG_TOTP_SECRET=<base32-secret>\n"
                "   Alternatively, disable 2FA on this account."
            )
            await send_to_log_group(
                text=(
                    "🔒 **Instagram TOTP 2FA Required – IG_TOTP_SECRET Not Set**\n\n"
                    "Set `IG_TOTP_SECRET` env var with the base32 TOTP secret "
                    "from your authenticator app.\n\n"
                    "#InstagramCookies #2FA"
                )
            )
            return False

        try:
            import pyotp
        except ImportError:
            logger.error(
                "🔒 pyotp is not installed. Install with: pip install pyotp\n"
                "   pyotp is required to auto-fill TOTP 2FA codes."
            )
            return False

        try:
            totp  = pyotp.TOTP(IG_TOTP_SECRET)
            code  = totp.now()
            logger.info(f"🔑 Generated TOTP code for Instagram 2FA: {code}")

            code_input = page.locator(
                "input[name='verificationCode'], "
                "input[aria-label*='Security Code'], "
                "input[aria-label*='Confirmation Code'], "
                "input[placeholder*='6-digit code'], "
                "input[placeholder*='security code']"
            )
            if await code_input.count() == 0:
                logger.error("❌ Could not find TOTP input field on page")
                return False

            await code_input.first.fill(code)
            await page.wait_for_timeout(random.randint(600, 1000))

            # Try to submit the form
            submit_btn = page.locator(
                "button[type='submit'], "
                "button:has-text('Confirm'), "
                "button:has-text('Submit')"
            )
            if await submit_btn.count() > 0:
                await submit_btn.first.click()
                logger.info("✅ TOTP code submitted – waiting for session ...")
                await page.wait_for_timeout(5000)
                return True
            else:
                # Some IG variants use Enter to submit
                await code_input.first.press("Enter")
                await page.wait_for_timeout(5000)
                return True

        except Exception as e:
            logger.error(f"TOTP 2FA handling error: {e}")
            return False

    return False


async def _verify_login_success(context, page) -> bool:
    """
    After login flow, verify that a real sessionid cookie was issued.
    This is more reliable than DOM selectors which change frequently.
    Also checks for auth_cookies in the live browser context.
    """
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

        # Extra DOM check as secondary signal (not authoritative)
        try:
            home_indicators = [
                "svg[aria-label='Home']",
                "a[href='/']",
                "nav",
                "div[role='main']",
            ]
            for sel in home_indicators:
                if await page.locator(sel).count() > 0:
                    logger.warning(
                        "⚠️ DOM suggests home page but NO session cookie found. "
                        "Instagram may have issued only guest cookies."
                    )
                    break
        except Exception:
            pass

        return False

    except Exception as e:
        logger.error(f"_verify_login_success error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  BROWSER PROFILE COOKIE GENERATION  (Playwright)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(
    reason: str = "Profile cookie generation",
) -> bool:
    logger.info(
        f"🌐 Launching Playwright to generate Instagram cookies [{reason}] ...\n"
        f"   Credentials: {'✅ IG_USERNAME + IG_PASSWORD set' if IG_USERNAME and IG_PASSWORD else '❌ NOT SET – will collect guest cookies only'}\n"
        f"   TOTP secret : {'✅ IG_TOTP_SECRET set' if IG_TOTP_SECRET else '⚠️  not set (needed only if account has TOTP 2FA)'}"
    )
    await send_to_log_group(
        text=(
            f"🌐 **Instagram Browser Profile – Generating Cookies**\n\n"
            f"📝 Reason      : {reason}\n"
            f"🔐 Credentials : {'Set ✅' if IG_USERNAME and IG_PASSWORD else 'NOT SET ❌ – guest cookies only'}\n"
            f"🔑 TOTP secret : {'Set ✅' if IG_TOTP_SECRET else 'Not set'}\n"
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

            # Stealth: mask automation signals
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)

            # ── 1. Visit homepage ─────────────────────────────────────────────
            logger.info("🔗 Step 1/5 – Visiting instagram.com ...")
            try:
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                await page.wait_for_timeout(random.randint(3000, 5000))
                await _log_page_state(page, "step1_homepage")
            except Exception as e:
                logger.warning(f"⚠️  Homepage navigation warning (non-fatal): {e}")
                shot = await _log_page_state(page, "step1_homepage_error")
                await _send_screenshot_to_log_group(
                    shot, f"⚠️ IG: Homepage navigation error\n`{str(e)[:200]}`"
                )

            # ── 2. Accept cookie banner ───────────────────────────────────────
            logger.info("🔗 Step 2/5 – Accepting cookie consent banner (if present) ...")
            try:
                accept_btn = page.locator(
                    "button:has-text('Allow all cookies'), "
                    "button:has-text('Allow essential and optional cookies'), "
                    "button:has-text('Allow'), "
                    "button:has-text('Accept')"
                )
                if await accept_btn.count() > 0:
                    await accept_btn.first.click()
                    await page.wait_for_timeout(random.randint(1500, 2500))
                    logger.info("✅ Cookie consent banner accepted")
                else:
                    logger.info("ℹ️  No cookie consent banner detected")
            except Exception as e:
                logger.debug(f"Cookie consent handling skipped: {e}")

            # ── 3. Login flow ─────────────────────────────────────────────────
            if IG_USERNAME and IG_PASSWORD:
                logger.info(f"🔗 Step 3/5 – Logging in as: {IG_USERNAME} ...")
                try:
                    await page.goto(
                        "https://www.instagram.com/accounts/login/",
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    await page.wait_for_timeout(random.randint(2500, 4000))
                    shot = await _log_page_state(page, "step3_login_page")

                    # Pre-login checkpoint check (account may already be flagged)
                    if await _check_for_checkpoint(page):
                        shot = await _log_page_state(page, "step3_checkpoint_prelogin")
                        await _send_screenshot_to_log_group(
                            shot,
                            "🚨 **IG: Checkpoint BEFORE login attempt**\n"
                            "Account may be suspended or flagged. See logs."
                        )
                        # Don't abort — collect whatever guest cookies we have
                    else:
                        # Fill username
                        username_input = page.locator("input[name='username']")
                        if await username_input.count() > 0:
                            await username_input.fill(IG_USERNAME)
                            logger.info(f"✍️  Username entered: {IG_USERNAME}")
                            await page.wait_for_timeout(random.randint(700, 1400))
                        else:
                            logger.error(
                                "❌ Username input field NOT FOUND.\n"
                                "   Instagram may have changed its login page structure, "
                                "or the page failed to load properly."
                            )
                            shot = await _log_page_state(page, "step3_no_username_field")
                            await _send_screenshot_to_log_group(
                                shot, "❌ IG: Username input field not found"
                            )

                        # Fill password
                        password_input = page.locator("input[name='password']")
                        if await password_input.count() > 0:
                            await password_input.fill(IG_PASSWORD)
                            logger.info("✍️  Password entered (hidden)")
                            await page.wait_for_timeout(random.randint(700, 1400))
                        else:
                            logger.error(
                                "❌ Password input field NOT FOUND.\n"
                                "   The username field may have been found but the "
                                "page did not advance to the password step. "
                                "Check the screenshot for the current state."
                            )
                            shot = await _log_page_state(page, "step3_no_password_field")
                            await _send_screenshot_to_log_group(
                                shot, "❌ IG: Password input field not found"
                            )

                        # Submit login form
                        login_btn = page.locator("button[type='submit']")
                        if await login_btn.count() > 0:
                            await login_btn.click()
                            logger.info("🖱️  Login button clicked – awaiting response ...")
                            await page.wait_for_timeout(random.randint(5000, 8000))
                        else:
                            logger.error(
                                "❌ Login submit button NOT FOUND.\n"
                                "   Could not submit login form."
                            )
                            shot = await _log_page_state(page, "step3_no_submit_btn")
                            await _send_screenshot_to_log_group(
                                shot, "❌ IG: Login submit button not found"
                            )

                        shot = await _log_page_state(page, "step3_post_submit")

                        # ── 3a. Checkpoint check ──────────────────────────────
                        if await _check_for_checkpoint(page):
                            shot = await _log_page_state(page, "step3_checkpoint_postlogin")
                            await _send_screenshot_to_log_group(
                                shot,
                                "🚨 **IG: Checkpoint after login submit**\n"
                                "Meta is blocking automated login. See logs for resolution steps."
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
                            # Fall through – collect guest cookies at minimum

                        # ── 3b. 2FA check ─────────────────────────────────────
                        elif await _check_for_2fa(page) != "none":
                            logger.info("🔑 2FA prompt detected – attempting to handle ...")
                            shot = await _log_page_state(page, "step3_2fa_prompt")
                            await _send_screenshot_to_log_group(
                                shot, "🔑 IG: 2FA prompt detected"
                            )
                            fa_ok = await _handle_2fa(page)
                            if fa_ok:
                                await page.wait_for_timeout(random.randint(4000, 6000))
                                await _dismiss_popups(page)
                                shot = await _log_page_state(page, "step3_post_2fa")
                                login_ok = await _verify_login_success(context, page)
                            else:
                                logger.error("❌ 2FA handling failed – cannot obtain authenticated cookies")
                                shot = await _log_page_state(page, "step3_2fa_failed")
                                await _send_screenshot_to_log_group(
                                    shot, "❌ IG: 2FA handling failed"
                                )

                        else:
                            # ── 3c. Normal login – dismiss popups + verify ────
                            await _dismiss_popups(page)
                            shot = await _log_page_state(page, "step3_post_popups")
                            login_ok = await _verify_login_success(context, page)

                            if login_ok:
                                logger.info("✅ Instagram login confirmed via session cookie!")
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
                                    "   Possible reasons:\n"
                                    "     • Wrong IG_USERNAME / IG_PASSWORD\n"
                                    "     • Instagram displayed an error (wrong password, "
                                    "account disabled, etc.)\n"
                                    "     • Meta detected the headless browser and silently "
                                    "rejected the login without a checkpoint page\n"
                                    "   Check the screenshot sent to the log group for the "
                                    "current page state."
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
                                        f"The bot will collect guest cookies only.\n\n"
                                        f"#InstagramCookies"
                                    )
                                )

                except Exception as e:
                    logger.error(
                        f"❌ Unhandled exception during Instagram login flow:\n"
                        f"   {type(e).__name__}: {str(e)[:400]}"
                    )
                    shot = await _log_page_state(page, "step3_exception")
                    await _send_screenshot_to_log_group(
                        shot,
                        f"❌ **IG: Login exception**\n`{str(e)[:300]}`"
                    )
            else:
                logger.warning(
                    "⚠️  Step 3/5 – SKIPPED (no credentials)\n"
                    "   IG_USERNAME and IG_PASSWORD are not set.\n"
                    "   Only guest/unauthenticated cookies will be collected.\n"
                    "   Downloads of private content or stories will fail.\n"
                    "   Set both env vars and restart the bot."
                )

            # ── 4. Simulate natural browsing ──────────────────────────────────
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

            # ── 5. Export cookies ─────────────────────────────────────────────
            logger.info("🔗 Step 5/5 – Exporting cookies from browser context ...")
            all_cookies = await context.cookies()
            await context.close()
            context = None

            ig_cookies = [
                c for c in all_cookies
                if "instagram.com" in c.get("domain", "")
                or "facebook.com" in c.get("domain", "")
            ]

            cookie_names = {c["name"] for c in ig_cookies}
            logger.info(
                f"🍪 Collected {len(ig_cookies)} Instagram/FB cookies: {cookie_names}"
            )

            if not ig_cookies:
                logger.error(
                    "❌ Zero Instagram cookies collected from browser context.\n"
                    "   This usually means the page never loaded correctly.\n"
                    "   Check earlier screenshots for clues."
                )
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
                # Try to grab a last screenshot before closing
                pages = context.pages
                if pages:
                    shot = await _log_page_state(pages[-1], "fatal_crash")
                    await _send_screenshot_to_log_group(
                        shot,
                        f"❌ **IG: Playwright session crashed**\n`{str(e)[:300]}`"
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
            logger.info(
                "✅ Instagram cookies already refreshed by another coroutine — reusing"
            )
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok:
            logger.error("Instagram cookie generation failed.")
            return None

        if not os.path.exists(COOKIE_FILE):
            logger.error("Cookie file missing after generation.")
            return None

        if not verify_cookies_file(COOKIE_FILE) or is_cookie_file_expired(COOKIE_FILE):
            logger.warning(
                "⚠️ Cookie verification failed on first attempt – retrying ..."
            )
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
            ok2 = await generate_cookies_via_playwright(reason=f"{reason} (retry)")
            if not ok2 or not os.path.exists(COOKIE_FILE):
                return None
            if not verify_cookies_file(COOKIE_FILE):
                logger.error("❌ Instagram cookie retry also failed verification")
                return None

        logger.info("✅ Instagram cookies verified successfully")
        ip_info   = await get_public_ip_info() or {}
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await send_to_log_group(
            text=(
                f"🌐 **Instagram Cookies Generated (Browser Profile)**\n\n"
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

        found_guest = [c for c in guest_cookies if c in content]
        found_auth  = [c for c in auth_cookies  if c in content]
        found_all   = found_guest + found_auth

        if len(found_all) < 2:
            logger.warning(f"⚠️ Too few Instagram cookies found: {found_all}")
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
        logger.error(f"Failed to parse Instagram cookie expiry: {e}")
        return None


def is_cookie_file_expired(filepath: str) -> bool:
    if not os.path.exists(filepath):
        return True
    min_exp = get_cookie_min_expiry(filepath)
    if min_exp is None:
        logger.info("Instagram cookies have no expiry timestamp (session cookies) – treating as valid")
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
                        "🔄 Regenerating cookies via Browser Profile ...\n\n"
                        "#InstagramCookies"
                    )
                )
                new_cookie = await refresh_cookies_from_browser(
                    reason="Auth/rate-limit detected during download"
                )
                if new_cookie:
                    logger.info("✅ Fresh Instagram cookies – retrying download ...")
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

    logger.info("🚀 Starting Instagram cookie services (Browser Profile) ...")
    cleanup_playwright_profile()

    need_refresh = (
        not os.path.exists(COOKIE_FILE)
        or not verify_cookies_file(COOKIE_FILE)
        or is_cookie_file_expired(COOKIE_FILE)
    )

    if need_refresh:
        logger.info("🔄 No valid Instagram cookies – generating via Browser Profile ...")
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
            "✅ Existing Instagram cookies are valid – skipping regeneration."
        )

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
