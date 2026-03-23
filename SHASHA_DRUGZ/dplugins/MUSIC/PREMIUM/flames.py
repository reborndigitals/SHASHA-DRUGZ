import random
import io
import os
import requests
from SHASHA_DRUGZ import app
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageStat
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatType

print("[flames] flames, match")

# --- FLAMES RESULT CONFIG ---
RESULTS = {
    "F": {
        "title": "💛 𝐅ʀɪᴇɴᴅ𝗌",
        "title_cap": "Friends",
        "desc": "A strong bond filled with laughter, trust, and memories. You two are perfect as friends forever! 🤝",
        "image_url": [
            "https://files.catbox.moe/cvstcx.jpg",
            "https://files.catbox.moe/boonda.jpg",
            "https://files.catbox.moe/fwppcq.jpg",
            "https://files.catbox.moe/xq3j81.jpg",
            "https://files.catbox.moe/iqqef4.jpg"
        ],
        "images": [f"SHASHA_DRUGZ/assets/flames/friends/{i}.jpg" for i in range(1, 6)]
    },
    "L": {
        "title": "❤️ 𝐋ᴏᴠᴇ",
        "title_cap": "Love",
        "desc": "There’s a spark and magic between you both — a true love story is forming! 💞",
        "image_url": [
            "https://i.imgur.com/4eAOSDq.jpeg",
            "https://i.imgur.com/4eAOSDq.jpeg",
            "https://i.imgur.com/4eAOSDq.jpeg"
        ],
        "images": [f"SHASHA_DRUGZ/assets/flames/love/{i}.jpg" for i in range(1, 6)]
    },
    "A": {
        "title": "💖 𝐀ғғᴇᴄᴛɪᴏɴ",
        "title_cap": "Affection",
        "desc": "You both care deeply for each other — gentle hearts and pure emotion bloom! 🌸",
        "image_url": [
            "https://i.imgur.com/4eAOSDq.jpeg",
            "https://i.imgur.com/4eAOSDq.jpeg",
            "https://i.imgur.com/4eAOSDq.jpeg"
        ],
        "images": [f"SHASHA_DRUGZ/assets/flames/affection/{i}.jpg" for i in range(1, 6)]
    },
    "M": {
        "title": "💍 𝐌ᴀʀʀɪᴀɢᴇ",
        "title_cap": "Marriage",
        "desc": "Destiny has already written your names together — a wedding bell symphony awaits! 💫",
        "image_url": [
            "https://files.catbox.moe/z4x6zw.jpg",
            "https://files.catbox.moe/nkau4y.jpg",
            "https://files.catbox.moe/hv79i3.jpg",
            "https://files.catbox.moe/cbcn50.jpg",
            ],
        "images": [f"SHASHA_DRUGZ/assets/flames/marriage/{i}.jpg" for i in range(1, 6)]
    },
    "E": {
        "title": "💔 𝐄ɴᴇᴍʏ",
        "title_cap": "Enemy",
        "desc": "Clashing energies and fiery tempers — maybe not meant to be this time 😅",
        "image_url": [
            "https://files.catbox.moe/otx3hc.jpg",
            "https://files.catbox.moe/s1fz6q.jpg",
            "https://files.catbox.moe/rfqnd4.jpg",
            "https://files.catbox.moe/7yz7mr.jpg",
            "https://files.catbox.moe/gub3ue.jpg"
        ],
        "images": [f"SHASHA_DRUGZ/assets/flames/enemy/{i}.jpg" for i in range(1, 6)]
    },
    "S": {
        "title": "💜 𝐒ɪʙʟɪɴɢ𝗌",
        "title_cap": "Siblings",
        "desc": "You both share a sibling-like connection — teasing, caring, and protective 💫",
        "image_url": [
            "https://files.catbox.moe/uf5fvm.jpg",
            "https://files.catbox.moe/06cypv.jpg",
            "https://files.catbox.moe/gy210f.jpg",
            "https://files.catbox.moe/5ho82n.jpg",
            ],
        "images": [f"SHASHA_DRUGZ/assets/flames/siblings/{i}.jpg" for i in range(1, 6)]
    }
}


