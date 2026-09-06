#!/usr/bin/env python
# ruff: noqa: E402

from __future__ import annotations

import argparse
from copy import deepcopy
import contextlib
import ctypes
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import pyudev
import sdl2

# absolute path modifications at the very beginning
ROOTDIR = Path(__file__).resolve().parents[2]
CONFIGGEN_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOTDIR))
sys.path.append(str(CONFIGGEN_DIR))

# pylint: disable=wrong-import-position
from configgen import profiler
from configgen.controller import Controller
from configgen.Emulator import Emulator
from configgen.exceptions import (
    BadCommandLineArguments,
    BaseRetroboxException,
    RetroboxException,
    UnexpectedEmulatorExit,
)
from configgen.generators import get_generator
from configgen.gun import Gun
from configgen.utils import bezels as bezelsUtil, metadata, videoMode, wheelsUtils
from configgen.utils.logger import setup_logging
from configgen.utils.overlayfs import mount_overlayfs
from configgen.utils.squashfs import mount_squashfs
from runtime.gamepadly.gamepadly_manager import GamepadManager
from runtime.paths import (
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    NVIDIA_POWERD_SCRIPT,
    ES_GAMES_METADATA,
    ES_INPUT_CFG,
    GAMEPADLY_MAPPER,
    HOOKS,
    RUNTIME_DIR,
    SAVES,
    GUN_OVERLAYS_DIR,
    HUD_CONFIG_FILE,
    USERDATA,
    mkdir_if_not_exists,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import FrameType

    from runtime.launcher.configgen.Command import Command
    from runtime.launcher.configgen.batoceraTypes import Resolution
    from runtime.launcher.configgen.generators.Generator import Generator

_logger = logging.getLogger(__name__)

# A lock to safely modify the active controller list from multiple threads
_player_controllers_lock = threading.Lock()
# A global variable to hold the current, up-to-date list of player controllers
_active_player_controllers = []

_POWER_PROFILES_BIN = "powerprofilesctl"
_VALID_POWER_PROFILES = {"power-saver", "balanced", "performance"}


def main(args: argparse.Namespace, maxnbplayers: int) -> int:
    """
Main function that wraps start_rom
    """
    original_rom = args.rom

    # squashfs roms if squashed
    if original_rom.suffix == ".squashfs":
        with mount_squashfs(original_rom) as squash_rom:
            return start_rom(args, maxnbplayers, squash_rom, original_rom)
    else:
        return start_rom(args, maxnbplayers, original_rom, original_rom)

def start_rom(args: argparse.Namespace, maxnbplayers: int, rom: Path, original_rom: Path) -> int:
    """The main ROM start function. This calls everything else in the module.
    Returns exit code for the emulator command
    """
    mkdir_if_not_exists(RUNTIME_DIR)
    
    global _active_player_controllers

    player_controllers = Controller.load_for_players(maxnbplayers, args)

    # Initialize the global state with the initial controller list
    with _player_controllers_lock:
        _active_player_controllers = list(player_controllers)

    # Start the background monitor thread.
    monitor_thread = threading.Thread(target=_controller_monitor_thread, daemon=True)

    # find the system to run
    system_name: str = args.system
    _logger.debug("Running system: %s", system_name)
    system = Emulator(args, original_rom)
    
    _logger.debug("Settings: %s", {
        key: '***' if 'password' in key else value for key, value in system.config.items()
    })

    if "emulator" in system.config and "core" in system.config:
        _logger.debug('emulator: %s, core: %s', system.config.emulator, system.config.core)
    else:
        if "emulator" in system.config:
            _logger.debug('emulator: %s', system.config.emulator)

    # power profiles
    power_prof = system.config.get("power_profile", "balanced")
    previous_power_profile = apply_power_profile(power_prof)      

    # metadata
    md = metadata.get_games_meta_data(ES_GAMES_METADATA, system_name, rom)

    guns = Gun.get_and_precalibrate_all(system, rom)

    with wheelsUtils.configure_wheels(player_controllers, system, md) \
    as (player_controllers, wheels):
        # find the generator
        generator = get_generator(system.config.emulator, system.config.core)

        with (
            mount_overlayfs(rom, Path(f"{SAVES}/{original_rom.parent.name}/{original_rom.stem}"))
            if original_rom.suffix == ".squashfs" and generator.writesToRom(system.config)
            else contextlib.nullcontext(rom)
        ) as rom:
            game_resolution = videoMode.getCurrentResolution()
            exit_code = 0

            try:
                # savedir: create the save directory if not already done
                dirname = Path(f"{SAVES}/{system.name}")
                if not dirname.exists():
                    dirname.mkdir(parents=True)

                # core
                effective_core = ""
                if "core" in system.config and system.config.core is not None:
                    effective_core = system.config.core

                # SDL VSync is a big deal on OGA and RPi4
                if not system.config.get_bool('sdlvsync', True):
                    system.config["sdlvsync"] = '0'
                else:
                    system.config["sdlvsync"] = '1'
                os.environ.update({'SDL_RENDER_VSYNC': system.config["sdlvsync"]})

                # run a script before emulator starts
                call_retrohook(
                    "_global",
                    "_platform",
                    "on-start-game",
                    [system.config.emulator, effective_core]
                )
                call_retrohook(
                    system_name,
                    "_platform",
                    "on-start-game",
                    [system.config.emulator,
                     effective_core]
                )
                call_retrohook(
                    system_name,
                    rom,
                    "on-start-game",
                    [system.config.emulator,
                     effective_core]
                )
       
                # run the emulator
                with (
                    GamepadManager(
                        system            = system_name,
                        emulator          = system.config.emulator,
                        core              = effective_core,
                        rom               = rom,
                        controllers       = player_controllers,
                        mapper_script     = GAMEPADLY_MAPPER,
                        profiles_dir      = _GAMEPADLY_PROFILES,
                        user_profiles_dir = _GAMEPADLY_USER_PROFILES,
                        es_input          = ES_INPUT_CFG,
                    )
                ):

                    # change directory if wanted
                    execution_directory = generator.executionDirectory(system.config, rom)
                    if execution_directory is not None:
                        os.chdir(execution_directory)

                    cmd = generator.generate(
                        system,
                        rom,
                        player_controllers,
                        md,
                        guns,
                        wheels,
                        game_resolution
                    )

                    if system.config.get_bool('hud_support'):
                        hud_bezel = getHudBezel(
                            system,
                            generator,
                            rom,
                            game_resolution,
                            system.guns_borders_size_name(guns),
                            system.guns_border_ratio_type(guns))

                        if ((hud := system.config.get('hud')) and hud.lower() != 'none')\
                        or hud_bezel is not None:
                            cmd.env["MANGOHUD"] = "1"
                            cmd.env["MANGOHUD_DLSYM"] = "1"
                            cmd.env["MANGOHUD_CONFIGFILE"] = str(HUD_CONFIG_FILE)

                            hudconfig = getHudConfig(
                                system, args.systemname, system.config.emulator,
                                effective_core, rom, hud_bezel
                            )

                            with HUD_CONFIG_FILE.open('w') as f:
                                f.write(hudconfig)

                            if generator.usesOpenGLDirectPreload(system.config):
                                # OpenGL: LD_PRELOAD directo, sin pasar por el wrapper mangohud
                                # (que lo pisaría con su propio shim vía --dlsym)
                                cmd.env["LD_PRELOAD"] =\
                                    "/usr/local/lib64/mangohud/libMangoHud_opengl.so"
                            elif not generator.hasInternalMangoHUDCall():
                                # Vulkan (u otros):
                                # dejamos que mangohud gestione el layer/preload él mismo
                                cmd.array.insert(0, "--dlsym")
                                cmd.array.insert(0, "mangohud")

                    # generate the gun help
                    try:
                        default_gun_help_dir = GUN_OVERLAYS_DIR
                        bezelsUtil.generate_gun_help(
                            system_name,
                            rom,
                            system.config.use_guns,
                            guns,
                            default_gun_help_dir,
                            "gun_help.png",
                            game_resolution
                        )
                    except Exception as e:
                        _logger.error("Failed to generate the gun help image")
                        _logger.error(e)

                    # gun borders
                    try:
                        if system.config.use_guns and guns:
                            if generator.supportsInternalBezels() \
                            or system.config.get_bool('hud_support'):
                                _logger.debug(
                                    "skipping configgen internal gun borders for emulator %s",
                                    system.config.emulator)
                            else:
                                gun_border_size_name = system.guns_borders_size_name(guns)
                                if gun_border_size_name is not None:
                                    _logger.debug(
                                        "using configgen internal gun borders for emulator %s",
                                        system.config.emulator)

                                    from .configgen.utils.gun_borders import draw_gun_borders
                                    draw_gun_borders(
                                        gun_border_size_name,
                                        bezelsUtil.gunsBordersColorFomConfig(system.config),
                                        system.guns_border_ratio_type(guns)
                                    )
                    except Exception as e:
                        _logger.error("Failed to draw_gun_borders for gun_borders")
                        _logger.error(e)

                    with profiler.pause():
                        monitor_thread.start()
                        exit_code = run_command(cmd)

                # run a script after emulator shuts down
                call_retrohook(
                    "_global",
                    "_platform",
                    "on-close-game",
                    [system.config.emulator, effective_core]
                )
                call_retrohook(
                    system_name,
                    "_platform",
                    "on-close-game",
                    [system.config.emulator, effective_core]
                )
                call_retrohook(
                    system_name,
                    rom,
                    "on-close-game",
                    [system.config.emulator, effective_core]
                )

            finally:
                restore_power_profile(previous_power_profile)
    # exit
    return exit_code

def getHudBezel(system: Emulator, generator: Generator, rom: Path, gameResolution: Resolution, bordersSize: str | None, bordersRatio: str | None):
    if generator.supportsInternalBezels():
        _logger.debug("skipping bezels for emulator %s", system.config.emulator)
        return None
    # no good reason for a bezel
    bezel = system.config.get_str('bezel', 'none')
    bezel_tattoo = system.config.get_str('bezel.tattoo', '0')
    bezel_qrcode = system.config.get_str('bezel.qrcode', '0')

    if (not bezel or bezel == 'none') and (not bezel_tattoo or bezel_tattoo == '0') and (not bezel_qrcode or bezel_qrcode == '0') and bordersSize is None:
        return None

    # no bezel, generate a transparent one for the tatoo/gun borders ... and so on
    if not bezel or bezel == 'none':
        overlay_png_file  = Path("/tmp/bezel_transhud_black.png")
        overlay_info_file = Path("/tmp/bezel_transhud_black.info")
        bezelsUtil.createTransparentBezel(overlay_png_file, gameResolution["width"], gameResolution["height"])

        w = gameResolution["width"]
        h = gameResolution["height"]
        with overlay_info_file.open("w") as fd:
            fd.write(f'{{ "width":{w}, "height":{h}, "opacity":1.0000000, "messagex":0.220000, "messagey":0.120000 }}')
    else:
        _logger.debug("hud enabled. trying to apply the bezel %s", bezel)

        bz_infos = bezelsUtil.get_bezel_infos(rom, bezel, system.name, system.config.emulator)
        if bz_infos is None:
            _logger.debug("no bezel info file found")
            return None

        overlay_info_file = bz_infos["info"]
        overlay_png_file  = bz_infos["png"]

    # check the info file
    # bottom, top, left and right must not cover too much the image to be considered as compatible
    if overlay_info_file.exists():
        try:
            with overlay_info_file.open() as f:
                infos = json.load(f)
        except Exception:
            _logger.warning("unable to read %s", overlay_info_file)
            infos = {}
    else:
        infos = {}

    if "width" in infos and "height" in infos:
        bezel_width  = infos["width"]
        bezel_height = infos["height"]
        _logger.info("bezel size read from %s", overlay_info_file)
    else:
        bezel_width, bezel_height = bezelsUtil.fast_image_size(overlay_png_file)
        _logger.info("bezel size read from %s", overlay_png_file)

    # max cover proportion and ratio distortion
    max_cover = 0.05 # 5%
    max_ratio_delta = 0.01

    screen_ratio = gameResolution["width"] / gameResolution["height"]
    bezel_ratio  = bezel_width / bezel_height

    # the screen and bezel ratio must be approximatly the same
    if bordersSize is None and abs(screen_ratio - bezel_ratio) > max_ratio_delta:
        _logger.debug(
            "screen ratio (%(screen_ratio)s) is too far from the bezel one (%(bezel_ratio)s) : %(screen_ratio)s - %(bezel_ratio)s > %(max_ratio_delta)s",
            {
                'screen_ratio': screen_ratio,
                'bezel_ratio': bezel_ratio,
                'max_ratio_delta': max_ratio_delta
            }
        )
        return None

    # the ingame image and the bezel free space must feet
    ## the bezel top and bottom cover must be minimum
    # in case there is a border, force it
    if bordersSize is None:
        if "top" in infos and infos["top"] / bezel_height > max_cover:
            _logger.debug('bezel top covers too much the game image : %s / %s > %s', infos["top"], bezel_height, max_cover)
            return None
        if "bottom" in infos and infos["bottom"] / bezel_height > max_cover:
            _logger.debug('bezel bottom covers too much the game image : %s / %s > %s', infos["bottom"], bezel_height, max_cover)
            return None

    # if there is no information about top/bottom, assume default is 0

    ## the bezel left and right cover must be maximum
    ingame_ratio = generator.getInGameRatio(system.config, gameResolution, rom)
    img_height = bezel_height
    img_width  = img_height * ingame_ratio

    if "left" not in infos:
        _logger.debug("bezel has no left info in %s", overlay_info_file)
        # assume default is 4/3 over 16/9
        infos_left = (bezel_width - (bezel_height / 3 * 4)) / 2
        if bordersSize is None and abs((infos_left  - ((bezel_width-img_width)/2.0)) / img_width) > max_cover:
            _logger.debug("bezel left covers too much the game image : %s / %s > %s", infos_left  - ((bezel_width-img_width)/2.0), img_width, max_cover)
            return None

    if "right" not in infos:
        _logger.debug("bezel has no right info in %s", overlay_info_file)
        # assume default is 4/3 over 16/9
        infos_right = (bezel_width - (bezel_height / 3 * 4)) / 2
        if bordersSize is None and abs((infos_right - ((bezel_width-img_width)/2.0)) / img_width) > max_cover:
            _logger.debug("bezel right covers too much the game image : %s / %s > %s", infos_right  - ((bezel_width-img_width)/2.0), img_width, max_cover)
            return None

    if bordersSize is None:
        if "left"  in infos and abs((infos["left"]  - ((bezel_width-img_width)/2.0)) / img_width) > max_cover:
            _logger.debug("bezel left covers too much the game image : %s / %s > %s", infos["left"]  - ((bezel_width-img_width)/2.0), img_width, max_cover)
            return None
        if "right" in infos and abs((infos["right"] - ((bezel_width-img_width)/2.0)) / img_width) > max_cover:
            _logger.debug("bezel right covers too much the game image : %s / %s > %s", infos["right"]  - ((bezel_width-img_width)/2.0), img_width, max_cover)
            return None

    # if screen and bezel sizes doesn't match, resize
    # stretch option
    bezel_stretch = system.config.get_bool('bezel_stretch')
    if (bezel_width != gameResolution["width"] or bezel_height != gameResolution["height"]):
        _logger.debug("bezel needs to be resized")
        output_png_file = Path("/tmp/bezel.png")
        try:
            bezelsUtil.resizeImage(overlay_png_file, output_png_file, gameResolution["width"], gameResolution["height"], bezel_stretch)
        except Exception as e:
            _logger.error("failed to resize the image %s", e)
            return None
        overlay_png_file = output_png_file

    if bezel_tattoo != "0":
        output_png_file = Path("/tmp/bezel_tattooed.png")
        bezelsUtil.tatooImage(overlay_png_file, output_png_file, system)
        overlay_png_file = output_png_file

    if bezel_qrcode != "0" and (cheevos_id := system.es_game_info.get("cheevosId", "0")) != "0":
        output_png_file = Path("/tmp/bezel_qrcode.png")
        bezelsUtil.addQRCode(overlay_png_file, output_png_file, cheevos_id, system)
        overlay_png_file = output_png_file

    # borders
    if bordersSize is not None:
        _logger.debug("Draw gun borders")
        output_png_file = Path("/tmp/bezel_gunborders.png")
        inner_size, outer_size = bezelsUtil.gunBordersSize(bordersSize)
        _logger.debug("Gun border ratio = %s", bordersRatio)
        bezelsUtil.gunBorderImage(overlay_png_file, output_png_file, bordersRatio, inner_size, outer_size, bezelsUtil.gunsBordersColorFomConfig(system.config))
        overlay_png_file = output_png_file

    _logger.debug("applying bezel %s", overlay_png_file)
    return overlay_png_file

import re

def _sanitize_hook_name(name: str) -> str:
    """
    Sanitiza un nombre para usarlo como componente de ruta en retrohook.d/.
    Solo afecta a la búsqueda del directorio de hooks, no a los args pasados al script.
    """
    name = name.replace("/", "_")          # único caracter realmente ilegal en Linux
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)  # control chars
    return name[:255]                      # límite de filename en ext4/btrfs

