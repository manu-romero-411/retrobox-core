from __future__ import annotations

from pathlib import Path
from typing import Final

from runtime.retrobox_paths import SAVES, EMULATORS

XEMU_BIN: Final = Path('/usr/bin/xemu')
XEMU_SAVES: Final = SAVES / 'xbox'
XEMU_CONFIG: Final = EMULATORS / 'xemu' / 'xemu.toml'
