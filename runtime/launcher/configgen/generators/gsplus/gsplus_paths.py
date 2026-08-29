
from typing import Final

from runtime.paths import EMULATORS


_GSPLUS_DIR: Final = EMULATORS / 'gsplus'
_GSPLUS_XDG: Final = _GSPLUS_DIR / 'configs'
_GSPLUS_CFGDIR: Final = _GSPLUS_XDG / 'GSplus'
GSPLUS_CFG: Final = _GSPLUS_CFGDIR / 'config.txt'
