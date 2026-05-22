# edenPaths.py
import os
from pathlib import Path
from configgen.batoceraPaths import BIOS, CONFIGS, ROMS, SAVES, _XDG_DATA, mkdir_if_not_exists

# --- Definición de Rutas Base ---
SWITCH_BIOS = os.path.join(BIOS, "switch")
SWITCH_KEYS = os.path.join(SWITCH_BIOS, "keys")
SWITCH_FIRMWARE = os.path.join(SWITCH_BIOS, "firmware")

EDEN_DATA = os.path.join(_XDG_DATA, "eden")
EDEN_KEYS = os.path.join(EDEN_DATA, "keys")
EDEN_REGISTERED = os.path.join(EDEN_DATA, "nand/system/Contents/registered")

UPDATE_DIR = os.path.join(ROMS, "switch_update")
DLC_DIR = os.path.join(UPDATE_DIR, "dlc")
UPDATES_DIR = os.path.join(UPDATE_DIR, "update")
SWITCH_ROMS = os.path.join(ROMS, "switch")

# Rutas de Guardado y Mods
SAVE_BASE = os.path.join(SAVES, "switch/eden_citron")
USER_SAVE_TARGET = os.path.join(SAVE_BASE, "save/save_user")
SYSTEM_SAVE_TARGET = os.path.join(SAVE_BASE, "save/save_system")
MODS_TARGET = os.path.join(SAVE_BASE, "mods")

EDEN_USER_SAVE_LINK = os.path.join(EDEN_DATA, "nand/user/save")
EDEN_SYSTEM_SAVE_LINK = os.path.join(EDEN_DATA, "nand/system/save")
EDEN_MODS_LINK = os.path.join(EDEN_DATA, "load")

YUZU_CONFIG_FILE = os.path.join(CONFIGS, 'yuzu/qt-config.ini')

def ensure_symlink(target, link_path):
    """Crea o actualiza un enlace simbólico de forma segura."""
    import shutil
    if os.path.exists(link_path):
        if not os.path.islink(link_path):
            shutil.rmtree(link_path)
            os.symlink(target, link_path)
        else:
            if os.readlink(link_path) != target:
                os.unlink(link_path)
                os.symlink(target, link_path)
    else:
        # Asegurar que el directorio padre del enlace existe
        os.makedirs(os.path.dirname(link_path), exist_ok=True)
        os.symlink(target, link_path)

def setup_eden_environments():
    """Inicializa todos los directorios requeridos y enlaces simbólicos."""
    # 1. Crear Directorios necesarios
    dirs_to_create = [
        SWITCH_BIOS, SWITCH_KEYS, SWITCH_FIRMWARE,
        EDEN_DATA, os.path.join(EDEN_DATA, "nand/system/Contents"),
        UPDATE_DIR, DLC_DIR, UPDATES_DIR, SWITCH_ROMS,
        USER_SAVE_TARGET, SYSTEM_SAVE_TARGET, MODS_TARGET
    ]
    
    for d in dirs_to_create:
        mkdir_if_not_exists(Path(d))

    # 2. Desplegar Enlaces Simbólicos (Symlinks)
    ensure_symlink(SWITCH_KEYS, EDEN_KEYS)
    ensure_symlink(SWITCH_FIRMWARE, EDEN_REGISTERED)
    ensure_symlink(USER_SAVE_TARGET, EDEN_USER_SAVE_LINK)
    ensure_symlink(SYSTEM_SAVE_TARGET, EDEN_SYSTEM_SAVE_LINK)
    ensure_symlink(MODS_TARGET, EDEN_MODS_LINK)