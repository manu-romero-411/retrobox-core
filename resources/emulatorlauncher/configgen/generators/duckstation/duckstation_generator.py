
from typing import Final

from configgen.retrobox_paths import EMULATORS

_DUCKSTATION_DIR: Final = EMULATORS / "duckstation"
_DUCKSTATION_XDG: Final = _DUCKSTATION_DIR / "configs"
_DUCKSTATION_CFGDIR: Final = _DUCKSTATION_XDG / "duckstation"
DUCKSTATION_CFG: Final = _DUCKSTATION_CFGDIR / "settings.ini"
DUCKSTATION_BIN: Final = "CONFIGS / settings.ini"
