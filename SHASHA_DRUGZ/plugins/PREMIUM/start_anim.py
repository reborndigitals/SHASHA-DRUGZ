# SHASHA_DRUGZ/plugins/bot/start_anim.py
"""
start_anim.py — Full-screen start animation module.

Provides:
    send_sticker_with_effect(chat_id)   → int | None
    run_start_animation(message)        → None

Import in start.py:
    from SHASHA_DRUGZ.plugins.bot.start_anim import (
        send_sticker_with_effect,
        run_start_animation,
    )
"""

import asyncio
import random

import httpx

import config

# ══════════════════════════════════════════════════════════════════════════════
#  START STICKERS
# ══════════════════════════════════════════════════════════════════════════════
START_STICKERS = [
    "CAACAgUAAxkBAAIKDGm80g_znNZjQLXko2KEZM1nr0qEAAKyCAACjfw5Vwmuqla3_0AwHgQ",
    "CAACAgUAAxkBAAIKDWm80hS0mpeZOgABlTG9UNpjvZI1WgACTgwAAiJJMFc40-Yhki2wlB4E",
    "CAACAgUAAxkBAAIKDmm80hnC_EQGNXEgg8bmiCWE32XLAALGCAAC0v05V82aflzlC23sHgQ",
    "CAACAgUAAxkBAAIKD2m80iHXNRg0a4YBB0Maz42ng4qTAAJxDAACyE0xV6aQfPRMeUokHgQ",
    "CAACAgUAAxkBAAIKEGm80iwLSwNsqJS6oiaK4qSfIekqAAIqCwACRA85V3w-iuqpGDgIHgQ",
    "CAACAgUAAxkBAAIKEWm80jUmiL-rSOgsVbvwGNoisya4AAJJDQACE6w5V--cufZUktLVHgQ",
    "CAACAgUAAxkBAAIKFmm80nwIlTijORY4AZPvzJN-uLW0AAKTDwAC8Bo4V2-xyEBcNmShHgQ",
    "CAACAgUAAxkBAAIKF2m80osFfSdFLU-i5rod-FsD4o1uAAL8CQACVOkwV5SIz-4RtYj2HgQ",
    "CAACAgUAAxkBAAIKGGm80pDOhtCP8mXTonXUlOLZ9mQzAALUCwACc045VwWrfNtzzpHvHgQ",
    "CAACAgUAAxkBAAIKG2m80qzrJSaBtSoAAasJasyuJ8X5VQACNwoAApLnMFfso_6k-QJv-x4E",
]

# ══════════════════════════════════════════════════════════════════════════════
#  EFFECT IDs
# ══════════════════════════════════════════════════════════════════════════════
PRIMARY_EFFECTS = [
    "5159385139981059251",   # ❤️  Hearts
    "5066970843586925436",   # 🔥 Flame
    "5070445174516318631",   # 🎉 Confetti
    "5104841245755180586",   # 😂 Laugh
    "5107584321108051015",   # 😍 Love Eyes
    "5104841245755180587",   # 😮 Wow
    "5104841245755180588",   # 👏 Clap
    "5107584321108051017",   # 🤯 Mind Blow
    "5046509860389126442",   # 💥 Explosion
    "5046589136895476101",   # ⚡ Lightning
    "5046589136895476102",   # 💫 Sparkle
    "5046589136895476103",   # 🌈 Rainbow
    "5046589136895476104",   # 🎶 Music
    "5046589136895476105",   # 🎯 Target
    "5046589136895476107",   # 💎 Diamond
    "5046589136895476108",   # 🚀 Rocket
    "5046589136895476109",   # 🌀 Spiral
    "5046589136895476110",   # 🌟 Star
]

SAFE_EFFECTS = [
    "5159385139981059251",   # ❤️  Hearts
    "5107584321108051014",   # 👍 Like
    "5070445174516318631",   # 🎉 Confetti
    "5066970843586925436",   # 🔥 Flame
]

# ══════════════════════════════════════════════════════════════════════════════
#  BOT API HELPER
# ══════════════════════════════════════════════════════════════════════════════
_BOT_API_URL = f"https://api.telegram.org/bot{config.BOT_TOKEN}"


