#!/usr/bin/env python3
"""
Script de inicio del proyecto Retrobox.
Administra argumentos, prepara el entorno, genera las configuraciones
y arranca el frontend (EmulationStation)
"""

from __future__ import annotations

import logging
import os
import argparse
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

RETROBOX_ROOTDIR = os.environ.get("RETROBOX_ROOTDIR", Path(__file__).resolve().parents[2])
sys.path.insert(0, str(f"{RETROBOX_ROOTDIR}/"))
sys.path.insert(0, str(f"{RETROBOX_ROOTDIR}/runtime"))
sys.path.insert(0, str(f"{RETROBOX_ROOTDIR}/runtime/launcher"))

from runtime.startup.es_ini_generator import generate_emulationstation_ini
from runtime.startup.features_list_generator import generate_es_features
from runtime.startup.system_list_generator import generate_es_systems
from runtime.startup.pcgames_utils import heroic_es_sync, lutris_es_sync, steam_es_sync
from runtime.launcher.emulatorlauncher import call_retrohook
from runtime.steamgriddb_scraper.steamgriddb_scraper import run_steamgriddb_scraper
from configgen.generators.libretro.libretroPaths import _RETROARCH_AUDIO_FILTERS, _RETROARCH_VIDEO_FILTERS
from runtime.retrobox_paths import (
    _FRONTEND_DIR,
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    _DECORATIONS_DIR,
    ENV_FILE,
    ES_FEATURES_CFG,
    ES_FEATURES_TMP,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    LOGS,
    ROMS,
    RUNTIME_DIR,
    SAVES,
    SCREENSHOTS,
    _SHADERS_DIR,
    _USER_ES_DIR,
    USERDATA,
    mkdir_if_not_exists,
) 

TEARDOWN_DONE = False

def load_env(env_path: Path) -> dict[str, str]:
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
        if key:
            env[key] = value
    return env

def apply_env_defaults() -> None:
    for key, value in load_env(ENV_FILE).items():
        os.environ.setdefault(key, value)

# EmulationStation config
def setup_emulationstation_config() -> None:
    if not _USER_ES_DIR.is_dir():
        mkdir_if_not_exists(_USER_ES_DIR)

    generate_emulationstation_ini()
    generate_es_systems()
    generate_es_features()


def run_emulationstation(argv: list[str]) -> int:
    es_binary = _FRONTEND_DIR / "emulationstation"
    if not es_binary.is_file():
        _logger.error("EmulationStation binary not found at %s", es_binary)
        return 1
    _logger.info("=========")
    result = subprocess.run(
        [str(es_binary), "--home", str(_FRONTEND_DIR), *argv],
        cwd=str(_FRONTEND_DIR),
        check=False,
    )
    return result.returncode

# executed after emulationstation exits normally
def teardown() -> None:
    global TEARDOWN_DONE
    if TEARDOWN_DONE:
        return
    TEARDOWN_DONE = True
    call_retrohook(
        "_frontend",
        "emulationstation",
        "on-frontend-stop",
        []
    )

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

def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
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
    return parser.parse_known_args(argv)

def main() -> int:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    apply_env_defaults()

    args, extra_argv = parse_args(sys.argv[1:])

    if args.disable_internal_display:
        os.environ["RETROBOX_DISABLE_INTERNAL_DISPLAY"] = "1"

    if not USERDATA.is_dir():
        _logger.error("Directorio de Retrobox no válido: %s", USERDATA)
        return 1

    if args.scrap_pc is not None:
        return run_steamgriddb_scraper(
            apikey=str(
                os.getenv("STEAMGRIDDB_API_KEY", str(args.scrap_pc)
            )
        ))

    #forward_argv = list(extra_argv)
    #if args.disable_internal_display:
    #    forward_argv.append("-i")

    try:
        setup_emulationstation_config()

        steam_es_sync(Path(f"{ROMS}/steam"))
        lutris_es_sync(Path(f"{ROMS}/lutris"))
        heroic_es_sync(Path(f"{ROMS}/heroic"))
        _logger.info("=========")

        call_retrohook("_frontend", "emulationstation", "on-frontend-start", sys.argv[1:])

        return run_emulationstation(sys.argv[1:])
    finally:
        teardown()

if __name__ == "__main__":
    raise SystemExit(main())