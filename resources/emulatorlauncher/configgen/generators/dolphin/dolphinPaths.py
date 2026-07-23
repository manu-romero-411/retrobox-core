from __future__ import annotations
from pathlib import Path
from typing import Final
from ...retrobox_paths import BIOS, EMULATORS, SAVES

_DOLPHIN_DIR:  Final = EMULATORS / 'dolphin-emu'
_DOLPHIN_XDG:  Final = _DOLPHIN_DIR / 'config'
_DOLPHIN_CFGDIR:  Final = _DOLPHIN_XDG / 'dolphin-emu'
_DOLPHIN_DATA:    Final = SAVES / 'dolphin-emu'
#DOLPHIN_BIN: Final = _DOLPHIN_DIR / "dolphin.AppImage"
DOLPHIN_BIN:     Final = _DOLPHIN_DIR / 'AppDir' / 'AppRun.sh'
#DOLPHIN_BIN:     Final = _DOLPHIN_DIR / "dolphin-emu-nogui"
#DOLPHIN_BIN: Final = Path("/usr/bin/dolphin-emu")


DOLPHIN_INI:     Final = _DOLPHIN_CFGDIR / 'Dolphin.ini'
DOLPHIN_GFX_INI: Final = _DOLPHIN_CFGDIR / 'GFX.ini'
DOLPHIN_QT_INI:  Final = _DOLPHIN_CFGDIR / 'Qt.ini'

DOLPHIN_SAVES:   Final = SAVES / 'dolphin-emu'
DOLPHIN_SYSCONF: Final = _DOLPHIN_DATA / 'Wii' / 'shared2' / 'sys' / 'SYSCONF'
DOLPHIN_BIOS:    Final = BIOS / 'GC'