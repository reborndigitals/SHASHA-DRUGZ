import os
import re
import asyncio
import logging
import random
from os import path
from typing import Optional, Union

import aiohttp
import yt_dlp

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGER
# ══════════════════════════════════════════════════════════════════════════════
try:
    from SHASHA_DRUGZ import LOGGER
    logger = LOGGER("SHASHA_DRUGZ/platforms/Instagram.py")
except Exception:
    logger = logging.getLogger("Instagram")
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(h)
    logger.setLevel(logging.INFO)

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
INSTAGRAM_DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(INSTAGRAM_DOWNLOAD_DIR, exist_ok=True)

INSTAGRAM_COOKIES_FILE = os.path.join(os.getcwd(), "cookies", "instagram_cookies.txt")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.6099.43 Mobile Safari/537.36",
]

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
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _get_ydl_opts(extra: dict = None) -> dict:
    ua = random.choice(USER_AGENTS)
    base = {
        "outtmpl":            os.path.join(INSTAGRAM_DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet":              True,
        "no_warnings":        True,
        "geo_bypass":         True,
        "nocheckcertificate": True,
        "retries":            5,
        "fragment_retries":   5,
        "http_headers": {
            "User-Agent":      ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer":         "https://www.instagram.com/",
        },
    }
    if os.path.exists(INSTAGRAM_COOKIES_FILE):
        base["cookiefile"] = INSTAGRAM_COOKIES_FILE
        logger.debug(f"Using Instagram cookiefile: {INSTAGRAM_COOKIES_FILE}")
    if extra:
        base.update(extra)
    return base


def _find_downloaded_file(shortcode: str) -> Optional[str]:
    """Scan the downloads dir for a file whose name contains the shortcode."""
    if not shortcode:
        return None
    for fname in os.listdir(INSTAGRAM_DOWNLOAD_DIR):
        if shortcode in fname:
            fpath = os.path.join(INSTAGRAM_DOWNLOAD_DIR, fname)
            if os.path.isfile(fpath):
                return fpath
    return None


def _extract_shortcode(url: str) -> Optional[str]:
    match = SHORTCODE_REGEX.search(url)
    return match.group(1) if match else None


def _seconds_to_min(seconds: int) -> str:
    try:
        minutes = int(seconds) // 60
        secs    = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"
    except Exception:
        return "00:00"


# ══════════════════════════════════════════════════════════════════════════════
#  INSTAGRAM API CLASS
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
        Returns a dict with title, uploader, duration, thumbnail, etc.,
        or None on failure.
        """
        ydl_opts = _get_ydl_opts({"skip_download": True})
        loop = asyncio.get_event_loop()
        try:
            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, _extract)
            if not info:
                return None

            duration_sec = info.get("duration") or 0
            return {
                "title":        info.get("title")    or info.get("uploader") or "Instagram Video",
                "uploader":     info.get("uploader") or "Unknown",
                "duration_sec": duration_sec,
                "duration_min": _seconds_to_min(duration_sec),
                "thumbnail":    info.get("thumbnail") or "",
                "webpage_url":  info.get("webpage_url") or url,
                "ext":          info.get("ext") or "mp4",
                "id":           info.get("id") or _extract_shortcode(url) or "",
            }
        except Exception as e:
            logger.error(f"Instagram info extraction error: {str(e)[:300]}")
            return None

    # ── DOWNLOAD (video / reel) ───────────────────────────────────────────────
    async def download(self, url: str) -> tuple:
        """
        Download an Instagram reel, post video, or IGTV clip.

        Returns
        -------
        (track_details: dict, filepath: str)  on success
        (False, None)                          on failure

        track_details keys:
            title, uploader, duration_sec, duration_min, thumb, filepath
        """
        shortcode = _extract_shortcode(url)

        # ── Re-use already-downloaded file ────────────────────────────────────
        if shortcode:
            existing = _find_downloaded_file(shortcode)
            if existing:
                logger.info(f"📁 Reusing cached Instagram file: {existing}")
                meta = await self.info(url) or {}
                track_details = {
                    "title":        meta.get("title", "Instagram Video"),
                    "uploader":     meta.get("uploader", "Unknown"),
                    "duration_sec": meta.get("duration_sec", 0),
                    "duration_min": meta.get("duration_min", "00:00"),
                    "thumb":        meta.get("thumbnail", ""),
                    "filepath":     existing,
                }
                return track_details, existing

        ydl_opts = _get_ydl_opts({
            "format":              "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        })

        loop = asyncio.get_event_loop()
        try:
            def _do_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            info = await loop.run_in_executor(None, _do_download)
            if not info:
                logger.error("yt-dlp returned no info for Instagram URL")
                return False, None

            video_id      = info.get("id") or shortcode or ""
            duration_sec  = info.get("duration") or 0
            filepath      = None

            # Prefer the path yt-dlp resolved, fall back to scanning the dir
            if info.get("requested_downloads"):
                filepath = info["requested_downloads"][0].get("filepath")
            if not filepath or not os.path.exists(filepath):
                filepath = _find_downloaded_file(video_id) or _find_downloaded_file(shortcode or "")

            if not filepath or not os.path.exists(filepath):
                logger.error("Instagram download finished but output file not found")
                return False, None

            track_details = {
                "title":        info.get("title")    or info.get("uploader") or "Instagram Video",
                "uploader":     info.get("uploader") or "Unknown",
                "duration_sec": duration_sec,
                "duration_min": _seconds_to_min(duration_sec),
                "thumb":        info.get("thumbnail") or "",
                "filepath":     filepath,
            }
            logger.info(f"✅ Instagram download complete: {filepath}")
            return track_details, filepath

        except Exception as e:
            logger.error(f"Instagram download error: {str(e)[:300]}")
            return False, None

    # ── AUDIO-ONLY EXTRACTION ─────────────────────────────────────────────────
    async def download_audio(self, url: str) -> tuple:
        """
        Extract audio from an Instagram reel / video as mp3.

        Returns
        -------
        (track_details: dict, filepath: str)  on success
        (False, None)                          on failure
        """
        shortcode = _extract_shortcode(url)

        ydl_opts = _get_ydl_opts({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key":              "FFmpegExtractAudio",
                "preferredcodec":   "mp3",
                "preferredquality": "192",
            }],
        })

        loop = asyncio.get_event_loop()
        try:
            def _do_download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=True)

            info = await loop.run_in_executor(None, _do_download)
            if not info:
                return False, None

            video_id     = info.get("id") or shortcode or ""
            duration_sec = info.get("duration") or 0
            filepath     = None

            if info.get("requested_downloads"):
                filepath = info["requested_downloads"][0].get("filepath")
            if not filepath or not os.path.exists(filepath):
                filepath = _find_downloaded_file(video_id) or _find_downloaded_file(shortcode or "")

            if not filepath or not os.path.exists(filepath):
                logger.error("Instagram audio extraction finished but file not found")
                return False, None

            track_details = {
                "title":        info.get("title")    or info.get("uploader") or "Instagram Audio",
                "uploader":     info.get("uploader") or "Unknown",
                "duration_sec": duration_sec,
                "duration_min": _seconds_to_min(duration_sec),
                "thumb":        info.get("thumbnail") or "",
                "filepath":     filepath,
            }
            logger.info(f"✅ Instagram audio extraction complete: {filepath}")
            return track_details, filepath

        except Exception as e:
            logger.error(f"Instagram audio extraction error: {str(e)[:300]}")
            return False, None

    # ── THUMBNAIL FETCH ───────────────────────────────────────────────────────
    async def thumbnail(self, url: str) -> Optional[str]:
        """Return the thumbnail URL for an Instagram post, or None."""
        meta = await self.info(url)
        return meta.get("thumbnail") if meta else None

    # ── TRACK-STYLE HELPER (mirrors YouTube/Spotify pattern) ─────────────────
    async def track(self, url: str) -> tuple:
        """
        Return (track_details dict, video_id str) without downloading,
        matching the interface used by YouTube/Spotify/Resso helpers.
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