def call_retrohook(
    platform: str,
    game: str | Path,
    state: str,  # "on-start-game" | "on-close-game"
    extra_args: Iterable[str | Path] = (),
) -> None:
    """
    Invoca el sistema de hooks de retrobox.
    Delega toda la lógica de jerarquía y ejecución al script bash retrohook.
    """

    if not HOOKS.is_file() or not os.access(HOOKS, os.X_OK):
        _logger.debug("retrohook not found or not executable: %s", HOOKS)
        return

    game_stem = Path(game).stem
    game_hook_name = _sanitize_hook_name(game_stem)  # para la ruta

    cmd = [str(HOOKS), platform, game_hook_name, state, str(game), *map(str, extra_args)]

    _logger.info("[retrohook] %s %s %s", platform, game_hook_name, state)
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        _logger.warning("[retrohook] exited with code %s", result.returncode)
        
def hudConfig_protectStr(string: str | Path | None) -> str:
    if string is None:
        return ""
    return str(string)

def getHudConfig(system: Emulator, systemName: str, emulator: str, core: str, rom: Path, bezel: Path | None) -> str:
    configstr = ""

    if bezel != "" and bezel != "none" and bezel is not None:
        configstr = f"background_image={hudConfig_protectStr(bezel)}\nlegacy_layout=false\n"

    if (mode := system.config.get('hud', 'none')) == 'none':
        return configstr + "background_alpha=0\n" # hide the background

    hud_position = "bottom-left"
    if (hud_corner := system.config.get('hud_corner', '')) != '':
        if hud_corner == "NW":
            hud_position = "top-left"
        elif hud_corner == "NE":
            hud_position = "top-right"
        elif hud_corner == "SE":
            hud_position = "bottom-right"

    emulatorstr = emulator
    if emulator != core and core is not None:
        emulatorstr += f"/{core}"

    game_name = system.es_game_info.get("name", "")
    game_thumbnail = system.es_game_info.get("thumbnail", "")

    # predefined values
    if mode == "perf":
        configstr += f"position={hud_position}\nbackground_alpha=0.4\nlegacy_layout=false\ncustom_text=%GAMENAME%\ncustom_text=%SYSTEMNAME%\ncustom_text=%EMULATORCORE%\nfps\ngpu_name\nengine_version\nvulkan_driver\nresolution\nram\ngpu_stats\ngpu_temp\ncpu_stats\ncpu_temp\ncore_load\n"
    elif mode == "game":
        configstr += f"position={hud_position}\nbackground_alpha=0\nlegacy_layout=false\nfont_size=32\nimage_max_width=200\nimage=%THUMBNAIL%\ncustom_text=%GAMENAME%\ncustom_text=%SYSTEMNAME%\ncustom_text=%EMULATORCORE%"
    elif mode == "custom" and (hud_custom := system.config.get_str('hud_custom')):
        configstr += hud_custom.replace("\\n", "\n")
    else:
        configstr = configstr + "background_alpha=0\n" # hide the background

    configstr = configstr.replace("%SYSTEMNAME%", hudConfig_protectStr(systemName))
    configstr = configstr.replace("%GAMENAME%", hudConfig_protectStr(game_name))
    configstr = configstr.replace("%EMULATORCORE%", hudConfig_protectStr(emulatorstr))
    return configstr.replace("%THUMBNAIL%", hudConfig_protectStr(game_thumbnail))


