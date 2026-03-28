FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BGUTIL_SERVER_HOME=/app/bgutil-ytdlp-pot-provider/server \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies + Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl wget git gnupg ca-certificates ffmpeg \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
        libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
        libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
        libpango-1.0-0 libpangocairo-1.0-0 libgtk-3-0 \
        libx11-xcb1 libxcb-dri3-0 fonts-liberation \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt /usr/share/doc \
              /usr/share/man /usr/share/locale /tmp/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -U bgutil-ytdlp-pot-provider playwright playwright-stealth camoufox \
    && rm -rf /root/.cache/pip /tmp/*

# Install Playwright browser
RUN playwright install chromium

# Clone bgutil server and install Node deps only.
# v1.3.1+ removed the TypeScript compile step entirely.
# The server runs src/main.ts directly at runtime via swc-node.
# There is NO build/ folder and NO npx tsc step.
RUN git clone --single-branch --depth 1 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
        /app/bgutil-ytdlp-pot-provider \
    && cd /app/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && test -f src/main.ts \
        || (echo "ERROR: src/main.ts not found after clone!" && exit 1) \
    && echo "OK: src/main.ts confirmed. No compile needed for v1.3.1+." \
    && rm -rf ../.git /root/.npm /tmp/*

# Copy project files
COPY . .

# Cleanup + fix start script permissions
RUN chmod +x start \
    && find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find . -name "*.pyc" -delete 2>/dev/null || true

CMD ["bash", "start"]
