from typing import Final

from runtime.paths import EMULATORS

_BIGPEMU_DIR: Final = EMULATORS / 'bigpemu'
_BIGPEMU_XDG: Final = _BIGPEMU_DIR / 'configs'
_BIGPEMU_CFGDIR: Final = _BIGPEMU_XDG / 'bigpemu'
BIGPEMU_CFG: Final = _BIGPEMU_CFGDIR / "bigpemu" / "BigPEmuConfig.bigpcfg"
