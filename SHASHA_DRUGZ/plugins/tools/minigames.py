from pyrogram import filters
from SHASHA_DRUGZ import app


# 🎲 Dice
@app.on_message(filters.command("dice"))
async def dice_handler(client, message):
    x = await client.send_dice(message.chat.id)
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🎯 Dart
@app.on_message(filters.command("dart"))
async def dart_handler(client, message):
    x = await client.send_dice(message.chat.id, "🎯")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🏀 Basketball
@app.on_message(filters.command("basket"))
async def basket_handler(client, message):
    x = await client.send_dice(message.chat.id, "🏀")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🎰 Jackpot
@app.on_message(filters.command("jackpot"))
async def jackpot_handler(client, message):
    x = await client.send_dice(message.chat.id, "🎰")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🎳 Bowling
@app.on_message(filters.command("ball"))
async def ball_handler(client, message):
    x = await client.send_dice(message.chat.id, "🎳")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# ⚽ Football
@app.on_message(filters.command("football"))
async def football_handler(client, message):
    x = await client.send_dice(message.chat.id, "⚽")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )
