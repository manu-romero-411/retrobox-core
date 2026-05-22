#!/usr/bin/env bash
unset LD_PRELOAD

CONFIGGEN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
#PYTHON="$CONFIGGEN_DIR/.venv/bin/python"
PYTHON=$(which python3)

# Fuerza a las AppImages a extraerse y ejecutarse sin requerir FUSE dentro del contenedor
export APPIMAGE_EXTRACT_AND_RUN=1

cd "$CONFIGGEN_DIR"
#"$PYTHON" -m configgen.sync_settings
mkdir -p /tmp/batocera-run/{squashfs,evmapy,overlays,mame_software,mame_artwork,cmdfiles,shader_bezels,batocera-overlays}
exec "$PYTHON" -m configgen.emulatorlauncher "$@"
#exec "$PYTHON" -m configgen.emulatorlauncher "$@" 2>&1 | grep -i 'bezel\|decoration\|overlay'
