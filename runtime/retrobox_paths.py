from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final, overload
import shutil

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
RETROBOX_ROOTDIR: Final = Path(
    os.environ.get('RETROBOX_ROOTDIR', Path(__file__).resolve().parents[1])
)
USERDATA: Final = RETROBOX_ROOTDIR

ENV_FILE = RETROBOX_ROOTDIR / ".env"

RESOURCES_DIR:  Final = RETROBOX_ROOTDIR / 'resources'
DATAINIT_DIR: Final = RESOURCES_DIR / 'datainit'
#BATOCERA_ES_DIR: Final = Path('/home/manuel/proyectos/batocera-emulationstation/appimage/es')
_FRONTEND_DIR: Final = RETROBOX_ROOTDIR / 'frontend'
DEFAULTS_DIR: Final = RESOURCES_DIR / 'configgen'

HOME_INIT:  Final = DATAINIT_DIR / 'system'
CONF_INIT:  Final = HOME_INIT / 'configs'
EMULATORS:  Final = USERDATA / 'emulators'

# ---------------------------------------------------------------------------
# "userdata" → $HOME
# ---------------------------------------------------------------------------
ROMS:     Final = USERDATA / 'roms'          # ajusta si los tienes en otro sitio

# ---------------------------------------------------------------------------
# "system" de batocera → ~/.local/share/batocera  (estado interno del port)
CACHE: Final = _XDG_CACHE / 'retrobox'
LOGS:  Final = USERDATA / 'logs'

HOOKS = USERDATA / "resources" / "hooks" / "retrohook"

# directories for emulator things
SAVES:       Final = USERDATA / 'saves'
SCREENSHOTS: Final = USERDATA / 'screenshots'
RECORDINGS:  Final = USERDATA / 'recordings'
BIOS:        Final = USERDATA / 'bios'
OVERLAYS:    Final = USERDATA / 'overlay'
CHEATS:      Final = USERDATA / 'cheats'

_SHADERS_DIR:    Final = USERDATA / 'shaders'
_SHADERS_USER_DIR: Final = _SHADERS_DIR
_DECORATIONS_DIR:  Final = USERDATA / 'decorations'
_DECORATIONS_USER_DIR: Final = _DECORATIONS_DIR

# EmulationStation
_USER_ES_DIR: Final = _FRONTEND_DIR / '.emulationstation'
ES_SETTINGS_CFG: Final = _USER_ES_DIR / 'es_settings.cfg'
ES_FEATURES_CFG: Final = _USER_ES_DIR  / "es_features.cfg"
ES_SYSTEMS_CFG: Final = _USER_ES_DIR  / "es_systems.cfg"
ES_INPUT_CFG: Final = _USER_ES_DIR  / "es_input.cfg"
ES_INI: Final = _USER_ES_DIR / "emulationstation.ini"

# Recursos de ES y configgen (sistema)
_ES_RESOURCES_DIR:   Final = _FRONTEND_DIR / 'resources'
_ES_FEATURES_DIR:   Final = _FRONTEND_DIR / 'emu_features'
_ES_SYSTEMS_DIR:   Final = _FRONTEND_DIR / 'systems_config'
ES_GUNS_METADATA:    Final = _ES_RESOURCES_DIR / 'gungames.xml'
ES_WHEELS_METADATA:  Final = _ES_RESOURCES_DIR / 'wheelgames.xml'
ES_GAMES_METADATA:   Final = _ES_RESOURCES_DIR / 'gamesdb.xml'
ES_GUNS_ART_METADATA: Final = DEFAULTS_DIR / 'data' / 'gamesbuttonsdb.xml'

_SYSTEM_SCRIPTS:      Final = RESOURCES_DIR / 'scripts'
_UTILS_DIR:      Final = RESOURCES_DIR / 'utils'

# Runtime dir
RUNTIME_DIR: Final = Path('/tmp/retrobox-run')

SQUASHFS_DIR:      Final = RUNTIME_DIR / 'squashfs'
ROTATION_FILE:     Final = RUNTIME_DIR / 'rk-rotation'
OVERLAY_BASE_DIR:  Final = RUNTIME_DIR / 'overlays'
MAME_SOFTWARE_DIR: Final = RUNTIME_DIR / 'mame_software'
MAME_ARTWORK_DIR:  Final = RUNTIME_DIR / 'mame_artwork'
CMDFILES_DIR:      Final = RUNTIME_DIR / 'cmdfiles'
SHADER_BEZELS_DIR: Final = RUNTIME_DIR / 'shader_bezels'
HUD_CONFIG_FILE:   Final = RUNTIME_DIR / 'hud.config'
GUN_OVERLAYS_DIR:  Final = RUNTIME_DIR / 'batocera-overlays'

# GAMEPADLY
_GAMEPADLY_DIR: Final = USERDATA / "runtime" / "gamepadly"
_GAMEPADLY_PROFILES:  Final = RESOURCES_DIR / "pad2key" / "profiles"
_GAMEPADLY_USER_PROFILES:  Final = _GAMEPADLY_DIR / "pad2key" / "user_profiles"
GAMEPADLY_MAPPER: Final = _GAMEPADLY_DIR / "gamepadly_mapper.py"

# Utilidades
def configure_emulator(rom: Path, /) -> bool:
    return str(rom) == 'config'

def mkdir_if_not_exists(dir):
    try:
        dir.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        # Si es un enlace simbólico roto, lo eliminamos y lo creamos de verdad
        if dir.is_symlink():
            dir.unlink()
            dir.mkdir(parents=True, exist_ok=True)
        else:
            # Si es un archivo regular, lo renombramos para no perder datos y creamos el directorio
            import time
            dir.rename(dir.with_name(f"{dir.name}.bak_{int(time.time())}"))
            dir.mkdir(parents=True, exist_ok=True)

def ensure_symlink(source: Path, link: Path) -> None:
    """
    Garantiza que exista un symlink: link -> source

    Seguridad:
    - No borra directorios no vacíos
    - Evita ciclos de symlinks
    - No toca nada si ya está correcto
    """

    source = source.resolve()
    link = link

    # --- 1. Evitar auto-referencia ---
    if link.resolve() == source:
        return

    # --- 2. Detectar ciclos (link dentro de source o viceversa) ---
    try:
        if source in link.resolve().parents:
            raise RuntimeError(f"Symlink loop detected: {link} -> {source}")
    except FileNotFoundError:
        # link aún no existe → ok
        pass

    # --- 3. Si ya existe ---
    if link.exists() or link.is_symlink():

        # --- Caso A: ya es symlink ---
        if link.is_symlink():
            try:
                if link.resolve() == source:
                    return  # ya correcto
            except FileNotFoundError:
                pass  # symlink roto → lo recreamos

            link.unlink()
            link.symlink_to(source)
            return

        # --- Caso B: es directorio real ---
        if link.is_dir():

            # protección crítica
            if any(link.iterdir()):
                raise RuntimeError(
                    f"Refusing to replace non-empty directory: {link}"
                )

            shutil.rmtree(link)
            link.symlink_to(source)
            return

        # --- Caso C: archivo ---
        link.unlink()
        link.symlink_to(source)
        return

    # --- 4. No existe ---
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)

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
