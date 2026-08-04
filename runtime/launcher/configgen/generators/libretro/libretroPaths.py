from __future__ import annotations

from typing import Final

from runtime.retrobox_paths import EMULATORS

# directorios y ejecutable de retroarch y su config
_RETROARCH_DIR: Final = EMULATORS / "retroarch"
_RETROARCH_BIN: Final = _RETROARCH_DIR / "app" / "bin" / "retroarch"
_RETROARCH_XDG: Final = _RETROARCH_DIR / "config"
_RETROARCH_CONFIG: Final = _RETROARCH_XDG / "retroarch"

_RETROARCH_SHARE: Final = _RETROARCH_DIR / "app" / "share" / "retroarch"

# configs de retroarch que generamos en el configgen
RETROARCH_CUSTOM: Final = _RETROARCH_CONFIG / 'retroarchcustom.cfg'
RETROARCH_CORE_CUSTOM: Final = _RETROARCH_CONFIG / 'cores' / 'retroarch-core-options.cfg'
RETROARCH_OVERLAY_CONFIG: Final = _RETROARCH_CONFIG / 'overlay.cfg'
RETROARCH_BASE_CONFIG: Final = _RETROARCH_CONFIG / 'retroarch.cfg'

# assets de retroarch
RETROARCH_CORES: Final = _RETROARCH_SHARE / 'cores'
RETROARCH_SHARE: Final = _RETROARCH_SHARE / 'cores'
RETROARCH_ASSETS:    Final = _RETROARCH_SHARE / 'assets'
RETROARCH_AUTOCONFIG: Final = _RETROARCH_SHARE / 'autoconfig'
RETROARCH_SHADERS: Final = _RETROARCH_SHARE / 'shaders'

_RETROARCH_VIDEO_FILTERS: Final = _RETROARCH_SHARE / 'filters' / 'video'
_RETROARCH_AUDIO_FILTERS: Final = _RETROARCH_SHARE / 'filters' / 'audio'