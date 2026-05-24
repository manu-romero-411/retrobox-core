#!/usr/bin/env bash
# sudo apt install libfreeimage3 libsdl2-2.0-0 libsdl2-mixer-2.0-0 libvlc5 p7zip-full jq python3-pyudev \
# python3-pip python3-venv python3-sdl2 python3-yaml python3-qrcode python3-pil python3-evdev
# sudo apt update && sudo apt install -y libice6 libsm6 libxtst6 libxi6 inotify-tools antimicro

# sudo dnf install freeimage SDL2_mixer vlc-libs jq p7zip
# sudo dnf install python3-pyudev python3-pyudev python3-pip python3-virtualenv python3-pysdl2 python3-yaml python3-qrcode python3-pillow python3-evdev python3-qrcode
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

export USERDATA="${HERE:-$HOME/.local/share/batocera}"
export BATOCERA_ROOT="${USERDATA}"
export PATH="${USERDATA}/resources/system_scripts:${USERDATA}/resources/user_scripts:$PATH"

# Comprobar que el directorio de Retrobox es real
if [ ! -d "${USERDATA}" ]; then
    echo "[ERROR] Directorio de Retrobox no válido: ${USERDATA}"
    exit 1
fi

# Crear directorios de config de emulationstation
if [ ! -d "${USERDATA}/frontend/.emulationstation" ]; then
    mkdir -p "${USERDATA}/frontend/.emulationstation"
    cp -r "${USERDATA}/frontend/share/emulationstation/." "${USERDATA}/frontend/.emulationstation/" 2>/dev/null
fi

cat << EOF > "${USERDATA}/frontend/.emulationstation/emulationstation.ini"
# Ficheros
config=${USERDATA}/batocera.conf

# Raíz y logs
root=${USERDATA}
log=${USERDATA}/logs

# ROMs y saves (root los infiere, pero explícitos por si acaso)
saves=${USERDATA}/saves
screenshots=${USERDATA}/screenshots

# Temas
system.themes=${USERDATA}/resources/themes
themes=${USERDATA}/frontend/.emulationstation/themes

# Música
system.music=${USERDATA}/resources/music
music=${USERDATA}/music

# Decoraciones/bezels
system.decorations=${USERDATA}/resources/datainit/decorations
decorations=${USERDATA}/decorations

# Shaders
system.shaders=${USERDATA}/resources/shaders/configs
shaders=${USERDATA}/shaders/configs

# Videofilters
system.videofilters=${USERDATA}/resources/videofilters
videofilters=${USERDATA}/videofilters

# RetroAchievement sounds
system.retroachievementsounds=${USERDATA}/resources/sounds/retroachievements
retroachievementsounds=${USERDATA}/sounds/retroachievements

# Padtokey (evmapy)
system.padtokey=${USERDATA}/resources/evmapy
padtokey=${USERDATA}/configs/evmapy

# Zonas horarias
timezones=/usr/share/zoneinfo
EOF

cd "${USERDATA}/frontend" || exit 1
exec "${USERDATA}/frontend/emulationstation" --home "${USERDATA}/frontend" "$@"
