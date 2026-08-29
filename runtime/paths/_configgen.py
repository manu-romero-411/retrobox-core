"""
Constantes de runtime.paths consumidas por configgen y por
emulatorlauncher.py: directorios de contenido de emuladores (bios, saves,
screenshots...), estado efímero de una sesión de juego (RUNTIME_DIR y sus
subdirectorios) y scripts/utilidades del sistema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from ._base import RESOURCES_DIR, USERDATA, check_env_dirs

EMU_FEATURES_DIR: Final = RESOURCES_DIR / "emu_features"
SYSTEMS_CONF_DIR: Final = RESOURCES_DIR / "systems_config"

# directories for emulator things
SAVES: Final = check_env_dirs("SAVES_DIR", USERDATA / "saves")
SCREENSHOTS: Final = check_env_dirs("SCREENSHOTS_DIR", USERDATA / "screenshots")
RECORDINGS: Final = check_env_dirs("RECORDINGS_DIR", USERDATA / "recordings")
BIOS: Final = check_env_dirs("BIOS_DIR", USERDATA / "bios")
OVERLAYS: Final = check_env_dirs("OVERLAYS_DIR", USERDATA / "overlay")
CHEATS: Final = check_env_dirs("CHEATS_DIR", USERDATA / "cheats")

_SHADERS_DIR: Final = check_env_dirs("SHADERS_DIR", USERDATA / "shaders")
_SHADERS_DEF_DIR: Final = check_env_dirs("SHADERS_DEFAULT_DIR", RESOURCES_DIR / "shaders")

_DECORATIONS_DIR: Final = check_env_dirs("BEZELS_DIR", USERDATA / "decorations")
_DECORATIONS_DEF_DIR: Final = check_env_dirs("BEZELS_DEFAULT_DIR", RESOURCES_DIR / "decorations")

_SYSTEM_SCRIPTS: Final = RESOURCES_DIR / "scripts"
UTILS_DIR: Final = RESOURCES_DIR / "utils"

NVIDIA_POWERD_SCRIPT: Final = UTILS_DIR / "nvidia-powerd-service"

# Runtime dir (estado efímero de una sesión de juego en curso)
RUNTIME_DIR: Final = Path("/tmp/retrobox-run")

SQUASHFS_DIR: Final = RUNTIME_DIR / "squashfs"
ROTATION_FILE: Final = RUNTIME_DIR / "rk-rotation"
OVERLAY_BASE_DIR: Final = RUNTIME_DIR / "overlays"
MAME_SOFTWARE_DIR: Final = RUNTIME_DIR / "mame_software"
MAME_ARTWORK_DIR: Final = RUNTIME_DIR / "mame_artwork"
CMDFILES_DIR: Final = RUNTIME_DIR / "cmdfiles"
SHADER_BEZELS_DIR: Final = RUNTIME_DIR / "shader_bezels"
HUD_CONFIG_FILE: Final = RUNTIME_DIR / "hud.config"
GUN_OVERLAYS_DIR: Final = RUNTIME_DIR / "batocera-overlays"


def configure_emulator(rom: Path, /) -> bool:
    return str(rom) == "config" or rom.suffix == ".menu"