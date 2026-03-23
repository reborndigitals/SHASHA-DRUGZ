import os
import psutil
import socket
import platform
import time
import asyncio
import speedtest
import shutil
from datetime import datetime
from pyrogram import filters, __version__ as pyrover
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from config import MONGO_DB_URI
from motor.motor_asyncio import AsyncIOMotorClient

print("[botstats] botstats")

START_TIME = time.time()    # Bot start time


# ---------- SUDO FILTER ----------
def sudo_filter(_, __, message: Message):
    return message.from_user and message.from_user.id in SUDOERS

sudo_only = filters.create(sudo_filter)


# ---------- READABLE TIME ----------
def get_readable_time(seconds: int) -> str:
    periods = [
        ("d", 86400),
        ("h", 3600),
        ("m", 60),
        ("s", 1)
    ]
    out = []
    for name, count in periods:
        value = seconds // count
        if value:
            seconds -= value * count
            out.append(f"{value}{name}")
    return " ".join(out)


# ---------- FOLDER SIZE ----------
def get_folder_size(path):
    total_size = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    return round(total_size / (1024 * 1024), 2)  # MB


# ---------- MONGODB STATUS ----------
async def mongo_status():
    try:
        client = AsyncIOMotorClient(MONGO_DB_URI)
        await client.server_info()
        return "🟢 Connected"
    except:
        return "🔴 Failed"


# ---------- SPEEDTEST ----------
async def get_speed():
    try:
        st = speedtest.Speedtest()
        download = round(st.download() / 1_000_000, 2)
        upload = round(st.upload() / 1_000_000, 2)
        return download, upload
    except:
        return 0, 0


# ---------- TOP PROCESSES ----------
def get_top_processes():
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            processes.append(proc.info)
        except:
            pass
    processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
    top5 = processes[:5]
    lines = ""
    for p in top5:
        lines += f"• {p['name']} (PID {p['pid']}): {p['cpu_percent']}%\n"
    return lines


# ---------- MAIN HANDLER ----------
@app.on_message(filters.command("botstats") & sudo_only)
async def botstats_handler(client, message: Message):

    uptime = get_readable_time(int(time.time() - START_TIME))
    uname = platform.uname()
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory().percent
    swap = psutil.swap_memory().percent
    disk = psutil.disk_usage("/").percent
    load1, load5, load15 = psutil.getloadavg()

    # CPU Temp (may be N/A on some VPS)
    temp = psutil.sensors_temperatures().get('coretemp', [{}])[0].get("current", "N/A")

    ipv4 = socket.gethostbyname(socket.gethostname())
    ipv6 = "N/A"
    try:
        ipv6 = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET6)[0][4][0]
    except:
        pass

    SHASHA_DRUGZ_size = get_folder_size("SHASHA_DRUGZ")
    mongo = await mongo_status()
    download, upload = await get_speed()
    top_process = get_top_processes()

    text = f"""
**🤖 BOT SYSTEM STATS**

**⏳ Runtime**
• Uptime: `{uptime}`

**🖥 System Info**
• OS: `{uname.system} {uname.release}`
• Machine: `{uname.machine}`
• Python: `{platform.python_version()}`
• Pyrogram: `{pyrover}`
• Hostname: `{socket.gethostname()}`

**🌍 Network**
• IPv4: `{ipv4}`
• IPv6: `{ipv6}`
• Download Speed: `{download} Mbps`
• Upload Speed: `{upload} Mbps`

**🗄 Storage**
• Disk Usage: `{disk}%`
• SHASHA_DRUGZ Folder: `{SHASHA_DRUGZ_size} MB`

**🔋 Performance**
• CPU: `{cpu}%`
• RAM: `{ram}%`
• SWAP: `{swap}%`
• Load Avg: `{load1} | {load5} | {load15}`
• CPU Temp: `{temp}°C`

**🧠 MongoDB**
• Status: {mongo}

**📋 Processes (Top 5 CPU)**
{top_process}
"""

    await message.reply_text(text)


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__ = """
🔻 /botstats ➠ ᴅɪsᴘʟᴀʏ ᴅᴇᴛᴀɪʟᴇᴅ sʏsᴛᴇᴍ ᴀɴᴅ ʙᴏᴛ sᴛᴀᴛs
"""
