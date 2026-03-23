import asyncio
import uuid
import html
import chess
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.core.mongo import mongodb

# ================= CONFIG =================
EDIT_MODE = True
TOTAL_TIME = 600
START_ELO = 1000
ELO_GAIN = 20
AUTO_ROTATE_DEFAULT = False

BOT_USERNAME = getattr(app, "username", None) or getattr(app.me, "username", "")
GROUP_LINK = f"https://t.me/{BOT_USERNAME}?startgroup=true"

leaderboard = mongodb.leaderboard
groupboard = mongodb.groupboard

# ================= STORAGE =================
GAMES = {}  # game_id -> game data

PIECES = {
    "P": "♙", "R": "♖", "N": "♘", "B": "♗", "Q": "♕", "K": "♔",
    "p": "♟", "r": "♜", "n": "♞", "b": "♝", "q": "♛", "k": "♚",
}

# ================= UTILS =================
def square_name(row, col):
    return chess.square(col, 7 - row)


def mention(uid, name):
    safe_name = html.escape(name)
    return f'<a href="tg://user?id={uid}">{safe_name}</a>'


def get_name(user):
    return user.first_name or "Unknown"


def current_player(game):
    return game["white"] if game["board"].turn else game["black"]


def leaderboard_badge(rank: int):
    if rank == 1:
        return "🥇 <b>ᴄʜᴀᴍᴘɪᴏɴ</b>"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    return ""


def render_board(game_id, board, selected=None, legal=None, flip=False, auto_rotate=False):
    kb = []
    for r in range(8):
        row = []
        for c in range(8):
            rr, cc = (7 - r, 7 - c) if flip else (r, c)
            sq = square_name(rr, cc)
            piece = board.piece_at(sq)
            text = PIECES.get(piece.symbol(), "·") if piece else "·"

            if selected == sq:
                text = f"[{text}]"
            elif legal and sq in legal:
                text = "⭕"

            row.append(
                InlineKeyboardButton(text, callback_data=f"s:{game_id}:{sq}")
            )
        kb.append(row)

    kb.append([
        InlineKeyboardButton("🤝 ᴅʀᴀᴡ", callback_data=f"draw:{game_id}"),
        InlineKeyboardButton("🏳 ʀᴇsɪɢɴ", callback_data=f"resign:{game_id}")
    ])

    rotate_text = "🔄 ᴀᴜᴛᴏ-ʀᴏᴛᴀᴛᴇ: ᴏɴ" if auto_rotate else "🔄 ᴀᴜᴛᴏ-ʀᴏᴛᴀᴛᴇ: ᴏғғ"
    kb.append([
        InlineKeyboardButton(rotate_text, callback_data=f"rot:{game_id}")
    ])

    return InlineKeyboardMarkup(kb)


@Client.on_message(filters.command("chesstop"))
async def leaderboard_menu(_, m):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 ᴏᴠᴇʀᴀʟʟ ᴛᴏᴘ 10", callback_data="lb:overall")],
        [InlineKeyboardButton("👥 ɢʀᴏᴜᴘ ᴛᴏᴘ 10", callback_data="lb:group")]
    ])
    await m.reply_text("<blockquote>📊 ᴄʜᴇss ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</blockquote>", reply_markup=kb)


@Client.on_message(filters.command("chessgame") & filters.group)
async def newgame(_, m):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("♔ ᴡʜɪᴛᴇ", callback_data="color:white"),
         InlineKeyboardButton("♚ ʙʟᴀᴄᴋ", callback_data="color:black")]
    ])
    await m.reply_text("Choose your color:", reply_markup=kb)


@Client.on_message(filters.command("chessplaying") & filters.group)
async def list_games(_, m):
    cid = m.chat.id
    rows = []

    for gid, g in GAMES.items():
        if g["chat"] != cid:
            continue
        w = g["white"]
        b = g["black"]
        rows.append(
            f"• <code>{gid}</code> – "
            f"{'Waiting' if not w else mention(w, 'White')} vs "
            f"{'Waiting' if not b else mention(b, 'Black')}"
        )

    if not rows:
        return await m.reply_text("No active games")

    await m.reply_text(
        "<blockquote>♟ <b>ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇs</b></blockquote>\n\n" + "\n".join(rows),
        disable_web_page_preview=True,
        #parse_mode=enums.ParseMode.HTML
    )


