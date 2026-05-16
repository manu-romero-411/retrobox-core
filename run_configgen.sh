#!/usr/bin/env bash

unset LD_PRELOAD

CONFIGGEN_DIR="/home/manuel/proyectos/batocera-configgen"
PYTHON="$CONFIGGEN_DIR/.venv/bin/python"

export PATH="$CONFIGGEN_DIR:$PATH"

mkdir -p /tmp/batocera-run/{squashfs,evmapy,overlays,mame_software,mame_artwork,cmdfiles,shader_bezels,batocera-overlays}

# Sincronizar es_settings.cfg → batocera.conf
"$PYTHON" - << 'EOF'
import xml.etree.ElementTree as ET
from pathlib import Path

es_settings = Path.home() / '.emulationstation' / 'es_settings.cfg'
batocera_conf = Path.home() / '.local/share/batocera/batocera.conf'

SKIP_PREFIXES = ('INPUT ', 'Last', 'Show', 'Theme', 'Audio', 'Brightness',
                 'Clock', 'Power', 'Scraper', 'UI', 'Video', 'Window')

try:
    tree = ET.parse(es_settings)
    lines = []
    for el in tree.getroot():
        name  = el.get('name', '')
        value = el.get('value', '')
        if any(name.startswith(p) for p in SKIP_PREFIXES):
            continue
        lines.append(f'{name}={value}')
    batocera_conf.write_text('\n'.join(lines) + '\n', encoding='latin1')
except Exception as e:
    print(f'[run_configgen] WARNING: {e}')
EOF

cd "$CONFIGGEN_DIR"
exec "$PYTHON" -m configgen.emulatorlauncher "$@"
exit $?