async def _api_post(endpoint: str, payload: dict) -> dict:
    """Low-level Bot API POST — returns the parsed JSON dict."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(f"{_BOT_API_URL}/{endpoint}", json=payload)
            return resp.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  DELAYED DELETE
# ══════════════════════════════════════════════════════════════════════════════
async def delayed_delete(chat_id: int, message_id: int, delay: float = 3.0) -> None:
    """Delete a message after `delay` seconds (non-blocking when used as a task)."""
    await asyncio.sleep(delay)
    await _api_post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


async def _delete_msg(chat_id: int, message_id: int) -> None:
    """Immediate delete (thin wrapper kept for backward compat)."""
    await _api_post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


# ══════════════════════════════════════════════════════════════════════════════
#  SEND STICKER + FULL-SCREEN EFFECT
#  Fallback chain: primary (3 random tries) → safe pool → sticker alone
# ══════════════════════════════════════════════════════════════════════════════
async def send_sticker_with_effect(chat_id: int) -> int | None:
    """
    Send a random start sticker with a full-screen animation effect.

    Returns the message_id of the sent sticker, or None on complete failure.
    The caller is responsible for scheduling deletion of the sticker message.
    """
    sticker_id   = random.choice(START_STICKERS)
    primary_pool = random.sample(PRIMARY_EFFECTS, min(3, len(PRIMARY_EFFECTS)))

    # ── Try primary effects (3 random picks) ─────────────────────────────────
    for effect_id in primary_pool:
        data = await _api_post("sendSticker", {
            "chat_id":           chat_id,
            "sticker":           sticker_id,
            "message_effect_id": effect_id,
        })
        if data.get("ok"):
            return data["result"]["message_id"]

    # ── Fallback: safe effects ────────────────────────────────────────────────
    for effect_id in SAFE_EFFECTS:
        data = await _api_post("sendSticker", {
            "chat_id":           chat_id,
            "sticker":           sticker_id,
            "message_effect_id": effect_id,
        })
        if data.get("ok"):
            return data["result"]["message_id"]

    # ── Fallback: bare sticker, no effect ─────────────────────────────────────
    data = await _api_post("sendSticker", {
        "chat_id": chat_id,
        "sticker": sticker_id,
    })
    if data.get("ok"):
        return data["result"]["message_id"]

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  FULL ANIMATION SEQUENCE
#  Encapsulates Steps A–D so start.py stays clean.
# ══════════════════════════════════════════════════════════════════════════════
async def run_start_animation(message) -> None:
    """
    Play the complete start animation sequence in the given chat:

        Step A — Send sticker + full-screen effect
        Step B — "Ding dong" text animation
        Step C — "Starting…" text animation
        Step D — Schedule background deletion of sticker message
    """
    chat_id = message.chat.id

    # Step A — Sticker + effect
    sticker_msg_id = await send_sticker_with_effect(chat_id)
    # Let the full-screen effect animation fully render before continuing
    await asyncio.sleep(0.6)

    # Step B — Ding dong animation
    vip = await message.reply_text("**ᴅιиg ᴅσиg ꨄ︎❣️.....**")
    for dots in [".❣️....", "..❣️...", "...❣️..", "....❣️.", ".....❣️"]:
        await asyncio.sleep(0.1)
        await vip.edit_text(f"**ᴅιиg ᴅσиg ꨄ︎{dots}**")
    await asyncio.sleep(0.05)
    await vip.delete()

    # Step C — "Starting" typewriter animation
    vips = await message.reply_text("**⚡ѕ**")
    for step in [
        "⚡ѕт",
        "⚡ѕтα",
        "⚡ѕтαя",
        "⚡ѕтαят",
        "⚡ѕтαятι",
        "⚡ѕтαятιи",
        "⚡ѕтαятιиg",
    ]:
        await vips.edit_text(f"**{step}**")
        await asyncio.sleep(0.02)
    await vips.delete()

    # Step D — Schedule delayed sticker deletion (background task, non-blocking)
    # Immediate delete after an effect animation breaks Telegram's client UI state.
    if sticker_msg_id:
        asyncio.create_task(delayed_delete(chat_id, sticker_msg_id, delay=3.0))
