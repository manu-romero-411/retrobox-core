from __future__ import annotations

from typing import Final

from runtime.paths import EMULATORS, BIOS, SAVES

_FSUAE_EMUDIR: Final = EMULATORS / 'fs-uae'
_FSUAE_XDG: Final = _FSUAE_EMUDIR / 'configs'
FSUAE_CONFIG_DIR: Final = _FSUAE_XDG / 'fs-uae'
FSUAE_BIOS_DIR: Final = BIOS / 'amiga'
FSUAE_SAVES: Final = SAVES / 'amiga'
