from typing import Final

from runtime.retrobox_paths import EMULATORS

_OPENMSX_INST: Final = EMULATORS / 'openmsx'
_OPENMSX_XDG: Final = _OPENMSX_INST / 'configs'
_OPENMSX_HOMEDIR: Final = _OPENMSX_XDG / 'openmsx'
_OPENMSX_CFGDIR: Final = _OPENMSX_INST
