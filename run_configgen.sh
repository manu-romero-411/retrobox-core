#!/usr/bin/env bash
unset LD_PRELOAD

CONFIGGEN_DIR="/home/manuel/proyectos/batocera-configgen"
PYTHON="$CONFIGGEN_DIR/.venv/bin/python"

export PATH="$CONFIGGEN_DIR:$PATH"

cd "$CONFIGGEN_DIR"
"$PYTHON" -m configgen.sync_settings
mkdir -p /tmp/batocera-run/{squashfs,evmapy,overlays,mame_software,mame_artwork,cmdfiles,shader_bezels,batocera-overlays}
exec "$PYTHON" -m configgen.emulatorlauncher "$@"
#exec "$PYTHON" -m configgen.emulatorlauncher "$@" 2>&1 | grep -i 'bezel\|decoration\|overlay'