# --- FLAMES LOGIC ---
def flames_result(name1, name2):
    n1, n2 = name1.replace(" ", "").lower(), name2.replace(" ", "").lower()
    for letter in n1:
        if letter in n2:
            n1 = n1.replace(letter, "", 1)
            n2 = n2.replace(letter, "", 1)
    combined = n1 + n2
    count = len(combined)
    flames = list("FLAMES")
    while len(flames) > 1:
        index = (count % len(flames)) - 1
        if index >= 0:
            flames = flames[index + 1:] + flames[:index]
        else:
            flames = flames[:-1]
    return flames[0]


# --- CREATE POSTER ---
def make_poster(image_url, name1, name2, title_cap, percentage):
    try:
        bg = None

        # --- Try URL first ---
        if image_url and image_url.startswith(("http://", "https://")):
            try:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                bg = Image.open(io.BytesIO(response.content)).convert("RGB")
            except Exception as e:
                print(f"[FLAMES] URL image failed: {e}")

        # --- If URL invalid or failed, fallback to local folder ---
        if bg is None:
            folder_path = f"SHASHA_DRUGZ/assets/flames/{title_cap.lower()}"
            if os.path.exists(folder_path):
                local_images = [
                    os.path.join(folder_path, f)
                    for f in os.listdir(folder_path)
                    if f.lower().endswith((".jpg", ".jpeg", ".png"))
                ]
                if local_images:
                    bg_path = random.choice(local_images)
                    bg = Image.open(bg_path).convert("RGB")
                    print(f"[FLAMES] Using fallback image: {bg_path}")
            if bg is None:
                bg = Image.new("RGB", (900, 600), (255, 192, 203))

        # --- Resize and blur ---
        bg = bg.resize((900, 600)).filter(ImageFilter.GaussianBlur(4))
        
        # --- Dark vignette effect ---
        shadow = Image.new("L", bg.size, 0)
        draw_shadow = ImageDraw.Draw(shadow)
        max_dim = max(bg.size)
        for i in range(int(max_dim / 2)):
            intensity = int(255 * (i / (max_dim / 2)))
            draw_shadow.ellipse(
                (i - 200, i - 200, bg.size[0] - i + 200, bg.size[1] - i + 200),
                fill=intensity
            )
        shadow = shadow.filter(ImageFilter.GaussianBlur(100))
        shadow_mask = ImageEnhance.Brightness(shadow).enhance(0.8)
        bg.paste((0, 0, 0), mask=shadow_mask)
        
        # --- Brightness adjust ---
        stat = ImageStat.Stat(bg)
        brightness = sum(stat.mean[:3]) / 3
        if brightness > 160:
            bg = ImageEnhance.Brightness(bg).enhance(0.8)
            text_color = "white"
        elif brightness < 90:
            bg = ImageEnhance.Brightness(bg).enhance(1.3)
            text_color = "white"
        else:
            text_color = "black" if brightness > 130 else "white"

        draw = ImageDraw.Draw(bg)

        # --- Load fonts ---
        try:
            font_title = ImageFont.truetype("SHASHA_DRUGZ/assets/Astroz Trial.ttf", 80)
            font_text = ImageFont.truetype("SHASHA_DRUGZ/assets/Sprintura Demo.otf", 35)
            font_small = ImageFont.truetype("SHASHA_DRUGZ/assets/Bilderberg Italic OTF.otf", 60)
            font_fancy = ImageFont.truetype("SHASHA_DRUGZ/assets/Rostex-Regular.ttf", 15)
        except Exception as e:
            print(f"[FLAMES] Font load failed: {e}")
            font_title = font_text = font_small = font_fancy = ImageFont.load_default()

        def safe_text(text):
            return text.encode("ascii", "ignore").decode("ascii")

        def draw_centered_text(y, text, font=None, max_width=850):
            text = safe_text(str(text))
            fnt = font or ImageFont.load_default()
            w, h = draw.textsize(text, font=fnt)
            while w > max_width and hasattr(fnt, "path") and fnt.size > 15:
                fnt = ImageFont.truetype(fnt.path, fnt.size - 2)
                w, h = draw.textsize(text, font=fnt)
            x = (900 - w) / 2
            shadow_color = (0, 0, 0, 180) if text_color == "white" else (255, 255, 255, 180)
            for ox, oy in [(-3, -3), (-3, 3), (3, -3), (3, 3)]:
                draw.text((x + ox, y + oy), text, font=fnt, fill=shadow_color)
            draw.text((x, y), text, fill=text_color, font=fnt)

        # --- Draw texts on poster ---
        draw_centered_text(40, "F L A M E S", font_title)
        draw_centered_text(150, f"{name1.title()} x {name2.title()}\n", font_small)
        draw_centered_text(310, f"{title_cap}", font_text)
        draw_centered_text(350, f"Compatibility: {percentage}%", font_text)
        draw_centered_text(530, "Made By x @ H e a r t B e a t _ F a m", font_fancy)

        # --- Output image ---
        bio = io.BytesIO()
        bio.name = "flames_result.jpg"
        bg.save(bio, "JPEG")
        bio.seek(0)
        return bio

    except Exception as e:
        print(f"[FLAMES ERROR] Poster generation failed: {e}")
        raise


