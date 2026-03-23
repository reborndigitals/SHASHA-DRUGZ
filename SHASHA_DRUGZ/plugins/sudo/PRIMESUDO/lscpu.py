# SHASHA_DRUGZ/modules/lscpu.py
import asyncio
import os
import platform
import shutil
import subprocess
import sys
from typing import Dict

from pyrogram import filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS
from SHASHA_DRUGZ.utils.decorators.language import language

print("[lscpu] lscpu")

def _run_cmd(cmd: list) -> str:
    """Blocking helper to run a command and return decoded output."""
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return out.decode(errors="ignore").strip()
    except Exception:
        return ""


def _parse_proc_cpuinfo() -> Dict[str, str]:
    """Fallback parser for /proc/cpuinfo (Linux)."""
    info = {}
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()
    except Exception:
        return info

    # grab a few common fields from cpuinfo for the first processor
    for line in data.splitlines():
        if ":" not in line:
            continue
        k, v = map(str.strip, line.split(":", 1))
        if k in ("model name", "cpu MHz", "vendor_id", "flags", "cache size", "processor"):
            info.setdefault(k, v)
    return info


def _read_file_first_line(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readline().strip()
    except Exception:
        return ""


def blocking_gather_system_info() -> Dict[str, str]:
    """Blocking function that gathers system info using lscpu or fallbacks."""
    out: Dict[str, str] = {}

    # Basic platform
    out["OS"] = f"{platform.system()} {platform.release()} ({platform.version()})"
    out["Platform"] = platform.platform()
    out["Python"] = f"{platform.python_implementation()} {platform.python_version()}"

    # Detect common PaaS indicators
    out["Platform-Env"] = ", ".join(
        name
        for name in (
            "DYNO" if os.environ.get("DYNO") else "",
            "RAILWAY" if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY") else "",
            "RENDER" if os.environ.get("RENDER") else "",
            "HEROKU" if os.environ.get("PORT") and os.environ.get("DYNO") else "",
        )
        if name
    ) or "self-host / unknown"

    # Try lscpu first
    lscpu = _run_cmd(["lscpu"])
    if lscpu:
        # keep only important lines to avoid massive text
        lines = []
        keep_keys = ("Architecture", "CPU(s)", "Model name", "Thread(s) per core", "Core(s) per socket", "Socket(s)", "Vendor ID", "CPU max MHz", "CPU min MHz", "L1d cache", "L1i cache", "L2 cache", "L3 cache")
        for line in lscpu.splitlines():
            for k in keep_keys:
                if line.startswith(k + ":"):
                    lines.append(line.strip())
                    break
        out["CPU"] = "\n".join(lines) if lines else lscpu[:2000]
    else:
        # fallback to /proc/cpuinfo
        cpuinfo = _parse_proc_cpuinfo()
        if cpuinfo:
            cpu_lines = []
            if "model name" in cpuinfo:
                cpu_lines.append(f"Model: {cpuinfo.get('model name')}")
            if "vendor_id" in cpuinfo:
                cpu_lines.append(f"Vendor: {cpuinfo.get('vendor_id')}")
            if "cpu MHz" in cpuinfo:
                cpu_lines.append(f"MHz: {cpuinfo.get('cpu MHz')}")
            if "cache size" in cpuinfo:
                cpu_lines.append(f"Cache: {cpuinfo.get('cache size')}")
            out["CPU"] = "\n".join(cpu_lines) or "cpuinfo available"
        else:
            out["CPU"] = "No lscpu or /proc/cpuinfo available"

    # Memory from /proc/meminfo (Linux) or shutil on other platforms
    if os.path.exists("/proc/meminfo"):
        mem_total = _read_file_first_line("/proc/meminfo").split()
        try:
            # /proc/meminfo first line like "MemTotal: 16384256 kB"
            with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                mem_data = f.read()
            for line in mem_data.splitlines():
                if line.startswith("MemTotal:"):
                    out["Memory"] = line.split(":", 1)[1].strip()
                    break
        except Exception:
            out["Memory"] = "unknown"
    else:
        try:
            total, used, free = shutil.disk_usage("/")
            out["Memory"] = "not-linux (/proc not available)"
        except Exception:
            out["Memory"] = "unknown"

    # Disk usage for root
    try:
        total, used, free = shutil.disk_usage("/")
        out["Disk"] = f"Total: {total // (1024 ** 3)} GB, Free: {free // (1024 ** 3)} GB"
    except Exception:
        out["Disk"] = "unknown"

    # Uptime (Linux)
    if os.path.exists("/proc/uptime"):
        try:
            with open("/proc/uptime", "r", encoding="utf-8", errors="ignore") as f:
                up = float(f.readline().split()[0])
            hours = int(up // 3600)
            mins = int((up % 3600) // 60)
            out["Uptime"] = f"{hours}h {mins}m"
        except Exception:
            out["Uptime"] = "unknown"
    else:
        # Try `uptime` command fallback
        up_cmd = _run_cmd(["uptime", "-p"])
        out["Uptime"] = up_cmd or "unknown"

    # Container/cgroup hints
    cgroup = _read_file_first_line("/proc/1/cgroup") if os.path.exists("/proc/1/cgroup") else ""
    out["Container"] = "likely" if "docker" in cgroup or "kubepods" in cgroup else "no obvious container marker"

    # Misc helpful info
    uname = _run_cmd(["uname", "-a"])
    if uname:
        out["uname"] = uname

    # CPU count from Python
    out["Logical-CPUs"] = str(os.cpu_count() or "unknown")

    return out


@app.on_message(filters.command(["lscpu"], prefixes=["/", "!", "%", ",", "", ".", "@", "#"]) & SUDOERS)
@language
async def lscpu_cmd(client, message: Message, _):
    """
    Sudo-only /lscpu command.
    Gathers server specs using lscpu or fallbacks and replies with a concise report.
    """
    status = await message.reply_text(_("server_please_wait") if _ and "server_please_wait" in _ else "Gathering server info...")
    loop = asyncio.get_event_loop()

    try:
        # run blocking gather in executor, with a conservative timeout
        info = await asyncio.wait_for(loop.run_in_executor(None, blocking_gather_system_info), timeout=30)
    except asyncio.TimeoutError:
        await status.edit_text("<code>Timed out while gathering system info.</code>")
        return
    except Exception as e:
        await status.edit_text(f"<code>{e}</code>")
        return

    # Build a readable message
    parts = []
    parts.append(f"<b>OS</b>: <code>{info.get('OS')}</code>")
    parts.append(f"<b>Platform</b>: <code>{info.get('Platform')}</code>")
    parts.append(f"<b>Python</b>: <code>{info.get('Python')}</code>")
    parts.append(f"<b>Platform-Env</b>: <code>{info.get('Platform-Env')}</code>")
    parts.append(f"<b>Logical CPUs</b>: <code>{info.get('Logical-CPUs')}</code>")
    parts.append("<b>CPU</b>:\n<pre>{}</pre>".format(info.get("CPU")))
    parts.append(f"<b>Memory</b>: <code>{info.get('Memory')}</code>")
    parts.append(f"<b>Disk</b>: <code>{info.get('Disk')}</code>")
    parts.append(f"<b>Uptime</b>: <code>{info.get('Uptime')}</code>")
    parts.append(f"<b>Container</b>: <code>{info.get('Container')}</code>")
    if info.get("uname"):
        parts.append(f"<b>uname</b>: <code>{info.get('uname')}</code>")

    text = "\n\n".join(parts)

    # ensure message not too long for Telegram (keep reasonable length)
    if len(text) > 4000:
        # trim CPU section if too long
        cpu = info.get("CPU", "")
        if len(cpu) > 800:
            cpu = cpu[:800] + "\n... (truncated)"
        # rebuild
        parts[5] = "<b>CPU</b>:\n<pre>{}</pre>".format(cpu)
        text = "\n\n".join(parts)

    await message.reply_text(text, disable_web_page_preview=True) #, parse_mode="html")
    await status.delete()


__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__ = """
🔻 /lscpu ➠ Show detailed server/system specs: OS, platform, Python version, logical CPUs, CPU info, memory, disk usage, uptime, container info.
"""
