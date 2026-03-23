# ===========================
#  SHASHA_DRUGZ ULTIMATE CRASH & TOOLS SUITE
#  (MERGED: crash_analyzer + advanced_crash_analyzer + advanced_tools)
# ===========================

import os
import sys
import traceback
import subprocess
import importlib.util
import importlib
from typing import Tuple, List

from pyrogram import Client, filters
from pyrogram.types import Message

from SHASHA_DRUGZ import app
from SHASHA_DRUGZ.misc import SUDOERS


# ---------------- SUDO FILTER ----------------
def sudo_filter(_, __, message: Message):
    return message.from_user and message.from_user.id in SUDOERS

sudo_only = filters.create(sudo_filter)


# ---------------- GLOBAL ----------------
PLUGIN_PATH = "SHASHA_DRUGZ/dplugins"


# ============================================================
#                 SHARED ANALYZE FUNCTIONS
# ============================================================

def analyze_module(module_path):
    """Check if python file can be imported correctly"""
    try:
        spec = importlib.util.spec_from_file_location(f"module_{hash(module_path)}", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True, "OK"
    except Exception as e:
        return False, traceback.format_exc()


# ============================================================
#                    ORIGINAL CRASH ANALYZER
# ============================================================

@Client.on_message(filters.command("crashes") & sudo_only)
async def crashes_handler(client, message: Message):
    report = "🔍 **SHASHA Crash Analyzer (PyV2)**\n\n"
    broken = 0
    checked = 0

    for root, dirs, files in os.walk(PLUGIN_PATH):
        for file in files:
            if file.endswith(".py"):
                checked += 1
                module_path = os.path.join(root, file)

                status, info = analyze_module(module_path)

                if status:
                    report += f"✔️ `{file}` → **OK**\n"
                else:
                    broken += 1
                    report += f"❌ `{file}` → **BROKEN**\n"
                    report += f"```{info}```\n"

    report += "\n📌 **Scan Complete**\n"
    report += f"• Checked Modules: `{checked}`\n"
    report += f"• Broken Modules: `{broken}`\n"

    if broken == 0:
        report += "\n✅ All modules are working perfectly!"
    else:
        report += "\n⚠️ Fix the above modules."

    await message.reply_text(report)


# ============================================================
#         ADVANCED CRASH ANALYZER (AUTO IMPORT FIXER)
# ============================================================

def try_fix_missing_import(error_text):
    """Detect missing imports & pip install automatically."""
    if "ModuleNotFoundError" not in error_text:
        return False, None
    try:
        missing = error_text.split("No module named '")[1].split("'")[0]
    except:
        return False, None

    try:
        subprocess.check_output(f"pip install {missing}", shell=True, stderr=subprocess.STDOUT)
        return True, f"📦 Installed missing module: **{missing}**"
    except subprocess.CalledProcessError as e:
        return False, f"❌ Failed to install `{missing}`\n```\n{e.output.decode()}\n```"


@Client.on_message(filters.command("crashespro") & sudo_only)
async def advanced_crashes_handler(client, message: Message):
    report = "🔍 **Advanced SHASHA_DRUGZ Crash Analyzer (PyV2)**\n\n"
    broken = 0
    fixed = 0
    checked = 0

    for root, dirs, files in os.walk(PLUGIN_PATH):
        for file in files:
            if file.endswith(".py"):
                checked += 1
                module_path = os.path.join(root, file)

                status, info = analyze_module(module_path)

                if status:
                    report += f"✔️ `{file}` → **OK**\n"
                else:
                    broken += 1
                    report += f"❌ `{file}` → **BROKEN**\n"

                    # AUTO FIX START
                    fixed_ok, fix_msg = try_fix_missing_import(info)

                    if fixed_ok:
                        fixed += 1
                        report += f"🛠 **Fix Applied:** {fix_msg}\n"

                        status2, info2 = analyze_module(module_path)
                        if status2:
                            report += f"✔️ `{file}` → **FIXED & OK NOW**\n"
                        else:
                            report += f"⚠️ Still broken:\n```{info2}```\n"
                    else:
                        if fix_msg:
                            report += fix_msg + "\n"
                        report += f"```{info}```\n"

    report += "\n📌 **Scan Summary**\n"
    report += f"• Checked Modules: `{checked}`\n"
    report += f"• Broken Modules: `{broken}`\n"
    report += f"• Auto-Fixed Missing Imports: `{fixed}`\n"

    if broken == 0:
        report += "\n✅ All modules are working perfectly!"
    elif fixed == broken:
        report += "\n✅ All issues fixed automatically!"
    else:
        report += "\n⚠️ Some modules still have errors."

    await message.reply_text(report)


# ============================================================
#               ADVANCED TOOLS (MASS FIX, RELOAD)
# ============================================================

def extract_missing_module(error_text: str) -> List[str]:
    missing = []
    for ln in error_text.splitlines():
        if "No module named" in ln:
            try:
                name = ln.split("No module named")[1].strip().strip(":").strip().strip("'\" ")
                if name:
                    missing.append(name)
            except:
                pass
    return list(dict.fromkeys(missing))


def pip_install(pkg: str) -> Tuple[bool, str]:
    try:
        cmd = [sys.executable, "-m", "pip", "install", pkg]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=300)
        return True, output
    except subprocess.CalledProcessError as e:
        return False, e.output
    except Exception as e:
        return False, str(e)


