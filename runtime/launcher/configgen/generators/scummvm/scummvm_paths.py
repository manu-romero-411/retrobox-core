from typing import Final

from runtime.paths import BIOS, EMULATORS, SAVES


_SCUMMVM_DIR: Final = EMULATORS / "scummvm"
_SCUMMVM_XDG: Final = _SCUMMVM_DIR / "configs"
_SCUMMVM_CFGDIR: Final = _SCUMMVM_XDG / "scummvm"
SCUMMVM_CFG: Final = _SCUMMVM_CFGDIR / "scummvm.ini"
_SCUMMVM_EXTRA: Final = BIOS / "scummvm" / "extra"
_SCUMMVM_SAVES: Final = SAVES / "scummvm"
