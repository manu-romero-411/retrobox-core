from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final, overload

if TYPE_CHECKING:
    from _typeshed import OpenBinaryModeUpdating, OpenBinaryModeWriting, OpenTextModeUpdating, OpenTextModeWriting
    from collections.abc import Iterator
    from io import BufferedRandom, BufferedWriter, TextIOWrapper

# ---------------------------------------------------------------------------
# Helpers XDG
# ---------------------------------------------------------------------------
_USER_HOME:   Final = Path.home()
_XDG_DATA:   Final = Path.home() / '.local' / 'share'
_XDG_CACHE:  Final = Path.home() / '.cache'
_XDG_CONFIG: Final = Path.home() / '.config'
_SYSTEM_LOCAL_BIN: Final = Path('/usr/local/bin')
_SYSTEM_LOCAL_SHARE: Final = Path('/usr/local/share')

# ---------------------------------------------------------------------------
# Paths de instalación del sistema (igual que en batocera)
# ---------------------------------------------------------------------------
BATOCERA_ROOT:  Final = _XDG_DATA / 'batocera'
BATOCERA_SHARE_DIR:  Final = BATOCERA_ROOT / 'resources'
DATAINIT_DIR:        Final = BATOCERA_SHARE_DIR / 'datainit'
BATOCERA_ES_DIR:     Final = Path('/home/manuel/proyectos/batocera-emulationstation/appimage/es')
CONFIGGEN_DATA_DIR:  Final = BATOCERA_SHARE_DIR / "configgen/data"
DEFAULTS_DIR: Final = Path('/home/manuel/proyectos/batocera-configgen')

HOME_INIT:  Final = DATAINIT_DIR / 'system'
CONF_INIT:  Final = HOME_INIT / 'configs'

# ---------------------------------------------------------------------------
# "userdata" → $HOME
# ---------------------------------------------------------------------------
USERDATA: Final = BATOCERA_ROOT
ROMS:     Final = USERDATA / 'roms'          # ajusta si los tienes en otro sitio

# ---------------------------------------------------------------------------
# "system" de batocera → ~/.local/share/batocera  (estado interno del port)
# ---------------------------------------------------------------------------
HOME:  Final = _XDG_DATA / 'batocera'
CACHE: Final = _XDG_CACHE / 'batocera'
LOGS:  Final = HOME / 'logs'

BATOCERA_CONF: Final = HOME / 'batocera.conf'
USER_SCRIPTS:  Final = HOME / 'scripts'

# ---------------------------------------------------------------------------
# Configs de emuladores → ~/.config  (XDG; retroarch ya vive en ~/.config/retroarch)
# ---------------------------------------------------------------------------
CONFIGS: Final = _XDG_CONFIG
EVMAPY:  Final = CONFIGS / 'evmapy'

SAVES:       Final = USERDATA / 'saves'
SCREENSHOTS: Final = USERDATA / 'screenshots'
RECORDINGS:  Final = USERDATA / 'recordings'
BIOS:        Final = USERDATA / 'bios'       # "system directory" de retroarch
OVERLAYS:    Final = USERDATA / 'overlay'
CHEATS:      Final = USERDATA / 'cheats'

USER_SHADERS:    Final = USERDATA / 'shaders'
USER_DECORATIONS:  Final = USERDATA / 'decorations'
# ---------------------------------------------------------------------------
# EmulationStation → ~/.emulationstation  (ES lo fija, no es configurable)
# ---------------------------------------------------------------------------
USER_ES_DIR: Final = USERDATA / '.emulationstation'
ES_SETTINGS: Final = USER_ES_DIR / 'es_settings.cfg'

# ---------------------------------------------------------------------------
# Recursos de ES y configgen (sistema)
# ---------------------------------------------------------------------------
_ES_RESOURCES_DIR:   Final = BATOCERA_ES_DIR / 'resources'
ES_GUNS_METADATA:    Final = _ES_RESOURCES_DIR / 'gungames.xml'
ES_WHEELS_METADATA:  Final = _ES_RESOURCES_DIR / 'wheelgames.xml'
ES_GAMES_METADATA:   Final = _ES_RESOURCES_DIR / 'gamesdb.xml'
ES_GUNS_ART_METADATA: Final = CONFIGGEN_DATA_DIR / 'gamesbuttonsdb.xml'

BATOCERA_SHADERS:    Final = BATOCERA_SHARE_DIR / 'shaders'
SYSTEM_DECORATIONS:  Final = DATAINIT_DIR / 'decorations'
SYSTEM_SCRIPTS:      Final = DEFAULTS_DIR / 'scripts'

# Runtime dir (en batocera es /var/run, en Debian usamos /tmp)
RUNTIME_DIR: Final = Path('/tmp/batocera-run')

SQUASHFS_DIR:      Final = RUNTIME_DIR / 'squashfs'
EVMAPY_RUN_DIR:    Final = RUNTIME_DIR / 'evmapy'
EVMAPY_MERGED:     Final = RUNTIME_DIR / 'evmapy_merged.keys'
ROTATION_FILE:     Final = RUNTIME_DIR / 'rk-rotation'
OVERLAY_BASE_DIR:  Final = RUNTIME_DIR / 'overlays'
MAME_SOFTWARE_DIR: Final = RUNTIME_DIR / 'mame_software'
MAME_ARTWORK_DIR:  Final = RUNTIME_DIR / 'mame_artwork'
CMDFILES_DIR:      Final = RUNTIME_DIR / 'cmdfiles'
SHADER_BEZELS_DIR: Final = RUNTIME_DIR / 'shader_bezels'
HUD_CONFIG_FILE:   Final = RUNTIME_DIR / 'hud.config'
GUN_OVERLAYS_DIR:  Final = RUNTIME_DIR / 'batocera-overlays'
HOTKEYGEN_BIN: Final = Path.home() / '.local' / 'bin' / 'hotkeygen'

# ---------------------------------------------------------------------------
# Utilidades (sin cambios)
# ---------------------------------------------------------------------------
def configure_emulator(rom: Path, /) -> bool:
    return str(rom) == 'config'

def mkdir_if_not_exists(dir: Path, /) -> None:
    if not dir.exists():
        dir.mkdir(parents=True)

@overload
@contextmanager
def ensure_parents_and_open(file: Path, mode: OpenTextModeWriting | OpenTextModeUpdating) -> Iterator[TextIOWrapper]: ...
@overload
@contextmanager
def ensure_parents_and_open(file: Path, mode: OpenBinaryModeUpdating) -> Iterator[BufferedRandom]: ...
@overload
@contextmanager
def ensure_parents_and_open(file: Path, mode: OpenBinaryModeWriting) -> Iterator[BufferedWriter]: ...

@contextmanager
def ensure_parents_and_open(file: Path, mode: str) -> Iterator[IO[Any]]:
    mkdir_if_not_exists(file.parent)
    with file.open(mode) as f:
        yield f