# --- EMOJI BAR ---
def emoji_bar(percent):
    full = int(percent / 20)
    return "★" * full + "✩" * (5 - full)


# --- /FLAMES COMMAND ---
@Client.on_message(filters.command("flames"))
async def flames_command(client, message):
    try:
        args = message.text.split(None, 2)
        if len(args) < 3:
            await message.reply_text("✨ Usage: `/flames Name1 Name2`", quote=True)
            return

        name1, name2 = args[1], args[2]
        result_letter = flames_result(name1, name2)
        result = RESULTS[result_letter]

        love = random.randint(60, 100) if result_letter in "LAM" else random.randint(10, 70)
        emotion = random.randint(60, 100)
        fun = random.randint(50, 100)
        communication = random.randint(50, 100)
        trust = random.randint(60, 100)

        # --- Random image (URL or local) ---
        image_source = random.choice(result["image_url"] + result["images"])
        poster = make_poster(image_source, name1, name2, result["title_cap"], love)

        caption = (
            f"<blockquote>          {result['title']}</blockquote>\n"
            f"<blockquote>✧══════•❁♡︎❁•══════✧\n**{name1.title()} ❣️ {name2.title()}**\n✧══════•❁♡︎❁•══════✧\n</blockquote>"
            f"<blockquote>💞 𝐂ᴏᴍᴘᴀᴛɪʙɪʟɪᴛʏ: **{love}%**\n       {emoji_bar(love)}\n"
            f"💓 𝐄ᴍᴏᴛɪᴏɴᴀʟ𝐁ᴏɴᴅ: **{emotion}%**\n       {emoji_bar(emotion)}\n"
            f"🤞🏻 𝐅ᴜɴ𝐋ᴇᴠᴇʟ: **{fun}%**\n       {emoji_bar(fun)}\n"
            f"✨ 𝐂ᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ: **{communication}%**\n       {emoji_bar(communication)}\n"
            f"💯 𝐓ʀᴜsᴛ: **{trust}%**\n       {emoji_bar(trust)}</blockquote>\n"
            f"<blockquote>🔥 {result['desc']}</blockquote>\n"
            f"<blockquote> 𝐁ᴇ𝗌ᴛ 𝐌ᴀᴛᴄʜᴇ𝗌 🚀 /match</blockquote>"
        )

        buttons = InlineKeyboardMarkup([
            [
                #InlineKeyboardButton("🔻ᴛʀʏ ᴀɢᴀɪɴ🔻", callback_data="flames_retry"),
                #InlineKeyboardButton("🔻 sʜᴀʀᴇ 🔻", switch_inline_query="flames love test"),
            #],
            #[
                InlineKeyboardButton("🔻ᴠɪᴇᴡ ᴀʟʟ🔻", callback_data="flames_list")
            ]
        ])

        await message.reply_photo(photo=poster, caption=caption, reply_markup=buttons)

    except Exception as e:
        await message.reply_text(f"⚠️ Error: {e}")