# ================= CALLBACKS =================
@Client.on_callback_query(filters.regex(r"^(s:|join:|color:|rot:|draw:|resign:|rematch:|lb:)"))
async def callbacks(_, q: CallbackQuery):
    cid = q.message.chat.id
    uid = q.from_user.id
    data = q.data

    # Leaderboard overall
    if data == "lb:overall":
        text = "<blockquote>🏆 <b>ᴏᴠᴇʀᴀʟʟ ᴛᴏᴘ 10</b></blockquote>\n\n"
        cursor = leaderboard.find().sort("wins", -1).limit(10)
        i = 1
        async for u in cursor:
            badge = leaderboard_badge(i)
            text += (
                f"<blockquote>"
                f"{i}. {mention(u['uid'], u['name'])} "
                f"{badge} — {u.get('wins',0)} ᴡɪɴs"
                f"</blockquote>\n"
            )
            i += 1

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 ɢʀᴏᴜᴘ ᴛᴏᴘ 10", callback_data="lb:group")],
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data="home")]
        ])
        return await q.message.edit_text(
            text or "No data",
            reply_markup=kb,
            disable_web_page_preview=True,
            #parse_mode=enums.ParseMode.HTML
        )

    # Leaderboard group
    if data == "lb:group":
        text = "<blockquote>👥 <b>ɢʀᴏᴜᴘ ᴛᴏᴘ 10</b></blockquote>\n\n"
        cursor = groupboard.find({"chat": cid}).sort("wins", -1).limit(10)
        found = False
        i = 1
        async for u in cursor:
            found = True
            badge = leaderboard_badge(i)
            text += (
                f"<blockquote>"
                f"{i}. {mention(u['uid'], u['name'])} "
                f"{badge} — {u.get('wins',0)} wins"
                f"</blockquote>\n"
            )
            i += 1

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 ᴏᴠᴇʀᴀʟʟ ᴛᴏᴘ 10", callback_data="lb:overall")],
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data="home")]
        ])
        return await q.message.edit_text(
            text if found else "ɴᴏ ɢᴀᴍᴇs ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ ʏᴇᴛ",
            reply_markup=kb,
            disable_web_page_preview=True,
            #parse_mode=enums.ParseMode.HTML
        )

    # Color selection
    if data.startswith("color:"):
        color = data.split(":")[1]
        game_id = str(uuid.uuid4())[:8]

        GAMES[game_id] = {
            "chat": cid,
            "board": chess.Board(),
            "white": uid if color == "white" else None,
            "black": uid if color == "black" else None,
            "selected": None,
            "started": False,
            "clock": {},
            "board_msg_id": None,
            "rotate": AUTO_ROTATE_DEFAULT
        }

        await q.message.reply_text(
            f"<blockquote>ɢᴀᴍᴇ <code>{game_id}</code> ᴄʀᴇᴀᴛᴇᴅ</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ᴊᴏɪɴ ɢᴀᴍᴇ", callback_data=f"join:{game_id}")]
            ]),
            #parse_mode=enums.ParseMode.HTML
        )
        return

    # Join game
    if data.startswith("join:"):
        game_id = data.split(":")[1]
        g = GAMES.get(game_id)
        if not g or g["started"]:
            return

        if g["white"] is None:
            g["white"] = uid
        elif g["black"] is None:
            g["black"] = uid

        if g["white"] and g["black"]:
            g["started"] = True
            g["clock"] = {g["white"]: TOTAL_TIME, g["black"]: TOTAL_TIME}
            asyncio.create_task(timer_task(game_id))
            await send_board(q.message, game_id)
        return

    # Toggle auto-rotate
    if data.startswith("rot:"):
        game_id = data.split(":")[1]
        g = GAMES.get(game_id)
        if not g:
            return
        if uid not in (g["white"], g["black"]):
            return await q.answer("<blockquote>ᴏɴʟʏ ᴘʟᴀʏᴇʀs ᴄᴀɴ ᴄʜᴀɴɢᴇ sᴇᴛᴛɪɴɢs</blockquote>", show_alert=True)

        g["rotate"] = not g["rotate"]
        await send_board(q.message, game_id)
        await q.answer(f"Auto-Rotate: {'ON' if g['rotate'] else 'OFF'}")
        return

    # Game actions (resign, draw, move)
    if ":" in data:
        action, game_id, *rest = data.split(":")
        g = GAMES.get(game_id)
        if not g:
            return

        if uid not in (g["white"], g["black"]):
            return await q.answer("sᴘᴇᴄᴛᴀᴛᴏʀ ᴍᴏᴅᴇ", show_alert=True)

        if uid != current_player(g):
            return await q.answer("ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ", show_alert=True)

        board = g["board"]

        if action == "resign":
            winner = g["black"] if uid == g["white"] else g["white"]
            await end_game(game_id, winner, "Resigned", q.message)
            return

        if action == "draw":
            await end_game(game_id, None, "Draw", q.message)
            return

        if action == "s":
            sq = int(rest[0])
            if g["selected"] is None:
                piece = board.piece_at(sq)
                if piece and piece.color == board.turn:
                    g["selected"] = sq
                    legal = [m.to_square for m in board.legal_moves if m.from_square == sq]
                    should_flip = (not board.turn) if g["rotate"] else False
                    try:
                        await q.message.edit_reply_markup(
                            render_board(game_id, board, sq, legal, should_flip, g["rotate"])
                        )
                    except:
                        pass
            else:
                move = chess.Move(g["selected"], sq)
                g["selected"] = None
                if move in board.legal_moves:
                    board.push(move)
                await send_board(q.message, game_id)

    # Rematch
    if data.startswith("rematch:"):
        old_game_id = data.split(":")[1]
        new_game_id = str(uuid.uuid4())[:8]

        GAMES[new_game_id] = {
            "chat": cid,
            "board": chess.Board(),
            "white": uid,
            "black": None,
            "selected": None,
            "started": False,
            "clock": {},
            "board_msg_id": None,
            "rotate": AUTO_ROTATE_DEFAULT
        }

        await q.message.reply_text(
            f"<blockquote>🔁 ʀᴇᴍᴀᴛᴄʜ ᴄʀᴇᴀᴛᴇᴅ (<code>{new_game_id}</code>)</blockquote>\n<blockquote>ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴏᴘᴘᴏɴᴇɴᴛ...</blockquote>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ᴊᴏɪɴ ʀᴇᴍᴀᴛᴄʜ", callback_data=f"join:{new_game_id}")]
            ]),
            #parse_mode=enums.ParseMode.HTML
        )
        return


