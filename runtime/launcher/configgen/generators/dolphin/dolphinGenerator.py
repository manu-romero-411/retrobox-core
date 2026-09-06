from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from runtime.launcher.configgen.Emulator import generate_bash_wrapper

from . import dolphin_config
from . import dolphin_controllers
from ... import Command
from runtime.paths import configure_emulator, mkdir_if_not_exists
from ..Generator import Generator
from .dolphin_paths import (
    _DOLPHIN_LOCALE,
    _DOLPHIN_XDG,
    DOLPHIN_BIN,
    DOLPHIN_BIN_NOGUI,
    DOLPHIN_SAVES,
    DOLPHIN_SYSCONF,
)

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

_logger = logging.getLogger(__name__)


class DolphinGenerator(Generator):
    def usesOpenGLDirectPreload(self, config) -> bool:
        return config.get("gfxbackend") == "OGL"

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        self.check_if_exists(DOLPHIN_BIN, system.config.emulator)

        # Dirs required for saves
        mkdir_if_not_exists(DOLPHIN_SAVES / "StateSaves")
        mkdir_if_not_exists(DOLPHIN_SAVES / "GameSettings")

        # Controller mapping (per-pad ini files: GCPadNew.ini / WiimoteNew.ini)
        dolphin_controllers.generateControllerConfig(system, playersControllers, metadata, wheels, rom, guns)

        # dolphin.ini: custom paths, discord rpc, rendering api, controller port types
        dolphin_config.write_dolphin_ini(system, playersControllers, wheels)

        # gfx.ini: aspect ratio, scaling multiplier, GPU adapter for Vulkan
        dolphin_config.write_gfx_ini(system)

        # Hotkeys.ini
        dolphin_config.write_hotkeys_ini()

        # SYSCONF: keep the Wii's internal aspect-ratio flag in sync
        dolphin_config.update_sysconf_aspect_ratio(system.config, DOLPHIN_SYSCONF, gameResolution)

        dolphin_exec_env = {
            "XDG_CONFIG_HOME": _DOLPHIN_XDG,
            "XDG_DATA_HOME": _DOLPHIN_XDG,
            "LOCPATH": str(_DOLPHIN_LOCALE),
            "SDL_JOYSTICK_HIDAPI": "1",
            "SDL_JOYSTICK_HIDAPI_SWITCH": "1",
            "SDL_JOYSTICK_HIDAPI_PRO": "1",
            "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",
        }

        if configure_emulator(rom):
            selected_bin = DOLPHIN_BIN
            dolphin_args = []  # config mode, no -b -e
        else:
            selected_bin = DOLPHIN_BIN_NOGUI
            dolphin_args = [
                "-C", "Dolphin.Display.Fullscreen=True",
                "-e", str(rom)]

        if state_filename := system.config.get('state_filename'):
            dolphin_args.extend(["--save_state", state_filename])

        command_wrapper = [generate_bash_wrapper(system.config.emulator, selected_bin, dolphin_args)]

        return Command.Command(
            array=command_wrapper,
            env=dolphin_exec_env
        )

    def getInGameRatio(self, config, gameResolution, rom):
        return dolphin_config.get_in_game_ratio(config, gameResolution)

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "dolphin",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"],
                      "previous_slot": [ "KEY_LEFTSHIFT", "KEY_F2" ], "next_slot": [ "KEY_LEFTSHIFT", "KEY_F1" ], "save_state": "KEY_F5", "restore_state": "KEY_F8" }
        }