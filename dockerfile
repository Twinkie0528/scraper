# Base image
FROM python:3.10-slim

# System dependencies for Playwright (БҮРЭН ЖАГСААЛТ)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
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
    # НЭМСЭН - Playwright-д заавал хэрэгтэй
    libpango-1.0-0 \
    libcairo2 \
    libpangocairo-1.0-0 \
    libcairo-gobject2 \
    libgdk-pixbuf-2.0-0 \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libxaw7 \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Browsers (Chromium only)
RUN playwright install chromium
RUN playwright install-deps chromium || true

# Copy Code
COPY . .

# Create necessary dirs
RUN mkdir -p banner_screenshots _export

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Ulaanbaatar

# Expose Port
EXPOSE 8899

# Start Command
CMD ["python", "server.py"]