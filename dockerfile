# Base image
FROM python:3.10-slim

# System dependencies for Playwright & Python
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
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Browsers (Chromium only to save space)
RUN playwright install chromium
RUN playwright install-deps chromium

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