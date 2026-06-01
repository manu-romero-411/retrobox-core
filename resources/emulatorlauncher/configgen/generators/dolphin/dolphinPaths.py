from __future__ import annotations
from pathlib import Path
from typing import Final
from ...batoceraPaths import BIOS, CONFIGS, EMULATORS, SAVES

DOLPHIN_BIN:     Final = EMULATORS / 'dolphin-emu' / 'dolphin.AppImage'
DOLPHIN_XDG:  Final = EMULATORS / 'dolphin-emu' / 'config'
DOLPHIN_CONFIG:  Final = DOLPHIN_XDG / 'dolphin-emu'
DOLPHIN_DATA:    Final = SAVES / 'dolphin-emu'

DOLPHIN_INI:     Final = DOLPHIN_CONFIG / 'Dolphin.ini'
DOLPHIN_GFX_INI: Final = DOLPHIN_CONFIG / 'GFX.ini'
DOLPHIN_QT_INI:  Final = DOLPHIN_CONFIG / 'Qt.ini'

DOLPHIN_SAVES:   Final = SAVES / 'dolphin-emu'
DOLPHIN_SYSCONF: Final = DOLPHIN_DATA / 'Wii' / 'shared2' / 'sys' / 'SYSCONF'
DOLPHIN_BIOS:    Final = BIOS / 'GC'