# ================= TIMER TASK =================
async def timer_task(game_id):
    while game_id in GAMES:
        await asyncio.sleep(1)
        g = GAMES.get(game_id)
        if not g or not g["started"]:
            return

        uid = current_player(g)
        g["clock"][uid] -= 1

        # Send warnings at 60 and 10 seconds
        if g["clock"][uid] in (60, 10):
            try:
                await app.send_message(g["chat"], f"<blockquote>⏰ {g['clock'][uid]} sᴇᴄᴏɴᴅs ʟᴇғᴛ!</blockquote>")
            except:
                pass

        if g["clock"][uid] <= 0:
            winner = g["black"] if uid == g["white"] else g["white"]
            await end_game(game_id, winner, "Time Out", None)
            return


# ================= END GAME & ELO =================
async def end_game(game_id, winner_uid, reason, msg):
    g = GAMES.get(game_id)
    if not g:
        return
    cid = g["chat"]

    for uid in (g["white"], g["black"]):
        try:
            user = await app.get_users(uid)
            name = get_name(user)
        except:
            name = "Unknown"

        delta = 0
        if winner_uid:
            delta = ELO_GAIN if uid == winner_uid else -ELO_GAIN

        # Update overall leaderboard
        await leaderboard.update_one(
            {"uid": uid},
            {
                "$set": {"name": name},
                "$inc": {
                    "elo": START_ELO + delta if uid == winner_uid and delta > 0 else delta,
                    "wins": 1 if uid == winner_uid else 0
                }
            },
            upsert=True
        )

        # Update group leaderboard
        await groupboard.update_one(
            {"uid": uid, "chat": cid},
            {
                "$set": {"name": name},
                "$inc": {
                    "elo": START_ELO + delta if uid == winner_uid and delta > 0 else delta,
                    "wins": 1 if uid == winner_uid else 0
                }
            },
            upsert=True
        )

    # Announce result
    if winner_uid:
        try:
            user = await app.get_users(winner_uid)
            winner_name = mention(winner_uid, get_name(user))
        except:
            winner_name = "Unknown"

        text = f"<blockquote>🏆 {reason}\nᴡɪɴɴᴇʀ: {winner_name}</blockquote>"

        if msg:
            try:
                await msg.reply_text(text, disable_web_page_preview=True)
            except:
                pass
        else:
            try:
                await app.send_message(cid, text, disable_web_page_preview=True)
            except:
                pass
    else:
        try:
            await app.send_message(cid, "<blockquote>🤝 ɢᴀᴍᴇ ᴇɴᴅᴇᴅ ɪɴ ᴀ ᴅʀᴀᴡ</blockquote>")
        except:
            pass

    # Remove game from memory
    GAMES.pop(game_id, None)