def _set_nvidia_powerd(enable: bool) -> None:
    """
    Arranca o para nvidia-powerd.service vía el script nvidia-powerd-service.
    No lanza excepciones: solo registra avisos si algo falla.
    
    Se asegura de que el binario 'nvidia-powerd' exista realmente en el sistema 
    antes de intentar nada, garantizando compatibilidad total con sistemas 
    AMD, Intel, Apple, Qualcomm, Nvidia antiguas o dispositivos como la Switch.
    """
    # 1. Verificar que nuestro script helper exista y sea ejecutable
    if not os.path.isfile(NVIDIA_POWERD_SCRIPT) or not os.access(NVIDIA_POWERD_SCRIPT, os.X_OK):
        _logger.debug("%s not found or not executable, skipping nvidia-powerd management", NVIDIA_POWERD_SCRIPT)
        return

    # 2. Verificar que el binario real del sistema exista en el PATH
    # Si no existe, abortamos silenciosamente. Esto protege a sistemas sin nvidia-powerd.
    if shutil.which("nvidia-powerd") is None:
        _logger.debug("nvidia-powerd binary not found in system PATH, skipping nvidia-powerd management")
        return

    action = "start" if enable else "stop"
    try:
        subprocess.run(
            [NVIDIA_POWERD_SCRIPT, action],
            check=True, capture_output=True, text=True, timeout=15,
        )
        _logger.info("nvidia-powerd %s", "started" if enable else "stopped")
    except subprocess.CalledProcessError as e:
        _logger.warning(
            "failed to %s nvidia-powerd: %s",
            action, e.stderr.strip() if e.stderr else e,
        )
    except Exception as e:
        _logger.warning("failed to %s nvidia-powerd: %s", action, e)

