# SHASHA_DRUGZ/VIPMUSIC/platforms/Instagram.py
# ══════════════════════════════════════════════════════════════
#  Instagram Platform Handler
#  Supports: Reels, Posts (video), IGTV, Stories (public)
#  Downloads via yt-dlp (same as YouTube handler uses internally)
#  Falls back to instaloader if yt-dlp fails
#
#  Usage in play.py:
#    from VIPMUSIC import Instagram
#    elif await Instagram.valid(url):
#        details, track_id = await Instagram.track(url)
# ══════════════════════════════════════════════════════════════

import os
import re
import asyncio
import time
from typing import Union

import aiohttp
import yt_dlp

# ── Optional: instaloader as fallback ────────────────────────
try:
    import instaloader
    INSTALOADER_AVAILABLE = True
except ImportError:
    INSTALOADER_AVAILABLE = False


class InstagramAPI:
    def __init__(self):
        # Matches all common Instagram video/reel/post/igtv URLs
        self.regex = (
            r"(?:https?://)?(?:www\.)?instagram\.com/"
            r"(?:p|reel|reels|tv|stories)/([A-Za-z0-9_\-]+)"
        )
        self.base = "https://www.instagram.com/"

    # ── URL Validation ────────────────────────────────────────
    async def valid(self, link: str) -> bool:
        return bool(re.search(self.regex, link))

    def _extract_shortcode(self, url: str) -> Union[str, None]:
        match = re.search(self.regex, url)
        return match.group(1) if match else None

    # ── yt-dlp options ────────────────────────────────────────
    def _ytdlp_opts(self, output_path: str, audio_only: bool = False) -> dict:
        fmt = (
            "bestaudio/best"
            if audio_only
            else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        )
        return {
            "format":            fmt,
            "outtmpl":           output_path,
            "quiet":             True,
            "no_warnings":       True,
            "noplaylist":        True,
            "geo_bypass":        True,
            "nocheckcertificate": True,
            "retries":           3,
            "socket_timeout":    30,
            "postprocessors": [
                {
                    "key":            "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }
            ] if not audio_only else [],
        }

    # ── Fetch metadata (no download) ─────────────────────────
    async def _fetch_info(self, url: str) -> Union[dict, None]:
        loop = asyncio.get_event_loop()

        def _extract():
            opts = {
                "quiet":             True,
                "no_warnings":       True,
                "noplaylist":        True,
                "skip_download":     True,
                "geo_bypass":        True,
                "nocheckcertificate": True,
                "socket_timeout":    20,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await loop.run_in_executor(None, _extract)
            return info
        except Exception:
            return None

    # ── track() — returns details dict + track_id (shortcode) ─
    async def track(
        self,
        url: str,
        playid: Union[bool, str] = None,
    ) -> tuple:
        """
        Returns:
            (track_details dict, shortcode str)

        track_details keys match YouTube.track() output so the
        existing stream() function works without modification:
            title, link, vidid, duration_min, thumb
        Also includes extra keys:
            duration_sec, platform="instagram"
        """
        if playid:
            url = self.base + url

        shortcode = self._extract_shortcode(url) or "instagram"
        info      = await self._fetch_info(url)

        if info:
            title        = info.get("title") or info.get("description") or "Instagram Video"
            # Clean up title
            title        = title[:80].strip()
            duration_sec = int(info.get("duration") or 0)
            thumbnail    = info.get("thumbnail") or ""
            uploader     = info.get("uploader") or info.get("channel") or "Instagram"
            webpage_url  = info.get("webpage_url") or url
        else:
            # Minimal fallback if yt-dlp metadata fetch fails
            title        = f"Instagram Reel — {shortcode}"
            duration_sec = 0
            thumbnail    = ""
            uploader     = "Instagram"
            webpage_url  = url

        # Format duration as MM:SS
        if duration_sec > 0:
            minutes      = duration_sec // 60
            seconds      = duration_sec % 60
            duration_min = f"{minutes:02d}:{seconds:02d}"
        else:
            duration_min = "00:00"

        track_details = {
            "title":        title,
            "link":         webpage_url,
            "vidid":        shortcode,          # used as track_id in queue
            "duration_min": duration_min,
            "duration_sec": duration_sec,
            "thumb":        thumbnail,
            "uploader":     uploader,
            "platform":     "instagram",
        }
        return track_details, shortcode

    # ── download() — mirrors YouTube.download() signature ─────
    async def download(
        self,
        shortcode_or_url: str,
        mystic=None,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
    ) -> tuple:
        """
        Downloads the Instagram video/reel.

        Returns:
            (file_path: str, direct: bool)
            direct=True  → file_path is a local path ready to stream
            direct=False → not used for Instagram (always True)

        Mirrors YouTube.download() so it can be dropped into
        the existing stream() call in play.py.
        """
        if videoid:
            url = f"https://www.instagram.com/reel/{shortcode_or_url}/"
        else:
            url = shortcode_or_url

        os.makedirs("cache", exist_ok=True)
        timestamp   = int(time.time())
        audio_only  = not video
        ext         = "mp4" if video else "m4a"
        output_path = f"cache/insta_{shortcode_or_url}_{timestamp}.%(ext)s"
        final_path  = f"cache/insta_{shortcode_or_url}_{timestamp}.{ext}"

        loop  = asyncio.get_event_loop()
        opts  = self._ytdlp_opts(output_path, audio_only=audio_only)

        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        try:
            if mystic:
                try:
                    await mystic.edit_text(
                        "⬇️ **ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ɪɴsᴛᴀɢʀᴀᴍ ᴠɪᴅᴇᴏ...**"
                    )
                except Exception:
                    pass

            await loop.run_in_executor(None, _download)

            # yt-dlp may rename the file after postprocessing
            if not os.path.exists(final_path):
                # Search for any matching file in cache/
                for f in os.listdir("cache"):
                    if f.startswith(f"insta_{shortcode_or_url}_{timestamp}"):
                        final_path = os.path.join("cache", f)
                        break

            if not os.path.exists(final_path):
                raise FileNotFoundError(f"Downloaded file not found: {final_path}")

            return final_path, True

        except Exception as e:
            # ── Fallback: instaloader ─────────────────────────
            if INSTALOADER_AVAILABLE and video:
                try:
                    result = await self._instaloader_download(url, shortcode_or_url, timestamp)
                    if result:
                        return result, True
                except Exception:
                    pass
            raise Exception(f"Instagram download failed: {e}")

    # ── instaloader fallback ──────────────────────────────────
    async def _instaloader_download(
        self, url: str, shortcode: str, timestamp: int
    ) -> Union[str, None]:
        loop = asyncio.get_event_loop()

        def _dl():
            L  = instaloader.Instaloader(
                download_videos=True,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                quiet=True,
                dirname_pattern="cache",
                filename_pattern=f"insta_{shortcode}_{timestamp}",
            )
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target="cache")
            # Find the mp4
            for f in os.listdir("cache"):
                if f.endswith(".mp4") and shortcode in f:
                    return os.path.join("cache", f)
            return None

        return await loop.run_in_executor(None, _dl)

    # ── exists() helper — mirrors YouTube.exists() ────────────
    async def exists(self, url: str) -> bool:
        return await self.valid(url)

    # ── details() — for playlist/queue compatibility ──────────
    async def details(self, url: str, fetch: bool = True) -> tuple:
        """
        Lightweight wrapper used by stream() playlist loop.
        Returns: (title, duration_min, duration_sec, thumbnail, vidid)
        """
        track_details, vidid = await self.track(url)
        return (
            track_details["title"],
            track_details["duration_min"],
            track_details["duration_sec"],
            track_details["thumb"],
            vidid,
        )
