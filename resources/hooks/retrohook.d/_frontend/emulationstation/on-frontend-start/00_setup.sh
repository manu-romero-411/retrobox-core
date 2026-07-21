#!/usr/bin/env bash
# Hook: frontend start
# Se ejecuta desde retrobox.sh antes de lanzar EmulationStation.

# Crear config de emulationstation (oneshot: solo si no existe)
if [ ! -d "${USERDATA}/frontend/.emulationstation" ]; then
    mkdir -p "${USERDATA}/frontend/.emulationstation"
    cp -r "${USERDATA}/frontend/share/emulationstation/." \
          "${USERDATA}/frontend/.emulationstation/" 2>/dev/null || true
fi

cat << EOF > "${USERDATA}/frontend/.emulationstation/emulationstation.ini"
# Ficheros
config=${USERDATA}/batocera.conf
# Raíz y logs
root=${USERDATA}
log=${USERDATA}/logs
# ROMs y saves
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
# Audiofilters
audiofilters=${USERDATA}/emulators/retroarch/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/filters/audio
# RetroAchievement sounds
retroachievementsounds=${USERDATA}/frontend/retroachievements-sounds
# Padtokey (gamepadly)
system.padtokey=${USERDATA}/resources/utils/gamepadly/profiles
padtokey=${USERDATA}/resources/utils/gamepadly/user_profiles
# Zonas horarias
timezones=/usr/share/zoneinfo
EOF

# Sincronización de juegos de PC
"${USERDATA}/resources/utils/steamgriddb_downloader/pcgames-cover-restore"
"${USERDATA}/resources/utils/pcgames-sync/heroic-es-sync" || true
"${USERDATA}/resources/utils/pcgames-sync/lutris-es-sync"  || true
"${USERDATA}/resources/utils/pcgames-sync/steam-es-sync"   || true
