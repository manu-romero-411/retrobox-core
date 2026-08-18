#!/usr/bin/env python3
"""
Script de inicio del proyecto Retrobox.
Administra argumentos, prepara el entorno, genera las configuraciones
y arranca el frontend (EmulationStation)
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

# logging.basicConfig(
#     level=logging.INFO,
#     format="[%(levelname)s] %(message)s"
# )
_logger = logging.getLogger(__name__)

TEARDOWN_DONE = False

RETROBOX_ROOTDIR = os.environ.get("RETROBOX_ROOTDIR", Path(__file__).resolve().parents[2])
sys.path.insert(0, str(f"{RETROBOX_ROOTDIR}/"))
sys.path.insert(0, str(f"{RETROBOX_ROOTDIR}/runtime"))
sys.path.insert(0, str(f"{RETROBOX_ROOTDIR}/runtime/launcher"))

# pylint: disable=wrong-import-position
# Bootstrap: hay que aplicar los overrides del .env ANTES de importar
# retrobox_paths (o cualquier módulo que lo importe transitivamente), porque
# sus constantes son Final y se congelan en el momento del import.
from startup.env_handling import apply_env_defaults

apply_env_defaults(RETROBOX_ROOTDIR)

from runtime.retrobox_paths import (
    _FRONTEND_DIR,
    ES_FEATURES_CFG,
    ES_FEATURES_TMP,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    ES_EXECUTABLE,
    ROMS,
    RUNTIME_DIR,
    _USER_ES_DIR,
    USERDATA,
    mkdir_if_not_exists,
)
from frontend_conf.es_ini_generator import generate_emulationstation_ini
from frontend_conf.features_list_generator import generate_es_features
from frontend_conf.system_list_generator import generate_es_systems
from frontend_conf.pcgames_utils import heroic_es_sync, lutris_es_sync, steam_es_sync
from runtime.launcher.emulatorlauncher import call_retrohook
# pylint: enable=wrong-import-position

def is_emulationstation_running(ES_BINARY: Path) -> bool:
    """
    Comprueba si ya hay un proceso EmulationStation vivo (de cualquier
    instancia de Retrobox), inspeccionando /proc directamente en vez de
    fiarnos de un pidfile que podría quedar obsoleto (p. ej. tras un SIGKILL
    que se salte el teardown()).
    """
    current_pid = os.getpid()
    try:
        proc_entries = list(Path("/proc").iterdir())
    except FileNotFoundError:
        return False

    for entry in proc_entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == current_pid:
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if not cmdline:
            continue
        argv0 = cmdline.split(b"\0", 1)[0]
        if Path(argv0.decode(errors="replace")).name == ES_BINARY.name:
            return True
    return False

# EmulationStation config
def setup_emulationstation_config() -> None:
    if not _USER_ES_DIR.is_dir():
        mkdir_if_not_exists(_USER_ES_DIR)

    generate_emulationstation_ini()
    generate_es_systems()
    generate_es_features()


def run_emulationstation(args: list[str]) -> int:
    setup_emulationstation_config()

    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-start",
        args
    )

    if not ES_EXECUTABLE.is_file():
        _logger.error("EmulationStation binary not found at %s", ES_EXECUTABLE)
        return 1
    _logger.info("=========")

    # Fuerza a SDL2 a usar el backend nativo de Wayland en vez de pasar
    # por XWayland/XRandR. "wayland,x11" deja x11 como fallback por si
    # el backend wayland de SDL fallara al iniciar por cualquier motivo.
    es_env = os.environ.copy()
    es_env["SDL_VIDEODRIVER"] = "wayland,x11"

    result = subprocess.run(
        [str(ES_EXECUTABLE), "--home", str(_FRONTEND_DIR), *map(str, args)],
        cwd=str(_FRONTEND_DIR),
        env=es_env,
        check=False,
    )
    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-stop",
        args
    )
    return result.returncode

# executed after emulationstation exits normally
def teardown() -> None:
    global TEARDOWN_DONE
    if TEARDOWN_DONE:
        return
    TEARDOWN_DONE = True

    for i in [
        ES_SYSTEMS_CFG,
        ES_FEATURES_CFG,
        ES_SYSTEMS_TMP,
        ES_FEATURES_TMP,
        ES_INI_CFG,
        ES_INI_TMP,
        Path("/tmp/game.xml"),
        Path("/tmp/emulationstation.ready"),
        Path("/tmp/gameoverlay_ui.txt"),
        Path("/tmp/env-launcher.txt"),
        RUNTIME_DIR,
    ]:
        if i.is_symlink() or i.is_file():
            i.unlink(missing_ok=True)
        elif i.is_dir():
            shutil.rmtree(i, ignore_errors=True)

    for f in Path("/tmp").glob("*wrapper*.sh"):
        f.unlink(missing_ok=True)

def _handle_sigterm(signum, frame) -> None:
    raise SystemExit(128 + signum)


# Rebuilds the argv that gets forwarded to the "emulationstation" binary from
# the parsed namespace, translating parsed values back into their original
# flag form and dropping anything that wasn't actually provided by the user.

def main() -> int:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    args = sys.argv[1:]

    if not USERDATA.is_dir():
        _logger.error("Directorio de Retrobox no válido: %s", USERDATA)
        return 1

    if is_emulationstation_running(ES_EXECUTABLE):
        _logger.error(
            "Retrobox (emulationstation) is already running"
        )
        return 1

    try:
        steam_es_sync(Path(f"{ROMS}/steam"))
        lutris_es_sync(Path(f"{ROMS}/lutris"))
        heroic_es_sync(Path(f"{ROMS}/heroic"))
        _logger.info("=========")

        return run_emulationstation(args)
    finally:
        teardown()

if __name__ == "__main__":
    
    raise SystemExit(main())