def apply_power_profile(desired_profile: str) -> str | None:
    """
    Aplica el power-profile pedido. Devuelve el perfil que estaba activo antes
    (o None si no se pudo leer / powerprofilesctl no está disponible).
    También arranca nvidia-powerd si el perfil es 'performance', y lo para
    en cualquier otro caso.
    """
    desired_profile = (desired_profile or "balanced").strip().lower()
    if desired_profile not in _VALID_POWER_PROFILES:
        _logger.warning("unknown power_profile '%s', falling back to 'balanced'", desired_profile)
        desired_profile = "balanced"

    # Gestión de nvidia-powerd: independiente de powerprofilesctl.
    _set_nvidia_powerd(desired_profile == "performance")

    if shutil.which(_POWER_PROFILES_BIN) is None:
        _logger.debug("%s not found, skipping power profile management", _POWER_PROFILES_BIN)
        return None

    previous_profile = None
    try:
        result = subprocess.run(
            [_POWER_PROFILES_BIN, "get"],
            check=True, capture_output=True, text=True,
        )
        previous_profile = result.stdout.strip()
        _logger.debug("current power profile before launch: %s", previous_profile)
    except Exception as e:
        _logger.warning("could not read current power profile: %s", e)

    if previous_profile != desired_profile:
        try:
            subprocess.run(
                [_POWER_PROFILES_BIN, "set", desired_profile],
                check=True, capture_output=True, text=True,
            )
            _logger.info("power profile set to '%s'", desired_profile)
        except Exception as e:
            _logger.warning("failed to set power profile to '%s': %s", desired_profile, e)
    else:
        _logger.debug("power profile already '%s', nothing to do", desired_profile)

    return previous_profile

