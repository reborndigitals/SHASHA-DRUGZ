from pyrogram import Client, filters
from SHASHA_DRUGZ import app


# 🎲 Dice
@Client.on_message(filters.command("dice"))
async def dice_handler(client, message):
    x = await client.send_dice(message.chat.id)
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🎯 Dart
@Client.on_message(filters.command("dart"))
async def dart_handler(client, message):
    x = await client.send_dice(message.chat.id, "🎯")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🏀 Basketball
@Client.on_message(filters.command("basket"))
async def basket_handler(client, message):
    x = await client.send_dice(message.chat.id, "🏀")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🎰 Jackpot
@Client.on_message(filters.command("jackpot"))
async def jackpot_handler(client, message):
    x = await client.send_dice(message.chat.id, "🎰")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# 🎳 Bowling
@Client.on_message(filters.command("ball"))
async def ball_handler(client, message):
    x = await client.send_dice(message.chat.id, "🎳")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )


# ⚽ Football
@Client.on_message(filters.command("football"))
async def football_handler(client, message):
    x = await client.send_dice(message.chat.id, "⚽")
    score = x.dice.value
    await message.reply_text(
        f"Hey {message.from_user.mention} your Score is : {score}",
        quote=True
    )
MOD_TYPE = "GAMES"
MOD_NAME = "Mini-Games"
MOD_PRICE = "20"
