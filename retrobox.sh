#!/usr/bin/env bash
# sudo apt install libfreeimage3 libsdl2-2.0-0 libsdl2-mixer-2.0-0 libvlc5 p7zip-full jq python3-pyudev \
# python3-pip python3-venv python3-sdl2 python3-yaml python3-qrcode python3-pil python3-evdev python3-pygame
# sudo apt update && sudo apt install -y libice6 libsm6 libxtst6 libxi6 inotify-tools antimicro
# sudo dnf install freeimage SDL2_mixer vlc-libs jq p7zip
# sudo dnf install python3-pyudev python3-pip python3-virtualenv python3-pysdl2 python3-yaml python3-qrcode python3-pillow python3-evdev python3-pygame

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
export USERDATA="${HERE:-$HOME/.local/share/batocera}"
export BATOCERA_ROOT="${USERDATA}"

RETROHOOK="${USERDATA}/resources/hooks/retrohook"

# Añadir utils al PATH
for i in "${USERDATA}/resources/utils/"*; do
    if [ -f "$i/.bash" ] && [ -x "$i/.bash" ]; then
        PATH="$i:$PATH"
    fi
done

# Comprobar que el directorio de Retrobox es real
if [ ! -d "${USERDATA}" ]; then
    echo "[ERROR] Directorio de Retrobox no válido: ${USERDATA}"
    exit 1
fi

# Trap: delega el teardown en el hook on-frontend-stop
trap '"$RETROHOOK" _frontend emulationstation on-frontend-stop' EXIT

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
    RETROBOX_DISABLE_INTERNAL_DISPLAY=1
    export RETROBOX_DISABLE_INTERNAL_DISPLAY
fi

# Hook de inicio (setup de pantalla, syncs, covers, .ini, etc.)
"$RETROHOOK" _frontend emulationstation on-frontend-start "$@"

cd "${USERDATA}/frontend" || exit 1
"${USERDATA}/frontend/emulationstation" --home "${USERDATA}/frontend" "$@"
