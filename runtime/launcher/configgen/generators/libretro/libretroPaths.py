from __future__ import annotations

from typing import Final

from runtime.retrobox_paths import EMULATORS

# directorios y ejecutable de retroarch y su config
_RETROARCH_DIR: Final = EMULATORS / "retroarch"
_RETROARCH_BIN: Final = _RETROARCH_DIR / "app" / "AppRun"
_RETROARCH_XDG: Final = _RETROARCH_DIR / "configs"
_RETROARCH_CONFIG: Final = _RETROARCH_XDG / "retroarch"

# como estamos tirando de appimage, el root de retroarch
# (donde están los assets, shaders, etc.) es el mismo que la config.
# Separo ambas variables por si alguien prefiere instalar retroarch en modo sistema
# (como lo trae batocera) o quiere explorar alternativas como flatpak.
_RETROARCH_ROOT: Final = _RETROARCH_CONFIG

# configs de retroarch que generamos en el configgen
RETROARCH_CUSTOM: Final = _RETROARCH_CONFIG / 'retroarchcustom.cfg'
RETROARCH_CORE_CUSTOM: Final = _RETROARCH_CONFIG / 'cores' / 'retroarch-core-options.cfg'
RETROARCH_OVERLAY_CONFIG: Final = _RETROARCH_CONFIG / 'overlay.cfg'
RETROARCH_BASE_CONFIG: Final = _RETROARCH_CONFIG / 'retroarch.cfg'

# assets de retroarch
RETROARCH_CORES: Final = _RETROARCH_ROOT / 'cores'
RETROARCH_SHARE: Final = _RETROARCH_ROOT / 'cores'
RETROARCH_ASSETS:    Final = _RETROARCH_ROOT / 'assets'
RETROARCH_AUTOCONFIG: Final = _RETROARCH_ROOT / 'autoconfig'
RETROARCH_SHADERS: Final = _RETROARCH_ROOT / 'shaders'

_RETROARCH_VIDEO_FILTERS: Final = _RETROARCH_ROOT / 'filters' / 'video'
_RETROARCH_AUDIO_FILTERS: Final = _RETROARCH_ROOT / 'filters' / 'audio'