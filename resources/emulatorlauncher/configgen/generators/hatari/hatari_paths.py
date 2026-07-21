# libretro generator uses this, so it needs to be public

from typing import Final

from configgen.retrobox_paths import EMULATORS

_HATARI_DIR: Final = EMULATORS / "hatari"
_HATARI_XDG: Final = _HATARI_DIR / "configs"
_HATARI_CFGDIR: Final = _HATARI_XDG / "hatari"
HATARI_CFG: Final = _HATARI_CFGDIR / "hatari.cfg"
