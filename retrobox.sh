#!/usr/bin/env bash
# sudo apt install libfreeimage3 libsdl2-2.0-0 libsdl2-mixer-2.0-0 libvlc5 p7zip-full jq python3-pyudev \
# python3-pip python3-venv python3-sdl2 python3-yaml python3-qrcode python3-pil python3-evdev python3-pygame
# sudo apt update && sudo apt install -y libice6 libsm6 libxtst6 libxi6 inotify-tools antimicro

# sudo dnf install freeimage SDL2_mixer vlc-libs jq p7zip
# sudo dnf install python3-pyudev python3-pyudev python3-pip python3-virtualenv python3-pysdl2 python3-yaml python3-qrcode python3-pillow python3-evdev python3-qrcode python3-pygame

trapfunc(){
    pcgames-cover-backup
    "${HOME}/.local/bin/display-restore-layout"
}
trap trapfunc EXIT

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"

export USERDATA="${HERE:-$HOME/.local/share/batocera}"
export BATOCERA_ROOT="${USERDATA}"
for i in "${USERDATA}/resources/utils/"*; do
    if [ -f "$i/.bash" ] && [ ! -x "$i/.bash" ]; then
        PATH="$i:$PATH"
    fi
done

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


# Parámetro --shell / -s
if [[ "$1" == "-s" || "$1" == "--shell" ]]; then
    exec env \
        USERDATA="$USERDATA" \
        BATOCERA_ROOT="$BATOCERA_ROOT" \
        PATH="${USERDATA}/resources/system_scripts:${USERDATA}/resources/user_scripts:$PATH" \
        PS1="🎮 \[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]\n\$ " \
        bash --norc --noprofile
fi

# Parámetro --disable-internal-display / -i
if [[ "$1" == "-i" || "$1" == "--disable-internal-display" ]]; then
	"${HOME}/.local/bin/display-only-hdmi" 1080p
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
themes=${USERDATA}/frontend/themes

# Música
music=${USERDATA}/frontend/music

# Decoraciones/bezels
decorations=${USERDATA}/decorations

# Shaders
shaders=${USERDATA}/shaders/configs

# Videofilters
videofilters=${USERDATA}/emulators/retroarch/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/filters/video

# Videofilters
audiofilters=${USERDATA}/emulators/retroarch/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/filters/audio

# RetroAchievement sounds
retroachievementsounds=${USERDATA}/frontend/retroachievements-sounds

# Padtokey (gamepadly)
system.padtokey=${USERDATA}/resources/utils/gamepadly/profiles
padtokey=${USERDATA}/resources/utils/gamepadly/user_profiles

# Zonas horarias
timezones=/usr/share/zoneinfo
EOF

pcgames-cover-restore
"${USERDATA}/resources/utils/pcgames-sync/heroic-es-sync" || true
"${USERDATA}/resources/utils/pcgames-sync/lutris-es-sync" || true
"${USERDATA}/resources/utils/pcgames-sync/steam-es-sync" || true

cd "${USERDATA}/frontend" || exit 1

"${USERDATA}/frontend/emulationstation" --home "${USERDATA}/frontend" "$@"
exit $?
