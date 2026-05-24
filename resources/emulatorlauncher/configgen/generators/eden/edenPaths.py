# edenPaths.py
import os
from pathlib import Path
from typing import Final
from configgen.batoceraPaths import _SYSTEM_LOCAL_BIN, BIOS, CONFIGS, ROMS, SAVES, _XDG_DATA, ensure_symlink, mkdir_if_not_exists

# --- Base ---
SWITCH_BIOS: Final = BIOS / "switch"
SWITCH_KEYS: Final = SWITCH_BIOS / "keys"
SWITCH_FIRMWARE: Final = SWITCH_BIOS / "firmware"

EDEN_BIN: Final = _SYSTEM_LOCAL_BIN / "eden-emu"
EDEN_DATA: Final = SAVES / "switch" / "eden"
EDEN_KEYS: Final = EDEN_DATA / "keys"
EDEN_REGISTERED: Final = EDEN_DATA / "nand/system/Contents/registered"

SWITCH_UPDATE_DIR: Final = ROMS / "switch_update"
SWITCH_DLC_DIR: Final = SWITCH_UPDATE_DIR / "dlc"
SWITCH_UPDATES_DIR: Final = SWITCH_UPDATE_DIR / "update"
SWITCH_ROMS: Final = ROMS / "switch"
SWITCH_MODS_DIR: Final = SWITCH_UPDATE_DIR / "mods"

# Saves
SAVE_BASE: Final = EDEN_DATA
USER_SAVE_TARGET: Final = SAVE_BASE / "save/save_user"
SYSTEM_SAVE_TARGET: Final = SAVE_BASE / "save/save_system"

EDEN_USER_SAVE_LINK: Final = EDEN_DATA / "nand/user/save"
EDEN_SYSTEM_SAVE_LINK: Final = EDEN_DATA / "nand/system/save"
EDEN_MODS_LINK: Final = EDEN_DATA / "load"

YUZU_CONFIG_FILE: Final = CONFIGS / "yuzu/qt-config.ini"

def setup_eden_environments():
    """Inicializa todos los directorios requeridos y enlaces simbólicos."""
    # 1. Crear Directorios necesarios
    dirs_to_create = [
        SWITCH_BIOS, SWITCH_KEYS, SWITCH_FIRMWARE,
        EDEN_DATA, os.path.join(EDEN_DATA, "nand/system/Contents"),
        SWITCH_UPDATE_DIR, SWITCH_DLC_DIR, SWITCH_UPDATES_DIR, SWITCH_ROMS,
        USER_SAVE_TARGET, SYSTEM_SAVE_TARGET, SWITCH_MODS_DIR
    ]
    
    for d in dirs_to_create:
        mkdir_if_not_exists(Path(d))

    # 2. Desplegar Enlaces Simbólicos (Symlinks)
    ensure_symlink(SWITCH_KEYS, EDEN_KEYS)
    ensure_symlink(SWITCH_FIRMWARE, EDEN_REGISTERED)
    ensure_symlink(USER_SAVE_TARGET, EDEN_USER_SAVE_LINK)
    ensure_symlink(SYSTEM_SAVE_TARGET, EDEN_SYSTEM_SAVE_LINK)
    ensure_symlink(SWITCH_MODS_DIR, EDEN_MODS_LINK)