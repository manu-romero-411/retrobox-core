from pathlib import Path

from runtime.retrobox_paths import EMULATORS, SAVES, SCREENSHOTS

_ARES_EMUDIR: Path = EMULATORS / "ares"
_ARES_XDG: Path = _ARES_EMUDIR / "configs"
_ARES_CFGDIR: Path = _ARES_XDG / "ares"
_ARES_LIBDIR: Path = _ARES_EMUDIR / "lib"
_ARES_CFG: Path = _ARES_CFGDIR / "settings.bml"
_ARES_SHADERS_DIR: Path = _ARES_EMUDIR / "share" / "ares" / "Shaders"

_ARES_SAVES: Path = SAVES
_ARES_SCREENSHOTS: Path = SCREENSHOTS

ARES_BIN: Path = _ARES_EMUDIR / "bin" / "ares"
