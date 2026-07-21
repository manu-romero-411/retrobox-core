#!/usr/bin/env bash
# Instalación de dependencias de Retrobox para Fedora.
# Probado en Fedora 39+. Requiere RPM Fusion (free) para algunos paquetes multimedia.
# Para habilitar RPM Fusion si no lo tienes:
#   sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
set -euo pipefail

echo "[retrobox] Installing system dependencies (dnf)..."
sudo dnf install -y \
    freeimage \
    SDL2_mixer \
    vlc-libs \
    jq \
    p7zip \
    inotify-tools \
    python3-pyudev \
    python3-pip \
    python3-virtualenv \
    python3-pysdl2 \
    python3-pyyaml \
    python3-qrcode \
    python3-pillow \
    python3-evdev \
    python3-pygame \
    python-ruamel-yaml \
    python3-tomlkit

echo "[retrobox] System dependencies sucessfully installed."