def restore_power_profile(previous_profile: str | None) -> None:
    # nvidia-powerd solo debe quedar activo si volvemos a 'performance';
    # en 'balanced', 'power-saver', o si no hay perfil previo válido, se para.
    _set_nvidia_powerd(previous_profile == "performance")

    if not previous_profile or previous_profile not in _VALID_POWER_PROFILES:
        return
    try:
        subprocess.run(
            [_POWER_PROFILES_BIN, "set", previous_profile],
            check=True, capture_output=True, text=True
        )
        _logger.info("power profile restored to '%s'", previous_profile)
    except Exception as e:
        _logger.warning("failed to restore power profile to '%s': %s", previous_profile, e)

def _controller_monitor_thread():
    """
    Runs in the background, watching for controller add/remove events.
    Uses pysdl2 to reliably get controller GUIDs and paths, then intelligently "revives"
    the original controller object to preserve player order without disrupting the emulator.
    """
    global _active_player_controllers

    initial_controllers_snapshot = []
    with _player_controllers_lock:
        initial_controllers_snapshot = deepcopy(_active_player_controllers)
        for i, p_controller in enumerate(initial_controllers_snapshot):
            if p_controller and p_controller.guid:
                _logger.info(
                    ">>>   [P%s] Stored GUID: %s, Initial Path: %s",
                    i+1,
                    p_controller.guid,
                    p_controller.device_path
                )

    we_initialized_sdl = False
    try:
        if sdl2.SDL_WasInit(sdl2.SDL_INIT_JOYSTICK) == 0:
            _logger.info(">>> SDL2 joystick subsystem not initialized. Initializing it now.")
            sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK)
            we_initialized_sdl = True
        else:
            _logger.info(">>> SDL2 joystick subsystem already initialized by host (emulator). Will not re-initialize.")
    except Exception as e:
        _logger.error("FATAL: Could not initialize pysdl2 for controller monitoring: %s", e)
        return

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem='input')

    _logger.info(">>> Starting background controller monitor.")
    for device in iter(monitor.poll, None):
        if device.properties.get('ID_INPUT_JOYSTICK') != '1':
            continue

        _logger.info("--- Joystick Event Detected: %s on %s ---", device.action, device.sys_path)

        sdl2.SDL_JoystickUpdate()
        online_controllers_map = {}
        for i in range(sdl2.SDL_NumJoysticks()):
            try:
                guid_struct = sdl2.SDL_JoystickGetDeviceGUID(i)
                guid_str_buffer = (ctypes.c_char * 33)()
                sdl2.SDL_JoystickGetGUIDString(guid_struct, guid_str_buffer, 33)
                guid = guid_str_buffer.value.decode('utf-8')

                path_bytes = sdl2.SDL_JoystickPathForIndex(i)
                path = path_bytes.decode('utf-8') if path_bytes else None

                if guid and path:
                    online_controllers_map[guid] = path
            except Exception as e:
                _logger.warning("Error while querying joystick index %s with pysdl2: %s", i, e)

        _logger.info(">>> [Check 1] Pysdl2 scan found online controllers: %s", online_controllers_map)

        with _player_controllers_lock:
            new_active_controllers: list[Controller | None] = [None] * len(initial_controllers_snapshot)

            for i, initial_controller in enumerate(initial_controllers_snapshot):
                if initial_controller and initial_controller.guid in online_controllers_map:
                    new_path = online_controllers_map[initial_controller.guid]
                    if initial_controller.device_path != new_path:
                        _logger.info(">>> [Revival] Player %s (GUID: %s) path has changed.", initial_controller.player_number, initial_controller.guid)
                        initial_controller.device_path = new_path
                    new_active_controllers[i] = initial_controller

            current_paths = [c.device_path if c else None for c in _active_player_controllers]
            new_paths = [c.device_path if c else None for c in new_active_controllers]

            if current_paths != new_paths:
                _logger.info(">>> [Check 2] Controller state changed. Old Paths: %s. New Paths: %s", current_paths, new_paths)
                _active_player_controllers = new_active_controllers
                reconfigure_needed = True
            else:
                _logger.info(">>> [Check 2] No change in assigned controller paths detected.")

    if we_initialized_sdl:
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_JOYSTICK)

