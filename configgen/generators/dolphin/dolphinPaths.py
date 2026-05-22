from __future__ import annotations
from pathlib import Path
from typing import Final
from ...batoceraPaths import BIOS, CONFIGS, SAVES

DOLPHIN_BIN:     Final = Path('/usr/local/bin/dolphin-emu')
DOLPHIN_CONFIG:  Final = CONFIGS / 'dolphin-emu'
DOLPHIN_DATA:    Final = SAVES / 'dolphin-emu'

DOLPHIN_INI:     Final = DOLPHIN_CONFIG / 'Dolphin.ini'
DOLPHIN_GFX_INI: Final = DOLPHIN_CONFIG / 'GFX.ini'
DOLPHIN_QT_INI:  Final = DOLPHIN_CONFIG / 'Qt.ini'

DOLPHIN_SAVES:   Final = SAVES / 'dolphin-emu'
DOLPHIN_SYSCONF: Final = DOLPHIN_DATA / 'Wii' / 'shared2' / 'sys' / 'SYSCONF'
DOLPHIN_BIOS:    Final = BIOS / 'GC'