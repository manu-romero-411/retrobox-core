from __future__ import annotations

from pathlib import Path
from typing import Final

from ...batoceraPaths import BIOS, EMULATORS, ROMS, SAVES

_CEMU_EMUDIR: Final  = EMULATORS / 'cemu'
_CEMU_XDG: Final = _CEMU_EMUDIR / 'configs'
CEMU_BIN: Final  = _CEMU_EMUDIR / 'cemu.AppImage'
CEMU_CONFIG: Final  = _CEMU_XDG / 'Cemu'
CEMU_ROMDIR: Final = ROMS / 'wiiu'
CEMU_SAVES: Final = SAVES / 'wiiu'
CEMU_BIOS: Final = BIOS / 'cemu'
#CEMU_DATA_DIR: Final = Path('/usr/bin/cemu')
CEMU_CONTROLLER_PROFILES: Final = CEMU_CONFIG / 'controllerProfiles'
