#!/usr/bin/env bash
# Instalación de dependencias de Retrobox para Debian, Ubuntu y Linux Mint.
# Probado en Debian 13 y Linux Mint 22
set -euo pipefail
RETROBOX_ROOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. >/dev/null 2>&1 && pwd -P)"

echo "[retrobox] Installing system dependencies (apt)..."
sudo apt-get update
sudo apt-get install -y \
    git \
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
    python3-pygame \
    power-profiles-daemon \
    python3-ruamel.yaml

sudo cp ${RETROBOX_ROOTDIR}/resources/udev/*.rules /etc/udev/rules.d/
sudo usermod -aG input $(whoami)
sudo udevadm control --reload-rules
sudo udevadm trigger
cat << EOF | sudo tee /etc/udev/rules.d/99-input.rules
KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"
EOF

git clone https://github.com/RetroBat-Official/retrobat-bezels ${RETROBOX_ROOTDIR}/resources/decorations

echo "[retrobox] System dependencies sucessfully installed."
