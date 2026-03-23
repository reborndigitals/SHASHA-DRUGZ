# SHASHA_DRUGZ/platforms/ytdatabase.py

import os
import datetime
import logging
from typing import Optional, Dict

from pyrogram.types import Message
from SHASHA_DRUGZ import app, LOGGER
from SHASHA_DRUGZ.platforms.Youtube import YouTubeAPI

# ========= CONFIG =========
DATABASE_SONGS = int(os.getenv("DATABASE_SONGS", "-1003440828193"))

# ========= LOGGER =========
def get_logger(name: str):
    try:
        return LOGGER(name)
    except Exception:
        log = logging.getLogger(name)
        if not log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            log.addHandler(handler)
        log.setLevel(logging.INFO)
        return log

logger = get_logger("HeartBeat/platforms/ytdatabase.py")


class YTDatabase:

    def __init__(self):
        self.yt = YouTubeAPI()
        self.runtime_cache: Dict[str, dict] = {}

    # --------------------------------------------------
    # SEARCH TELEGRAM GROUP FOR EXISTING FILE
    # --------------------------------------------------
    async def search_in_group(self, vidid: str):
        """
        Search DATABASE_SONGS group using vidid.
        """

        if vidid in self.runtime_cache:
            return self.runtime_cache[vidid]

        try:
            async for msg in app.search_messages(
                chat_id=DATABASE_SONGS,
                query=vidid,
                limit=3
            ):
                if not msg.caption:
                    continue

                if vidid in msg.caption:

                    data = {
                        "audio_file_id": msg.audio.file_id if msg.audio else None,
                        "video_file_id": msg.video.file_id if msg.video else None,
                        "message_id": msg.id
                    }

                    self.runtime_cache[vidid] = data
                    logger.info(f"⚡ Found cached media in group for {vidid}")
                    return data

        except Exception as e:
            logger.error(f"Search error: {e}")

        return None

    # --------------------------------------------------
    # CAPTION BUILDER
    # --------------------------------------------------
    def build_caption(self, details: dict, media_type: str) -> str:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        return (
            f"🎵 **YouTube {media_type.upper()} Stored**\n\n"
            f"**Title:** {details['title']}\n"
            f"**Duration:** {details['duration_min']}\n"
            f"**YouTube ID:** `{details['vidid']}`\n"
            f"**Source:** {details['link']}\n\n"
            f"**Uploaded At:** {now}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"#YT_DATABASE\n\n@HeartBeat_Fam | @HeartBeat_Offi"
        )

    # --------------------------------------------------
    # MAIN HANDLER
    # --------------------------------------------------
    async def handle_upload(
        self,
        link: str,
        file_path: Optional[str] = None,
        media_type: str = "audio"  # audio or video
    ):
        """
        Returns:
            Telegram file_id
        """

        details, vidid = await self.yt.track(link)

        # 1️⃣ Check Telegram Group First
        existing = await self.search_in_group(vidid)

        if existing:
            logger.info(f"⚡ Using existing file_id for {vidid}")
            return existing.get(f"{media_type}_file_id")

        # 2️⃣ Upload New Media
        if not file_path:
            logger.error("No file path provided for upload")
            return None

        caption = self.build_caption(details, media_type)

        if media_type == "audio":
            msg = await app.send_audio(
                chat_id=DATABASE_SONGS,
                audio=file_path,
                caption=caption,
                title=details["title"],
                duration=0
            )
            file_id = msg.audio.file_id

        else:
            msg = await app.send_video(
                chat_id=DATABASE_SONGS,
                video=file_path,
                caption=caption,
            )
            file_id = msg.video.file_id

        # 3️⃣ Store in Runtime Cache
        self.runtime_cache[vidid] = {
            "audio_file_id": msg.audio.file_id if msg.audio else None,
            "video_file_id": msg.video.file_id if msg.video else None,
            "message_id": msg.id
        }

        logger.info(f"✅ Stored {media_type.upper()} in DATABASE_SONGS: {vidid}")

        return file_id


# ========= GLOBAL INSTANCE =========
yt_database = YTDatabase()
