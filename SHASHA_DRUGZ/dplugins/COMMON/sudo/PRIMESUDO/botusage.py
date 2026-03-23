import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    InputMediaPhoto
)

import matplotlib.pyplot as plt
import os

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.database import mongodb


# ===================== Mongo Collections =====================
users_col = mongodb.users
chats_col = mongodb.chats
channels_col = mongodb.channels
monthly_col = mongodb.monthly_users

print("[botusage] botusage")


# ===================== SUDO FILTER =====================
def sudo_filter(_, __, message: Message):
    return message.from_user and message.from_user.id in SUDOERS

sudo_only = filters.create(sudo_filter)


# ===================== AUTO RESET MONTHLY =====================
async def auto_reset_monthly():
    while True:
        now = datetime.utcnow()
        if now.day == 1 and now.hour == 0:
            await monthly_col.delete_many({})
            print("[AUTO] Monthly reset completed")
            await asyncio.sleep(3600)
        await asyncio.sleep(300)

asyncio.get_event_loop().create_task(auto_reset_monthly())


# ===================== GET STATS =====================
async def get_stats():
    total_users = await users_col.count_documents({})
    total_chats = await chats_col.count_documents({})
    total_channels = await channels_col.count_documents({})
    monthly_users = await monthly_col.count_documents({})
    return total_users, total_chats, total_channels, monthly_users


# ===================== PIE CHART GENERATOR =====================
async def generate_pie_chart():
    total_users, total_chats, total_channels, monthly_users = await get_stats()

    labels = ["Users", "Chats", "Channels", "Monthly"]
    values = [total_users, total_chats, total_channels, monthly_users]

    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=labels, autopct='%1.1f%%')
    plt.title("Bot Usage Statistics")
    plt.tight_layout()

    path = "usage_pie_chart.png"
    plt.savefig(path)
    plt.close()
    return path


# ===================== SEND IMAGE + CAPTION =====================
async def send_usage_graph(message):
    img = await generate_pie_chart()
    total_users, total_chats, total_channels, monthly_users = await get_stats()

    caption = (
        "📊 **Bot Usage Statistics**\n\n"
        f"👥 Users: `{total_users}`\n"
        f"💬 Chats: `{total_chats}`\n"
        f"📢 Channels: `{total_channels}`\n"
        f"📅 Monthly Users: `{monthly_users}`"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats_graph")],
            [
                InlineKeyboardButton("Tot-Users", callback_data="show_users"),
                InlineKeyboardButton("Chats", callback_data="show_chats"),
            ],
            [
                InlineKeyboardButton("Channels", callback_data="show_channels"),
                InlineKeyboardButton("MonthlyUsers", callback_data="show_monthly"),
            ],
        ]
    )

    await message.reply_photo(photo=img, caption=caption, reply_markup=keyboard)


# ===================== COMMAND HANDLER =====================
@Client.on_message(filters.command("botusage") & sudo_only)
async def usage_graph_handler(client, message):
    await send_usage_graph(message)


# ===================== CALLBACK QUERY HANDLER =====================
@Client.on_callback_query(filters.regex("^(refresh_stats_graph|show_users|show_chats|show_channels|show_monthly)$"))
async def callback_handler(client, callback):

    total_users, total_chats, total_channels, monthly_users = await get_stats()

    # -------- REFRESH --------
    if callback.data == "refresh_stats_graph":
        img = await generate_pie_chart()

        new_caption = (
            "📊 **Bot Usage Statistics (Updated)**\n\n"
            f"👥 Users: `{total_users}`\n"
            f"💬 Chats: `{total_chats}`\n"
            f"📢 Channels: `{total_channels}`\n"
            f"📅 Monthly Users: `{monthly_users}`"
        )

        await callback.message.edit_media(
            InputMediaPhoto(img),
            reply_markup=callback.message.reply_markup
        )

        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=callback.message.reply_markup
        )

        return await callback.answer("✔ Stats Updated!", show_alert=False)

    # -------- POPUP ONLY BUTTONS --------
    if callback.data == "show_users":
        return await callback.answer(f"👥 Users: {total_users}", show_alert=True)

    if callback.data == "show_chats":
        return await callback.answer(f"💬 Chats: {total_chats}", show_alert=True)

    if callback.data == "show_channels":
        return await callback.answer(f"📢 Channels: {total_channels}", show_alert=True)

    if callback.data == "show_monthly":
        return await callback.answer(f"📅 Monthly Users: {monthly_users}", show_alert=True)


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__ = """
🔻 /botusage ➠ ᴅɪsᴘʟᴀʏ ɢʀᴀᴘʜɪᴄᴀʟ ʙᴏᴛ ᴜsᴀɢᴇ sᴛᴀᴛs ᴡɪᴛʜ ɪɴᴛᴇʀᴀᴄᴛɪᴠᴇ ʙᴜᴛᴛᴏɴs
"""
MOD_TYPE = "SUDO"
MOD_NAME = "Bot-Usage"
MOD_PRICE = "20"
