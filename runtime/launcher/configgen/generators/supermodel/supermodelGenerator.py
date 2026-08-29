from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .supermodel_config import configPadsIni
from .supermodel_paths import _SUPERMODEL_EMUDIR, SUPERMODEL_BIN

from ... import Command
from runtime.paths import (
    EMULATORS,
    LOGS
)

from ...controller import generate_sdl_game_controller_config
from ...gun import guns_need_crosses
from ..Generator import Generator

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

class SupermodelGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "supermodel",
            "keys": { "exit": "KEY_ESC", "menu": ["KEY_LEFTALT", "KEY_P"], "pause": ["KEY_LEFTALT", "KEY_P"], "reset": ["KEY_LEFTALT", "KEY_R"],
                      "save_state": "KEY_F5", "restore_state": "KEY_F7", "next_state": "KEY_F6"
                     }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        command_array: list[str | Path] = [SUPERMODEL_BIN, "-fullscreen", "-channels=2"]

        # legacy3d
        if system.config.get("engine3D") == "new3d":
            command_array.append("-new3d")
        else:
            command_array.extend(["-multi-texture", "-legacy-scsp", "-legacy3d"])

        # widescreen
        if system.config.get_bool("m3_wideScreen"):
            command_array.append("-wide-screen")
            command_array.append("-wide-bg")
            system.config["bezel"] == "none"

        # quad rendering
        if system.config.get_bool("quadRendering"):
            command_array.append("-quad-rendering")

        # crosshairs
        if crosshairs := system.config.get("crosshairs"):
            command_array.append(f"-crosshairs={crosshairs}")
        else:
            if guns_need_crosses(guns):
                if len(guns) == 1:
                    command_array.append("-crosshairs=1")
                else:
                    command_array.append("-crosshairs=3")

        # force feedback
        if system.config.get_bool("forceFeedback"):
            command_array.append("-force-feedback")

        # powerpc frequesncy
        if freq := system.config.get("ppcFreq"):
            command_array.append(f"-ppc-frequency={freq}")

        # crt colour
        if color := system.config.get("crt_colour"):
            command_array.append(f"-crtcolors={color}")

        # upscale mode
        if upscale_mode := system.config.get("upscale_mode"):
            command_array.append(f"-upscalemode={upscale_mode}")

        # resolution
        command_array.append(f"-res={gameResolution['width']},{gameResolution['height']}")

        # logs
        command_array.extend([f"-log-output={LOGS}/Supermodel.log", rom])

        # controller config
        configPadsIni(system, rom, guns)
        os.chdir(_SUPERMODEL_EMUDIR)
        return Command.Command(
            array=command_array,
            env={
                "XDG_CONFIG_HOME": EMULATORS,
                "SDL_VIDEODRIVER": "x11",
                "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
                "SDL_JOYSTICK_HIDAPI": "0"
            }
        )

    def getInGameRatio(self, config, gameResolution, rom):
        if config.get('m3_wideScreen') == "1":
            return 16 / 9
        return 4 / 3
