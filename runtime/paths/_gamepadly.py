"""
Constantes de runtime.paths relativas a gamepadly.

Tras el cambio en gamepadly_manager.py, el paquete `runtime.gamepadly` ya
no importa nada de aquí — estas constantes las consume únicamente
emulatorlauncher.py, que las pasa por parámetro al construir
GamepadManager(...). Se mantienen en retrobox_paths (y no dentro del
propio paquete gamepadly) porque siguen siendo, conceptualmente, paths de
instalación de Retrobox — igual que EMULATORS, BIOS, etc.
"""

from __future__ import annotations

from typing import Final

from ._base import RESOURCES_DIR, USERDATA

_GAMEPADLY_DIR: Final = USERDATA / "runtime" / "gamepadly"
_GAMEPADLY_PROFILES: Final = RESOURCES_DIR / "pad2key" / "profiles"
_GAMEPADLY_USER_PROFILES: Final = _GAMEPADLY_DIR / "pad2key" / "user_profiles"
GAMEPADLY_MAPPER: Final = _GAMEPADLY_DIR / "gamepadly_mapper.py"