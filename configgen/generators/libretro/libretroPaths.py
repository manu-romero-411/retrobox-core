from __future__ import annotations

from pathlib import Path
from typing import Final

from ...batoceraPaths import CONF_INIT, CONFIGS

RETROARCH_CONFIG: Final = CONFIGS / 'retroarch'
RETROARCH_CUSTOM: Final = RETROARCH_CONFIG / 'retroarchcustom.cfg'
RETROARCH_CORE_CUSTOM: Final = RETROARCH_CONFIG / 'cores' / 'retroarch-core-options.cfg'
RETROARCH_OVERLAY_CONFIG: Final = RETROARCH_CONFIG / 'overlay.cfg'

RETROARCH_BIN: Final = Path("/opt/retroarch/RetroArch-Linux-x86_64.AppImage")

_RETROARCH: Final = Path.home() / '.config' / 'retroarch'
RETROARCH_CORES: Final = _RETROARCH / 'cores'
RETROARCH_SHARE: Final = _RETROARCH / 'cores'   # los .info están aquí también en instalación normal
RETROARCH_ASSETS:    Final = _RETROARCH / 'assets'
RETROARCH_AUTOCONFIG: Final = _RETROARCH / 'autoconfig'