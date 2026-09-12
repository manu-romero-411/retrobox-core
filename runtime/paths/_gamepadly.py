"""runtime.paths constants related to gamepadly.

Since the change in gamepadly_manager.py, the `runtime.gamepadly` package
no longer imports anything from here — these constants are only consumed
by emulatorlauncher.py, which passes them as parameters when constructing
GamepadManager(...). They're kept in runtime.paths (rather than inside
the gamepadly package itself) because, conceptually, they're still
Retrobox installation paths — same as EMULATORS, BIOS, etc.
"""

from __future__ import annotations

from typing import Final

from ._base import RESOURCES_DIR, USERDATA

_GAMEPADLY_DIR: Final = USERDATA / "runtime" / "gamepadly"
_GAMEPADLY_PROFILES: Final = RESOURCES_DIR / "pad2key" / "profiles"
_GAMEPADLY_USER_PROFILES: Final = _GAMEPADLY_DIR / "pad2key" / "user_profiles"
GAMEPADLY_MAPPER: Final = _GAMEPADLY_DIR / "gamepadly_mapper.py"