def run_command(command: Command) -> int:
    """Catches the generated command and runs it with subprocess.Popen.
    Also handles error codes and exceptions to send them to main() and launch().
    """
    global proc

    # compute environment : first the current envs, then override by values set at generator level
    envvars: dict[str, str | Path] = dict(os.environ)
    envvars.update(command.env)
    command.env = envvars

    #_logger.debug("command: %s", command)
    _logger.info("command: %s", command.array)
    _logger.debug("env: %s", command.env)

    if not command.array:
        raise BadCommandLineArguments

    with open("/tmp/env-launcher.txt", "w", encoding="utf-8") as f:
        for k, v in sorted(envvars.items()):
            print(f"{k}={v}", file=f)

    exitcode = 0

    try:
        with subprocess.Popen(
            command.array,
            env=command.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ) as proc:
            out, err = proc.communicate()
            exitcode = proc.returncode

            if err is not None:
                _logger.error(err.decode(errors='backslashreplace'))

            if out is not None:
                _logger.debug(out.decode(errors='backslashreplace'))

    except BrokenPipeError:
        pass
    except BaseException as e:
        _logger.error("emulator exited: %s: %s", type(e).__name__, e)
        raise UnexpectedEmulatorExit from e

    return exitcode

def signal_handler(signal: int, frame: FrameType | None):
    global proc
    _logger.debug('Exiting')
    if proc:
        _logger.debug('killing proc')
        proc.kill()

