
from pathlib import Path
from typing import Final

from runtime.paths import EMULATORS


_PYXEL_DIR: Final = EMULATORS / "pyxel"
_PYXEL_XDG: Final = _PYXEL_DIR / "configs"
_PYXEL_CFGDIR: Final = _PYXEL_XDG / "pyxel"
PYXEL_BIN = Path("/usr/bin/pyxel")
