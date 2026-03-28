import os
import re
import glob
import time
import shutil
import random
import asyncio
import logging
import datetime
from typing import Optional, Union, Tuple

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

try:
    from pyrogram.enums import MessageEntityType
    from pyrogram.types import Message
    PYROGRAM_AVAILABLE = True
except Exception:
    PYROGRAM_AVAILABLE = False
    Message = None
    MessageEntityType = None

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

DOWNLOAD_DIR   = os.path.join(os.getcwd(), "downloads");   os.makedirs(DOWNLOAD_DIR,   exist_ok=True)
COOKIES_DIR    = os.path.join(os.getcwd(), "cookies");     os.makedirs(COOKIES_DIR,    exist_ok=True)
COOKIE_FILE    = os.path.join(COOKIES_DIR, "instagram_cookies.txt")
IG_PROFILE_DIR = os.path.join(os.getcwd(), "ig_playwright_profile"); os.makedirs(IG_PROFILE_DIR, exist_ok=True)
IG_CACHE_DIR   = os.path.join(os.getcwd(), "igcache");     os.makedirs(IG_CACHE_DIR,   exist_ok=True)
SCREENSHOT_DIR = os.path.join(os.getcwd(), "ig_screenshots"); os.makedirs(SCREENSHOT_DIR, exist_ok=True)

DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
_COOKIE_LOCK       = asyncio.Lock()

# Required by several Instagram API endpoints
IG_APP_ID = "936619743392459"

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
#  USER-AGENT POOL  (Chrome 131-134, early 2026)
# ══════════════════════════════════════════════════════════════════════════════
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
]

_SEC_CH_UA = {
    "131": '"Chromium";v="131", "Not(A:Brand";v="99", "Google Chrome";v="131"',
    "132": '"Chromium";v="132", "Not(A:Brand";v="99", "Google Chrome";v="132"',
    "133": '"Chromium";v="133", "Not(A:Brand";v="99", "Google Chrome";v="133"',
    "134": '"Chromium";v="134", "Not(A:Brand";v="99", "Google Chrome";v="134"',
}

def _ua_sec_ch(ua: str) -> str:
    for ver in ("134", "133", "132", "131"):
        if f"Chrome/{ver}" in ua:
            return _SEC_CH_UA[ver]
    return _SEC_CH_UA["131"]

# ══════════════════════════════════════════════════════════════════════════════
#  PROXY HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_proxy_list(env: str):
    return [p.strip() for p in env.split(",") if p.strip()] if env else []

IG_PROXY_POOL            = _parse_proxy_list(IG_PROXIES)
IG_PLAYWRIGHT_PROXY_POOL = _parse_proxy_list(IG_PLAYWRIGHT_PROXY)

def choose_random_proxy(pool):
    return random.choice(pool) if pool else None

# ══════════════════════════════════════════════════════════════════════════════
#  LOG-GROUP HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def send_to_log_group(text: str = None, file_obj=None):
    if not LOG_GROUP_ID or not app:
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
        f"🍪 **Instagram Cookie Regenerated**\n\n"
        f"📅 Time   : `{ts}`\n"
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
    except Exception:
        try:
            with open(COOKIE_FILE, "rb") as f:
                await send_to_log_group(text=caption, file_obj=f)
        except Exception as e:
            logger.error(f"send_cookie_file_to_log_group: {e}")

