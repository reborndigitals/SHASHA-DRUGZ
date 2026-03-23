from typing import Union

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from SHASHA_DRUGZ import app

# Main category page (first page shown for help)
def first_page(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["CMD_MUSIC"], callback_data="help_cat music"),
            InlineKeyboardButton(text=_["CMD_GAMES"], callback_data="help_cat games"),
        ],
        [
            InlineKeyboardButton(text=_["CMD_MANAGE"], callback_data="help_cat management"),
        ],
        [
            InlineKeyboardButton(text=_["CMD_CHAT"], callback_data="help_cat chat"),
            InlineKeyboardButton(text=_["CMD_REACT"], callback_data="help_cat reaction"),
        ],
        [
            InlineKeyboardButton(text=_["CMD_MENTION"], callback_data="help_cat mention"),
        ],
        #[
         #   InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
        #],
    ]
    return InlineKeyboardMarkup(buttons)


# Private panel (used when /help is used in private or for returning to start)
def private_help_panel(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["S_B_12"], callback_data="settings_back_helper"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# Single-category panels -----------------------------------------------------

def music_panel(_):
    # Music contains hb14 and hb22
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_22"], callback_data="help_callback hb22"),
            InlineKeyboardButton(text=_["H_B_34"], callback_data="help_callback hb34"),
            InlineKeyboardButton(text=_["H_B_14"], callback_data="help_callback hb14"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_36"], callback_data="help_callback hb36"),
            InlineKeyboardButton(text=_["H_B_8"], callback_data="help_callback hb8"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def games_panel1(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["GAME_1"], web_app=WebAppInfo(url="https://ultrashort.info/gkR6Ci")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJQaXhlbER1bmdlb24ifX0
            InlineKeyboardButton(text=_["GAME_2"], web_app=WebAppInfo(url="https://ultrashort.info/xkKB8w")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJLYXJhdGVLaWRvIn19
            InlineKeyboardButton(text=_["GAME_3"], web_app=WebAppInfo(url="https://ultrashort.info/TMyKFw")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJNYXJzUm92ZXIifX0
        ],
        [
            InlineKeyboardButton(text=_["GAME_4"], web_app=WebAppInfo(url="https://ultrashort.info/Q4XZDV")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJHcmF2aXR5TmluamFFbWVyYWxkQ2l0eSJ9fQ
            InlineKeyboardButton(text=_["GAME_5"], web_app=WebAppInfo(url="https://ultrashort.info/yzuwfg")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJBdGFyaUFzdGVyb2lkcyJ9fQ
            InlineKeyboardButton(text=_["GAME_6"], web_app=WebAppInfo(url="https://ultrashort.info/fMPToV")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJHcmF2aXR5TmluamEifX0
        ],
        [
            InlineKeyboardButton(text=_["GAME_7"], web_app=WebAppInfo(url="https://ultrashort.info/tJHfhb")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJHcmF2aXR5VW5pY29ybnMifX0
            InlineKeyboardButton(text=_["GAME_8"], web_app=WebAppInfo(url="https://ultrashort.info/ujoRZA")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJCZWFjaFJhY2VyIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_9"], web_app=WebAppInfo(url="https://ultrashort.info/ggg4cY")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJRdWJlMjA0OCJ9fQ
            InlineKeyboardButton(text=_["GAME_10"], web_app=WebAppInfo(url="https://ultrashort.info/FYZLhg")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJNb29uc2hvdCJ9fQ
        ],
        [
            InlineKeyboardButton(text=_["H_B_27"], callback_data="help_callback hb27"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
            InlineKeyboardButton(text=_["NEXT_BUTTON"], callback_data="games_p2"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def games_panel2(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["GAME_11"], web_app=WebAppInfo(url="https://ultrashort.info/K3cP4N")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJSdW4ifX0
            InlineKeyboardButton(text=_["GANE-12"], web_app=WebAppInfo(url="https://ultrashort.info/9iS2ot")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJCcmlja1N0YWNrZXIifX0
            InlineKeyboardButton(text=_["GAME_13"], web_app=WebAppInfo(url="https://ultrashort.info/NVMWSU")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJJbnRvVGhlTW9jYXZlcnNlIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_14"], web_app=WebAppInfo(url="https://ultrashort.info/zbL7Ee")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJOZW9uQmxhc3QyIn19
            InlineKeyboardButton(text=_["GAME_15"], web_app=WebAppInfo(url="https://ultrashort.info/ZxPIFE")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJCcmF0elBvcCJ9fQ
            InlineKeyboardButton(text=_["GAME_16"], web_app=WebAppInfo(url="https://ultrashort.info/qbSQ7L")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJIb29rZWQyMDQ4In19
        ],
        [
            InlineKeyboardButton(text=_["GAME_17"], web_app=WebAppInfo(url="https://ultrashort.info/1TFVOO")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJSaWRlT3JEaWUifX0
            InlineKeyboardButton(text=_["GAME_18"], web_app=WebAppInfo(url="https://ultrashort.info/CvIbGW")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJCYXNrZXRCb3lSdXNoIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_19"], web_app=WebAppInfo(url="https://ultrashort.info/z5T0hl")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJKdW1wdHViZXIxIn19
            InlineKeyboardButton(text=_["GAME_20"], web_app=WebAppInfo(url="https://ultrashort.info/wXu7P9")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTcGlreUZpc2gzIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_21"], web_app=WebAppInfo(url="https://ultrashort.info/o8d7m4")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJBdG9taWNEcm9wMSJ9fQ
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="games_p1"),
            InlineKeyboardButton(text=_["NEXT_BUTTON"], callback_data="games_p3"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)



def games_panel3(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["GAME_22"], web_app=WebAppInfo(url="https://ultrashort.info/VqWr4i")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJQZW5hbHR5U2hvb3RlcjIifX0
            InlineKeyboardButton(text=_["GAME_23"], web_app=WebAppInfo(url="https://ultrashort.info/cUUfD8")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTdW5zaGluZVNvbGl0YWlyZSJ9fQ
            InlineKeyboardButton(text=_["GAME_24"], web_app=WebAppInfo(url="https://ultrashort.info/5UF1ky")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJSZWRBbmRCbHVlIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_25"], web_app=WebAppInfo(url="https://ultrashort.info/SL3s2o")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJSb2xsZXJEaXNjbyJ9fQ
            InlineKeyboardButton(text=_["GAME_26"], web_app=WebAppInfo(url="https://ultrashort.info/MSOvrx")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJvbmV0d290aHJlZSJ9fQ
            InlineKeyboardButton(text=_["GAME_27"], web_app=WebAppInfo(url="https://ultrashort.info/mlcO59")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJHcm9vdnlTa2kifX0
        ],
        [
            InlineKeyboardButton(text=_["GAME_28"], web_app=WebAppInfo(url="https://ultrashort.info/Q5mfgi")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJNYXJibGVEYXNoIn19
            InlineKeyboardButton(text=_["GAME_29"], web_app=WebAppInfo(url="https://ultrashort.info/tK6bF9")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTd2l0Y2gxIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_30"], web_app=WebAppInfo(url="https://ultrashort.info/HJZmt1")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJDb2xvb3JIaXQifX0
            InlineKeyboardButton(text=_["GAME_31"], web_app=WebAppInfo(url="https://ultrashort.info/qu3Xjd")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJUZW50c0FuZFRyZWVzIn19
        ],
        [
            InlineKeyboardButton(text=_["GAME_32"], web_app=WebAppInfo(url="https://ultrashort.info/ISf9PD")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJOZW9uUmFjZXIifX0
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="games_p2"),
            InlineKeyboardButton(text=_["NEXT_BUTTON"], callback_data="games_p4"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def games_panel4(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["GAME_33"], web_app=WebAppInfo(url="https://ultrashort.info/xJSEBZ")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTYW11cmFpSG9sZGVtIn19
            InlineKeyboardButton(text=_["GAME_34"], web_app=WebAppInfo(url="https://ultrashort.info/Xv8xLQ")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJNYW5DaXR5U3RyaWtlcjNEIn19
            InlineKeyboardButton(text=_["GAME_35"], web_app=WebAppInfo(url="https://ultrashort.info/zgG9Cz")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTbWFydFVwU2hhcmsifX0
        ],
        [
            InlineKeyboardButton(text=_["GAME_36"], web_app=WebAppInfo(url="https://ultrashort.info/uEVnVD")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJGMVJhY2VyIn19
            InlineKeyboardButton(text=_["GAME_37"], web_app=WebAppInfo(url="https://ultrashort.info/z7SnZT")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTdXBlcmJ1Z3oifX0
            InlineKeyboardButton(text=_["GAME_38"], web_app=WebAppInfo(url="https://ultrashort.info/YbjaHn")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJLZWVwSXRVcCJ9fQ
        ],
        [
            InlineKeyboardButton(text=_["GAME_39"], web_app=WebAppInfo(url="https://ultrashort.info/CWatkc")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJLaW5nZG9tc09mMjA0OCJ9fQ
            InlineKeyboardButton(text=_["GAME_40"], web_app=WebAppInfo(url="https://ultrashort.info/2Sn9J1")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJHbG9ib1J1biJ9fQ
        ],
        [
            InlineKeyboardButton(text=_["GAME_41"], web_app=WebAppInfo(url="https://ultrashort.info/GqgTKg")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJBc3Ryb2NhdCJ9fQ
            InlineKeyboardButton(text=_["GAME_42"], web_app=WebAppInfo(url="https://ultrashort.info/U4n7cR")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTcGFjZU9yYml0In19
        ],
        [
            InlineKeyboardButton(text=_["GAME_43"], web_app=WebAppInfo(url="https://ultrashort.info/zDemd8")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJNb3RvRngifX0
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="games_p3"),
            InlineKeyboardButton(text=_["NEXT_BUTTON"], callback_data="games_p5"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)



def games_panel5(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["GAME_44"], web_app=WebAppInfo(url="https://ultrashort.info/ivhBMA")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJOZW9uQmxhc3RlciJ9fQ
            InlineKeyboardButton(text=_["GAME_45"], web_app=WebAppInfo(url="https://ultrashort.info/LJ2kSZ")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJUYW1hY2hpSnVtcCJ9fQ
            InlineKeyboardButton(text=_["GAME_46"], web_app=WebAppInfo(url="https://ultrashort.info/4SHOGN")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJXaXphcmRzMjEifX0
        ],
        [
            InlineKeyboardButton(text=_["GAME_47"], web_app=WebAppInfo(url="https://ultrashort.info/h9GT5e")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJTdWRva3VQdXp6bGUifX0
            InlineKeyboardButton(text=_["GAME_48"], web_app=WebAppInfo(url="https://ultrashort.info/DN6bd4")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJCbG9ja0JyZWFrZXIifX0
        ],
        [
            InlineKeyboardButton(text=_["GAME_49"], web_app=WebAppInfo(url="https://ultrashort.info/YbSe53")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJIb29wU2hvdCJ9fQ
            InlineKeyboardButton(text=_["GAME_50"], web_app=WebAppInfo(url="https://ultrashort.info/Mh9b2H")), #https://t.me/gamee/game?startapp=eyJnYW1lIjp7InNsdWciOiJHcmF2aXR5TmluamEyMSJ9fQ
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def chat_panel(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_9"], callback_data="help_callback hb9"),
            InlineKeyboardButton(text=_["H_B_37"], callback_data="help_callback hb37"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def reaction_panel(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_10"], callback_data="help_callback hb10"),
            InlineKeyboardButton(text=_["H_B_38"], callback_data="help_callback hb38"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def mention_panel(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_11"], callback_data="help_callback hb11"),
            InlineKeyboardButton(text=_["H_B_38"], callback_data="help_callback hb39"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_40"], callback_data="help_callback hb40"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# Management multi-page panels -----------------------------------------------

def management_page1(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_1"], callback_data="help_callback hb1"),
            InlineKeyboardButton(text=_["H_B_2"], callback_data="help_callback hb2"),
            InlineKeyboardButton(text=_["H_B_3"], callback_data="help_callback hb3"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_4"], callback_data="help_callback hb4"),
            InlineKeyboardButton(text=_["H_B_5"], callback_data="help_callback hb5"),
            InlineKeyboardButton(text=_["H_B_6"], callback_data="help_callback hb6"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_7"], callback_data="help_callback hb7"),
            InlineKeyboardButton(text=_["H_B_8"], callback_data="help_callback hb8"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_12"], callback_data="help_callback hb12"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="settings_back_helper"),
            InlineKeyboardButton(text=_["NEXT_BUTTON"], callback_data="management_p2"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def management_page2(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_13"], callback_data="help_callback hb13"),
            InlineKeyboardButton(text=_["H_B_15"], callback_data="help_callback hb15"),
            InlineKeyboardButton(text=_["H_B_16"], callback_data="help_callback hb16"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_17"], callback_data="help_callback hb17"),
            InlineKeyboardButton(text=_["H_B_18"], callback_data="help_callback hb18"),
            InlineKeyboardButton(text=_["H_B_19"], callback_data="help_callback hb19"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_20"], callback_data="help_callback hb20"),
            InlineKeyboardButton(text=_["H_B_21"], callback_data="help_callback hb21"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_23"], callback_data="help_callback hb23"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="management_p1"),
            InlineKeyboardButton(text=_["NEXT_BUTTON"], callback_data="management_p3"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def management_page3(_):
    buttons = [
        [
            InlineKeyboardButton(text=_["H_B_24"], callback_data="help_callback hb24"),
            InlineKeyboardButton(text=_["H_B_25"], callback_data="help_callback hb25"),
            InlineKeyboardButton(text=_["H_B_26"], callback_data="help_callback hb26"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_28"], callback_data="help_callback hb28"),
            InlineKeyboardButton(text=_["H_B_29"], callback_data="help_callback hb29"),
            InlineKeyboardButton(text=_["H_B_30"], callback_data="help_callback hb30"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_31"], callback_data="help_callback hb31"),
            InlineKeyboardButton(text=_["H_B_32"], callback_data="help_callback hb32"),
        ],
        [
            InlineKeyboardButton(text=_["H_B_33"], callback_data="help_callback hb33"),
        ],
        [
            InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data="management_p2"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# generic back/close markup used by individual help pages
def help_back_markup(_):
    upl = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text=_["BACK_BUTTON"], callback_data=f"settings_back_helper"),
                InlineKeyboardButton(text=_["CLOSE_BUTTON"], callback_data=f"close"),
            ]
        ]
    )
    return upl