# --- /MATCH COMMAND ---
@Client.on_message(filters.command("match"))
async def match_command(client, message):
    try:
        if message.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP, "supergroup", "group"):
            await message.reply_text("❌ This command only works in groups!", quote=True)
            return

        user = message.from_user
        members = []
        async for member in client.get_chat_members(message.chat.id):
            if not member.user.is_bot and member.user.id != user.id:
                members.append(member.user)
            if len(members) >= 50:
                break

        if len(members) < 3:
            await message.reply_text("⚠️ Not enough members in this group to match!", quote=True)
            return

        selected = random.sample(members, 3)

        text = (
            f"<blockquote>🎯 **𝐓ᴏᴘ 3 𝐌ᴀᴛᴄʜᴇs 𝐅ᴏʀ\n"
            f"[{user.first_name}](tg://user?id={user.id})** 💘</blockquote>\n"
        )

        for idx, member in enumerate(selected, start=1):
            name = member.first_name or "Unknown"
            uid = member.id
            tag = f"[{name}](tg://user?id={uid})"
            result_letter = random.choice(list(RESULTS.keys()))
            result = RESULTS[result_letter]
            percent = random.randint(50, 100)

            alert = (
                "💞 **Perfect Couple Alert!** 💞"
                if percent >= 85 and result_letter in ["L", "S", "M"]
                else ""
            )

            text += (
                f"<blockquote>{idx}. {tag} → {result['title']} ({percent}%)\n"
                f"{emoji_bar(percent)}\n"
                f"📝 {result['desc']}\n{alert}</blockquote>\n"
            )

        # --- Choose random image safely ---
        all_images = [
            img for res in RESULTS.values() for img in res["image_url"] if img
        ]
        image_url = random.choice(all_images)

        # Convert local paths to absolute ones
        if not image_url.startswith(("http://", "https://")):
            image_url = os.path.abspath(image_url)

        await message.reply_photo(
            photo=image_url,
            caption=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔻 ᴛʀʏ ᴀɢᴀɪɴ 🔻", callback_data="match_retry")]
            ])
        )

    except Exception as e:
        await message.reply_text(f"⚠️ Error: {e}")


# --- CALLBACKS ---
@Client.on_callback_query(filters.regex("^flames_"))
async def callback_handler(client, cq):
    try:
        if cq.data == "flames_retry":
            await cq.answer("✨ Type /flames Name1 Name2 again to try another match!", show_alert=False)
        elif cq.data == "flames_list":
            await cq.message.reply_text(
                "📜 **FLAMES Meaning:**\n\n"
                "💛 F - Friendship\n"
                "❤️ L - Love\n"
                "💖 A - Affection\n"
                "💍 M - Marriage\n"
                "💔 E - Enemy\n"
                "💜 S - Sibling\n",
                quote=True
            )
            await cq.answer()
    except Exception as e:
        await cq.answer(f"⚠️ Callback Error: {e}", show_alert=True)
        


__menu__ = "CMD_MENTION"
__mod_name__ = "H_B_33"
__help__ = """
🔻 /flames <Name1> <Name2> ➠ ᴄʀᴇᴀᴛᴇ ᴀ ғᴜɴ ʜᴏᴛ ᴘᴏsᴛᴇʀ ᴀɴᴅ sʜᴏᴡ ғʟᴀᴍᴇs ʀᴇsᴜʟᴛ ᴡɪᴛʜ ᴄᴏᴍᴘᴀᴛɪʙɪʟɪᴛʏ
🔻 /match ➠ ᴘɪᴄᴋ ʀᴀɴᴅᴏᴍ ᴍᴇᴍʙᴇʀs ɪɴ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇᴠᴀʟᴜᴀᴛᴇ ᴛʜᴇɪʀ ғʟᴀᴍᴇs ᴄᴏᴍᴘᴀᴛɪʙɪʟɪᴛʏ
"""

MOD_TYPE = "TOOLS"
MOD_NAME = "Flames"
MOD_PRICE = "50"