async def _send_screenshot(path: str, caption: str):
    if not LOG_GROUP_ID or not app or not os.path.exists(path):
        return
    try:
        await app.send_photo(chat_id=LOG_GROUP_ID, photo=path, caption=caption)
        logger.info(f"📸 Debug screenshot sent to log group: {path}")
    except Exception as e:
        logger.error(f"_send_screenshot: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC IP INFO
# ══════════════════════════════════════════════════════════════════════════════
async def get_public_ip_info() -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://ipapi.co/json/", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    d = await r.json()
                    return {"ip": d.get("ip"), "city": d.get("city"),
                            "country": d.get("country_name"), "org": d.get("org")}
    except Exception as e:
        logger.error(f"get_public_ip_info: {e}")
    return {}

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE / PROFILE CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def clear_old_cookies():
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            logger.warning("🧹 Old Instagram cookies removed")
        for f in glob.glob(os.path.join(COOKIES_DIR, "instagram*")):
            try: os.remove(f)
            except Exception: pass
    except Exception as e:
        logger.error(f"clear_old_cookies: {e}")

def wipe_playwright_profile():
    try:
        if os.path.exists(IG_PROFILE_DIR):
            shutil.rmtree(IG_PROFILE_DIR)
            logger.info("🧹 Wiped stale Playwright profile directory")
        os.makedirs(IG_PROFILE_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"wipe_playwright_profile: {e}")

def cleanup_playwright_profile():
    for fname in ("SingletonLock", "SingletonCookie", "SingletonSocket", "DevToolsActivePort"):
        fpath = os.path.join(IG_PROFILE_DIR, fname)
        if os.path.exists(fpath):
            try: os.remove(fpath)
            except Exception: pass

# ══════════════════════════════════════════════════════════════════════════════
#  NETSCAPE COOKIE WRITER
# ══════════════════════════════════════════════════════════════════════════════
def _write_netscape_cookies(cookies: list, filepath: str) -> bool:
    try:
        lines   = ["# Netscape HTTP Cookie File", "# Auto-generated by Instagram.py\n"]
        written = 0
        for c in cookies:
            domain = c.get("domain", "")
            if not domain:
                continue
            if not domain.startswith("."):
                domain = "." + domain
            name  = c.get("name", "")
            value = c.get("value", "")
            if not name:
                continue
            include_sub = "TRUE"
            path        = c.get("path", "/")
            secure      = "TRUE" if c.get("secure", False) else "FALSE"
            exp_raw     = c.get("expires", -1)
            expires     = int(exp_raw) if exp_raw and exp_raw > 0 else 0
            lines.append(f"{domain}\t{include_sub}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
            written += 1
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info(f"✅ Wrote {written} cookies → {filepath}")
        return written > 0
    except Exception as e:
        logger.error(f"_write_netscape_cookies: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  STEALTH INIT SCRIPT
# ══════════════════════════════════════════════════════════════════════════════
STEALTH_SCRIPT = """
(() => {
  // 1. Erase webdriver flag
  Object.defineProperty(navigator, 'webdriver', { get: () => false, configurable: true });
  try { delete navigator.__proto__.webdriver; } catch(e) {}

  // 2. Realistic plugin list
  const _plugins = [
    {name:'Chrome PDF Plugin',   filename:'internal-pdf-viewer', description:'Portable Document Format'},
    {name:'Chrome PDF Viewer',   filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
    {name:'Native Client',       filename:'internal-nacl-plugin', description:''},
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => Object.assign(_plugins, {
      length: _plugins.length,
      item:      (i) => _plugins[i] ?? null,
      namedItem: (n) => _plugins.find(p => p.name === n) ?? null,
      refresh:   () => {},
    }),
  });

  // 3. Language / locale
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });

  // 4. Chrome runtime object
  if (!window.chrome) {
    window.chrome = {
      app: { isInstalled: false, InstallState: {DISABLED:'disabled',INSTALLED:'installed',NOT_INSTALLED:'not_installed'}, RunningState: {CANNOT_RUN:'cannot_run',READY_TO_RUN:'ready_to_run',RUNNING:'running'} },
      runtime: {
        PlatformOs: {MAC:'mac',WIN:'win',ANDROID:'android',CROS:'cros',LINUX:'linux',OPENBSD:'openbsd'},
        PlatformArch: {ARM:'arm',X86_32:'x86-32',X86_64:'x86-64'},
        PlatformNaclArch: {ARM:'arm',X86_32:'x86-32',X86_64:'x86-64'},
        RequestUpdateCheckStatus: {THROTTLED:'throttled',NO_UPDATE:'no_update',UPDATE_AVAILABLE:'update_available'},
        OnInstalledReason: {INSTALL:'install',UPDATE:'update',CHROME_UPDATE:'chrome_update',SHARED_MODULE_UPDATE:'shared_module_update'},
        OnRestartRequiredReason: {APP_UPDATE:'app_update',OS_UPDATE:'os_update',PERIODIC:'periodic'},
      },
      loadTimes: () => ({}),
      csi: () => ({}),
    };
  }

  // 5. Permissions – hide notification prompt state
  const _origPerms = navigator.permissions?.query?.bind(navigator.permissions);
  if (_origPerms) {
    navigator.permissions.query = (p) =>
      p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origPerms(p);
  }

  // 6. Hardware fingerprint
  Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
  Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8 });
  Object.defineProperty(navigator, 'maxTouchPoints',      { get: () => 0 });
  Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
  Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });

  // 7. WebGL vendor/renderer spoof
  const _getParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Intel Inc.';
    if (param === 37446) return 'Intel Iris OpenGL Engine';
    return _getParam.call(this, param);
  };
})();
"""

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
async def _log_page_state(page, label: str) -> str:
    try:
        url   = page.url
        title = await page.title()
        logger.info(f"📍 [{label}] URL: {url} | Title: {title}")
        ts   = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        lbl  = re.sub(r"[^A-Za-z0-9_\-]", "_", label)[:40]
        path = os.path.join(SCREENSHOT_DIR, f"ig_{lbl}_{ts}.png")
        await page.screenshot(path=path, full_page=False)
        logger.info(f"📸 Screenshot saved: {path}")
        return path
    except Exception as e:
        logger.warning(f"_log_page_state [{label}]: {e}")
        return ""

async def _body_len(page) -> int:
    try:
        return len(await page.inner_text("body"))
    except Exception:
        return 0

async def _dismiss_popups(page) -> None:
    targets = [
        ("save login",    "button:has-text('Save info'), button:has-text('Save Info')"),
        ("not now",       "button:has-text('Not now'), button:has-text('Not Now')"),
        ("notifications", "button:has-text('Turn On')"),
        ("cookie banner", "button:has-text('Allow all cookies'), button:has-text('Accept All')"),
    ]
    for desc, sel in targets:
        try:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                logger.info(f"✅ Dismissed popup: {desc}")
                await page.wait_for_timeout(random.randint(1000, 2000))
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════════════════════
#  HUMAN-LIKE TYPING
# ══════════════════════════════════════════════════════════════════════════════
async def _human_type(page, locator, text: str) -> None:
    try:
        await locator.click()
        await page.wait_for_timeout(random.randint(200, 500))
        await locator.press("Control+a")
        await page.wait_for_timeout(random.randint(80, 160))
        await locator.press("Delete")
        await page.wait_for_timeout(random.randint(150, 350))
        for ch in text:
            await locator.press(ch)
            await page.wait_for_timeout(random.randint(60, 180))
        await page.wait_for_timeout(random.randint(300, 700))
    except Exception as e:
        logger.warning(f"_human_type fallback fill: {e}")
        try:
            await locator.fill(text)
        except Exception as e2:
            logger.error(f"_human_type fill failed: {e2}")

# ══════════════════════════════════════════════════════════════════════════════
#  CHECKPOINT / 2FA
# ══════════════════════════════════════════════════════════════════════════════
async def _check_for_checkpoint(page) -> bool:
    url = page.url.lower()
    if any(s in url for s in ("challenge", "checkpoint", "accounts/suspended",
                               "unusualactivity", "verification")):
        logger.error(f"🚨 Checkpoint detected: {page.url}")
        return True
    try:
        body = (await page.inner_text("body")).lower()
        if any(s in body for s in ("verify your account", "verify it's you",
                                    "we detected an unusual", "suspicious activity",
                                    "complete a security check")):
            logger.error(f"🚨 Checkpoint via page text: {page.url}")
            return True
    except Exception:
        pass
    return False

async def _check_for_2fa(page) -> str:
    """Returns 'sms', 'totp', or 'none'."""
    try:
        url = page.url.lower()
        if "two_factor" in url or "2fa" in url or "checkpoint" in url:
            body = (await page.inner_text("body")).lower()
            if "text message" in body or "sms" in body or "phone number" in body:
                return "sms"
            return "totp"
        code_inp = page.locator(
            "input[name='verificationCode'], "
            "input[aria-label*='Security Code'], "
            "input[aria-label*='Confirmation Code'], "
            "input[placeholder*='6-digit'], "
            "input[placeholder*='security code']"
        )
        if await code_inp.count() > 0:
            body = (await page.inner_text("body")).lower()
            if "text message" in body or "sms" in body:
                return "sms"
            return "totp"
    except Exception as e:
        logger.debug(f"_check_for_2fa: {e}")
    return "none"

async def _handle_2fa(page) -> bool:
    fa = await _check_for_2fa(page)
    if fa == "none":
        return True
    if fa == "sms":
        logger.error("🔒 SMS 2FA required – cannot automate")
        await send_to_log_group(text="🔒 **Instagram SMS 2FA Required – Cannot Automate**\n#2FA")
        return False
    # TOTP
    if not IG_TOTP_SECRET:
        logger.error("🔒 TOTP required but IG_TOTP_SECRET not set")
        return False
    try:
        import pyotp
    except ImportError:
        logger.error("pyotp not installed: pip install pyotp")
        return False
    try:
        code = pyotp.TOTP(IG_TOTP_SECRET).now()
        logger.info(f"🔑 TOTP code: {code}")
        inp = page.locator(
            "input[name='verificationCode'], "
            "input[aria-label*='Security Code'], "
            "input[aria-label*='Confirmation Code'], "
            "input[placeholder*='6-digit'], "
            "input[placeholder*='security code']"
        )
        if await inp.count() == 0:
            logger.error("❌ TOTP input not found")
            return False
        await inp.first.fill(code)
        await page.wait_for_timeout(random.randint(500, 900))
        btn = page.locator("button[type='submit'], button:has-text('Confirm'), button:has-text('Submit')")
        if await btn.count() > 0:
            await btn.first.click()
        else:
            await inp.first.press("Enter")
        logger.info("✅ TOTP submitted")
        await page.wait_for_timeout(5000)
        return True
    except Exception as e:
        logger.error(f"_handle_2fa TOTP error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════
async def _verify_login(context, page) -> bool:
    try:
        all_c  = await context.cookies()
        names  = {c["name"] for c in all_c if "instagram.com" in c.get("domain", "")}
        found  = names & {"sessionid", "ds_user_id", "rur"}
        url    = page.url
        title  = await page.title()
        logger.info(
            f"🔍 Login verification:\n"
            f"   URL          : {url}\n"
            f"   Title        : {title}\n"
            f"   All cookies  : {names}\n"
            f"   Auth cookies : {found or 'NONE ← login failed'}"
        )
        if found:
            logger.info(f"✅ Login verified: {found}")
            return True
        return False
    except Exception as e:
        logger.error(f"_verify_login: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  WAIT-FOR-LOGIN-RESULT HELPER
# ══════════════════════════════════════════════════════════════════════════════
async def _wait_for_login_result(page, timeout_ms: int = 25_000) -> str:
    """
    Polls after form submit.
    Returns: 'success' | 'wrong_password' | 'checkpoint' | '2fa' | 'timeout'
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        await page.wait_for_timeout(800)
        url = page.url.lower()

        # ── Navigated away from login → success ──────────────────────────────
        if "instagram.com" in url and "login" not in url and "accounts" not in url:
            return "success"

        # ── 2FA page ─────────────────────────────────────────────────────────
        if "two_factor" in url or "2fa" in url:
            return "2fa"

        # ── Checkpoint ───────────────────────────────────────────────────────
        if "challenge" in url or "checkpoint" in url:
            return "checkpoint"

        # ── Inline error messages ─────────────────────────────────────────────
        try:
            body = (await page.inner_text("body")).lower()
            wrong_pw_signals = [
                "sorry, your password was incorrect",
                "the password you entered is incorrect",
                "your password was incorrect",
                "incorrect password",
                "wrong password",
            ]
            suspicious_signals = [
                "there was an unusual login attempt",
                "we detected an unusual login",
                "suspicious login",
            ]
            if any(s in body for s in wrong_pw_signals):
                logger.error("❌ Wrong password detected via page text")
                return "wrong_password"
            if any(s in body for s in suspicious_signals):
                logger.warning("⚠️ Suspicious login warning detected")
                return "checkpoint"
        except Exception:
            pass

    return "timeout"

# ══════════════════════════════════════════════════════════════════════════════
#  FIND USERNAME / PASSWORD FIELDS  (handles both old and new IG layouts)
# ══════════════════════════════════════════════════════════════════════════════
async def _find_username_input(page):
    """Try multiple selectors to locate the username/email input."""
    selectors = [
        "input[name='username']",
        "input[name='email']",
        "input[aria-label='Phone number, username, or email']",
        "input[aria-label='Mobile number, username or email']",
        "input[aria-label*='username']",
        "input[aria-label*='email']",
        "input[autocomplete='username']",
        "input[type='text']",
    ]
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=5_000, state="visible")
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                logger.info(f"✅ Username field found: {sel}")
                return el.first
        except Exception:
            continue
    return None

async def _find_password_input(page):
    """Try multiple selectors to locate the password input."""
    selectors = [
        "input[name='pass']",
        "input[name='password']",
        "input[type='password']",
        "input[aria-label='Password']",
        "input[aria-label*='assword']",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                logger.info(f"✅ Password field found: {sel}")
                return el.first
        except Exception:
            continue
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  FILL CREDENTIALS + SUBMIT
# ══════════════════════════════════════════════════════════════════════════════
async def _fill_and_submit(page, context) -> bool:
    """Find fields, type credentials, click submit, wait for result."""

    # ── find username field ───────────────────────────────────────────────────
    username_input = await _find_username_input(page)
    if not username_input:
        logger.error("❌ username field not found")
        shot = await _log_page_state(page, "no_username_field")
        await _send_screenshot(shot, "❌ **IG: Username field not found**")
        return False

    # ── find password field ───────────────────────────────────────────────────
    password_input = await _find_password_input(page)
    if not password_input:
        logger.error("❌ password field not found")
        shot = await _log_page_state(page, "no_password_field")
        await _send_screenshot(shot, "❌ **IG: Password field not found**")
        return False

    # ── type credentials ──────────────────────────────────────────────────────
    logger.info(f"✍️  Entering username: {IG_USERNAME}")
    await _human_type(page, username_input, IG_USERNAME)
    await page.wait_for_timeout(random.randint(400, 900))

    logger.info("✍️  Entering password")
    await _human_type(page, password_input, IG_PASSWORD)
    await page.wait_for_timeout(random.randint(600, 1100))

    # ── find and click submit ─────────────────────────────────────────────────
    # IMPORTANT: On the new Instagram React login, the button starts as
    # aria-disabled="true" and becomes clickable only after credentials are typed.
    # We MUST NOT check for aria-disabled here — just click whatever submit button
    # is visible. The button may still have aria-disabled="true" in the DOM but
    # still respond to a click after the fields are filled.
    submit_btn = None
    submit_selectors = [
        "button[type='submit']",
        "button:has-text('Log in')",
        "button:has-text('Log In')",
        "button:has-text('Log into')",
        "[role='button']:has-text('Log in')",
    ]
    for sel in submit_selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                # Check visible regardless of aria-disabled
                if await el.first.is_visible():
                    submit_btn = el.first
                    logger.info(f"✅ Submit button found: {sel}")
                    break
        except Exception:
            continue

    if submit_btn:
        try:
            # Use JavaScript click to bypass aria-disabled blocking
            await submit_btn.evaluate("btn => btn.click()")
            logger.info("🖱️  Submit button clicked (JS)")
        except Exception:
            try:
                await submit_btn.click(force=True)
                logger.info("🖱️  Submit button clicked (force)")
            except Exception as e:
                logger.warning(f"Submit button click failed, trying Enter: {e}")
                await password_input.press("Enter")
                logger.info("🖱️  Enter pressed on password field")
    else:
        # Fallback: press Enter on password field
        await password_input.press("Enter")
        logger.info("🖱️  Enter pressed on password field (no button found)")

    # ── wait for result ───────────────────────────────────────────────────────
    result = await _wait_for_login_result(page)
    logger.info(f"📊 Login result signal: {result}")

    if result == "wrong_password":
        logger.error(
            "❌ Instagram rejected credentials.\n"
            "   → Check IG_PASSWORD env var is correct.\n"
            "   → The account may have been locked after too many attempts."
        )
        await send_to_log_group(
            text=(
                f"❌ **Instagram: Wrong Password**\n\n"
                f"👤 Account : `{IG_USERNAME}`\n"
                f"Action     : Update `IG_PASSWORD` env var.\n\n"
                f"#InstagramCookies"
            )
        )
        return False

    if result == "2fa":
        fa_ok = await _handle_2fa(page)
        if not fa_ok:
            return False
        await page.wait_for_timeout(5000)

    if result == "checkpoint":
        if await _check_for_checkpoint(page):
            shot = await _log_page_state(page, "checkpoint")
            await _send_screenshot(shot, "🚨 **IG: Checkpoint after login**")
            return False

    if result == "timeout":
        # Timeout — check if we somehow got logged in anyway
        logger.warning("⚠️  Login result timeout — verifying via cookies ...")

    return await _verify_login(context, page)

# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIC LOGIN  (navigates directly to /accounts/login/)
# ══════════════════════════════════════════════════════════════════════════════
async def _try_classic_login(page, context) -> bool:
    logger.info("🔐 Classic login path: /accounts/login/")
    try:
        await page.goto(
            "https://www.instagram.com/accounts/login/",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        # Give React time to hydrate and enable the form
        await page.wait_for_timeout(random.randint(6000, 9000))
    except Exception as e:
        logger.warning(f"Classic goto warning: {e}")
        await page.wait_for_timeout(6000)

    bl = await _body_len(page)
    logger.info(f"📄 Login page body: {bl} chars")
    if bl < 200:
        logger.error("❌ Login page blank – bot-blocked at /accounts/login/")
        shot = await _log_page_state(page, "blank_classic_login")
        await _send_screenshot(shot, "🚨 **IG: Blank login page (classic)**")
        return False

    # Dismiss cookie consent banners if present
    await _dismiss_popups(page)
    await page.wait_for_timeout(1000)

    return await _fill_and_submit(page, context)

# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIC LOGIN ON CURRENT PAGE  (already navigated via click from homepage)
# ══════════════════════════════════════════════════════════════════════════════
async def _try_classic_login_on_current_page(page, context) -> bool:
    logger.info("🔐 Classic login: already on page (arrived via click)")
    bl = await _body_len(page)
    logger.info(f"📄 Login page body: {bl} chars")
    if bl < 200:
        logger.error("❌ Login page blank after click-nav")
        shot = await _log_page_state(page, "blank_click_nav")
        await _send_screenshot(shot, "🚨 **IG: Blank login page (click-nav)**")
        return False

    await _dismiss_popups(page)
    await page.wait_for_timeout(1000)

    return await _fill_and_submit(page, context)

# ══════════════════════════════════════════════════════════════════════════════
#  MOBILE LOGIN  (fallback – smaller viewport, simpler DOM)
# ══════════════════════════════════════════════════════════════════════════════
async def _try_mobile_login(page, context) -> bool:
    logger.info("📱 Mobile web login path")
    try:
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(
            "https://www.instagram.com/accounts/login/?source=auth_switcher",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        await page.wait_for_timeout(random.randint(5000, 7500))
        bl = await _body_len(page)
        logger.info(f"📄 Mobile login body: {bl} chars")
        if bl < 200:
            logger.error("❌ Mobile login page blank – bot-blocked")
            return False

        # Accept cookie banner
        await _dismiss_popups(page)
        await page.wait_for_timeout(1000)

        result = await _fill_and_submit(page, context)
        await page.set_viewport_size({"width": 1920, "height": 1080})
        return result
    except Exception as e:
        logger.error(f"_try_mobile_login: {e}")
        try:
            await page.set_viewport_size({"width": 1920, "height": 1080})
        except Exception:
            pass
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PLAYWRIGHT COOKIE GENERATION
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cookies_via_playwright(reason: str = "Profile cookie generation") -> bool:
    """
    Launch headless Chromium, log in to Instagram, and write authenticated
    cookies to COOKIE_FILE in Netscape format.
    Returns True only if sessionid / ds_user_id cookies are present.
    """
    if not IG_USERNAME or not IG_PASSWORD:
        logger.error("❌ IG_USERNAME / IG_PASSWORD not set")
        await send_to_log_group(
            text="❌ **Instagram: credentials not set**\nSet IG_USERNAME + IG_PASSWORD.\n#InstagramCookies"
        )
        return False

    logger.info(
        f"🌐 Launching Playwright [{reason}] ...\n"
        f"   Username    : {IG_USERNAME}\n"
        f"   TOTP secret : {'✅ set' if IG_TOTP_SECRET else '⚠️  not set'}\n"
        f"   Proxy       : {choose_random_proxy(IG_PLAYWRIGHT_PROXY_POOL) or 'none (⚠️ may fail on cloud IPs)'}"
    )
    await send_to_log_group(
        text=(
            f"🌐 **Instagram – Generating Cookies**\n"
            f"📝 Reason : {reason}\n"
            f"⏳ Launching Chromium ...\n#InstagramCookies"
        )
    )

    wipe_playwright_profile()
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
                    "--disable-extensions",
                    "--disable-gpu",
                    "--window-size=1920,1080",
                    "--start-maximized",
                    "--lang=en-US",
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
                    "--metrics-recording-only",
                    "--safebrowsing-disable-auto-update",
                    "--exclude-switches=enable-automation",
                    "--disable-web-security",
                ],
                proxy={"server": proxy} if proxy else None,
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                ignore_https_errors=True,
                accept_downloads=False,
                extra_http_headers={
                    "Accept-Language":    "en-US,en;q=0.9",
                    "sec-ch-ua":          _ua_sec_ch(user_agent),
                    "sec-ch-ua-mobile":   "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
            )

            page = await context.new_page()
            await page.add_init_script(STEALTH_SCRIPT)

            # ── Step 1: Warm up ───────────────────────────────────────────────
            logger.info("🔗 Step 1/4 – Warming up: visiting instagram.com ...")
            try:
                await page.goto(
                    "https://www.instagram.com/",
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
                await page.wait_for_timeout(random.randint(3000, 5000))
                # Accept cookie banners
                await _dismiss_popups(page)
                await _log_page_state(page, "step1_homepage")
                await page.mouse.move(random.randint(200, 800), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(600, 1400))
                await page.mouse.wheel(0, random.randint(100, 400))
                await page.wait_for_timeout(random.randint(1000, 2500))
            except Exception as e:
                logger.warning(f"Warmup non-fatal: {e}")

            # ── Step 2: Login ─────────────────────────────────────────────────
            logger.info(f"🔗 Step 2/4 – Logging in as: {IG_USERNAME} ...")

            # Try clicking the Log In link from homepage first (less bot-like)
            login_clicked = False
            try:
                link = page.locator(
                    "a[href='/accounts/login/'], a:has-text('Log in'), a:has-text('Log In')"
                )
                if await link.count() > 0:
                    await link.first.click()
                    await page.wait_for_timeout(random.randint(4000, 6500))
                    logger.info(f"✅ Navigated to login via click → {page.url}")
                    login_clicked = True
            except Exception as e:
                logger.warning(f"Click-to-login failed: {e}")

            try:
                if login_clicked and "login" in page.url.lower():
                    login_ok = await _try_classic_login_on_current_page(page, context)
                else:
                    login_ok = await _try_classic_login(page, context)
            except Exception as e:
                logger.warning(f"Classic login exception: {e}")
                login_ok = False

            if not login_ok:
                logger.warning("⚠️ Classic login failed – trying mobile path ...")
                try:
                    login_ok = await _try_mobile_login(page, context)
                except Exception as e:
                    logger.warning(f"Mobile login exception: {e}")
                    login_ok = False

            # ── Post-login ────────────────────────────────────────────────────
            if login_ok:
                if await _check_for_checkpoint(page):
                    shot = await _log_page_state(page, "step2_checkpoint")
                    await _send_screenshot(shot, "🚨 **IG: Checkpoint after login**")
                    login_ok = False

            if login_ok:
                await _dismiss_popups(page)
                await page.wait_for_timeout(random.randint(2000, 3500))
                await _log_page_state(page, "step2_logged_in")
                logger.info("✅ Instagram login confirmed!")
                await send_to_log_group(
                    text=(
                        f"✅ **Instagram Login Successful**\n"
                        f"👤 Account : `{IG_USERNAME}`\n"
                        f"📝 Reason  : {reason}\n#InstagramCookies"
                    )
                )
            else:
                logger.error(
                    "❌ Instagram login FAILED.\n"
                    "   Most likely causes on Railway/cloud:\n"
                    "   1. Set IG_PLAYWRIGHT_PROXY to a residential proxy\n"
                    "   2. Verify IG_PASSWORD is correct\n"
                    "   3. Account may require SMS 2FA (not automatable)\n"
                    "   4. Account locked – log in manually once to unlock"
                )
                shot = await _log_page_state(page, "step2_login_failed")
                await _send_screenshot(shot, "❌ **IG: Login Failed**\nCheck proxy + credentials.")
                await send_to_log_group(
                    text=(
                        f"❌ **Instagram Login FAILED**\n"
                        f"👤 Account : `{IG_USERNAME}`\n"
                        f"📝 Reason  : {reason}\n\n"
                        f"Fixes:\n"
                        f"• Set `IG_PLAYWRIGHT_PROXY` (residential)\n"
                        f"• Verify `IG_PASSWORD`\n"
                        f"• Disable SMS 2FA on account\n"
                        f"• Unlock account via browser manually\n#InstagramCookies"
                    )
                )
                await context.close()
                context = None
                return False

            # ── Step 3: Simulate natural browsing ─────────────────────────────
            logger.info("🔗 Step 3/4 – Natural browsing ...")
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
                logger.debug(f"Natural browsing non-fatal: {e}")

            # ── Step 4: Export cookies ─────────────────────────────────────────
            logger.info("🔗 Step 4/4 – Exporting cookies ...")
            all_cookies = await context.cookies()
            await context.close()
            context = None

            ig_cookies   = [c for c in all_cookies if "instagram.com" in c.get("domain", "")
                                                    or "facebook.com"  in c.get("domain", "")]
            cookie_names = {c["name"] for c in ig_cookies}
            auth_present = {"sessionid", "ds_user_id"} & cookie_names

            logger.info(f"🍪 Collected {len(ig_cookies)} cookies | auth: {auth_present or 'NONE'}")

            if not auth_present:
                logger.error("❌ sessionid/ds_user_id missing – NOT writing cookie file")
                await send_to_log_group(
                    text="❌ **Instagram: no auth cookies after login**\nFile NOT written.\n#InstagramCookies"
                )
                return False

            ok = _write_netscape_cookies(ig_cookies, COOKIE_FILE)
            if ok:
                logger.info(f"✅ Cookies saved | auth={auth_present} | total={len(ig_cookies)}")
            return ok

    except Exception as e:
        logger.error(f"❌ Playwright session crashed: {type(e).__name__}: {str(e)[:400]}")
        if context:
            try:
                pages = context.pages
                if pages:
                    shot = await _log_page_state(pages[-1], "fatal_crash")
                    await _send_screenshot(shot, f"❌ **IG: Playwright crash**\n`{str(e)[:200]}`")
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=(
                f"❌ **Instagram Browser Crashed**\n"
                f"📝 Reason : {reason}\n"
                f"⚠️ Error  : `{str(e)[:300]}`\n#InstagramCookies"
            )
        )
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE REFRESH  (with lock)
# ══════════════════════════════════════════════════════════════════════════════
async def refresh_cookies_from_browser(reason: str = "On-demand refresh") -> Optional[str]:
    async with _COOKIE_LOCK:
        if (os.path.exists(COOKIE_FILE)
                and verify_cookies_file(COOKIE_FILE)
                and not is_cookie_file_expired(COOKIE_FILE)):
            logger.info("✅ Cookies already refreshed by another coroutine – reusing")
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok or not os.path.exists(COOKIE_FILE):
            logger.error("Cookie generation failed or file missing")
            return None

        if not verify_cookies_file(COOKIE_FILE):
            logger.error("Cookie file failed verification")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
            return None

        if is_cookie_file_expired(COOKIE_FILE):
            logger.warning("Cookie file appears expired immediately after generation – proceeding anyway")

        logger.info("✅ Cookies verified successfully")
        ip   = await get_public_ip_info()
        ts   = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await send_to_log_group(
            text=(
                f"🌐 **Instagram Cookies Ready**\n"
                f"📅 Time     : `{ts}`\n"
                f"🌍 IP       : `{(ip or {}).get('ip','unknown')}`\n"
                f"📍 Location : {(ip or {}).get('city','?')}, {(ip or {}).get('country','?')}\n"
                f"🏢 ISP      : {(ip or {}).get('org','?')}\n"
                f"📝 Reason   : {reason}\n#InstagramCookies"
            )
        )
        await send_cookie_file_to_log_group(reason=reason)
        return COOKIE_FILE

# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════
def verify_cookies_file(filename: str) -> bool:
    try:
        if not os.path.exists(filename):
            return False
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        if "instagram.com" not in content:
            logger.error("No instagram.com in cookie file")
            return False
        # Require at least one auth cookie
        found_auth = [c for c in ("sessionid", "ds_user_id") if c in content]
        if not found_auth:
            logger.error("❌ Cookie file has no auth cookies (sessionid/ds_user_id missing)")
            return False
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Cookie file is JSON not Netscape")
            return False
        valid = sum(
            1 for line in content.strip().split("\n")
            if line and not line.startswith("#") and "\t" in line
        )
        if valid < 2:
            logger.error(f"Too few valid cookie lines: {valid}")
            return False
        logger.info(f"✅ Cookies verified: lines={valid} | auth={found_auth}")
        return True
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
                if len(parts) < 7 or "instagram.com" not in parts[0]:
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
        return False
    now = int(time.time())
    if min_exp < now:
        logger.info(f"🕐 Cookie expired at {datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z")
        return True
    rem = min_exp - now
    logger.info(f"✅ Cookie valid for {rem // 3600}h {(rem % 3600) // 60}m")
    return False

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH-ERROR DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def is_auth_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(k in s for k in (
        "login required", "not logged in", "checkpoint required",
        "rate limit", "rate-limit", "rate_limit",
        "http error 401", "http error 403",
        "unable to extract", "cookie", "sign in",
        "authentication", "access denied", "forbidden",
        "bad credentials", "challenge required",
        "content is not available",
    ))

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN COOKIE GETTER
# ══════════════════════════════════════════════════════════════════════════════
async def get_cookies(force_refresh: bool = False) -> Optional[str]:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        if verify_cookies_file(COOKIE_FILE) and not is_cookie_file_expired(COOKIE_FILE):
            logger.info("✅ Using existing valid cookies")
            return COOKIE_FILE
        logger.warning("Cookies invalid/expired – regenerating ...")
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
    reason = "Force refresh – auth/rate-limit" if force_refresh else "Initial / expired"
    return await refresh_cookies_from_browser(reason=reason)

# ══════════════════════════════════════════════════════════════════════════════
#  YT-DLP OPTIONS
# ══════════════════════════════════════════════════════════════════════════════
def get_ytdlp_opts(extra_opts: dict = None, use_cookie_file: str = None) -> dict:
    ua   = random.choice(USER_AGENTS)
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
            "x-ig-app-id":     IG_APP_ID,
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.instagram.com/",
        },
    }
    if use_cookie_file and os.path.exists(use_cookie_file):
        base["cookiefile"] = use_cookie_file
    else:
        logger.warning("No cookie file for yt-dlp")

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
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"

def _extract_shortcode(url: str) -> Optional[str]:
    m = SHORTCODE_REGEX.search(url)
    return m.group(1) if m else None

def _find_downloaded_file(identifier: str) -> Optional[str]:
    if not identifier:
        return None
    for fname in os.listdir(DOWNLOAD_DIR):
        if identifier in fname:
            fp = os.path.join(DOWNLOAD_DIR, fname)
            if os.path.isfile(fp):
                return fp
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  CORE DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════
async def download_with_ytdlp(url: str, is_audio: bool = False) -> Optional[str]:
    shortcode = _extract_shortcode(url)
    if shortcode:
        existing = _find_downloaded_file(shortcode)
        if existing:
            logger.info(f"📁 Reusing cached: {existing}")
            return existing

    cookie_file = await get_cookies()
    if not cookie_file:
        logger.error("❌ No valid cookies – login must succeed first")
        return None

    def _build_opts(cf):
        extra = (
            {
                "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio",
                                    "preferredcodec": "mp3", "preferredquality": "192"}],
            }
            if is_audio
            else {"format": "bestvideo+bestaudio/best", "merge_output_format": "mp4"}
        )
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
                filepath = (_find_downloaded_file(video_id)
                            or _find_downloaded_file(shortcode or ""))

            if filepath and os.path.exists(filepath):
                logger.info(f"✅ Download OK: {filepath}")
                return filepath
            logger.error("Download finished but file not found on disk")
            return None

        except Exception as e:
            if is_auth_error(e) and AUTO_REFRESH_COOKIES and attempt == 0:
                logger.warning(f"🔒 Auth/rate-limit (attempt {attempt+1}) – refreshing cookies ...")
                clear_old_cookies()
                await send_to_log_group(
                    text="⚠️ **Instagram Auth/Rate-Limit**\n🔄 Regenerating cookies ...\n#InstagramCookies"
                )
                new_cf = await refresh_cookies_from_browser(reason="Auth/rate-limit during download")
                if new_cf:
                    ydl_opts = _build_opts(new_cf)
                    continue
                logger.error("Cookie regen failed – cannot retry")
                return None
            logger.error(f"Download error (attempt {attempt+1}): {str(e)[:300]}")
            return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
#  METADATA  (no download)
# ══════════════════════════════════════════════════════════════════════════════
async def _fetch_info(url: str) -> Optional[dict]:
    cookie_file = await get_cookies()
    if not cookie_file:
        logger.warning("No cookies for info fetch")
        return None
    ydl_opts = get_ytdlp_opts({"skip_download": True}, use_cookie_file=cookie_file)
    loop = asyncio.get_event_loop()
    try:
        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        return await loop.run_in_executor(None, _run)
    except Exception as e:
        logger.error(f"_fetch_info: {str(e)[:300]}")
        return None

# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def startup_services():
    if not ENABLE_IG_COOKIES:
        logger.info("Instagram cookie handling disabled.")
        return

    if not IG_USERNAME or not IG_PASSWORD:
        logger.error(
            "❌ IG_USERNAME / IG_PASSWORD not set.\n"
            "   Set them as Railway environment variables."
        )
        await send_to_log_group(
            text=(
                "❌ **Instagram: Credentials Not Set**\n"
                "Set `IG_USERNAME` + `IG_PASSWORD` env vars.\n#InstagramCookies"
            )
        )
        return

    logger.info("🚀 Instagram cookie service starting ...")
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
                "⚠️ Cookie generation failed on startup.\n"
                "   Will retry on first download request.\n"
                "   PRIMARY FIX: set IG_PLAYWRIGHT_PROXY to a residential proxy."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **Instagram Startup Cookie Generation Failed**\n\n"
                    "Set `IG_PLAYWRIGHT_PROXY` to a residential proxy.\n"
                    "Will retry on first download.\n#InstagramCookies"
                )
            )
    else:
        logger.info("✅ Existing cookies valid – skipping regeneration.")

# ══════════════════════════════════════════════════════════════════════════════
#  InstagramAPI CLASS
# ══════════════════════════════════════════════════════════════════════════════
class InstagramAPI:
    def __init__(self):
        self.regex    = INSTAGRAM_REGEX
        self.base_url = "https://www.instagram.com/"

    async def valid(self, link: str) -> bool:
        return bool(re.search(self.regex, link))

    async def exists(self, link: str) -> bool:
        return await self.valid(link)

    async def info(self, url: str) -> dict:
        raw       = await _fetch_info(url)
        shortcode = _extract_shortcode(url) or ""
        if raw:
            return {
                "title":        raw.get("title") or raw.get("uploader") or "Instagram Video",
                "uploader":     raw.get("uploader") or "Unknown",
                "duration_sec": raw.get("duration") or 0,
                "duration_min": _seconds_to_min(raw.get("duration") or 0),
                "thumbnail":    raw.get("thumbnail") or "",
                "thumb":        raw.get("thumbnail") or "",
                "webpage_url":  raw.get("webpage_url") or url,
                "ext":          raw.get("ext") or "mp4",
                "id":           raw.get("id") or shortcode,
            }
        return {
            "title": "Instagram Video", "uploader": "Unknown",
            "duration_sec": 0, "duration_min": "00:00",
            "thumbnail": "", "thumb": "",
            "webpage_url": url, "ext": "mp4", "id": shortcode,
        }

    async def track(self, link: str) -> Tuple[dict, str]:
        """
        Fetch metadata for an Instagram reel / post.
        Returns (details_dict, video_id_str).
        Raises Exception on failure so the caller can surface an error message.
        """
        meta = await _fetch_info(link)
        if not meta:
            raise Exception("Could not fetch Instagram metadata")

        shortcode = _extract_shortcode(link) or meta.get("id", link)
        duration_sec = meta.get("duration") or 0

        thumb = meta.get("thumbnail") or ""
        if not thumb:
            thumbs = meta.get("thumbnails") or []
            if thumbs:
                thumb = thumbs[-1].get("url", "")

        details = {
            "title":        meta.get("title") or meta.get("uploader") or "Instagram Video",
            "link":         meta.get("webpage_url") or link,
            "vidid":        meta.get("id") or shortcode,
            "duration_min": _seconds_to_min(duration_sec),
            "duration_sec": duration_sec,
            "thumb":        thumb,
            "uploader":     meta.get("uploader") or "Instagram",
        }
        return details, details["vidid"]

    async def url(self, message_1) -> Optional[str]:
        if not PYROGRAM_AVAILABLE or message_1 is None:
            return None
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

    async def download(self, url: str, mystic=None,
                       video: Union[bool, str] = None,
                       audio: Union[bool, str] = None) -> tuple:
        try:
            if audio:
                filepath = await download_with_ytdlp(url, is_audio=True)
            else:
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
        except Exception as e:
            logger.error(f"InstagramAPI.download: {e}")
            return False, None

    async def download_audio(self, url: str) -> tuple:
        try:
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
        except Exception as e:
            logger.error(f"InstagramAPI.download_audio: {e}")
            return False, None

    async def thumbnail(self, url: str) -> str:
        return (await self.info(url))["thumb"]