# ================= SEND/UPDATE BOARD =================
async def send_board(msg, game_id):
    g = GAMES.get(game_id)
    if not g:
        return
    b = g["board"]

    text = (
        f"<blockquote>⏱ ᴡʜɪᴛᴇ: {g['clock'][g['white']]}s | "
        f"ʙʟᴀᴄᴋ: {g['clock'][g['black']]}s\n</blockquote>"
        f"<blockquote>ᴛᴜʀɴ: {'White' if b.turn else 'Black'}</blockquote>"
    )

    should_flip = (not b.turn) if g["rotate"] else False
    kb = render_board(game_id, b, flip=should_flip, auto_rotate=g["rotate"])

    if EDIT_MODE and g["board_msg_id"]:
        try:
            await app.edit_message_text(
                chat_id=g["chat"],
                message_id=g["board_msg_id"],
                text=text,
                reply_markup=kb
            )
            return
        except:
            g["board_msg_id"] = None

    try:
        sent = await msg.reply_text(text, reply_markup=kb)
        g["board_msg_id"] = sent.id
    except:
        pass


__menu__ = "CMD_GAMES"
__mod_name__ = "H_B_40"
__help__ = """
🔻 /chessgame - ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ᴄʜᴇꜱꜱ ɢᴀᴍᴇ ɪɴ ɢʀᴏᴜᴘ
🔻 /chessplaying - ꜱʜᴏᴡ ᴀʟʟ ᴀᴄᴛɪᴠᴇ ᴄʜᴇꜱꜱ ɢᴀᴍᴇꜱ ɪɴ ᴛʜᴇ ɢʀᴏᴜᴘ
🔻 /chesstop - ꜱʜᴏᴡ ᴄʜᴇꜱꜱ ᴛᴏᴘ 10 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ (ᴏᴠᴇʀᴀʟʟ & ɢʀᴏᴜᴘ ʀᴀɴᴋɪɴɢꜱ)
━━━━━━━━━━━━━━━━━━━━
♟ ɢᴀᴍᴇ ᴏᴘᴛɪᴏɴꜱ:
🤝 Draw - ʀᴇǫᴜᴇꜱᴛ ᴀ ᴅʀᴀᴡ ᴍᴀᴛᴄʜ  
🏳 Resign - ꜱᴜʀʀᴇɴᴅᴇʀ ᴛʜᴇ ɢᴀᴍᴇ  
🔄 Auto-Rotate ON/OFF - ᴛᴏɢɢʟᴇ ʙᴏᴀʀᴅ ʀᴏᴛᴀᴛɪᴏɴ  
🔁 Rematch - ꜱᴛᴀʀᴛ ᴀ ʀᴇᴍᴀᴛᴄʜ ᴀꜰᴛᴇʀ ɢᴀᴍᴇ ᴇɴᴅ  

⏱ ᴛɪᴍᴇʀ ꜰᴇᴀᴛᴜʀᴇꜱ
⏰ 600 ᴛᴏᴛᴀʟ ꜱᴇᴄᴏɴᴅꜱ ᴇᴀᴄʜ ᴘʟᴀʏᴇʀ  
⚠️ 60ꜱ ᴡᴀʀɴɪɴɢ  
⚠️ 10ꜱ ᴡᴀʀɴɪɴɢ  
⌛ ᴛɪᴍᴇ ᴏᴜᴛ = ᴀᴜᴛᴏ ʟᴏꜱꜱ  

🏆 ᴇʟᴏ & ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ ꜱʏꜱᴛᴇᴍ
📈 +20 ᴇʟᴏ ᴡɪɴ  
📉 -20 ᴇʟᴏ ʟᴏꜱꜱ  
🥇🥈🥉 ᴛᴏᴘ ʀᴀɴᴋ ʙᴀᴅɢᴇꜱ
"""

MOD_TYPE = "GAMES"
MOD_NAME = "Chess-Game"
MOD_PRICE = "300"
