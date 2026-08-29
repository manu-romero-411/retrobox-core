from typing import Final

from runtime.paths import EMULATORS


_DOSBOX_X_EMUDIR: Final = EMULATORS / 'dosbox-x'
_DOSBOX_X_XDG: Final = _DOSBOX_X_EMUDIR / "configs"
_DOSBOX_X_CFGDIR: Final = _DOSBOX_X_XDG / "dosbox"
_DOSBOX_X_CFG: Final = _DOSBOX_X_CFGDIR / 'dosboxx.conf'
