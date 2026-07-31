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

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
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
from runtime.startup.env_handling import apply_env_defaults

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
from runtime.startup.es_ini_generator import generate_emulationstation_ini
from runtime.startup.features_list_generator import generate_es_features
from runtime.startup.system_list_generator import generate_es_systems
from runtime.startup.pcgames_utils import heroic_es_sync, lutris_es_sync, steam_es_sync
from runtime.launcher.emulatorlauncher import call_retrohook
from runtime.steamgriddb_scraper.steamgriddb_scraper import run_steamgriddb_scraper
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


def run_emulationstation(argv: list[str]) -> int:
    setup_emulationstation_config()

    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-start",
        argv
    )

    if not ES_EXECUTABLE.is_file():
        _logger.error("EmulationStation binary not found at %s", ES_EXECUTABLE)
        return 1
    _logger.info("=========")
    result = subprocess.run(
        [str(ES_EXECUTABLE), "--home", str(_FRONTEND_DIR), *argv],
        cwd=str(_FRONTEND_DIR),
        check=False,
    )
    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-stop",
        argv
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

# NOTE: EmulationStation's own flags (--resolution, --gamelist-only, --debug, etc.)
# are declared here as regular argparse arguments (not merely "known"), so that
# parse_args() rejects anything that isn't one of Retrobox's own flags or a real
# EmulationStation flag. Any other argument now triggers an argparse error instead
# of being silently forwarded.
def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="startup.py",
        description="Arranque de RetroBox",
    )
    parser.add_argument(
        "-i", "--disable-internal-display",
        action="store_true",
        help="Desactiva la pantalla interna (portátiles con doble pantalla).",
    )
    parser.add_argument(
        "--scrap-pc",
        nargs="?",
        const="",
        default=None,
        metavar="STEAMGRIDDB_API_KEY",
        help="No arranca EmulationStation: solo scrapea portadas de PC games vía "
             "SteamGridDB. Sin valor, usa STEAMGRIDDB_API_KEY del .env.",
    )

    # EmulationStation's own arguments. These are only validated and reconstructed
    # here; they are forwarded as-is to the "emulationstation" binary by
    # build_es_argv() / run_emulationstation().
    es_group = parser.add_argument_group("EmulationStation arguments")
    es_group.add_argument(
        "--resolution", nargs=2, metavar=("WIDTH", "HEIGHT"),
        help="Try and force a particular resolution.",
    )
    es_group.add_argument(
        "--gamelist-only", action="store_true",
        help="Skip automatic game search, only read from gamelist.xml.",
    )
    es_group.add_argument(
        "--ignore-gamelist", action="store_true",
        help="Ignore the gamelist (useful for troubleshooting).",
    )
    es_group.add_argument(
        "--draw-framerate", action="store_true",
        help="Display the framerate.",
    )
    es_group.add_argument(
        "--no-exit", action="store_true",
        help="Don't show the exit option in the menu.",
    )
    es_group.add_argument(
        "--no-splash", action="store_true",
        help="Don't show the splash screen.",
    )
    es_group.add_argument(
        "--debug", action="store_true",
        help="More logging.",
    )
    es_group.add_argument(
        "--windowed", action="store_true",
        help="Not fullscreen, should be used with --resolution.",
    )
    es_group.add_argument(
        "--vsync", metavar="1/on|0/off",
        help="Turn vsync on or off (default is on).",
    )
    es_group.add_argument(
        "--max-vram", metavar="SIZE",
        help="Max VRAM to use in Mb before swapping. 0 for unlimited.",
    )
    es_group.add_argument(
        "--force-kid", action="store_true",
        help="Force the UI mode to be Kid.",
    )
    es_group.add_argument(
        "--force-kiosk", action="store_true",
        help="Force the UI mode to be Kiosk.",
    )
    es_group.add_argument(
        "--force-disable-filters", action="store_true",
        help="Force the UI to ignore applied filters in gamelist.",
    )
    es_group.add_argument(
        "--monitor", metavar="INDEX",
        help="Monitor index.",
    )
    # --home is intentionally NOT exposed: startup.py always forces it to
    # _FRONTEND_DIR itself when launching EmulationStation (see
    # run_emulationstation()), so accepting it here would just cause a
    # conflicting duplicate --home in the final command line.

    return parser.parse_args(argv)


# Rebuilds the argv that gets forwarded to the "emulationstation" binary from
# the parsed namespace, translating parsed values back into their original
# flag form and dropping anything that wasn't actually provided by the user.
def build_es_argv(args: argparse.Namespace) -> list[str]:
    es_argv: list[str] = []

    if args.resolution:
        es_argv += ["--resolution", *args.resolution]
    if args.gamelist_only:
        es_argv.append("--gamelist-only")
    if args.ignore_gamelist:
        es_argv.append("--ignore-gamelist")
    if args.draw_framerate:
        es_argv.append("--draw-framerate")
    if args.no_exit:
        es_argv.append("--no-exit")
    if args.no_splash:
        es_argv.append("--no-splash")
    if args.debug:
        es_argv.append("--debug")
    if args.windowed:
        es_argv.append("--windowed")
    if args.vsync is not None:
        es_argv += ["--vsync", args.vsync]
    if args.max_vram is not None:
        es_argv += ["--max-vram", args.max_vram]
    if args.force_kid:
        es_argv.append("--force-kid")
    if args.force_kiosk:
        es_argv.append("--force-kiosk")
    if args.force_disable_filters:
        es_argv.append("--force-disable-filters")
    if args.monitor is not None:
        es_argv += ["--monitor", args.monitor]

    return es_argv

def main() -> int:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    args = parse_args(sys.argv[1:])

    if args.disable_internal_display:
        os.environ["RETROBOX_DISABLE_INTERNAL_DISPLAY"] = "1"

    if not USERDATA.is_dir():
        _logger.error("Directorio de Retrobox no válido: %s", USERDATA)
        return 1

    if args.scrap_pc is not None:
        return run_steamgriddb_scraper(
            apikey=str(os.getenv("STEAMGRIDDB_API_KEY", str(args.scrap_pc)))
        )

    if is_emulationstation_running(ES_EXECUTABLE):
        _logger.error(
            "Retrobox (emulationstation) is already running"
        )
        return 1

    es_argv = build_es_argv(args)

    try:
        steam_es_sync(Path(f"{ROMS}/steam"))
        lutris_es_sync(Path(f"{ROMS}/lutris"))
        heroic_es_sync(Path(f"{ROMS}/heroic"))
        _logger.info("=========")

        return run_emulationstation(es_argv)
    finally:
        teardown()

if __name__ == "__main__":
    
    raise SystemExit(main())