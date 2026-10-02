#!/usr/bin/env python
# ruff: noqa: E402
"""Retrobox emulator launcher: prepares the environment and runs an emulator for a ROM."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from configgen.utils import bezels as bezels_util, metadata, videoMode, wheelsUtils
from configgen.utils.logger import setup_logging
from configgen.utils.overlayfs import mount_overlayfs
from configgen.utils.squashfs import mount_squashfs
from runtime.gamepadly.gamepadly_manager import GamepadManager
from runtime.paths import (
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
    MANGOHUD_BIN,
    NVIDIA_POWERD_SCRIPT,
    ES_GAMES_METADATA,
    ES_INPUT_CFG,
    GAMEPADLY_MAPPER,
    HOOKS,
    RUNTIME_DIR,
    SAVES,
    GUN_OVERLAYS_DIR,
    HUD_CONFIG_FILE,
    mkdir_if_not_exists,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import FrameType

    from runtime.launcher.configgen.Command import Command
    from runtime.launcher.configgen.batoceraTypes import Resolution
    from runtime.launcher.configgen.generators.Generator import Generator
    from runtime.launcher.configgen.gun import Guns

_logger = logging.getLogger(__name__)

_POWER_PROFILES_BIN = "powerprofilesctl"
_VALID_POWER_PROFILES = {"power-saver", "balanced", "performance"}

# Bezels must ALWAYS cover the whole target resolution. If the bezel aspect
# ratio does not match the screen one, it is stretched instead of being
# rejected or padded with black.
_BEZEL_STRETCH = True
# max cover proportion and ratio distortion (only used when not stretching)
_MAX_COVER = 0.05  # 5%
_MAX_RATIO_DELTA = 0.01

_HUD_POSITIONS = {"NW": "top-left", "NE": "top-right", "SE": "bottom-right"}
_HUD_PERF_LINES = (
    "background_alpha=0.4", "legacy_layout=false", "custom_text=%GAMENAME%",
    "custom_text=%SYSTEMNAME%", "custom_text=%EMULATORCORE%", "fps", "gpu_name",
    "engine_version", "vulkan_driver", "resolution", "ram", "gpu_stats", "gpu_temp",
    "cpu_stats", "cpu_temp", "core_load",
)
_HUD_GAME_LINES = (
    "background_alpha=0", "legacy_layout=false", "font_size=32", "image_max_width=200",
    "image=%THUMBNAIL%", "custom_text=%GAMENAME%", "custom_text=%SYSTEMNAME%",
    "custom_text=%EMULATORCORE%",
)

# per-player command-line options: (suffix, help text, type)
_PLAYER_ARGUMENTS = (
    ("index", "controller index", int),
    ("guid", "controller SDL2 guid", str),
    ("name", "controller name", str),
    ("devicepath", "controller device", str),
    ("nbbuttons", "controller number of buttons", int),
    ("nbhats", "controller number of hats", int),
    ("nbaxes", "controller number of axes", int),
)
# plain string command-line options: (name, help text)
_STRING_ARGUMENTS = (
    ("-emulator", "force emulator"),
    ("-core", "force emulator core"),
    ("-netplaymode", "host/client"),
    ("-netplaypass", "enable spectator mode"),
    ("-netplayip", "remote ip"),
    ("-netplayport", "remote port"),
    ("-netplaysession", "netplay session"),
    ("-state_slot", "state slot"),
    ("-state_filename", "state filename"),
    ("-autosave", "autosave"),
    ("-systemname", "system fancy name"),
)
_FLAG_ARGUMENTS = (
    ("-lightgun", "configure lightguns"),
    ("-wheel", "configure wheel"),
    ("-trackball", "configure trackball"),
    ("-spinner", "configure spinner"),
)


@dataclass
class _ControllerState:
    """Up-to-date list of player controllers, shared between threads."""

    # a lock to safely modify the active controller list from multiple threads
    lock: threading.Lock = field(default_factory=threading.Lock)
    controllers: list[Controller | None] = field(default_factory=list)


@dataclass
class _RunningProcess:
    """The emulator process currently running, so signals can kill it."""

    proc: subprocess.Popen[bytes] | None = None


@dataclass
class _GameSession:
    """Everything needed to run one game, shared by the launch helpers."""

    args: argparse.Namespace
    system: Emulator
    generator: Generator
    rom: Path
    guns: Guns
    resolution: Resolution
    controllers: list[Controller]
    wheels: Any
    metadata: dict[str, str]


@dataclass
class _Overlay:
    """A bezel image with its info file and the parsed info."""

    png: Path
    info_file: Path
    infos: dict[str, Any]


_controller_state = _ControllerState()
_running = _RunningProcess()


def main(args: argparse.Namespace, maxnbplayers: int) -> int:
    """Entry point that wraps start_rom, mounting the rom first if it is squashed.

    Args:
        args: Parsed command-line arguments.
        maxnbplayers: Maximum number of players/controllers supported.

    Returns:
        The exit code of the launched emulator command.
    """
    original_rom = args.rom

    # squashfs roms if squashed
    if original_rom.suffix == ".squashfs":
        with mount_squashfs(original_rom) as squash_rom:
            return start_rom(args, maxnbplayers, squash_rom, original_rom)
    return start_rom(args, maxnbplayers, original_rom, original_rom)


def _log_system_settings(system: Emulator) -> None:
    """Log the system settings (hiding passwords) and the selected emulator/core."""
    _logger.debug(
        "Settings: %s",
        {key: "***" if "password" in key else value for key, value in system.config.items()},
    )

    if "emulator" in system.config and "core" in system.config:
        _logger.debug("emulator: %s, core: %s", system.config.emulator, system.config.core)
    elif "emulator" in system.config:
        _logger.debug("emulator: %s", system.config.emulator)


def start_rom(args: argparse.Namespace, maxnbplayers: int, rom: Path, original_rom: Path) -> int:
    """Run the main ROM start sequence, calling into the rest of the module.

    Args:
        args: Parsed command-line arguments.
        maxnbplayers: Maximum number of players/controllers supported.
        rom: The (possibly squashfs-mounted) rom path to launch.
        original_rom: The original, unmounted rom path.

    Returns:
        The exit code of the launched emulator command.
    """
    mkdir_if_not_exists(RUNTIME_DIR)

    player_controllers = Controller.load_for_players(maxnbplayers, args)

    # initialize the shared state with the initial controller list
    with _controller_state.lock:
        _controller_state.controllers = list(player_controllers)

    # find the system to run
    _logger.debug("Running system: %s", args.system)
    system = Emulator(args, original_rom)
    _log_system_settings(system)

    # power profiles
    previous_power_profile = apply_power_profile(system.config.get("power_profile", "balanced"))

    game_metadata = metadata.get_games_meta_data(ES_GAMES_METADATA, args.system, rom)
    guns = Gun.get_and_precalibrate_all(system, rom)

    exit_code = 0
    with wheelsUtils.configure_wheels(
        player_controllers, system, game_metadata
    ) as (controllers, wheels):
        # find the generator
        generator = get_generator(system.config.emulator, system.config.core)

        with (
            mount_overlayfs(rom, Path(f"{SAVES}/{original_rom.parent.name}/{original_rom.stem}"))
            if original_rom.suffix == ".squashfs" and generator.writesToRom(system.config)
            else contextlib.nullcontext(rom)
        ) as game_rom:
            exit_code = _run_game(
                _GameSession(
                    args=args,
                    system=system,
                    generator=generator,
                    rom=game_rom,
                    guns=guns,
                    resolution=videoMode.getCurrentResolution(),
                    controllers=controllers,
                    wheels=wheels,
                    metadata=game_metadata,
                ),
                previous_power_profile,
            )
    return exit_code


def _effective_core(system: Emulator) -> str:
    """Return the configured core, or an empty string if there is none."""
    if "core" in system.config and system.config.core is not None:
        return system.config.core
    return ""


def _prepare_game_environment(system: Emulator) -> None:
    """Create the save directory and set the SDL VSync environment."""
    Path(f"{SAVES}/{system.name}").mkdir(parents=True, exist_ok=True)

    # SDL VSync is a big deal on OGA and RPi4
    system.config["sdlvsync"] = "1" if system.config.get_bool("sdlvsync", True) else "0"
    os.environ.update({"SDL_RENDER_VSYNC": system.config["sdlvsync"]})


def _call_game_hooks(session: _GameSession, state: str) -> None:
    """Run the global, system and game hooks for a game state."""
    extra_args = [session.system.config.emulator, _effective_core(session.system)]
    call_retrohook("_global", "_platform", state, extra_args)
    call_retrohook(session.args.system, "_platform", state, extra_args)
    call_retrohook(session.args.system, session.rom, state, extra_args)


def _run_game(session: _GameSession, previous_power_profile: str | None) -> int:
    """Run hooks and the emulator for a game, restoring the power profile at the end."""
    try:
        _prepare_game_environment(session.system)

        # run a script before emulator starts
        _call_game_hooks(session, "on-start-game")

        exit_code = _run_emulator(session)

        # run a script after emulator shuts down
        _call_game_hooks(session, "on-close-game")
        return exit_code
    finally:
        restore_power_profile(previous_power_profile)
        Path("/tmp/game.xml").unlink(missing_ok=True)


def _run_emulator(session: _GameSession) -> int:
    """Generate the emulator command, set up HUD and gun helpers, and run it."""
    system = session.system
    monitor_thread = threading.Thread(target=_controller_monitor_thread, daemon=True)

    with GamepadManager(
        system=session.args.system,
        emulator=system.config.emulator,
        core=_effective_core(system),
        rom=session.rom,
        controllers=session.controllers,
        mapper_script=GAMEPADLY_MAPPER,
        profiles_dir=_GAMEPADLY_PROFILES,
        user_profiles_dir=_GAMEPADLY_USER_PROFILES,
        es_input=ES_INPUT_CFG,
    ):
        # change directory if wanted
        execution_directory = session.generator.executionDirectory(system.config, session.rom)
        if execution_directory is not None:
            os.chdir(execution_directory)

        cmd = session.generator.generate(
            system,
            session.rom,
            session.controllers,
            session.metadata,
            session.guns,
            session.wheels,
            session.resolution,
        )

        _setup_hud(session, cmd)
        _generate_gun_help(session)
        _draw_internal_gun_borders(session)

        with profiler.pause():
            monitor_thread.start()
            return run_command(cmd)


def _setup_hud(session: _GameSession, cmd: Command) -> None:
    """Configure the MangoHud overlay (HUD and bezel) for the command, if enabled."""
    system = session.system
    if not system.config.get_bool("hud_support"):
        return

    hud_bezel = get_hud_bezel(
        system, session.generator, session.rom, session.resolution, session.guns
    )

    hud = system.config.get("hud")
    hud_enabled = bool(hud) and hud.lower() != "none"
    if not hud_enabled and hud_bezel is None:
        return

    mangohud_bin = _resolve_mangohud_binary()
    if mangohud_bin is None:
        _logger.info(
            "Skipping the HUD overlay: no usable MangoHud installation found (bundled or system)."
        )
        return

    _configure_mangohud_env(cmd, mangohud_bin)

    hud_config = get_hud_config(
        system,
        session.args.systemname,
        system.config.emulator,
        _effective_core(system),
        hud_bezel,
    )
    HUD_CONFIG_FILE.write_text(hud_config, encoding="utf-8")

    if session.generator.usesOpenGLDirectPreload(system.config):
        # OpenGL: run through the mangohud wrapper in dlsym-hook mode. The
        # installed wrapper now hardcodes the real lib64 path instead of
        # relying on ld.so to expand "$LIB" (several launchers, including
        # sharun-wrapped emulators, never expand it), so "mangohud --dlsym"
        # is safe to use again instead of setting LD_PRELOAD by hand here.
        cmd.array = [str(mangohud_bin), "--dlsym", *cmd.array]

    # Vulkan: MANGOHUD=1 is enough to trigger the Vulkan Implicit Layer on
    # its own. We deliberately do NOT prepend the mangohud binary to
    # cmd.array here, since doing so triggers a fatal
    # "eglStreamPostD3DTextureANGLE" error on Asahi.


def _generate_gun_help(session: _GameSession) -> None:
    """Generate the gun help image, never failing the launch."""
    system = session.system
    try:
        bezels_util.generate_gun_help(
            session.args.system,
            session.rom,
            system.config.use_guns,
            session.guns,
            GUN_OVERLAYS_DIR,
            "gun_help.png",
            session.resolution,
        )
    except Exception as err:  # pylint: disable=broad-exception-caught
        # best effort: a missing gun help must never prevent the game from starting
        _logger.error("Failed to generate the gun help image")
        _logger.error(err)


def _draw_internal_gun_borders(session: _GameSession) -> None:
    """Draw the configgen internal gun borders if needed, never failing the launch."""
    system = session.system
    try:
        if not (system.config.use_guns and session.guns):
            return

        if session.generator.supportsInternalBezels() or system.config.get_bool("hud_support"):
            _logger.debug(
                "skipping configgen internal gun borders for emulator %s", system.config.emulator
            )
            return

        gun_border_size_name = system.guns_borders_size_name(session.guns)
        if gun_border_size_name is None:
            return

        _logger.debug(
            "using configgen internal gun borders for emulator %s", system.config.emulator
        )
        # pylint: disable-next=import-outside-toplevel
        from configgen.utils.gun_borders import draw_gun_borders

        draw_gun_borders(
            gun_border_size_name,
            bezels_util.guns_borders_color_from_config(system.config),
            system.guns_border_ratio_type(session.guns),
        )
    except Exception as err:  # pylint: disable=broad-exception-caught
        # best effort: missing gun borders must never prevent the game from starting
        _logger.error("Failed to draw_gun_borders for gun_borders")
        _logger.error(err)


def _bezel_settings(system: Emulator) -> tuple[str, str, str]:
    """Return the (bezel, tattoo, qrcode) settings, all unset if force_no_bezel is on."""
    if bezels_util.bezel_is_disabled(system.config):
        _logger.debug("bezel disabled by force_no_bezel")
        return "none", "0", "0"
    return (
        system.config.get_str("bezel", "none"),
        system.config.get_str("bezel.tattoo", "0"),
        system.config.get_str("bezel.qrcode", "0"),
    )


def _nothing_to_draw(bezel: str, tattoo: str, qrcode: str) -> bool:
    """Return True when there is no bezel, tattoo or QR code to draw."""
    return (
        (not bezel or bezel == "none")
        and (not tattoo or tattoo == "0")
        and (not qrcode or qrcode == "0")
    )


def _load_overlay(
    system: Emulator, rom: Path, resolution: Resolution, bezel: str
) -> _Overlay | None:
    """Find the bezel to use (or generate a transparent one) and read its info."""
    if not bezel or bezel == "none":
        # no bezel: generate a transparent one for the tattoo/gun borders and so on
        png_file = Path("/tmp/bezel_transhud_black.png")
        info_file = Path("/tmp/bezel_transhud_black.info")
        width = resolution["width"]
        height = resolution["height"]
        bezels_util.create_transparent_bezel(png_file, width, height)
        info_file.write_text(
            f'{{ "width":{width}, "height":{height}, "opacity":1.0000000, '
            '"messagex":0.220000, "messagey":0.120000 }',
            encoding="utf-8",
        )
    else:
        _logger.debug("hud enabled. trying to apply the bezel %s", bezel)

        bezel_infos = bezels_util.get_bezel_infos(rom, bezel, system.name, system.config.emulator)
        if bezel_infos is None:
            _logger.debug("no bezel info file found")
            return None

        info_file = bezel_infos["info"]
        png_file = bezel_infos["png"]

    return _Overlay(png_file, info_file, _read_bezel_infos(info_file))


def _read_bezel_infos(info_file: Path) -> dict[str, Any]:
    """Read a bezel info file, returning an empty dict if missing or unreadable."""
    if not info_file.exists():
        return {}
    try:
        with info_file.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        _logger.warning("unable to read %s", info_file)
        return {}


def _bezel_size(overlay: _Overlay) -> tuple[int, int]:
    """Return the bezel size, from its info file if possible, else from the PNG."""
    if "width" in overlay.infos and "height" in overlay.infos:
        _logger.info("bezel size read from %s", overlay.info_file)
        return overlay.infos["width"], overlay.infos["height"]
    _logger.info("bezel size read from %s", overlay.png)
    return bezels_util.fast_image_size(overlay.png)


def _bezel_fits(
    infos: dict[str, Any],
    bezel_size: tuple[int, int],
    resolution: Resolution,
    ingame_ratio: float,
) -> bool:
    """Check that the bezel is compatible with the screen and the in-game image.

    Only used when the bezel is not stretched: the screen and bezel ratios must
    be approximately the same, and bottom, top, left and right must not cover
    too much of the game image.
    """
    bezel_width, bezel_height = bezel_size
    screen_ratio = resolution["width"] / resolution["height"]
    bezel_ratio = bezel_width / bezel_height

    if abs(screen_ratio - bezel_ratio) > _MAX_RATIO_DELTA:
        _logger.debug(
            "screen ratio (%s) is too far from the bezel one (%s) : delta > %s",
            screen_ratio, bezel_ratio, _MAX_RATIO_DELTA,
        )
        return False

    # the bezel top and bottom cover must be minimum
    # (if there is no information about top/bottom, assume default is 0)
    for side in ("top", "bottom"):
        if side in infos and infos[side] / bezel_height > _MAX_COVER:
            _logger.debug(
                "bezel %s covers too much the game image : %s / %s > %s",
                side, infos[side], bezel_height, _MAX_COVER,
            )
            return False

    # the bezel left and right cover must be maximum
    img_width = bezel_height * ingame_ratio
    margin = (bezel_width - img_width) / 2.0
    # assume default is 4/3 over 16/9
    default_side = (bezel_width - (bezel_height / 3 * 4)) / 2
    for side in ("left", "right"):
        delta = infos.get(side, default_side) - margin
        if abs(delta / img_width) > _MAX_COVER:
            _logger.debug(
                "bezel %s covers too much the game image : %s / %s > %s",
                side, delta, img_width, _MAX_COVER,
            )
            return False
    return True


def _resize_bezel(
    overlay: _Overlay, bezel_size: tuple[int, int], resolution: Resolution
) -> Path | None:
    """Resize the bezel (and its info file) to the screen resolution."""
    _logger.debug("bezel needs to be resized")
    width = resolution["width"]
    height = resolution["height"]
    output_png = Path("/tmp/bezel.png")
    try:
        bezels_util.resize_image(overlay.png, output_png, width, height, _BEZEL_STRETCH)

        # The PNG has been stretched independently in X/Y. The sidecar .info
        # must receive the same transformation so the game's opening stays
        # aligned with the transparent opening in the bezel.
        if overlay.info_file.exists():
            bezels_util.resize_info(
                overlay.info_file,
                Path("/tmp/bezel.info"),
                bezel_size[0],
                bezel_size[1],
                width,
                height,
                keep_aspect_ratio=not _BEZEL_STRETCH,
            )
    except (OSError, ValueError, RetroboxException) as err:
        _logger.error("failed to resize the image %s", err)
        return None
    return output_png


def _add_tattoo_and_qrcode(system: Emulator, overlay_png: Path, tattoo: str, qrcode: str) -> Path:
    """Add the tattoo and the RetroAchievements QR code to the bezel, if enabled."""
    if tattoo != "0":
        output_png = Path("/tmp/bezel_tattooed.png")
        bezels_util.tattoo_image(overlay_png, output_png, system)
        overlay_png = output_png

    if qrcode != "0" and (cheevos_id := system.es_game_info.get("cheevosId", "0")) != "0":
        output_png = Path("/tmp/bezel_qrcode.png")
        bezels_util.add_qr_code(overlay_png, output_png, cheevos_id, system)
        overlay_png = output_png

    return overlay_png


def _add_gun_borders(
    system: Emulator, overlay_png: Path, borders_size: str, guns: Guns
) -> Path:
    """Draw the gun borders on the bezel."""
    _logger.debug("Draw gun borders")
    output_png = Path("/tmp/bezel_gunborders.png")
    inner_size, outer_size = bezels_util.gun_borders_size(borders_size)
    borders_ratio = system.guns_border_ratio_type(guns)
    _logger.debug("Gun border ratio = %s", borders_ratio)
    bezels_util.gun_border_image(
        overlay_png,
        output_png,
        borders_ratio,
        inner_size,
        outer_size,
        bezels_util.guns_borders_color_from_config(system.config),
    )
    return output_png


def get_hud_bezel(
    system: Emulator,
    generator: Generator,
    rom: Path,
    game_resolution: Resolution,
    guns: Guns,
) -> Path | None:
    """Build the bezel image used as MangoHud background.

    Returns:
        The path of the final bezel image, or None if no bezel must be drawn.
    """
    if generator.supportsInternalBezels():
        _logger.debug("skipping bezels for emulator %s", system.config.emulator)
        return None

    bezel, tattoo, qrcode = _bezel_settings(system)
    borders_size = system.guns_borders_size_name(guns)

    # no good reason for a bezel
    if _nothing_to_draw(bezel, tattoo, qrcode) and borders_size is None:
        return None

    overlay = _load_overlay(system, rom, game_resolution, bezel)
    if overlay is None:
        return None

    bezel_size = _bezel_size(overlay)

    # in case there are gun borders, skip the compatibility checks
    if not _BEZEL_STRETCH and borders_size is None:
        ingame_ratio = generator.getInGameRatio(system.config, game_resolution, rom)
        if not _bezel_fits(overlay.infos, bezel_size, game_resolution, ingame_ratio):
            return None

    overlay_png = overlay.png
    # if screen and bezel sizes don't match, resize
    if bezel_size != (game_resolution["width"], game_resolution["height"]):
        overlay_png = _resize_bezel(overlay, bezel_size, game_resolution)
        if overlay_png is None:
            return None

    overlay_png = _add_tattoo_and_qrcode(system, overlay_png, tattoo, qrcode)
    if borders_size is not None:
        overlay_png = _add_gun_borders(system, overlay_png, borders_size, guns)

    _logger.debug("applying bezel %s", overlay_png)
    return overlay_png


def _sanitize_hook_name(name: str) -> str:
    """Sanitize a name for use as a path component under retrohook.d/.

    Only affects the hook directory lookup, not the args passed to the script.
    """
    name = name.replace("/", "_")  # the only truly illegal char on Linux
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)  # control chars
    return name[:255]  # filename limit on ext4/btrfs


def call_retrohook(
    platform: str,
    game: str | Path,
    state: str,  # "on-start-game" | "on-close-game"
    extra_args: Iterable[str | Path] = (),
) -> None:
    """Invoke retrobox's hook system.

    Delegates all hierarchy and execution logic to the retrohook bash script.
    """
    if not HOOKS.is_file() or not os.access(HOOKS, os.X_OK):
        _logger.debug("retrohook not found or not executable: %s", HOOKS)
        return

    game_hook_name = _sanitize_hook_name(Path(game).stem)  # for the path

    cmd = [str(HOOKS), platform, game_hook_name, state, str(game), *map(str, extra_args)]

    _logger.info("[retrohook] %s %s %s", platform, game_hook_name, state)
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        _logger.warning("[retrohook] exited with code %s", result.returncode)


def _protect_str(string: str | Path | None) -> str:
    """Convert a value to a string, mapping None to an empty string."""
    if string is None:
        return ""
    return str(string)


def get_hud_config(
    system: Emulator,
    system_name: str | None,
    emulator: str,
    core: str | None,
    bezel: Path | None,
) -> str:
    """Build the MangoHud configuration text for the current game."""
    configstr = ""

    if bezel is not None:
        configstr = f"background_image={_protect_str(bezel)}\nlegacy_layout=false\n"

    mode = system.config.get("hud", "none")
    if mode == "none":
        return configstr + "background_alpha=0\n"  # hide the background

    hud_position = _HUD_POSITIONS.get(system.config.get("hud_corner", ""), "bottom-left")

    emulator_str = emulator
    if core and core != emulator:
        emulator_str += f"/{core}"

    # predefined values
    if mode == "perf":
        configstr += f"position={hud_position}\n" + "\n".join(_HUD_PERF_LINES) + "\n"
    elif mode == "game":
        configstr += f"position={hud_position}\n" + "\n".join(_HUD_GAME_LINES)
    elif mode == "custom" and (hud_custom := system.config.get_str("hud_custom")):
        configstr += hud_custom.replace("\\n", "\n")
    else:
        configstr += "background_alpha=0\n"  # hide the background

    replacements = {
        "%SYSTEMNAME%": system_name,
        "%GAMENAME%": system.es_game_info.get("name", ""),
        "%EMULATORCORE%": emulator_str,
        "%THUMBNAIL%": system.es_game_info.get("thumbnail", ""),
    }
    for placeholder, value in replacements.items():
        configstr = configstr.replace(placeholder, _protect_str(value))
    return configstr


def _resolve_mangohud_binary() -> Path | None:
    """Resolve which MangoHud binary to use for the HUD overlay.

    Retrobox ships its own MangoHud build (with bezel support) under
    MANGOHUD_BIN, kept in a private prefix so it never shadows a
    system-wide install. That bundled build is preferred; if it's
    missing, fall back to whatever "mangohud" is on PATH (which may or
    may not support bezels); if neither is available, the HUD overlay
    is skipped entirely rather than failing the launch.

    Returns:
        The Path to the MangoHud binary to use, or None if none is
        available.
    """
    if MANGOHUD_BIN.is_file() and os.access(MANGOHUD_BIN, os.X_OK):
        return MANGOHUD_BIN

    if system_mangohud := shutil.which("mangohud"):
        _logger.warning(
            "Bundled MangoHud not found at %s, falling back to the system "
            "'mangohud' (bezel support may not be available).",
            MANGOHUD_BIN,
        )
        return Path(system_mangohud)

    return None


def _configure_mangohud_env(cmd: Command, mangohud_bin: Path) -> None:
    """Set the environment variables that drive the MangoHud Vulkan layer.

    There are two distinct MangoHud installs that can be in play:

    - The bundled retrobox build (bezel/background_image support),
      registered under its own "RETROBOX_MANGOHUD" implicit layer so it
      never collides with a system-wide install.
    - Whatever system-wide "mangohud" (apt/dnf, etc.) might be
      installed, registered under the vanilla "MANGOHUD" implicit
      layer, with no bezel support.

    Only one should ever be enabled for a given launch, and the other
    one's implicit layer must be actively disabled -- not left alone --
    so it can't "conquer" a process retrobox is trying to overlay.

    Important Vulkan Loader gotcha: a layer's "disable_environment"
    check is presence-only, not value-based. Setting a variable to "0"
    still counts as "present" and forces the layer off regardless of
    any other variable. So to truly enable a layer, its own *_DISABLE
    variable must be entirely absent from the child's environment, not
    merely set to a falsy value. cmd.env supports this via a None
    sentinel: run_command() strips any key whose value is None from the
    environment it hands to the child process, instead of just setting
    it to "0".

    Args:
        cmd: The Command whose env will be updated in place.
        mangohud_bin: The MangoHud binary resolved by
            _resolve_mangohud_binary(), used to tell which of the two
            installs is actually going to run.
    """
    if mangohud_bin == MANGOHUD_BIN:
        # Bundled retrobox build: drive it via its own layer, and force
        # the system layer off.
        cmd.env["RETROBOX_MANGOHUD"] = "1"
        cmd.env["RETROBOX_MANGOHUD_DISABLE"] = None
        cmd.env["MANGOHUD"] = "0"
        cmd.env["DISABLE_MANGOHUD"] = "1"
    else:
        # Fell back to whatever "mangohud" is on PATH. That build has
        # no notion of RETROBOX_MANGOHUD, and doesn't carry the
        # background_image/bezel patch, so this is a best-effort
        # overlay without bezel support.
        _logger.info(
            "Using the system MangoHud install for the HUD overlay "
            "(bezel/background image will not be rendered)."
        )
        cmd.env["MANGOHUD"] = "1"
        cmd.env["DISABLE_MANGOHUD"] = None
        cmd.env["RETROBOX_MANGOHUD"] = "0"
        cmd.env["RETROBOX_MANGOHUD_DISABLE"] = "1"

    cmd.env["MANGOHUD_CONFIGFILE"] = str(HUD_CONFIG_FILE)


def _set_nvidia_powerd(enable: bool) -> None:
    """Start or stop nvidia-powerd.service via the nvidia-powerd-service script.

    Never raises: only logs warnings if something fails.

    Makes sure the 'nvidia-powerd' binary actually exists on the system
    before attempting anything, guaranteeing full compatibility with
    AMD, Intel, Apple, Qualcomm, older Nvidia systems, or devices like
    the Switch.
    """
    # 1. Check that our helper script exists and is executable
    if not os.path.isfile(NVIDIA_POWERD_SCRIPT) or not os.access(NVIDIA_POWERD_SCRIPT, os.X_OK):
        _logger.debug(
            "%s not found or not executable, skipping nvidia-powerd management",
            NVIDIA_POWERD_SCRIPT,
        )
        return

    # 2. Check that the real system binary exists in PATH.
    # If it doesn't, abort silently. This protects systems without nvidia-powerd.
    if shutil.which("nvidia-powerd") is None:
        _logger.debug(
            "nvidia-powerd binary not found in system PATH, skipping nvidia-powerd management"
        )
        return

    action = "start" if enable else "stop"
    try:
        subprocess.run(
            [NVIDIA_POWERD_SCRIPT, action],
            check=True, capture_output=True, text=True, timeout=15,
        )
        _logger.info("nvidia-powerd %s", "started" if enable else "stopped")
    except subprocess.CalledProcessError as err:
        _logger.warning(
            "failed to %s nvidia-powerd: %s",
            action, err.stderr.strip() if err.stderr else err,
        )
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("failed to %s nvidia-powerd: %s", action, err)


def _powerprofilesctl(*args: str) -> subprocess.CompletedProcess[str]:
    """Run powerprofilesctl with the given arguments, raising on failure."""
    return subprocess.run(
        [_POWER_PROFILES_BIN, *args],
        check=True, capture_output=True, text=True,
    )


def apply_power_profile(desired_profile: str) -> str | None:
    """Apply the requested power profile.

    Also starts nvidia-powerd if the profile is 'performance', and stops it in
    any other case.

    Returns:
        The profile that was active before, or None if it couldn't be read or
        powerprofilesctl isn't available.
    """
    desired_profile = (desired_profile or "balanced").strip().lower()
    if desired_profile not in _VALID_POWER_PROFILES:
        _logger.warning("unknown power_profile '%s', falling back to 'balanced'", desired_profile)
        desired_profile = "balanced"

    # nvidia-powerd management: independent of powerprofilesctl.
    _set_nvidia_powerd(desired_profile == "performance")

    if shutil.which(_POWER_PROFILES_BIN) is None:
        _logger.debug("%s not found, skipping power profile management", _POWER_PROFILES_BIN)
        return None

    previous_profile = None
    try:
        previous_profile = _powerprofilesctl("get").stdout.strip()
        _logger.debug("current power profile before launch: %s", previous_profile)
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("could not read current power profile: %s", err)

    if previous_profile == desired_profile:
        _logger.debug("power profile already '%s', nothing to do", desired_profile)
        return previous_profile

    try:
        _powerprofilesctl("set", desired_profile)
        _logger.info("power profile set to '%s'", desired_profile)
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("failed to set power profile to '%s': %s", desired_profile, err)

    return previous_profile


def restore_power_profile(previous_profile: str | None) -> None:
    """Restore the power profile that was active before the game started."""
    # nvidia-powerd should only stay active if we're going back to
    # 'performance'; for 'balanced', 'power-saver', or no valid previous
    # profile, it gets stopped.
    _set_nvidia_powerd(previous_profile == "performance")

    if not previous_profile or previous_profile not in _VALID_POWER_PROFILES:
        return
    try:
        _powerprofilesctl("set", previous_profile)
        _logger.info("power profile restored to '%s'", previous_profile)
    except (OSError, subprocess.SubprocessError) as err:
        _logger.warning("failed to restore power profile to '%s': %s", previous_profile, err)


def _init_sdl_joystick() -> bool:
    """Initialize the SDL2 joystick subsystem if needed.

    Returns:
        True if this call initialized it, False if the host had already done it.
    """
    if sdl2.SDL_WasInit(sdl2.SDL_INIT_JOYSTICK) != 0:
        _logger.info(
            ">>> SDL2 joystick subsystem already initialized by host (emulator). "
            "Will not re-initialize."
        )
        return False

    _logger.info(">>> SDL2 joystick subsystem not initialized. Initializing it now.")
    sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK)
    return True


def _scan_online_controllers() -> dict[str, str]:
    """Return a GUID -> device path map of the joysticks currently seen by SDL2."""
    sdl2.SDL_JoystickUpdate()
    online_controllers: dict[str, str] = {}
    for index in range(sdl2.SDL_NumJoysticks()):
        try:
            guid_struct = sdl2.SDL_JoystickGetDeviceGUID(index)
            guid_buffer = (ctypes.c_char * 33)()
            sdl2.SDL_JoystickGetGUIDString(guid_struct, guid_buffer, 33)
            guid = guid_buffer.value.decode("utf-8")

            path_bytes = sdl2.SDL_JoystickPathForIndex(index)
            path = path_bytes.decode("utf-8") if path_bytes else None

            if guid and path:
                online_controllers[guid] = path
        except Exception as err:  # pylint: disable=broad-exception-caught
            # one misbehaving device must not stop the monitoring of the others
            _logger.warning("Error while querying joystick index %s with pysdl2: %s", index, err)
    return online_controllers


def _sync_active_controllers(
    snapshot: list[Controller | None], online_controllers: dict[str, str]
) -> None:
    """Revive the original controller objects and update the shared active list.

    Reusing the original objects preserves the player order without disrupting
    the emulator.
    """
    with _controller_state.lock:
        new_active: list[Controller | None] = [None] * len(snapshot)

        for index, controller in enumerate(snapshot):
            if controller and controller.guid in online_controllers:
                new_path = online_controllers[controller.guid]
                if controller.device_path != new_path:
                    _logger.info(
                        ">>> [Revival] Player %s (GUID: %s) path has changed.",
                        controller.player_number, controller.guid,
                    )
                    controller.device_path = new_path
                new_active[index] = controller

        current_paths = [c.device_path if c else None for c in _controller_state.controllers]
        new_paths = [c.device_path if c else None for c in new_active]

        if current_paths != new_paths:
            _logger.info(
                ">>> [Check 2] Controller state changed. Old Paths: %s. New Paths: %s",
                current_paths, new_paths,
            )
            _controller_state.controllers = new_active
        else:
            _logger.info(">>> [Check 2] No change in assigned controller paths detected.")


def _controller_monitor_thread() -> None:
    """Watch for controller add/remove events in the background.

    Uses pysdl2 to reliably get controller GUIDs and paths, then intelligently
    "revives" the original controller object to preserve player order without
    disrupting the emulator.
    """
    with _controller_state.lock:
        snapshot = deepcopy(_controller_state.controllers)
        for index, controller in enumerate(snapshot):
            if controller and controller.guid:
                _logger.info(
                    ">>>   [P%s] Stored GUID: %s, Initial Path: %s",
                    index + 1, controller.guid, controller.device_path,
                )

    try:
        we_initialized_sdl = _init_sdl_joystick()
    except Exception as err:  # pylint: disable=broad-exception-caught
        # a background thread must log and stop instead of dying with a traceback
        _logger.error("FATAL: Could not initialize pysdl2 for controller monitoring: %s", err)
        return

    monitor = pyudev.Monitor.from_netlink(pyudev.Context())
    monitor.filter_by(subsystem="input")

    _logger.info(">>> Starting background controller monitor.")
    for device in iter(monitor.poll, None):
        if device.properties.get("ID_INPUT_JOYSTICK") != "1":
            continue

        _logger.info("--- Joystick Event Detected: %s on %s ---", device.action, device.sys_path)

        online_controllers = _scan_online_controllers()
        _logger.info(">>> [Check 1] Pysdl2 scan found online controllers: %s", online_controllers)
        _sync_active_controllers(snapshot, online_controllers)

    if we_initialized_sdl:
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_JOYSTICK)


def run_command(command: Command) -> int:
    """Run the generated command with subprocess.Popen.

    Also handles error codes and exceptions to send them to main() and launch().
    """
    # Compute the environment: current os.environ overridden by
    # generator-level values. A None value in command.env means "unset
    # this variable, even if it's currently inherited from the parent
    # environment" -- e.g. to defeat a login-session default such as
    # RETROBOX_MANGOHUD_DISABLE=1. This is a local variable rather than
    # something stored back on `command`, since subprocess.Popen (and
    # Command itself) only understand str/Path values, never None.
    envvars: dict[str, str | Path] = dict(os.environ)
    for key, value in command.env.items():
        if value is None:
            envvars.pop(key, None)
        else:
            envvars[key] = value

    _logger.info("command: %s", command.array)
    _logger.debug("env: %s", envvars)

    if not command.array:
        raise BadCommandLineArguments

    with Path("/tmp/env-launcher.txt").open("w", encoding="utf-8") as env_file:
        for key, value in sorted(envvars.items()):
            print(f"{key}={value}", file=env_file)

    exitcode = 0

    try:
        with subprocess.Popen(
            command.array,
            env=envvars,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:
            _running.proc = process
            out, err = process.communicate()
            exitcode = process.returncode

            if err is not None:
                _logger.error(err.decode(errors="backslashreplace"))

            if out is not None:
                _logger.debug(out.decode(errors="backslashreplace"))

    except BrokenPipeError:
        pass
    except BaseException as err:
        _logger.error("emulator exited: %s: %s", type(err).__name__, err)
        raise UnexpectedEmulatorExit from err

    return exitcode


def signal_handler(sig: int, _frame: FrameType | None) -> None:
    """Kill the running emulator process when the launcher is interrupted."""
    _logger.debug("Exiting (signal %s)", sig)
    if _running.proc:
        _logger.debug("killing proc")
        _running.proc.kill()


def _resolve_rom_path(path_str: str) -> Path:
    """Resolve the rom path, leaving the special "config" value untouched."""
    if path_str == "config":
        return Path(path_str)
    return Path(path_str).resolve()


def _build_argument_parser(maxnbplayers: int) -> argparse.ArgumentParser:
    """Build the command-line parser of the launcher."""
    parser = argparse.ArgumentParser(description="emulator-launcher script")

    for player in range(1, maxnbplayers + 1):
        for suffix, description, arg_type in _PLAYER_ARGUMENTS:
            parser.add_argument(
                f"-p{player}{suffix}",
                help=f"player{player} {description}",
                type=arg_type,
                required=False,
            )

    parser.add_argument(
        "-system", help="select the system to launch", type=str, required=True
    )
    parser.add_argument(
        "-rom", help="rom absolute path", type=_resolve_rom_path, required=True
    )

    for name, description in _STRING_ARGUMENTS:
        parser.add_argument(name, help=description, type=str, required=False)

    parser.add_argument(
        "-gameinfoxml", help="game info xml", type=str, nargs="?", default="/dev/null",
        required=False,
    )

    for name, description in _FLAG_ARGUMENTS:
        parser.add_argument(name, help=description, action="store_true")

    return parser


def _normalize_exit_code(exitcode: int) -> int:
    """Map an exit code caused by a signal (negative value) to a clean exit."""
    if exitcode >= 0:
        return exitcode

    signal_number = -exitcode
    if signal_number >= signal.NSIG:
        return exitcode

    signal_description = signal.strsignal(signal_number)
    if signal_description and ":" not in signal_description:
        signal_description = f"{signal_description}: {signal_number}"

    _logger.debug("Emulator terminated by signal (%s)", signal_description)
    return 0


def launch() -> None:
    """Handle program arguments and exception handling to EmulationStation and logs."""
    with setup_logging():
        _running.proc = None
        signal.signal(signal.SIGINT, signal_handler)

        _logger.info("%s Retrobox %s", "=" * 20, "=" * 20)
        _logger.info(
            "emulatorlauncher started at: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        maxnbplayers = 8
        args = _build_argument_parser(maxnbplayers).parse_args()
        _logger.debug(
            "args: %s", {k: v for k, v in vars(args).items() if v is not None and v is not False}
        )

        exitcode = 0
        try:
            exitcode = main(args, maxnbplayers)
        except BaseRetroboxException as err:
            _logger.exception("configgen exception: ")
            exitcode = err.exit_code

            if isinstance(err, RetroboxException):
                Path("/tmp/launch_error.log").write_text(err.args[0], encoding="utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            # last-resort handler: log everything and exit cleanly for EmulationStation
            _logger.exception("configgen exception: ")

        profiler.stop()

        # this seems to be required so that the gpu memory is restituated and available for es
        time.sleep(1)

        exitcode = _normalize_exit_code(exitcode)

        _logger.debug("Exiting configgen with status %s", exitcode)

        sys.exit(exitcode)


if __name__ == "__main__":
    launch()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4: