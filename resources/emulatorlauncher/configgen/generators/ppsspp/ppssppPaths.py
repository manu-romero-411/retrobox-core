from __future__ import annotations

from typing import Final

from ...retrobox_paths import CONF_INIT, EMULATORS, SAVES

_PPSSPP_EMUDIR: Final = EMULATORS / 'ppsspp'
_PPSSPP_XDG: Final = _PPSSPP_EMUDIR / 'config'
PPSSPP_BIN: Final = _PPSSPP_EMUDIR / 'app' / 'AppRun'
_PPSSPP_CFGDIR: Final = _PPSSPP_XDG / 'ppsspp'
_PPSSPP_PSPDIR: Final = SAVES / 'psp'
_PPSSPP_SYSDIR: Final =  _PPSSPP_PSPDIR / 'SYSTEM'
PPSSPP_CONFIG_INIT: Final = CONF_INIT / 'ppsspp' / 'PSP' / 'SYSTEM'
