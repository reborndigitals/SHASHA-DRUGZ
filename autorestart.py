import subprocess
import time
import datetime
import os

# ⬇️ Change this to your bot’s main file if it’s not main.py
BOT_COMMAND = ["bash", "start"]
REQUIREMENTS_FILE = "requirements.txt"

def log(message: str):
    """Log messages with timestamp to console and file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}"
    print(msg)
    with open("autorestart.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def install_requirements():
    """Install dependencies from requirements.txt if it exists."""
    if os.path.exists(REQUIREMENTS_FILE):
        log("Installing dependencies from requirements.txt...")
        try:
            subprocess.check_call(["pip", "install", "-r", REQUIREMENTS_FILE])
            log("✅ Requirements installed successfully.")
        except subprocess.CalledProcessError as e:
            log(f"❌ Error installing requirements: {e}")
    else:
        log("⚠️ No requirements.txt found — skipping dependency installation.")

def start_bot():
    """Start the bot process and wait for it to finish."""
    log("Starting bot process...")
    process = subprocess.Popen(BOT_COMMAND)
    process.wait()
    return process

def autorestart():
    """Continuously restart the bot if it stops."""
    install_requirements()  # install before first run
    while True:
        process = start_bot()
        exit_code = process.returncode
        log(f"💥Bot stopped (exit code: {exit_code}). 🔁Restarting in 60 seconds...")
        time.sleep(60)
        install_requirements()  # reinstall before restarting
