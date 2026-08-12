from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .pcsx2_config import configureINI
from runtime.retrobox_paths import (
    configure_emulator,
    mkdir_if_not_exists,
)

from ...Emulator import generate_bash_wrapper
from ...exceptions import RetroboxException
from .pcsx2_paths import PCSX2_BIN, _PCSX2_CFGDIR, _PCSX2_XDG, PCSX2_PATCHES, PCSX2_DBFILE
from .pcsx2_controllers import get_wheel_type, is_playing_with_wheel, use_emulator_wheels, wheelTypeMapping

from ... import Command

from ...controller import generate_sdl_game_controller_config, write_sdl_controller_db
from ..Generator import Generator

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

_logger = logging.getLogger(__name__)

class Pcsx2Generator(Generator):
    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "pcsx2",
            "keys": { "exit":          ["KEY_LEFTALT", "KEY_F4"],
                      "menu":          "KEY_ESC",
                      "save_state":    "KEY_F1",
                      "restore_state": "KEY_F3",
                      "previous_slot": [ "KEY_LEFTSHIFT", "KEY_F2" ],
                      "next_slot":     "KEY_F2"
                     }
        }
    
    def usesOpenGLDirectPreload(self, config) -> bool:
        return config.get("pcsx2_gfxbackend") != "12"
    
  

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        with Path("/proc/cpuinfo").open(encoding="utf8") as cpuinfo:
            if not re.search(r'^flags\s*:.*\ssse4_1\W', cpuinfo.read(), re.MULTILINE):
                raise RetroboxException("CPU does not support SSE4.1, which is required by pcsx2.")


        # Remove older config files if present
        inisDir = _PCSX2_CFGDIR / "inis"
        files_to_remove = ["PCSX2_ui.ini", "PCSX2_vm.ini", "GS.ini"]
        for filename in files_to_remove:
            file_path = inisDir / filename
            if file_path.exists():
                file_path.unlink()

        playing_with_wheel = is_playing_with_wheel(system, wheels)

        # Config files
        #configureReg(_PCSX2_CONFIG)
        configureINI(
            system,
            playersControllers,
            metadata,
            guns,
            wheels,
            playing_with_wheel
        )
        #configureAudio(_PCSX2_CONFIG)

        # write our own game_controller_db.txt file before launching the game
        write_sdl_controller_db(playersControllers, PCSX2_DBFILE)

        args = []
        if not configure_emulator(rom):
            args = ["-nogui", "-batch", "-fullscreen", str(rom)]

        envcmd: dict[str, str | Path] = {
            "XDG_CONFIG_HOME": _PCSX2_XDG
        }

        # wheels won't work correctly when SDL_GAMECONTROLLERCONFIG is set. excluding wheels from SDL_GAMECONTROLLERCONFIG doesn't fix too.
        # wheel metadata
        if not use_emulator_wheels(
            playing_with_wheel,
            get_wheel_type(metadata, playing_with_wheel, system.config, wheelTypeMapping)
        ):
            envcmd["SDL_GAMECONTROLLERCONFIG"] = \
                generate_sdl_game_controller_config(playersControllers)

        # ensure we have the patches.zip file to avoid message.
        mkdir_if_not_exists(PCSX2_PATCHES.parent)
        if not PCSX2_PATCHES.exists():
            _logger.debug("patches.zip not found in %s, skipping", PCSX2_PATCHES)

        # state_slot option
        if state_filename := system.config.get('state_filename'):
            args.extend(["-statefile", state_filename])

        if state_slot := system.config.get_str('state_slot'):
            args.extend(["-stateindex", state_slot])
        #_logger.warning("DEBUG pcsx2 command: %s env: %s", commandArray, envcmd)

        command_wrapper = [generate_bash_wrapper(system.config.emulator, PCSX2_BIN, args)]

        comm = Command.Command(
            array=command_wrapper,
            env=envcmd
        )
        return comm
