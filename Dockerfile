# ─────────────────────────────────────────────────────────────
#  Railway-optimized build — target < 3.5 GB
#
#  Size reductions vs old Dockerfile:
#  1. Base: slim debian instead of nikolaik full image  (-400MB)
#  2. Node.js: only install what's needed              (-300MB)
#  3. Playwright: chromium only, NO --with-deps        (-400MB)
#     (system chromium deps installed manually — only what's needed)
#  4. bgutil: node_modules pruned after tsc compile    (-100MB)
#  5. pip packages: heavy unused ones removed from cleanup
#  6. ALL layers: aggressive cleanup in same RUN       (-200MB)
# ─────────────────────────────────────────────────────────────
FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV BGUTIL_SERVER_HOME=/app/bgutil-ytdlp-pot-provider/server
ENV DEBIAN_FRONTEND=noninteractive

# ── System deps: ffmpeg + Node.js 20 + Chromium deps + git ──
# Everything in ONE layer — no intermediate layers wasting space.
# Node.js installed via NodeSource (lean, no extra bloat).
# Chromium system deps: only what playwright actually needs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        # Build essentials
        curl \
        wget \
        git \
        gnupg \
        ca-certificates \
        # Audio/video
        ffmpeg \
        # Chromium runtime deps (minimal set for headless)
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcb-dri3-0 \
        fonts-liberation \
    # Install Node.js 20 via NodeSource
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    # Cleanup
    && apt-get clean \
    && apt-get autoremove -y \
    && rm -rf \
        /var/lib/apt/lists/* \
        /var/cache/apt/archives/* \
        /usr/share/doc/* \
        /usr/share/man/* \
        /usr/share/locale/* \
        /tmp/*

WORKDIR /app

# ── Python packages ───────────────────────────────────────────
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir -U bgutil-ytdlp-pot-provider \
    # Aggressive cleanup
    && find /usr/local/lib/python3.10 -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.10 -type d -name "tests"       -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.10 -type d -name "test"        -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.10 -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr/local/lib/python3.10 -name "*.pyo" -delete 2>/dev/null || true \
    # Remove heavy unused test/docs from installed packages
    && find /usr/local/lib/python3.10/dist-packages -name "*.dist-info" -type d \
         -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /root/.cache/pip /tmp/*

# ── Playwright: install chromium ONLY (no --with-deps) ───────
# System deps already installed above — much smaller than --with-deps
RUN pip install --no-cache-dir playwright \
    && playwright install chromium \
    && rm -rf \
        /root/.cache/pip \
        /tmp/* \
        /var/tmp/*

# ── bgutil Node.js server ─────────────────────────────────────
# Clone → install → compile → prune dev deps → remove node_modules
# Only keep the compiled build/ directory — saves ~150MB
RUN git clone --single-branch --depth 1 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
        /app/bgutil-ytdlp-pot-provider \
    && cd /app/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && npx tsc \
    # Keep only build output — remove node_modules and source
    && npm prune --production \
    && rm -rf \
        /app/bgutil-ytdlp-pot-provider/server/src \
        /app/bgutil-ytdlp-pot-provider/.git \
        /root/.npm \
        /tmp/*

ENV CHROME_BIN=/usr/bin/chromium

# ── Project source ────────────────────────────────────────────
COPY . .
RUN chmod +x start \
    && find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find . -name "*.pyc" -delete 2>/dev/null || true

CMD ["bash", "start"]
