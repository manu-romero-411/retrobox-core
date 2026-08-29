"""
Base de runtime.paths.

Cero conocimiento de configgen, del launcher, del frontend (EmulationStation)
o de gamepadly. Solo resolución de paths genéricos (XDG, ROOTDIR) y helpers
de filesystem. Este es el único módulo del paquete que otros subsistemas
del proyecto (fuera de retrobox_paths) deberían poder considerar realmente
"independiente".
"""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final, overload

if TYPE_CHECKING:
    from _typeshed import (
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextModeUpdating,
        OpenTextModeWriting,
    )
    from collections.abc import Iterator
    from io import BufferedRandom, BufferedWriter, TextIOWrapper


def check_env_dirs(variable: str, default_dir: Path) -> Path:
    """
    Function to safely assign directory values and env overrides
    """
    override = Path(os.environ.get(variable, str(default_dir)))
    if override.exists() \
    and override.is_dir() \
    and os.access(override, os.R_OK):
        return override
    return default_dir


def _load_env_file(env_path: Path) -> dict[str, str]:
    """
    Parser mínimo de .env.

    Vive aquí (y no en startup/env_handling.py) porque tiene que
    ejecutarse ANTES de que se calculen las constantes Final de este
    paquete, y ya no queremos depender de que quien nos importe se
    acuerde de llamar a nada por su cuenta en el orden correcto.
    """
    env: dict[str, str] = {}
    if not env_path.is_file():
        return env
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Un valor vacío ("VAR=" o "VAR=\"\"") se interpreta como "sin
        # definir": cae al default en vez de sobreescribirlo con "".
        if key and value:
            env[key] = value
    return env


def _bootstrap_env(rootdir: Path) -> None:
    for key, value in _load_env_file(rootdir / ".env").items():
        os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Bootstrap: hay que aplicar los overrides del .env ANTES de calcular
# cualquier constante Final de este paquete (aquí y en _configgen.py /
# _frontend.py / _gamepadly.py, que importan RETROBOX_ROOTDIR /
# RESOURCES_DIR / USERDATA de aquí). Al vivir en el propio import del
# paquete, ya no depende de que retrobox_run.py (o cualquier otro
# entrypoint futuro) recuerde llamarlo en el orden correcto antes de
# importar retrobox_paths.
# ---------------------------------------------------------------------------
_ROOTDIR_GUESS: Final = Path(__file__).resolve().parents[2]
_bootstrap_env(Path(os.environ.get("RETROBOX_ROOTDIR", str(_ROOTDIR_GUESS))))

# Helpers XDG
_USER_HOME: Final = Path.home()
_XDG_DATA: Final = Path.home() / ".local" / "share"
_XDG_CACHE: Final = Path.home() / ".cache"
_XDG_CONFIG: Final = Path.home() / ".config"
_SYSTEM_LOCAL_BIN: Final = Path("/usr/local/bin")
_SYSTEM_LOCAL_SHARE: Final = Path("/usr/local/share")

# ---------------------------------------------------------------------------
# Paths de instalación del sistema (igual que en batocera)
# ---------------------------------------------------------------------------
RETROBOX_ROOTDIR: Final = check_env_dirs("RETROBOX_ROOTDIR", _ROOTDIR_GUESS)

USERDATA: Final = RETROBOX_ROOTDIR

ENV_FILE: Final = RETROBOX_ROOTDIR / ".env"

RESOURCES_DIR: Final = RETROBOX_ROOTDIR / "resources"
DATAINIT_DIR: Final = RESOURCES_DIR / "datainit"
DEFAULTS_DIR: Final = RESOURCES_DIR / "configgen"

HOME_INIT: Final = DATAINIT_DIR / "system"
CONF_INIT: Final = HOME_INIT / "configs"
EMULATORS: Final = USERDATA / "emulators"
ROMS: Final = check_env_dirs("ROMS_DIR", USERDATA / "roms")

CACHE: Final = _XDG_CACHE / "retrobox"
LOGS: Final = USERDATA / "logs"

HOOKS: Final = USERDATA / "resources" / "hooks" / "retrohook"


# ---------------------------------------------------------------------------
# Utilidades genéricas de filesystem
# ---------------------------------------------------------------------------
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