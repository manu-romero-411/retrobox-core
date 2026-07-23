from typing import Final

from configgen.retrobox_paths import BIOS, EMULATORS

_PCSX2_DIR: Final = EMULATORS / 'pcsx2'
_PCSX2_XDG: Final = _PCSX2_DIR / 'config'
_PCSX2_CFGDIR: Final = _PCSX2_XDG / 'PCSX2'
_PCSX2_BIOS: Final = BIOS / "pcsx2" / "bios"
PCSX2_BIN: Final = _PCSX2_DIR / "app" / "AppRun"
