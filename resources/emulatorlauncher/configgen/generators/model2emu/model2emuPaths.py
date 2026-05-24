import os
from pathlib import Path
from typing import Final
from configgen.batoceraPaths import _SYSTEM_LOCAL_BIN, BIOS, CONFIGS, DEFAULTS_DIR, ROMS, SAVES, _XDG_DATA, ensure_symlink, mkdir_if_not_exists

MODEL2_ROMS: Final = ROMS / "model2"

M2EMU_WINEPREFIX: Final = Path("/opt/model2emu")
M2EMU_EMUDIR: Final = M2EMU_WINEPREFIX / "drive_c" / "model2emu"
M2EMU_RESOURCES: Final = DEFAULTS_DIR / "data" / "model2emu"