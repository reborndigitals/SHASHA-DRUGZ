from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from SHASHA_DRUGZ.utils.shasha_font import Fonts
from SHASHA_DRUGZ import app

print("[fonts] font")

@Client.on_message(filters.command(["font", "fonts"]))
async def style_buttons(c, m, cb=False):
    # ✅ Prevent crash if no text is provided
    if len(m.command) < 2:
        return await m.reply_text(
            "❍ Please provide some text to stylize.\n\nExample:\n`/fonts Hello world!`"
        )

    text = m.text.split(' ', 1)[1]

    buttons = [
        [
            InlineKeyboardButton("𝚃𝚢𝚙𝚎𝚠𝚛𝚒𝚝𝚎𝚛", callback_data="style+typewriter"),
            InlineKeyboardButton("𝕆𝕦𝕥𝕝𝕚𝕟𝕖", callback_data="style+outline"),
            InlineKeyboardButton("𝐒𝐞𝐫𝐢𝐟", callback_data="style+serif"),
        ],
        [
            InlineKeyboardButton("𝑺𝒆𝒓𝒊𝒇", callback_data="style+bold_cool"),
            InlineKeyboardButton("𝑆𝑒𝑟𝑖𝑓", callback_data="style+cool"),
            InlineKeyboardButton("Sᴍᴀʟʟ Cᴀᴘs", callback_data="style+small_cap"),
        ],
        [
            InlineKeyboardButton("𝓈𝒸𝓇𝒾𝓅𝓉", callback_data="style+script"),
            InlineKeyboardButton("𝓼𝓬𝓻𝓲𝓹𝓽", callback_data="style+script_bolt"),
            InlineKeyboardButton("ᵗⁱⁿʸ", callback_data="style+tiny"),
        ],
        [
            InlineKeyboardButton("ᑕOᗰIᑕ", callback_data="style+comic"),
            InlineKeyboardButton("𝗦𝗮𝗻𝘀", callback_data="style+sans"),
            InlineKeyboardButton("𝙎𝙖𝙣𝙨", callback_data="style+slant_sans"),
        ],
        [
            InlineKeyboardButton("𝘚𝘢𝘯𝘴", callback_data="style+slant"),
            InlineKeyboardButton("𝖲𝖺𝗇𝗌", callback_data="style+sim"),
            InlineKeyboardButton("Ⓒ︎Ⓘ︎Ⓡ︎Ⓒ︎Ⓛ︎Ⓔ︎Ⓢ︎", callback_data="style+circles"),
        ],
        [
            InlineKeyboardButton("🅒︎🅘︎🅡︎🅒︎🅛︎🅔︎🅢︎", callback_data="style+circle_dark"),
            InlineKeyboardButton("𝔊𝔬𝔱𝔥𝔦𝔠", callback_data="style+gothic"),
            InlineKeyboardButton("𝕲𝖔𝖙𝖍𝖎𝖈", callback_data="style+gothic_bolt"),
        ],
        [
            InlineKeyboardButton("C͜͡l͜͡o͜͡u͜͡d͜͡s͜͡", callback_data="style+cloud"),
            InlineKeyboardButton("H̆̈ă̈p̆̈p̆̈y̆̈", callback_data="style+happy"),
            InlineKeyboardButton("S̑̈ȃ̈d̑̈", callback_data="style+sad"),
        ],
        [
            InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close_reply"),
            InlineKeyboardButton("ɴᴇxᴛ ➻", callback_data="nxt"),
        ],
    ]

    if not cb:
        await m.reply_text(
            f"`{text}`", reply_markup=InlineKeyboardMarkup(buttons), quote=True
        )
    else:
        await m.answer()
        await m.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("^nxt"))
async def nxt(c, m):
    if m.data == "nxt":
        buttons = [
            [
                InlineKeyboardButton("🇸 🇵 🇪 🇨 🇮 🇦 🇱 ", callback_data="style+special"),
                InlineKeyboardButton("🅂🅀🅄🄰🅁🄴🅂", callback_data="style+squares"),
                InlineKeyboardButton("🆂︎🆀︎🆄︎🅰︎🆁︎🅴︎🆂︎", callback_data="style+squares_bold"),
            ],
            [
                InlineKeyboardButton("ꪖꪀᦔꪖꪶꪊᥴ𝓲ꪖ", callback_data="style+andalucia"),
                InlineKeyboardButton("爪卂几ᘜ卂", callback_data="style+manga"),
                InlineKeyboardButton("S̾t̾i̾n̾k̾y̾", callback_data="style+stinky"),
            ],
            [
                InlineKeyboardButton("B̥ͦu̥ͦb̥ͦb̥ͦl̥ͦe̥ͦs̥ͦ", callback_data="style+bubbles"),
                InlineKeyboardButton("U͟n͟d͟e͟r͟l͟i͟n͟e͟", callback_data="style+underline"),
                InlineKeyboardButton("꒒ꍏꀷꌩꌃꀎꁅ", callback_data="style+ladybug"),
            ],
            [
                InlineKeyboardButton("R҉a҉y҉s҉", callback_data="style+rays"),
                InlineKeyboardButton("B҈i҈r҈d҈s҈", callback_data="style+birds"),
                InlineKeyboardButton("S̸l̸a̸s̸h̸", callback_data="style+slash"),
            ],
            [
                InlineKeyboardButton("s⃠t⃠o⃠p⃠", callback_data="style+stop"),
                InlineKeyboardButton("S̺͆k̺͆y̺͆l̺͆i̺͆n̺͆e̺͆", callback_data="style+skyline"),
                InlineKeyboardButton("A͎r͎r͎o͎w͎s͎", callback_data="style+arrows"),
            ],
            [
                InlineKeyboardButton("ዪሀክቿነ", callback_data="style+qvnes"),
                InlineKeyboardButton("S̶t̶r̶i̶k̶e̶", callback_data="style+strike"),
                InlineKeyboardButton("F༙r༙o༙z༙e༙n༙", callback_data="style+frozen"),
            ],
            [
                InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close_reply"),
                InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="nxt+0"),
            ],
        ]
        await m.answer()
        await m.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
    else:
        await style_buttons(c, m, cb=True)


@Client.on_callback_query(filters.regex("^style"))
async def style(c, m):
    await m.answer()
    _, style = m.data.split('+', 1)

    # ✅ Get font function safely
    cls = getattr(Fonts, style, None)
    if not cls:
        return await m.message.reply_text("⚠️ Unknown font style selected!")

    # ✅ Ensure the message is a reply with text
    if not m.message.reply_to_message or not m.message.reply_to_message.text:
        return await m.message.reply_text("❍ Please reply to a text message to stylize it!")

    text = m.message.reply_to_message.text
    new_text = cls(text)

    try:
        await m.message.edit_text(new_text, reply_markup=m.message.reply_markup)
    except Exception:
        pass

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_17"
__help__ = """
🔻 /fonts <text> ➠ Converts normal text into multiple beautiful stylish fonts.
"""
MOD_TYPE = "TOOLS"
MOD_NAME = "Fonts"
MOD_PRICE = "50"
