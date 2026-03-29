import os
import re
import glob
import time
import shutil
import random
import asyncio
import logging
import datetime
from typing import Optional
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

DOWNLOAD_DIR   = os.path.join(os.getcwd(), "downloads");      os.makedirs(DOWNLOAD_DIR,   exist_ok=True)
COOKIES_DIR    = os.path.join(os.getcwd(), "cookies");        os.makedirs(COOKIES_DIR,    exist_ok=True)
COOKIE_FILE    = os.path.join(COOKIES_DIR, "instagram_cookies.txt")
IG_PROFILE_DIR = os.path.join(os.getcwd(), "ig_playwright_profile"); os.makedirs(IG_PROFILE_DIR, exist_ok=True)
IG_CACHE_DIR   = os.path.join(os.getcwd(), "igcache");        os.makedirs(IG_CACHE_DIR,   exist_ok=True)
SCREENSHOT_DIR = os.path.join(os.getcwd(), "ig_screenshots"); os.makedirs(SCREENSHOT_DIR, exist_ok=True)

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

def is_instagram_url(url: str) -> bool:
    """
    Hard domain check.  Must be called before any processing.

    Root cause of the reported bug:
      https://www.instagram.com/reel/DV6J4yQNjIA/ was being passed to
      Youtube.py because the shortcode 'DV6J4yQNjIA' is 11 chars and
      looks identical to a YouTube video ID.  This guard ensures the
      'instagram.com' domain is always verified before routing.
    """
    if not url:
        return False
    clean = url.lower().split("?")[0].split("#")[0]
    return "instagram.com" in clean

# ══════════════════════════════════════════════════════════════════════════════
#  USER-AGENT POOL
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
        logger.info(f"📸 Screenshot sent: {path}")
    except Exception as e:
        logger.error(f"_send_screenshot: {e}")

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
#  COOKIE / PROFILE CLEANUP
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
            try:
                os.remove(fpath)
            except Exception:
                pass

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
            path    = c.get("path", "/")
            secure  = "TRUE" if c.get("secure", False) else "FALSE"
            exp_raw = c.get("expires", -1)
            expires = int(exp_raw) if exp_raw and exp_raw > 0 else 0
            lines.append(f"{domain}\tTRUE\t{path}\t{secure}\t{expires}\t{name}\t{value}")
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
  Object.defineProperty(navigator, 'webdriver', { get: () => false, configurable: true });
  try { delete navigator.__proto__.webdriver; } catch(e) {}
  const _plugins = [
    {name:'Chrome PDF Plugin',  filename:'internal-pdf-viewer', description:'Portable Document Format'},
    {name:'Chrome PDF Viewer',  filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
    {name:'Native Client',      filename:'internal-nacl-plugin', description:''},
  ];
  Object.defineProperty(navigator, 'plugins', {
    get: () => Object.assign(_plugins, {
      length: _plugins.length,
      item: (i) => _plugins[i] ?? null,
      namedItem: (n) => _plugins.find(p => p.name === n) ?? null,
      refresh: () => {},
    }),
  });
  Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
  window.chrome = {
    app: { isInstalled: false },
    runtime: {},
    loadTimes: () => ({}),
    csi: () => ({}),
  };
  const _origPerms = navigator.permissions?.query?.bind(navigator.permissions);
  if (_origPerms) {
    navigator.permissions.query = (p) =>
      p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origPerms(p);
  }
  Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
  Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8 });
  Object.defineProperty(navigator, 'maxTouchPoints',      { get: () => 0 });
  Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
  Object.defineProperty(screen, 'pixelDepth', { get: () => 24 });
  const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
    const ctx = this.getContext('2d');
    if (ctx && this.width > 0 && this.height > 0) {
      const img = ctx.getImageData(0, 0, this.width, this.height);
      for (let i = 0; i < img.data.length; i += 4) {
        img.data[i]   = Math.min(255, img.data[i]   + (Math.random() * 2 - 1));
        img.data[i+1] = Math.min(255, img.data[i+1] + (Math.random() * 2 - 1));
        img.data[i+2] = Math.min(255, img.data[i+2] + (Math.random() * 2 - 1));
      }
      ctx.putImageData(img, 0, 0);
    }
    return _toDataURL.apply(this, arguments);
  };
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
        logger.info(f"📍 [{label}] URL   : {url}\n            Title : {title}")
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
    for desc, sel in [
        ("save login",    "button:has-text('Save info'), button:has-text('Save Info')"),
        ("not now",       "button:has-text('Not now'), button:has-text('Not Now')"),
        ("notifications", "button:has-text('Turn On')"),
    ]:
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
        logger.warning(f"_human_type fallback: {e}")
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
        logger.error(f"🚨 Checkpoint: {page.url}")
        return True
    try:
        body = (await page.inner_text("body")).lower()
        if any(s in body for s in ("verify your account", "verify it's you",
                                    "we detected an unusual", "complete a security check")):
            logger.error(f"🚨 Checkpoint via text: {page.url}")
            return True
    except Exception:
        pass
    return False

