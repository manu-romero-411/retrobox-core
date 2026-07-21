from pathlib import Path
from typing import Final

from configgen.retrobox_paths import EMULATORS


_DOSBOX_DIR: Final = EMULATORS / 'dosbox'
_DOSBOX_XDG: Final = _DOSBOX_DIR / 'configs'
_DOSBOX_CFGDIR: Final = _DOSBOX_XDG / 'dosbox'
# Use a separate file from dosbox.conf to avoid overwriting by dosbox
DOSBOX_CFG: Final = _DOSBOX_CFGDIR / 'dosbox-custom.conf'
DOSBOX_BIN: Final = Path("/usr/bin/dosbox")