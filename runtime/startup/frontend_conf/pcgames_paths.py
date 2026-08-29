
import os
from pathlib import Path
import re

from runtime.paths import _USER_HOME, _XDG_CONFIG, _XDG_DATA

def _env_paths(var_name: str) -> tuple[Path, ...]:
    """Lee una variable de entorno con rutas separadas por `os.pathsep`
    y las convierte en una tupla de Path. Si la variable no existe o
    está vacía, devuelve una tupla vacía."""
    raw = os.environ.get(var_name, "")
    if not raw:
        return ()
    return tuple(Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip())

_LUTRIS_DB_CANDIDATES = (
    _XDG_DATA / "lutris" / "pga.db",
    _USER_HOME / ".var" / "app" / "net.lutris.Lutris" / ".local" / "share" / "lutris" / "pga.db",  # Flatpak
)

_INVALID_FILENAME_CHARS = str.maketrans({c: "-" for c in '/\\:*?"<>|'})

_STEAM_ROOTS = (
    *_env_paths("STEAM_LIBRARY_DIR"),
    _XDG_DATA / "Steam",
    _USER_HOME / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",  # Flatpak
)

_SKIP_NAME_RE = re.compile(
    r"proton|steam linux runtime|steamworks|redistributabl|pressure vessel|sniper|soldier",
    re.IGNORECASE,
)

_HEROIC_CONFIG = _XDG_CONFIG / "heroic"
_EPIC_JSON = _HEROIC_CONFIG / "legendaryConfig" / "legendary" / "installed.json"
_GOG_JSON = _HEROIC_CONFIG / "gog_store" / "installed.json"
_HEROIC_SIDELOAD_JSON = _HEROIC_CONFIG / "sideload_apps" / "library.json"