async def _check_for_2fa(page) -> str:
    try:
        url = page.url.lower()
        if "two_factor" in url or "2fa" in url or "checkpoint" in url:
            body = (await page.inner_text("body")).lower()
            if "text message" in body or "sms" in body or "phone number" in body:
                return "sms"
            return "totp"
        inp = page.locator(
            "input[name='verificationCode'], "
            "input[aria-label*='Security Code'], "
            "input[aria-label*='Confirmation Code'], "
            "input[placeholder*='6-digit'], "
            "input[placeholder*='security code']"
        )
        if await inp.count() > 0:
            body = (await page.inner_text("body")).lower()
            return "sms" if ("text message" in body or "sms" in body) else "totp"
    except Exception as e:
        logger.debug(f"_check_for_2fa: {e}")
    return "none"

async def _handle_2fa(page) -> bool:
    fa = await _check_for_2fa(page)
    if fa == "none":
        return True
    if fa == "sms":
        logger.error("🔒 SMS 2FA – cannot automate")
        await send_to_log_group(text="🔒 **Instagram SMS 2FA – Cannot Automate**\n#2FA")
        return False
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
        logger.info(f"🔑 TOTP: {code}")
        inp = page.locator(
            "input[name='verificationCode'], "
            "input[aria-label*='Security Code'], "
            "input[placeholder*='6-digit'], "
            "input[placeholder*='security code']"
        )
        if await inp.count() == 0:
            logger.error("❌ TOTP input not found")
            return False
        await inp.first.fill(code)
        await page.wait_for_timeout(random.randint(500, 900))
        btn = page.locator("button[type='submit'], button:has-text('Confirm')")
        if await btn.count() > 0:
            await btn.first.click()
        else:
            await inp.first.press("Enter")
        await page.wait_for_timeout(5000)
        return True
    except Exception as e:
        logger.error(f"_handle_2fa: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════
async def _verify_login(context, page) -> bool:
    try:
        all_c = await context.cookies()
        names = {c["name"] for c in all_c if "instagram.com" in c.get("domain", "")}
        found = names & {"sessionid", "ds_user_id", "rur"}
        url   = page.url
        title = await page.title()
        logger.info(
            f"🔍 Login verification:\n"
            f"   URL          : {url}\n"
            f"   Title        : {title}\n"
            f"   All cookies  : {names}\n"
            f"   Auth cookies : {found or 'NONE ← failed'}"
        )
        if found:
            return True
        if ("instagram.com" in url and "login" not in url.lower()
                and "accounts" not in url.lower()
                and "sessionid" in str(all_c).lower()):
            return True
        return False
    except Exception as e:
        logger.error(f"_verify_login: {e}")
        return False

# ══════════════════════════════════════════════════════════════════════════════
#  WAIT FOR LOGIN RESULT
# ══════════════════════════════════════════════════════════════════════════════
async def _wait_for_login_result(page, timeout_ms: int = 18_000) -> str:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        await page.wait_for_timeout(800)
        url = page.url.lower()
        if "login" not in url and "accounts" not in url and "instagram.com" in url:
            return "success"
        if "two_factor" in url or "2fa" in url:
            return "2fa"
        if "challenge" in url or "checkpoint" in url:
            return "checkpoint"
        try:
            body = (await page.inner_text("body")).lower()
            if any(s in body for s in (
                "sorry, your password was incorrect",
                "the password you entered is incorrect",
                "incorrect password", "wrong password",
            )):
                logger.error("❌ Wrong password")
                return "wrong_password"
            if any(s in body for s in (
                "there was an unusual login attempt",
                "we detected an unusual login",
            )):
                return "checkpoint"
        except Exception:
            pass
    return "timeout"

# ══════════════════════════════════════════════════════════════════════════════
#  FILL AND SUBMIT
# ══════════════════════════════════════════════════════════════════════════════
async def _fill_and_submit(page, context) -> bool:
    username_input = None
    for sel in [
        "input[name='username']",
        "input[aria-label='Phone number, username, or email']",
        "input[aria-label*='username']",
        "input[type='text']",
    ]:
        try:
            await page.wait_for_selector(sel, timeout=10_000, state="visible")
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                username_input = el.first
                logger.info(f"✅ username field: {sel}")
                break
        except Exception:
            continue

    if not username_input:
        logger.error("❌ username field not found")
        return False

    password_input = None
    for sel in ["input[name='password']", "input[type='password']", "input[aria-label='Password']"]:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                password_input = el.first
                logger.info(f"✅ password field: {sel}")
                break
        except Exception:
            continue

    if not password_input:
        logger.error("❌ password field not found")
        return False

    logger.info(f"✍️  Entering username: {IG_USERNAME}")
    await _human_type(page, username_input, IG_USERNAME)
    await page.wait_for_timeout(random.randint(400, 900))

    logger.info("✍️  Entering password")
    await _human_type(page, password_input, IG_PASSWORD)
    await page.wait_for_timeout(random.randint(600, 1100))

    submit_btn = None
    for sel in ["button[type='submit']", "button:has-text('Log in')", "button:has-text('Log In')"]:
        try:
            el = page.locator(sel)
            if await el.count() > 0 and await el.first.is_visible():
                submit_btn = el.first
                break
        except Exception:
            continue

    if submit_btn:
        await submit_btn.click()
        logger.info("🖱️  Submit clicked")
    else:
        await password_input.press("Enter")
        logger.info("🖱️  Enter pressed")

    result = await _wait_for_login_result(page)
    logger.info(f"📊 Login result: {result}")

    if result == "wrong_password":
        await send_to_log_group(
            text=(
                f"❌ **Instagram: Wrong Password**\n"
                f"👤 Account : `{IG_USERNAME}`\n"
                f"Fix: update `IG_PASSWORD` env var.\n#InstagramCookies"
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

    return await _verify_login(context, page)

# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN PATHS
# ══════════════════════════════════════════════════════════════════════════════
async def _try_classic_login(page, context) -> bool:
    logger.info("🔐 Classic login: /accounts/login/")
    try:
        await page.goto(
            "https://www.instagram.com/accounts/login/",
            wait_until="domcontentloaded", timeout=45_000,
        )
        await page.wait_for_timeout(random.randint(6000, 9000))
    except Exception as e:
        logger.warning(f"Classic goto: {e}")
        await page.wait_for_timeout(6000)
    bl = await _body_len(page)
    logger.info(f"📄 Login page body: {bl} chars")
    if bl < 200:
        shot = await _log_page_state(page, "blank_classic_login")
        await _send_screenshot(shot, "🚨 **IG: Blank login page (classic)**")
        return False
    return await _fill_and_submit(page, context)

async def _try_classic_login_on_current_page(page, context) -> bool:
    logger.info("🔐 Classic login: already on page")
    bl = await _body_len(page)
    if bl < 200:
        shot = await _log_page_state(page, "blank_click_nav")
        await _send_screenshot(shot, "🚨 **IG: Blank page after click**")
        return False
    return await _fill_and_submit(page, context)

async def _try_mobile_login(page, context) -> bool:
    logger.info("📱 Mobile login path")
    try:
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(
            "https://www.instagram.com/accounts/login/?source=auth_switcher",
            wait_until="domcontentloaded", timeout=45_000,
        )
        await page.wait_for_timeout(random.randint(5000, 7500))
        bl = await _body_len(page)
        if bl < 200:
            logger.error("❌ Mobile login page blank")
            return False
        try:
            cb = page.locator("button:has-text('Allow all cookies'), button:has-text('Accept All')")
            if await cb.count() > 0:
                await cb.first.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass
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
        f"   Proxy       : {choose_random_proxy(IG_PLAYWRIGHT_PROXY_POOL) or 'none'}"
    )
    await send_to_log_group(
        text=f"🌐 **Instagram – Generating Cookies**\n📝 {reason}\n⏳ Launching ...\n#InstagramCookies"
    )
    wipe_playwright_profile()
    proxy      = choose_random_proxy(IG_PLAYWRIGHT_PROXY_POOL)
    user_agent = random.choice(USER_AGENTS)
    context    = None

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                IG_PROFILE_DIR,
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars", "--disable-extensions",
                    "--disable-gpu", "--window-size=1920,1080",
                    "--start-maximized", "--lang=en-US",
                    "--disable-automation", "--no-first-run",
                    "--no-default-browser-check", "--disable-default-apps",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-client-side-phishing-detection",
                    "--disable-hang-monitor", "--disable-popup-blocking",
                    "--disable-prompt-on-repost", "--disable-sync",
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
            logger.info("🔗 Step 1/4 – Warming up ...")
            try:
                await page.goto("https://www.instagram.com/",
                                wait_until="domcontentloaded", timeout=45_000)
                await page.wait_for_timeout(random.randint(3000, 5000))
                for sel in [
                    "[data-testid='cookie-policy-manage-dialog-accept-button']",
                    "button:has-text('Allow all cookies')",
                    "button:has-text('Accept All')",
                ]:
                    try:
                        btn = page.locator(sel)
                        if await btn.count() > 0 and await btn.first.is_visible():
                            await btn.first.click()
                            logger.info(f"✅ Cookie consent: {sel}")
                            await page.wait_for_timeout(random.randint(1500, 2500))
                            break
                    except Exception:
                        pass
                await _log_page_state(page, "step1_homepage")
                await page.mouse.move(random.randint(200, 800), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(600, 1400))
                await page.mouse.wheel(0, random.randint(100, 400))
                await page.wait_for_timeout(random.randint(1000, 2500))
            except Exception as e:
                logger.warning(f"Warmup non-fatal: {e}")

            # ── Step 2: Login ─────────────────────────────────────────────────
            logger.info(f"🔗 Step 2/4 – Logging in as: {IG_USERNAME} ...")
            login_clicked = False
            try:
                link = page.locator(
                    "a[href='/accounts/login/'], a:has-text('Log in'), a:has-text('Log In')"
                )
                if await link.count() > 0:
                    await link.first.click()
                    await page.wait_for_timeout(random.randint(4000, 6500))
                    logger.info(f"✅ Navigated via click → {page.url}")
                    login_clicked = True
            except Exception as e:
                logger.warning(f"Click-to-login: {e}")

            login_ok = False
            try:
                if login_clicked and "login" in page.url.lower():
                    login_ok = await _try_classic_login_on_current_page(page, context)
                else:
                    login_ok = await _try_classic_login(page, context)
            except Exception as e:
                logger.warning(f"Classic login exception: {e}")

            if not login_ok:
                logger.warning("⚠️ Classic failed – trying mobile ...")
                try:
                    login_ok = await _try_mobile_login(page, context)
                except Exception as e:
                    logger.warning(f"Mobile login exception: {e}")

            # ── Post-login checks ─────────────────────────────────────────────
            if login_ok and await _check_for_checkpoint(page):
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
                    "   Fixes:\n"
                    "   1. Set IG_PLAYWRIGHT_PROXY (residential proxy)\n"
                    "   2. Verify IG_PASSWORD env var\n"
                    "   3. Disable SMS 2FA on the account\n"
                    "   4. Log in manually once via browser to unlock"
                )
                shot = await _log_page_state(page, "step2_login_failed")
                await _send_screenshot(shot, "❌ **IG: Login Failed**")
                await send_to_log_group(
                    text=(
                        f"❌ **Instagram Login FAILED**\n"
                        f"👤 `{IG_USERNAME}`\n"
                        f"Fixes: residential proxy / correct password / disable SMS 2FA\n"
                        f"#InstagramCookies"
                    )
                )
                await context.close()
                context = None
                return False

            # ── Step 3: Natural browsing ──────────────────────────────────────
            logger.info("🔗 Step 3/4 – Natural browsing ...")
            try:
                await page.goto("https://www.instagram.com/",
                                wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(random.randint(2000, 4000))
                await page.mouse.move(random.randint(100, 600), random.randint(100, 400))
                await page.wait_for_timeout(random.randint(500, 1200))
                await page.mouse.wheel(0, random.randint(200, 600))
                await page.wait_for_timeout(random.randint(1000, 2000))
                await _log_page_state(page, "step3_feed")
            except Exception as e:
                logger.debug(f"Natural browsing non-fatal: {e}")

            # ── Step 4: Export cookies ────────────────────────────────────────
            logger.info("🔗 Step 4/4 – Exporting cookies ...")
            all_cookies = await context.cookies()
            await context.close()
            context     = None

            ig_cookies   = [c for c in all_cookies
                            if "instagram.com" in c.get("domain", "")
                            or "facebook.com"  in c.get("domain", "")]
            cookie_names = {c["name"] for c in ig_cookies}
            auth_present = {"sessionid", "ds_user_id"} & cookie_names
            logger.info(f"🍪 {len(ig_cookies)} cookies | auth: {auth_present or 'NONE'}")

            if not auth_present:
                logger.error("❌ sessionid/ds_user_id missing – NOT saving cookies")
                return False

            ok = _write_netscape_cookies(ig_cookies, COOKIE_FILE)
            if ok:
                logger.info(f"✅ Cookies saved | auth={auth_present} | total={len(ig_cookies)}")
            return ok

    except Exception as e:
        logger.error(f"❌ Playwright crashed: {type(e).__name__}: {str(e)[:400]}")
        if context:
            try:
                pages = context.pages
                if pages:
                    shot = await _log_page_state(pages[-1], "fatal_crash")
                    await _send_screenshot(shot, f"❌ **IG: Crashed**\n`{str(e)[:200]}`")
                await context.close()
            except Exception:
                pass
        await send_to_log_group(
            text=f"❌ **Instagram Browser Crashed**\n📝 {reason}\n⚠️ `{str(e)[:300]}`\n#InstagramCookies"
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
            logger.info("✅ Cookies already fresh – reusing")
            return COOKIE_FILE

        ok = await generate_cookies_via_playwright(reason=reason)
        if not ok or not os.path.exists(COOKIE_FILE):
            logger.error("Cookie generation failed")
            return None

        if not verify_cookies_file(COOKIE_FILE):
            logger.error("Cookie file failed verification")
            if os.path.exists(COOKIE_FILE):
                os.remove(COOKIE_FILE)
            return None

        if is_cookie_file_expired(COOKIE_FILE):
            logger.error("Cookie expired immediately")
            return None

        logger.info("✅ Cookies verified")
        ip = await get_public_ip_info()
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        await send_to_log_group(
            text=(
                f"🌐 **Instagram Cookies Ready**\n"
                f"📅 Time : `{ts}`\n"
                f"🌍 IP   : `{ip.get('ip','unknown')}`\n"
                f"📍 {ip.get('city','?')}, {ip.get('country','?')}\n"
                f"📝 {reason}\n#InstagramCookies"
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
        found_auth = [c for c in ("sessionid", "ds_user_id") if c in content]
        if not found_auth:
            logger.error("❌ No auth cookies (sessionid/ds_user_id)")
            return False
        if content.strip().startswith("{") or '"domain"' in content:
            logger.error("Cookie file is JSON not Netscape")
            return False
        valid = sum(
            1 for line in content.strip().split("\n")
            if line and not line.startswith("#") and "\t" in line
        )
        if valid < 2:
            logger.error(f"Too few valid lines: {valid}")
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
        logger.info(f"🕐 Expired at {datetime.datetime.utcfromtimestamp(min_exp).isoformat()}Z")
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
        "rate limit", "rate-limit", "http error 401", "http error 403",
        "unable to extract", "cookie", "sign in",
        "authentication", "access denied", "forbidden",
        "bad credentials", "challenge required", "content is not available",
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
    reason = "Force refresh" if force_refresh else "Initial / expired"
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
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.instagram.com/",
            "Origin":          "https://www.instagram.com",
        },
    }
    if use_cookie_file and os.path.exists(use_cookie_file):
        base["cookiefile"] = use_cookie_file
    else:
        logger.warning("No Instagram cookie file for yt-dlp")
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
    # Hard domain guard — reject non-Instagram URLs at module boundary
    if not is_instagram_url(url):
        logger.error(
            f"❌ Rejected non-Instagram URL: {url}\n"
            f"   This module only handles instagram.com links."
        )
        return None

    shortcode = _extract_shortcode(url)
    if shortcode:
        existing = _find_downloaded_file(shortcode)
        if existing:
            logger.info(f"📁 Reusing cached: {existing}")
            return existing

    cookie_file = await get_cookies()
    if not cookie_file:
        logger.error("❌ No valid Instagram cookies – login must succeed first")
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
                filepath = (
                    _find_downloaded_file(video_id)
                    or _find_downloaded_file(shortcode or "")
                )
            if filepath and os.path.exists(filepath):
                logger.info(f"✅ Instagram download OK: {filepath}")
                return filepath
            logger.error("Download finished but file not found on disk")
            return None

        except Exception as e:
            if is_auth_error(e) and AUTO_REFRESH_COOKIES and attempt == 0:
                logger.warning("🔒 Auth/rate-limit – refreshing cookies ...")
                clear_old_cookies()
                await send_to_log_group(
                    text="⚠️ **Instagram Auth/Rate-Limit**\n🔄 Regenerating ...\n#InstagramCookies"
                )
                new_cf = await refresh_cookies_from_browser(reason="Auth/rate-limit during download")
                if new_cf:
                    ydl_opts = _build_opts(new_cf)
                    continue
                logger.error("Cookie regen failed")
                return None
            logger.error(f"Download error (attempt {attempt+1}): {str(e)[:300]}")
            return None

    return None

# ══════════════════════════════════════════════════════════════════════════════
#  METADATA  (no download)
# ══════════════════════════════════════════════════════════════════════════════
async def _fetch_info(url: str) -> Optional[dict]:
    if not is_instagram_url(url):
        logger.error(f"❌ _fetch_info: not Instagram: {url}")
        return None
    cookie_file = await get_cookies()
    if not cookie_file:
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
        logger.error("❌ IG_USERNAME / IG_PASSWORD not set")
        await send_to_log_group(
            text="❌ **Instagram: Set IG_USERNAME + IG_PASSWORD**\n#InstagramCookies"
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
                "⚠️ Startup cookie generation failed.\n"
                "   PRIMARY FIX: set IG_PLAYWRIGHT_PROXY to a residential proxy."
            )
            await send_to_log_group(
                text=(
                    "⚠️ **Instagram Startup Failed**\n"
                    "Set `IG_PLAYWRIGHT_PROXY` (residential proxy).\n#InstagramCookies"
                )
            )
    else:
        logger.info("✅ Existing cookies valid.")

# ══════════════════════════════════════════════════════════════════════════════
#  InstagramAPI CLASS
# ══════════════════════════════════════════════════════════════════════════════
class InstagramAPI:
    def __init__(self):
        self.regex    = INSTAGRAM_REGEX
        self.base_url = "https://www.instagram.com/"

    async def valid(self, link: str) -> bool:
        """Returns True only for genuine instagram.com URLs."""
        return is_instagram_url(link) and bool(re.search(self.regex, link))

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

    async def download(self, url: str) -> tuple:
        if not await self.valid(url):
            logger.error(f"❌ Not an Instagram URL: {url}")
            return False, None
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
        if not await self.valid(url):
            logger.error(f"❌ Not an Instagram URL: {url}")
            return False, None
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
        return (await self.info(url))["thumb"]

    async def track(self, url: str) -> tuple:
        meta = await self.info(url)
        return {
            "title":        meta["title"],
            "link":         meta["webpage_url"],
            "vidid":        meta["id"],
            "duration_min": meta["duration_min"],
            "thumb":        meta["thumb"],
        }, meta["id"]
