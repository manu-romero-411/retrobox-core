from __future__ import annotations

from typing import Final

from ...batoceraPaths import CONF_INIT, CONFIGS, _SYSTEM_LOCAL_BIN

PPSSPP_BIN: Final = _SYSTEM_LOCAL_BIN / 'ppsspp'
PPSSPP_CONFIG_DIR: Final = CONFIGS / 'ppsspp'
PPSSPP_PSP_SYSTEM_DIR: Final = PPSSPP_CONFIG_DIR / 'PSP' / 'SYSTEM'
PPSSPP_CONFIG_INIT: Final = CONF_INIT / 'ppsspp' / 'PSP' / 'SYSTEM'