def _resolve_rom_path(path_str: str) -> Path:
    if path_str == "config":
        return Path(path_str)
    return Path(path_str).resolve()



def launch() -> None:
    """Handles program arguments and exception handling to EmulationStation and logs.
    """
    with setup_logging():
        global proc
        proc = None
        signal.signal(signal.SIGINT, signal_handler)

        launch_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        _logger.info('=' * 20 + ' Retrobox ' + '=' * 20)
        _logger.info('emulatorlauncher started at: %s', launch_timestamp)

        parser = argparse.ArgumentParser(description='emulator-launcher script')

        maxnbplayers = 8
        for p in range(1, maxnbplayers+1):
            parser.add_argument(f"-p{p}index"     , help=f"player{p} controller index"            , type=int, required=False)
            parser.add_argument(f"-p{p}guid"      , help=f"player{p} controller SDL2 guid"        , type=str, required=False)
            parser.add_argument(f"-p{p}name"      , help=f"player{p} controller name"             , type=str, required=False)
            parser.add_argument(f"-p{p}devicepath", help=f"player{p} controller device"           , type=str, required=False)
            parser.add_argument(f"-p{p}nbbuttons" , help=f"player{p} controller number of buttons", type=int, required=False)
            parser.add_argument(f"-p{p}nbhats"    , help=f"player{p} controller number of hats"   , type=int, required=False)
            parser.add_argument(f"-p{p}nbaxes"    , help=f"player{p} controller number of axes"   , type=int, required=False)

        parser.add_argument(
            "-system",
            help="select the system to launch",
            type=str,
            required=True)

        parser.add_argument(
            "-rom",
            help="rom absolute path",
            type=_resolve_rom_path,
            required=True,
        )

        parser.add_argument(
            "-emulator",
            help="force emulator",
            type=str, required=False
        )
        
        parser.add_argument("-core",           help="force emulator core",         type=str, required=False)
        parser.add_argument("-netplaymode",    help="host/client",                 type=str, required=False)
        parser.add_argument("-netplaypass",    help="enable spectator mode",       type=str, required=False)
        parser.add_argument("-netplayip",      help="remote ip",                   type=str, required=False)
        parser.add_argument("-netplayport",    help="remote port",                 type=str, required=False)
        parser.add_argument("-netplaysession", help="netplay session",             type=str, required=False)
        parser.add_argument("-state_slot",     help="state slot",                  type=str, required=False)
        parser.add_argument("-state_filename", help="state filename",              type=str, required=False)
        parser.add_argument("-autosave",       help="autosave",                    type=str, required=False)
        parser.add_argument("-systemname",     help="system fancy name",           type=str, required=False)
        parser.add_argument("-gameinfoxml",    help="game info xml",               type=str, nargs='?', default='/dev/null', required=False)
        parser.add_argument("-lightgun",       help="configure lightguns",         action="store_true")
        parser.add_argument("-wheel",          help="configure wheel",             action="store_true")
        parser.add_argument("-trackball",      help="configure trackball",         action="store_true")
        parser.add_argument("-spinner",        help="configure spinner",           action="store_true")

        args = parser.parse_args()
        _logger.debug('args: %s', {k: v for k, v in vars(args).items() if v is not None and v is not False})
        
        exitcode = 0
        try:
            exitcode = main(args, maxnbplayers)
        except BaseRetroboxException as e:
            _logger.exception("configgen exception: ")
            exitcode = e.exit_code

            if isinstance(e, RetroboxException):
                Path('/tmp/launch_error.log').write_text(e.args[0])
        except Exception:
            _logger.exception("configgen exception: ")

        profiler.stop()

        time.sleep(1) # this seems to be required so that the gpu memory is restituated and available for es

        if exitcode < 0:
            signal_number = exitcode * -1

            if signal_number < signal.NSIG:
                signal_description = signal.strsignal(signal_number)

                if signal_description and ':' not in signal_description:
                    signal_description = f'{signal_description}: {signal_number}'

                _logger.debug("Emulator terminated by signal (%s)", signal_description)
                exitcode = 0

        _logger.debug("Exiting configgen with status %s", exitcode)

        exit(exitcode)

if __name__ == '__main__':
    launch()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
