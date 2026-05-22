#!/usr/bin/env bash
# sudo apt install libfreeimage3 libsdl2-2.0-0 libsdl2-mixer-2.0-0 libvlc5 p7zip-full jq python3-pyudev python3-pip python3-venv python3-sdl2 python3-yaml python3-qrcode python3-pil python3-evdev
# sudo apt update && sudo apt install -y libice6 libsm6 libxtst6 libxi6 inotify-tools antimicro
#HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

export USERDATA="${HERE:-$HOME/.local/share/batocera}"
export BATOCERA_ROOT="${USERDATA}"
export PATH="${USERDATA}/scripts:$PATH"

if [ ! -d "${USERDATA}/.emulationstation" ]; then
    mkdir -p "${USERDATA}/.emulationstation"
    cp -r "${USERDATA}/emulationstation/share/emulationstation/." "${USERDATA}/.emulationstation/" 2>/dev/null
fi

cat << EOF > "${USERDATA}/.emulationstation/emulationstation.ini"
# Ficheros
config=${USERDATA}/batocera.conf

# Raíz y logs
root=${USERDATA}
log=${USERDATA}/logs

# ROMs y saves (root los infiere, pero explícitos por si acaso)
saves=${USERDATA}/saves
screenshots=${USERDATA}/screenshots

# Temas
system.themes=${HOME}/proyectos/batocera-emulationstation/themes
themes=${USERDATA}/.emulationstation/themes

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

cd "${USERDATA}/emulationstation" || exit 1
exec "${USERDATA}/emulationstation/emulationstation" --home "${USERDATA}" "$@"