def find_plugin_by_name(name: str) -> str:
    if os.path.isabs(name) and os.path.exists(name):
        return name
    candidate = os.path.join(PLUGIN_PATH, name)
    if os.path.exists(candidate):
        return candidate
    if name.endswith(".py"):
        for root, _, files in os.walk(PLUGIN_PATH):
            if name in files:
                return os.path.join(root, name)
    fname = f"{name}.py"
    for root, _, files in os.walk(PLUGIN_PATH):
        if fname in files:
            return os.path.join(root, fname)
    return ""


def safe_reload_file(path: str) -> Tuple[bool, str]:
    try:
        key = f"shasha_plugin_{hash(path)}"
        spec = importlib.util.spec_from_file_location(key, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[key] = module
        return True, "Reloaded"
    except Exception:
        return False, traceback.format_exc()


def scan_all_plugins() -> List[dict]:
    results = []
    for root, _, files in os.walk(PLUGIN_PATH):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                ok, info = analyze_module(path)
                results.append({"path": path, "ok": ok, "info": info})
    return results


# ---------------- /broken ----------------
@Client.on_message(filters.command("broken") & sudo_only)
async def broken_cmd(client, message: Message):
    await message.reply_text("🔍 Scanning plugins for broken modules...")
    results = scan_all_plugins()
    broken = [r for r in results if not r["ok"]]

    if not broken:
        return await message.reply_text("✅ No broken modules found.")

    text = "❌ **Broken Modules**\n\n"
    for r in broken:
        fname = os.path.relpath(r["path"], PLUGIN_PATH)
        text += f"• `{fname}`\n```\n{r['info'][:1000]}\n```\n"

    await message.reply_text(text)


# ---------------- /fixall ----------------
@Client.on_message(filters.command("fixall") & sudo_only)
async def fixall_cmd(client, message: Message):
    await message.reply_text("🔧 Auto-fixing missing imports...")

    results = scan_all_plugins()
    broken = [r for r in results if not r["ok"]]

    fixed = 0
    cannot = []

    for r in broken:
        tb = r["info"]
        missing = extract_missing_module(tb)

        if not missing:
            cannot.append({"path": r["path"], "reason": "No missing import", "trace": tb})
            continue

        installed_any = False
        for pkg in missing:
            ok, _ = pip_install(pkg)
            if ok:
                installed_any = True

        ok2, info2 = analyze_module(r["path"])
        if ok2:
            fixed += 1
        else:
            cannot.append({"path": r["path"], "reason": "Still broken", "trace": info2})

    summary = (
        f"🛠 Auto-fix complete\n"
        f"✔ Fixed: {fixed}\n"
        f"❌ Failed: {len(cannot)}"
    )

    await message.reply_text(summary)


# ---------------- /reloadmodule ----------------
@Client.on_message(filters.command("reloadmodule") & sudo_only)
async def reloadmodule_cmd(client, message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply_text("Usage: /reloadmodule <module_name>")

    name = parts[1].strip()
    path = find_plugin_by_name(name)
    if not path:
        return await message.reply_text("❌ File not found.")

    ok, info = safe_reload_file(path)
    if ok:
        await message.reply_text(f"✅ Reloaded `{name}`")
    else:
        await message.reply_text(f"❌ Failed to reload\n```\n{info}\n```")


# ---------------- /reloadall ----------------
@Client.on_message(filters.command("reloadall") & sudo_only)
async def reloadall_cmd(client, message: Message):
    await message.reply_text("♻️ Reloading all plugins...")

    success = 0
    failed = []

    for root, _, files in os.walk(PLUGIN_PATH):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                ok, info = safe_reload_file(path)
                if ok:
                    success += 1
                else:
                    failed.append({"path": path, "info": info})

    text = f"✅ Reloaded: {success}\n❌ Failed: {len(failed)}"
    await message.reply_text(text)

__menu__ = "CMD_MANAGE"
__mod_name__ = "H_B_36"
__help__ = """
🔻 /crashes ➠ Scan all plugins for errors & report broken modules
🔻 /crashespro ➠ Advanced scan: detects broken plugins, auto-installs missing imports, reports fixes
🔻 /broken ➠ List all currently broken modules in plugins
🔻 /fixall ➠ Auto-fix missing imports in all broken modules
🔻 /reloadmodule <module_name> ➠ Reload a single plugin/module by name
🔻 /reloadall ➠ Reload all plugins/modules at once
"""

MOD_TYPE = "SUDO"
MOD_NAME = "Crash-Analyser"
MOD_PRICE = "30"
