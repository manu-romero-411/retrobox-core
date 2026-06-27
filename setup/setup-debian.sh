#!/usr/bin/env bash
# Instalación de dependencias de Retrobox para Debian, Ubuntu y Linux Mint.
# Probado en Debian 12+, Ubuntu 22.04+, Linux Mint 21+.
set -euo pipefail

echo "[retrobox] Installing system dependencies (apt)..."
sudo apt-get update
sudo apt-get install -y \
    libfreeimage3 \
    libsdl2-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libvlc5 \
    p7zip-full \
    jq \
    inotify-tools \
    libice6 \
    libsm6 \
    libxtst6 \
    libxi6 \
    python3-pyudev \
    python3-pip \
    python3-venv \
    python3-sdl2 \
    python3-yaml \
    python3-qrcode \
    python3-pil \
    python3-evdev \
    python3-pygame

echo "[retrobox] System dependencies sucessfully installed."
