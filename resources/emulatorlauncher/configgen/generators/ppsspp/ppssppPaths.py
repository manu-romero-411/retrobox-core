from __future__ import annotations

from typing import Final

from ...batoceraPaths import CONF_INIT, CONFIGS, _SYSTEM_LOCAL_BIN, EMULATORS

_PPSSPP_EMUDIR: Final = EMULATORS / 'ppsspp'
_PPSSPP_XDG: Final = _PPSSPP_EMUDIR / 'configs'
PPSSPP_BIN: Final = _PPSSPP_EMUDIR / 'ppsspp.AppImage'
PPSSPP_CONFIG_DIR: Final = _PPSSPP_XDG / 'ppsspp'
PPSSPP_PSP_SYSTEM_DIR: Final = PPSSPP_CONFIG_DIR / 'PSP' / 'SYSTEM'
PPSSPP_CONFIG_INIT: Final = CONF_INIT / 'ppsspp' / 'PSP' / 'SYSTEM'
