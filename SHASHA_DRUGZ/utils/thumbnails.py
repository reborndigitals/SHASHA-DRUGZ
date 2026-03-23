# SHASHA_DRUGZ/utils/thumbnails.py
import os
import re
from io import BytesIO
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch
from config import YOUTUBE_IMG_URL

# Constants
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

THUMP_LOGO = "SHASHA_DRUGZ/assets/thumb.png"

PANEL_W, PANEL_H = 763, 545
PANEL_X = (1280 - PANEL_W) // 2
PANEL_Y = 88
TRANSPARENCY = 170
INNER_OFFSET = 36

THUMB_W, THUMB_H = 542, 273
THUMB_X = PANEL_X + (PANEL_W - THUMB_W) // 2
THUMB_Y = PANEL_Y + INNER_OFFSET

TITLE_X = 377
META_X = 377
TITLE_Y = THUMB_Y + THUMB_H + 10
META_Y = TITLE_Y + 45

BAR_X, BAR_Y = 388, META_Y + 45
BAR_RED_LEN = 280
BAR_TOTAL_LEN = 480

ICONS_W, ICONS_H = 415, 45
ICONS_X = PANEL_X + (PANEL_W - ICONS_W) // 2
ICONS_Y = BAR_Y + 48

MAX_TITLE_WIDTH = 580


def trim_to_width(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    ellipsis = "…"
    try:
        if font.getlength(text) <= max_w:
            return text
    except Exception:
        # fallback if getlength not available
        if font.getsize(text)[0] <= max_w:
            return text
    for i in range(len(text) - 1, 0, -1):
        try:
            if font.getlength(text[:i] + ellipsis) <= max_w:
                return text[:i] + ellipsis
        except Exception:
            if font.getsize(text[:i] + ellipsis)[0] <= max_w:
                return text[:i] + ellipsis
    return ellipsis


async def get_thumb(videoid: str) -> str:
    cache_path = os.path.join(CACHE_DIR, f"{videoid}_v4.png")
    # If you want to force refresh during debugging, uncomment next line
    # if os.path.exists(cache_path): os.remove(cache_path)
    if os.path.exists(cache_path):
        return cache_path

    # Fetch YouTube details via VideosSearch
    results = VideosSearch(f"https://www.youtube.com/watch?v={videoid}", limit=1)
    try:
        results_data = await results.next()
        result_items = results_data.get("result", [])
        if not result_items:
            raise ValueError("No results found.")
        data = result_items[0]
        title = re.sub(r"\W+", " ", data.get("title", "Unsupported Title")).strip().title()
        thumb_url = data.get("thumbnails", [{}])[0].get("url", YOUTUBE_IMG_URL)
        thumbnail = thumb_url.split("?")[0] if thumb_url else YOUTUBE_IMG_URL
        duration = data.get("duration")
        views = data.get("viewCount", {}).get("short", "Unknown Views")
    except Exception:
        title, thumbnail, duration, views = (
            "Unsupported Title",
            YOUTUBE_IMG_URL,
            None,
            "Unknown Views",
        )

    is_live = not duration or str(duration).strip().lower() in {"", "live", "live now"}
    duration_text = "Live" if is_live else duration or "Unknown Mins"

    # Download thumbnail to temporary thumb_path
    thumb_path = os.path.join(CACHE_DIR, f"thumb{videoid}.png")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    async with aiofiles.open(thumb_path, "wb") as f:
                        await f.write(await resp.read())
                else:
                    # fallback to default image URL or stop
                    thumb_path = None
    except Exception:
        thumb_path = None

    # If download failed, return a default image URL (or a local default)
    if not thumb_path or not os.path.exists(thumb_path):
        return YOUTUBE_IMG_URL

    # Base image (resize to 1280x720)
    base = Image.open(thumb_path).resize((1280, 720)).convert("RGBA")
    bg = ImageEnhance.Brightness(base.filter(ImageFilter.BoxBlur(10))).enhance(0.6)

    # Frosted glass panel
    panel_area = bg.crop((PANEL_X, PANEL_Y, PANEL_X + PANEL_W, PANEL_Y + PANEL_H))
    overlay = Image.new("RGBA", (PANEL_W, PANEL_H), (255, 255, 255, TRANSPARENCY))
    frosted = Image.alpha_composite(panel_area, overlay)

    mask = Image.new("L", (PANEL_W, PANEL_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, PANEL_W, PANEL_H), 50, fill=255)
    bg.paste(frosted, (PANEL_X, PANEL_Y), mask)

    draw = ImageDraw.Draw(bg)

    # Fonts - try expected path first, fallback to load_default
    try:
        title_font = ImageFont.truetype("SHASHA_DRUGZ/assets/font2.ttf", 32)
        regular_font = ImageFont.truetype("SHASHA_DRUGZ/assets/font.ttf", 18)
    except OSError:
        try:
            title_font = ImageFont.truetype("SHASHA_DRUGZ/assets/DejaVuSans-Bold.ttf", 26)
            regular_font = ImageFont.truetype("SHASHA_DRUGZ/assets/DejaVuSans.ttf", 16)
        except Exception:
            title_font = regular_font = ImageFont.load_default()

    # Thumbnail with rounding
    thumb = base.resize((THUMB_W, THUMB_H)).convert("RGBA")
    tmask = Image.new("L", (THUMB_W, THUMB_H), 0)
    ImageDraw.Draw(tmask).rounded_rectangle((0, 0, THUMB_W, THUMB_H), 20, fill=255) 
    bg.paste(thumb, (THUMB_X, THUMB_Y), tmask)

    # Texts
    draw.text((TITLE_X, TITLE_Y), trim_to_width(title, title_font, MAX_TITLE_WIDTH), fill="black", font=title_font)
    draw.text((META_X, META_Y), f"YouTube | {views}", fill="black", font=regular_font)

    # Progress bar
    draw.line([(BAR_X, BAR_Y), (BAR_X + BAR_RED_LEN, BAR_Y)], fill="red", width=6)
    draw.line([(BAR_X + BAR_RED_LEN, BAR_Y), (BAR_X + BAR_TOTAL_LEN, BAR_Y)], fill="gray", width=5)
    draw.ellipse([(BAR_X + BAR_RED_LEN - 7, BAR_Y - 7), (BAR_X + BAR_RED_LEN + 7, BAR_Y + 7)], fill="red")

    draw.text((BAR_X, BAR_Y + 15), "00:00", fill="black", font=regular_font)
    end_text = "Live" if is_live else duration_text
    draw.text((BAR_X + BAR_TOTAL_LEN - (90 if is_live else 60), BAR_Y + 15), end_text,
              fill="red" if is_live else "black", font=regular_font)

    # Icons
    icons_path = "SHASHA_DRUGZ/assets/play_icons.png"
    if os.path.isfile(icons_path):
        try:
            ic = Image.open(icons_path).resize((ICONS_W, ICONS_H)).convert("RGBA")
            # convert icon to black silhouette preserving alpha
            r, g, b, a = ic.split()
            black_ic = Image.merge("RGBA", (r.point(lambda *_: 0), g.point(lambda *_: 0), b.point(lambda *_: 0), a))
            bg.paste(black_ic, (ICONS_X, ICONS_Y), black_ic)
        except Exception:
            pass

    # Watermark text + logo
    try:
        watermark_font = ImageFont.truetype("SHASHA_DRUGZ/assets/Sprintura_Demo.otf", 14)
    except Exception:
        watermark_font = ImageFont.load_default()

    watermark_text = "MadeBy. @ HeartBeat_Offi"
    try:
        text_w, text_h = draw.textsize(watermark_text, font=watermark_font)
    except Exception:
        text_w, text_h = watermark_font.getsize(watermark_text)

    # Bottom center outside panel
    x = (bg.width // 2) - (text_w // 2)
    y = PANEL_Y + PANEL_H + 25  # 25px below panel

    # sample brightness under watermark area
    try:
        sample = bg.crop((x, y, x + 50, y + 50)).convert("L")
        brightness = sum(sample.getdata()) / (50 * 50)
    except Exception:
        brightness = 200

    if brightness < 128:
        main_color = (255, 255, 255, 240)
        glow_color = (0, 0, 0, 180)
    else:
        main_color = (0, 0, 0, 240)
        glow_color = (255, 255, 255, 180)

    glow_positions = [(x + dx, y + dy) for dx in (-1, 1) for dy in (-1, 1)]
    for pos in glow_positions:
        draw.text(pos, watermark_text, font=watermark_font, fill=glow_color)

    draw.text((x, y), watermark_text, font=watermark_font, fill=main_color)

    # Download watermark logo and paste # Watermark logo (local file or URL)
    try:
        logo_img = None
        if os.path.isfile(THUMP_LOGO):
            # Local file
            logo_img = Image.open(THUMP_LOGO).convert("RGBA")
        else:  # URL Download
            async with aiohttp.ClientSession() as session:
                async with session.get(THUMP_LOGO) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        logo_img = Image.open(BytesIO(data)).convert("RGBA")

        if logo_img:
            logo_img = logo_img.resize((60, 60))
            bg.paste(logo_img, (x - 80, y - 20), logo_img)  # center-left

    except Exception as e:
        print("WM logo paste err:", e)

    # Cleanup temp
    try:
        os.remove(thumb_path)
    except Exception:
        pass

    # Save final
    bg.save(cache_path)
    return cache_path


    # Cleanup temp
    try:
        os.remove(thumb_path)
    except Exception:
        pass

    # Save final
    bg.save(cache_path)
    return cache_path
